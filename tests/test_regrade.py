"""scripts/regrade.py — chấm lại theo đáp án đã sửa. DB thật, không gọi API, không đọc test.jsonl thật."""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

from src.pipeline.run import Record

ROOT = Path(__file__).resolve().parents[1]
ALL = "SELECT COUNT(*) FROM orders"
NOT_CANCELLED = "SELECT COUNT(*) FROM orders WHERE status != 'cancelled'"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


regrade = _load_script("regrade")
analyze = sys.modules["analyze_runs"]
FROZEN = sys.modules["run_matrix"].FROZEN_PROMPT_HASH


def _rec(qid: str, repeat: int = 0, **kw) -> dict:
    return asdict(Record(id=qid, config="C0", model="haiku", repeat=repeat, difficulty="easy", tags=["date"], **kw))


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    """Lượt haiku C0 × 3 với: q1 sai→đúng, q5 đúng→sai, q2 đổi đề, q3 từ chối, q4 lỗi API."""
    results = tmp_path / "results"
    (results / "raw").mkdir(parents=True)
    rows = []
    for rep in range(3):
        rows += [_rec("q1", rep, sql=NOT_CANCELLED, first_sql=NOT_CANCELLED, correct=False, reason="mismatch"),
                 _rec("q5", rep, sql=ALL, first_sql=ALL, correct=True, reason="match"),
                 _rec("q2", rep, sql=ALL, first_sql=ALL, correct=True, reason="match"),
                 _rec("q3", rep, refused=True, reason="refused"),
                 _rec("q4", rep, error="boom", reason="api_error")]
    run_id = "test_C0_haiku_20261031-013612"
    (results / "raw" / f"{run_id}.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    summary = {"run_id": run_id, "split": "test", "model": "haiku", "config": "C0", "limit": None, "stopped": None,
               "n": len(rows), "repeats": 3, "prompt_hash": FROZEN, "accuracy": 0.4, "total_cost_usd": 0.0}
    (results / f"{run_id}_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    questions = tmp_path / "test.jsonl"
    new = [{"id": "q1", "question": "Q1", "sql": NOT_CANCELLED}, {"id": "q5", "question": "Q5", "sql": NOT_CANCELLED},
           {"id": "q2", "question": "Q2 đã đổi", "sql": ALL}, {"id": "q3", "question": "Q3", "sql": ALL},
           {"id": "q4", "question": "Q4", "sql": ALL}]
    questions.write_text("\n".join(json.dumps(q, ensure_ascii=False) for q in new), encoding="utf-8")
    return results, questions


BASELINE = {"q1": "Q1", "q5": "Q5", "q2": "Q2", "q3": "Q3", "q4": "Q4", "q9": "Q9 đã bị xóa"}


def _run(tmp_path: Path) -> tuple[Path, list[dict], dict]:
    results, questions = _setup(tmp_path)
    original = {p.name: p.read_bytes() for p in results.rglob("*") if p.is_file()}
    assert regrade.main(["--split", "test"], results_dir=results, out_dir=results / "corrected",
                        baseline=lambda _s: BASELINE, questions_path=questions) == 0
    assert {p.name: p.read_bytes() for p in results.rglob("*") if p.is_file() and "corrected" not in p.parts} \
        == original  # không ghi đè kết quả gốc
    out = results / "corrected"
    raw = [json.loads(line) for line in (out / "raw" / "test_C0_haiku_20261031-013612.jsonl").read_text(
        encoding="utf-8").splitlines()]
    summary = json.loads((out / "test_C0_haiku_20261031-013612_summary.json").read_text(encoding="utf-8"))
    return results, raw, summary


def test_excluded_ids_changed_added_removed() -> None:
    current = {"a": {"question": "A"}, "b": {"question": "B mới"}, "c": {"question": "C"}}
    assert regrade.excluded_ids({"a": "A", "b": "B", "d": "D"}, current) == ["b", "c", "d"]


def test_regrade_flips_both_ways_and_keeps_refusal_and_api_error(tmp_path: Path) -> None:
    _, raw, summary = _run(tmp_path)
    by_id = {}
    for r in raw:
        by_id.setdefault(r["id"], []).append(r)
    assert set(by_id) == {"q1", "q5", "q3", "q4"}  # q2 đổi đề → loại
    assert all(r["correct"] and r["reason"] == "match" for r in by_id["q1"])
    assert all(not r["correct"] and r["reason"] == "mismatch" for r in by_id["q5"])
    assert all(r["reason"] == "refused" and not r["correct"] for r in by_id["q3"])
    assert all(r["reason"] == "api_error" and not r["correct"] for r in by_id["q4"])
    assert summary["accuracy"] == 0.25 and summary["n_questions"] == 4
    assert summary["regraded"]["excluded"] == ["q2", "q9"]
    assert summary["prompt_hash"] == FROZEN  # metadata gốc giữ nguyên → analyze_runs vẫn chọn được lượt


def test_regrade_record_rechecks_first_sql_for_repairs() -> None:
    raw = _rec("q", sql=NOT_CANCELLED, first_sql=ALL, correct=False, first_correct=True, repairs=1)
    record = regrade.regrade_record(raw, {"id": "q", "sql": NOT_CANCELLED}, regrade.DEFAULT_DB)
    assert record.correct and record.first_correct is False  # theo đáp án mới: lần sửa đã giúp


def test_regrade_record_refusal_during_repair_and_new_tags() -> None:
    raw = _rec("q", first_sql=ALL, refused=True, executable=True, correct=False, repairs=1, reason="refused")
    record = regrade.regrade_record(raw, {"id": "q", "sql": ALL, "difficulty": "hard", "tags": ["join"]},
                                    regrade.DEFAULT_DB)
    assert record.reason == "refused" and not record.executable and record.first_correct is True
    assert record.difficulty == "hard" and record.tags == ["join"]


def test_merged_summary_has_no_stale_counts(tmp_path: Path) -> None:
    results, questions = _setup(tmp_path)
    path = results / "test_C0_haiku_20261031-013612_summary.json"
    stale = {**json.loads(path.read_text(encoding="utf-8")), "reasons": {"stale": 99}, "errors": 99,
             "repair": {"triggered": 99}}
    path.write_text(json.dumps(stale), encoding="utf-8")
    regrade.main(["--split", "test"], results_dir=results, out_dir=results / "corrected",
                 baseline=lambda _s: BASELINE, questions_path=questions)
    summary = json.loads((results / "corrected" / path.name).read_text(encoding="utf-8"))
    assert "stale" not in summary["reasons"] and summary["errors"] == 3 and summary["repair"]["triggered"] == 0


def test_corrected_report_reads_corrected_dir(tmp_path: Path) -> None:
    results, _, _ = _run(tmp_path)
    assert analyze.main(["--split", "test", "--corrected"], results_dir=results) == 0
    report = (results / "report_test_corrected.md").read_text(encoding="utf-8")
    assert "đáp án đã sửa" in report and "q2, q9" in report and "25.0" in report
    assert not (results / "report_test.md").exists()
