#!/usr/bin/env python3
"""Merge Aether-only revision experiment outputs into paper-friendly CSVs."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "experiments" / "results" / "aether_revision"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-dir", type=Path, default=OUT_ROOT)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def fnum(value):
    try:
        if value in ("", None):
            return None
        return float(value)
    except Exception:
        return None


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return math.nan
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * pct
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return values[low]
    return values[low] * (high - pos) + values[high] * (pos - low)


def geomean(values: list[float]) -> float:
    positives = [value for value in values if value > 0]
    if not positives:
        return math.nan
    return math.exp(sum(math.log(value) for value in positives) / len(positives))


def ci95(values: list[float]) -> tuple[float, float]:
    if len(values) < 2:
        return (math.nan, math.nan)
    mean = statistics.mean(values)
    sem = statistics.stdev(values) / math.sqrt(len(values))
    delta = 1.96 * sem
    return mean - delta, mean + delta


def summarize(values: list[float]) -> dict:
    if not values:
        return {}
    low, high = ci95(values)
    return {
        "count": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "geomean": geomean(values),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "min": min(values),
        "max": max(values),
        "ci95_low": low,
        "ci95_high": high,
    }


def rank(values: list[float]) -> list[float]:
    indexed = sorted((value, index) for index, value in enumerate(values))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][0] == indexed[i][0]:
            j += 1
        avg = (i + j) / 2 + 1
        for _, index in indexed[i : j + 1]:
            ranks[index] = avg
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return math.nan
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return math.nan
    return num / (denx * deny)


def spearman(xs: list[float], ys: list[float]) -> float:
    return pearson(rank(xs), rank(ys))


def main() -> None:
    args = parse_args()
    raw = [row for row in read_csv(args.in_dir / "aether_raw.csv") if row.get("status") == "ok"]
    features = {row["dataset_id"]: row for row in read_csv(args.in_dir / "features.csv")}

    dist_rows = []
    for (scenario, metric), values in collect_metric_groups(raw).items():
        row = {"scenario": scenario, "metric": metric}
        row.update(summarize(values))
        dist_rows.append(row)
    dist_fields = ["scenario", "metric", "count", "mean", "median", "geomean", "p90", "p95", "p99", "min", "max", "ci95_low", "ci95_high"]
    write_csv(args.in_dir / "summary_distribution.csv", dist_rows, dist_fields)

    corr_rows = []
    metrics = ["initial_total_ms", "incremental_ms", "full_no_io_ms", "num_lec", "affected_trace_count", "trace_count"]
    feature_names = ["rr_count", "zone_file_count", "CNAME", "DNAME", "wildcard", "NS", "SOA", "rewrite_density", "delegation_density", "avg_rr_per_file", "max_rr_per_file"]
    for metric in metrics:
        for feature_name in feature_names:
            xs, ys = [], []
            for row in raw:
                feature = features.get(row["dataset_id"])
                if not feature:
                    continue
                x = fnum(feature.get(feature_name))
                y = fnum(row.get(metric))
                if x is not None and y is not None:
                    xs.append(x)
                    ys.append(y)
            corr_rows.append({
                "metric": metric,
                "feature": feature_name,
                "n": len(xs),
                "pearson": pearson(xs, ys),
                "spearman": spearman(xs, ys),
            })
    write_csv(args.in_dir / "feature_correlations.csv", corr_rows, ["metric", "feature", "n", "pearson", "spearman"])

    case_rows = []
    for row in raw:
        initial = fnum(row.get("initial_total_ms"))
        incremental = fnum(row.get("incremental_ms"))
        full_no_io = fnum(row.get("full_no_io_ms"))
        case_rows.append({
            **row,
            "incremental_vs_initial_speedup": initial / incremental if initial and incremental and incremental > 0 else "",
            "incremental_vs_full_no_io_speedup": full_no_io / incremental if full_no_io and incremental and incremental > 0 else "",
        })
    write_csv(args.in_dir / "summary_by_case.csv", case_rows, list(case_rows[0].keys()) if case_rows else [])

    print(f"Wrote merged summaries under {args.in_dir}")


def collect_metric_groups(raw: list[dict]) -> dict[tuple[str, str], list[float]]:
    groups = defaultdict(list)
    for row in raw:
        for metric in ["initial_total_ms", "incremental_ms", "full_no_io_ms", "affected_trace_count", "trace_count", "num_lec"]:
            value = fnum(row.get(metric))
            if value is not None:
                groups[(row["scenario"], metric)].append(value)
                groups[("__ALL__", metric)].append(value)
    return groups


if __name__ == "__main__":
    main()
