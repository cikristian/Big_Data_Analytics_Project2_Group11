"""Section 6.2/6.3 - collect execution plans outside timing.

    python plans.py --engine pg      # EXPLAIN (ANALYZE, BUFFERS): Q2, Q4 B d10, Q7 B b6 (baseline + bidir)
    python plans.py --engine neo     # PROFILE for the same three cases
Writes results/plans/<engine>_<case>.txt
"""
import argparse
import os

from config import SETS
from db import neo_driver, pg_conn
from queries import Q2_CYPHER, Q2_SQL, Q4_SQL, Q7_SQL, Q7_SQL_BIDIR, q4_cypher, q7_cypher

B_ACC, B_DEST, _ = SETS["B"]
PLAN_CASES = [
    ("Q2", Q2_SQL, Q2_CYPHER, {}),
    ("Q4-B-d10", Q4_SQL, q4_cypher(10), {"account": B_ACC, "depth": 10}),
    ("Q7-B-b6", Q7_SQL, q7_cypher(6), {"source": B_ACC, "dest": B_DEST, "bound": 6}),
    ("Q7-B-b6-bidir", Q7_SQL_BIDIR, None, {"source": B_ACC, "dest": B_DEST, "bound": 6}),
]


def pg_plans():
    conn = pg_conn()
    for name, sql, _, params in PLAN_CASES:
        with conn.cursor() as cur:
            cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql.strip().rstrip(";"), params)
            text = "\n".join(r[0] for r in cur.fetchall())
        save(f"pg_{name}", text)


def fmt_profile(p, depth=0):
    args = p.get("args", {})
    line = (f"{'  ' * depth}+{p.get('operatorType')}  rows={p.get('rows')}  dbHits={p.get('dbHits')}"
            f"  pageHits={p.get('pageCacheHits', '')}  time={args.get('Time', '')}"
            f"  details={args.get('Details', '')}")
    lines = [line]
    for child in p.get("children", []):
        lines += fmt_profile(child, depth + 1)
    return lines


def neo_plans():
    with neo_driver().session(database="neo4j") as s:
        for name, _, cypher, params in PLAN_CASES:
            if cypher is None:
                continue
            res = s.run("PROFILE " + cypher, params)
            list(res)
            summary = res.consume()
            prof = summary.profile
            total = 0
            def hits(p):
                return p.get("dbHits", 0) + sum(hits(c) for c in p.get("children", []))
            total = hits(prof)
            head = (f"Total dbHits: {total}  result available after "
                    f"{summary.result_available_after} ms, consumed after {summary.result_consumed_after} ms")
            save(f"neo_{name}", head + "\n" + "\n".join(fmt_profile(prof)))


def save(name, text):
    os.makedirs("results/plans", exist_ok=True)
    with open(f"results/plans/{name}.txt", "w") as f:
        f.write(text)
    print(f"===== {name} =====\n{text}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["pg", "neo"], required=True)
    pg_plans() if ap.parse_args().engine == "pg" else neo_plans()
