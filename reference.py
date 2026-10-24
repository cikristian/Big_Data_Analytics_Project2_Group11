"""Independent reference answers computed directly from the captured CSVs with
pandas/numpy (no database). Used as a third opinion in compare.py and for the
section 6.1 independent checks. Run once:  python reference.py
Writes results/reference_answers.json (case id -> normalized rows).
Needs about 2 GB RAM; takes a minute or two.
"""
import json
import os
from collections import deque

import numpy as np
import pandas as pd

from config import SETS, csv_path, hour_bounds
from queries import Q4_DEPTHS, Q7_BOUNDS

START = 1788213600  # 2026-09-01 00:00 CAT


def load():
    acc = pd.read_csv(csv_path("accounts"))
    cus = pd.read_csv(csv_path("customers"))
    dev = pd.read_csv(csv_path("devices"))
    ad = pd.read_csv(csv_path("account_devices"))
    tr = pd.read_csv(csv_path("transfers"), dtype={"transfer_id": np.int64, "sender_id": np.int32,
                     "receiver_id": np.int32, "occurred_at": np.int64, "amount_rwf": np.int64})
    return acc, cus, dev, ad, tr


class Out:
    """Transfers grouped by sender (and by receiver) using sorted arrays."""
    def __init__(self, tr, key, other):
        order = np.lexsort((tr["occurred_at"].values, tr[key].values))
        self.key = tr[key].values[order]
        self.other = tr[other].values[order]
        self.t = tr["occurred_at"].values[order]
        self.amt = tr["amount_rwf"].values[order]
        self.id = tr["transfer_id"].values[order]

    def rows(self, account):
        lo, hi = np.searchsorted(self.key, [account, account + 1])
        return zip(self.id[lo:hi].tolist(), self.other[lo:hi].tolist(),
                   self.t[lo:hi].tolist(), self.amt[lo:hi].tolist())


def amount_ok(prev, nxt):
    return 90 * prev <= 100 * nxt <= 105 * prev


def main():
    acc, cus, dev, ad, tr = load()
    role = dict(zip(acc.account_id, acc.role))
    owner = dict(zip(acc.account_id, acc.customer_id))
    region = dict(zip(cus.customer_id, cus.region))
    access = dict(zip(dev.device_id, dev.access_type))
    out = Out(tr, "sender_id", "receiver_id")
    ans = {}

    # Q1
    for s, (a, _, day) in SETS.items():
        st, en = hour_bounds(day)
        rows = [(i, r, t, m) for i, r, t, m in out.rows(a) if st <= t < en]
        ans[f"Q1-{s}"] = [[len(rows), sum(m for *_, m in rows)]]

    # Q2
    day = (tr.occurred_at.values - START) // 86400
    g = pd.DataFrame({"d": day, "a": tr.amount_rwf.values}).groupby("d")["a"].agg(["count", "sum"])
    ans["Q2-month"] = [[f"2026-09-{int(d) + 1:02d}", int(r["count"]), int(r["sum"])] for d, r in g.iterrows()]

    # Q3
    by_dev = ad.groupby("device_id")
    by_acc = ad.groupby("account_id")
    for s, (a, _, _) in SETS.items():
        res = []
        for _, r in by_acc.get_group(a).iterrows():
            for _, o in by_dev.get_group(r.device_id).iterrows():
                if o.account_id == a:
                    continue
                lo, hi = max(r.first_day, o.first_day), min(r.last_day, o.last_day)
                if lo <= hi:
                    res.append([int(o.account_id), int(r.device_id), access[r.device_id], int(lo), int(hi)])
        ans[f"Q3-{s}"] = sorted(res)

    # Q4: undirected BFS over ownership + device-use edges
    adj = {}
    def link(x, y):
        adj.setdefault(x, []).append(y); adj.setdefault(y, []).append(x)
    for a_, c_ in zip(acc.account_id, acc.customer_id):
        link(("A", a_), ("C", c_))
    for a_, d_ in zip(ad.account_id, ad.device_id):
        link(("A", a_), ("D", d_))
    for s, (a, _, _) in SETS.items():
        dist = {("A", a): 0}
        q = deque([("A", a)])
        while q:
            n = q.popleft()
            if dist[n] == max(Q4_DEPTHS):
                continue
            for m in adj.get(n, ()):
                if m not in dist:
                    dist[m] = dist[n] + 1
                    q.append(m)
        for d in Q4_DEPTHS:
            counts = {}
            for (k, i), dd in dist.items():
                if k == "A" and i != a and dd <= d:
                    rg = region[owner[i]]
                    counts[rg] = counts.get(rg, 0) + 1
            ans[f"Q4-{s}-d{d}"] = sorted([k, v] for k, v in counts.items())

    # Q5
    for s, (a, _, day) in SETS.items():
        st, en = hour_bounds(day)
        res = []
        for i1, b, t1, m1 in out.rows(a):
            if not (st <= t1 < en) or b == a:
                continue
            for i2, c, t2, m2 in out.rows(b):
                if not (t1 < t2 <= t1 + 600 and amount_ok(m1, m2)) or c in (a, b):
                    continue
                for i3, d_, t3, m3 in out.rows(c):
                    if t2 < t3 <= t2 + 600 and amount_ok(m2, m3) and d_ not in (a, b, c):
                        res.append([i1, i2, i3, d_])
        ans[f"Q5-{s}"] = sorted(res)

    # Q6
    for s, (a, _, day) in SETS.items():
        st, en = hour_bounds(day)
        res = []
        def dfs(cur, ids, first, last, amt):
            if len(ids) == 8:
                return
            for i, r, t, m in out.rows(cur):
                if not (last < t < en and t <= first + 1800 and amount_ok(amt, m)):
                    continue
                if r == a:
                    if len(ids) + 1 >= 3:
                        res.append([ids + [i], len(ids) + 1])
                else:
                    dfs(r, ids + [i], first, t, m)
        for i, r, t, m in out.rows(a):
            if st <= t < en and r != a:
                dfs(r, [i], t, t, m)
        ans[f"Q6-{s}"] = sorted(res)

    # Q7: BFS over distinct person->person neighbours
    person = tr.sender_id.map(role).eq("person").values & tr.receiver_id.map(role).eq("person").values
    pp = tr.loc[person, ["sender_id", "receiver_id"]].drop_duplicates()
    nbr = pp.groupby("sender_id")["receiver_id"].apply(list).to_dict()
    for s, (a, dest, _) in SETS.items():
        dist = {a: 0}
        q = deque([a])
        while q and dest not in dist:
            n = q.popleft()
            for m in nbr.get(n, ()):
                if m not in dist:
                    dist[m] = dist[n] + 1
                    q.append(m)
        for b in Q7_BOUNDS:
            L = dist.get(dest)
            ans[f"Q7-{s}-b{b}"] = [[L if L is not None and L <= b else None]]

    os.makedirs("results", exist_ok=True)
    with open("results/reference_answers.json", "w") as f:
        json.dump(ans, f, default=int, indent=1)
    print(f"Saved {len(ans)} reference answers to results/reference_answers.json")


if __name__ == "__main__":
    main()
