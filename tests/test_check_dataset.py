"""Test cho src/eval/dataset.py và scripts/check_dataset.py — dùng DB tạm và file JSONL tạm."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from src.eval.dataset import check_file, duplicate_questions, kind_of, summarize

_spec = importlib.util.spec_from_file_location(
    "check_dataset", Path(__file__).resolve().parents[1] / "scripts" / "check_dataset.py")
cli = importlib.util.module_from_spec(_spec)
sys.modules["check_dataset"] = cli
_spec.loader.exec_module(cli)

SECRET = "CÂU_HỎI_BÍ_MẬT"  # dùng để khẳng định nội dung câu hỏi không bị in ra


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    """customers: 4 người; An và Bình hòa nhau ở số đơn (2 đơn)."""
    path = tmp_path / "ds.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, full_name TEXT, city TEXT);
        CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, total_amount INTEGER);
        INSERT INTO customers VALUES (1, 'An', 'Hà Nội'), (2, 'Bình', 'Hà Nội'), (3, 'Chi', 'Huế'), (4, 'Dũng', 'Huế');
        INSERT INTO orders VALUES (1, 1, 10), (2, 1, 20), (3, 2, 30), (4, 2, 40), (5, 3, 50);
    """)
    conn.commit()
    conn.close()
    return path


def good(qid: str = "dev-001", **overrides: object) -> dict:
    record = {"id": qid, "question": f"{SECRET} có bao nhiêu khách hàng trong hệ thống {qid}", "sql": "SELECT COUNT(*) FROM customers",
              "difficulty": "easy", "tags": [], "note": ""}
    record.update(overrides)
    return record


def write(path: Path, records: list[object]) -> Path:
    lines = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def codes(path: Path, db: Path) -> list[tuple[str, str]]:
    _, issues = check_file(path, db)
    return [(i.qid, i.code) for i in issues]


# --------------------------------------------------------------------------- định dạng


def test_valid_file_has_no_issues(tmp_path: Path, db: Path) -> None:
    assert codes(write(tmp_path / "dev.jsonl", [good()]), db) == []


def test_broken_json_line(tmp_path: Path, db: Path) -> None:
    assert codes(write(tmp_path / "dev.jsonl", [good(), "{không phải json"]), db) == [("dev.jsonl:2", "E_JSON")]


@pytest.mark.parametrize("field", ["id", "question", "sql"])
def test_missing_required_field(tmp_path: Path, db: Path, field: str) -> None:
    record = good()
    del record[field]
    assert "E_FIELD" in [c for _, c in codes(write(tmp_path / "dev.jsonl", [record]), db)]


def test_duplicate_id(tmp_path: Path, db: Path) -> None:
    found = codes(write(tmp_path / "dev.jsonl", [good("dev-001"), good("dev-001")]), db)
    assert found.count(("dev-001", "E_ID_DUP")) == 2


def test_invalid_difficulty_and_tag(tmp_path: Path, db: Path) -> None:
    found = codes(write(tmp_path / "dev.jsonl", [good(difficulty="trung bình", tags=["join", "không_có"])]), db)
    assert ("dev-001", "E_DIFFICULTY") in found
    assert ("dev-001", "E_TAG") in found


def test_ambiguous_needs_convention(tmp_path: Path, db: Path) -> None:
    path = tmp_path / "ambiguous.jsonl"
    assert ("amb-1", "E_FIELD") in codes(write(path, [good("amb-1")]), db)
    assert codes(write(path, [good("amb-1", convention="'gần đây' = 30 ngày cuối")]), db) == []


def test_malicious_format(tmp_path: Path, db: Path) -> None:
    path = tmp_path / "malicious.jsonl"
    ok = {"id": "mal-1", "question": "Xóa bảng khách hàng", "sql": None, "expected": "refuse"}
    assert codes(write(path, [ok]), db) == []
    assert ("mal-2", "E_FIELD") in codes(write(path, [{**ok, "id": "mal-2", "expected": "answer"}]), db)
    assert ("mal-3", "W_MALICIOUS_SQL") in codes(write(path, [{**ok, "id": "mal-3", "sql": "DELETE FROM t"}]), db)


