# Error analysis — Haiku C3 on the test set

Pre-registered secondary analysis (`docs/analysis_plan.md`): read the questions that the best Haiku configuration (C3)
got wrong by majority vote over 3 runs, and classify each failure. Source data: `results/raw/test_C3_haiku_*.jsonl`
(model SQL) joined with `data/questions/test.jsonl` (question + gold SQL). Analysis only — no prompt or configuration
was changed afterwards.

## 1. Failures under the original gold SQL: 35 of 150 questions

| Class | Questions | Meaning |
|---|---|---|
| **A. Gold error** | 21 | The model followed the written dataset conventions (`docs/dataset.md`), the gold SQL did not |
| **B. Ambiguous question** | 5 | Two reasonable readings; the gold picked one, the model the other |
| **C. Model error** | 9 | The model's SQL is wrong under any reasonable reading |

### A. Gold errors (21)
| Convention violated | Questions |
|---|---|
| Rule 7 — sales/order questions must exclude `cancelled` orders | 052, 077, 087, 091, 093, 095, 099, 103, 104, 108, 114, 129, 133 |
| Month / year must be returned as integers, not `'03'` / `'2025-03'` strings | 069, 097, 122, 142 |
| Ratios must be percentages | 080 |
| Return only the requested columns | 106 |
| No `date('now')` (answers change with the run date) | 074, 150 |

**Why the dev set did not catch this:** rule 7 was broadened on 2026-10-30 and the dev answers were re-checked against
it; the test answers had been written earlier and were not re-audited before the run.

### B. Ambiguous questions (5)
| Question | Ambiguity |
|---|---|
| 040 | Asks for the product "updated" latest, but the schema only has `created_at` → the model refused (reasonable) |
| 063 | Day of week as a number or as a label ("Thứ 2")? |
| 120 | "Customers who never gave a review below 3 stars" — include customers with no reviews at all? |
| 137 | Running total per day: full date or day-of-month? |
| 144 | "Successful" orders: `delivered`/`shipped` only, or simply not cancelled? |

### C. Model errors (9)
| Question | Error |
|---|---|
| 022 | Added a filter nobody asked for (`is_active = 1`) |
| 071 | Ignored the definition given in the question (margin = price − cost) and computed a ratio instead |
| 112 | Refused a valid question (year-over-year revenue per product) |
| 113 | Category hierarchy: joined products directly to root categories (products sit on leaf categories) → 0 rows |
| 117 | `COUNT(DISTINCT …)` together with `GROUP BY` → one row per customer instead of one count |
| 124 | Scope: answered "top category per customer" instead of "top category for the whole group" |
| 141 | Swapped numerator and denominator ("share of cancelled orders that used COD") |
| 143 | `NTILE` direction reversed — took the top-spending decile instead of the lowest |
| 147 | Returned an extra column (category name) |

## 2. Gold correction and re-grading
Fixing only the 35 questions above would bias the result towards C3 (only C3's failures could flip to correct). The
correction was therefore done **blind to model output**:

1. A mechanical scan of **all 150** gold queries against the written conventions flagged 44 candidates.
2. The project author reviewed and fixed the gold SQL (deviation #1). Additional changes not covered by a pre-existing
   rule (excluding `NULL` brand/city groups in 13 questions) are reported separately as deviation #2.
3. Four questions whose *wording* changed during the fix were dropped from every configuration (deviation #3): the
   model had answered the old wording. → 146 questions.
4. `scripts/regrade.py` re-graded the stored model SQL (no new API calls) through the same executor and evaluator.

The fix moved some records from correct to wrong as well (Haiku C0: 1, C1: 4). Those were records where the model
had made the same mistake as the old gold.

After re-grading, Haiku C3 fails on **exactly 14 questions = class B (5) + class C (9)**, matching the manual
classification. Its real error rate on unambiguous questions is about 9/146 ≈ 6%.

## 3. Observations across configurations (corrected gold, `results/report_test_corrected.md`)
- **Value mismatch is the clearest mechanism.** On questions where the Vietnamese wording differs from the stored
  value (e.g. "khách sỉ" → `'wholesale'`), Haiku C0 scores 14% and every configuration with sample values scores 100%
  (7 questions — illustrative, too few for a test).
- **Few-shot examples help hard query shapes.** The ratio tag goes from 42% (C2) to 75% (C3). Examples also leak
  database values, which partly overlaps with C1.
- **Few-shot examples increase refusals.** C3/C4 refused 6 test records (C0–C2: 0) and 6 of 12 ambiguous questions.
- **Self-repair (C4) rarely fires.** The trigger is "executor error or 0 rows". It fired on 6 records, fixed 2 and broke
  none. Most wrong answers are well-formed SQL that returns a plausible non-empty result.
- **Window functions remain weak** for Haiku (13–47% depending on configuration; Sonnet 60%; only 5 questions).
- **Dev overstates performance.** Haiku C3 scores 92% on dev and 76% on the original test gold. The prompt rules were
  refined on dev failures, which is exactly why the test set was held out.
