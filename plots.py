"""Charts for the report (PNG files in results/charts/).

    python plots.py
Uses: PostgreSQL Q2 (daily chart), results/compare_*.json (Q4 count vs depth),
results/bench_summary.csv, results/loadtest/combined_summary.csv.
Each chart is skipped if its input does not exist yet.
"""
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = "results/charts"
os.makedirs(OUT, exist_ok=True)


def daily():
    from db import run_pg
    from queries import Q2_SQL
    rows = run_pg(Q2_SQL)
    days = [r[0].day for r in rows]
    counts = [r[1] / 1e3 for r in rows]
    values = [int(r[2]) / 1e9 for r in rows]
    fig, ax1 = plt.subplots(figsize=(10, 4.5))
    ax1.plot(days, counts, color="#4C78A8", marker="s", label="Transfers (thousands)")
    ax1.set_xlabel("Day of September 2026 (CAT)")
    ax1.set_ylabel("Transfers per day (thousands; axis not from zero)")
    ax2 = ax1.twinx()
    ax2.plot(days, values, color="#F58518", marker="o", label="Value (billion RWF)")
    ax2.set_ylabel("Transfer value per day (billion RWF)")
    fig.legend(loc="upper right", bbox_to_anchor=(0.9, 0.88))
    ax1.set_title("Q2 Daily transfer count and value, September 2026")
    fig.tight_layout(); fig.savefig(f"{OUT}/q2_daily.png", dpi=150); plt.close(fig)


def q4_depth():
    files = [f for f in ("results/compare_bidir.json", "results/compare_baseline.json") if os.path.exists(f)]
    if not files:
        return print("skip Q4 plot: run compare.py first")
    data = json.load(open(files[0]))["outputs"]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for s in "ABCDEF":
        ys = [sum(r[1] for r in data[f"Q4-{s}-d{d}"]["postgres"]) for d in (4, 6, 8, 10)]
        ax.plot([4, 6, 8, 10], ys, marker="o", label=f"Set {s}")
    ax.set_xlabel("Maximum links (OWNS / USED_DEVICE)")
    ax.set_ylabel("Distinct other accounts reached")
    ax.set_title("Q4 Accounts reached versus depth")
    ax.set_xticks([4, 6, 8, 10]); ax.legend()
    fig.tight_layout(); fig.savefig(f"{OUT}/q4_depth.png", dpi=150); plt.close(fig)


def bench():
    p = "results/bench_summary.csv"
    if not os.path.exists(p):
        return print("skip benchmark plot")
    rows = list(csv.DictReader(open(p)))
    f = lambda v: float(v) if v not in ("", "None") else float("nan")
    labels = [f"{r['case']}{'*' if r['sql_version'] == 'bidir' else ''}" for r in rows]
    fig, ax = plt.subplots(figsize=(12, 5))
    x = range(len(rows))
    ax.bar([i - 0.2 for i in x], [f(r["pg_median_ms"]) for r in rows], 0.4, label="PostgreSQL")
    ax.bar([i + 0.2 for i in x], [f(r["neo_median_ms"]) for r in rows], 0.4, label="Neo4j")
    ax.set_yscale("log"); ax.set_ylabel("Median latency (ms, log scale)")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, rotation=60, ha="right")
    ax.set_title("Section 6.2 median latency per case (* = improved SQL)")
    ax.legend(); fig.tight_layout(); fig.savefig(f"{OUT}/bench_medians.png", dpi=150); plt.close(fig)


def scaling():
    p = "results/loadtest/combined_summary.csv"
    if not os.path.exists(p):
        return print("skip load-test plots")
    rows = list(csv.DictReader(open(p)))
    for metric, ylabel in (("throughput_rps", "Correct requests per second"), ("p95_ms", "p95 latency (ms)")):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
        for ax, wl in zip(axes, ("Q4d10", "Q7b6")):
            for eng, name in (("pg", "PostgreSQL"), ("neo", "Neo4j")):
                pts = sorted((int(r["clients"]), float(r[metric])) for r in rows
                             if r["engine"] == eng and r["workload"] == wl)
                if pts:
                    ax.plot(*zip(*pts), marker="o", label=name)
            ax.set_title(f"{wl}: {ylabel}"); ax.set_xlabel("Concurrent clients")
            ax.set_ylabel(ylabel); ax.set_xticks([1, 4, 8, 16]); ax.legend()
        fig.tight_layout(); fig.savefig(f"{OUT}/load_{metric}.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    for fn in (daily, q4_depth, bench, scaling):
        try:
            fn()
        except Exception as e:
            print(f"{fn.__name__} skipped: {e}")
    print("Charts in", OUT)
