"""Chạy thử một câu SQL khi viết đáp án dataset (đi qua executor, DB chỉ đọc).

Chạy:  python scripts/try_sql.py "SELECT city, COUNT(*) FROM customers GROUP BY city"
hoặc:  python scripts/try_sql.py < query.sql      (tiện cho câu SQL nhiều dòng)

In bảng kết quả (tối đa --show dòng) và các cảnh báo mà scripts/check_dataset.py sẽ báo,
để sửa ngay lúc viết thay vì đợi kiểm cả file.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.executor import DEFAULT_DB, ExecResult, execute  # noqa: E402
from src.eval.dataset import check_answer  # noqa: E402
from src.eval.evaluator import has_order_by  # noqa: E402

MAX_CELL = 40  # cắt ô quá dài cho dễ đọc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chạy thử SQL trên data/sales.db")
    parser.add_argument("sql", nargs="?", help="câu SQL; bỏ trống thì đọc từ stdin")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--show", type=int, default=20, help="số dòng tối đa in ra")
    return parser.parse_args(argv)


def format_table(result: ExecResult, show: int) -> str:
    """Bảng văn bản đơn giản, căn cột theo ô dài nhất."""
    header = [str(c) for c in result.columns]
    body = [[_cell(v) for v in row] for row in result.rows[:show]]
    widths = [max(len(r[i]) for r in [header, *body]) for i in range(len(header))]
    lines = [" | ".join(h.ljust(w) for h, w in zip(header, widths)),
             "-+-".join("-" * w for w in widths)]
    lines += [" | ".join(c.ljust(w) for c, w in zip(row, widths)) for row in body]
    return "\n".join(lines)


def _cell(value: object) -> str:
    text = "NULL" if value is None else str(value)
    return text if len(text) <= MAX_CELL else text[: MAX_CELL - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    sql = args.sql if args.sql is not None else sys.stdin.read()
    result = execute(sql, args.db)
    if result.error is not None:
        print(f"LỖI: {result.error}")
        return 1
    print(format_table(result, args.show))
    shown = min(len(result.rows), args.show)
    more = "+ (bị cắt ở 1000)" if result.truncated else ""
    print(f"\n{len(result.rows)}{more} dòng, hiện {shown}. ORDER BY ngoài cùng: {'có' if has_order_by(sql) else 'không'}.")
    for issue in check_answer(sql, "sql", args.db):
        print(f"{issue.level}: {issue.code} — {issue.detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
