"""Stage 2, verification: check that each database holds exactly what FDA published.

Checks, per quarter and file:
  1. Rows in the database equal the data lines in the source file, recounted
     straight from the ZIP (independent of the loader).
  2. Every DEMO row has a primaryid, a caseid and a whole-number caseversion.
  3. Child-file rows (DRUG, REAC, ...) point to a DEMO report of the same quarter
     (reported, not a failure: FDA files contain a handful of such rows).
Then it applies the FDA case rule (newest version, deleted cases removed) and
prints raw vs kept counts for every file (the numbers in docs/verification_results.md).

Usage:
    python 02_verify.py --db current.duckdb [--zips DIR]

Exits with status 1 when any check fails. Writes results/verify_<database>.csv.
"""

import argparse
import sys
import zipfile
from pathlib import Path

from common import FAMILIES, RESULTS, connect, kept_cases_sql, write_csv

ingest = __import__("01_ingest")


def count_lines(bundle, member):
    """Data lines in a ZIP member: newlines, minus the header, plus an unterminated last line."""
    newlines, last = 0, b"\n"
    with bundle.open(member) as f:
        for block in iter(lambda: f.read(1 << 24), b""):
            newlines += block.count(b"\n")
            last = block[-1:]
    return newlines - 1 + (last != b"\n")


def recount(con, zips):
    problems = []
    quarters = [
        r[0] for r in con.execute("SELECT DISTINCT quarter FROM raw.load_log ORDER BY 1").fetchall()
    ]
    for quarter in quarters:
        path = next(p for p in zips.glob("*.zip") if quarter.lower() in p.name.lower())
        with zipfile.ZipFile(path) as bundle:
            members, _ = ingest.find_members(bundle.namelist(), quarter)
            for family, member in members.items():
                source = count_lines(bundle, member)
                table = f"raw.{family.lower()}"
                loaded = con.execute(
                    f"SELECT count(*) FROM {table} WHERE source_quarter = ?", [quarter]
                ).fetchone()[0]
                if source != loaded:
                    problems.append(f"{quarter} {family}: source {source:,} vs loaded {loaded:,}")
        print(f"  {quarter}: all seven files recounted")
    return problems


def field_checks(con):
    problems = []
    bad = con.execute(
        """SELECT count(*) FROM raw.demo WHERE primaryid IS NULL OR caseid IS NULL
        OR NOT regexp_full_match(coalesce(caseversion, ''), '[0-9]+')"""
    ).fetchone()[0]
    if bad:
        problems.append(f"DEMO rows missing a key or with a non-numeric caseversion: {bad:,}")
    dupes = con.execute(
        """SELECT count(*) FROM (SELECT source_quarter, primaryid FROM raw.demo
        GROUP BY ALL HAVING count(*) > 1)"""
    ).fetchone()[0]
    if dupes:
        problems.append(f"primaryid repeated inside one quarter's DEMO file: {dupes:,}")
    return problems


def orphans(con):
    """Child rows whose report is not in the same quarter's DEMO file."""
    out = {}
    for family in FAMILIES[1:]:
        out[family] = con.execute(
            f"""SELECT count(*) FROM raw.{family.lower()} c ANTI JOIN raw.demo d
            ON c.primaryid = d.primaryid AND c.source_quarter = d.source_quarter"""
        ).fetchone()[0]
    return out


def raw_vs_kept(con):
    first, last = con.execute("SELECT min(quarter), max(quarter) FROM raw.load_log").fetchone()
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE kept AS "
        f"{kept_cases_sql('raw.demo', 'raw.deleted', first, last)}"
    )
    rows = []
    for family in FAMILIES:
        table = f"raw.{family.lower()}"
        raw = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        kept = con.execute(
            f"""SELECT count(*) FROM {table} t SEMI JOIN kept k
            ON t.primaryid = k.primaryid AND t.source_quarter = k.source_quarter"""
        ).fetchone()[0]
        rows.append({"file": family, "raw_rows": raw, "rows_after_cleaning": kept})
    cases = con.execute("SELECT count(DISTINCT caseid) FROM raw.demo").fetchone()[0]
    deleted = con.execute(
        """SELECT count(DISTINCT caseid) FROM raw.demo
        WHERE caseid IN (SELECT caseid FROM raw.deleted)"""
    ).fetchone()[0]
    return first, last, cases, deleted, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--zips", type=Path, help="recount source lines from these ZIPs")
    args = parser.parse_args()
    con = connect(args.db, read_only=True)

    problems = recount(con, args.zips) if args.zips else []
    problems += field_checks(con)
    for family, n in orphans(con).items():
        print(f"  {family} rows without a same-quarter DEMO report: {n:,}")
    fallback = con.execute("SELECT sum(cp1252_lines) FROM raw.load_log").fetchone()[0]
    print(f"  lines read as Windows-1252 instead of UTF-8: {fallback:,}")

    first, last, cases, deleted, rows = raw_vs_kept(con)
    kept = rows[0]["rows_after_cleaning"]
    print(f"\n{args.db.name}: {first} to {last}")
    print(f"  distinct cases {cases:,}, deleted by FDA {deleted:,}, kept {kept:,}")
    for r in rows:
        print(
            f"  {r['file']:5} raw {r['raw_rows']:>13,}"
            f"  after cleaning {r['rows_after_cleaning']:>13,}"
        )
    write_csv(rows, RESULTS / f"verify_{args.db.stem}.csv")

    if problems:
        print("\nFAILED:\n  " + "\n  ".join(problems))
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
