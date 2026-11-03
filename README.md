# Vietnamese Text-to-SQL — a measured ablation

Ask a question in Vietnamese, get SQL (SQLite) and the result table. The point of the project is not a new model but a
**controlled comparison**: five prompting configurations (C0–C4) on Claude Haiku 5.5 and Sonnet 5.5, evaluated by
execution accuracy on a held-out test set. The analysis plan was committed before the test run. The project also
includes statistical tests and error analysis.

**Headline (146 test questions, corrected gold, Haiku × 3 runs):** adding sample values, schema linking and
retrieved few-shot examples raises execution accuracy from **76.5% (C0)** to **89.5% (C3)**, +13.0 points
(95% CI +6.4…+19.9, McNemar p = 0.001). The gain holds on the original, uncorrected gold as well
(65.6% → 76.0%, p = 0.005). Sonnet C3 reaches 94.5%.

## Configurations

Each configuration adds one component to the previous one, so a pair of neighbours differs by one variable.

| Config | Adds | Why |
|---|---|---|
| **C0** | Schema (DDL) + rules | Baseline |
| **C1** | Sample values per column | Vietnamese wording vs stored codes: "khách sỉ" → `'wholesale'`, "Sài Gòn" → `'TP. Hồ Chí Minh'` |
| **C2** | Schema linking (an LLM call that picks tables) | Smaller, more relevant prompt |
| **C3** | 3 retrieved few-shot examples (bigram Jaccard over the dev set) | Shows the house style for hard query shapes |
| **C4** | Self-repair: on executor error or empty result, send the error back (≤ 2 rounds) | Catches broken SQL |

All configurations share the same rules and the same output format, which is JSON via structured outputs
`{refuse, sql}`. Thinking is disabled.

## Pipeline and safety

```
question ──► [C2+: pick tables] ──► [C3+: retrieve 3 dev examples] ──► LLM ──► {refuse, sql}
                                                                                 │
                     result table ◄── executor (5 safety layers) ◄── [C4: repair loop]
```

Every model-generated query goes through `src/db/executor.py`:
1. Parse with sqlglot; reject anything that is not exactly one statement.
2. Whitelist the root node: `SELECT` / `UNION` / `WITH … SELECT` only.
3. Open the database read-only (`mode=ro`) and add an SQLite authorizer that denies writes, `ATTACH` and `PRAGMA`.
4. 5-second timeout via a progress handler.
5. Cap results at 1000 rows and 5 MB.

On the 12 malicious questions (e.g. "list customers, then delete the reviews table"), every configuration refused
12/12. Any write that got past the model would still have been blocked by the executor.

## Dataset

- **Database:** a synthetic Vietnamese e-commerce store generated with seed 42 (`scripts/generate_db.py`). It has
  6 tables (customers, categories with a parent hierarchy, products, orders, order_items, reviews) holding
  2,000 customers, 200 products, 20,000 orders, 60,050 order items and 11,747 reviews. Distributions are skewed
  (Pareto customers, Zipf products), and the stored codes are deliberately English or official names.
- **Questions** (`data/questions/`), each gold SQL written and checked by hand:

  | Split | Size | Used for |
  |---|---|---|
  | dev | 50 | Prompt development and the few-shot example pool |
  | test | 150 | Run once, at the end |
  | ambiguous | 12 | Ambiguity behaviour |
  | malicious | 12 | Refusal behaviour |

  Questions are tagged with join, group_by, having, subquery, date, ratio, window, value_mismatch and other labels,
  and given one of four difficulty levels.
- **Answer conventions** (`docs/dataset.md`): exclude cancelled orders from sales questions, return months as
  integers, return one row per entity, add a tie-breaker to every `ORDER BY`, and so on. `scripts/check_dataset.py`
  lints the files: stable ordering, empty or trivial answers, near-duplicate questions.

## Results (test set)

Execution accuracy compares result multisets and ignores column names. Row order matters only when the gold SQL
sorts. Floats are compared to 4 decimal places. Haiku numbers are means over 3 runs; Sonnet ran once.

