"""Gọi Claude API và tính chi phí.

- Không gửi temperature/top_p/top_k: từ API version 2026-10-21 các tham số này bị từ chối (400),
  nên kết quả có thể dao động giữa các lần chạy → dùng --repeats ở scripts/run_pipeline.py để đo.
- Tắt thinking cho cả hai model (quyết định của dự án, để so sánh công bằng và rẻ):
  Haiku 5.5 nhận {"type": "disabled"}; Sonnet 5.5 KHÔNG nhận "disabled" (400) → dùng {"type": "between_tools"}.
- Đầu ra cố định bằng structured output (output_config.format) → luôn là JSON hợp lệ theo schema.
- Lỗi tạm thời (mạng, 408, 409, 429, 5xx, 529 quá tải): SDK tự retry (max_retries). Hết lượt retry thì ghi lỗi
  vào kết quả, không dừng cả lượt chạy. Lỗi cấu hình (400, 401, 403, 404...) thì raise ngay — chạy tiếp chỉ tốn tiền.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Protocol

import anthropic


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    input_per_mtok: float
    output_per_mtok: float
    thinking: dict


MODELS: dict[str, ModelSpec] = {
    "haiku": ModelSpec("claude-haiku-5-5", 0.10, 0.50, {"type": "disabled"}),
    "sonnet": ModelSpec("claude-sonnet-5-5", 2.00, 10.00, {"type": "between_tools"}),
}
CACHE_WRITE_MULTIPLIER = 1.25  # ghi cache (TTL 5 phút) đắt hơn input thường 25%
CACHE_READ_MULTIPLIER = 0.10   # đọc cache rẻ hơn 90%
MAX_TOKENS = 2048              # SQL ngắn; đủ dư cho câu dài
TRANSIENT_STATUS = {408, 409, 429}  # cộng mọi mã >= 500 (gồm 529 quá tải)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    thinking_tokens: int = 0  # phải luôn bằng 0 vì đã tắt thinking — ghi lại để chứng minh

    def add(self, other: "Usage") -> "Usage":
        return Usage(*(a + b for a, b in zip(self.as_tuple(), other.as_tuple())))

    def as_tuple(self) -> tuple[int, int, int, int, int]:
        return (self.input_tokens, self.output_tokens, self.cache_write_tokens,
                self.cache_read_tokens, self.thinking_tokens)


def cost_usd(spec: ModelSpec, usage: Usage) -> float:
    per_input = spec.input_per_mtok / 1_000_000
    return (usage.input_tokens * per_input
            + usage.cache_write_tokens * per_input * CACHE_WRITE_MULTIPLIER
            + usage.cache_read_tokens * per_input * CACHE_READ_MULTIPLIER
            + usage.output_tokens * spec.output_per_mtok / 1_000_000)


@dataclass
class LLMReply:
    data: dict | None             # JSON đã parse theo schema; None nếu lỗi / bị từ chối
    usage: Usage = field(default_factory=Usage)
    cost: float = 0.0
    latency_s: float = 0.0
    safety_refusal: bool = False  # bộ lọc an toàn của API chặn (stop_reason == "refusal")
    error: str | None = None


class LLM(Protocol):
    """Giao diện chung — pipeline chỉ biết hàm này, nên test dùng được LLM giả không tốn tiền."""
    name: str

    def complete(self, system: str, user: str, schema: dict) -> LLMReply: ...


class AnthropicLLM:
    def __init__(self, model_key: str, client: anthropic.Anthropic | None = None) -> None:
        self.spec = MODELS[model_key]
        self.name = model_key
        if client is None:
            from dotenv import load_dotenv  # đọc ANTHROPIC_API_KEY từ .env vào biến môi trường
            load_dotenv()
            client = anthropic.Anthropic(max_retries=4)
        self.client = client

    def complete(self, system: str, user: str, schema: dict) -> LLMReply:
        start = time.monotonic()
        try:
            response = self.client.messages.create(
                model=self.spec.model_id,
                max_tokens=MAX_TOKENS,
                # cache_control ở block cuối của system → cache phần luật + schema dùng chung cho mọi câu
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                thinking=self.spec.thinking,
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.APIConnectionError as exc:  # gồm cả timeout
            return LLMReply(data=None, latency_s=time.monotonic() - start, error=f"{type(exc).__name__}: {exc}")
        except anthropic.APIStatusError as exc:
            if exc.status_code in TRANSIENT_STATUS or exc.status_code >= 500:
                return LLMReply(data=None, latency_s=time.monotonic() - start,
                                error=f"{type(exc).__name__} {exc.status_code}: {exc.message}")
            raise  # 400 / 401 / 403 / 404 ...: lỗi cấu hình hoặc key → dừng ngay
        return self._parse(response, time.monotonic() - start)

    def _parse(self, response: anthropic.types.Message, latency: float) -> LLMReply:
        u = response.usage
        details = getattr(u, "output_tokens_details", None)
        usage = Usage(u.input_tokens, u.output_tokens,
                      u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0,
                      (getattr(details, "thinking_tokens", 0) or 0) if details is not None else 0)
        reply = LLMReply(data=None, usage=usage, cost=cost_usd(self.spec, usage), latency_s=latency)
        if response.stop_reason == "refusal":
            reply.safety_refusal = True
            return reply
        if response.stop_reason not in ("end_turn", "stop_sequence"):
            reply.error = f"stop_reason={response.stop_reason}"  # max_tokens, context window, pause_turn...
            return reply
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            reply.data = json.loads(text)
        except json.JSONDecodeError as exc:
            reply.error = f"JSON không hợp lệ: {exc}"
        return reply


class FakeLLM:
    """LLM giả cho test: trả lời định sẵn theo câu hỏi, không gọi mạng.

    sql_answers: câu hỏi → {"refuse": ..., "sql": ...}; table_answers: câu hỏi → {"tables": [...]} (bước C2).
    Phân biệt hai loại lời gọi bằng schema đầu ra.
    """

    def __init__(self, sql_answers: dict[str, dict], table_answers: dict[str, dict] | None = None,
                 name: str = "fake") -> None:
        self.sql_answers = sql_answers
        self.table_answers = table_answers or {}
        self.name = name
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, schema: dict) -> LLMReply:
        self.calls.append((system, user))
        answers = self.table_answers if "tables" in schema["properties"] else self.sql_answers
        data = answers.get(user)
        usage = Usage(input_tokens=100, output_tokens=20)
        if data is None:
            return LLMReply(data=None, usage=usage, error="FakeLLM: không có câu trả lời")
        return LLMReply(data=data, usage=usage, cost=0.0)
