# Rules

Every rule that decides which data are kept or how a value is derived. Each rule has
the ID used in the project's data-quality log (`DQ-` for a data issue, `DQD-` for the
decision that settled it). The reviewed tables that the code reads are in
[`tables/`](tables/).

| Stage | Rule document | IDs | Rule table |
|---|---|---|---|
| Ingestion | [Ingestion rules](ingestion.md) | DQ-023, DQ-032, DQ-033, DQ-034, DQ-039 | |
| Verification | [Verification rules](verification.md) | DQ-003, DQ-023, DQ-025, DQ-035 | |
| Munging | [Case selection: rules D1-D6, X1 and the DQ-038 exclusion](case_selection.md) | DQ-005, DQ-006, X1, DQ-038 | |
| Munging | [Age, sex and weight](demographics.md) | DQ-012 | [age_sex_rules_v0.1.json](tables/age_sex_rules_v0.1.json) |
| Munging | [ADHD drug map](adhd_drug_map.md) | DQ-015 | [adhd_ingredient_map_v0.1.csv](tables/adhd_ingredient_map_v0.1.csv), [adhd_name_alias_v0.1.csv](tables/adhd_name_alias_v0.1.csv) |
| Munging | [ADHD indication](adhd_indication.md) | DQ-016 | [adhd_indication_terms_v0.1.csv](tables/adhd_indication_terms_v0.1.csv) |
| Munging | [Study groups](study_groups.md) | DQ-019 | |
| Munging | [Event groups](event_groups.md) | DQ-017 | [reaction_term_groups_v0.1.csv](tables/reaction_term_groups_v0.1.csv) |
| RQ datasets | [Research-question datasets](rq_datasets.md) | DQ-018, DQ-020, DQ-021, DQ-037 | |

## Known limitations kept in the data

These were reviewed and deliberately left in; the report states them as limitations.

- **2015 atomoxetine batch (DQ-036, DQD-066).** On 2015-08-03 one manufacturer sent
  FDA 8,001 periodic reports at once, 3,663 of them with atomoxetine as a suspect drug;
  the manufacturer had received most of them in 2007-2013. They are real, distinct
  reports, so they stay in, but they make up a large share of the nonstimulant group.
- **Missing versions (DQ-008).** A case version received and replaced within one
  quarter never appears in FDA's files and cannot be recovered.
- **Reports, not people (DQ-026).** FAERS counts voluntary reports. There is no count
  of patients taking each drug, so the results describe reporting patterns, not risk.
