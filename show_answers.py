"""Readable Q1-Q7 answers for the report screenshots (sections 4 and 5).

    python show_answers.py            # uses results/compare_bidir.json, else compare_baseline.json
    python show_answers.py Q5         # one question only
Shows the PostgreSQL rows, whether Neo4j returned exactly the same rows,
and the verified Q7 supporting paths.
"""
import json
import os
import sys

from config import SETS, cat

src = next((p for p in ("results/compare_bidir.json", "results/compare_baseline.json") if os.path.exists(p)), None)
if not src:
    sys.exit("Run compare.py first.")
data = json.load(open(src))
outputs, paths = data["outputs"], data.get("paths", {})
only = sys.argv[1].upper() if len(sys.argv) > 1 else None

TITLES = {
    "Q1": "Q1  Outgoing transfers in the review hour  (count, total RWF)",
    "Q2": "Q2  Daily transfers, September 2026 CAT  (day, count, total RWF)",
    "Q3": "Q3  Accounts sharing a device with overlapping days  (other, device, access, from, to)",
    "Q4": "Q4  Accounts reached through OWNS/USED_DEVICE, by region",
    "Q5": "Q5  Rapid three-transfer chains  (t1, t2, t3, final receiver)",
    "Q6": "Q6  Rapid cycles back to the review account  (transfer ids, length)",
    "Q7": "Q7  Shortest person-only transfer route  (length; None = no route within bound)",
}

for q, title in TITLES.items():
    if only and q != only:
        continue
    print("\n" + "=" * 100 + f"\n{title}\n" + "=" * 100)
    for case, o in outputs.items():
        if not case.startswith(q + "-"):
            continue
        same = "Neo4j identical" if o["postgres"] == o["neo4j"] else "!! Neo4j DIFFERENT"
        p = o["params"]
        extra = ""
        if "start" in p:
            extra = f"  hour {cat(p['start'])} -> {cat(p['end'])[11:]}"
        print(f"\n{case}  params {p}{extra}   [{same}]")
        rows = o["postgres"]
        if not rows:
            print("   (no rows)")
        for r in rows:
            if q == "Q2":
                print(f"   {r[0]}  {r[1]:>9,}  {r[2]:>16,}")
            elif q == "Q4":
                print(f"   {r[0]:10s} {r[1]:>6,}")
            else:
                print("  ", r)
        if q == "Q4":
            print(f"   total {sum(r[1] for r in rows):,}")
        if q == "Q2":
            print(f"   month total {sum(r[1] for r in rows):,} transfers, {sum(r[2] for r in rows):,} RWF")
        if q == "Q7" and paths.get(case):
            pa = paths[case]
            print(f"   path accounts {pa['accounts']}\n   transfers     {pa['transfer_ids']}"
                  f"\n   verified against PostgreSQL rows: {'VALID' if not pa['problems'] else pa['problems']}")
    if q == "Q4" and paths.get("Q4-A-example"):
        print("\nQ4 supporting path (set A):", paths["Q4-A-example"])

st = data["status"]
print(f"\n{sum(s['status'] == 'OK' for s in st)}/{len(st)} cases match  (source: {src})")
