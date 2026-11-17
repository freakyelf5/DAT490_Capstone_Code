"""Shared settings and helpers for the stage scripts.

Every rule table (drug map, indication terms, reaction-term groups, age/sex units)
is read from the repository's rules/tables folder, so the code and the documented
rules can never drift apart.
"""

import csv
import json
import os
import re
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "tables"
RESULTS = Path(os.environ.get("RESULTS_DIR", ROOT / "results"))
FAMILIES = ("DEMO", "DRUG", "REAC", "OUTC", "INDI", "THER", "RPSR")

STUDY_START, STUDY_END = "2012Q4", "2026Q2"  # final project plan: 55 quarters
CURRENT_START = "2022Q1"  # first quarter of the current database (RQ3 uses only this era)
COVID = ("2020-03-01", "2021-12-31")  # COVID-19 window (DQ-037), flagged for sensitivity checks


def connect(path=":memory:", read_only=False):
    con = duckdb.connect(str(path), read_only=read_only)
    con.execute("SET preserve_insertion_order = true")
    return con


def quarter_list(start, end):
    """'2012Q4', '2013Q1', ... through ``end``."""
    year, q = int(start[:4]), int(start[5])
    out = []
    while f"{year}Q{q}" <= end:
        out.append(f"{year}Q{q}")
        year, q = (year + 1, 1) if q == 4 else (year, q + 1)
    return out


def sql_list(values):
    return ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Rule tables


def age_sex_rules():
    return json.loads((RULES / "age_sex_rules_v0.1.json").read_text())


def term_groups():
    """{group: {"narrow": [...], "broad": [...]}}; the broad list includes the narrow one."""
    groups = {}
    for row in read_csv(RULES / "reaction_term_groups_v0.1.csv"):
        if row["tier"] in ("narrow", "broad"):
            g = groups.setdefault(row["group"], {"narrow": [], "broad": []})
            g["broad"].append(row["pt"])
            if row["tier"] == "narrow":
                g["narrow"].append(row["pt"])
    return groups


def indication_terms():
    """{tier: [terms]} with tiers adhd, related and unknown."""
    tiers = {"adhd": [], "related": [], "unknown": []}
    for row in read_csv(RULES / "adhd_indication_terms_v0.1.csv"):
        tiers[row["tier"]].append(row["indi_pt"])
    return tiers


# ---------------------------------------------------------------------------
# ADHD drug map: prod_ai (active ingredient) first, then brand/generic name aliases

ORDER = ("INCLUDE", "CONDITIONAL", "EXCLUDE")  # later = more restrictive


def load_drug_map():
    ingredients = {r["component"]: r for r in read_csv(RULES / "adhd_ingredient_map_v0.1.csv")}
    aliases = read_csv(RULES / "adhd_name_alias_v0.1.csv")
    return ingredients, aliases


def normalize_name(name):
    """Upper case, drop dictionary codes like /00016601/, keep whole words."""
    text = re.sub(r"[^A-Z0-9]+", " ", re.sub(r"/\d+/", " ", (name or "").upper())).strip()
    return f" {text} "


def _aliases_in(aliases, drugname):
    text = normalize_name(drugname)
    hits = [a for a in aliases if f" {a['alias']} " in text]
    names = {a["alias"] for a in hits}
    # Keep the longest match ("DEXTROAMPHETAMINE" over "AMPHETAMINE"), and use the
    # short "DEXTR" only when an amphetamine word is also present ("AMPHET/DEXTR").
    hits = [a for a in hits if not any(f" {a['alias']} " in f" {n} " for n in names - {a["alias"]})]
    return [
        a
        for a in hits
        if a["alias"] != "DEXTR" or any(n.startswith(("AMPHET", "AMFET")) for n in names)
    ]


def classify(drug_map, prod_ai, drugname):
    """(classes, disposition) for one DRUG row's ingredient and name text.

    Classes are STIMULANT, NONSTIMULANT and ALPHA2. Disposition INCLUDE counts,
    CONDITIONAL counts only with an ADHD indication (guanfacine, clonidine), and
    EXCLUDE never counts. Unknown products return no classes.
    """
    ingredients, aliases = drug_map
    hits = _aliases_in(aliases, drugname)
    overrides = [a for a in hits if a["overrides_prod_ai"] == "Y"]  # e.g. INTUNIV, KAPVAY
    if not overrides and (prod_ai or "").strip():
        parts = [p.strip() for p in re.split(r"\\|, | AND ", prod_ai.strip().upper())]
        known = [ingredients[p] for p in parts if p in ingredients]
        if not known:
            return set(), None
        disposition = max((i["disposition"] for i in known), key=ORDER.index)
        if len(known) < len(parts):  # combined with a non-ADHD ingredient
            disposition = "EXCLUDE"
        return {i["adhd_class"] for i in known} - {"NONE"}, disposition
    hits = overrides or hits
    if not hits:
        return set(), None
    return (
        {a["adhd_class"] for a in hits} - {"NONE"},
        max((a["disposition"] for a in hits), key=ORDER.index),
    )


def drug_prefilter(drug_map):
    """SQL regexes that every DRUG row the map can classify must match (a fast first filter)."""
    ingredients, aliases = drug_map
    keys = sorted(ingredients, key=len, reverse=True)
    names = sorted({a["alias"] for a in aliases}, key=len, reverse=True)
    return "|".join(map(re.escape, keys)), " (" + "|".join(map(re.escape, names)) + ") "


# ---------------------------------------------------------------------------
# Case selection (FDA instructions): newest version of each case, deleted cases removed


def kept_cases_sql(demo, deleted, start, end):
    """One row per kept case among quarters ``start``..``end``.

    The highest caseversion wins; when the same version appears twice, the later
    quarter's copy (and then the later line) wins. Any case on an FDA deleted-case
    list up to ``end`` is removed.
    """
    return f"""
        SELECT caseid, primaryid, source_quarter, TRY_CAST(caseversion AS BIGINT) AS caseversion
        FROM {demo}
        WHERE source_quarter BETWEEN '{start}' AND '{end}'
        QUALIFY row_number() OVER (
            PARTITION BY caseid
            ORDER BY TRY_CAST(caseversion AS BIGINT) DESC, source_quarter DESC, line_no DESC) = 1
        AND caseid NOT IN (
            SELECT caseid FROM {deleted} WHERE source_quarter BETWEEN '{start}' AND '{end}')"""
