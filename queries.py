"""Q1-Q7 as parameterized SQL / Cypher pairs, plus the case list used by every
program (61 correctness cases, 21 timing cases).

SQL placeholders are psycopg %(name)s parameters; Cypher uses $name.
Variable-length bounds cannot be Cypher parameters, so the Q4 depth and the Q7
bound are substituted from a fixed whitelist of integers (never user text).
"""
from config import SETS, hour_bounds

# --------------------------------------------------------------------------- Q1
Q1_SQL = """
SELECT COUNT(*) AS transfers, COALESCE(SUM(amount_rwf), 0) AS total_rwf
FROM transfers
WHERE sender_id = %(account)s
  AND occurred_at >= %(start)s AND occurred_at < %(end)s;
"""
Q1_CYPHER = """
MATCH (a:Account {account_id: $account})
OPTIONAL MATCH (a)-[t:TRANSFER]->()
  WHERE t.occurred_at >= $start AND t.occurred_at < $end
RETURN count(t) AS transfers, coalesce(sum(t.amount_rwf), 0) AS total_rwf;
"""

# --------------------------------------------------------------------------- Q2
Q2_SQL = """
SELECT (to_timestamp(occurred_at) AT TIME ZONE 'Africa/Kigali')::date AS day,
       COUNT(*) AS transfers,
       SUM(amount_rwf::bigint) AS total_rwf
FROM transfers
GROUP BY 1
ORDER BY 1;
"""
Q2_CYPHER = """
MATCH ()-[t:TRANSFER]->()
WITH date(datetime({epochSeconds: t.occurred_at, timezone: 'Africa/Kigali'})) AS day,
     t.amount_rwf AS amount
RETURN day, count(*) AS transfers, sum(amount) AS total_rwf
ORDER BY day;
"""

# --------------------------------------------------------------------------- Q3
Q3_SQL = """
SELECT o.account_id                        AS other_account,
       o.device_id,
       d.access_type,
       GREATEST(r.first_day, o.first_day)  AS overlap_start,
       LEAST(r.last_day, o.last_day)       AS overlap_end
FROM account_devices r
JOIN account_devices o ON o.device_id = r.device_id AND o.account_id <> r.account_id
JOIN devices d         ON d.device_id = r.device_id
WHERE r.account_id = %(account)s
  AND GREATEST(r.first_day, o.first_day) <= LEAST(r.last_day, o.last_day)
ORDER BY other_account, o.device_id;
"""
Q3_CYPHER = """
MATCH (a:Account {account_id: $account})-[r1:USED_DEVICE]->(d:Device)<-[r2:USED_DEVICE]-(b:Account)
WHERE b <> a
WITH b, d,
     CASE WHEN r1.first_day > r2.first_day THEN r1.first_day ELSE r2.first_day END AS s,
     CASE WHEN r1.last_day  < r2.last_day  THEN r1.last_day  ELSE r2.last_day  END AS e
WHERE s <= e
RETURN b.account_id AS other_account, d.device_id AS device_id, d.access_type AS access_type,
       s AS overlap_start, e AS overlap_end
ORDER BY other_account, device_id;
"""

# --------------------------------------------------------------------------- Q4
Q4_SQL = """
WITH RECURSIVE edges(sk, si, dk, di) AS (
    SELECT 'Customer'::text, customer_id, 'Account'::text,  account_id  FROM accounts
    UNION ALL
    SELECT 'Account'::text,  account_id,  'Customer'::text, customer_id FROM accounts
    UNION ALL
    SELECT 'Account'::text,  account_id,  'Device'::text,   device_id   FROM account_devices
    UNION ALL
    SELECT 'Device'::text,   device_id,   'Account'::text,  account_id  FROM account_devices
), walk(kind, id, depth) AS (
    SELECT 'Account'::text, %(account)s::integer, 0
    UNION
    SELECT e.dk, e.di, w.depth + 1
    FROM walk w
    JOIN edges e ON e.sk = w.kind AND e.si = w.id
    WHERE w.depth < %(depth)s
)
SELECT c.region, COUNT(DISTINCT w.id) AS accounts
FROM walk w
JOIN accounts a  ON w.kind = 'Account' AND a.account_id = w.id
JOIN customers c ON c.customer_id = a.customer_id
WHERE w.id <> %(account)s
GROUP BY c.region
ORDER BY c.region;
"""
Q4_CYPHER_TEMPLATE = """
MATCH (a:Account {account_id: $account})
MATCH (a)-[:OWNS|USED_DEVICE*1..%d]-(b:Account)
WHERE b <> a
WITH DISTINCT b
MATCH (c:Customer)-[:OWNS]->(b)
RETURN c.region AS region, count(b) AS accounts
ORDER BY region;
"""
Q4_DEPTHS = (4, 6, 8, 10)


