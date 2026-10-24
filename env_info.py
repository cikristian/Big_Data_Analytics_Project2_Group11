"""Section 1.1 - record software/driver versions, hardware, OS and DB memory settings.
    python env_info.py          (both databases running; screenshot the output)
Writes results/environment.json. psutil is optional (pip install psutil) for RAM."""
import json
import os
import platform
import sys

info = {"os": platform.platform(), "cpu": platform.processor() or platform.machine(),
        "logical_cpus": os.cpu_count(), "python": sys.version.split()[0]}
try:
    import psutil
    info["ram_gb"] = round(psutil.virtual_memory().total / 1e9, 2)
except ImportError:
    info["ram_gb"] = "install psutil or read from system settings"

import numpy, psycopg, neo4j
info.update(numpy=numpy.__version__, psycopg=psycopg.__version__, neo4j_driver=neo4j.__version__)

from db import run_neo, run_pg
try:
    info["postgresql"] = run_pg("SELECT version()")[0][0]
    info["postgresql_settings"] = {name: run_pg(f"SHOW {name}")[0][0] for name in
        ("timezone", "shared_buffers", "work_mem", "maintenance_work_mem", "effective_cache_size",
         "max_parallel_workers_per_gather", "max_connections")}
    print("PostgreSQL connection OK")
except Exception as e:
    info["postgresql"] = f"not reachable: {e}"
try:
    info["neo4j"] = [list(r) for r in run_neo("CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition")]
    info["neo4j_settings"] = {r[0]: r[1] for r in run_neo(
        "SHOW SETTINGS YIELD name, value WHERE name IN ['server.memory.heap.initial_size',"
        "'server.memory.heap.max_size','server.memory.pagecache.size','db.transaction.timeout',"
        "'dbms.memory.transaction.total.max'] RETURN name, value")}
    print("Neo4j connection OK")
except Exception as e:
    info["neo4j"] = f"not reachable: {e}"

print(json.dumps(info, indent=2))
os.makedirs("results", exist_ok=True)
json.dump(info, open("results/environment.json", "w"), indent=2)