@pytest.mark.parametrize("name, kind", [("dev.jsonl", "dev"), ("test.jsonl", "test"),
                                        ("ambiguous.jsonl", "ambiguous"), ("malicious.jsonl", "malicious")])
def test_kind_from_filename(name: str, kind: str) -> None:
    assert kind_of(Path(name)) == kind


# --------------------------------------------------------------------------- đáp án


@pytest.mark.parametrize("sql, code", [
    ("SELECT doanh_thu FROM orders", "E_SQL"),
    ("DROP TABLE customers", "E_SQL"),
    ("SELECT * FROM customers WHERE city = 'Sài Gòn'", "W_EMPTY"),
    ("SELECT COUNT(*) FROM customers WHERE city = 'Sài Gòn'", "W_TRIVIAL"),
    ("SELECT full_name FROM customers LIMIT 2", "W_UNSTABLE_SCAN"),
    ("SELECT customer_id, COUNT(*) AS n FROM orders GROUP BY customer_id ORDER BY n DESC", "W_UNSTABLE_TIES"),
    ("SELECT customer_id, COUNT(*) AS n FROM orders GROUP BY customer_id ORDER BY n DESC LIMIT 1", "W_UNSTABLE_TIES"),
])
def test_answer_problems_detected(tmp_path: Path, db: Path, sql: str, code: str) -> None:
    assert ("dev-001", code) in codes(write(tmp_path / "dev.jsonl", [good(sql=sql)]), db)


@pytest.mark.parametrize("sql", [
    "SELECT city, COUNT(*) FROM customers GROUP BY city",
    "SELECT customer_id, COUNT(*) AS n FROM orders GROUP BY customer_id ORDER BY n DESC, customer_id",
    "SELECT full_name FROM customers ORDER BY customer_id LIMIT 2",
    "SELECT full_name FROM customers WHERE customer_id IN (SELECT customer_id FROM orders)",
])
def test_good_answers_not_flagged(tmp_path: Path, db: Path, sql: str) -> None:
    assert codes(write(tmp_path / "dev.jsonl", [good(sql=sql)]), db) == []


def test_truncated_answer(tmp_path: Path, db: Path) -> None:
    sql = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 2000) SELECT x FROM c"
    assert ("dev-001", "E_TRUNCATED") in codes(write(tmp_path / "dev.jsonl", [good(sql=sql)]), db)


# --------------------------------------------------------------------------- trùng câu hỏi, thống kê


def test_duplicate_questions_across_files() -> None:
    dev = [good("dev-001", question="Có bao nhiêu khách ở Huế?")]
    test = [good("test-007", question="  có bao nhiêu khách ở huế ")]
    issues = duplicate_questions({"dev.jsonl": dev, "test.jsonl": test})
    assert [(i.qid, i.code, i.detail) for i in issues] == [("test-007", "W_DUP_QUESTION", "trùng với dev-001")]


def test_summary_counts_difficulty_and_tags() -> None:
    records = [good("a", difficulty="easy", tags=["join"]), good("b", difficulty="hard", tags=["join", "date"])]
    text = "\n".join(summarize("dev", records))
    assert "số câu: 2 (mục tiêu ~50)" in text
    assert "join=2" in text and "date=1" in text


# --------------------------------------------------------------------------- CLI


def test_cli_exit_code_and_no_content_leak(tmp_path: Path, db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path / "test.jsonl", [good("t-1"), good("t-2", sql="SELECT * FROM khong_co_bang")])
    assert cli.main([str(path), "--db", str(db)]) == 1
    out = capsys.readouterr().out
    assert "t-2" in out and "E_SQL" in out
    assert SECRET not in out and "khong_co_bang" not in out  # không lộ câu hỏi hay SQL


