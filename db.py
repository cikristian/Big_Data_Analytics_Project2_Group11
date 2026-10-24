"""Connection helpers and the two wrappers required by section 6.1.

run_pg(query, params) and run_neo(query, params) return every result row as a
list of tuples. normalize() turns driver-specific values (Decimal, dates, lists,
None) into plain Python values so the two engines can be compared exactly.
"""
import datetime as _dt
from decimal import Decimal

from config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, PG_DSN

_pg = None
_neo = None


def pg_conn():
    global _pg
    if _pg is None or _pg.closed:
        import psycopg
        _pg = psycopg.connect(PG_DSN, autocommit=True)
        _pg.execute("SET timezone = 'Africa/Kigali'")
    return _pg


def neo_driver():
    global _neo
    if _neo is None:
        from neo4j import GraphDatabase
        _neo = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        _neo.verify_connectivity()
    return _neo


def run_pg(query, params=None, timeout_s=None):
    conn = pg_conn()
    with conn.cursor() as cur:
        if timeout_s:
            cur.execute(f"SET statement_timeout = {int(timeout_s * 1000)}")
        try:
            cur.execute(query, params or {})
            return [tuple(r) for r in cur.fetchall()]
        finally:
            if timeout_s:
                cur.execute("SET statement_timeout = 0")


def run_neo(query, params=None, timeout_s=None):
    from neo4j import Query
    q = Query(query, timeout=timeout_s) if timeout_s else query
    with neo_driver().session(database="neo4j") as s:
        result = s.run(q, params or {})
        return [tuple(rec.values()) for rec in result]   # consumes every row


def _norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, Decimal)):
        return int(v)
    if isinstance(v, float):
        return int(v) if v.is_integer() else v
    if isinstance(v, (list, tuple)):
        return tuple(_norm(x) for x in v)
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()
    if hasattr(v, "iso_format"):          # neo4j.time.Date / DateTime
        return v.iso_format()
    return v


def normalize(rows, q=None):
    rows = [tuple(_norm(x) for x in r) for r in rows]
    # Q1/Q7 always yield one logical row; Neo4j returns no row when there is no route.
    if q == "Q7" and not rows:
        rows = [(None,)]
    return sorted(rows, key=lambda r: tuple((x is None, x) for x in r))
