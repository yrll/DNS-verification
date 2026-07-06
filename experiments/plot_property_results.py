#!/usr/bin/env python3
"""Plot performance and verdict consistency for property-aware experiments."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import plot_incremental_results as perf_plots


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "experiments" / "results" / "incremental_property_all"
DEFAULT_OUT = DEFAULT_RESULTS / "plots"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--mismatch-as-aether-win",
        action="store_true",
        help="For performance plots, count VeriDNS/Aether verdict mismatches as Aether wins.",
    )
    return parser.parse_args()


def write_perf_compatible(results_dir: Path, tmp_dir: Path, mismatch_as_aether_win: bool) -> None:
    summary = pd.read_csv(results_dir / "summary.csv")
    features = pd.read_csv(results_dir / "features.csv")
    rows = []
    category = dict(zip(features["dataset_id"], features["category"]))
    for _, row in summary.iterrows():
        if row["status"] != "ok":
            continue
        a = pd.to_numeric(row["aether_incremental_ms"], errors="coerce")
        v = pd.to_numeric(row["veridns_incremental_ms"], errors="coerce")
        f = pd.to_numeric(row["veridns_full_update_ms"], errors="coerce")
        if pd.isna(a) or pd.isna(v) or a <= 0:
            continue
        speedup = v / a
        if mismatch_as_aether_win and str(row.get("veridns_matches_aether", "")) == "False":
            speedup = max(speedup, 1.000001)
        rows.append({
            "group": row["group"],
            "dataset": row["dataset"],
            "dataset_id": row["dataset_id"],
            "category": category.get(row["dataset_id"], ""),
            "scenario": row["scenario"],
            "aether_incremental_ms": a,
            "veridns_incremental_ms": v,
            "veridns_full_update_ms": f if not pd.isna(f) else "",
            "incremental_speedup": speedup,
            "full_update_speedup": f / a if not pd.isna(f) and a > 0 else "",
        })
    tmp_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(tmp_dir / "advantage_by_case.csv", index=False)
    features.to_csv(tmp_dir / "features.csv", index=False)


def plot_match_rate_by_scale(consistency: pd.DataFrame, out_dir: Path) -> None:
    groups = perf_plots.GROUP_ORDER
    scenarios = perf_plots.SCENARIO_ORDER
    table = pd.DataFrame(index=groups, columns=scenarios, dtype=float)
    labels = pd.DataFrame(index=groups, columns=scenarios, dtype=object)
    for group in groups:
        for scenario in scenarios:
            subset = consistency[(consistency["group"] == group) & (consistency["scenario"] == scenario)]
            if subset.empty:
                table.loc[group, scenario] = np.nan
                labels.loc[group, scenario] = "n/a"
                continue
            matches = subset["matches_aether"].astype(str).eq("True").sum()
            total = len(subset)
            table.loc[group, scenario] = matches / total
            labels.loc[group, scenario] = f"{matches}/{total}"

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    image = ax.imshow(np.ma.masked_invalid(table.to_numpy(dtype=float)), cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(scenarios)), labels=scenarios)
    ax.set_yticks(range(len(groups)), labels=groups)
    ax.set_title("VeriDNS verdict match rate against Aether")
    ax.set_xlabel("Incremental scenario")
    ax.set_ylabel("Dataset scale")
    for i in range(len(groups)):
        for j in range(len(scenarios)):
            value = table.iloc[i, j]
            color = "white" if not pd.isna(value) and value < 0.35 else "black"
            ax.text(j, i, labels.iloc[i, j], ha="center", va="center", color=color, fontsize=10)
    cbar = fig.colorbar(image, ax=ax)
    cbar.set_label("Match fraction")
    perf_plots.savefig(out_dir / "consistency_match_rate_by_scale.png")


def plot_mismatch_by_feature(consistency: pd.DataFrame, features: pd.DataFrame, out_dir: Path) -> None:
    data = consistency.merge(features[["dataset_id", "category"]], on="dataset_id", how="left")
    cats = ["common-case", "delegation-heavy", "rewrite-heavy"]
    scenarios = perf_plots.SCENARIO_ORDER
    table = pd.DataFrame(index=cats, columns=scenarios, dtype=float)
    for cat in cats:
        for scenario in scenarios:
            subset = data[(data["category"] == cat) & (data["scenario"] == scenario)]
            table.loc[cat, scenario] = subset["matches_aether"].astype(str).ne("True").sum()
    fig, ax = plt.subplots(figsize=(8.8, 3.8))
    image = ax.imshow(table.to_numpy(dtype=float), cmap="Reds", aspect="auto")
    ax.set_xticks(range(len(scenarios)), labels=scenarios)
    ax.set_yticks(range(len(cats)), labels=cats)
    ax.set_title("Mismatch count by dataset feature and scenario")
    for i in range(len(cats)):
        for j in range(len(scenarios)):
            ax.text(j, i, str(int(table.iloc[i, j])), ha="center", va="center", color="black")
    cbar = fig.colorbar(image, ax=ax)
    cbar.set_label("Mismatches")
    perf_plots.savefig(out_dir / "mismatch_count_by_feature.png")


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = out_dir / "_perf_input"
    write_perf_compatible(args.results_dir, tmp_dir, args.mismatch_as_aether_win)
    data = perf_plots.load_data(tmp_dir)
    if not data.empty:
        perf_plots.plot_group_outputs(data, out_dir / "performance")
        perf_plots.write_plot_summary(data, out_dir / "performance")
    consistency = pd.read_csv(args.results_dir / "verdict_consistency.csv")
    features = pd.read_csv(args.results_dir / "features.csv")
    if not consistency.empty:
        plot_match_rate_by_scale(consistency, out_dir)
        plot_mismatch_by_feature(consistency, features, out_dir)
        mismatches = consistency[consistency["matches_aether"].astype(str) != "True"]
        mismatches.to_csv(out_dir / "mismatch_table.csv", index=False)
    print(f"wrote plots to {out_dir}")


if __name__ == "__main__":
    main()
