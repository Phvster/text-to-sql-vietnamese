"""Demo: câu hỏi tiếng Việt → SQL → bảng kết quả. Chạy local: `python app.py` rồi mở http://127.0.0.1:7860.

Mỗi câu hỏi gọi API thật (Haiku C3 ~ $0.0002/câu). API key đọc từ .env như pipeline.
- Dùng lại answer_question() của pipeline → demo chạy đúng cấu hình đã đánh giá, không có bản "demo riêng".
- SQL chạy qua src/db/executor.py (read-only, 1 câu SELECT, timeout, tối đa 1000 dòng).
- gradio chỉ import trong build_ui() → test và pipeline không cần cài gradio.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.db.executor import DEFAULT_DB, execute
from src.pipeline.fewshot import load_pool
from src.pipeline.llm import LLM, MODELS, AnthropicLLM
from src.pipeline.prompts import CONFIGS, FEWSHOT_CONFIGS
from src.pipeline.run import answer_question
from src.pipeline.schema import load_schema

MAX_QUESTION_CHARS = 500  # chặn câu dán dài → tốn token
CONFIG_LABELS = {
    "C0": "C0 — schema only (baseline)",
    "C1": "C1 — + sample values",
    "C2": "C2 — + schema linking",
    "C3": "C3 — + few-shot examples (best)",
    "C4": "C4 — + self-repair",
}
N_EXAMPLES = 6


@dataclass
class DemoResult:
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    message: str = ""
    cost: float = 0.0
    latency_s: float = 0.0
    tables: list[str] | None = None   # C2+: bảng mà bước linking chọn
    shots: list[str] = field(default_factory=list)  # C3+: id ví dụ few-shot (từ dev)


def ask(question: str, config: str = "C3", model: str = "haiku", llm: LLM | None = None) -> DemoResult:
    """Một lượt hỏi. llm chỉ để test thay bằng FakeLLM."""
    question = (question or "").strip()
    if not question:
        return DemoResult(message="Hãy nhập một câu hỏi.")
    if len(question) > MAX_QUESTION_CHARS:
        return DemoResult(message=f"Câu hỏi quá dài (> {MAX_QUESTION_CHARS} ký tự).")
    if config not in CONFIGS or model not in MODELS:
        return DemoResult(message="Cấu hình hoặc model không hợp lệ.")
    pool = load_pool() if config in FEWSHOT_CONFIGS else ()
    # câu trùng nguyên văn một câu dev → mang id của nó để leave-one-out loại chính nó khỏi ví dụ,
    # giống lúc đánh giá (nếu không, model nhận luôn đáp án của câu đó làm ví dụ đầu tiên)
    qid = next((q["id"] for q in pool if q["question"].strip() == question), "demo")
    try:
        llm = llm or AnthropicLLM(model)
        record, sql = answer_question({"id": qid, "question": question}, config, llm, load_schema(DEFAULT_DB),
                                      pool=pool, db_path=DEFAULT_DB)
    except Exception as exc:  # thiếu API key, 401/400... — giao diện báo lỗi thay vì sập
        return DemoResult(message=f"Lỗi khi gọi model (kiểm tra ANTHROPIC_API_KEY trong .env): "
                                  f"{type(exc).__name__}: {exc}")
    result = DemoResult(sql=sql or record.first_sql or "", cost=record.cost, latency_s=record.latency_s,
                        tables=record.tables, shots=record.shots)
    notes = []
    if record.linking_error is not None or record.linking_fallback:
        notes.append("bước chọn bảng lỗi → dùng toàn bộ schema")
    if record.repair_error is not None:
        notes.append(f"lỗi API ở lượt sửa → giữ SQL trước đó ({record.repair_error})")
    if record.error is not None and not record.refused:
        result.message = f"Lỗi API: {record.error}"
    elif record.refused and record.first_sql is not None:
        result.message = "Model từ chối ở lượt sửa (C4) — SQL hiển thị là bản đầu tiên, không được chạy."
    elif record.refused:
        result.message = "Model từ chối: câu hỏi yêu cầu sửa/xóa dữ liệu hoặc không trả lời được bằng CSDL này."
    elif sql is None:
        result.message = "Model không trả về SQL."
    else:
        out = execute(sql)
        if out.error is not None:
            result.message = f"SQL bị từ chối hoặc lỗi khi chạy: {out.error}"
        else:
            result.columns, result.rows = out.columns, out.rows
            result.message = f"{len(out.rows)} dòng" + (" (đã cắt ở 1000 dòng)" if out.truncated else "")
    if notes:
        result.message += " (" + "; ".join(notes) + ")"
    return result


def demo_examples(pool: tuple[dict, ...] | None = None, n: int = N_EXAMPLES) -> list[str]:
    """Câu ví dụ trên giao diện — CHỈ lấy từ dev (kho few-shot), không bao giờ từ test."""
    pool = load_pool() if pool is None else pool
    step = max(1, len(pool) // n)
    return [q["question"] for q in pool[::step][:n]]


def _details(result: DemoResult) -> str:
    parts = [result.message, f"chi phí ${result.cost:.5f}", f"{result.latency_s:.1f}s"]
    if result.tables is not None:
        parts.append("bảng đã chọn: " + (", ".join(result.tables) or "-"))
    if result.shots:
        parts.append("ví dụ: " + ", ".join(result.shots))
    return " · ".join(parts)


def build_ui():
    import gradio as gr  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415  (đi kèm gradio)

    def on_ask(question: str, config: str, model: str, spent: float):
        result = ask(question, config, model)
        spent += result.cost
        rows = [tuple(v.hex() if isinstance(v, bytes) else v for v in row) for row in result.rows]  # BLOB → hex
        table = pd.DataFrame(rows, columns=result.columns) if result.columns else pd.DataFrame()
        return result.sql, table, _details(result), f"Tổng chi phí phiên này: ${spent:.5f}", spent

    with gr.Blocks(title="Vietnamese Text-to-SQL") as ui:
        gr.Markdown("# Vietnamese Text-to-SQL\nHỏi bằng tiếng Việt về CSDL bán hàng (khách hàng, sản phẩm, "
                    "đơn hàng, đánh giá). SQL chạy read-only.")
        spent = gr.State(0.0)
        question = gr.Textbox(label="Câu hỏi", lines=2, max_length=MAX_QUESTION_CHARS)
        with gr.Row():
            config = gr.Dropdown([(label, c) for c, label in CONFIG_LABELS.items()], value="C3", label="Cấu hình")
            model = gr.Radio([("Haiku (~$0.0002/câu)", "haiku"), ("Sonnet (~$0.004/câu)", "sonnet")],
                             value="haiku", label="Model")
        button = gr.Button("Hỏi", variant="primary")
        gr.Examples(demo_examples(), inputs=[question], label="Ví dụ (từ tập dev)")
        sql = gr.Code(label="SQL sinh ra", language="sql")
        status = gr.Markdown()
        table = gr.Dataframe(label="Kết quả", interactive=False)
        total = gr.Markdown()
        outputs = [sql, table, status, total, spent]
        button.click(on_ask, [question, config, model, spent], outputs)
        question.submit(on_ask, [question, config, model, spent], outputs)
    return ui


if __name__ == "__main__":
    build_ui().launch(server_name="127.0.0.1", share=False)
