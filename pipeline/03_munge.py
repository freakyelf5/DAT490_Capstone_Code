"""Stage 3, munging: turn the raw FDA tables into one clean case table.

Steps (each rule is documented in rules/ and its table is in rules/tables/):
  1. Case selection: newest version of every case, FDA-deleted cases removed. The two
     databases are read as one series, so a case in both counts once (its newest
     version). Rules D1-D6 and X1.
  2. Demographics: age to years, weight to kg, sex codes; values outside 0-120 years or
     0-650 kg stay missing. Raw values are never changed; cleaned values are new columns.
     Rule DQ-012.
  3. ADHD medicines: each drug row is matched to an ingredient (prod_ai first, then the
     brand/generic name list). Guanfacine and clonidine count only with an ADHD
     indication. Rules DQ-015 and DQ-016.
  4. Study groups: a case is STIMULANT or NONSTIMULANT when an ADHD medicine is a primary
     or secondary suspect; cases with both classes are MULTI_ADHD_CLASS and kept apart.
     Rule DQ-019.
  5. Event flags from the reaction terms (narrow and broad lists per group), serious
     outcome flags from OUTC, and the dose, route and other-drug counts used by RQ3.
     Rules DQ-017 and DQ-018.
  6. One patient reported as separate cases by many manufacturers (Canada, age 40,
     96 kg) is removed from every case table. Rule DQ-038.

Output, in study.duckdb:
  drug_classes  every distinct (prod_ai, drugname) pair that is an ADHD medicine
  cases         every kept case 2012Q4-2026Q2 with its group, demographics and flags

The research-question datasets are built from these in stage 4.

Usage:
    python 03_munge.py --dbs historical.duckdb current.duckdb --out study.duckdb
"""

import argparse
from pathlib import Path

from common import (
    FAMILIES,
    STUDY_END,
    STUDY_START,
    age_sex_rules,
    classify,
    connect,
    drug_prefilter,
    indication_terms,
    kept_cases_sql,
    load_drug_map,
    sql_list,
    term_groups,
)

EVENT_GROUPS = (
    "cardiovascular",
    "psychiatric",
    "dependence",
    "abuse",
    "misuse",
    "addiction",
    "withdrawal",
    "overdose",
    "ineffectiveness",
    "product_quality_supply",
)
SERIOUS = {"DE": "death", "LT": "life_threatening", "HO": "hospitalization"}


def attach(con, dbs):
    """all_<family> views stack every database's raw table (columns matched by name)."""
    for i, db in enumerate(dbs):
        con.execute(f"ATTACH '{db}' AS d{i} (READ_ONLY)")
    for family in (*FAMILIES, "deleted"):
        parts = [f"SELECT * FROM d{i}.raw.{family.lower()}" for i in range(len(dbs))]
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW all_{family.lower()} AS "
            + " UNION ALL BY NAME ".join(parts)
        )


def column(con, table, name):
    names = {r[0].lower() for r in con.execute(f"DESCRIBE {table}").fetchall()}
    return name if name in names else "NULL::VARCHAR"


def classify_drugs(con):
    """drug_classes: one row per distinct (prod_ai, drugname) that is an ADHD medicine."""
    drug_map = load_drug_map()
    ingredient_re, alias_re = drug_prefilter(drug_map)
    name = (
        r"' ' || trim(regexp_replace(regexp_replace(upper(drugname), '/[0-9]+/', ' ', 'g'), "
        r"'[^A-Z0-9]+', ' ', 'g')) || ' '"
    )
    pairs = con.execute(
        f"""SELECT DISTINCT prod_ai, drugname FROM all_drug
        WHERE regexp_matches(upper(prod_ai), ?) OR regexp_matches({name}, ?)""",
        [ingredient_re, alias_re],
    ).fetchall()
    rows = []
    for prod_ai, drugname in pairs:
        classes, disposition = classify(drug_map, prod_ai, drugname)
        if classes and disposition in ("INCLUDE", "CONDITIONAL"):
            rows.append((prod_ai, drugname, sorted(classes), disposition))
    con.execute("""CREATE OR REPLACE TABLE drug_classes (prod_ai VARCHAR, drugname VARCHAR,
        classes VARCHAR[], disposition VARCHAR)""")
    con.executemany("INSERT INTO drug_classes VALUES (?, ?, ?, ?)", rows)
    print(f"  {len(pairs):,} candidate drug names, {len(rows):,} are ADHD medicines")


