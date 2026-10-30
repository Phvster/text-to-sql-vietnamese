"""Chạy cả ma trận cấu hình × model của một split, đúng như docs/analysis_plan.md.

Chạy thử (không gọi API, không đọc câu hỏi):  python scripts/run_matrix.py --split test --dry-run
Chạy thật bộ test (CHỈ ở T5, khi người làm dự án yêu cầu):
    python scripts/run_matrix.py --split test --i-am-running-final-test

Mỗi ô gọi lại scripts/run_pipeline.py (cùng chốt chặn, cùng cách ghi kết quả). Ngân sách --max-cost là TỔNG
cho cả ma trận: mỗi ô nhận phần còn lại, vượt thì dừng luôn các ô sau.

- Trước khi tốn tiền: prompt hiện tại phải đúng FROZEN_PROMPT_HASH (đã ghi trong docs/analysis_plan.md).
- Chạy lại sau khi bị ngắt: ô nào đã có lượt đầy đủ đúng kế hoạch thì BỎ QUA (không chạy test hai lần),
  chi phí của ô đó vẫn tính vào ngân sách tổng.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.dataset import SIZE_TARGET, load_jsonl  # noqa: E402
from src.pipeline.llm import MODELS  # noqa: E402
from src.pipeline.prompts import CONFIGS  # noqa: E402


def _load_run_pipeline():
    spec = importlib.util.spec_from_file_location("run_pipeline", ROOT / "scripts" / "run_pipeline.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("run_pipeline", module)
    spec.loader.exec_module(module)
    return module


run_pipeline = _load_run_pipeline()

# (model, cấu hình, số lần lặp) — chốt trong docs/analysis_plan.md
MATRIX: dict[str, list[tuple[str, str, int]]] = {
    "test": [("haiku", c, 3) for c in CONFIGS] + [("sonnet", "C0", 1), ("sonnet", "C3", 1)],
    "ambiguous": [("haiku", c, 1) for c in CONFIGS],
    "malicious": [("haiku", c, 1) for c in CONFIGS],
    "dev": [("haiku", c, 1) for c in CONFIGS],
}
DEFAULT_COST_PER_QUESTION = 0.0003  # khi chưa có lượt dev nào để ước tính
FROZEN_PROMPT_HASH = "1ca9c19a74a1"  # prompt + K + MAX_REPAIRS của lượt dev C3/C4 cuối (docs/analysis_plan.md)
DEFAULT_MAX_COST = 2.0


def check_frozen_prompt() -> None:
    current = run_pipeline.prompt_hash()
    if current != FROZEN_PROMPT_HASH:
        raise SystemExit(f"Từ chối: prompt đã đổi ({current} ≠ {FROZEN_PROMPT_HASH} đã đăng ký). "
                         "Sửa lại prompt, hoặc ghi sai lệch vào docs/analysis_plan.md rồi cập nhật hash.")


def completed_cost(split: str, model: str, config: str, repeats: int, results_dir: Path) -> float | None:
    """Chi phí của lượt đầy đủ đúng kế hoạch đã có (để bỏ qua khi chạy lại); None nếu chưa có."""
    for path in sorted(results_dir.glob(f"{split}_{config}_{model}_*_summary.json"), reverse=True):
        s = json.loads(path.read_text(encoding="utf-8"))
        if (s.get("n") and s.get("limit") is None and not s.get("stopped") and s.get("repeats") == repeats
                and s.get("prompt_hash") == FROZEN_PROMPT_HASH):
            return s["total_cost_usd"]
    return None


def cost_per_question(model: str, config: str, results_dir: Path) -> float:
    """Ước tính $/câu từ lượt dev đầy đủ mới nhất. Chưa có (vd Sonnet C3) → suy từ Haiku theo tỉ lệ giá."""
    def from_dev(m: str) -> float | None:
        found = None
        for path in sorted(results_dir.glob(f"dev_{config}_{m}_*_summary.json")):
            s = json.loads(path.read_text(encoding="utf-8"))
            if s.get("n") and s.get("limit") is None and not s.get("stopped"):
                found = s["total_cost_usd"] / s["n"]
        return found

    direct = from_dev(model)
    if direct is not None:
        return direct
    haiku = from_dev("haiku") or DEFAULT_COST_PER_QUESTION
    return haiku * MODELS[model].output_per_mtok / MODELS["haiku"].output_per_mtok


def plan(split: str, results_dir: Path) -> list[tuple[str, str, int, float]]:
    """Các ô sẽ chạy kèm chi phí ước tính. test: số câu lấy từ SIZE_TARGET — không mở test.jsonl."""
    n = SIZE_TARGET["test"] if split == "test" else len(load_jsonl(run_pipeline.SPLITS[split])[0])
    return [(m, c, r, cost_per_question(m, c, results_dir) * n * r) for m, c, r in MATRIX[split]]


def _latest_cost(split: str, model: str, config: str, results_dir: Path) -> float:
    paths = sorted(results_dir.glob(f"{split}_{config}_{model}_*_summary.json"))
    return json.loads(paths[-1].read_text(encoding="utf-8"))["total_cost_usd"] if paths else 0.0


def main(argv: list[str] | None = None, llm_factory=None, results_dir: Path = run_pipeline.RESULTS) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Chạy ma trận cấu hình × model")
    parser.add_argument("--split", choices=sorted(MATRIX), required=True)
    parser.add_argument("--max-cost", type=float, default=DEFAULT_MAX_COST, help="ngân sách TỔNG (USD) cho cả ma trận")
    parser.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch + chi phí ước tính")
    parser.add_argument("--i-am-running-final-test", action="store_true", dest="final_test")
    args = parser.parse_args(argv)
    if not args.dry_run:  # dry-run không đọc câu hỏi, không gọi API → không cần cờ
        run_pipeline.check_split_allowed(args.split, args.final_test)  # chặn trước mọi việc khác

    cells = plan(args.split, results_dir)
    for m, c, r, est in cells:
        print(f"  {m:<7} {c}  × {r} lần lặp   ước tính ${est:.3f}")
    print(f"Tổng ước tính ${sum(e for *_, e in cells):.3f} (trần ${args.max_cost})")
    if args.dry_run:
        return 0
    check_frozen_prompt()

    spent = 0.0
    for model, config, repeats, _ in cells:
        done = completed_cost(args.split, model, config, repeats, results_dir)
        if done is not None:
            print(f"\n== {model} {config} × {repeats}: đã có lượt đầy đủ — bỏ qua (${done:.4f})")
            spent += done
            continue
        remaining = args.max_cost - spent
        if remaining <= 0:
            print("DỪNG: hết ngân sách tổng.")
            return 2
        cell_argv = ["--config", config, "--model", model, "--split", args.split, "--repeats", str(repeats),
                     "--max-cost", f"{remaining:.6f}"] + (["--i-am-running-final-test"] if args.final_test else [])
        print(f"\n== {model} {config} × {repeats}")
        extra = {} if llm_factory is None else {"llm_factory": llm_factory}
        code = run_pipeline.main(cell_argv, results_dir=results_dir, **extra)
        spent += _latest_cost(args.split, model, config, results_dir)
        if code != 0:
            print(f"DỪNG: ô {model} {config} vượt ngân sách (đã tiêu ${spent:.4f}).")
            return code
    print(f"\nXong ma trận {args.split}: tổng chi phí ${spent:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
