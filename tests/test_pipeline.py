"""Runs the five stage scripts end to end on small synthetic FAERS quarters."""

import os
import random
import subprocess
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import duckdb

PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
HEADERS = {
    "DEMO": "primaryid$caseid$caseversion$i_f_code$init_fda_dt$fda_dt$age$age_cod$sex$wt$wt_cod"
    "$occr_country",
    "DRUG": "primaryid$caseid$drug_seq$role_cod$drugname$prod_ai$route$dose_amt$dose_unit",
    "REAC": "primaryid$caseid$pt$drug_rec_act",
    "OUTC": "primaryid$caseid$outc_cod",
    "INDI": "primaryid$caseid$indi_drug_seq$indi_pt",
    "THER": "primaryid$caseid$dsg_drug_seq$start_dt$end_dt",
    "RPSR": "primaryid$caseid$rpsr_cod",
}
DRUGS = [
    ("ADDERALL XR", "AMPHETAMINE ASPARTATE\\AMPHETAMINE SULFATE"),
    ("VYVANSE", "LISDEXAMFETAMINE DIMESYLATE"),
    ("RITALIN", ""),
    ("STRATTERA", "ATOMOXETINE HYDROCHLORIDE"),
    ("INTUNIV", "GUANFACINE HYDROCHLORIDE"),
    ("CLONIDINE", "CLONIDINE"),
]
OTHER = [("LIPITOR", "ATORVASTATIN"), ("ZOLOFT", "SERTRALINE"), ("ADVIL", "IBUPROFEN")]
TERMS = [
    "hypertension",
    "anxiety",
    "drug dependence",
    "drug ineffective",
    "withdrawal syndrome",
    "drug abuse",
    "product supply issue",
    "headache",
    "nausea",
    "tachycardia",
]


def quarter(rng, name, cases, first_id, start, end):
    """Rows for one quarter; ``cases`` lists (caseid, version) pairs, some reused later."""
    rows = {f: [HEADERS[f]] for f in HEADERS}
    for n, (caseid, version) in enumerate(cases):
        pid = str(first_id + n)
        day = start + timedelta(days=rng.randrange((end - start).days))
        country = "US" if n % 50 else "CA"
        age, weight = rng.randint(3, 70), rng.randint(20, 110)
        if n % 100 == 0:  # Canadian cases with no age or weight
            age = weight = ""
        rows["DEMO"].append(
            f"{pid}${caseid}${version}$I${day:%Y%m%d}${day:%Y%m%d}${age}$YR$"
            f"{rng.choice('FM')}${weight}$KG${country}"
        )
        drugs = [rng.choice(DRUGS)] + rng.sample(OTHER + DRUGS[3:4], rng.randint(0, 2))
        for seq, (drug, ingredient) in enumerate(drugs, 1):
            role = "PS" if seq == 1 else rng.choice(["C", "SS", "I"])
            rows["DRUG"].append(f"{pid}${caseid}${seq}${role}${drug}${ingredient}$Oral$10$MG")
            indication = "attention deficit hyperactivity disorder" if rng.random() < 0.6 else ""
            if seq == 1 and indication:
                rows["INDI"].append(f"{pid}${caseid}$1${indication}")
            rows["THER"].append(f"{pid}${caseid}${seq}$$")
        for term in rng.sample(TERMS, 2):
            rows["REAC"].append(f"{pid}${caseid}${term}$")
        if rng.random() < 0.3:
            rows["OUTC"].append(f"{pid}${caseid}${rng.choice(['DE', 'HO', 'LT', 'OT'])}")
        rows["RPSR"].append(f"{pid}${caseid}$CSM")
    token = name[2:4] + "Q" + name[5]
    with zipfile.ZipFile(ZIPS / f"faers_ascii_{name.lower()}.zip", "w") as z:
        for family, lines in rows.items():
            data = ("\n".join(lines) + "\n").encode()
            if family == "DRUG" and name == "2021Q4":  # one Windows-1252 line, as in FDA's 2019Q3
                data += b"1$900000$9$C$CAF\xc9 NOIR$$$$\n"
            z.writestr(f"ASCII/{family}{token}.txt", data)
        z.writestr(f"ASCII/DELETE{token}.txt", "900001\n")
        z.writestr("ASCII/ASC_NTS.pdf", "notes")


def run(script, *args, env):
    subprocess.run([sys.executable, script, *map(str, args)], cwd=PIPELINE, env=env, check=True)


