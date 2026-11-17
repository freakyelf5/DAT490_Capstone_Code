"""Stage 4, research-question datasets: one analysis-ready table per research question.

Built from the clean `cases` table of stage 3 (and, for RQ3 and the RQ1 term counts,
from the raw databases again). No model is fitted here; each table is the exact input
an analysis reads. Definitions are in rules/rq_datasets.md.

Output, in study.duckdb:
  rq1_cases    one row per study-group case: group, demographics, COVID window flag
               and the RQ1 event flags
  rq1_counts   cases per group x age band x sex x COVID window, with event counts; the
               group OTHER_FAERS holds every kept case outside the study group, so each
               class can also be compared with the rest of FAERS
  rq1_terms    cases per reaction term in the stimulant and nonstimulant groups
  rq2_cases    one row per study-group case with a valid receipt date: month, period
               (before shortage / shortage to label change / after label change)
               and the RQ2 event flags
  rq2_monthly  cases and event counts per study group and month, January 2018 to
               February 2026 (the RQ2 time series)
  rq3_cases    study-group cases of the 2022-2026 database, split by time into TRAIN
               (case versions known at the end of 2024) and TEST (received January 2025
               to February 2026, newest version)

With --csv DIR each table is also written to DIR as a CSV file.

Usage:
    python 04_rq_datasets.py --dbs historical.duckdb current.duckdb --study study.duckdb
"""

import argparse
from pathlib import Path

from common import COVID, CURRENT_START, STUDY_END, STUDY_START, connect

munge = __import__("03_munge")

RQ1_EVENTS = (
    "cardiovascular",
    "psychiatric",
    "dependence",
    "abuse",
    "misuse",
    "addiction",
    "overdose",
)
RQ2_EVENTS = ("ineffectiveness", "withdrawal", "misuse", "abuse", "addiction")
RQ2_CONTROL = "product_quality_supply"  # should rise if the shortage reached the reports
RQ2_FIRST, RQ2_LAST = "2018-01-01", "2026-02-28"
SHORTAGE_MONTH, LABEL_MONTH = "2022-10-01", "2023-05-01"  # announcement months, left out of periods
TRAIN_AS_OF = "2024Q4"  # RQ3 training rows use only what was known by the end of 2024
TEST_FROM, TEST_TO = "2025-01-01", "2026-02-28"  # last month before FDA's new system (AEMS)
TIERS = ("narrow", "broad")


def flags(groups):
    return ", ".join(f"{g}_{t}" for g in groups for t in TIERS)


def rq1(con):
    covid = f"coalesce(init_date BETWEEN DATE '{COVID[0]}' AND DATE '{COVID[1]}', false)"
    con.execute(f"""CREATE OR REPLACE TABLE rq1_cases AS
        SELECT caseid, init_date, {covid} AS covid_window, age_years, age_band, sex, wt_kg,
            rq1_group, rq1_group_confirmed, alpha2, concomitant_adhd, {flags(RQ1_EVENTS)}
        FROM cases WHERE rq1_group IS NOT NULL""")
    sums = ", ".join(f"count(*) FILTER ({g}_{t}) AS {g}_{t}" for g in RQ1_EVENTS for t in TIERS)
    con.execute(f"""CREATE OR REPLACE TABLE rq1_counts AS
        SELECT coalesce(rq1_group, 'OTHER_FAERS') AS rq1_group,
            coalesce(rq1_group_confirmed, 'NONE') AS rq1_group_confirmed, alpha2,
            {covid} AS covid_window, age_band, sex, count(*) AS cases, {sums}
        FROM cases GROUP BY ALL ORDER BY ALL""")


def rq1_terms(con, dbs):
    munge.attach(con, dbs)
    munge.select_cases(con, STUDY_START, STUDY_END)
    con.execute("""CREATE OR REPLACE TABLE rq1_terms AS
        SELECT c.rq1_group, lower(trim(r.pt)) AS pt, count(DISTINCT c.caseid) AS cases
        FROM cases c JOIN kept_reac r ON r.caseid = c.caseid
        WHERE c.rq1_group IN ('STIMULANT', 'NONSTIMULANT') AND trim(r.pt) <> ''
        GROUP BY ALL ORDER BY 1, 3 DESC, 2""")


