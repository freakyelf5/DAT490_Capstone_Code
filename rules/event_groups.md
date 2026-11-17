# Event group rules (DQ-017)

Code: the `events` step of `build` in [`pipeline/03_munge.py`](../pipeline/03_munge.py).
Rule table: [`tables/reaction_term_groups_v0.1.csv`](tables/reaction_term_groups_v0.1.csv)
(417 rows). Approved 2026-10-27 (DQD-034).

Each reaction is a MedDRA Preferred Term (`pt`). A case gets a true/false flag per
group: `<group>_narrow` when it lists a term from the narrow list, `<group>_broad` when
it lists a term from the narrow or the broad list. Terms match exactly on the
lower-cased, trimmed `pt`; there is no partial matching. Narrow lists hold terms that
clearly mean the event and are used for the main results; broad lists add related
terms for sensitivity checks.

| Group | Used by | Scope |
|---|---|---|
| `cardiovascular` | RQ1, RQ3 | raised blood pressure, fast or slow heart rhythms (including QT), low blood pressure and fainting, heart attack, stroke, cardiac arrest, heart failure, Raynaud's |
| `psychiatric` | RQ1, RQ3 | psychosis, mania, suicidality and self-harm, depression, anxiety, aggression, sleep problems |
| `dependence` | RQ1, RQ2 | drug dependence; tolerance and detoxification (broad) |
| `abuse` | RQ1, RQ2 | drug abuse |
| `misuse` | RQ1, RQ2 | intentional misuse, diversion, prescription fraud |
| `addiction` | RQ1, RQ2 | drug or substance use disorder |
| `withdrawal` | RQ2 | withdrawal and rebound |
| `overdose` | RQ1, RQ2 | overdose; dosing errors (broad) |
| `ineffectiveness` | RQ2 | lack or loss of effect; condition aggravated (broad) |
| `product_quality_supply` | RQ2 control | product quality, substitution and availability problems |

The table also lists two groups that are not outcomes: `excluded` (terms considered
and deliberately left out, with the reason, for example off-label use and "no adverse
event") and `rq3_outcome_leakage` (terms that restate death or hospitalization, which
an RQ3 model must not use as predictors).

Choices worth knowing: `addiction` is separate from `abuse` and `dependence` because
the 2023 labeling change names them separately; venous thromboembolism is left out of
`cardiovascular`; "ADHD" reported as a reaction counts only as broad
`ineffectiveness`.
