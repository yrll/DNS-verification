#!/usr/bin/env python3
"""Plot Aether-only revision experiment summaries."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "experiments" / "results" / "aether_revision"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-dir", type=Path, default=OUT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        import matplotlib.pyplot as plt
        import pandas as pd
    except ImportError as exc:
        raise SystemExit(f"plotting requires pandas and matplotlib: {exc}") from exc

    plot_dir = args.in_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    raw_path = args.in_dir / "aether_raw.csv"
    corr_path = args.in_dir / "feature_correlations.csv"
    if not raw_path.exists():
        raise SystemExit(f"missing raw CSV: {raw_path}")

    raw = pd.read_csv(raw_path)
    raw = raw[raw["status"] == "ok"].copy()
    if raw.empty:
        raise SystemExit("no ok rows to plot")
    for column in ["initial_total_ms", "incremental_ms", "full_no_io_ms"]:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")

    plt.figure(figsize=(10, 5))
    raw.boxplot(column="incremental_ms", by="scenario", rot=35)
    plt.suptitle("")
    plt.title("Aether Incremental Latency by Update Scenario")
    plt.ylabel("Latency (ms)")
    plt.tight_layout()
    plt.savefig(plot_dir / "incremental_latency_by_scenario.png", dpi=200)
    plt.close()

    speedup = raw[["scenario", "initial_total_ms", "incremental_ms"]].dropna().copy()
    speedup = speedup[speedup["incremental_ms"] > 0]
    speedup["speedup"] = speedup["initial_total_ms"] / speedup["incremental_ms"]
    if not speedup.empty:
        plt.figure(figsize=(10, 5))
        speedup.boxplot(column="speedup", by="scenario", rot=35)
        plt.suptitle("")
        plt.title("Aether Incremental Speedup vs Initial Verification")
        plt.ylabel("Speedup")
        plt.tight_layout()
        plt.savefig(plot_dir / "incremental_speedup_by_scenario.png", dpi=200)
        plt.close()

    if corr_path.exists():
        corr = pd.read_csv(corr_path)
        corr = corr[corr["metric"].isin(["incremental_ms", "initial_total_ms"])]
        corr["spearman"] = pd.to_numeric(corr["spearman"], errors="coerce")
        corr = corr.dropna(subset=["spearman"])
        if not corr.empty:
            pivot = corr.pivot(index="feature", columns="metric", values="spearman")
            pivot.plot(kind="bar", figsize=(10, 5))
            plt.title("Feature Correlation with Aether Latency")
            plt.ylabel("Spearman correlation")
            plt.tight_layout()
            plt.savefig(plot_dir / "feature_latency_correlations.png", dpi=200)
            plt.close()

    print(f"Wrote plots under {plot_dir}")


if __name__ == "__main__":
    main()
