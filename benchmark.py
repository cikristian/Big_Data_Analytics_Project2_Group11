"""Section 6.2 / 6.3 - time the fixed 21-case selection on ONE engine at a time.

    python benchmark.py --engine pg                        # PostgreSQL, baseline Q7
    python benchmark.py --engine neo                       # Neo4j
    python benchmark.py --engine pg --q7 bidir --only Q7   # 6.3: four revised SQL cases
    python benchmark.py --summary                          # combine all raw files

Stop the other database service before timing. Three untimed warm-ups (180 s
limit) then five measured runs (60 s limit). Errors/timeouts are recorded with
their status and never counted as completed timings. Answers are compared with
the reference outside the timer.
"""
import argparse
import csv
import glob
import json
import os
import statistics
from datetime import datetime
from time import perf_counter

from config import CAT
from db import normalize, run_neo, run_pg
from queries import Q7_SQL, Q7_SQL_BIDIR, timing_cases

WARMUPS, RUNS, WARM_LIMIT, RUN_LIMIT = 3, 5, 180, 60


def classify(exc):
    text = f"{type(exc).__name__} {exc}".lower()
    return "timeout" if any(k in text for k in ("timeout", "timedout", "cancel", "terminated")) else "error"


def bench(engine, q7, only):
    wrapper = run_pg if engine == "pg" else run_neo
    ref = json.load(open("results/reference_answers.json")) if os.path.exists("results/reference_answers.json") else {}
    cases = timing_cases(Q7_SQL if q7 == "baseline" else Q7_SQL_BIDIR)
    if only:
        cases = [c for c in cases if c["q"] in only]
    tag = f"{engine}_{q7}" + (f"_{'-'.join(only)}" if only else "")
    os.makedirs("results", exist_ok=True)
    path = f"results/bench_raw_{tag}.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "params", "engine", "q7_sql", "run", "start_cat", "duration_ms", "rows", "status", "correct"])
        for c in cases:
            query = c["sql"] if engine == "pg" else c["cypher"]
            for i in range(WARMUPS):
                try:
                    wrapper(query, c["params"], timeout_s=WARM_LIMIT)
                except Exception as e:
                    print(f"  warm-up {i + 1} {c['id']}: {classify(e)}")
            for run in range(1, RUNS + 1):
                start_cat = datetime.now(CAT).isoformat(timespec="seconds")
                rows, status = None, "ok"
                start = perf_counter()
                try:
                    rows = wrapper(query, c["params"], timeout_s=RUN_LIMIT)   # consumes all rows
                    duration = perf_counter() - start
                except Exception as e:
                    duration, status = perf_counter() - start, classify(e)
                correct = ""
                if rows is not None and c["id"] in ref:          # outside the timer
                    correct = normalize(rows, c["q"]) == normalize([tuple(x) for x in ref[c["id"]]], c["q"])
                w.writerow([c["id"], json.dumps(c["params"]), engine, q7, run, start_cat,
                            round(duration * 1000, 3) if status == "ok" else "",
                            len(rows) if rows is not None else "", status, correct])
                f.flush()
                print(f"{engine} {c['id']:10s} run {run}: "
                      f"{duration * 1000:10.1f} ms {status} correct={correct}", flush=True)
    print("Saved", path)


def summary():
    rows = []
    for p in glob.glob("results/bench_raw_*.csv"):
        rows += list(csv.DictReader(open(p)))
    groups = {}
    for r in rows:
        key = (r["case"], r["engine"], r["q7_sql"] if r["case"].startswith("Q7") else "-")
        groups.setdefault(key, []).append(r)
    stats = {}
    for key, rs in groups.items():
        ok = [float(r["duration_ms"]) for r in rs if r["status"] == "ok"]
        stats[key] = dict(n_ok=len(ok), n_timeout=sum(r["status"] == "timeout" for r in rs),
                          n_error=sum(r["status"] == "error" for r in rs),
                          median=statistics.median(ok) if ok else None,
                          min=min(ok) if ok else None, max=max(ok) if ok else None)
    out = []
    for (case, engine, ver), s in sorted(stats.items()):
        if engine != "pg":
            continue
        neo = stats.get((case, "neo", "-")) or stats.get((case, "neo", "baseline")) or {}
        ratio = (s["median"] / neo["median"]) if s["median"] and neo.get("median") else None
        out.append([case, ver, s["median"], s["min"], s["max"], s["n_timeout"], s["n_error"],
                    neo.get("median"), neo.get("min"), neo.get("max"), ratio])
    hdr = ["case", "sql_version", "pg_median_ms", "pg_min_ms", "pg_max_ms", "pg_timeouts", "pg_errors",
           "neo_median_ms", "neo_min_ms", "neo_max_ms", "pg_over_neo_median"]
    with open("results/bench_summary.csv", "w", newline="") as f:
        csv.writer(f).writerows([hdr] + out)
    fmt = lambda v: "-" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))
    print(" | ".join(hdr))
    for r in out:
        print(" | ".join(fmt(v) for v in r))
    print("Saved results/bench_summary.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["pg", "neo"])
    ap.add_argument("--q7", choices=["baseline", "bidir"], default="baseline")
    ap.add_argument("--only", nargs="*", help="e.g. --only Q7")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    summary() if a.summary else bench(a.engine, a.q7, a.only)
