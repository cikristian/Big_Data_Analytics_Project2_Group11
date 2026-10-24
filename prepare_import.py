"""Section 3.2 - make temporary typed import copies of the CSVs for
neo4j-admin database import full, leaving data/*.csv unchanged.

    python prepare_import.py              # writes data/import/*.csv and prints the command
    python prepare_import.py --run        # also runs the import (Neo4j must be STOPPED)
    python prepare_import.py --cleanup    # removes data/import after the checks

Set NEO4J_HOME to the Neo4j Community folder (the one containing bin/), e.g.
    set NEO4J_HOME=C:\\neo4j\\neo4j-community-5.26.0        (Windows)
    export NEO4J_HOME=~/neo4j-community-5.26.0             (macOS/Linux)
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import time

from config import DATA_DIR, csv_path

IMPORT_DIR = os.path.join(DATA_DIR, "import")

# source stream -> (import file name, typed header). Column order matches the source CSV.
HEADERS = {
    "customers":       ("customers.csv",   ["customer_id:ID(Customer)", "region:string"]),
    "accounts":        ("accounts.csv",    ["account_id:ID(Account)", ":IGNORE", "role:string"]),
    "devices":         ("devices.csv",     ["device_id:ID(Device)", "access_type:string"]),
    "account_devices": ("used_device.csv", [":START_ID(Account)", ":END_ID(Device)",
                                            "first_day:int", "last_day:int", "observations:int"]),
    "transfers":       ("transfers.csv",   ["transfer_id:long", ":START_ID(Account)", ":END_ID(Account)",
                                            "occurred_at:long", "amount_rwf:int"]),
}


def copy_with_header(src, dst, header):
    """Stream src to dst, replacing only the header line."""
    rows = 0
    with open(src, newline="") as fin, open(dst, "w", newline="") as fout:
        next(fin)                                   # drop the plain header
        fout.write(",".join(header) + "\n")
        for line in fin:
            fout.write(line)
            rows += 1
    return rows


def prepare():
    os.makedirs(IMPORT_DIR, exist_ok=True)
    t0 = time.perf_counter()
    for name, (fname, header) in HEADERS.items():
        n = copy_with_header(csv_path(name), os.path.join(IMPORT_DIR, fname), header)
        print(f"{fname:16s} {n:>11,} rows  header: {','.join(header)}")

    # owns.csv: Customer -[:OWNS]-> Account, ordered by customer_id then account_id
    pairs = []
    with open(csv_path("accounts"), newline="") as f:
        for r in csv.DictReader(f):
            pairs.append((int(r["customer_id"]), int(r["account_id"])))
    pairs.sort()
    with open(os.path.join(IMPORT_DIR, "owns.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([":START_ID(Customer)", ":END_ID(Account)"])
        w.writerows(pairs)
    print(f"{'owns.csv':16s} {len(pairs):>11,} rows  header: :START_ID(Customer),:END_ID(Account)")
    print(f"Prepared import copies in {time.perf_counter() - t0:.1f} s -> {IMPORT_DIR}")


def import_command():
    home = os.environ.get("NEO4J_HOME", "<NEO4J_HOME>")
    admin = os.path.join(home, "bin", "neo4j-admin" + (".bat" if os.name == "nt" else ""))
    p = lambda f: os.path.join(IMPORT_DIR, f)
    return [admin, "database", "import", "full", "neo4j",
            "--overwrite-destination=true", "--id-type=integer",
            f"--nodes=Customer={p('customers.csv')}",
            f"--nodes=Account={p('accounts.csv')}",
            f"--nodes=Device={p('devices.csv')}",
            f"--relationships=OWNS={p('owns.csv')}",
            f"--relationships=USED_DEVICE={p('used_device.csv')}",
            f"--relationships=TRANSFER={p('transfers.csv')}"]


def run_import():
    cmd = import_command()
    print("Running:", " ".join(cmd))
    t0 = time.perf_counter()
    subprocess.run(cmd, check=True)
    secs = time.perf_counter() - t0
    print(f"Import finished in {secs:.1f} s")
    os.makedirs("results", exist_ok=True)
    with open("results/neo4j_import_time.json", "w") as f:
        json.dump({"import_seconds": round(secs, 2), "command": cmd}, f, indent=2)


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        shutil.rmtree(IMPORT_DIR, ignore_errors=True)
        print("Removed", IMPORT_DIR)
    else:
        prepare()
        print("\nImport command (Neo4j stopped):\n" + " ".join(import_command()))
        if "--run" in sys.argv:
            run_import()
