"""Chạy pipeline Text-to-SQL trên một bộ câu hỏi.

Chạy:  python scripts/run_pipeline.py --config C1 --model haiku --split dev [--limit 5] [--repeats 3]

Kết quả:
- results/raw/<run_id>.jsonl   — từng câu (gitignore, có SQL model sinh ra)
- results/<run_id>_summary.json — số liệu tổng hợp (commit được)

Split test bị chặn: chỉ chạy ở T5, do người làm dự án chủ động chạy với cờ --i-am-running-final-test.
Tốn tiền thật — dùng --limit để thử trước.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db.executor import DEFAULT_DB  # noqa: E402
from src.eval.dataset import load_jsonl  # noqa: E402
from src.pipeline.fewshot import K_EXAMPLES, load_pool  # noqa: E402
from src.pipeline.llm import MODELS, AnthropicLLM  # noqa: E402
from src.pipeline.prompts import CONFIGS, FEWSHOT_CONFIGS, PROMPT_TEXTS  # noqa: E402
from src.pipeline.run import MAX_REPAIRS, Record, run, summarize  # noqa: E402

SPLITS = {name: ROOT / "data" / "questions" / f"{name}.jsonl" for name in ("dev", "ambiguous", "malicious", "test")}
RESULTS = ROOT / "results"


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("phải >= 1")  # --limit 0 không được hiểu thành "chạy hết"
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chạy pipeline Text-to-SQL")
    parser.add_argument("--config", choices=CONFIGS, required=True)
    parser.add_argument("--model", choices=sorted(MODELS), required=True)
    parser.add_argument("--split", choices=sorted(SPLITS), default="dev")
    parser.add_argument("--limit", type=positive_int, default=None, help="chỉ chạy N câu đầu (để thử, đỡ tốn tiền)")
    parser.add_argument("--repeats", type=positive_int, default=1,
                        help="chạy lặp để đo dao động (không đặt được temperature)")
    parser.add_argument("--max-cost", type=float, default=None, help="dừng khi tổng chi phí (USD) vượt mức này")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--i-am-running-final-test", action="store_true", dest="final_test",
                        help="bắt buộc khi --split test (chỉ dùng ở T5)")
    return parser.parse_args(argv)


def check_split_allowed(split: str, final_test: bool) -> None:
    """Guardrail: bộ test chỉ chạy một lần ở T5 khi người làm dự án yêu cầu rõ."""
    if split == "test" and not final_test:
        raise SystemExit("Từ chối: split test chỉ chạy ở T5 với cờ --i-am-running-final-test.")


def load_questions(split: str, limit: int | None) -> list[dict]:
    records, issues = load_jsonl(SPLITS[split])
    if issues:
        raise SystemExit(f"File {split} có lỗi định dạng; chạy scripts/check_dataset.py trước.")
    return records[:limit] if limit is not None else records


def prompt_hash() -> str:
    """Mã của prompt hiện tại — để biết hai lượt chạy có dùng cùng prompt không khi so sánh."""
    settings = f"k={K_EXAMPLES};repairs={MAX_REPAIRS}"
    return hashlib.sha256("\n".join([*PROMPT_TEXTS, settings]).encode("utf-8")).hexdigest()[:12]


def pool_hash(pool: tuple[dict, ...]) -> str | None:
    """Mã của kho ví dụ (C3/C4): sửa dev.jsonl thì ví dụ đổi → hai lượt chạy không còn cùng prompt."""
    if not pool:
        return None
    text = json.dumps([(r["id"], r["question"], r["sql"]) for r in pool], ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class BudgetExceeded(Exception):
    pass


def main(argv: list[str] | None = None, llm_factory=AnthropicLLM, results_dir: Path = RESULTS) -> int:
    """llm_factory / results_dir chỉ để test thay bằng LLM giả và thư mục tạm."""
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    check_split_allowed(args.split, args.final_test)
    questions = load_questions(args.split, args.limit)
    run_id = f"{args.split}_{args.config}_{args.model}_{time.strftime('%Y%m%d-%H%M%S')}"
    (results_dir / "raw").mkdir(parents=True, exist_ok=True)
    raw_path = results_dir / "raw" / f"{run_id}.jsonl"
    done: list[Record] = []

    with raw_path.open("w", encoding="utf-8") as raw:
        def on_record(record: Record) -> None:
            done.append(record)
            raw.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
            raw.flush()  # ghi ngay: lỡ dừng giữa chừng vẫn còn kết quả các câu đã chạy
            mark = "✓" if record.correct else "✗"
            print(f"  {mark} {record.id:<10} {record.reason:<16} ${record.cost:.5f}  {record.latency_s:.1f}s")
            spent = sum(r.cost for r in done)
            if args.max_cost is not None and spent > args.max_cost:
                raise BudgetExceeded(f"đã tiêu ${spent:.4f} > --max-cost {args.max_cost}")

        kind = "malicious" if args.split == "malicious" else "qa"
        pool = load_pool() if args.config in FEWSHOT_CONFIGS else ()  # kho ví dụ: luôn là dev
        stopped = None
        try:
            run(questions, args.config, llm_factory(args.model), kind, args.db, args.repeats, on_record, pool)
        except BudgetExceeded as exc:
            stopped = str(exc)
            print(f"DỪNG: {stopped}")

    summary = {"run_id": run_id, "split": args.split, "config": args.config, "model": args.model,
               "model_id": MODELS[args.model].model_id, "limit": args.limit, "db": str(args.db),
               "prompt_hash": prompt_hash(), "pool_hash": pool_hash(pool), "stopped": stopped,
               **summarize(done)}
    (results_dir / f"{run_id}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{run_id}: accuracy {summary['accuracy']:.1%}, chạy được {summary['executable_rate']:.1%}, "
          f"chi phí ${summary['total_cost_usd']:.4f}, lỗi API {summary['errors']}")
    return 0 if stopped is None else 2


if __name__ == "__main__":
    sys.exit(main())
