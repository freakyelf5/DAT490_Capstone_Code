# Ingestion rules

Code: [`pipeline/01_ingest.py`](../pipeline/01_ingest.py)

FDA publishes FAERS as one ZIP per quarter (`faers_ascii_YYYYqN.zip`). Each ZIP holds
seven `$`-delimited text files and, from 2019 on, a list of deleted case numbers. The
project uses 55 quarters, 2012Q4 to 2026Q2, in two DuckDB databases.

| Rule | What the code does | Why |
|---|---|---|
| Two databases (DQD-024, DQD-039) | 2012Q4-2021Q4 load into `historical.duckdb`, 2022Q1-2026Q2 into `current.duckdb`. They are combined only when the case table is built ([case selection](case_selection.md#rule-x1-two-databases-one-series)). | FDA changed systems and file layouts over time; keeping the eras apart makes each easy to check on its own. |
| Raw values kept as text (DQ-023) | Every column is read as text. Nothing is trimmed, recoded or guessed; quote characters are kept as data. A row with the wrong number of fields stops the load. | Cleaning happens later in new columns, so the raw data can always be compared with FDA's files. |
| Load metadata | Each row gets `source_quarter` and `line_no` (its line in the file). | The case rule uses them to choose between copies of the same report. |
| One quarter at a time | A quarter loads inside one transaction: all seven files or nothing. Quarters already in `raw.load_log` are skipped. | A failed load never leaves half a quarter behind. |
| File names (DQ-033) | Files are found by FDA's standard names (`DEMO12Q4.txt` ...). The one exception, 2018Q1 `DEMO18Q1_new.txt`, is listed in the code. Deleted-case lists are recognized under every name FDA used (`DELETE19Q1.txt`, `ADR19Q1DeletedCases.txt`, `AllDeletedCases.txt` ...). A missing file stops the quarter. | Found by surveying every ZIP before loading. Without the deleted-list names, deleted cases would have stayed in. |
| Header names over time (DQ-032) | Columns are matched by name. A field FDA added later (for example `prod_ai` in 2014Q3) becomes a new column, empty for earlier quarters. | Older files have fewer fields; nothing is shifted or invented. |
| 2012Q4 header spellings (DQ-039) | Three 2012Q4 header names are read with the later spelling: DEMO ` rept_dt` (leading space), DRUG `lot_nbr` to `lot_num`, OUTC `outc_code` to `outc_cod`. Values are unchanged. | Without it the first FAERS quarter cannot be stacked with the rest. |
| Text encoding (DQ-034) | Files are read as UTF-8. A file that is not valid UTF-8 is rewritten line by line, and only the lines that fail UTF-8 are read as Windows-1252. The number of such lines is recorded in `raw.load_log.cp1252_lines`. | FDA's 2019Q3 DRUG file has 5 such lines; no other quarter has any. |
| Deleted-case lists (DQ-006, rule D3) | One case number per line. Only lines that are digits and nothing else count; they go to `raw.deleted`. | FDA's 2020Q1 list has 26 numbers followed by a tab; the rule leaves those unparsed, as the full pipeline did. |
