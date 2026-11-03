"""Chấm lại SQL model đã sinh theo đáp án đã sửa — KHÔNG gọi API (sai lệch #1–#3 trong docs/analysis_plan.md).

    python scripts/regrade.py --split test
    python scripts/analyze_runs.py --split test --corrected   # → results/report_test_corrected.md

- Đọc đúng các lượt mà báo cáo gốc dùng (cùng bộ lọc prompt đã đóng băng + số lần lặp).
- Câu có đề khác bản tại BASELINE_REF (đề model đã thấy) → loại khỏi MỌI cấu hình: SQL của model trả lời đề cũ,
  chấm với đáp án của đề mới là vô nghĩa.
- Chấm bằng chính `grade()` của pipeline → SQL vẫn đi qua src/db/executor.py, cùng evaluator.
- Ghi vào results/corrected/ — file gốc giữ nguyên để báo được cả hai bộ số.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_runs import RESULTS, load_records, load_summaries, select_runs  # noqa: E402
from run_matrix import FROZEN_PROMPT_HASH, MATRIX  # noqa: E402
from src.db.executor import DEFAULT_DB  # noqa: E402
from src.eval.dataset import load_jsonl  # noqa: E402
from src.pipeline.run import Record, grade, summarize  # noqa: E402

BASELINE_REF = "b491734"  # commit kế hoạch phân tích, ngay trước lượt test 2026-10-31 01:36
CORRECTED = RESULTS / "corrected"
SPLIT_PATH = {"test": ROOT / "data" / "questions" / "test.jsonl"}


def git_baseline(split: str) -> dict[str, str]:
    """{id: đề} của split tại BASELINE_REF — đúng đề mà model đã nhận."""
    rel = SPLIT_PATH[split].relative_to(ROOT).as_posix()
    text = subprocess.run(["git", "show", f"{BASELINE_REF}:{rel}"], cwd=ROOT, capture_output=True,
                          check=True, encoding="utf-8").stdout
    rows = [json.loads(line) for line in text.lstrip("﻿").splitlines() if line.strip()]
    return {r["id"]: r["question"] for r in rows}


def excluded_ids(baseline: dict[str, str], current: dict[str, dict]) -> list[str]:
    """Câu bị đổi đề, bị xóa hoặc mới thêm so với bản gốc."""
    ids = baseline.keys() | current.keys()
    return sorted(i for i in ids if i not in baseline or i not in current
                  or baseline[i] != current[i]["question"])


def regrade_record(raw: dict, question: dict, db_path: Path) -> Record:
    """Dựng lại bản ghi, xóa kết quả chấm cũ, chấm lại. Giữ nguyên SQL, từ chối, lỗi API, chi phí."""
    record = Record(**raw)
    record.correct, record.executable, record.reason = False, False, ""
    record.first_correct, record.linking_recall = None, None
    # tag/độ khó lấy theo bản đã sửa (có thể đã được gắn lại) — bảng theo nhóm dùng các trường này
    record.difficulty, record.tags = question.get("difficulty"), list(question.get("tags") or [])
    return grade(record, question, record.sql, "qa", db_path)


def _flips(old: list[dict], new: list[Record]) -> tuple[int, int]:
    before = {(r["id"], r["repeat"]): r["correct"] for r in old}
    gained = sum(r.correct and not before[(r.id, r.repeat)] for r in new)
    lost = sum(before[(r.id, r.repeat)] and not r.correct for r in new)
    return gained, lost


def main(argv: list[str] | None = None, results_dir: Path = RESULTS, out_dir: Path = CORRECTED,
         baseline: Callable[[str], dict[str, str]] = git_baseline, questions_path: Path | None = None,
         db_path: Path = DEFAULT_DB) -> int:
    """baseline / questions_path / out_dir chỉ để test thay bằng dữ liệu giả."""
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Chấm lại theo đáp án đã sửa (không gọi API)")
    parser.add_argument("--split", choices=sorted(SPLIT_PATH), default="test")
    args = parser.parse_args(argv)

    path = questions_path or SPLIT_PATH[args.split]
    questions = {q["id"]: q for q in load_jsonl(path)[0]}
    excluded = excluded_ids(baseline(args.split), questions)
    print(f"Loại {len(excluded)} câu đổi đề / thêm / xóa: {', '.join(excluded) or '(không có)'}")

    planned = {(m, c): r for m, c, r in MATRIX[args.split]}
    runs = select_runs(load_summaries(args.split, results_dir), FROZEN_PROMPT_HASH, planned)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)
    info = {"baseline_ref": BASELINE_REF, "excluded": excluded,
            "gold_sha": hashlib.sha256(path.read_bytes()).hexdigest()[:12]}
    print("\n| Lượt | Đáp án gốc | Đáp án đã sửa | sai→đúng | đúng→sai |\n|---|---|---|---|---|")
    for key, summary in sorted(runs.items()):
        old = load_records(summary["run_id"], results_dir)
        if old is None:
            print(f"⚠️ Thiếu file raw của {summary['run_id']} — bỏ qua.")
            continue
        old = [r for r in old if r["id"] not in excluded]
        if not old:
            print(f"⚠️ {summary['run_id']}: mọi câu đều bị loại — bỏ qua.")
            continue
        new = [regrade_record(r, questions[r["id"]], db_path) for r in old]
        run_id = summary["run_id"]
        (out_dir / "raw" / f"{run_id}.jsonl").write_text(
            "".join(json.dumps(asdict(r), ensure_ascii=False) + "\n" for r in new), encoding="utf-8")
        new_summary = {**summary, **summarize(new), "regraded": info}
        (out_dir / f"{run_id}_summary.json").write_text(
            json.dumps(new_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        gained, lost = _flips(old, new)
        old_acc = sum(r["correct"] for r in old) / len(old)  # cùng tập câu → chênh lệch chỉ do đáp án
        print(f"| {key[0]} {key[1]} | {old_acc:.1%} | {new_summary['accuracy']:.1%} | {gained} | {lost} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
