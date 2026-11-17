# Age, sex and weight rules (DQ-012)

Code: `demographics_sql` in [`pipeline/03_munge.py`](../pipeline/03_munge.py).
Rule table: [`tables/age_sex_rules_v0.1.json`](tables/age_sex_rules_v0.1.json).
Accepted 2026-10-29 (DQD-056).

Raw values are never changed. The cleaned values are new columns in `cases`.

| Field | Rule |
|---|---|
| Age (`age_years`) | The reported amount must be a plain number. It is converted to years with its unit: `YR` x1, `DEC` x10, `MON` /12, `WK` x7/365.25, `DY` /365.25, `HR` /8,766. Ages outside 0-120 years, unknown units and non-numbers stay missing. Zero is valid (newborns). |
| Age band (`age_band`) | `0_5`, `6_11`, `12_17`, `18_25`, `26_44`, `45_64`, `65_PLUS` from a valid age, else `UNKNOWN`. The reported age group code (`age_grp`) is never used to fill a missing age. |
| Sex (`sex`) | `F` and `M` as reported; `UNK` and `NS` become `UNKNOWN`; empty becomes `NOT_REPORTED`. Files before 2014Q3 call the field `gndr_cod`, which is read when `sex` is absent. No sex is inferred. |
| Weight (`wt_kg`) | Converted to kg: `KG` x1, `LBS` x0.45359237, `GMS` /1,000. Weights of zero or less, above 650 kg, or with unknown units stay missing. |

Nothing is imputed or capped; a missing value stays missing and is shown as missing
in every dataset.