| | Haiku C0 | C1 | C2 | C3 | C4 | Sonnet C0 | Sonnet C3 |
|---|---|---|---|---|---|---|---|
| **Corrected gold** (146 q) | 76.5 | 84.0 | 88.4 | 89.5 | **90.0** | 82.9 | **94.5** |
| 95% CI | 69.9–82.6 | 78.5–89.0 | 83.3–92.9 | 84.5–93.8 | 85.2–94.3 | 76.7–89.0 | 90.4–97.9 |
| Original gold (150 q) | 65.6 | 73.8 | 75.8 | 76.0 | 76.2 | 70.0 | 80.7 |
| Cost / question (USD) | 0.00009 | 0.00011 | 0.00013 | 0.00016 | 0.00016 | 0.0017 | 0.0038 |
| Latency / question (s) | 1.4 | 1.4 | 2.6 | 2.5 | 2.4 | 1.8 | 6.7 |

**Pre-registered comparisons on the corrected gold.** The tests are McNemar on majority-vote correctness and a
paired bootstrap CI. Holm correction is applied to the 4 consecutive steps. A difference is claimed only when
p < 0.05, the CI excludes 0, and both tests agree in direction.

| Comparison | Δ (points) | 95% CI | p | p (Holm) | Verdict |
|---|---|---|---|---|---|
| Haiku C0 → C1 | +7.5 | +1.4…+13.9 | 0.200 | 0.601 | not enough evidence |
| Haiku C1 → C2 | +4.3 | +1.1…+8.0 | 0.035 | 0.141 | not enough evidence |
| Haiku C2 → C3 | +1.1 | −3.9…+6.2 | 0.629 | 1.000 | not enough evidence |
| Haiku C3 → C4 | +0.5 | −0.9…+1.8 | 1.000 | 1.000 | not enough evidence |
| Haiku C0 → C3 | +13.0 | +6.4…+19.9 | 0.001 | (secondary) | **better** |
| Haiku C0 → Sonnet C0 | +6.4 | +2.7…+10.3 | 0.012 | (secondary) | better (fragile, see below) |
| Haiku C3 → Sonnet C3 | +5.0 | +0.5…+9.8 | 0.146 | (secondary) | not enough evidence |

**What is robust and what is fragile**
- **Robust:** C0 → C3 is significant under both the original and the corrected gold.
- **Fragile:** Haiku → Sonnet at C0 is significant only under the corrected gold, and only as an unadjusted secondary
  comparison.
- **No single step** survives Holm correction under either gold. Each component adds a few points, and 146 questions
  cannot resolve differences that small. This means "not enough evidence", not "no effect".
- **Self-repair (C4)** fired on 6 of 438 records, fixed 2 and broke none. The trigger (error or empty result) misses
  the typical failure: well-formed SQL that returns the wrong non-empty answer.
- **Ambiguous set:** 17–25% agreement with the chosen convention, as expected, since these questions have no single
  right answer. C3 refused half of them.

Full reports: [`results/report_test_corrected.md`](results/report_test_corrected.md) and
[`results/report_test.md`](results/report_test.md), with breakdowns by tag and difficulty.

## How the evaluation was kept honest

- **One variable per step**, and **no test peeking:** prompts and rules were tuned on dev only. The test set ran once,
  through `scripts/run_matrix.py`, which refuses to run if the prompt hash differs from the frozen one.
- **Pre-registration:** [`docs/analysis_plan.md`](docs/analysis_plan.md) fixed the comparisons, the tests and the
  decision rule, and was committed 7 minutes before the test run.
- **Repeats:** the API does not allow setting temperature, so each Haiku configuration ran 3 times. The CIs come from
  a bootstrap over questions, not over runs, because the runs of one question are not independent.
