"""Section 1.2 - capture the five generator streams to CSV, progressively.

Usage:
    python capture.py --preview      # ten records from every stream (screenshot)
    python capture.py                # full capture with audit totals (screenshot)
Nothing is held in memory beyond the current row.
"""
import csv
import json
import os
import sys
import time
from itertools import islice
from pprint import pprint

import mobile_money_generator as g
from config import DATA_DIR, cat, csv_path

STREAMS = ["customers", "accounts", "devices", "account_devices", "transfers"]


def iterator(name):
    # A fresh call restarts the stream.
    return getattr(g, f"iter_{name}")()


def preview():
    print("dataset_info():")
    pprint(g.dataset_info())
    print("\nFIELDS:")
    pprint(g.FIELDS)
    for name in STREAMS:
        print(f"\n--- first 10 rows of iter_{name}() ---")
        for row in islice(iterator(name), 10):
            print(row)


def capture():
    os.makedirs(DATA_DIR, exist_ok=True)
    expected = g.dataset_info()["expected_counts"]
    summary = {}
    t_all = time.perf_counter()
    for name in STREAMS:
        path = csv_path(name)
        consumed = written = 0
        audit = {"count": 0, "min_occurred_at": None, "max_occurred_at": None, "sum_amount_rwf": 0}
        t0 = time.perf_counter()
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=g.FIELDS[name])
            writer.writeheader()
            for row in iterator(name):
                consumed += 1
                writer.writerow(row)
                written += 1
                if name == "transfers":
                    ts = row["occurred_at"]
                    audit["count"] += 1
                    audit["sum_amount_rwf"] += row["amount_rwf"]
                    if audit["min_occurred_at"] is None or ts < audit["min_occurred_at"]:
                        audit["min_occurred_at"] = ts
                    if audit["max_occurred_at"] is None or ts > audit["max_occurred_at"]:
                        audit["max_occurred_at"] = ts
                    if written % 1_000_000 == 0:
                        print(f"  transfers: {written:,} rows written "
                              f"({time.perf_counter() - t0:.1f} s)", flush=True)
        secs = time.perf_counter() - t0
        size = os.path.getsize(path)
        ok = consumed == written == expected[name]
        summary[name] = dict(consumed=consumed, written=written, expected=expected[name],
                             match=ok, seconds=round(secs, 2), csv_bytes=size,
                             csv_gb=round(size / 1e9, 4))
        print(f"{name:16s} consumed={consumed:>11,} written={written:>11,} "
              f"expected={expected[name]:>11,} match={ok} {secs:8.1f} s {size / 1e9:.4f} GB", flush=True)
        if name == "transfers":
            summary["transfer_audit"] = audit
    total_rows = sum(summary[s]["written"] for s in STREAMS)
    summary["total_rows"] = total_rows
    summary["total_seconds"] = round(time.perf_counter() - t_all, 2)
    summary["total_csv_gb"] = round(sum(summary[s]["csv_bytes"] for s in STREAMS) / 1e9, 4)
    a = summary["transfer_audit"]
    print("\nTotal source records:", f"{total_rows:,}", "(expected 20,993,500)")
    print("Transfer audit:", f"count={a['count']:,}",
          f"earliest={a['min_occurred_at']} ({cat(a['min_occurred_at'])})",
          f"latest={a['max_occurred_at']} ({cat(a['max_occurred_at'])})",
          f"sum_amount_rwf={a['sum_amount_rwf']:,}")
    print(f"Capture seconds: {summary['total_seconds']}  CSV total: {summary['total_csv_gb']} GB")
    os.makedirs("results", exist_ok=True)
    with open("results/capture_audit.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("Saved results/capture_audit.json")


if __name__ == "__main__":
    preview() if "--preview" in sys.argv else capture()
