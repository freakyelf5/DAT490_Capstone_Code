# Case selection rules

Code: `kept_cases_sql` in [`pipeline/common.py`](../pipeline/common.py), used by
[`02_verify.py`](../pipeline/02_verify.py) and [`03_munge.py`](../pipeline/03_munge.py).

FAERS lists every version of a case. When a case is updated, FDA publishes a new
report (`primaryid`) with a higher `caseversion` under the same `caseid`. Counting
every row would count the same patient event several times, so each case is reduced
to one report. These rules follow FDA's own instructions for FAERS users.

## Rules D1-D6

DQ-005 and DQ-006, accepted 2026-10-27 (DQD-036 to DQD-038).

| Rule | What the code does |
|---|---|
| D1 Newest version | Each `caseid` keeps only its report with the highest `caseversion` (compared as a number, so 10 is after 9). |
| D2 Same report twice | When the same version appears in more than one quarter file, the later quarter's copy wins (FDA FAQ 29), then the later line. |
| D3 Deleted cases | A case named on any of FDA's deleted-case lists is removed entirely, whichever version it is on. Only lines that are just digits count as case numbers. |
| D4 Deletions apply backwards | Every deleted-case list up to the end of the study period applies to every earlier quarter. |
| D5 Unmatched deletions | Deleted case numbers that match no case are ignored, not errors. |
| D6 Time placement | A case is placed in time by `init_fda_dt`, the date FDA first received it. `fda_dt` (the date of this version) is not used. |

Nothing is deleted from the raw tables; kept cases are chosen when tables are built.

## Rule X1: two databases, one series

Accepted 2026-10-29 (DQD-052). The historical and current databases are read as one
quarter-ordered series (`attach` in `03_munge.py` stacks their raw tables), and rules D1-D6 are applied
across both. A case reported in both databases is therefore kept once, with its
newest version (in practice always the 2022+ copy), and a deletion in either
database removes the case from both. An audit found 245,064 cases in both databases
and no version conflicts between them (DQD-080).

## DQ-038: one patient reported by many manufacturers

Decided 2026-10-30 (DQD-072). Exploring the data turned up 133 study-group cases
(686 kept cases in all) describing the same 40-year-old, 96 kg patient in Canada,
filed by about 25 manufacturers under separate case numbers. Rules D1-D6 work within one case number, so they cannot join these.
By the team lead's decision, every kept case with occurrence country `CA`, age 40 and
weight 96 kg is left out of the `cases` table (and so out of every research-question
dataset). A case with no age or weight is not part of the cluster and stays in. No
general rule for cross-manufacturer duplicates was made; only this cluster was found.
