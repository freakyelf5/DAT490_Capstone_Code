# DAT490_Capstone_Code

Dat A Project - Code Deliverable

Source code for the DAT 490 capstone project on adverse event reports for ADHD
medicines in the FDA Adverse Event Reporting System (FAERS). It turns FDA's public
quarterly files (2012Q4 to 2026Q2, 55 quarters) into clean, documented datasets for
the three research questions:

- **RQ1:** Do stimulant and nonstimulant ADHD medicines differ in reported
  cardiovascular, psychiatric and dependence-related events, by age and sex?
- **RQ2:** Did reporting change after the October 2022 Adderall shortage and the May
  2023 FDA stimulant labeling update?
- **RQ3:** Can demographics, drug class, dose, route and other medicines predict a
  serious outcome, and how do statistical and machine-learning models compare?

This repository covers the data work (ingestion, verification, munging, the
research-question datasets, the data dictionary and the rules behind them) in
`pipeline/`, and the team's EDA, analysis and visualization notebooks in
[`Colab_Notebooks/`](#colab-notebooks).

## What is in the repository

| Stage | Script | What it does | Rules |
|---|---|---|---|
| 1. Ingestion | [`pipeline/01_ingest.py`](pipeline/01_ingest.py) | Loads each quarter's seven files and FDA's deleted-case lists into DuckDB, every value kept as text | [Ingestion](rules/ingestion.md) |
| 2. Verification | [`pipeline/02_verify.py`](pipeline/02_verify.py) | Recounts every file's lines from the ZIP, checks keys, applies the case rule and reports raw vs kept counts | [Verification](rules/verification.md) |
| 3. Munging | [`pipeline/03_munge.py`](pipeline/03_munge.py) | Newest version of each case, deleted cases removed, both databases combined, age/sex/weight cleaned, ADHD medicines matched, study groups, event and outcome flags | [Case selection](rules/case_selection.md), [demographics](rules/demographics.md), [drug map](rules/adhd_drug_map.md), [indication](rules/adhd_indication.md), [study groups](rules/study_groups.md), [event groups](rules/event_groups.md) |
| 4. Research-question datasets | [`pipeline/04_rq_datasets.py`](pipeline/04_rq_datasets.py) | Builds the RQ1, RQ2 and RQ3 tables (and CSV copies on request) | [RQ datasets](rules/rq_datasets.md) |
| 5. Data dictionary | [`pipeline/05_dictionary.py`](pipeline/05_dictionary.py) | Checks that every column has a definition of the right type and publishes the dictionary | [Data dictionary](dictionary/data_dictionary.md) |
| Shared | [`pipeline/common.py`](pipeline/common.py) | Settings, rule-table readers, the drug-name matcher and the case-selection SQL | |

Other folders:

| Folder | Contents |
|---|---|
| [`rules/`](rules/README.md) | One document per rule, with its project ID, and [`rules/tables/`](rules/tables/), the reviewed rule tables the code reads (drug map, indication terms, event term groups, age/sex/weight units) |
| [`dictionary/`](dictionary/data_dictionary.md) | [`definitions.csv`](dictionary/definitions.csv) (written by hand) and the generated [`data_dictionary.md`](dictionary/data_dictionary.md) and [`data_dictionary.csv`](dictionary/data_dictionary.csv) |
| [`docs/`](docs/verification_results.md) | [Verification results](docs/verification_results.md): raw and kept counts for every quarter and the final study counts |
| [`tests/`](tests/test_pipeline.py) | An end-to-end test that runs all five scripts on small synthetic quarters |
| [`Colab_Notebooks/`](#colab-notebooks) | The team's Google Colab notebooks: shared setup, EDA, and analysis and visualizations for each research question |

## Rules

Every rule is listed, with its ID, in [`rules/README.md`](rules/README.md):

- [Ingestion rules](rules/ingestion.md): file names, header spellings, text encoding, deleted-case lists (DQ-023, DQ-032, DQ-033, DQ-034, DQ-039)
- [Verification rules](rules/verification.md): row recounts, key checks, raw vs kept counts (DQ-003, DQ-023, DQ-025, DQ-035)
- [Case selection](rules/case_selection.md): newest version per case, FDA deletions, combining the two databases, the repeat-reported patient (D1-D6, DQ-005, DQ-006, X1, DQ-038)
- [Age, sex and weight](rules/demographics.md) (DQ-012)
- [ADHD drug map](rules/adhd_drug_map.md) (DQ-015)
- [ADHD indication](rules/adhd_indication.md) (DQ-016)
- [Study groups](rules/study_groups.md) (DQ-019)
- [Event groups](rules/event_groups.md) (DQ-017)
- [Research-question datasets](rules/rq_datasets.md) (DQ-018, DQ-020, DQ-021, DQ-037)
- [Known limitations kept in the data](rules/README.md#known-limitations-kept-in-the-data) (DQ-008, DQ-026, DQ-036)

## How to run it

Python 3.12 or later with DuckDB 1.4.5 (`pip install -r requirements.txt`). Download
FDA's quarterly ASCII ZIPs (`faers_ascii_2012q4.zip` ... `faers_ascii_2026q2.zip`)
from the [FAERS quarterly data page](https://fis.fda.gov/extensions/FPD-QDE-FAERS/FPD-QDE-FAERS.html)
into one folder (`ZIPS` below). Then, from the `pipeline` folder:

```bash
cd pipeline
python 01_ingest.py --zips ZIPS --db historical.duckdb --start 2012Q4 --end 2021Q4
python 01_ingest.py --zips ZIPS --db current.duckdb    --start 2022Q1 --end 2026Q2
python 02_verify.py --db historical.duckdb --zips ZIPS
python 02_verify.py --db current.duckdb    --zips ZIPS
python 03_munge.py --dbs historical.duckdb current.duckdb --out study.duckdb
python 04_rq_datasets.py --dbs historical.duckdb current.duckdb --study study.duckdb --csv ../csv
python 05_dictionary.py --dbs historical.duckdb current.duckdb --study study.duckdb --stats
```

Loading all 55 quarters is the slow step (the ZIPs are about 3 GB); the others take
minutes. Verification results go to `results/`, and the RQ tables to `csv/` when
`--csv` is given; both folders, the ZIPs and the databases stay out of Git.

`05_dictionary.py` with no arguments rebuilds the dictionary from `definitions.csv`
alone. With the databases it first checks every column, and with `--stats` it adds
how many rows fill each column.

## Output

`study.duckdb` holds these tables (full column list in the
[data dictionary](dictionary/data_dictionary.md)):

| Table | Grain | Used for |
|---|---|---|
| `drug_classes` | Distinct drug name and ingredient pair that is an ADHD medicine | Drug matching |
| `cases` | Kept case, 2012Q4-2026Q2, both databases combined | Source of every RQ table |
| `rq1_cases`, `rq1_counts`, `rq1_terms` | Study-group case; count cell; reaction term | RQ1 |
| `rq2_cases`, `rq2_monthly` | Study-group case; group and month | RQ2 |
| `rq3_cases` | Study-group case of 2022-2026 with its TRAIN/TEST split | RQ3 |

The raw tables (`raw.demo`, `raw.drug` ...) stay in `historical.duckdb` and
`current.duckdb`, unchanged.

## Testing

```bash
pip install -r requirements.txt
python -m pytest
```

[`tests/test_pipeline.py`](tests/test_pipeline.py) writes three small synthetic FDA
quarters (with follow-up versions, a case in both databases, a deleted case, a
Windows-1252 line and Canadian cases with no age or weight), runs all five scripts and
checks the case rule, the study groups, the RQ tables, the time split and the
dictionary. [`tests/test_docs.py`](tests/test_docs.py) checks that every rule document
is linked from this README, every relative link works, and the published dictionary
matches `definitions.csv`. A third test checks the 2012Q4 header spellings.

## Colab notebooks

The team's notebooks, run in Google Colab. They read the project's shared ADHD study
data on MotherDuck (the `faers_adhd_study` database and the
`Capstone_faers_adhd_data_only` share: the 94,803 study-group cases built with the
rules above), so they need a MotherDuck account or token, which is entered when the
notebook runs and is never stored in this repository. Run `00` first for the shared
definitions, then the notebooks for each question. Saved outputs and charts are kept,
so each notebook can be read without running it.

| Notebook | What it covers |
|---|---|
| [00 - Data Setup](Colab_Notebooks/00%20-%20Data%20Setup.ipynb) | General setup shared by all three questions: how ADHD medicines were identified (the drug map and indication rules) and which reaction terms count in each event group, with an EDA of each selection. |
| [01 - RQ1 - EDA](Colab_Notebooks/01%20-%20RQ1%20-%20EDA.ipynb) | RQ1 exploratory analysis: the variables used, missing age and sex, and how cardiovascular, psychiatric and dependence-related events are distributed across stimulant and nonstimulant cases by age and sex, with findings. |
| [01 - RQ2 - EDA](Colab_Notebooks/01%20-%20RQ2%20-%20EDA.ipynb) | RQ2 exploratory analysis and proposed method: the receipt-month timeline, reporting volume, and each RQ2 event group before and after the October 2022 shortage and the May 2023 labeling change. |
| [01 - RQ3 - EDA](Colab_Notebooks/01%20-%20RQ3%20-%20EDA.ipynb) | RQ3 exploratory analysis of the 2022-2026 cases: the serious-outcome target, each predictor (demographics, drug class, dose, route, other medicines), a timeline check and a leakage check. |
| [02 - RQ1 Visualizations and Analysis](Colab_Notebooks/02%20-%20RQ1%20Visualizations%20and%20Analysis.ipynb) | RQ1 analysis and charts: data preparation and encoding, a train/test/validation split, and logistic regression, decision tree and support vector machine models compared on stimulant vs nonstimulant event patterns. |
| [02 - RQ2 Visualizations and Analysis](Colab_Notebooks/02%20-%20RQ2%20Visualizations%20and%20Analysis.ipynb) | RQ2 analysis and charts: monthly reporting from January 2018 to February 2026, the effect of bulk submissions, and event shares before, between and after the shortage and labeling change, with statistical tests. |
| [02 - RQ3 Visualizations and Analysis](Colab_Notebooks/02%20-%20RQ3%20Visualizations%20and%20Analysis.ipynb) | RQ3 analysis and charts: the time-based train/test split, baselines, logistic regression and lasso, random forest and gradient-boosted trees predicting a serious outcome, compared by ROC AUC, calibration, precision-recall and feature importance. |

## Data source

FDA Adverse Event Reporting System (FAERS) quarterly data extract files, public
domain. FAERS holds voluntary reports, so results describe reporting patterns, not
how often events happen.

## License

[GNU GPL v3](LICENSE).