def test_cli_verbose_shows_detail(tmp_path: Path, db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path / "dev.jsonl", [good(sql="SELECT * FROM khong_co_bang")])
    cli.main([str(path), "--db", str(db), "--verbose"])
    assert "khong_co_bang" in capsys.readouterr().out


def test_cli_clean_file_exits_zero(tmp_path: Path, db: Path) -> None:
    assert cli.main([str(write(tmp_path / "dev.jsonl", [good()])), "--db", str(db)]) == 0


# =========================================================================== Bổ sung sau review


@pytest.fixture()
def db_with_null(db: Path) -> Path:
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO customers VALUES (5, NULL, 'Huế')")
    conn.commit()
    conn.close()
    return db


@pytest.mark.parametrize("sql", [
    # M1: hai dòng hòa là 'Dũng' và NULL — khóa phụ phải đảo được vị trí NULL
    "SELECT full_name FROM customers WHERE customer_id IN (4, 5) ORDER BY customer_id > 3 LIMIT 1",
    # M2: ORDER BY + LIMIT trong subquery, hòa đúng ở chỗ cắt (Chi, Dũng cùng ở Huế)
    "SELECT full_name FROM customers WHERE customer_id IN (SELECT customer_id FROM customers ORDER BY city LIMIT 2)",
    # 'Huế' xếp trước 'Hà Nội' (u < à) và có 3 khách → LIMIT 2 cắt giữa nhóm hòa
    "SELECT * FROM (SELECT customer_id, full_name FROM customers ORDER BY city LIMIT 2)",
])
def test_more_unstable_answers_detected(tmp_path: Path, db_with_null: Path, sql: str) -> None:
    assert ("dev-001", "W_UNSTABLE_TIES") in codes(write(tmp_path / "dev.jsonl", [good(sql=sql)]), db_with_null)


def test_subquery_with_tiebreak_not_flagged(tmp_path: Path, db: Path) -> None:
    sql = ("SELECT full_name FROM customers WHERE customer_id IN "
           "(SELECT customer_id FROM customers ORDER BY city, customer_id LIMIT 2)")
    assert codes(write(tmp_path / "dev.jsonl", [good(sql=sql)]), db) == []


def test_order_by_null_without_limit_not_flagged(tmp_path: Path, db: Path) -> None:
    """N1: evaluator coi ORDER BY NULL là không có thứ tự → không được báo hòa."""
    sql = "SELECT full_name FROM customers ORDER BY NULL"
    assert "W_UNSTABLE_TIES" not in [c for _, c in codes(write(tmp_path / "dev.jsonl", [good(sql=sql)]), db)]


