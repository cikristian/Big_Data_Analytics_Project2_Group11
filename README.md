# Mobile Money Investigations with PostgreSQL and Neo4j (Project 2)

Group: `<names and student IDs>`  ·  Repository: `<GitHub URL>`

All commands run from this folder, in this order. CSVs and database stores stay
local (`data/` is git-ignored). Secrets are placeholders: set them as environment
variables, never in the code.

## 0. Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python verify_generator.py      # must print: Generator unchanged: True
```

Connection settings (`config.py` reads these; defaults are placeholders):

```bash
# Windows PowerShell
$env:MM_PG_DSN = "host=localhost port=5432 dbname=mobile_money user=postgres password=<pg password>"
$env:MM_NEO4J_PASSWORD = "<neo4j password>"
$env:NEO4J_HOME = "C:\neo4j\neo4j-community-<version>"
# macOS/Linux: export MM_PG_DSN="..."  etc.
```

Recommended fixed resource settings (record whatever you use):
- PostgreSQL `postgresql.conf`: `shared_buffers = 2GB`, `work_mem = 64MB`, `maintenance_work_mem = 1GB`, `max_wal_size = 8GB`, `timezone = 'Africa/Kigali'`
- Neo4j `conf/neo4j.conf`: `server.memory.heap.initial_size=2g`, `server.memory.heap.max_size=2g`, `server.memory.pagecache.size=3g`
  (adjust to your RAM; keep them the same for every timed run)

## 1. Workspace and capture (sections 1.1–1.2)

```bash
createdb -U postgres mobile_money                      # or CREATE DATABASE in pgAdmin/psql
python env_info.py                                     # versions, CPU, RAM, OS, memory settings
python capture.py --preview                            # dataset_info, FIELDS, 10 rows per stream
python capture.py                                      # writes data/*.csv + results/capture_audit.json
```

## 2. PostgreSQL (sections 2.1–2.2)

```bash
psql -U postgres -d mobile_money -f sql/01_schema.sql
psql -U postgres -d mobile_money -f sql/02_load.sql                 # load seconds (\timing)
psql -U postgres -d mobile_money -f sql/03_constraints_indexes.sql  # constraint/index seconds
psql -U postgres -d mobile_money -f sql/04_checks.sql               # counts, audit, roles, constraints, indexes, sizes
psql -U postgres -d mobile_money -c "\d+ transfers"                 # definitions screenshot
```

## 3. Neo4j (sections 3.1–3.3)

```bash
# Neo4j must be STOPPED for the full import:  %NEO4J_HOME%\bin\neo4j stop
python prepare_import.py --run          # typed copies in data/import/, owns.csv, then neo4j-admin import (timed)
# start Neo4j:  %NEO4J_HOME%\bin\neo4j console   (or neo4j start / Neo4j Desktop)
python neo4j_checks.py --setup          # constraints + TRANSFER.occurred_at range index, waits online, times it
python neo4j_checks.py                  # node/relationship counts, roles, owners, unique transfer_id, audit, sizes
python prepare_import.py --cleanup      # remove temporary import copies (after the checks screenshot)
python inspect_account.py 998           # section 3.3: same account traced with JOINs and MATCH
```

## 4. Questions Q1–Q7 and correctness (sections 4, 5, 6.1)

All query pairs are in `queries.py` (`Q1_SQL` / `Q1_CYPHER`, … `Q7_SQL`, `Q7_SQL_BIDIR`).

```bash
python reference.py                     # independent pandas answers from the CSVs (third opinion)
python compare.py                       # 61 cases on both engines + Q7 path verification (baseline SQL)
python verify_csv.py                    # one device overlap + one chain + one cycle checked against CSV rows
```

## 5. Timing (sections 6.2–6.3) — one database service running at a time

```bash
# stop Neo4j, PostgreSQL running:
python benchmark.py --engine pg
python benchmark.py --engine pg --q7 bidir --only Q7     # 6.3: four revised SQL cases
python plans.py --engine pg
python compare.py --q7 bidir                             # 6.3: recheck 12 Q7 cases (needs both engines)
# stop PostgreSQL, start Neo4j:
python benchmark.py --engine neo
python plans.py --engine neo
python benchmark.py --summary                            # results/bench_summary.csv (median/min/max, ratio)
```

## 6. Concurrency (section 7) — one engine at a time

```bash
python loadtest.py --engine pg --q7 bidir   # Q4 d10 and Q7 b6 x 1/4/8/16 clients x 3 repetitions
python loadtest.py --engine neo
python loadtest.py --summary
python plots.py                              # all charts into results/charts/
```

## 7. Final verification (section 9.2)

```bash
python compare.py --q7 bidir                 # rerun the submitted 61-case comparison
pg_ctl stop -D "<PGDATA>"   (or stop the Windows service)    &&    %NEO4J_HOME%\bin\neo4j stop
```

## Files

| File | Purpose |
|---|---|
| `mobile_money_generator.py` | supplied generator, unchanged (`verify_generator.py`) |
| `config.py` | connection placeholders, investigation sets, CAT hour boundaries |
| `capture.py` | streams the five generators to CSV with audit totals |
| `sql/01–04_*.sql` | schema, bulk load, constraints + indexes, checks |
| `prepare_import.py`, `neo4j_checks.py`, `cypher/neo4j_setup.cypher` | Neo4j import and verification |
| `queries.py` | Q1–Q7 SQL/Cypher pairs, improved Q7 SQL, 61 + 21 case lists |
| `db.py` | `run_pg`, `run_neo`, result normalization |
| `reference.py`, `compare.py`, `verify_csv.py` | correctness |
| `benchmark.py`, `plans.py`, `loadtest.py`, `plots.py` | performance, plans, concurrency, charts |
| `results/` | raw timings, plans, load-test logs, comparison outputs, charts |
