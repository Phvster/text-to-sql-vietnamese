"""Test cho src/eval/evaluator.py.

Phần lớn test gọi compare_results() với ExecResult tự tạo (không cần DB), để mỗi test
kiểm đúng một quy tắc chấm. Vài test cuối chạy evaluate() trên DB tạm.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from src.db.executor import ExecResult
from src.eval.evaluator import EvalOutcome, compare_results, evaluate, has_order_by


def res(rows: list[tuple], columns: list[str] | None = None, truncated: bool = False) -> ExecResult:
    """ExecResult thành công; tên cột mặc định c0, c1, ... theo số cột của dòng đầu."""
    n_cols = len(rows[0]) if rows else 1
    return ExecResult(rows=rows, columns=columns or [f"c{i}" for i in range(n_cols)],
                      truncated=truncated, error=None)


def err(message: str = "lỗi") -> ExecResult:
    return ExecResult(rows=[], columns=[], truncated=False, error=message)


def check(gold: ExecResult, pred: ExecResult, ordered: bool = False) -> EvalOutcome:
    return compare_results(gold, pred, ordered)


# --------------------------------------------------------------------------- thứ tự dòng


def test_identical_match() -> None:
    assert check(res([(1, "a"), (2, "b")]), res([(1, "a"), (2, "b")])) == EvalOutcome(True, "match")


def test_row_order_ignored_without_order_by() -> None:
    assert check(res([(1,), (2,), (3,)]), res([(3,), (1,), (2,)])).correct


def test_row_order_matters_with_order_by() -> None:
    assert check(res([(1,), (2,)]), res([(2,), (1,)]), ordered=True) == EvalOutcome(False, "mismatch")


def test_same_order_with_order_by_matches() -> None:
    assert check(res([(1,), (2,)]), res([(1,), (2,)]), ordered=True).correct


# --------------------------------------------------------------------------- cột


def test_column_names_ignored() -> None:
    assert check(res([(1,)], ["doanh_thu"]), res([(1,)], ["SUM(total_amount)"])).correct


def test_swapped_columns_match() -> None:
    gold = res([("An", 100), ("Bình", 200)], ["ten", "tien"])
    pred = res([(200, "Bình"), (100, "An")], ["tien", "ten"])
    assert check(gold, pred).correct


def test_swapped_columns_match_when_ordered() -> None:
    gold = res([("An", 100), ("Bình", 200)])
    pred = res([(100, "An"), (200, "Bình")])
    assert check(gold, pred, ordered=True).correct


def test_right_column_values_but_wrong_pairing() -> None:
    """Từng cột đúng giá trị nhưng ghép sai cặp trong dòng: An phải đi với 100, không phải 200."""
    gold = res([("An", 100), ("Bình", 200)])
    pred = res([("An", 200), ("Bình", 100)])
    assert check(gold, pred) == EvalOutcome(False, "mismatch")


def test_same_signature_columns_need_row_check() -> None:
    """Hai cột có cùng đa tập giá trị → phải thử cả hai cách ghép, và chỉ cách đúng mới khớp."""
    gold = res([(1, 2), (2, 1), (3, 3)])
    assert check(gold, res([(2, 1), (1, 2), (3, 3)])).correct  # đổi chỗ 2 cột → vẫn đúng
    assert not check(gold, res([(1, 1), (2, 2), (3, 3)])).correct  # cùng chữ ký từng cột nhưng sai dòng


def test_different_column_count() -> None:
    assert check(res([(1, 2)]), res([(1,)])) == EvalOutcome(False, "column_count")


def test_extra_column_is_wrong() -> None:
    """Hỏi tên, model trả thêm id → sai (chính sách: số cột phải bằng nhau)."""
    assert check(res([("An",)]), res([(7, "An")])) == EvalOutcome(False, "column_count")


def test_many_identical_columns_do_not_hang() -> None:
    row = tuple([1] * 8)  # 8! = 40320 cách ghép nếu không có trần
    gold = res([row, row])
    pred = res([row, tuple([1] * 7 + [2])])
    start = time.monotonic()
    assert not check(gold, pred).correct
    assert time.monotonic() - start < 1.0


# --------------------------------------------------------------------------- đa tập


def test_missing_duplicate_rows() -> None:
    assert check(res([(1,), (1,)]), res([(1,)])) == EvalOutcome(False, "row_count")


def test_multiset_not_set() -> None:
    """Cùng tập {1, 2}, cùng số dòng, nhưng số lần lặp khác → sai (so bằng set sẽ chấm nhầm là đúng)."""
    assert check(res([(1,), (1,), (2,)]), res([(1,), (2,), (2,)])) == EvalOutcome(False, "mismatch")


# --------------------------------------------------------------------------- chuẩn hóa giá trị


@pytest.mark.parametrize("gold, pred, expected", [
    (1 / 3, 0.3333, True),
    (0.1234, 0.1249, False),
    (5, 5.0, True),
    (-0.0, 0.0, True),
    (float("nan"), float("nan"), True),
    (float("inf"), float("inf"), True),
    (12_500_000, 12_500_000, True),
    (None, None, True),
    (None, 0, False),
    (None, "", False),
    ("5", 5, False),
    ("Hà Nội", "hà nội", False),
    ("TP. Hồ Chí Minh", "Sài Gòn", False),
])
def test_value_normalization(gold: object, pred: object, expected: bool) -> None:
    assert check(res([(gold,)]), res([(pred,)])).correct is expected


# --------------------------------------------------------------------------- lỗi và cắt dòng


@pytest.mark.parametrize("gold, pred, reason", [
    (err(), res([(1,)]), "gold_error"),
    (res([(1,)]), err(), "pred_error"),
    (err(), err(), "gold_error"),
    (res([(1,)], truncated=True), res([(1,)], truncated=True), "gold_truncated"),
    (res([(1,)]), res([(1,)], truncated=True), "pred_truncated"),
])
def test_error_and_truncation_reasons(gold: ExecResult, pred: ExecResult, reason: str) -> None:
    assert check(gold, pred) == EvalOutcome(False, reason)


def test_both_empty_same_columns_match() -> None:
    gold = ExecResult(rows=[], columns=["a", "b"], truncated=False, error=None)
    pred = ExecResult(rows=[], columns=["x", "y"], truncated=False, error=None)
    assert check(gold, pred).correct


def test_empty_vs_non_empty() -> None:
    gold = ExecResult(rows=[], columns=["a"], truncated=False, error=None)
    assert check(gold, res([(1,)])) == EvalOutcome(False, "row_count")


# --------------------------------------------------------------------------- has_order_by


@pytest.mark.parametrize("sql, expected", [
    ("SELECT a FROM t ORDER BY a", True),
    ("SELECT a FROM t ORDER BY a DESC LIMIT 5", True),
    ("SELECT a FROM t UNION SELECT b FROM u ORDER BY 1", True),
    ("WITH x AS (SELECT a FROM t) SELECT a FROM x ORDER BY a", True),
    ("(SELECT a FROM t ORDER BY a)", True),
    ("SELECT a FROM t", False),
    ("SELECT a FROM (SELECT a FROM t ORDER BY a)", False),
    ("WITH x AS (SELECT a FROM t ORDER BY a) SELECT a FROM x", False),
    ("SELECT ROW_NUMBER() OVER (ORDER BY a) FROM t", False),
    ("SELECT 'ORDER BY' FROM t", False),
    ("SELEC FROM WHERE ORDER BY", False),
])
def test_has_order_by(sql: str, expected: bool) -> None:
    assert has_order_by(sql) is expected


# --------------------------------------------------------------------------- evaluate (DB tạm)


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / "eval.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, full_name TEXT, city TEXT);
        CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, status TEXT, total_amount INTEGER);
        INSERT INTO customers VALUES (1, 'An', 'Hà Nội'), (2, 'Bình', 'TP. Hồ Chí Minh'), (3, 'Chi', 'Hà Nội');
        INSERT INTO orders VALUES (1, 1, 'delivered', 100), (2, 1, 'cancelled', 50),
                                  (3, 2, 'delivered', 300), (4, 3, 'delivered', 200);
    """)
    conn.commit()
    conn.close()
    return path


