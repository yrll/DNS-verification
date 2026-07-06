#!/usr/bin/env python3
"""Plot Aether vs VeriDNS incremental experiment results."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "experiments" / "results" / "incremental_all"
DEFAULT_OUT = DEFAULT_RESULTS / "plots"
GROUP_ORDER = ["files-100-500", "files-500-1000", "files-1000-plus", "top-10"]
SCENARIO_ORDER = ["A_ADD", "A_UPDATE", "NS_UPDATE", "CNAME_UPDATE"]
SCENARIO_COLORS = {
    "A_ADD": "#4C78A8",
    "A_UPDATE": "#F58518",
    "NS_UPDATE": "#54A24B",
    "CNAME_UPDATE": "#B279A2",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def load_data(results_dir: Path) -> pd.DataFrame:
    cases = pd.read_csv(results_dir / "advantage_by_case.csv")
    features = pd.read_csv(results_dir / "features.csv")
    size_cols = ["dataset_id", "files", "total_rr"]
    data = cases.merge(features[size_cols], on="dataset_id", how="left")
    if "target_ratio" not in data.columns:
        data["target_ratio"] = "single"
    data["target_ratio"] = data["target_ratio"].astype(str)
    data["incremental_speedup"] = pd.to_numeric(data["incremental_speedup"], errors="coerce")
    data["aether_wins"] = data["incremental_speedup"] > 1.0
    data["group"] = pd.Categorical(data["group"], categories=GROUP_ORDER, ordered=True)
    data["scenario"] = pd.Categorical(data["scenario"], categories=SCENARIO_ORDER, ordered=True)
    return data.dropna(subset=["incremental_speedup"])


def savefig(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=220)
    plt.close()


def plot_winrate_heatmap(data: pd.DataFrame, path: Path, title: str, group_rows: bool) -> None:
    if group_rows:
        rows = GROUP_ORDER
        table = pd.DataFrame(index=rows, columns=SCENARIO_ORDER, dtype=float)
        labels = pd.DataFrame(index=rows, columns=SCENARIO_ORDER, dtype=object)
        for group in rows:
            for scenario in SCENARIO_ORDER:
                subset = data[(data["group"] == group) & (data["scenario"] == scenario)]
                wins = int(subset["aether_wins"].sum())
                total = int(len(subset))
                table.loc[group, scenario] = wins / total if total else np.nan
                labels.loc[group, scenario] = f"{wins}/{total}" if total else "n/a"
    else:
        rows = ["all"]
        table = pd.DataFrame(index=rows, columns=SCENARIO_ORDER, dtype=float)
        labels = pd.DataFrame(index=rows, columns=SCENARIO_ORDER, dtype=object)
        for scenario in SCENARIO_ORDER:
            subset = data[data["scenario"] == scenario]
            wins = int(subset["aether_wins"].sum())
            total = int(len(subset))
            table.loc["all", scenario] = wins / total if total else np.nan
            labels.loc["all", scenario] = f"{wins}/{total}" if total else "n/a"

    fig_width = 8.8
    fig_height = 1.9 + 0.65 * len(rows)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    masked = np.ma.masked_invalid(table.to_numpy(dtype=float))
    image = ax.imshow(masked, cmap="RdBu_r", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(SCENARIO_ORDER)), labels=SCENARIO_ORDER)
    ax.set_yticks(range(len(rows)), labels=rows)
    ax.set_title(title)
    ax.set_xlabel("Incremental scenario")
    ax.set_ylabel("Dataset scale" if group_rows else "")
    for i in range(len(rows)):
        for j in range(len(SCENARIO_ORDER)):
            value = table.iloc[i, j]
            text = labels.iloc[i, j]
            color = "white" if not pd.isna(value) and (value < 0.25 or value > 0.75) else "black"
            ax.text(j, i, text, ha="center", va="center", color=color, fontsize=10)
    cbar = fig.colorbar(image, ax=ax)
    cbar.set_label("Aether faster fraction")
    ax.text(
        0.5,
        -0.35 if group_rows else -0.75,
        "Cell text: Aether faster cases / paired successful cases. Red favors Aether; blue favors VeriDNS.",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=9,
    )
    savefig(path)


def plot_speedup_boxplot(data: pd.DataFrame, path: Path, title: str) -> None:
    values = [data[data["scenario"] == scenario]["incremental_speedup"].to_numpy() for scenario in SCENARIO_ORDER]
    fig, ax = plt.subplots(figsize=(8.8, 5.0))
    bp = ax.boxplot(values, labels=SCENARIO_ORDER, patch_artist=True, showfliers=True)
    for patch, scenario in zip(bp["boxes"], SCENARIO_ORDER):
        patch.set_facecolor(SCENARIO_COLORS[scenario])
        patch.set_alpha(0.55)
    ax.axhline(1.0, color="#222222", linestyle="--", linewidth=1.2)
    ax.set_yscale("log")
    ax.set_title(title)
    ax.set_xlabel("Incremental scenario")
    ax.set_ylabel("Speedup = VeriDNS incremental / Aether incremental")
    ax.text(0.02, 0.96, ">1: Aether faster\n<1: VeriDNS faster", transform=ax.transAxes, va="top", fontsize=9)
    savefig(path)


def plot_size_scatter(data: pd.DataFrame, path: Path, title: str, size_col: str) -> None:
    fig, ax = plt.subplots(figsize=(8.8, 5.4))
    for scenario in SCENARIO_ORDER:
        subset = data[data["scenario"] == scenario]
        if subset.empty:
            continue
        ax.scatter(
            subset[size_col],
            subset["incremental_speedup"],
            label=scenario,
            s=32,
            alpha=0.72,
            color=SCENARIO_COLORS[scenario],
            edgecolors="none",
        )
    ax.axhline(1.0, color="#222222", linestyle="--", linewidth=1.2)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_title(title)
    ax.set_xlabel("Zone file count" if size_col == "files" else "Total RR count")
    ax.set_ylabel("Speedup = VeriDNS incremental / Aether incremental")
    ax.legend(title="Scenario", frameon=False, ncol=2)
    savefig(path)


def plot_group_outputs(data: pd.DataFrame, out_dir: Path) -> None:
    plot_winrate_heatmap(
        data,
        out_dir / "all" / "winrate_heatmap_by_scale.png",
        "Aether win rate by dataset scale and incremental scenario",
        group_rows=True,
    )
    plot_winrate_heatmap(
        data,
        out_dir / "all" / "winrate_heatmap_all.png",
        "Aether win rate across all datasets",
        group_rows=False,
    )
    plot_speedup_boxplot(data, out_dir / "all" / "speedup_boxplot_by_scenario.png", "Speedup distribution across all datasets")
    plot_size_scatter(data, out_dir / "all" / "speedup_vs_zone_files.png", "Speedup vs dataset size", "files")
    plot_size_scatter(data, out_dir / "all" / "speedup_vs_total_rr.png", "Speedup vs total RR count", "total_rr")

    for group in GROUP_ORDER:
        subset = data[data["group"] == group]
        if subset.empty:
            continue
        group_dir = out_dir / group
        plot_winrate_heatmap(
            subset,
            group_dir / "winrate_heatmap.png",
            f"Aether win rate by scenario: {group}",
            group_rows=False,
        )
        plot_speedup_boxplot(
            subset,
            group_dir / "speedup_boxplot_by_scenario.png",
            f"Speedup distribution by scenario: {group}",
        )
        plot_size_scatter(
            subset,
            group_dir / "speedup_vs_zone_files.png",
            f"Speedup vs dataset size: {group}",
            "files",
        )


def plot_ratio_outputs(data: pd.DataFrame, out_dir: Path) -> None:
    for ratio in sorted(data["target_ratio"].unique()):
        ratio_data = data[data["target_ratio"] == ratio]
        ratio_dir = out_dir / f"ratio_{ratio}"
        plot_group_outputs(ratio_data, ratio_dir)


def write_plot_summary(data: pd.DataFrame, out_dir: Path) -> None:
    rows = []
    for ratio, ratio_data in sorted(data.groupby("target_ratio")):
        for group_name, subset in [("all", ratio_data), *[(group, ratio_data[ratio_data["group"] == group]) for group in GROUP_ORDER]]:
            for scenario in SCENARIO_ORDER:
                scenario_data = subset[subset["scenario"] == scenario]
                if scenario_data.empty:
                    continue
                speedups = scenario_data["incremental_speedup"].to_numpy(dtype=float)
                rows.append({
                    "target_ratio": ratio,
                    "group": group_name,
                    "scenario": scenario,
                    "cases": len(scenario_data),
                    "aether_faster": int(scenario_data["aether_wins"].sum()),
                    "veridns_faster": int((~scenario_data["aether_wins"]).sum()),
                    "aether_win_rate": scenario_data["aether_wins"].mean(),
                    "median_speedup": float(np.median(speedups)),
                    "mean_speedup": float(np.mean(speedups)),
                })
    pd.DataFrame(rows).to_csv(out_dir / "plot_summary.csv", index=False)


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    data = load_data(args.results_dir)
    if data.empty:
        raise SystemExit("no paired successful cases to plot")
    if set(data["target_ratio"].unique()) == {"single"}:
        plot_group_outputs(data, out_dir)
    else:
        plot_ratio_outputs(data, out_dir)
    write_plot_summary(data, out_dir)
    print(f"wrote plots to {out_dir}")


if __name__ == "__main__":
    main()
