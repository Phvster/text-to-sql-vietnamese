"""C3 — few-shot: chèn vài cặp (câu hỏi, SQL đáp án) giống câu đang hỏi nhất vào prompt.

Kho ví dụ LUÔN là dev.jsonl (đường dẫn cố định, không có tham số đổi) — guardrail: câu test không bao giờ
thành ví dụ. Khi chấm dev thì bỏ chính câu đang hỏi (leave-one-out), nếu không model sẽ thấy sẵn đáp án.

Độ giống = Jaccard trên cặp từ liền nhau (bigram), dùng chung với cảnh báo W_SIMILAR của bộ kiểm dataset:
không cần thêm thư viện hay API embedding, và đã hiệu chỉnh trên dev.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.eval.dataset import jaccard, load_jsonl, question_bigrams

POOL_PATH = Path(__file__).resolve().parents[2] / "data" / "questions" / "dev.jsonl"
K_EXAMPLES = 3


@lru_cache(maxsize=1)
def load_pool() -> tuple[dict, ...]:
    """Các câu dev có đáp án — kho ví dụ cho C3/C4."""
    records, issues = load_jsonl(POOL_PATH)
    if issues:
        raise RuntimeError("dev.jsonl có lỗi định dạng; chạy scripts/check_dataset.py trước.")
    return tuple(r for r in records if r.get("sql"))


def select_examples(question: str, pool: tuple[dict, ...], k: int = K_EXAMPLES,
                    exclude_id: str | None = None) -> list[dict]:
    """k ví dụ giống nhất. Hòa điểm thì xếp theo id → luôn ra cùng kết quả (tất định)."""
    grams = question_bigrams(question)
    candidates = [r for r in pool if r["id"] != exclude_id]
    ranked = sorted(candidates, key=lambda r: (-jaccard(grams, question_bigrams(r["question"])), r["id"]))
    return ranked[:k]
