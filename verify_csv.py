"""Section 6.1 independent checks against the captured CSV rows (no database).

    python verify_csv.py
Checks (1) one device overlap from Q3 set A and (2) one Q5 chain and one Q6
cycle, by streaming the CSVs with the csv module and re-applying every rule.
Edit the constants below to check different examples from your results.
"""
import csv

from config import SETS, cat, csv_path, hour_bounds

OVERLAP = (998, 24755, 228001)                      # review account, other account, device
CHAIN = [20000001, 20000002, 20000003]               # Q5 set A
CYCLE = [20000229, 20000230, 20000231, 20000232, 20000233, 20000234]   # Q6 set C


def check_overlap(a, b, device):
    rows = {}
    with open(csv_path("account_devices"), newline="") as f:
        for r in csv.DictReader(f):
            if int(r["device_id"]) == device and int(r["account_id"]) in (a, b):
                rows[int(r["account_id"])] = r
    with open(csv_path("devices"), newline="") as f:
        access = next(r["access_type"] for r in csv.DictReader(f) if int(r["device_id"]) == device)
    ra, rb = rows[a], rows[b]
    lo = max(int(ra["first_day"]), int(rb["first_day"]))
    hi = min(int(ra["last_day"]), int(rb["last_day"]))
    print(f"Device {device} ({access})")
    print(f"  account {a}: days [{ra['first_day']},{ra['last_day']}] observations {ra['observations']}")
    print(f"  account {b}: days [{rb['first_day']},{rb['last_day']}] observations {rb['observations']}")
    print(f"  overlap [{lo},{hi}] -> {'VALID' if lo <= hi else 'NO OVERLAP'}")


def fetch(ids):
    want, got = set(ids), {}
    with open(csv_path("transfers"), newline="") as f:
        for r in csv.DictReader(f):
            if int(r["transfer_id"]) in want:
                got[int(r["transfer_id"])] = {k: int(v) for k, v in r.items()}
    return [got[i] for i in ids]


def amount_ok(p, n):
    return 90 * p <= 100 * n <= 105 * p


def check_sequence(ids, kind, letter):
    account, _, day = SETS[letter]
    start, end = hour_bounds(day)
    rows = fetch(ids)
    print(f"\n{kind} for set {letter} (account {account}):")
    for r in rows:
        print(f"  {r['transfer_id']}: {r['sender_id']} -> {r['receiver_id']}  "
              f"{cat(r['occurred_at'])}  {r['amount_rwf']:,} RWF")
    ok = rows[0]["sender_id"] == account and start <= rows[0]["occurred_at"] < end
    for p, n in zip(rows, rows[1:]):
        ok &= p["receiver_id"] == n["sender_id"]
        ok &= n["occurred_at"] > p["occurred_at"]
        ok &= amount_ok(p["amount_rwf"], n["amount_rwf"])
        if kind == "Chain":
            ok &= n["occurred_at"] - p["occurred_at"] <= 600
    if kind == "Chain":
        accts = [rows[0]["sender_id"]] + [r["receiver_id"] for r in rows]
        ok &= len(rows) == 3 and len(set(accts)) == 4
    else:
        ok &= rows[-1]["receiver_id"] == account and 3 <= len(rows) <= 8
        ok &= all(r["receiver_id"] != account for r in rows[:-1])
        ok &= rows[-1]["occurred_at"] < end and rows[-1]["occurred_at"] - rows[0]["occurred_at"] <= 1800
    print(f"  all rules satisfied: {ok}")


if __name__ == "__main__":
    check_overlap(*OVERLAP)
    check_sequence(CHAIN, "Chain", "A")
    check_sequence(CYCLE, "Cycle", "C")