def q4_cypher(depth):
    assert depth in Q4_DEPTHS
    return Q4_CYPHER_TEMPLATE % depth


# One supporting path (screenshot) for Q4
Q4_PATH_CYPHER_TEMPLATE = """
MATCH (a:Account {account_id: $account}), (b:Account {account_id: $other})
MATCH p = shortestPath((a)-[:OWNS|USED_DEVICE*..%d]-(b))
RETURN [n IN nodes(p) | labels(n)[0] + ' ' +
        toString(coalesce(n.account_id, n.customer_id, n.device_id))] AS path,
       [r IN relationships(p) | type(r)] AS links, length(p) AS hops;
"""

# --------------------------------------------------------------------------- Q5
Q5_SQL = """
SELECT t1.transfer_id AS t1, t2.transfer_id AS t2, t3.transfer_id AS t3,
       t3.receiver_id AS final_receiver
FROM transfers t1
JOIN transfers t2 ON t2.sender_id = t1.receiver_id
                 AND t2.occurred_at >  t1.occurred_at
                 AND t2.occurred_at <= t1.occurred_at + 600
JOIN transfers t3 ON t3.sender_id = t2.receiver_id
                 AND t3.occurred_at >  t2.occurred_at
                 AND t3.occurred_at <= t2.occurred_at + 600
WHERE t1.sender_id = %(account)s
  AND t1.occurred_at >= %(start)s AND t1.occurred_at < %(end)s
  AND 90::bigint  * t1.amount_rwf <= 100::bigint * t2.amount_rwf
  AND 100::bigint * t2.amount_rwf <= 105::bigint * t1.amount_rwf
  AND 90::bigint  * t2.amount_rwf <= 100::bigint * t3.amount_rwf
  AND 100::bigint * t3.amount_rwf <= 105::bigint * t2.amount_rwf
  -- four distinct accounts
  AND t1.receiver_id <> t1.sender_id
  AND t2.receiver_id NOT IN (t1.sender_id, t1.receiver_id)
  AND t3.receiver_id NOT IN (t1.sender_id, t1.receiver_id, t2.receiver_id)
ORDER BY t1, t2, t3, final_receiver;
"""
Q5_CYPHER = """
MATCH (a:Account {account_id: $account})-[t1:TRANSFER]->(b:Account)
WHERE t1.occurred_at >= $start AND t1.occurred_at < $end AND b <> a
MATCH (b)-[t2:TRANSFER]->(c:Account)
WHERE t2.occurred_at > t1.occurred_at AND t2.occurred_at <= t1.occurred_at + 600
  AND 90 * t1.amount_rwf <= 100 * t2.amount_rwf AND 100 * t2.amount_rwf <= 105 * t1.amount_rwf
  AND c <> a AND c <> b
MATCH (c)-[t3:TRANSFER]->(d:Account)
WHERE t3.occurred_at > t2.occurred_at AND t3.occurred_at <= t2.occurred_at + 600
  AND 90 * t2.amount_rwf <= 100 * t3.amount_rwf AND 100 * t3.amount_rwf <= 105 * t2.amount_rwf
  AND d <> a AND d <> b AND d <> c
RETURN t1.transfer_id AS t1, t2.transfer_id AS t2, t3.transfer_id AS t3,
       d.account_id AS final_receiver
ORDER BY t1, t2, t3, final_receiver;
"""

