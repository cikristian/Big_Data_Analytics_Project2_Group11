"""Section 7.1 - concurrent analysts. One engine at a time.

    python loadtest.py --engine pg  --q7 bidir    # all workloads x clients x 3 repetitions
    python loadtest.py --engine neo
    python loadtest.py --summary                  # summary table from the raw logs
Workloads: Q4 depth 10 and Q7 length-only bound 6, cycling sets A-B-C.
Each client: own persistent connection, one untimed A-B-C warm-up, Barrier, then
cycles until 15 s after release (a started cycle is finished). 60 s query timeout.
Correctness is checked after timing against results/reference_answers.json.
"""
import argparse
import csv
import glob
import json
import math
import multiprocessing as mp
import os
import statistics
import time

from config import SETS

CLIENTS = tuple(int(x) for x in os.environ.get("MM_CLIENTS", "1,4,8,16").split(","))
REPS = int(os.environ.get("MM_REPS", "3"))
WINDOW = 15.0
TIMEOUT = 60
CYCLE = ("A", "B", "C")


def make_request(workload, letter, q7):
    from queries import Q4_SQL, Q7_SQL, Q7_SQL_BIDIR, q4_cypher, q7_cypher
    acc, dest, _ = SETS[letter]
    if workload == "Q4d10":
        return f"Q4-{letter}-d10", "Q4", Q4_SQL, q4_cypher(10), {"account": acc, "depth": 10}
    sql = Q7_SQL_BIDIR if q7 == "bidir" else Q7_SQL
    return f"Q7-{letter}-b6", "Q7", sql, q7_cypher(6), {"source": acc, "dest": dest, "bound": 6}


def worker(engine, workload, q7, barrier, t0, out_q, cid):
    import db
    run = db.run_pg if engine == "pg" else db.run_neo
    reqs = [make_request(workload, s, q7) for s in CYCLE]
    for _, _, sql, cy, p in reqs:                       # warm-up A-B-C once
        try:
            run(sql if engine == "pg" else cy, p, timeout_s=TIMEOUT)
        except Exception:
            pass
    barrier.wait()                                      # synchronized start
    start = t0.value
    deadline = start + WINDOW
    log, cycle_no = [], 0
    while time.time() < deadline:                       # start cycles until the deadline
        cycle_no += 1
        for case, q, sql, cy, p in reqs:                # finish any started cycle
            s = time.time()
            status, rows = "ok", None
            try:
                rows = run(sql if engine == "pg" else cy, p, timeout_s=TIMEOUT)
            except Exception as e:
                txt = f"{type(e).__name__} {e}".lower()
                status = "timeout" if any(k in txt for k in ("timeout", "timedout", "cancel", "terminated")) else "error"
            e = time.time()
            log.append(dict(client=cid, cycle=cycle_no, case=case, q=q, start=s, end=e,
                            latency_ms=(e - s) * 1000, status=status,
                            rows=[list(r) for r in rows] if rows is not None else None))
    out_q.put(log)


def one_test(engine, workload, q7, n, rep, ref):
    from db import normalize
    t0 = mp.Value("d", 0.0)          # common start time, set by the first released client
    barrier = mp.Barrier(n)
    q = mp.Queue()
    procs = [mp.Process(target=_worker_entry, args=(engine, workload, q7, barrier, t0, q, i))
             for i in range(n)]
    for p in procs:
        p.start()
    logs = []
    for _ in procs:
        logs += q.get()
    for p in procs:
        p.join()
    start = t0.value
    finish = max(r["end"] for r in logs) if logs else start
    for r in logs:
        r["correct"] = (r["status"] == "ok" and
                        normalize([tuple(x) for x in r["rows"]], r["q"]) ==
                        normalize([tuple(x) for x in ref[r["case"]]], r["q"]))
        r.pop("rows")
    good = sorted(r["latency_ms"] for r in logs if r["status"] == "ok")
    correct = sum(r["correct"] for r in logs)
    elapsed = finish - start
    res = dict(engine=engine, workload=workload, q7_sql=q7 if workload == "Q7b6" else "-",
               clients=n, rep=rep, requests=len(logs), correct=correct,
               elapsed_s=round(elapsed, 3),
               throughput_rps=round(correct / elapsed, 3) if elapsed > 0 else 0,
               median_ms=round(statistics.median(good), 2) if good else None,
               p95_ms=round(good[math.ceil(0.95 * len(good)) - 1], 2) if good else None,
               errors=sum(r["status"] == "error" for r in logs),
               timeouts=sum(r["status"] == "timeout" for r in logs),
               wrong=sum(r["status"] == "ok" and not r["correct"] for r in logs))
    return res, logs


def _worker_entry(engine, workload, q7, barrier, t0, q, cid):
    class _Release:
        """Barrier wait that records one shared start time at release."""
        def wait(self):
            if barrier.wait() == 0:
                t0.value = time.time()
            while t0.value == 0.0:      # others wait until the start is published
                time.sleep(0.0005)
    worker(engine, workload, q7, _Release(), t0, q, cid)


def run_all(engine, q7):
    ref = json.load(open("results/reference_answers.json"))
    os.makedirs("results/loadtest", exist_ok=True)
    summary_path = f"results/loadtest/summary_{engine}.csv"
    with open(summary_path, "w", newline="") as f:
        w = None
        for workload in ("Q4d10", "Q7b6"):
            for n in CLIENTS:
                for rep in range(1, REPS + 1):
                    res, logs = one_test(engine, workload, q7, n, rep, ref)
                    with open(f"results/loadtest/raw_{engine}_{workload}_c{n}_r{rep}.csv", "w", newline="") as g:
                        dw = csv.DictWriter(g, fieldnames=list(logs[0].keys()))
                        dw.writeheader()
                        dw.writerows(logs)
                    if w is None:
                        w = csv.DictWriter(f, fieldnames=list(res.keys()))
                        w.writeheader()
                    w.writerow(res)
                    f.flush()
                    print(res, flush=True)
    print("Saved", summary_path)


def summary():
    rows = []
    for p in glob.glob("results/loadtest/summary_*.csv"):
        rows += list(csv.DictReader(open(p)))
    groups = {}
    for r in rows:
        groups.setdefault((r["engine"], r["workload"], int(r["clients"])), []).append(r)
    hdr = ["engine", "workload", "clients", "throughput_rps", "median_ms", "p95_ms", "errors", "timeouts", "wrong"]
    out = []
    for (e, wl, n), rs in sorted(groups.items()):
        med = lambda k: statistics.median(float(r[k]) for r in rs if r[k] not in ("", "None"))
        out.append([e, wl, n, round(med("throughput_rps"), 2), round(med("median_ms"), 1),
                    round(med("p95_ms"), 1), int(med("errors")), int(med("timeouts")), int(med("wrong"))])
    with open("results/loadtest/combined_summary.csv", "w", newline="") as f:
        csv.writer(f).writerows([hdr] + out)
    print(" | ".join(hdr))
    for r in out:
        print(" | ".join(map(str, r)))
    print("Saved results/loadtest/combined_summary.csv (median of the 3 repetitions)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["pg", "neo"])
    ap.add_argument("--q7", choices=["baseline", "bidir"], default="bidir",
                    help="SQL version selected in section 6.3")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    summary() if a.summary else run_all(a.engine, a.q7)
