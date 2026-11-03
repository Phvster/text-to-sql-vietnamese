"""Báo cáo thống kê cho một split theo đúng kế hoạch ở docs/analysis_plan.md.

Chạy: python scripts/analyze_runs.py --split dev
Ghi:  results/report_<split>.md (đồng thời in ra màn hình)

Với mỗi (model, cấu hình) lấy lượt chạy ĐẦY ĐỦ mới nhất (không --limit, không bị dừng vì ngân sách).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.dataset import DIFFICULTIES  # noqa: E402
from src.eval.stats import (bootstrap_ci, discordant, holm, majority, mcnemar_exact,  # noqa: E402
                            paired_bootstrap_diff, per_question)

RESULTS = ROOT / "results"
CONFIG_ORDER = ("C0", "C1", "C2", "C3", "C4")
# So sánh định trước (docs/analysis_plan.md). FAMILY: hiệu chỉnh Holm cùng nhau. EXTRA: báo riêng.
FAMILY = [(("haiku", "C0"), ("haiku", "C1")), (("haiku", "C1"), ("haiku", "C2")),
          (("haiku", "C2"), ("haiku", "C3")), (("haiku", "C3"), ("haiku", "C4"))]
EXTRA = [(("haiku", "C0"), ("haiku", "C3")), (("haiku", "C0"), ("sonnet", "C0")),
         (("haiku", "C3"), ("sonnet", "C3"))]
ALPHA = 0.05

Key = tuple[str, str]  # (model, config)


def select_runs(summaries: list[dict], prompt_hash: str | None = None,
                repeats: dict[Key, int] | None = None) -> dict[Key, dict]:
    """Lượt đầy đủ mới nhất cho mỗi (model, config). run_id kết thúc bằng thời gian → so chuỗi là so thời gian.

    test: chỉ nhận lượt đúng kế hoạch (prompt đã đóng băng + đúng số lần lặp) — một lượt chạy lẻ sau đó
    (vd thử lại 1 lần lặp) không được âm thầm thay thế lượt chính.
    """
    chosen: dict[Key, dict] = {}
    for s in summaries:
        if s.get("limit") is not None or s.get("stopped") or not s.get("n"):
            continue
        key = (s["model"], s["config"])
        if prompt_hash is not None and s.get("prompt_hash") != prompt_hash:
            continue
        if repeats is not None and s.get("repeats") != repeats.get(key):
            continue
        if key not in chosen or s["run_id"] > chosen[key]["run_id"]:
            chosen[key] = s
    return chosen


def load_summaries(split: str, results_dir: Path) -> list[dict]:
    summaries = [json.loads(p.read_text(encoding="utf-8")) for p in results_dir.glob("*_summary.json")]
    return [s for s in summaries if s.get("split") == split]


def load_records(run_id: str, results_dir: Path) -> list[dict] | None:
    """None nếu thiếu file raw (results/raw không commit → clone mới sẽ không có)."""
    path = results_dir / "raw" / f"{run_id}.jsonl"
    if not path.exists():
        return None
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _pct(x: float) -> str:
    return f"{x * 100:.1f}"


def _sort_key(key: Key) -> tuple:
    return (key[0], CONFIG_ORDER.index(key[1]) if key[1] in CONFIG_ORDER else 99)


def accuracy_table(runs: dict[Key, dict], records: dict[Key, list[dict]], malicious: bool) -> list[str]:
    metric = "Từ chối đúng %" if malicious else "Accuracy %"
    lines = [f"| Model | Cấu hình | Câu | Lặp | {metric} | CI 95% | Chạy được % | Lỗi API | $/câu | Trễ s |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(runs, key=_sort_key):
        s, recs = runs[key], records[key]
        mean, lo, hi = bootstrap_ci(list(per_question(recs).values()))
        lines.append(f"| {key[0]} | {key[1]} | {s['n_questions']} | {s.get('repeats', 1)} | {_pct(mean)} | "
                     f"{_pct(lo)}–{_pct(hi)} | {_pct(s['executable_rate'])} | {s.get('errors', 0)} | "
                     f"{s['total_cost_usd'] / s['n']:.5f} | {s['mean_latency_s']:.2f} |")
    return lines


def compare(a: list[dict], b: list[dict]) -> dict | None:
    """None nếu hai lượt khác tập câu hỏi (không ghép cặp được)."""
    try:
        diff, lo, hi = paired_bootstrap_diff(per_question(a), per_question(b))
        worse_to_better, better_to_worse = discordant(majority(a), majority(b))
    except ValueError:
        return None
    return {"diff": diff, "lo": lo, "hi": hi, "b": worse_to_better, "c": better_to_worse,
            "p": mcnemar_exact(worse_to_better, better_to_worse)}


def _verdict(r: dict, p_used: float) -> str:
    """Kết luận chỉ khi p < 0.05, CI không chứa 0, VÀ hai phép thử cùng chiều (b > c ⇔ chênh lệch > 0)."""
    ci_excludes_zero = r["lo"] > 0 or r["hi"] < 0
    same_direction = (r["b"] > r["c"]) == (r["diff"] > 0)
    if p_used < ALPHA and ci_excludes_zero and same_direction:
        return "B tốt hơn" if r["diff"] > 0 else "B kém hơn"
    return "chưa đủ bằng chứng"


def comparison_table(records: dict[Key, list[dict]]) -> list[str]:
    """Họ FAMILY luôn hiệu chỉnh Holm với m = 4 như đã đăng ký: cặp thiếu lượt chạy / không ghép được
    tính p = 1 (bảo thủ) chứ không thu nhỏ họ — thu nhỏ họ làm p_Holm nhỏ đi."""
    lines = ["| So sánh | Chênh lệch (điểm %) | CI 95% | b (A sai, B đúng) | c (A đúng, B sai) | p | p Holm | Kết luận |",
             "|---|---|---|---|---|---|---|---|"]
    family = [(a, b, compare(records[a], records[b]) if a in records and b in records else None) for a, b in FAMILY]
    adjusted = holm([1.0 if r is None else r["p"] for _, _, r in family])
    rows = [(a, b, r, p_adj) for (a, b, r), p_adj in zip(family, adjusted)]
    rows += [(a, b, compare(records[a], records[b]), None) for a, b in EXTRA if a in records and b in records]
    for a, b, r, p_adj in rows:
        label = f"{a[0]} {a[1]} → {b[0]} {b[1]}"
        if r is None:
            missing = "thiếu lượt chạy" if a not in records or b not in records else "khác tập câu hỏi"
            lines.append(f"| {label} | - | - | - | - | - | {'-' if p_adj is None else f'{p_adj:.3f}'} | ⚠️ {missing} |")
            continue
        verdict = _verdict(r, r["p"] if p_adj is None else p_adj)
        holm_text = f"{p_adj:.3f}" if p_adj is not None else "không hiệu chỉnh"
        lines.append(f"| {label} | {r['diff'] * 100:+.1f} | {r['lo'] * 100:+.1f}…{r['hi'] * 100:+.1f} | "
                     f"{r['b']} | {r['c']} | {r['p']:.3f} | {holm_text} | {verdict} |")
    return lines


def group_table(records: dict[Key, list[dict]], field: str) -> list[str]:
    """Accuracy theo độ khó / tag: trung bình tỉ lệ đúng của các câu trong nhóm. Cột = (model, config)."""
    keys = sorted(records, key=_sort_key)
    groups: dict[str, dict[Key, list[float]]] = defaultdict(lambda: defaultdict(list))
    sizes: dict[str, set[str]] = defaultdict(set)
    for key in keys:
        first = {}
        for r in records[key]:
            first.setdefault(r["id"], r)
        rates = per_question(records[key])
        for qid, rate in rates.items():
            values = first[qid].get(field)
            for g in ([values or "-"] if field == "difficulty" else (values or [])):
                groups[g][key].append(rate)
                sizes[g].add(qid)
    header = "| Nhóm | Câu | " + " | ".join(f"{m} {c}" for m, c in keys) + " |"
    lines = [header, "|---|---|" + "---|" * len(keys)]
    for g in sorted(groups, key=lambda g: (DIFFICULTIES.index(g) if g in DIFFICULTIES else 9, g)):
        cells = [_pct(sum(v) / len(v)) if (v := groups[g].get(k)) else "-" for k in keys]
        lines.append(f"| {g} | {len(sizes[g])} | " + " | ".join(cells) + " |")
    return lines


def reasons_table(runs: dict[Key, dict]) -> list[str]:
    all_reasons = sorted({r for s in runs.values() for r in s.get("reasons", {})})
    keys = sorted(runs, key=_sort_key)
    lines = ["| Lý do | " + " | ".join(f"{m} {c}" for m, c in keys) + " |", "|---|" + "---|" * len(keys)]
    for reason in all_reasons:
        lines.append(f"| {reason} | " + " | ".join(str(runs[k].get("reasons", {}).get(reason, 0)) for k in keys) + " |")
    return lines


def build_report(split: str, results_dir: Path = RESULTS, prompt_hash: str | None = None,
                 repeats: dict[Key, int] | None = None) -> str:
    runs = select_runs(load_summaries(split, results_dir), prompt_hash, repeats)
    warnings = []
    records: dict[Key, list[dict]] = {}
    for key, s in list(runs.items()):
        loaded = load_records(s["run_id"], results_dir)
        if loaded is None:
            warnings.append(f"⚠️ Thiếu file raw của {s['run_id']} — bỏ khỏi báo cáo.")
            del runs[key]
        else:
            records[key] = loaded
    if not runs:
        return f"Chưa có lượt chạy đầy đủ nào cho split {split}.\n" + "\n".join(warnings)
    malicious = split == "malicious"
    regraded = next((s["regraded"] for s in runs.values() if s.get("regraded")), None)
    gold_versions = {(s.get("regraded") or {}).get("gold_sha") for s in runs.values()}
    if regraded is not None and len(gold_versions) > 1:
        warnings.append(f"⚠️ Các lượt được chấm theo {len(gold_versions)} phiên bản đáp án khác nhau — "
                        "chạy lại scripts/regrade.py.")
    if regraded is not None:  # bộ số chấm lại bằng scripts/regrade.py
        excluded = regraded.get("excluded") or []
        warnings.append(f"Chấm lại theo đáp án đã sửa (sai lệch trong docs/analysis_plan.md; test.jsonl "
                        f"sha {regraded.get('gold_sha')}). Loại {len(excluded)} câu đổi đề so với "
                        f"{regraded.get('baseline_ref')}: {', '.join(excluded) or '-'}.")
    out = [f"# Báo cáo split `{split}`" + (" — đáp án đã sửa" if regraded else ""), "", *warnings, "",
           "## Lượt chạy được dùng", "",
           "| Model | Cấu hình | run_id | prompt_hash | pool_hash |", "|---|---|---|---|---|"]
    out += [f"| {k[0]} | {k[1]} | {s['run_id']} | {s.get('prompt_hash')} | {s.get('pool_hash') or '-'} |"
            for k, s in sorted(runs.items(), key=lambda kv: _sort_key(kv[0]))]
    hashes = {s.get("prompt_hash") for s in runs.values()}
    if len(hashes) > 1:
        out += ["", f"⚠️ Các lượt chạy dùng {len(hashes)} prompt khác nhau — so sánh giữa chúng không công bằng."]
    out += ["", "## Accuracy", ""] + accuracy_table(runs, records, malicious)
    if not malicious:
        out += ["", "## So sánh định trước", "",
                "McNemar trên đúng theo đa số lần lặp; Holm cho 4 so sánh liên tiếp của Haiku (m = 4 cố định); "
                "3 so sánh phụ dùng p không hiệu chỉnh. Kết luận chỉ khi p < 0.05, CI không chứa 0 và hai phép thử "
                "cùng chiều.", ""] + comparison_table(records)
        out += ["", "## Theo độ khó", ""] + group_table(records, "difficulty")
        out += ["", "## Theo tag", ""] + group_table(records, "tags")
    out += ["", "## Lý do (số bản ghi)", ""] + reasons_table(runs)
    repairs = [(k, s.get("repair") or {}) for k, s in sorted(runs.items(), key=lambda kv: _sort_key(kv[0]))
               if (s.get("repair") or {}).get("triggered") or k[1] == "C4"]
    if repairs:
        out += ["", "## C4 — vòng sửa (đếm theo bản ghi: 3 lần lặp → mỗi câu tính 3 lần)", "",
                "| Model | Bản ghi kích hoạt | Lần gọi sửa | Sửa được | Làm hỏng |",
                "|---|---|---|---|---|"]
        out += [f"| {k[0]} | {r.get('triggered', 0)} | {r.get('calls', 0)} | {r.get('fixed', 0)} | {r.get('broken', 0)} |"
                for k, r in repairs]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None, results_dir: Path = RESULTS) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Báo cáo thống kê một split")
    parser.add_argument("--split", default="dev", choices=["dev", "test", "ambiguous", "malicious"])
    parser.add_argument("--corrected", action="store_true",
                        help="dùng kết quả chấm lại trong results/corrected/ (scripts/regrade.py)")
    args = parser.parse_args(argv)
    source = results_dir / "corrected" if args.corrected else results_dir
    if args.split == "test":  # chỉ nhận đúng các lượt theo kế hoạch đã đăng ký
        sys.path.insert(0, str(ROOT / "scripts"))
        from run_matrix import FROZEN_PROMPT_HASH, MATRIX  # noqa: PLC0415
        planned = {(m, c): r for m, c, r in MATRIX["test"]}
        report = build_report("test", source, FROZEN_PROMPT_HASH, planned)
    else:
        report = build_report(args.split, source)
    name = f"report_{args.split}_corrected.md" if args.corrected else f"report_{args.split}.md"
    (results_dir / name).write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