def demographics_sql(con):
    rules = age_sex_rules()
    pattern = rules["amount_pattern"]

    def convert(amount, unit, units):
        whens = " ".join(
            f"WHEN '{c}' THEN CAST({amount} AS DOUBLE) * {u['multiply']} / {u['divide']}"
            for c, u in units.items()
        )
        return (
            f"CASE WHEN regexp_full_match({amount}, '{pattern}') THEN CASE {unit} {whens} END END"
        )

    age, wt = (
        convert("age", "age_cod", rules["age_units"]),
        convert("wt", "wt_cod", rules["weight_units"]),
    )
    bands = " ".join(
        f"WHEN age_years >= {b['min_inclusive']}"
        + (f" AND age_years < {b['max_exclusive']}" if b["max_exclusive"] else "")
        + f" THEN '{b['band']}'"
        for b in rules["age_band_fine"]
    )
    sex = column(con, "all_demo", "gndr_cod")  # the sex field was called gndr_cod before 2014Q3
    return f"""SELECT *, coalesce(CASE {bands} END, 'UNKNOWN') AS age_band FROM (
        SELECT caseid, primaryid, source_quarter,
            {column(con, "all_demo", "occr_country")} AS country,
            try_strptime(init_fda_dt, '%Y%m%d')::DATE AS init_date,
            CASE WHEN {age} BETWEEN 0 AND 120 THEN {age} END AS age_years,
            CASE WHEN {wt} > 0 AND {wt} <= 650 THEN {wt} END AS wt_kg,
            CASE coalesce(sex, {sex}) WHEN 'F' THEN 'F' WHEN 'M' THEN 'M'
                WHEN 'UNK' THEN 'UNKNOWN' WHEN 'NS' THEN 'UNKNOWN' ELSE 'NOT_REPORTED' END AS sex
        FROM all_demo d SEMI JOIN kept k USING (primaryid, source_quarter))"""


def select_cases(con, start, end):
    """TEMP tables kept (one row per kept case) and kept_<family> views of their rows."""
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE kept AS "
        f"{kept_cases_sql('all_demo', 'all_deleted', start, end)}"
    )
    for family in ("drug", "reac", "outc", "indi"):
        con.execute(f"""CREATE OR REPLACE TEMP VIEW kept_{family} AS SELECT x.*, k.caseid
            FROM all_{family} x JOIN kept k USING (primaryid, source_quarter)""")