def test_pipeline(tmp_path):
    global ZIPS
    ZIPS = tmp_path / "zips"
    ZIPS.mkdir()
    rng = random.Random(490)
    old = [(str(900000 + i), 1) for i in range(1500)]
    quarter(rng, "2021Q4", old, 1, date(2018, 1, 1), date(2021, 12, 31))
    new = [(str(800000 + i), 1) for i in range(2500)]
    quarter(rng, "2024Q4", new[:1500] + old[:100], 10_000, date(2022, 1, 1), date(2024, 12, 31))
    quarter(
        rng,
        "2025Q1",
        new[1500:] + [(c, 2) for c, _ in new[:50]],
        20_000,
        date(2025, 1, 1),
        date(2026, 2, 28),
    )

    env = {**os.environ, "RESULTS_DIR": str(tmp_path / "results")}
    hist, cur, study = tmp_path / "hist.duckdb", tmp_path / "cur.duckdb", tmp_path / "study.duckdb"
    run(
        "01_ingest.py",
        "--zips",
        ZIPS,
        "--db",
        hist,
        "--start",
        "2021Q4",
        "--end",
        "2021Q4",
        env=env,
    )
    run(
        "01_ingest.py", "--zips", ZIPS, "--db", cur, "--start", "2024Q4", "--end", "2025Q1", env=env
    )
    run("02_verify.py", "--db", cur, "--zips", ZIPS, env=env)
    run("02_verify.py", "--db", hist, "--zips", ZIPS, env=env)
    run("03_munge.py", "--dbs", hist, cur, "--out", study, env=env)
    csv = tmp_path / "csv"
    run("04_rq_datasets.py", "--dbs", hist, cur, "--study", study, "--csv", csv, env=env)
    out = tmp_path / "dictionary"
    run("05_dictionary.py", "--dbs", hist, cur, "--study", study, "--out", out, env=env)

    fallback = duckdb.connect(str(hist), read_only=True).execute(
        "SELECT sum(cp1252_lines) FROM raw.load_log"
    )
    assert fallback.fetchone()[0] == 1
    con = duckdb.connect(str(study), read_only=True)
    # 1,500 + 2,500 new cases (100 old ones followed up), case 900001 deleted, one case per caseid
    assert con.execute("SELECT count(*), count(DISTINCT caseid) FROM cases").fetchone()[0] <= 3999
    assert con.execute("SELECT count(*) FROM cases WHERE caseid = '900001'").fetchone()[0] == 0
    # the DQ-038 rule must not drop Canadian cases with no age or weight
    blank = "SELECT count(*) FROM cases WHERE age_years IS NULL AND wt_kg IS NULL"
    assert con.execute(blank).fetchone()[0] > 0
    groups = dict(con.execute("SELECT rq1_group, count(*) FROM cases GROUP BY 1").fetchall())
    assert min(groups[g] for g in ("STIMULANT", "NONSTIMULANT", "MULTI_ADHD_CLASS")) > 0
    splits = dict(con.execute("SELECT split, count(*) FROM rq3_cases GROUP BY 1").fetchall())
    assert splits["TRAIN"] > 0 and splits["TEST"] > 0
    both = "SELECT count(*) FROM (SELECT caseid FROM rq3_cases GROUP BY 1 HAVING count(*) > 1)"
    assert con.execute(both).fetchone()[0] == 0
    study_group = sum(groups[g] for g in ("STIMULANT", "NONSTIMULANT", "MULTI_ADHD_CLASS"))
    assert con.execute("SELECT count(*) FROM rq1_cases").fetchone()[0] == study_group
    counted = con.execute("SELECT sum(cases) FROM rq1_counts").fetchone()[0]
    assert counted == con.execute("SELECT count(*) FROM cases").fetchone()[0]
    periods = {r[0] for r in con.execute("SELECT DISTINCT period FROM rq2_cases").fetchall()}
    assert {"before shortage", "shortage to label change", "after label change"} <= periods
    months = con.execute("SELECT min(month), max(month) FROM rq2_monthly").fetchone()
    assert str(months[0]) >= "2018-01-01" and str(months[1]) <= "2026-02-01"
    assert con.execute("SELECT count(*) FROM rq1_terms").fetchone()[0] > 0
    for table in ("rq1_cases", "rq1_counts", "rq1_terms", "rq2_cases", "rq2_monthly", "rq3_cases"):
        assert (csv / f"{table}.csv").exists()
    dictionary = (out / "data_dictionary.md").read_text(encoding="utf-8")
    assert "## `rq3_cases`" in dictionary and "| `serious_target` |" in dictionary
    assert (out / "data_dictionary.csv").exists()


def test_2012q4_header_aliases(tmp_path):
    """The 2012Q4 DEMO header has ' rept_dt' and OUTC has 'outc_code' (DQ-039)."""
    import importlib.util

    sys.path.insert(0, str(PIPELINE))
    spec = importlib.util.spec_from_file_location("ingest", PIPELINE / "01_ingest.py")
    ingest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ingest)
    con = duckdb.connect()
    con.execute("CREATE SCHEMA raw")
    con.execute(
        "CREATE TABLE raw.load_log (quarter VARCHAR, family VARCHAR, file VARCHAR, "
        "rows BIGINT, cp1252_lines BIGINT)"
    )
    for family, text in (
        ("DEMO", "primaryid$caseid$ rept_dt$sex\n1$1$20121001$F\n"),
        ("OUTC", "primaryid$caseid$outc_code\n1$1$HO\n"),
    ):
        path = tmp_path / f"{family}.txt"
        path.write_text(text, encoding="utf-8")
        assert ingest.load_family(con, family, "2012Q4", path, path.name) == 1
    assert con.execute("SELECT rept_dt FROM raw.demo").fetchone()[0] == "20121001"
    assert con.execute("SELECT outc_cod FROM raw.outc").fetchone()[0] == "HO"