def test_evaluate_equivalent_sql_matches(db: Path) -> None:
    gold = ("SELECT DISTINCT c.full_name FROM customers c JOIN orders o ON o.customer_id = c.customer_id "
            "WHERE o.total_amount > 150")
    pred = ("SELECT full_name FROM customers WHERE customer_id IN "
            "(SELECT customer_id FROM orders WHERE total_amount > 150)")
    assert evaluate(gold, pred, db).correct


def test_evaluate_missing_filter_is_wrong(db: Path) -> None:
    gold = "SELECT SUM(total_amount) FROM orders WHERE status != 'cancelled'"
    pred = "SELECT SUM(total_amount) FROM orders"
    assert evaluate(gold, pred, db) == EvalOutcome(False, "mismatch")


def test_evaluate_uses_gold_order_by(db: Path) -> None:
    gold = "SELECT full_name FROM customers ORDER BY full_name DESC"
    assert not evaluate(gold, "SELECT full_name FROM customers ORDER BY full_name", db).correct
    assert evaluate("SELECT full_name FROM customers", "SELECT full_name FROM customers ORDER BY 1 DESC", db).correct


def test_evaluate_malicious_pred_is_error_and_db_unchanged(db: Path) -> None:
    gold = "SELECT COUNT(*) FROM customers"
    assert evaluate(gold, "DROP TABLE customers", db) == EvalOutcome(False, "pred_error")
    assert evaluate(gold, gold, db).correct  # bảng vẫn còn