# --------------------------------------------------------------------------- Q6
Q6_SQL = """
WITH RECURSIVE chain(cur, ids, first_at, last_at, last_amount, len, returned) AS (
    SELECT receiver_id, ARRAY[transfer_id], occurred_at, occurred_at, amount_rwf, 1,
           receiver_id = %(account)s
    FROM transfers
    WHERE sender_id = %(account)s
      AND occurred_at >= %(start)s AND occurred_at < %(end)s
    UNION ALL
    SELECT t.receiver_id, c.ids || t.transfer_id, c.first_at, t.occurred_at, t.amount_rwf,
           c.len + 1, t.receiver_id = %(account)s
    FROM chain c
    JOIN transfers t ON t.sender_id = c.cur
                    AND t.occurred_at >  c.last_at          -- strictly increasing
                    AND t.occurred_at <  %(end)s            -- inside the hour
                    AND t.occurred_at <= c.first_at + 1800  -- span at most 1,800 s
    WHERE NOT c.returned                                    -- stop at the first return
      AND c.len < 8
      AND 90::bigint  * c.last_amount <= 100::bigint * t.amount_rwf
      AND 100::bigint * t.amount_rwf  <= 105::bigint * c.last_amount
)
SELECT ids AS transfer_ids, len AS transfers
FROM chain
WHERE returned AND len >= 3
ORDER BY ids;
"""
Q6_CYPHER = """
MATCH (a:Account {account_id: $account})
MATCH p = (a)-[ts:TRANSFER*3..8]->(a)
WHERE all(t IN ts WHERE t.occurred_at >= $start AND t.occurred_at < $end)
  AND ts[-1].occurred_at - ts[0].occurred_at <= 1800
  AND all(i IN range(1, size(ts) - 1) WHERE
          ts[i].occurred_at > ts[i - 1].occurred_at
          AND 90 * ts[i - 1].amount_rwf <= 100 * ts[i].amount_rwf
          AND 100 * ts[i].amount_rwf <= 105 * ts[i - 1].amount_rwf)
  AND none(n IN nodes(p)[1..-1] WHERE n = a)
RETURN [t IN ts | t.transfer_id] AS transfer_ids, size(ts) AS transfers
ORDER BY transfer_ids;
"""

# --------------------------------------------------------------------------- Q7
# Baseline: breadth-first recursive search over directed transfer neighbours.
Q7_SQL = """
WITH RECURSIVE bfs(acct, depth) AS (
    SELECT account_id, 0 FROM accounts
    WHERE account_id = %(source)s AND role = 'person'
    UNION
    SELECT t.receiver_id, b.depth + 1
    FROM bfs b
    JOIN transfers t ON t.sender_id = b.acct
    JOIN accounts  r ON r.account_id = t.receiver_id
    WHERE b.depth < %(bound)s
      AND r.role = 'person'          -- restriction applied during the search
)
SELECT MIN(depth) AS min_length FROM bfs WHERE acct = %(dest)s;
"""

# Section 6.3 improvement: bidirectional search. Forward ball of radius
# ceil(bound/2) from the source, backward ball of radius floor(bound/2) into the
# destination, each deduplicated per (account, depth) and per distinct neighbour;
# the answer is the smallest forward+backward depth over accounts in both balls.
Q7_SQL_BIDIR = """
WITH RECURSIVE fwd(acct, depth) AS (
    SELECT account_id, 0 FROM accounts
    WHERE account_id = %(source)s AND role = 'person'
    UNION
    SELECT n.receiver_id, f.depth + 1
    FROM fwd f
    CROSS JOIN LATERAL (SELECT DISTINCT t.receiver_id FROM transfers t
                        WHERE t.sender_id = f.acct) n
    JOIN accounts r ON r.account_id = n.receiver_id AND r.role = 'person'
    WHERE f.depth < (%(bound)s + 1) / 2
), bwd(acct, depth) AS (
    SELECT account_id, 0 FROM accounts
    WHERE account_id = %(dest)s AND role = 'person'
    UNION
    SELECT n.sender_id, b.depth + 1
    FROM bwd b
    CROSS JOIN LATERAL (SELECT DISTINCT t.sender_id FROM transfers t
                        WHERE t.receiver_id = b.acct) n
    JOIN accounts s ON s.account_id = n.sender_id AND s.role = 'person'
    WHERE b.depth < %(bound)s / 2
), f AS (SELECT acct, MIN(depth) AS d FROM fwd GROUP BY acct),
   b AS (SELECT acct, MIN(depth) AS d FROM bwd GROUP BY acct)
SELECT MIN(f.d + b.d) AS min_length
FROM f JOIN b USING (acct)
WHERE f.d + b.d <= %(bound)s;
"""