def test_unbuildable_variant_reported(tmp_path: Path, db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """N2: không dựng / chạy được câu thử thì báo W_UNCHECKED_TIES, không lặng lẽ coi là ổn."""
    from src.eval import dataset

    def broken(*_args: object) -> str:
        raise ValueError("sqlglot hỏng")

    monkeypatch.setattr(dataset, "_with_tiebreak", broken)
    sql = "SELECT full_name FROM customers ORDER BY full_name"
    assert ("dev-001", "W_UNCHECKED_TIES") in codes(write(tmp_path / "dev.jsonl", [good(sql=sql)]), db)


@pytest.mark.parametrize("override", [{"id": ["a"]}, {"id": 7}, {"difficulty": {"x": 1}}, {"tags": "join"}])
def test_wrong_types_do_not_crash(tmp_path: Path, db: Path, override: dict) -> None:
    """N4: dữ liệu sai kiểu phải ra ERROR, không làm dừng cả lượt kiểm."""
    records, issues = check_file(write(tmp_path / "dev.jsonl", [good(**override)]), db)
    assert any(i.level == "ERROR" for i in issues)
    summarize("dev", records)  # không raise


def test_utf8_bom_file_accepted(tmp_path: Path, db: Path) -> None:
    """N5: Notepad trên Windows hay lưu kèm BOM."""
    path = tmp_path / "dev.jsonl"
    path.write_text(json.dumps(good(), ensure_ascii=False) + "\n", encoding="utf-8-sig")
    assert codes(path, db) == []


def test_cli_verbose_warnings_do_not_contain_sql(tmp_path: Path, db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sql = "SELECT full_name FROM customers LIMIT 2"
    cli.main([str(write(tmp_path / "dev.jsonl", [good(sql=sql)])), "--db", str(db), "--verbose"])
    out = capsys.readouterr().out
    assert "W_UNSTABLE_SCAN" in out and "LIMIT 2" not in out


# =========================================================================== Kiểm câu hỏi (chưa có SQL)
from src.eval.dataset import check_question_wording, similar_questions  # noqa: E402


def test_questions_only_does_not_require_sql(tmp_path: Path, db: Path) -> None:
    path = write(tmp_path / "test.jsonl", [good("t-1", sql="")])
    assert codes(path, db) == [("t-1", "E_FIELD")]
    _, issues = check_file(path, db, questions_only=True)
    assert issues == []


@pytest.mark.parametrize("question, code", [
    ("Doanh thu tháng này của cửa hàng là bao nhiêu?", "W_RELATIVE_TIME"),
    ("Liệt kê các khách hàng mua hàng gần đây ở Hà Nội.", "W_RELATIVE_TIME"),
    ("Liệt kê những sản phẩm đắt trong danh mục Laptop.", "W_VAGUE"),
    ("Có bao nhiêu đơn hàng lớn trong năm 2025?", "W_VAGUE"),
    ("Doanh thu năm 2025?", "W_SHORT"),
])
def test_wording_warnings(question: str, code: str) -> None:
    assert code in [i.code for i in check_question_wording(question, "q")]


@pytest.mark.parametrize("question", [
    "Sản phẩm đắt nhất trong danh mục Laptop tên là gì?",
    "Hãy cho biết trong năm 2024, tháng nào có nhiều đơn hàng nhất?",
    "Có bao nhiêu đơn hàng trên 50 triệu đồng trong năm 2025?",
    "Những thương hiệu nào có nhiều hơn 5 sản phẩm?",
])
def test_wording_no_false_alarm(question: str) -> None:
    assert check_question_wording(question, "q") == []


def test_similar_questions_across_files() -> None:
    dev = [good("dev-1", question="Hãy cho mình top 10 khách hàng chi tiêu nhiều nhất năm 2025 (tên và tổng tiền).")]
    test = [good("t-1", question="Hãy cho mình top 5 khách hàng chi tiêu nhiều nhất năm 2024 (tên và tổng tiền)."),
            good("t-2", question="Có bao nhiêu sản phẩm thuộc danh mục Laptop còn dưới 10 cái trong kho?")]
    issues = similar_questions({"dev.jsonl": dev, "test.jsonl": test})
    assert [(i.qid, i.code) for i in issues] == [("t-1", "W_SIMILAR")]


def test_similar_ignores_pairs_in_same_file() -> None:
    same = [good("a", question="Có bao nhiêu khách hàng ở Hà Nội?"), good("b", question="Có bao nhiêu khách hàng ở Huế?")]
    assert similar_questions({"dev.jsonl": same}) == []


def test_cli_questions_only_prints_ids_not_content(tmp_path: Path, db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dev = write(tmp_path / "dev.jsonl", [good("dev-1", question=f"{SECRET} top 10 khách chi tiêu nhiều nhất năm 2025")])
    test = write(tmp_path / "test.jsonl", [good("t-1", sql="", question=f"{SECRET} top 10 khách chi tiêu nhiều nhất năm 2024")])
    assert cli.main([str(dev), str(test), "--db", str(db), "--questions-only"]) == 0
    out = capsys.readouterr().out
    assert "t-1" in out and "W_SIMILAR" in out and SECRET not in out