def build(con, name, start, end):
    """Table ``name``: one row per kept case of quarters start..end, with every study field."""
    select_cases(con, start, end)
    con.execute(f"CREATE OR REPLACE TEMP TABLE demo AS {demographics_sql(con)}")
    tiers = {t: sql_list(v) for t, v in indication_terms().items()}
    term = "coalesce(lower(trim(indi_pt)), '')"
    # One row per ADHD-medicine drug row, with the indication written for that same drug.
    con.execute(f"""CREATE OR REPLACE TEMP TABLE adhd_rows AS
        WITH linked AS (
            SELECT primaryid, source_quarter, indi_drug_seq AS drug_seq,
                bool_or({term} IN ({tiers["adhd"]})) AS any_adhd,
                bool_or({term} IN ({tiers["related"]})) AS any_related,
                bool_and({term} IN ({tiers["unknown"]})) AS all_unknown
            FROM kept_indi GROUP BY ALL)
        SELECT d.caseid, c.classes, coalesce(d.role_cod, '') IN ('PS', 'SS') AS suspect,
            coalesce(l.any_adhd, false) AS confirmed,
            -- a drug row stated for another illness is not counted; a missing or unknown
            -- indication is, except for guanfacine/clonidine, which need ADHD stated
            (l.primaryid IS NULL OR l.any_adhd OR l.any_related OR l.all_unknown)
                AND (c.disposition = 'INCLUDE' OR coalesce(l.any_adhd, false)) AS matched,
            d.dose_amt, d.dose_unit, d.route
        FROM kept_drug d
        JOIN drug_classes c ON d.prod_ai IS NOT DISTINCT FROM c.prod_ai
            AND d.drugname IS NOT DISTINCT FROM c.drugname
        LEFT JOIN linked l USING (primaryid, source_quarter, drug_seq)""")

    def has(flag, *classes):
        test = " OR ".join(f"list_contains(classes, '{c}')" for c in classes)
        return f"bool_or(suspect AND {flag} AND ({test}))"

    def group(flag):
        s, n = has(flag, "STIMULANT"), has(flag, "NONSTIMULANT", "ALPHA2")
        return f"""CASE WHEN {s} AND {n} THEN 'MULTI_ADHD_CLASS' WHEN {s} THEN 'STIMULANT'
            WHEN {n} THEN 'NONSTIMULANT' END"""

    con.execute(f"""CREATE OR REPLACE TEMP TABLE exposure AS
        SELECT caseid, {group("matched")} AS rq1_group, {group("confirmed")} AS rq1_group_confirmed,
            {has("matched", "ALPHA2")} AS alpha2, bool_or(NOT suspect) AS concomitant_adhd
        FROM adhd_rows GROUP BY caseid""")

    groups = term_groups()
    flags = ", ".join(
        f"bool_or(lower(trim(pt)) IN ({sql_list(groups[g][t])})) AS {g}_{t}"
        for g in EVENT_GROUPS
        for t in ("narrow", "broad")
    )
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE events AS SELECT caseid, {flags} "
        "FROM kept_reac GROUP BY caseid"
    )
    outc = ", ".join(f"bool_or(trim(outc_cod) = '{c}') AS {n}" for c, n in SERIOUS.items())
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE outcomes AS SELECT caseid, {outc} "
        "FROM kept_outc GROUP BY caseid"
    )

    # RQ3 predictors, for study-group cases only. Dose and route come from the ADHD rows
    # that put the case in its group; the counts are of the other drugs on the report.
    exposed = "suspect AND matched"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE dose_route AS
        SELECT caseid,
            bool_or({exposed} AND regexp_full_match(trim(dose_amt), '[0-9]+(\\.[0-9]+)?')
                AND coalesce(trim(dose_unit), '') <> '') AS dose_reported,
            bool_or({exposed} AND upper(trim(dose_unit)) = 'MG') AS dose_unit_mg,
            bool_or({exposed} AND lower(trim(route)) = 'oral') AS route_oral,
            bool_or({exposed} AND lower(trim(route)) NOT IN ('', 'oral', 'unknown')) AS route_other
        FROM adhd_rows GROUP BY caseid""")
    drug = "upper(trim(coalesce(nullif(trim(d.prod_ai), ''), d.drugname)))"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE features AS
        SELECT d.caseid,
            count(DISTINCT {drug}) FILTER (WHERE d.role_cod = 'C') AS concomitant_drugs,
            count(DISTINCT {drug}) FILTER (WHERE d.role_cod IN ('PS', 'SS') AND c.classes IS NULL)
                AS other_suspect_drugs,
            count(DISTINCT {drug}) FILTER (WHERE d.role_cod = 'I') AS interacting_drugs
        FROM kept_drug d
        LEFT JOIN drug_classes c ON d.prod_ai IS NOT DISTINCT FROM c.prod_ai
            AND d.drugname IS NOT DISTINCT FROM c.drugname
        WHERE d.caseid IN (SELECT caseid FROM exposure WHERE rq1_group IS NOT NULL)
        GROUP BY d.caseid""")

    any_serious = " OR ".join(f"o.{n}" for n in SERIOUS.values())
    con.execute(f"""CREATE OR REPLACE TABLE {name} AS
        SELECT m.caseid, m.init_date, m.age_years, m.age_band, m.sex, m.wt_kg,
            e.rq1_group, e.rq1_group_confirmed, coalesce(e.alpha2, false) AS alpha2,
            coalesce(e.concomitant_adhd, false) AS concomitant_adhd,
            {
        ", ".join(
            f"coalesce(v.{g}_{t}, false) AS {g}_{t}"
            for g in EVENT_GROUPS
            for t in ("narrow", "broad")
        )
    },
            {", ".join(f"coalesce(o.{n}, false) AS {n}" for n in SERIOUS.values())},
            coalesce({any_serious}, false) AS serious_target,
            CASE WHEN o.caseid IS NULL THEN 'NO_OUTC_RECORD' WHEN {any_serious} THEN 'TARGET_CODE'
                ELSE 'OTHER_CODE_ONLY' END AS outc_state,
            coalesce(r.dose_reported, false) AS dose_reported,
            coalesce(r.dose_unit_mg, false) AS dose_unit_mg,
            CASE WHEN r.route_other THEN 'OTHER' WHEN r.route_oral THEN 'ORAL' ELSE 'UNKNOWN' END
                AS route_category,
            coalesce(f.concomitant_drugs, 0) AS concomitant_drugs,
            coalesce(f.other_suspect_drugs, 0) AS other_suspect_drugs,
            coalesce(f.interacting_drugs, 0) AS interacting_drugs
        FROM demo m
        LEFT JOIN exposure e USING (caseid)
        LEFT JOIN events v USING (caseid)
        LEFT JOIN outcomes o USING (caseid)
        LEFT JOIN features f USING (caseid)
        LEFT JOIN dose_route r USING (caseid)
        -- DQ-038: one Canadian patient filed as separate cases by about 25 manufacturers
        -- (coalesce: a case with no age or weight is not one of them and stays in)
        WHERE NOT coalesce(m.country = 'CA' AND m.age_years = 40 AND round(m.wt_kg) = 96, false)""")
    n = con.execute(f"SELECT count(*), count(rq1_group) FROM {name}").fetchone()
    print(f"  {name}: {n[0]:,} kept cases, {n[1]:,} in an ADHD study group")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dbs", nargs="+", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--start", default=STUDY_START)
    parser.add_argument("--end", default=STUDY_END)
    args = parser.parse_args()
    con = connect(args.out)
    attach(con, args.dbs)
    classify_drugs(con)

    print("Combined 2012Q4-2026Q2 series")
    build(con, "cases", args.start, args.end)
    con.close()


if __name__ == "__main__":
    main()
