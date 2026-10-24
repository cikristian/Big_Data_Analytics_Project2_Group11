"""Section 3.3 - trace one account to its owner, a device and an outgoing transfer
in both models.   python inspect_account.py [account_id]   (default 998)"""
import sys

from config import cat
from db import run_neo, run_pg

ACCOUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 998

SQL = """
SELECT a.account_id, a.role, c.customer_id, c.region,
       d.device_id, d.access_type, ad.first_day, ad.last_day, ad.observations,
       t.transfer_id, t.receiver_id, t.occurred_at, t.amount_rwf
FROM accounts a
JOIN customers c        ON c.customer_id = a.customer_id
JOIN account_devices ad ON ad.account_id = a.account_id
JOIN devices d          ON d.device_id   = ad.device_id
JOIN LATERAL (SELECT * FROM transfers t WHERE t.sender_id = a.account_id
              ORDER BY t.occurred_at, t.transfer_id LIMIT 1) t ON true
WHERE a.account_id = %(account)s
ORDER BY d.device_id
LIMIT 1;
"""

CYPHER = """
MATCH (c:Customer)-[:OWNS]->(a:Account {account_id: $account})-[u:USED_DEVICE]->(d:Device)
WITH c, a, u, d ORDER BY d.device_id LIMIT 1
MATCH (a)-[t:TRANSFER]->(r:Account)
WITH c, a, u, d, t, r ORDER BY t.occurred_at, t.transfer_id LIMIT 1
RETURN a.account_id, a.role, c.customer_id, c.region,
       d.device_id, d.access_type, u.first_day, u.last_day, u.observations,
       t.transfer_id, r.account_id, t.occurred_at, t.amount_rwf;
"""

if __name__ == "__main__":
    cols = ["account_id", "role", "customer_id", "region", "device_id", "access_type",
            "first_day", "last_day", "observations", "transfer_id", "receiver_id",
            "occurred_at", "amount_rwf"]
    pg = run_pg(SQL, {"account": ACCOUNT})
    neo = run_neo(CYPHER, {"account": ACCOUNT})
    for name, rows in (("PostgreSQL", pg), ("Neo4j", neo)):
        print(f"\n{name}:")
        for k, v in zip(cols, rows[0]):
            print(f"  {k:13s} {v}" + (f"  ({cat(v)})" if k == "occurred_at" else ""))
    print("\nIdentical:", [int(x) if isinstance(x, int) else x for x in pg[0]] ==
          [int(x) if isinstance(x, int) else x for x in neo[0]])