def test_evaluate_broken_gold(db: Path) -> None:
    assert evaluate("SELEC 1", "SELECT 1", db) == EvalOutcome(False, "gold_error")


# =========================================================================== Bổ sung sau review


def test_multiset_with_matching_column_signatures() -> None:
    """Mỗi cột có cùng đa tập giá trị, nhưng đa tập DÒNG khác → sai. Bắt lỗi đổi Counter thành set."""
    gold = res([(1, "a"), (1, "a"), (1, "b"), (2, "a"), (2, "b"), (2, "b")])
    pred = res([(1, "a"), (1, "b"), (1, "b"), (2, "a"), (2, "a"), (2, "b")])
    assert check(gold, pred) == EvalOutcome(False, "mismatch")


def test_identity_mapping_is_not_the_right_one() -> None:
    """Hai cột cùng chữ ký, cách ghép giữ nguyên thứ tự sai, chỉ cách đổi chỗ mới đúng."""
    assert check(res([(1, 2), (2, 1), (3, 4)]), res([(2, 1), (1, 2), (4, 3)])).correct


@pytest.mark.parametrize("n_cols", [12, 20])
def test_one_column_without_partner_does_not_hang(n_cols: int) -> None:
    """S1: kiểu bảng pivot nhiều cột 0, model sai đúng 1 cột → trước đây mất hàng phút."""
    gold = res([tuple([0] * (n_cols - 1) + [5])])
    pred = res([tuple([0] * n_cols)])
    start = time.monotonic()
    assert check(gold, pred) == EvalOutcome(False, "mismatch")
    assert time.monotonic() - start < 1.0


@pytest.mark.parametrize("ordered", [False, True])
def test_reversed_columns_with_shared_signatures(ordered: bool) -> None:
    """S2: 8 cột cùng chữ ký {1, 2}; cách ghép đúng nằm ngoài 1000 cách đầu → trước đây bị chấm sai."""
    gold_rows = [(1, 2, 1, 2, 2, 1, 1, 2), (2, 1, 2, 1, 1, 2, 2, 1)]
    pred_rows = [row[::-1] for row in gold_rows]
    assert check(res(gold_rows), res(pred_rows), ordered=ordered).correct


