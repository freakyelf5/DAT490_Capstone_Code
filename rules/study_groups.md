# Study group rules (DQ-019)

Code: the `exposure` step of `build` in [`pipeline/03_munge.py`](../pipeline/03_munge.py).
Used for every result (DQD-058, DQD-083).

1. **Exposure.** A case is exposed when a counted ADHD drug row (see
   [ADHD indication](adhd_indication.md)) is a primary (`PS`) or secondary (`SS`)
   suspect. FAERS reporters name suspect drugs as the ones they link to the event.
2. **Not exposure.** An ADHD drug listed as concomitant (`C`) or interacting (`I`) is
   background only; it sets `concomitant_adhd` but does not put the case in a group.
3. **Classes.** The case's classes are those of its exposure rows. Alpha-2 agonists
   count as nonstimulants and also set `alpha2`.
4. **Group (`rq1_group`).** `STIMULANT` or `NONSTIMULANT` when the case has exactly one
   class; `MULTI_ADHD_CLASS` when it has both. Multi-class cases are kept and reported
   but never counted in either exclusive group, so no case is counted twice.
5. **Confirmed group (`rq1_group_confirmed`).** The same rule using only drug rows
   whose own indication is ADHD, for sensitivity checks.

The study group is every case with a `rq1_group`: 94,803 cases over 2012Q4-2026Q2
(81,998 stimulant, 11,805 nonstimulant, 1,000 both).
