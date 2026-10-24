"""Section 6.1 (and 6.3 recheck, 9.2 rerun) - run all 61 cases on both engines,
normalize, compare exactly, then verify every Q7 supporting path.

    python compare.py                    # baseline SQL for Q7
    python compare.py --q7 bidir         # improved SQL (section 6.3)
Outputs: printed 61-case status table, results/compare_<tag>.json (full outputs).
If results/reference_answers.json exists (python reference.py), it is used as a
third, database-independent opinion.
"""
import argparse
import json
import os
import time

from config import SETS, cat
from db import normalize, run_neo, run_pg
from queries import (Q7_SQL, Q7_SQL_BIDIR, Q7_VERIFY_HOP_SQL, Q4_PATH_CYPHER_TEMPLATE,
                     build_cases, q7_cypher)


def verify_path(accounts, transfer_ids, length, source, dest):
    """Check a Neo4j path against PostgreSQL rows: IDs, direction, roles, events, length."""
    problems = []
    if accounts[0] != source or accounts[-1] != dest:
        problems.append("endpoints")
    if len(transfer_ids) != length or len(accounts) != length + 1:
        problems.append("length")
    for i, tid in enumerate(transfer_ids):
        rows = run_pg(Q7_VERIFY_HOP_SQL, {"transfer_id": tid})
        if not rows:
            problems.append(f"transfer {tid} missing")
            continue
        _, s, r, srole, rrole = rows[0]
        if (s, r) != (accounts[i], accounts[i + 1]):
            problems.append(f"transfer {tid} direction")
        if srole != "person" or rrole != "person":
            problems.append(f"transfer {tid} role")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q7", choices=["baseline", "bidir"], default="baseline")
    args = ap.parse_args()
    q7_sql = Q7_SQL if args.q7 == "baseline" else Q7_SQL_BIDIR
    ref = {}
    if os.path.exists("results/reference_answers.json"):
        ref = json.load(open("results/reference_answers.json"))

    status, full = [], {}
    print(f"{'case':12s} {'PG rows':>7s} {'Neo rows':>8s} {'PG ms':>9s} {'Neo ms':>9s}  PG=Neo  ref  status")
    for c in build_cases(q7_sql):
        t0 = time.perf_counter(); pg = normalize(run_pg(c["sql"], c["params"]), c["q"]); tp = time.perf_counter() - t0
        t0 = time.perf_counter(); neo = normalize(run_neo(c["cypher"], c["params"]), c["q"]); tn = time.perf_counter() - t0
        same = pg == neo
        r_ok = None
        if c["id"] in ref:
            r_ok = normalize([tuple(x) for x in ref[c["id"]]], c["q"]) == pg
        ok = same and r_ok is not False
        status.append(dict(case=c["id"], pg_rows=len(pg), neo_rows=len(neo), match=same,
                           reference_match=r_ok, status="OK" if ok else "MISMATCH"))
        full[c["id"]] = dict(params=c["params"], postgres=pg, neo4j=neo)
        print(f"{c['id']:12s} {len(pg):7d} {len(neo):8d} {tp*1000:9.1f} {tn*1000:9.1f}  "
              f"{str(same):6s} {str(r_ok):5s} {'OK' if ok else 'MISMATCH'}", flush=True)

    # Q7 supporting paths (separate from length comparison)
    print("\nQ7 supporting paths (Neo4j path verified against PostgreSQL rows)")
    paths = {}
    for s, (src, dst, _) in SETS.items():
        for b in (4, 6):
            rows = run_neo(q7_cypher(b, path=True), {"source": src, "dest": dst})
            if not rows:
                print(f"Q7-{s}-b{b}: no route within {b}")
                paths[f"Q7-{s}-b{b}"] = None
                continue
            accounts, tids, length = rows[0]
            probs = verify_path(list(accounts), list(tids), length, src, dst)
            paths[f"Q7-{s}-b{b}"] = dict(accounts=list(accounts), transfer_ids=list(tids),
                                         length=length, problems=probs)
            print(f"Q7-{s}-b{b}: length {length} accounts {list(accounts)} transfers {list(tids)} "
                  f"-> {'VALID' if not probs else probs}")

    # One Q4 supporting path: first account reached at depth 4 for set A
    a = SETS["A"][0]
    other = run_neo("MATCH (a:Account {account_id:$a})-[:OWNS|USED_DEVICE*1..4]-(b:Account) "
                    "WHERE b <> a RETURN DISTINCT b.account_id ORDER BY b.account_id DESC LIMIT 1", {"a": a})
    if other:
        p = run_neo(Q4_PATH_CYPHER_TEMPLATE % 10, {"account": a, "other": other[0][0]})
        print(f"\nQ4 supporting path from {a} to {other[0][0]}: {p}")
        paths["Q4-A-example"] = [list(x) for x in p[0]] if p else None

    n_ok = sum(s["status"] == "OK" for s in status)
    print(f"\n{n_ok}/61 cases match. Q7 SQL version: {args.q7}")
    os.makedirs("results", exist_ok=True)
    with open(f"results/compare_{args.q7}.json", "w") as f:
        json.dump(dict(status=status, outputs=full, paths=paths), f, indent=1, default=str)
    print(f"Saved results/compare_{args.q7}.json")


if __name__ == "__main__":
    main()
