"""C2 — schema linking: chỉ đưa vào prompt những bảng liên quan tới câu hỏi.

Một lời gọi LLM chọn bảng (enum trong schema đầu ra bắt model chỉ chọn tên có thật).
Rủi ro của C2: chọn THIẾU bảng → model không thể viết SQL đúng. Vì vậy đo "linking recall" trên dev:
tỉ lệ bảng mà SQL đáp án dùng có nằm trong các bảng được chọn. Recall thấp → lỗi do bước linking,
không phải do bước viết SQL.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from src.pipeline.llm import LLM, Usage
from src.pipeline.prompts import build_linking_system, linking_output_schema
from src.pipeline.schema import TableInfo, table_names


@dataclass
class LinkingResult:
    tables: list[str] | None  # None = fallback: dùng toàn bộ schema (lỗi API hoặc model không chọn bảng nào)
    usage: Usage
    cost: float
    latency_s: float = 0.0
    error: str | None = None


def link_tables(llm: LLM, question: str, schema: tuple[TableInfo, ...]) -> LinkingResult:
    names = table_names(schema)
    reply = llm.complete(build_linking_system(schema), question, linking_output_schema(names))
    chosen = None
    if reply.data is not None:
        picked = [t for t in names if t in set(reply.data.get("tables", []))]  # giữ thứ tự cố định
        chosen = picked or None
    return LinkingResult(tables=chosen, usage=reply.usage, cost=reply.cost,
                         latency_s=reply.latency_s, error=reply.error)


def gold_tables(sql: str) -> set[str]:
    """Các bảng thật sự dùng trong SQL đáp án, viết thường (SQLite không phân biệt hoa thường tên bảng:
    ORDERS = orders). Bỏ tên CTE — đó là bảng tạm, không phải bảng trong DB."""
    tree = sqlglot.parse_one(sql, read="sqlite")
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    return {t.name.lower() for t in tree.find_all(exp.Table) if t.name and t.name.lower() not in cte_names}


def linking_recall(gold_sql: str, chosen: list[str] | None) -> float | None:
    """Tỉ lệ bảng đáp án cần mà bước linking đã chọn.

    chosen=None (fallback dùng toàn bộ schema) → None: loại khỏi trung bình recall và đếm riêng,
    vì câu đó thực chất chạy như C1 — tính là 1.0 sẽ làm C2 trông tốt hơn thực tế.
    """
    if chosen is None:
        return None
    needed = gold_tables(gold_sql)
    if not needed:
        return 1.0
    return len(needed & {t.lower() for t in chosen}) / len(needed)
