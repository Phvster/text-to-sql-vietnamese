"""In bảng so sánh các lượt chạy (đọc results/*_summary.json).

Chạy: python scripts/compare_runs.py [--split dev]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"


def load_summaries(split: str | None) -> list[dict]:
    summaries = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS.glob("*_summary.json"))]
    return [s for s in summaries if split is None or s.get("split") == split]


def format_table(summaries: list[dict]) -> str:
    """Một dòng mỗi lượt chạy. Cột "thử" = chạy với --limit (không so sánh được với lượt đầy đủ)."""
    header = (f"{'run':<38} {'thử':>4} {'câu':>4} {'acc':>7} {'±std':>6} {'exec':>7} "
              f"{'recall':>7} {'lỗi':>4} {'cost $':>9} {'lat s':>6}")
    lines = [header, "-" * len(header)]
    for s in sorted(summaries, key=lambda s: (s["model"], s["config"], s["run_id"])):
        if not s.get("n"):
            continue  # lượt chạy rỗng (bị dừng trước câu đầu tiên)
        recall = "-" if s.get("linking_recall") is None else f"{s['linking_recall']:.1%}"
        trial = "có" if s.get("limit") else ""
        lines.append(f"{s['run_id']:<38} {trial:>4} {s.get('n_questions', s['n']):>4} {s['accuracy']:>7.1%} "
                     f"{s.get('accuracy_std', 0):>6.1%} {s['executable_rate']:>7.1%} {recall:>7} "
                     f"{s.get('errors', 0):>4} {s['total_cost_usd']:>9.4f} {s['mean_latency_s']:>6.2f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev")
    args = parser.parse_args(argv)
    summaries = load_summaries(args.split)
    print(format_table(summaries) if summaries else "Chưa có lượt chạy nào.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
