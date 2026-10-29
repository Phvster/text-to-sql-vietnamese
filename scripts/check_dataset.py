"""Kiểm bộ câu hỏi trước khi chạy thí nghiệm.

Chạy: python scripts/check_dataset.py data/questions/dev.jsonl [data/questions/test.jsonl ...]

Mặc định chỉ in id + mã lỗi (không in nội dung câu hỏi / SQL) để chạy được trên test.jsonl.
--verbose in thêm chi tiết (thông báo SQLite, một phần SQL) — chỉ dùng khi tự mình đọc kết quả.
--questions-only: mới viết câu hỏi, chưa có SQL. Vd kiểm câu test có gần giống câu dev không:
    python scripts/check_dataset.py data/questions/dev.jsonl data/questions/test.jsonl --questions-only
Exit code 1 nếu có ERROR.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # để import được src/ khi chạy như script

from src.db.executor import DEFAULT_DB  # noqa: E402
from src.eval.dataset import (  # noqa: E402
    Issue, check_file, duplicate_questions, kind_of, similar_questions, summarize)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kiểm bộ câu hỏi (docs/dataset.md)")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--verbose", action="store_true", help="in chi tiết lỗi (có thể chứa SQL)")
    parser.add_argument("--no-sql", action="store_true", help="chỉ kiểm định dạng, không chạy SQL")
    parser.add_argument("--questions-only", action="store_true",
                        help="chỉ kiểm câu hỏi: không đòi trường sql, không chạy SQL")
    return parser.parse_args(argv)


def format_issue(issue: Issue, verbose: bool) -> str:
    line = f"  {issue.level:<5} {issue.qid:<12} {issue.code}"
    return f"{line}  {issue.detail}" if verbose and issue.detail else line


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    all_records: dict[str, list[dict]] = {}
    n_errors = n_warnings = 0
    for path in args.files:
        records, issues = check_file(path, args.db, run_sql=not args.no_sql, questions_only=args.questions_only)
        all_records[path.name] = records
        print(f"{path} [{kind_of(path)}]")
        for issue in issues:
            print(format_issue(issue, args.verbose))
        print("\n".join(summarize(kind_of(path), records)))
        n_errors += sum(i.level == "ERROR" for i in issues)
        n_warnings += sum(i.level == "WARN" for i in issues)

    duplicates = duplicate_questions(all_records) + similar_questions(all_records)
    if duplicates:
        print("Câu hỏi trùng / gần giống (giữa các file):")
        for issue in duplicates:
            print(format_issue(issue, verbose=True))  # chỉ chứa id + độ giống, an toàn để in
    n_warnings += len(duplicates)
    print(f"Tổng: {n_errors} ERROR, {n_warnings} WARN")
    return 1 if n_errors else 0


if __name__ == "__main__":
    sys.exit(main())
