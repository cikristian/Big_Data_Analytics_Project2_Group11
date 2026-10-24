"""Section 3.2 steps 3-4 - setup timing, store sizes and graph checks.

    python neo4j_checks.py --setup     # creates constraints/index, waits online, times it
    python neo4j_checks.py             # runs all verification checks
Set NEO4J_HOME so store and transaction-log sizes can be measured.
"""
import json
import os
import sys
import time

from db import run_neo

SETUP = [
    "CREATE CONSTRAINT customer_id_unique IF NOT EXISTS FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE",
    "CREATE CONSTRAINT account_id_unique IF NOT EXISTS FOR (a:Account) REQUIRE a.account_id IS UNIQUE",
    "CREATE CONSTRAINT device_id_unique IF NOT EXISTS FOR (d:Device) REQUIRE d.device_id IS UNIQUE",
    "CREATE INDEX transfer_occurred_at IF NOT EXISTS FOR ()-[t:TRANSFER]-() ON (t.occurred_at)",
    "CALL db.awaitIndexes(1800)",
]

CHECKS = [
    ("Customer nodes (228,000)", "MATCH (n:Customer) RETURN count(n)"),
    ("Account nodes (248,000)", "MATCH (n:Account) RETURN count(n)"),
    ("Device nodes (228,600)", "MATCH (n:Device) RETURN count(n)"),
    ("All nodes (704,600)", "MATCH (n) RETURN count(n)"),
    ("OWNS (248,000)", "MATCH ()-[r:OWNS]->() RETURN count(r)"),
    ("USED_DEVICE (285,600)", "MATCH ()-[r:USED_DEVICE]->() RETURN count(r)"),
    ("TRANSFER (20,003,300)", "MATCH ()-[r:TRANSFER]->() RETURN count(r)"),
    ("All relationships (20,536,900)", "MATCH ()-[r]->() RETURN count(r)"),
    ("Account roles", "MATCH (a:Account) RETURN a.role, count(*) ORDER BY a.role"),
    ("Accounts without exactly one owner (0)",
     "MATCH (a:Account) OPTIONAL MATCH (c:Customer)-[:OWNS]->(a) "
     "WITH a, count(c) AS owners WHERE owners <> 1 RETURN count(a)"),
    ("Transfers vs distinct transfer_id",
     "MATCH ()-[t:TRANSFER]->() RETURN count(t), count(DISTINCT t.transfer_id)"),
    ("Transfer audit (count, earliest, latest, sum)",
     "MATCH ()-[t:TRANSFER]->() RETURN count(t), min(t.occurred_at), max(t.occurred_at), sum(t.amount_rwf)"),
    ("Property types sample",
     "MATCH (c:Customer)-[:OWNS]->(a:Account)-[u:USED_DEVICE]->(d:Device) WITH c,a,u,d LIMIT 1 "
     "MATCH (a)-[t:TRANSFER]->() WITH c,a,u,d,t LIMIT 1 "
     "RETURN valueType(c.customer_id), valueType(a.account_id), valueType(u.first_day), "
     "valueType(t.occurred_at), valueType(t.amount_rwf)"),
]


def folder_gb(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return round(total / 1e9, 4)


def sizes():
    home = os.environ.get("NEO4J_HOME")
    if not home:
        print("Set NEO4J_HOME to report store sizes.")
        return {}
    s = {"store_gb": folder_gb(os.path.join(home, "data", "databases", "neo4j")),
         "transaction_log_gb": folder_gb(os.path.join(home, "data", "transactions", "neo4j"))}
    print(f"Store {s['store_gb']} GB, transaction logs {s['transaction_log_gb']} GB (1 GB = 1e9 bytes)")
    return s


def main():
    os.makedirs("results", exist_ok=True)
    if "--setup" in sys.argv:
        t0 = time.perf_counter()
        for q in SETUP:
            run_neo(q)
        secs = time.perf_counter() - t0
        print(f"Constraint/index setup and population: {secs:.1f} s")
        for r in run_neo("SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties"):
            print(r)
        for r in run_neo("SHOW INDEXES YIELD name, state, populationPercent, type, labelsOrTypes, properties"):
            print(r)
        json.dump({"setup_seconds": round(secs, 2), **sizes()},
                  open("results/neo4j_setup.json", "w"), indent=2)
        return
    out = {}
    for label, q in CHECKS:
        t0 = time.perf_counter()
        try:
            rows = run_neo(q)
        except Exception as e:          # e.g. valueType() needs Neo4j 5.13+
            rows = [f"ERROR {type(e).__name__}: {e}"]
        print(f"{label:48s} {rows}   ({time.perf_counter() - t0:.1f} s)")
        out[label] = [list(r) for r in rows]
    out["sizes"] = sizes()
    audit = json.load(open("results/capture_audit.json"))["transfer_audit"]
    print("capture.py audit:", audit)
    json.dump(out, open("results/neo4j_checks.json", "w"), indent=2, default=str)


if __name__ == "__main__":
    main()