def test_large_table_reversed_columns() -> None:
    """S2: 1000 dòng × 10 cột, mỗi cột là một hoán vị khác nhau của 0..999 (cùng chữ ký)."""
    import random
    rng = random.Random(0)
    cols = []
    for _ in range(10):
        values = list(range(1000))
        rng.shuffle(values)
        cols.append(values)
    gold_rows = list(zip(*cols))
    pred_rows = [row[::-1] for row in gold_rows]
    rng.shuffle(pred_rows)
    start = time.monotonic()
    assert check(res(gold_rows), res(pred_rows)).correct
    assert time.monotonic() - start < 2.0


def test_ordered_swapped_columns_but_rows_out_of_order() -> None:
    gold = res([("An", 1), ("Bình", 2)])
    pred = res([(2, "Bình"), (1, "An")])
    assert check(gold, pred, ordered=False).correct
    assert check(gold, pred, ordered=True) == EvalOutcome(False, "mismatch")


@pytest.mark.parametrize("sql, expected", [
    ("SELECT a FROM t ORDER BY a; -- ghi chú", True),  # M1
    ("SELECT a FROM t ORDER BY a;", True),
    ("SELECT a FROM t ORDER BY NULL", False),  # M3
    ("SELECT a FROM t ORDER BY 'x'", False),
    ("SELECT a FROM t ORDER BY 1", True),  # ORDER BY 1 = theo cột 1, có ý nghĩa
    ("SELECT a FROM t ORDER BY NULL, a", True),
    ("SELECT a FROM t EXCEPT SELECT b FROM u ORDER BY 1 LIMIT 3", True),
    ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 3) SELECT x FROM c ORDER BY x", True),
    ("SELECT a FROM t /* ORDER BY a */", False),
    ("SELECT a FROM t WHERE a IN (SELECT a FROM t ORDER BY a LIMIT 1)", False),
    ("SELECT 1; SELECT 2 ORDER BY 1", False),  # nhiều câu lệnh: executor cũng từ chối
])
def test_has_order_by_after_review(sql: str, expected: bool) -> None:
    assert has_order_by(sql) is expected


def test_evaluate_gold_with_trailing_comment_keeps_order(db: Path) -> None:
    gold = "SELECT full_name FROM customers ORDER BY full_name DESC; -- giảm dần"
    pred = "SELECT full_name FROM customers ORDER BY full_name"
    assert evaluate(gold, pred, db) == EvalOutcome(False, "mismatch")


@pytest.mark.parametrize("gold, pred, expected", [
    (float("nan"), "<NaN>", False),  # L2: chuỗi "<NaN>" không được trùng với NaN
    (float("inf"), float("-inf"), False),
])
def test_special_values_after_review(gold: object, pred: object, expected: bool) -> None:
    assert check(res([(gold,)]), res([(pred,)])).correct is expected


def test_order_by_ties_is_known_limitation(db: Path) -> None:
    """M2 (hạn chế đã biết): Hà Nội có 2 khách, TP.HCM 1 khách → không hòa, nên ổn.
    Nếu đáp án ORDER BY một cột có giá trị hòa thì thứ tự các dòng hòa không xác định.
    Quy ước dataset (T2): SQL đáp án có ORDER BY phải có khóa phụ phá hòa."""
    gold = "SELECT city, COUNT(*) AS n FROM customers GROUP BY city ORDER BY n DESC, city"
    pred = "SELECT city, COUNT(*) FROM customers GROUP BY city ORDER BY COUNT(*) DESC, city ASC"
    assert evaluate(gold, pred, db).correct


def test_search_limit_reported_separately(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vượt trần tìm kiếm → reason riêng 'mapping_limit', không lẫn vào 'mismatch'."""
    from src.eval import evaluator
    monkeypatch.setattr(evaluator, "MAX_SEARCH_STEPS", 1)
    gold = res([(1, 2), (2, 1), (3, 4)])
    pred = res([(2, 1), (1, 2), (4, 3)])  # cần thử ít nhất 2 bước
    assert check(gold, pred) == EvalOutcome(False, "mapping_limit")
