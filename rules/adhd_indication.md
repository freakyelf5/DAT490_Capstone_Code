# ADHD indication rules (DQ-016)

Code: the `adhd_rows` step of `build` in [`pipeline/03_munge.py`](../pipeline/03_munge.py).
Rule table: [`tables/adhd_indication_terms_v0.1.csv`](tables/adhd_indication_terms_v0.1.csv).
Accepted 2026-10-29 (DQD-054).

An indication (INDI row) belongs to one drug: the same report with `indi_drug_seq`
equal to the drug's `drug_seq`. An indication written for another drug on the same
report never counts. Terms match exactly on the lower-cased, trimmed `indi_pt`.

| Tier | Terms | Effect |
|---|---|---|
| `adhd` | attention deficit hyperactivity disorder (and spelling variants), attention deficit disorder, hyperkinetic syndrome | Confirms ADHD use |
| `related` | disturbance in attention, psychomotor hyperactivity, impulsive behaviour, minimal brain dysfunction | ADHD-like; never confirms |
| `unknown` | product used for unknown indication, drug use for unknown indication, ill-defined disorder | Says nothing either way |

## Which ADHD drug rows count

- **Medication-matched (main):** an `INCLUDE` ADHD medicine whose own indication is
  ADHD, ADHD-like, unknown or missing. A drug given for another stated illness (for
  example narcolepsy) does not count.
- **Alpha-2 agonists** (guanfacine, clonidine, `CONDITIONAL`) count only when their own
  indication is ADHD.
- **Confirmed (sensitivity):** only ADHD medicines whose own indication is ADHD. Used
  for `rq1_group_confirmed`.
