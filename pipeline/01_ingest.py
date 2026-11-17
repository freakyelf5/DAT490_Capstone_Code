"""Stage 1, ingestion: load FDA FAERS quarterly ASCII ZIP files into DuckDB.

Each quarter ZIP holds seven dollar-sign ($) delimited text files (DEMO, DRUG,
REAC, OUTC, INDI, THER, RPSR) and, from 2019 on, a list of deleted case numbers.
Values are loaded exactly as written: every column is text, nothing is trimmed or
recoded, and quote characters are kept as data. Each row also gets the quarter it
came from and its line number, which the case-version rule needs later.

Usage:
    python 01_ingest.py --zips DIR --db historical.duckdb --start 2012Q4 --end 2021Q4
    python 01_ingest.py --zips DIR --db current.duckdb --start 2022Q1 --end 2026Q2

The ZIPs are the files FDA publishes as faers_ascii_YYYYqN.zip.
"""

import argparse
import codecs
import re
import tempfile
import zipfile
from pathlib import Path

from common import FAMILIES, connect, quarter_list

# Known exceptions in FDA's own file names (found by surveying all ZIPs first).
NAME_EXCEPTIONS = {("2018Q1", "DEMO"): "demo18q1_new.txt"}
DELETED_FILE = re.compile(r"(delete\d\dq\d|(adr)?\d\dq\ddeletedcases|alldeletedcases)\.txt", re.I)


def find_members(names, quarter):
    """Map each family to its ZIP member, plus the deleted-case files."""
    token = quarter[2:4] + "q" + quarter[5]
    members, deleted = {}, []
    for name in names:
        base = Path(name).name.lower()
        for family in FAMILIES:
            if base in (f"{family.lower()}{token}.txt", NAME_EXCEPTIONS.get((quarter, family))):
                members[family] = name
        if DELETED_FILE.fullmatch(base):
            deleted.append(name)
    missing = set(FAMILIES) - set(members)
    if missing:
        raise ValueError(f"{quarter}: ZIP has no file for {sorted(missing)}")
    return members, deleted