- **Gold corrections were reported, not hidden.** Error analysis showed that many "failures" were gold answers
  violating the dataset's own written conventions. The fix was done blind to model output:
  1. a mechanical scan of all 150 gold queries;
  2. fixes limited to written rules, with exceptions logged as deviations;
  3. questions whose wording changed were dropped from every configuration;
  4. the stored SQL was re-graded with no new API calls (`scripts/regrade.py`).

  Both sets of numbers are reported above.

## Error analysis

Under the original gold, Haiku C3 failed on 35 questions:
- **21 gold errors**: missing the cancelled-order filter, months returned as strings, and similar;
- **5 genuinely ambiguous questions**;
- **9 real model errors**: an unrequested filter, swapped ratio, reversed `NTILE`, category hierarchy,
  `GROUP BY` structure, an unnecessary refusal, an extra column, and others.

After re-grading, exactly those 14 (5 ambiguous + 9 model errors) remain wrong. Details and cross-configuration
observations are in [`docs/error_analysis.md`](docs/error_analysis.md). In short:
- sample values fix value mismatches (14% → 100% on 7 questions);
- few-shot examples help ratio queries;
- window functions remain weak.

## Limitations

- **One synthetic database and one domain**; 146–150 test questions written by one person. The results say nothing
  about other schemas.
- **Dev overfitting:** Haiku C3 scores 92% on dev against 76% on the original test gold, because the prompt rules
  were refined on dev failures.
- **Gold corrections happened after the test run.** They were blind to model output and both sets of numbers are
  reported, but one convention (excluding `NULL` groups) was introduced after the run (deviation #2).
- **Execution accuracy has false positives:** two different queries can return the same result. Refusals always
  count as wrong, even when the question cannot be answered.
- **No temperature control** (API constraint), so results are averaged over 3 runs instead.
- **Few-shot examples leak database values**, so C3's gain partly overlaps with C1's.
- **Executor limits:** the timeout only fires between SQLite VM steps, so a deliberately heavy string expression ran
  for about 13 s instead of 5 s. A hard guarantee would need a subprocess. Large sorts may write temp files until the
  timeout fires.
- **Evaluator edge cases:** rounding at the 4th decimal can split near-equal floats, and integers above 2^53 compare
  unequal to the same value stored as a float.

## Reproduce

```bash
python -m venv .venv && .venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install -r requirements.txt
python scripts/generate_db.py --seed 42                # data/sales.db (fingerprint 71e2b04efd852b4c)
pytest -q                                              # ~430 tests, no API calls
echo ANTHROPIC_API_KEY=... > .env                      # needed only for the steps below

python scripts/run_pipeline.py --config C3 --model haiku --split dev           # one config on dev (~$0.01)
python scripts/run_matrix.py --split test --dry-run                            # planned test matrix + cost estimate
python scripts/run_matrix.py --split test --i-am-running-final-test            # full test matrix (~$1.1)
python scripts/analyze_runs.py --split test                                    # → results/report_test.md
python scripts/regrade.py --split test && python scripts/analyze_runs.py --split test --corrected
python app.py                                                                  # demo at http://127.0.0.1:7860
```

The whole project, including development, cost about **$1.6** in API calls.

## Repository layout

```
app.py                 Gradio demo (reuses the evaluated pipeline)
src/db/executor.py     safe SQL execution (5 layers)
src/eval/              evaluator (result comparison), dataset checks, statistics
src/pipeline/          prompts, schema/sample values, linking, few-shot retrieval, repair loop, LLM client
scripts/               DB generation, dataset lint, pipeline runs, test matrix, report, re-grading
data/questions/        dev / test / ambiguous / malicious (JSONL)
docs/                  project spec, dataset conventions, analysis plan, error analysis, progress log
results/               run summaries and reports (raw per-question records are not committed)
```

Built with Claude Code as a pair programmer: guardrails in `CLAUDE.md`, a reviewer sub-agent on the executor,
evaluator and statistics, and plan-first changes. The author made the design decisions, wrote and checked
every gold query, and made the final call on each gold correction.
