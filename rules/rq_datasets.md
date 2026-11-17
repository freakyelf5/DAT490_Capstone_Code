# Research-question dataset rules

Code: [`pipeline/04_rq_datasets.py`](../pipeline/04_rq_datasets.py) (and the
`cases` table from [`03_munge.py`](../pipeline/03_munge.py)). Column meanings: the
[data dictionary](../dictionary/data_dictionary.md).

Every dataset starts from kept cases ([case selection](case_selection.md)) in the
[study group](study_groups.md), with the DQ-038 cluster already removed. These are
the inputs to the analyses; no model is fitted in this repository.

## RQ1: stimulant vs nonstimulant event patterns by age and sex

- `rq1_cases`: one row per study-group case, 2012Q4-2026Q2, with age band, sex, the
  `covid_window` flag and the seven RQ1 event groups (narrow and broad).
- `rq1_counts`: the same cases counted by group x age band x sex x COVID window, plus
  every other kept FAERS case as `OTHER_FAERS`, so each class can also be compared
  with the rest of FAERS. The disproportionality analysis needs only these counts.
- `rq1_terms`: how many stimulant and nonstimulant cases list each reaction term (the
  most frequently reported terms).

**COVID-19 window (DQ-037, DQD-067).** Cases FDA first received from 2020-03-01 to
2021-12-31 are flagged, not removed, so a sensitivity check can leave them out.

## RQ2: reporting around the October 2022 shortage and the May 2023 labeling change

- `rq2_cases`: one row per study-group case with a valid receipt date, with its
  receipt month, its period and the RQ2 event groups (ineffectiveness, withdrawal,
  misuse, abuse, addiction) plus the `product_quality_supply` control series.
  `rq2_any_narrow` (any of the five groups) is the primary outcome.
- `rq2_monthly`: cases and event counts per group and month, January 2018 to
  February 2026, by `rq1_group` and by `rq1_group_confirmed`.

| Period | Months |
|---|---|
| before shortage | January 2018 - September 2022 |
| shortage to label change | November 2022 - April 2023 |
| after label change | June 2023 - February 2026 |

The two announcement months (October 2022, May 2023) belong to no period. The window
ends in February 2026, the last month before FDA moved to its new reporting system
(AEMS).

## RQ3: predicting a serious outcome

`rq3_cases` holds study-group cases of the 2022-2026 database only.

- **Target (DQ-018).** `serious_target` is true when the case has OUTC code `DE`
  (death), `LT` (life-threatening) or `HO` (hospitalization). A case with no OUTC
  row is not serious; `outc_state` keeps that difference visible.
- **Predictors.** Age, age band, sex, weight, drug class (`rq1_group`, `alpha2`),
  whether a numeric dose and an mg unit are reported, route of the ADHD drug, and the
  numbers of concomitant, other suspect and interacting drugs. Missing values stay
  missing (DQ-020); the modeling step decides how to treat them.
- **Time split (DQ-021).** `TRAIN`: cases FDA first received before 2025, using the
  case version that existed at the end of 2024Q4, so later follow-ups (for example a
  death added in 2025) never leak into training. `TEST`: cases received January
  2025 to February 2026, newest version. A case is never in both.

Verified counts on the real data: 22,948 training and 9,356 test cases.
