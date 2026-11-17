# Verification rules

Code: [`pipeline/02_verify.py`](../pipeline/02_verify.py). Results:
[verification results](../docs/verification_results.md).

Each database is checked after loading. The script exits with an error if a check
fails, so a bad load cannot reach the later stages unnoticed.

| Check | Rule | Fails the run? |
|---|---|---|
| Row counts (DQ-023) | Each file's data lines are recounted straight from the ZIP, independently of the loader, and must equal the rows loaded for that quarter and file. | Yes |
| Keys (DQ-003) | Every DEMO row has a `primaryid`, a `caseid` and a whole-number `caseversion`. | Yes |
| Duplicate reports | A `primaryid` may appear only once in one quarter's DEMO file. | Yes |
| Child rows without a report | DRUG, REAC, OUTC, INDI, THER and RPSR rows whose report is not in the same quarter's DEMO file are counted. | No: FDA's files contain a handful (DQ-035) |
| Encoding fallback | Lines read as Windows-1252 are counted (expected: 5, all in 2019Q3). | No |
| Raw vs kept (DQ-025) | The [case rule](case_selection.md) is applied and the raw and kept row counts of every file are printed and saved to `results/verify_<database>.csv`. | No: a record for the report |
