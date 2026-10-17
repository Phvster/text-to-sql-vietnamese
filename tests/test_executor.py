"""Test cho src/db/executor.py. Dùng DB tạm, không phụ thuộc data/sales.db."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from src.db import executor
from src.db.executor import ExecResult, execute

N_ROWS = 1500
INFINITE_SQL = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    """Bảng t(id, name, created_at): 1500 dòng, name NULL ở các id chia hết cho 10."""
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT, created_at TEXT)")
    conn.executemany("INSERT INTO t VALUES (?, ?, ?)",
                     [(i, None if i % 10 == 0 else f"n{i}", "2025-01-01") for i in range(1, N_ROWS + 1)])
    conn.commit()
    conn.close()
    return path


def snapshot(path: Path) -> tuple[list[tuple], list[tuple]]:
    """Trạng thái DB (schema + dữ liệu) để khẳng định không có gì bị thay đổi."""
    conn = sqlite3.connect(path)
    try:
        schema = conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
        data = conn.execute("SELECT * FROM t ORDER BY id").fetchall()
        return schema, data
    finally:
        conn.close()


def assert_rejected(result: ExecResult) -> None:
    assert result.error is not None
    assert result.rows == []
    assert result.columns == []
    assert result.truncated is False


# --------------------------------------------------------------------------- A. Hợp lệ


def test_simple_select(db: Path) -> None:
    result = execute("SELECT id, name FROM t WHERE id <= 2 ORDER BY id", db)
    assert result.error is None and result.ok
    assert result.rows == [(1, "n1"), (2, "n2")]
    assert result.columns == ["id", "name"]
    assert result.truncated is False


def test_with_select(db: Path) -> None:
    result = execute("WITH small AS (SELECT id FROM t WHERE id < 4) SELECT COUNT(*) AS n FROM small", db)
    assert result.rows == [(3,)]
    assert result.columns == ["n"]


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM t;",
    "  \n  SELECT COUNT(*) FROM t  ;  ",
    "-- đếm số dòng\nSELECT COUNT(*) FROM t",
    "/* ghi chú */ select count(*) from t",
])
def test_formatting_variants_accepted(db: Path, sql: str) -> None:
    assert execute(sql, db).rows == [(N_ROWS,)]


def test_union(db: Path) -> None:
    result = execute("SELECT id FROM t WHERE id = 1 UNION SELECT id FROM t WHERE id = 2 ORDER BY id", db)
    assert result.rows == [(1,), (2,)]


def test_empty_result_keeps_columns(db: Path) -> None:
    result = execute("SELECT id, name FROM t WHERE id < 0", db)
    assert result.error is None
    assert result.rows == []
    assert result.columns == ["id", "name"]


def test_null_values(db: Path) -> None:
    assert execute("SELECT name FROM t WHERE id = 10", db).rows == [(None,)]


# --------------------------------------------------------------------------- B. Không phải SELECT


@pytest.mark.parametrize("sql", [
    "INSERT INTO t VALUES (9999, 'x', 'y')",
    "UPDATE t SET name = 'hacked'",
    "DELETE FROM t",
    "DROP TABLE t",
    "ALTER TABLE t ADD COLUMN z INTEGER",
    "CREATE TABLE z (a INTEGER)",
    "CREATE VIEW v AS SELECT * FROM t",
    "ATTACH DATABASE 'other.db' AS other",
    "PRAGMA table_info(t)",
    "REPLACE INTO t VALUES (1, 'x', 'y')",
    "VACUUM",
])
def test_non_select_rejected_and_db_unchanged(db: Path, sql: str) -> None:
    before = snapshot(db)
    assert_rejected(execute(sql, db))
    assert snapshot(db) == before


# --------------------------------------------------------------------------- C. Nhiều câu lệnh


@pytest.mark.parametrize("sql", [
    "SELECT 1; DROP TABLE t",
    "SELECT 1; SELECT 2",
    "SELECT 1; -- vô hại\nDROP TABLE t",
])
def test_multiple_statements_rejected(db: Path, sql: str) -> None:
    before = snapshot(db)
    assert_rejected(execute(sql, db))
    assert snapshot(db) == before


# --------------------------------------------------------------------------- D. Mẹo lách / chặn nhầm


@pytest.mark.parametrize("sql", [
    "WITH x AS (SELECT 1) DELETE FROM t",
    "dRoP tAbLe t",
    "/* c */ DROP TABLE t",
    "SELECT * INTO backup FROM t",
])
def test_evasion_attempts_rejected(db: Path, sql: str) -> None:
    before = snapshot(db)
    assert_rejected(execute(sql, db))
    assert snapshot(db) == before


def test_keyword_inside_string_is_allowed(db: Path) -> None:
    """Parser hiểu đây là chuỗi, không phải lệnh — bộ lọc từ khóa sẽ chặn nhầm."""
    assert execute("SELECT 'DROP TABLE t; DELETE FROM t' AS s", db).rows == [("DROP TABLE t; DELETE FROM t",)]


def test_column_name_containing_keyword_is_allowed(db: Path) -> None:
    assert execute("SELECT created_at FROM t WHERE id = 1", db).rows == [("2025-01-01",)]


@pytest.mark.parametrize("sql", ["", "   \n ", "-- chỉ có comment", ";", "SELEC FROM WHERE", "SELECT 'chưa đóng"])
def test_empty_or_garbage_rejected(db: Path, sql: str) -> None:
    assert_rejected(execute(sql, db))


def test_non_string_rejected(db: Path) -> None:
    assert_rejected(execute(None, db))  # type: ignore[arg-type]


# --------------------------------------------------------------------------- E. Lớp 3 đứng độc lập


@pytest.mark.parametrize("sql", [
    "INSERT INTO t VALUES (9999, 'x', 'y')",
    "DELETE FROM t",
    "DROP TABLE t",
    "CREATE TABLE z (a INTEGER)",
    "PRAGMA journal_mode = DELETE",
    "ATTACH DATABASE ':memory:' AS other",
])
def test_read_only_layer_holds_without_validation(db: Path, sql: str) -> None:
    """Gọi thẳng _run, giả lập trường hợp lớp 1–2 bị lừa: SQLite vẫn phải từ chối."""
    before = snapshot(db)
    assert_rejected(executor._run(sql, db, timeout_s=5.0, max_rows=1000))
    assert snapshot(db) == before


def test_missing_db_is_error_and_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "khong_ton_tai.db"
    assert_rejected(execute("SELECT 1", missing))
    assert not missing.exists()


def test_huge_value_rejected(db: Path) -> None:
    assert_rejected(execute("SELECT zeroblob(100000000)", db))


# --------------------------------------------------------------------------- F. Timeout


def test_timeout_interrupts_infinite_query(db: Path) -> None:
    start = time.monotonic()
    result = execute(INFINITE_SQL, db, timeout_s=0.2)
    elapsed = time.monotonic() - start
    assert_rejected(result)
    assert "timeout" in result.error.lower()
    assert elapsed < 2.0


def test_fast_query_not_affected_by_timeout(db: Path) -> None:
    assert execute("SELECT COUNT(*) FROM t", db, timeout_s=0.2).rows == [(N_ROWS,)]


# --------------------------------------------------------------------------- G. Giới hạn dòng


def test_rows_truncated_at_limit(db: Path) -> None:
    result = execute("SELECT id FROM t ORDER BY id", db)
    assert len(result.rows) == 1000
    assert result.rows[0] == (1,) and result.rows[-1] == (1000,)
    assert result.truncated is True
    assert result.error is None


def test_exactly_limit_is_not_truncated(db: Path) -> None:
    result = execute("SELECT id FROM t ORDER BY id LIMIT 1000", db)
    assert len(result.rows) == 1000
    assert result.truncated is False


def test_custom_max_rows(db: Path) -> None:
    result = execute("SELECT id FROM t", db, max_rows=10)
    assert len(result.rows) == 10
    assert result.truncated is True


# --------------------------------------------------------------------------- H. Lỗi runtime


@pytest.mark.parametrize("sql, fragment", [
    ("SELECT * FROM khong_co_bang", "no such table"),
    ("SELECT khong_co_cot FROM t", "no such column"),
])
def test_runtime_error_returned_not_raised(db: Path, sql: str, fragment: str) -> None:
    result = execute(sql, db)
    assert_rejected(result)
    assert fragment in result.error


def test_defaults_match_safety_rules() -> None:
    assert executor.TIMEOUT_S == 5.0
    assert executor.MAX_ROWS == 1000
    assert executor.DEFAULT_DB.name == "sales.db"


# =========================================================================== Bổ sung sau review
# Các test ở trên gọi execute(): nếu lớp 1–2 hỏng, lớp 3 vẫn chặn và test vẫn pass.
# Các test dưới đây gọi thẳng từng lớp để mỗi lớp phải tự đứng vững.

# --------------------------------------------------------------------------- Lớp 1–2 độc lập (_validate)


@pytest.mark.parametrize("sql", [
    "INSERT INTO t VALUES (1, 'x', 'y')", "UPDATE t SET name = 'x'", "DELETE FROM t", "DROP TABLE t",
    "ALTER TABLE t ADD COLUMN z INTEGER", "CREATE TABLE z (a INTEGER)", "CREATE VIEW v AS SELECT 1",
    "CREATE INDEX i ON t(name)", "CREATE TEMP TABLE z (a INTEGER)",
    "CREATE TRIGGER tr AFTER INSERT ON t BEGIN DELETE FROM t; END",
    "ATTACH DATABASE 'other.db' AS other", "DETACH DATABASE other", "PRAGMA table_info(t)",
    "REPLACE INTO t VALUES (1, 'x', 'y')", "VACUUM", "VACUUM INTO 'copy.db'", "REINDEX", "ANALYZE",
    "BEGIN", "COMMIT", "SAVEPOINT s", "EXPLAIN SELECT 1", "EXPLAIN QUERY PLAN SELECT 1", "VALUES (1)",
    "INSERT INTO t SELECT * FROM t", "UPDATE t SET name = 'x' RETURNING id",
    "WITH x AS (SELECT 1) DELETE FROM t", "SELECT * INTO backup FROM t",
    "dRoP tAbLe t", "/* c */ DROP TABLE t",
])
def test_validate_rejects_non_select(sql: str) -> None:
    error = executor._validate(sql)
    assert error is not None and error.startswith(("Từ chối", "Lỗi cú pháp"))


@pytest.mark.parametrize("sql", [
    "SELECT 1; DROP TABLE t", "SELECT 1; SELECT 2", "SELECT 1; -- vô hại\nDROP TABLE t",
    "SELECT 1; /* c */ DELETE FROM t",
])
def test_validate_rejects_multiple_statements(sql: str) -> None:
    assert "đúng 1 câu lệnh" in executor._validate(sql)


@pytest.mark.parametrize("sql", [
    "SELECT id, ROW_NUMBER() OVER (PARTITION BY name ORDER BY id DESC) AS rn FROM t",
    "SELECT SUM(id) OVER (ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) FROM t",
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 5) SELECT x FROM c",
    "SELECT id FROM t EXCEPT SELECT id FROM t WHERE id > 5",
    "SELECT id FROM t INTERSECT SELECT id FROM t WHERE id > 5",
    "SELECT strftime('%Y-%m', created_at) AS thang, COUNT(*) FROM t GROUP BY 1 HAVING COUNT(*) > 1",
    "SELECT GROUP_CONCAT(name, ', ') FROM t WHERE id < 5",
    "SELECT CASE WHEN id > 5 THEN 'lớn' ELSE 'nhỏ' END AS \"phân loại\" FROM t",
    "SELECT name FROM t a WHERE EXISTS (SELECT 1 FROM t b WHERE b.id = a.id + 1)",
    "SELECT name FROM t WHERE name = 'TP. Hồ Chí Minh; -- không phải comment'",
    "SELECT REPLACE(name, 'n', 'm') AS \"into\" FROM t",
    "SELECT id FROM t LEFT JOIN (SELECT id AS i2 FROM t) s ON s.i2 = t.id WHERE s.i2 IS NULL",
    "SELECT 1; -- xong",
])
def test_valid_analytics_sql_not_blocked(db: Path, sql: str) -> None:
    assert executor._validate(sql) is None
    assert execute(sql, db).error is None


def test_sql_too_long_rejected(db: Path) -> None:
    sql = "SELECT 1 FROM t WHERE id IN (" + ", ".join(["1"] * 20_000) + ")"
    result = execute(sql, db)
    assert_rejected(result)
    assert "dài quá" in result.error


def test_deep_nesting_rejected_with_clear_message() -> None:
    assert "lồng quá sâu" in executor._validate("SELECT " + "(" * 3000 + "1" + ")" * 3000)


# --------------------------------------------------------------------------- Lớp 3: từng chốt riêng


def test_mode_ro_alone_blocks_writes(db: Path) -> None:
    """Tắt authorizer: mode=ro một mình vẫn phải chặn ghi."""
    before = snapshot(db)
    conn = executor._connect(db, timeout_s=1.0)
    conn.set_authorizer(None)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("INSERT INTO t VALUES (9999, 'x', 'y')")
    finally:
        conn.close()
    assert snapshot(db) == before


@pytest.mark.parametrize("action", [
    sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_DROP_TABLE,
    sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_CREATE_TEMP_TABLE, sqlite3.SQLITE_ALTER_TABLE,
    sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_PRAGMA, sqlite3.SQLITE_TRANSACTION,
])
def test_authorizer_denies_write_actions(action: int) -> None:
    assert executor._authorize(action, None, None, None, None) == sqlite3.SQLITE_DENY


def test_authorizer_allows_read_actions() -> None:
    for action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION):
        assert executor._authorize(action, None, None, None, None) == sqlite3.SQLITE_OK


@pytest.mark.parametrize("sql", [
    "UPDATE t SET name = 'x'", "REPLACE INTO t VALUES (1, 'x', 'y')", "CREATE TEMP TABLE z (a INTEGER)",
    "SELECT 1; DROP TABLE t", "SELECT load_extension('x')", "SELECT * FROM pragma_table_info('t')",
    "BEGIN IMMEDIATE",
])
def test_run_rejects_more_bypass_attempts(db: Path, sql: str) -> None:
    before = snapshot(db)
    assert_rejected(executor._run(sql, db, timeout_s=5.0, max_rows=1000))
    assert snapshot(db) == before


@pytest.mark.parametrize("template, target", [
    ("VACUUM INTO '{}'", "copy.db"),
    ("ATTACH DATABASE '{}' AS other", "other.db"),
])
def test_run_cannot_create_other_files(db: Path, tmp_path: Path, template: str, target: str) -> None:
    out = tmp_path / target
    assert_rejected(executor._run(template.format(out.as_posix()), db, timeout_s=5.0, max_rows=1000))
    assert not out.exists()


@pytest.mark.parametrize("sql", ["SELECT 1 {# ; DROP TABLE t #}", "SELECT 1;;"])
def test_parser_disagreement_still_rejected(db: Path, sql: str) -> None:
    """sqlglot và SQLite hiểu khác nhau: lớp 1–2 cho qua, lớp 3–5 phải chặn."""
    before = snapshot(db)
    assert executor._validate(sql) is None
    assert_rejected(execute(sql, db))
    assert snapshot(db) == before


# --------------------------------------------------------------------------- Không bao giờ raise


@pytest.mark.parametrize("sql", [
    "SELECT '[1,2]' -> 1e2",  # sqlglot raise ValueError
    "SELECT '" + chr(0xD800) + "'",  # surrogate lẻ: sqlite3 raise UnicodeEncodeError
    "SELECT 'a" + chr(0) + "b'",
    "SELECT ?",
    "SELECT CAST(x'ff' AS TEXT)",
    "```sql\nSELECT 1\n```",
    b"SELECT 1",
    123,
], ids=["sqlglot-valueerror", "surrogate", "nul", "binding", "bad-utf8", "markdown", "bytes", "int"])
def test_never_raises(db: Path, sql: object) -> None:
    assert isinstance(execute(sql, db), ExecResult)  # type: ignore[arg-type]


def test_error_message_is_clean_and_bounded(db: Path) -> None:
    result = execute("SELECT TOP 5 * FROM " + "x" * 5000, db)
    assert_rejected(result)
    assert "\x1b" not in result.error
    assert len(result.error) <= executor.MAX_ERROR_CHARS + 1


# --------------------------------------------------------------------------- Lớp 4: timeout (bổ sung)


def test_timeout_during_fetch(db: Path) -> None:
    """Vài dòng đầu ra ngay, dòng sau không bao giờ tới → timeout phải ngắt cả lúc fetch."""
    sql = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT x FROM c WHERE x < 5"
    start = time.monotonic()
    result = execute(sql, db, timeout_s=0.2)
    assert "timeout" in result.error.lower()
    assert time.monotonic() - start < 2.0


def test_locked_db_respects_timeout(db: Path) -> None:
    locker = sqlite3.connect(db)
    locker.execute("BEGIN EXCLUSIVE")
    try:
        start = time.monotonic()
        result = execute("SELECT COUNT(*) FROM t", db, timeout_s=0.2)
        assert_rejected(result)
        assert time.monotonic() - start < 2.0
    finally:
        locker.rollback()
        locker.close()


def test_plain_sqlite_error_not_labelled_timeout(db: Path) -> None:
    assert "timeout" not in execute("SELECT * FROM khong_co_bang", db).error.lower()


def test_heavy_string_function_is_bounded(db: Path) -> None:
    """Hàm chuỗi là một lệnh máy ảo, timeout không ngắt giữa chừng → trần kích thước giá trị phải chặn."""
    start = time.monotonic()
    result = execute("SELECT instr(hex(zeroblob(499000)), hex(zeroblob(250000)) || '1')", db)
    assert_rejected(result)
    assert time.monotonic() - start < 2.0


# --------------------------------------------------------------------------- Lớp 5 (bổ sung)


def test_infinite_rows_stop_at_limit_quickly(db: Path) -> None:
    """Nếu ai đó đổi sang fetchall() thì test này treo tới timeout thay vì trả 1000 dòng."""
    result = execute("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT x FROM c", db)
    assert result.error is None
    assert len(result.rows) == 1000 and result.truncated is True


def test_total_result_size_capped(db: Path) -> None:
    result = execute("SELECT zeroblob(90000) FROM t", db)  # 1000 dòng x 90 KB = 90 MB
    assert_rejected(result)
    assert "lớn hơn" in result.error


def test_max_rows_zero(db: Path) -> None:
    result = execute("SELECT id FROM t", db, max_rows=0)
    assert result.rows == [] and result.truncated is True


# --------------------------------------------------------------------------- reverse_unordered (kiểm dataset)


def test_reverse_unordered_flips_scan_order(db: Path) -> None:
    sql = "SELECT id FROM t LIMIT 3"
    assert execute(sql, db).rows == [(1,), (2,), (3,)]
    assert execute(sql, db, reverse_unordered=True).rows == [(N_ROWS,), (N_ROWS - 1,), (N_ROWS - 2,)]


def test_reverse_unordered_keeps_explicit_order(db: Path) -> None:
    sql = "SELECT id FROM t ORDER BY id LIMIT 3"
    assert execute(sql, db, reverse_unordered=True).rows == execute(sql, db).rows


def test_reverse_unordered_is_off_by_default(db: Path) -> None:
    """Pipeline chấm model gọi execute() không có cờ → thứ tự quét bình thường."""
    assert execute("SELECT id FROM t LIMIT 1", db).rows == [(1,)]


@pytest.mark.parametrize("sql", [
    "DROP TABLE t", "PRAGMA reverse_unordered_selects = OFF", "DELETE FROM t",
    "SELECT * FROM pragma_reverse_unordered_selects", "SELECT * FROM pragma_table_info('t')",
    "SELECT 1; PRAGMA writable_schema = ON",
])
def test_reverse_unordered_does_not_weaken_layers(db: Path, sql: str) -> None:
    """Cờ chỉ chạy một PRAGMA cố định trước khi cài authorizer; SQL đầu vào vẫn bị chặn như cũ."""
    before = snapshot(db)
    assert_rejected(execute(sql, db, reverse_unordered=True))
    assert_rejected(executor._run(sql, db, timeout_s=5.0, max_rows=1000, reverse_unordered=True))
    assert snapshot(db) == before


def test_reverse_unordered_keeps_timeout_and_row_limit(db: Path) -> None:
    assert "timeout" in execute(INFINITE_SQL, db, timeout_s=0.2, reverse_unordered=True).error.lower()
    result = execute("SELECT id FROM t", db, reverse_unordered=True)
    assert len(result.rows) == 1000 and result.truncated is True


def test_reverse_unordered_does_not_leak_to_next_call(db: Path) -> None:
    execute("SELECT id FROM t LIMIT 1", db, reverse_unordered=True)
    assert execute("SELECT id FROM t LIMIT 1", db).rows == [(1,)]  # mỗi lần gọi mở kết nối mới
