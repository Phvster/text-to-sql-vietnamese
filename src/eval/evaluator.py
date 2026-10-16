"""Chấm execution accuracy: so KẾT QUẢ CHẠY của SQL model với SQL đáp án (xem .claude/rules/eval.md).

Quy tắc:
- Bỏ qua tên cột; cột khác thứ tự vẫn được chấm đúng (thử ghép cột).
- Không phụ thuộc thứ tự dòng, TRỪ KHI SQL đáp án có ORDER BY ở cấp ngoài cùng.
- So đa tập (đếm cả dòng trùng), không phải tập: quên DISTINCT là sai.
- Số thực làm tròn FLOAT_DIGITS chữ số trước khi so. NULL bằng NULL.

compare_results() là hàm thuần (không cần DB) để test logic chấm bằng dữ liệu tự tạo;
evaluate() chạy hai câu SQL qua src/db/executor.py rồi gọi compare_results().
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlglot import exp

from src.db.executor import DEFAULT_DB, ExecResult, _parse_single, execute

FLOAT_DIGITS = 4
MAX_SEARCH_STEPS = 2000  # trần số bước thử ghép cột (chỉ khi không có thứ tự), tránh treo


class _NaNType:
    """nan != nan, nên thay mọi NaN bằng một đối tượng duy nhất để hai NaN bằng nhau.
    Dùng đối tượng riêng thay vì chuỗi để không trùng với chuỗi "<NaN>" có thật trong dữ liệu."""

    def __repr__(self) -> str:
        return "NaN"


_NAN = _NaNType()

Row = tuple[Hashable, ...]
Column = tuple[Hashable, ...]  # giá trị của một cột theo thứ tự dòng


@dataclass(frozen=True)
class EvalOutcome:
    correct: bool
    # match | pred_error | gold_error | pred_truncated | gold_truncated | column_count | row_count
    # | mismatch | mapping_limit (vượt trần tìm cách ghép cột — hiếm, đếm riêng)
    reason: str


def evaluate(gold_sql: str, pred_sql: str, db_path: Path = DEFAULT_DB) -> EvalOutcome:
    """Chạy cả hai câu qua executor (guardrail: không gọi sqlite3 trực tiếp) rồi so kết quả."""
    gold = execute(gold_sql, db_path)
    pred = execute(pred_sql, db_path)
    return compare_results(gold, pred, ordered=has_order_by(gold_sql))


def has_order_by(sql: str) -> bool:
    """True nếu câu SQL có ORDER BY ở cấp ngoài cùng.

    ORDER BY trong subquery, CTE hay OVER (...) không quyết định thứ tự dòng của kết quả cuối,
    nên không tính. sqlglot gắn ORDER BY ngoài cùng vào gốc cây (kể cả sau UNION / sau WITH).
    Dùng chung _parse_single với executor để hai bên hiểu câu SQL giống nhau
    (vd "... ORDER BY a; -- ghi chú": parse_one sẽ lỗi, nhưng executor vẫn chạy câu này).
    """
    try:
        root = _parse_single(sql)
    except Exception:  # noqa: BLE001 — không parse được thì executor cũng từ chối → gold_error
        return False
    if isinstance(root, str):  # rỗng / nhiều câu lệnh: executor cũng từ chối
        return False
    while isinstance(root, exp.Subquery):  # "(SELECT ... ORDER BY ...)" — bóc lớp ngoặc
        root = root.this
    order = root.args.get("order")
    return order is not None and not all(_is_constant_key(o.this) for o in order.expressions)


def _is_constant_key(key: exp.Expression) -> bool:
    """ORDER BY NULL / ORDER BY 'x' không sắp xếp gì. ORDER BY 1 thì có (nghĩa là theo cột thứ 1)."""
    return isinstance(key, exp.Null) or (isinstance(key, exp.Literal) and key.is_string)


def compare_results(gold: ExecResult, pred: ExecResult, ordered: bool) -> EvalOutcome:
    """So hai kết quả. Kiểm tra rẻ trước (lỗi, cắt, số cột, số dòng), so giá trị sau cùng."""
    if gold.error is not None:
        return EvalOutcome(False, "gold_error")  # lỗi dataset, không phải lỗi model
    if pred.error is not None:
        return EvalOutcome(False, "pred_error")
    if gold.truncated:
        return EvalOutcome(False, "gold_truncated")  # đáp án > MAX_ROWS dòng: câu hỏi cần sửa
    if pred.truncated:
        return EvalOutcome(False, "pred_truncated")  # đáp án đủ dòng mà model vượt trần → chắc chắn sai
    if len(gold.columns) != len(pred.columns):
        return EvalOutcome(False, "column_count")
    if len(gold.rows) != len(pred.rows):
        return EvalOutcome(False, "row_count")

    gold_rows = _normalize_rows(gold.rows)
    pred_rows = _normalize_rows(pred.rows)
    matched = _columns_match(gold_rows, pred_rows, len(gold.columns), ordered)
    if matched is None:
        return EvalOutcome(False, "mapping_limit")  # tách riêng để đếm được, không lẫn vào mismatch
    return EvalOutcome(True, "match") if matched else EvalOutcome(False, "mismatch")


# --------------------------------------------------------------------------- chuẩn hóa giá trị


def _normalize_value(value: object) -> Hashable:
    """Đưa giá trị về dạng so sánh được.

    Chỉ chuẩn hóa số thực. Chuỗi giữ nguyên văn: "hà nội" khác "Hà Nội" — đó chính là lỗi
    lệch giá trị cần đo. 5 và 5.0 bằng nhau sẵn trong Python (cùng hash) nên không cần đổi int.
    """
    if isinstance(value, float):
        if math.isnan(value):
            return _NAN
        return round(value, FLOAT_DIGITS) + 0.0  # + 0.0 biến -0.0 thành 0.0
    return value  # type: ignore[return-value]


def _normalize_rows(rows: Sequence[tuple]) -> list[Row]:
    return [tuple(_normalize_value(v) for v in row) for row in rows]


# --------------------------------------------------------------------------- ghép cột + so dòng


def _columns_match(gold_rows: list[Row], pred_rows: list[Row], n_cols: int, ordered: bool) -> bool | None:
    """Có cách sắp lại cột của model để kết quả khớp đáp án không? None = vượt trần tìm kiếm."""
    gold_cols = _columns(gold_rows, n_cols)
    pred_cols = _columns(pred_rows, n_cols)
    if ordered:
        # Thứ tự dòng cố định → mỗi cột là một vector cố định. Khớp được khi và chỉ khi hai bên có
        # cùng đa tập vector cột (ghép cột có vector giống nhau). Chính xác, không cần tìm kiếm.
        return Counter(gold_cols) == Counter(pred_cols)
    return _search_unordered(gold_rows, pred_rows, gold_cols, pred_cols)


def _columns(rows: list[Row], n_cols: int) -> list[Column]:
    return [tuple(row[i] for row in rows) for i in range(n_cols)]


def _signature(col: Column) -> frozenset:
    """Chữ ký cột = đa tập giá trị (không quan tâm thứ tự dòng). frozenset để dùng được làm khóa."""
    return frozenset(Counter(col).items())


def _search_unordered(gold_rows: list[Row], pred_rows: list[Row],
                      gold_cols: list[Column], pred_cols: list[Column]) -> bool | None:
    """Quay lui tìm cách ghép: mapping[i] = cột của model ứng với cột i của đáp án.

    Ba cách cắt nhánh để không bùng nổ tổ hợp:
    1. Hai bên phải có cùng đa tập chữ ký cột — không thì chắc chắn sai, khỏi tìm.
    2. Cột đáp án i chỉ thử với cột model cùng chữ ký; cột model giống hệt nhau chỉ thử một lần.
    3. Sau mỗi bước, đa tập các dòng chiếu lên những cột đã ghép phải khớp đáp án — sai thì bỏ nhánh ngay.
    Tới cột cuối mà vẫn khớp nghĩa là toàn bộ đa tập dòng khớp.
    """
    gold_sigs = [_signature(c) for c in gold_cols]
    pred_sigs = [_signature(c) for c in pred_cols]
    if Counter(gold_sigs) != Counter(pred_sigs):
        return False
    gold_proj = [Counter(row[: i + 1] for row in gold_rows) for i in range(len(gold_cols))]
    steps = [0]

    def extend(mapping: tuple[int, ...]) -> bool | None:
        i = len(mapping)
        if i == len(gold_cols):
            return True
        tried: set[Column] = set()
        for j, col in enumerate(pred_cols):
            if j in mapping or pred_sigs[j] != gold_sigs[i] or col in tried:
                continue
            tried.add(col)
            steps[0] += 1
            if steps[0] > MAX_SEARCH_STEPS:
                return None
            candidate = mapping + (j,)
            if Counter(tuple(row[k] for k in candidate) for row in pred_rows) != gold_proj[i]:
                continue
            result = extend(candidate)
            if result is not False:  # True (khớp) hoặc None (vượt trần) → dừng luôn
                return result
        return False

    return extend(())