def rq2(con):
    month = "date_trunc('month', init_date)"
    any_event = {t: " OR ".join(f"{g}_{t}" for g in RQ2_EVENTS) for t in TIERS}
    con.execute(f"""CREATE OR REPLACE TABLE rq2_cases AS
        SELECT caseid, rq1_group, rq1_group_confirmed, init_date, {month} AS init_month,
            CASE WHEN {month} BETWEEN DATE '{RQ2_FIRST}' AND DATE '{SHORTAGE_MONTH}' - 1
                    THEN 'before shortage'
                WHEN {month} > DATE '{SHORTAGE_MONTH}' AND {month} < DATE '{LABEL_MONTH}'
                    THEN 'shortage to label change'
                WHEN {month} > DATE '{LABEL_MONTH}' AND {month} <= DATE '{RQ2_LAST}'
                    THEN 'after label change' END AS period,
            {flags((*RQ2_EVENTS, RQ2_CONTROL))},
            {any_event["narrow"]} AS rq2_any_narrow, {any_event["broad"]} AS rq2_any_broad
        FROM cases WHERE rq1_group IS NOT NULL AND init_date IS NOT NULL""")
    sums = ", ".join(
        f"count(*) FILTER ({c}) AS {c}"
        for c in [f"{g}_{t}" for g in (*RQ2_EVENTS, RQ2_CONTROL) for t in TIERS]
        + ["rq2_any_narrow", "rq2_any_broad"]
    )
    parts = [
        f"""SELECT '{grouping}' AS grouping, {grouping} AS grp, init_month AS month,
            count(*) AS cases, {sums}
        FROM rq2_cases WHERE {grouping} IS NOT NULL
            AND init_month BETWEEN DATE '{RQ2_FIRST}' AND DATE '{RQ2_LAST}'
        GROUP BY ALL"""
        for grouping in ("rq1_group", "rq1_group_confirmed")
    ]
    con.execute(
        "CREATE OR REPLACE TABLE rq2_monthly AS " + " UNION ALL ".join(parts) + " ORDER BY ALL"
    )


def rq3(con):
    munge.build(con, "rq3_known_2024", CURRENT_START, TRAIN_AS_OF)
    munge.build(con, "rq3_known_now", CURRENT_START, STUDY_END)
    train = f"rq1_group IS NOT NULL AND init_date < DATE '{TEST_FROM}'"
    test = f"rq1_group IS NOT NULL AND init_date BETWEEN DATE '{TEST_FROM}' AND DATE '{TEST_TO}'"
    con.execute(f"""CREATE OR REPLACE TABLE rq3_cases AS
        SELECT 'TRAIN' AS split, * FROM rq3_known_2024 WHERE {train}
        UNION ALL
        SELECT 'TEST', * FROM rq3_known_now WHERE {test}
            AND caseid NOT IN (SELECT caseid FROM rq3_known_2024 WHERE {train})""")
    con.execute("DROP TABLE rq3_known_2024; DROP TABLE rq3_known_now")


def summary(con):
    for table, sql in (
        ("rq1_cases", "SELECT rq1_group, count(*) FROM rq1_cases GROUP BY 1 ORDER BY 1"),
        ("rq2_cases", "SELECT period, count(*) FROM rq2_cases GROUP BY 1 ORDER BY 1"),
        ("rq3_cases", "SELECT split, count(*) FROM rq3_cases GROUP BY 1 ORDER BY 1"),
    ):
        for label, n in con.execute(sql).fetchall():
            print(f"  {table} {label or '(outside the RQ2 periods)'}: {n:,}")
    for table in ("rq1_counts", "rq1_terms", "rq2_monthly"):
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n:,} rows")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dbs", nargs="+", required=True, type=Path)
    parser.add_argument("--study", required=True, type=Path)
    parser.add_argument("--csv", type=Path, help="also write each table to this folder")
    args = parser.parse_args()
    con = connect(args.study)
    if not con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = 'cases'"
    ).fetchone()[0]:
        raise SystemExit("study database has no cases table: run 03_munge.py first")
    print("RQ1: stimulant vs nonstimulant event patterns")
    rq1(con)
    rq1_terms(con, args.dbs)
    print("RQ2: reporting before and after the shortage and the label change")
    rq2(con)
    print("RQ3: serious outcomes, training as known at the end of 2024, then test")
    rq3(con)
    summary(con)
    if args.csv:
        args.csv.mkdir(parents=True, exist_ok=True)
        for table in (
            "rq1_cases",
            "rq1_counts",
            "rq1_terms",
            "rq2_cases",
            "rq2_monthly",
            "rq3_cases",
        ):
            con.execute(f"COPY {table} TO '{args.csv / (table + '.csv')}' (HEADER)")
        print(f"  CSV files written to {args.csv}")
    con.close()


if __name__ == "__main__":
    main()