def is_utf8(path):
    """True when the whole file decodes as UTF-8 (checked before loading, because a
    failed read would abort the quarter's transaction)."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 24), b""):
                decoder.decode(block)
            decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return False
    return True


def utf8_copy(path):
    """Rewrite a file whose few bad lines are Windows-1252 instead of UTF-8.

    FDA's 2019Q3 DRUG file has five such lines. Each line is decoded on its own and
    only lines that fail UTF-8 fall back, so the count printed is exactly the lines changed.
    """
    fixed = path.with_suffix(".utf8.txt")
    changed = 0
    with open(path, "rb") as src, open(fixed, "w", encoding="utf-8", newline="") as out:
        for line in src:
            try:
                out.write(line.decode("utf-8"))
            except UnicodeDecodeError:
                out.write(line.decode("cp1252"))
                changed += 1
    return fixed, changed


def read_sql(path):
    # header row gives the column names; quote='' keeps any " character as data.
    # strict_mode makes a row with the wrong number of fields an error, not a guess.
    return f"""SELECT * FROM read_csv('{path}', delim='$', quote='', escape='', header=true,
        all_varchar=true, strict_mode=true, null_padding=false)"""


# 2012Q4 misspells three header names; read them with the later spelling (DQ-039).
HEADER_ALIASES = {
    ("2012Q4", "DEMO"): {"rept_dt": "rept_dt"},  # the file has " rept_dt" (leading space)
    ("2012Q4", "DRUG"): {"lot_nbr": "lot_num"},
    ("2012Q4", "OUTC"): {"outc_code": "outc_cod"},
}


def load_family(con, family, quarter, path, member):
    table = f"raw.{family.lower()}"
    fallback = 0
    if not is_utf8(path):
        path, fallback = utf8_copy(path)
    con.execute(f"CREATE OR REPLACE TEMP TABLE stage AS {read_sql(path)}")
    alias = HEADER_ALIASES.get((quarter, family), {})
    for name in [r[0] for r in con.execute("DESCRIBE stage").fetchall()]:
        clean = alias.get(name.strip().lower(), name.strip().lower())
        if clean != name.lower():
            con.execute(f'ALTER TABLE stage RENAME COLUMN "{name}" TO {clean}')
    columns = [r[0] for r in con.execute("DESCRIBE stage").fetchall()]
    tables = con.execute("SELECT table_name FROM duckdb_tables() WHERE schema_name = 'raw'")
    if family.lower() not in {r[0] for r in tables.fetchall()}:
        con.execute(
            f"""CREATE TABLE {table} AS SELECT '{quarter}' AS source_quarter,
            0::BIGINT AS line_no, * FROM stage LIMIT 0"""
        )
    # Fields FDA added over the years (for example prod_ai in 2014Q3) become new columns.
    have = {r[0].lower() for r in con.execute(f"DESCRIBE {table}").fetchall()}
    for column in columns:
        if column not in have:
            con.execute(f'ALTER TABLE {table} ADD COLUMN "{column}" VARCHAR')
    con.execute(
        f"""INSERT INTO {table} BY NAME SELECT '{quarter}' AS source_quarter,
        row_number() OVER () + 1 AS line_no, * FROM stage"""
    )  # line 1 is the header, so data starts on line 2
    rows = con.execute("SELECT count(*) FROM stage").fetchone()[0]
    con.execute(
        "INSERT INTO raw.load_log VALUES (?, ?, ?, ?, ?)", [quarter, family, member, rows, fallback]
    )
    return rows


def load_quarter(con, quarter, zip_path):
    with zipfile.ZipFile(zip_path) as bundle, tempfile.TemporaryDirectory() as tmp:
        members, deleted = find_members(bundle.namelist(), quarter)
        for family, member in members.items():
            path = Path(bundle.extract(member, tmp))
            rows = load_family(con, family, quarter, path, Path(member).name)
            print(f"  {quarter} {family}: {rows:,} rows")
            path.unlink()
        # Deleted-case lists: one case number per line, no header. Only lines that are
        # digits and nothing else count (rule D3; FDA's 2020Q1 list has 26 numbers
        # followed by a tab, which the rule leaves unparsed).
        for member in deleted:
            lines = bundle.read(member).decode("utf-8-sig").splitlines()
            ids = [(quarter, x) for x in lines if re.fullmatch(r"[0-9]+", x)]
            if ids:
                con.executemany("INSERT INTO raw.deleted VALUES (?, ?)", ids)
            print(f"  {quarter} deleted-case list {Path(member).name}: {len(ids):,} case numbers")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zips", required=True, type=Path, help="folder of faers_ascii_*.zip")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()

    con = connect(args.db)
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(
        """CREATE TABLE IF NOT EXISTS raw.load_log (quarter VARCHAR, family VARCHAR,
        file VARCHAR, rows BIGINT, cp1252_lines BIGINT)"""
    )
    con.execute("CREATE TABLE IF NOT EXISTS raw.deleted (source_quarter VARCHAR, caseid VARCHAR)")
    done = {r[0] for r in con.execute("SELECT DISTINCT quarter FROM raw.load_log").fetchall()}
    for quarter in quarter_list(args.start, args.end):
        if quarter in done:
            print(f"{quarter}: already loaded, skipped")
            continue
        zips = [p for p in args.zips.glob("*.zip") if quarter.lower() in p.name.lower()]
        if len(zips) != 1:
            raise SystemExit(f"{quarter}: expected one ZIP in {args.zips}, found {len(zips)}")
        print(f"{quarter}: loading {zips[0].name}")
        con.execute("BEGIN TRANSACTION")  # a quarter loads completely or not at all
        load_quarter(con, quarter, zips[0])
        con.execute("COMMIT")
    con.close()


if __name__ == "__main__":
    main()