Q7_CYPHER_TEMPLATE = """
MATCH (s:Account {account_id: $source}), (t:Account {account_id: $dest})
MATCH p = shortestPath((s)-[:TRANSFER*1..%d]->(t))
WHERE all(n IN nodes(p) WHERE n.role = 'person')
RETURN length(p) AS min_length;
"""
Q7_PATH_CYPHER_TEMPLATE = """
MATCH (s:Account {account_id: $source}), (t:Account {account_id: $dest})
MATCH p = shortestPath((s)-[:TRANSFER*1..%d]->(t))
WHERE all(n IN nodes(p) WHERE n.role = 'person')
RETURN [n IN nodes(p) | n.account_id] AS accounts,
       [r IN relationships(p) | r.transfer_id] AS transfer_ids,
       length(p) AS min_length;
"""
Q7_BOUNDS = (4, 6)


def q7_cypher(bound, path=False):
    assert bound in Q7_BOUNDS
    return (Q7_PATH_CYPHER_TEMPLATE if path else Q7_CYPHER_TEMPLATE) % bound


# Path verification in SQL: each hop must be an existing transfer from the
# previous account to the next one, and every account must be a person.
Q7_VERIFY_HOP_SQL = """
SELECT t.transfer_id, t.sender_id, t.receiver_id, s.role, r.role
FROM transfers t
JOIN accounts s ON s.account_id = t.sender_id
JOIN accounts r ON r.account_id = t.receiver_id
WHERE t.transfer_id = %(transfer_id)s;
"""


# --------------------------------------------------------------------------- cases
def _hour_params(letter):
    account, dest, day = SETS[letter]
    start, end = hour_bounds(day)
    return {"account": account, "start": start, "end": end}


def build_cases(q7_sql=None):
    """Return the 61 correctness cases in order: 6, 1, 6, 24, 6, 6, 12."""
    q7_sql = q7_sql or Q7_SQL
    cases = []
    for s in SETS:
        cases.append(dict(id=f"Q1-{s}", q="Q1", sql=Q1_SQL, cypher=Q1_CYPHER, params=_hour_params(s)))
    cases.append(dict(id="Q2-month", q="Q2", sql=Q2_SQL, cypher=Q2_CYPHER, params={}))
    for s in SETS:
        cases.append(dict(id=f"Q3-{s}", q="Q3", sql=Q3_SQL, cypher=Q3_CYPHER,
                          params={"account": SETS[s][0]}))
    for s in SETS:
        for d in Q4_DEPTHS:
            cases.append(dict(id=f"Q4-{s}-d{d}", q="Q4", sql=Q4_SQL, cypher=q4_cypher(d),
                              params={"account": SETS[s][0], "depth": d}))
    for s in SETS:
        cases.append(dict(id=f"Q5-{s}", q="Q5", sql=Q5_SQL, cypher=Q5_CYPHER, params=_hour_params(s)))
    for s in SETS:
        cases.append(dict(id=f"Q6-{s}", q="Q6", sql=Q6_SQL, cypher=Q6_CYPHER, params=_hour_params(s)))
    for s in SETS:
        for b in Q7_BOUNDS:
            cases.append(dict(id=f"Q7-{s}-b{b}", q="Q7", sql=q7_sql, cypher=q7_cypher(b),
                              params={"source": SETS[s][0], "dest": SETS[s][1], "bound": b}))
    assert len(cases) == 61
    return cases


def timing_cases(q7_sql=None):
    """The 21 timed cases of section 6.2."""
    keep = {f"{q}-{s}" for q in ("Q1", "Q3", "Q5", "Q6") for s in "BE"} | {"Q2-month"}
    keep |= {f"Q4-{s}-d{d}" for s in "BE" for d in Q4_DEPTHS}
    keep |= {f"Q7-{s}-b{b}" for s in "BE" for b in Q7_BOUNDS}
    out = [c for c in build_cases(q7_sql) if c["id"] in keep]
    assert len(out) == 21
    return out
