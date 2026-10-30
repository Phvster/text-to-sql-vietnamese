"""Test thống kê (src/eval/stats.py), báo cáo (analyze_runs) và chạy ma trận (run_matrix) — không gọi API."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from src.eval.stats import (bootstrap_ci, discordant, holm, majority, mcnemar_exact, paired_bootstrap_diff,
                            per_question)
from src.pipeline.llm import FakeLLM

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


analyze = _load_script("analyze_runs")
run_matrix = _load_script("run_matrix")


# --------------------------------------------------------------------------- stats


def test_mcnemar_known_value() -> None:
    assert mcnemar_exact(7, 2) == pytest.approx(0.1797, abs=1e-4)  # 2·(1+9+36)/512


@pytest.mark.parametrize("b, c", [(0, 0), (3, 3), (10, 10)])
def test_mcnemar_no_difference(b: int, c: int) -> None:
    assert mcnemar_exact(b, c) == 1.0


def test_mcnemar_symmetric_and_small() -> None:
    assert mcnemar_exact(2, 9) == mcnemar_exact(9, 2)
    assert mcnemar_exact(0, 10) == pytest.approx(2 / 1024)


def test_holm_hand_example() -> None:
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert all(p <= 1.0 for p in holm([0.5, 0.6, 0.9]))
    assert holm([]) == []


def test_bootstrap_deterministic_and_contains_mean() -> None:
    values = [1.0] * 30 + [0.0] * 20
    first = bootstrap_ci(values, n=2000)
    assert first == bootstrap_ci(values, n=2000)
    mean, lo, hi = first
    assert mean == pytest.approx(0.6) and lo <= mean <= hi and hi - lo > 0


def test_bootstrap_constant_values_zero_width() -> None:
    assert bootstrap_ci([1.0] * 10, n=500) == (1.0, 1.0, 1.0)


def test_bootstrap_empty_raises() -> None:
    with pytest.raises(ValueError):
        bootstrap_ci([])


def recs(pattern: dict[str, list[bool]]) -> list[dict]:
    return [{"id": qid, "correct": ok, "repeat": i} for qid, oks in pattern.items() for i, ok in enumerate(oks)]


def test_per_question_and_majority_with_repeats() -> None:
    records = recs({"a": [True, True, False], "b": [False, False, True], "c": [True, True, True]})
    assert per_question(records) == pytest.approx({"a": 2 / 3, "b": 1 / 3, "c": 1.0})
    assert majority(records) == {"a": True, "b": False, "c": True}


def test_paired_requires_same_questions() -> None:
    with pytest.raises(ValueError):
        paired_bootstrap_diff({"a": 1.0}, {"b": 1.0})
    with pytest.raises(ValueError):
        discordant({"a": True}, {"b": True})


def test_discordant_counts() -> None:
    a = {"q1": False, "q2": True, "q3": True, "q4": False}
    b = {"q1": True, "q2": False, "q3": True, "q4": False}
    assert discordant(a, b) == (1, 1)


# --------------------------------------------------------------------------- analyze_runs


def _write_run(results: Path, run_id: str, model: str, config: str, correct: dict[str, list[bool]],
               limit: int | None = None, stopped: str | None = None, split: str = "dev") -> None:
    (results / "raw").mkdir(parents=True, exist_ok=True)
    rows = [{"id": qid, "correct": ok, "repeat": i, "difficulty": "easy", "tags": ["join"],
             "reason": "match" if ok else "mismatch"}
            for qid, oks in correct.items() for i, ok in enumerate(oks)]
    (results / "raw" / f"{run_id}.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    summary = {"run_id": run_id, "split": split, "model": model, "config": config, "limit": limit,
               "stopped": stopped, "n": len(rows), "n_questions": len(correct),
               "repeats": max(len(v) for v in correct.values()), "executable_rate": 1.0,
               "total_cost_usd": 0.01, "mean_latency_s": 1.0, "prompt_hash": "h", "reasons": {"match": 1}}
    (results / f"{run_id}_summary.json").write_text(json.dumps(summary), encoding="utf-8")


def test_select_runs_latest_full_only() -> None:
    summaries = [
        {"run_id": "dev_C0_haiku_20261001-000000", "model": "haiku", "config": "C0", "limit": None, "stopped": None, "n": 5},
        {"run_id": "dev_C0_haiku_20261002-000000", "model": "haiku", "config": "C0", "limit": None, "stopped": None, "n": 5},
        {"run_id": "dev_C0_haiku_20261003-000000", "model": "haiku", "config": "C0", "limit": 1, "stopped": None, "n": 1},
        {"run_id": "dev_C0_haiku_20261004-000000", "model": "haiku", "config": "C0", "limit": None, "stopped": "hết tiền", "n": 2},
    ]
    assert analyze.select_runs(summaries)[("haiku", "C0")]["run_id"].endswith("20261002-000000")


def test_report_end_to_end(tmp_path: Path) -> None:
    ids = [f"q{i}" for i in range(10)]
    _write_run(tmp_path, "dev_C0_haiku_20261001-000000", "haiku", "C0", {q: [i < 5] * 3 for i, q in enumerate(ids)})
    _write_run(tmp_path, "dev_C1_haiku_20261001-000001", "haiku", "C1", {q: [True] * 3 for q in ids})
    report = analyze.build_report("dev", tmp_path)
    assert "haiku C0 → haiku C1" in report and "| 5 | 0 |" in report  # b=5, c=0
    assert "50.0" in report and "100.0" in report


def test_report_empty_split(tmp_path: Path) -> None:
    assert "Chưa có" in analyze.build_report("dev", tmp_path)


# --------------------------------------------------------------------------- run_matrix


def _never(*_a, **_k):
    raise AssertionError("không được gọi LLM / đọc câu hỏi")


def test_matrix_test_split_blocked_without_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_matrix.run_pipeline, "load_questions", _never)
    with pytest.raises(SystemExit):
        run_matrix.main(["--split", "test"], llm_factory=_never, results_dir=tmp_path)


def test_matrix_dry_run_calls_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_matrix.run_pipeline, "load_questions", _never)
    monkeypatch.setattr(run_matrix.run_pipeline, "main", _never)
    assert run_matrix.main(["--split", "test", "--dry-run"], results_dir=tmp_path) == 0


def test_matrix_plan_matches_analysis_plan() -> None:
    cells = [(m, c, r) for m, c, r in run_matrix.MATRIX["test"]]
    assert cells == [("haiku", c, 3) for c in ("C0", "C1", "C2", "C3", "C4")] + [("sonnet", "C0", 1), ("sonnet", "C3", 1)]


def test_matrix_stops_when_total_budget_exceeded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_main(argv, results_dir, **_kw):
        calls.append(argv)
        model, config = argv[argv.index("--model") + 1], argv[argv.index("--config") + 1]
        _write_run(results_dir, f"dev_{config}_{model}_2026{len(calls):04d}", model, config, {"q": [True]})
        summary = results_dir / f"dev_{config}_{model}_2026{len(calls):04d}_summary.json"
        data = json.loads(summary.read_text(encoding="utf-8"))
        data["total_cost_usd"] = 0.4
        summary.write_text(json.dumps(data), encoding="utf-8")
        return 0

    monkeypatch.setattr(run_matrix.run_pipeline, "main", fake_main)
    code = run_matrix.main(["--split", "dev", "--max-cost", "1.0"], llm_factory=lambda name: FakeLLM({}),
                           results_dir=tmp_path)
    assert code == 2 and len(calls) == 3  # 0.4 + 0.4 + 0.4 > 1.0 → ô thứ 4 không chạy
    assert float(calls[1][calls[1].index("--max-cost") + 1]) == pytest.approx(0.6)  # ô sau nhận phần còn lại


# =========================================================================== Bổ sung sau review


def test_paired_diff_sign_and_majority_tie() -> None:
    diff, lo, hi = paired_bootstrap_diff({"a": 0.0, "b": 0.0}, {"a": 1.0, "b": 1.0}, n=200)
    assert diff == 1.0 and lo == hi == 1.0  # B − A
    assert majority(recs({"q": [True, False]})) == {"q": True}  # hòa → đúng (đã ghi trong docstring)


def test_verdict_requires_same_direction() -> None:
    r = {"diff": 0.05, "lo": 0.01, "hi": 0.09, "b": 2, "c": 9}  # CI dương nhưng McNemar nghiêng ngược lại
    assert analyze._verdict(r, 0.01) == "chưa đủ bằng chứng"
    assert analyze._verdict({**r, "b": 9, "c": 2}, 0.01) == "B tốt hơn"
    assert analyze._verdict({"diff": -0.05, "lo": -0.09, "hi": -0.01, "b": 2, "c": 9}, 0.01) == "B kém hơn"


def test_holm_family_keeps_m4_when_run_missing(tmp_path: Path) -> None:
    ids = [f"q{i}" for i in range(20)]
    _write_run(tmp_path, "dev_C0_haiku_20261001-000000", "haiku", "C0", {q: [False] for q in ids})
    _write_run(tmp_path, "dev_C1_haiku_20261001-000001", "haiku", "C1", {q: [True] for q in ids})
    report = analyze.build_report("dev", tmp_path)
    row = next(line for line in report.splitlines() if line.startswith("| haiku C0 → haiku C1"))
    p_raw = mcnemar_exact(20, 0)
    assert f"{min(1.0, 4 * p_raw):.3f}" in row  # m = 4, không phải 1
    assert "thiếu lượt chạy" in report


def test_report_survives_different_question_sets_and_missing_raw(tmp_path: Path) -> None:
    _write_run(tmp_path, "dev_C0_haiku_20261001-000000", "haiku", "C0", {"q1": [True], "q2": [False]})
    _write_run(tmp_path, "dev_C1_haiku_20261001-000001", "haiku", "C1", {"q1": [True], "q3": [True]})
    _write_run(tmp_path, "dev_C2_haiku_20261001-000002", "haiku", "C2", {"q1": [True]})
    (tmp_path / "raw" / "dev_C2_haiku_20261001-000002.jsonl").unlink()
    report = analyze.build_report("dev", tmp_path)
    assert "khác tập câu hỏi" in report and "Thiếu file raw" in report


def test_select_runs_filters_hash_and_repeats() -> None:
    base = {"model": "haiku", "config": "C0", "limit": None, "stopped": None, "n": 450}
    summaries = [{**base, "run_id": "test_C0_haiku_1", "prompt_hash": "good", "repeats": 3},
                 {**base, "run_id": "test_C0_haiku_2", "prompt_hash": "good", "repeats": 1},
                 {**base, "run_id": "test_C0_haiku_3", "prompt_hash": "other", "repeats": 3}]
    chosen = analyze.select_runs(summaries, "good", {("haiku", "C0"): 3})
    assert chosen[("haiku", "C0")]["run_id"] == "test_C0_haiku_1"


def test_matrix_refuses_changed_prompt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_matrix, "FROZEN_PROMPT_HASH", "khac")
    monkeypatch.setattr(run_matrix.run_pipeline, "main", _never)
    with pytest.raises(SystemExit):
        run_matrix.main(["--split", "dev"], results_dir=tmp_path)


def test_matrix_resume_skips_done_and_passes_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for c in ("C0", "C1"):  # hai ô đầu đã chạy xong đúng kế hoạch
        _write_run(tmp_path, f"test_{c}_haiku_20261101-00000{c[1]}", "haiku", c, {"q": [True] * 3}, split="test")
        path = tmp_path / f"test_{c}_haiku_20261101-00000{c[1]}_summary.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(prompt_hash=run_matrix.FROZEN_PROMPT_HASH, total_cost_usd=0.05)
        path.write_text(json.dumps(data), encoding="utf-8")
    calls: list[list[str]] = []

    def fake_main(argv, results_dir, **_kw):
        calls.append(argv)
        return 0

    monkeypatch.setattr(run_matrix.run_pipeline, "main", fake_main)
    monkeypatch.setattr(run_matrix.run_pipeline, "load_questions", _never)
    assert run_matrix.main(["--split", "test", "--i-am-running-final-test"], results_dir=tmp_path) == 0
    configs = [(a[a.index("--model") + 1], a[a.index("--config") + 1]) for a in calls]
    assert ("haiku", "C0") not in configs and ("haiku", "C1") not in configs and len(calls) == 5
    assert all("--i-am-running-final-test" in a for a in calls)
    assert float(calls[0][calls[0].index("--max-cost") + 1]) == pytest.approx(run_matrix.DEFAULT_MAX_COST - 0.10)
