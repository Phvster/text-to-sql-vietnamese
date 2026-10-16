"""Cổng duy nhất để chạy SQL do model sinh (xem .claude/rules/safety.md).

5 lớp phòng thủ, xếp từ "kiểm tra văn bản" tới "SQLite tự chặn":
  1. Đúng 1 câu lệnh            (_parse_single)   — chặn "SELECT 1; DROP TABLE x"
  2. Chỉ SELECT / WITH...SELECT  (_check_read_only) — chặn lệnh ghi, PRAGMA, ATTACH
  3. DB mở chỉ đọc + authorizer  (_connect)        — lưới an toàn nếu lớp 1–2 bị lừa
  4. Timeout                     (_install_timeout) — chặn truy vấn chạy mãi
  5. Giới hạn kích thước kết quả (_fetch_limited)   — chặn kết quả khổng lồ

Lớp 1–2 dựa vào sqlglot, lớp 3–5 dựa vào SQLite: hai bộ phân tích độc lập, nên một câu SQL
phải lừa được cả hai mới gây hại.

execute() không bao giờ raise: mọi lỗi nằm trong ExecResult.error, để pipeline (vòng sửa lỗi C4)
đọc thông báo và evaluator chấm "không chạy được" mà không cần try/except ở nơi gọi.

Hạn chế đã biết (reviewer tìm ra, đã giảm thiểu nhưng không triệt để):
- Timeout chỉ ngắt được GIỮA các lệnh máy ảo của SQLite. Một hàm chuỗi nặng (instr/replace trên
  chuỗi dài) là một lệnh duy nhất nên không bị ngắt giữa chừng. Giảm thiểu bằng MAX_VALUE_BYTES,
  MAX_LIKE_PATTERN và MAX_SQL_CHARS (đầu vào nhỏ → mỗi lệnh chạy nhanh). Chặn tuyệt đối cần chạy
  truy vấn trong tiến trình con và kill khi quá hạn — chưa cần cho dự án này.
- Truy vấn sắp xếp dữ liệu lớn có thể ghi file tạm vào %TEMP% cho tới khi timeout.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import exp

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "sales.db"
TIMEOUT_S = 5.0
MAX_ROWS = 1000
MAX_SQL_CHARS = 10_000  # SQL do LLM sinh hiếm khi quá vài nghìn ký tự; chặn sớm trước khi parse
MAX_VALUE_BYTES = 100_000  # trần kích thước một giá trị (chuỗi/blob)
MAX_LIKE_PATTERN = 1_000  # trần độ dài mẫu LIKE/GLOB
MAX_RESULT_BYTES = 5_000_000  # trần tổng kích thước kết quả trả về
MAX_ERROR_CHARS = 500  # thông báo lỗi đi vào prompt sửa lỗi (C4) nên phải ngắn

# sqlglot in cảnh báo khi gặp cú pháp lạ (REPLACE, EXPLAIN...); ta đã từ chối các câu đó nên không cần log.
logging.getLogger("sqlglot").setLevel(logging.ERROR)

# Lớp 2: gốc cây cú pháp được phép. SetOperation = UNION / INTERSECT / EXCEPT.
_ALLOWED_ROOTS = (exp.Select, exp.SetOperation)
# Lớp 2: nút bị cấm ở bất kỳ đâu trong cây (vd "SELECT * INTO x FROM t" có gốc Select nhưng chứa Into).
_FORBIDDEN_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create, exp.Into,
                    exp.Attach, exp.Detach, exp.Pragma, exp.Command, exp.Transaction, exp.Analyze)
# Lớp 3: các hành động SQLite được phép làm. Mọi hành động khác (ghi, PRAGMA, ATTACH...) bị từ chối.
_ALLOWED_ACTIONS = frozenset({sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ,
                              sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE})
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")  # sqlglot tô màu vị trí lỗi bằng mã ANSI


@dataclass(frozen=True)
class ExecResult:
    rows: list[tuple]
    columns: list[str]
    truncated: bool  # True nếu kết quả bị cắt ở max_rows
    error: str | None  # None = chạy thành công

    @property
    def ok(self) -> bool:
        return self.error is None


class _ResultTooLarge(Exception):
    pass


def _failure(message: str) -> ExecResult:
    clean = _ANSI_ESCAPE.sub("", message)
    if len(clean) > MAX_ERROR_CHARS:
        clean = clean[:MAX_ERROR_CHARS] + "…"
    return ExecResult(rows=[], columns=[], truncated=False, error=clean)


def execute(sql: str, db_path: Path = DEFAULT_DB, timeout_s: float = TIMEOUT_S,
            max_rows: int = MAX_ROWS) -> ExecResult:
    """Chạy một câu SELECT trên DB chỉ đọc. Tham số ngoài `sql` chỉ để test (DB tạm, timeout ngắn)."""
    error = _validate(sql)
    if error is not None:
        return _failure(error)  # bị từ chối trước khi chạm vào DB
    return _run(sql, db_path, timeout_s, max_rows)


# --------------------------------------------------------------------------- lớp 1 + 2: kiểm tra văn bản


def _validate(sql: str) -> str | None:
    """Trả về thông báo lỗi, hoặc None nếu câu SQL được phép chạy."""
    if not isinstance(sql, str):
        return "Từ chối: SQL phải là chuỗi."
    if len(sql) > MAX_SQL_CHARS:
        return f"Từ chối: câu SQL dài quá {MAX_SQL_CHARS} ký tự."
    try:
        statement = _parse_single(sql)
    except RecursionError:
        return "Từ chối: câu SQL lồng quá sâu."
    except Exception as exc:  # noqa: BLE001 — parser lỗi kiểu gì cũng là "không hiểu được" → từ chối
        return f"Lỗi cú pháp: {exc}"
    if isinstance(statement, str):
        return statement
    return _check_read_only(statement)


def _parse_single(sql: str) -> exp.Expression | str:
    """LỚP 1 — đúng một câu lệnh.

    Dùng parser thay vì đếm dấu ';' vì ';' có thể nằm trong chuỗi ("SELECT 'a;b'") hoặc comment.
    Trả về cây cú pháp, hoặc chuỗi thông báo lỗi.
    """
    parsed = sqlglot.parse(sql, read="sqlite")
    # sqlglot trả None cho phần rỗng ("SELECT 1;;") và Semicolon cho ';' có comment theo sau.
    statements = [s for s in parsed if s is not None and not isinstance(s, exp.Semicolon)]
    if not statements:
        return "Từ chối: câu SQL rỗng."
    if len(statements) > 1:
        return f"Từ chối: chỉ chấp nhận đúng 1 câu lệnh, nhận được {len(statements)}."
    return statements[0]


def _check_read_only(statement: exp.Expression) -> str | None:
    """LỚP 2 — chỉ SELECT (cho phép WITH ... SELECT và UNION).

    Whitelist ở gốc cây: cái gì không phải SELECT thì từ chối, kể cả lệnh ta chưa nghĩ tới
    (an toàn hơn blacklist từ khóa — blacklist chặn nhầm "SELECT 'DROP'" và lọt lệnh lạ).
    "WITH x AS (...) DELETE ..." có gốc là Delete nên bị chặn ở đây.
    """
    if not isinstance(statement, _ALLOWED_ROOTS):
        return f"Từ chối: chỉ cho phép SELECT, nhận được {statement.key.upper()}."
    for node in statement.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            return f"Từ chối: câu lệnh chứa {node.key.upper()}."
    return None


# --------------------------------------------------------------------------- lớp 3 + 4 + 5: SQLite tự chặn


def _run(sql: str, db_path: Path, timeout_s: float, max_rows: int) -> ExecResult:
    """Chạy SQL với lớp 3–5. Không gọi lớp 1–2: các lớp này phải tự đứng vững (có test riêng)."""
    timed_out: list[bool] = []
    conn: sqlite3.Connection | None = None
    try:
        conn = _connect(db_path, timeout_s)
        _install_timeout(conn, timeout_s, timed_out)
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description or []]
        rows, truncated = _fetch_limited(cursor, max_rows)
        return ExecResult(rows=rows, columns=columns, truncated=truncated, error=None)
    except _ResultTooLarge:
        return _failure(f"Từ chối: kết quả lớn hơn {MAX_RESULT_BYTES} byte.")
    except sqlite3.Error as exc:
        if timed_out:
            return _failure(f"Timeout: truy vấn chạy quá {timeout_s:g} giây.")
        return _failure(f"Lỗi SQLite: {exc}")
    except Exception as exc:  # noqa: BLE001 — hợp đồng "không bao giờ raise" (vd ký tự Unicode hỏng, hết bộ nhớ)
        return _failure(f"Lỗi khi chạy: {type(exc).__name__}: {exc}")
    finally:
        if conn is not None:
            conn.close()


def _connect(db_path: Path, timeout_s: float) -> sqlite3.Connection:
    """LỚP 3 — DB chỉ đọc. Hai chốt:

    - mode=ro: SQLite mở file ở chế độ chỉ đọc; cũng không tạo file mới nếu DB không tồn tại.
    - authorizer: SQLite hỏi callback trước MỖI hành động khi biên dịch câu lệnh; ta chỉ cho đọc.
      Chặn cả những thứ mode=ro không chặn (PRAGMA, ATTACH file khác).
    `timeout=` là thời gian chờ khi DB đang bị tiến trình khác khóa; progress handler (lớp 4) không
    chạy trong lúc chờ khóa nên phải đặt riêng ở đây.
    """
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout_s)
    conn.set_authorizer(_authorize)
    # Giá trị nhỏ → hàm chuỗi chạy nhanh → timeout (chỉ ngắt được giữa các lệnh) vẫn hiệu quả.
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_VALUE_BYTES)
    conn.setlimit(sqlite3.SQLITE_LIMIT_LIKE_PATTERN_LENGTH, MAX_LIKE_PATTERN)
    return conn


def _authorize(action: int, *_details: object) -> int:
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _install_timeout(conn: sqlite3.Connection, timeout_s: float, timed_out: list[bool]) -> None:
    """LỚP 4 — timeout.

    SQLite gọi handler sau mỗi 1000 lệnh máy ảo; handler trả giá trị khác 0 thì truy vấn bị ngắt.
    Đơn giản hơn dùng thread riêng để hủy, và áp dụng cho cả lúc execute lẫn lúc fetch.
    `timed_out` là cờ để _run phân biệt timeout với lỗi SQLite khác.
    """
    deadline = time.monotonic() + timeout_s  # monotonic: không bị ảnh hưởng khi đồng hồ hệ thống đổi

    def handler() -> int:
        if time.monotonic() > deadline:
            timed_out.append(True)
            return 1
        return 0

    conn.set_progress_handler(handler, 1000)


def _fetch_limited(cursor: sqlite3.Cursor, max_rows: int) -> tuple[list[tuple], bool]:
    """LỚP 5 — giới hạn kích thước kết quả.

    Đọc từng dòng, dừng ở dòng thứ max_rows + 1: dòng dư cho biết kết quả bị cắt mà không cần
    đọc hết phần còn lại. Đồng thời cộng dồn kích thước để chặn "ít dòng nhưng mỗi dòng rất to".
    """
    rows: list[tuple] = []
    total_bytes = 0
    for row in cursor:
        if len(rows) == max_rows:
            return rows, True
        total_bytes += sum(len(v) if isinstance(v, (str, bytes)) else 8 for v in row)
        if total_bytes > MAX_RESULT_BYTES:
            raise _ResultTooLarge
        rows.append(row)
    return rows, False
