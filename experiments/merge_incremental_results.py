#!/usr/bin/env python3
"""Merge staged incremental experiment outputs into one result directory."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from run_incremental_all import SUMMARY_FIELDS, write_advantages, write_csv


ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = ROOT / "experiments" / "results"
DEFAULT_INPUTS = [
    RESULTS_ROOT / "incremental_all_files_100_500",
    RESULTS_ROOT / "incremental_all_files_500_1000",
    RESULTS_ROOT / "incremental_all_files_1000_plus",
    RESULTS_ROOT / "incremental_all_top_10_v2",
]
DEFAULT_OUT = RESULTS_ROOT / "incremental_all"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", action="append", type=Path, default=[])
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def unique_rows(rows: list[dict], keys: list[str]) -> list[dict]:
    seen = set()
    output = []
    for row in rows:
        key = tuple(row.get(field, "") for field in keys)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def main() -> None:
    args = parse_args()
    input_dirs = args.input_dir or DEFAULT_INPUTS
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    features = []
    updates = []
    skipped = []
    summary = []
    for input_dir in input_dirs:
        features.extend(read_rows(input_dir / "features.csv"))
        updates.extend(read_rows(input_dir / "updates.csv"))
        skipped.extend(read_rows(input_dir / "skipped_updates.csv"))
        summary.extend(read_rows(input_dir / "summary.csv"))

    features = unique_rows(features, ["dataset_id"])
    updates = unique_rows(updates, ["dataset", "zone_file", "scenario", "op", "domain", "type", "rdata"])
    skipped = unique_rows(skipped, ["dataset_id", "scenario"])
    summary = unique_rows(summary, ["tool", "dataset_id", "scenario"])

    if not features:
        raise SystemExit("no features.csv rows found")

    feature_fields = list(features[0].keys())
    write_csv(out_dir / "features.csv", features, feature_fields)
    write_csv(out_dir / "updates.csv", updates, ["dataset", "zone_file", "scenario", "op", "domain", "type", "rdata"])
    write_csv(out_dir / "skipped_updates.csv", skipped, ["group", "dataset", "dataset_id", "scenario", "status", "skipped_reason"])
    write_csv(out_dir / "summary.csv", summary, SUMMARY_FIELDS)
    write_csv(out_dir / "veridns_raw.csv", [row for row in summary if row["tool"] == "VeriDNS"], SUMMARY_FIELDS)
    write_csv(out_dir / "aether_raw.csv", [row for row in summary if row["tool"] == "Aether"], SUMMARY_FIELDS)
    write_advantages(summary, {row["dataset_id"]: row for row in features}, out_dir)

    status_counts = defaultdict(int)
    for row in summary:
        status_counts[row["status"]] += 1
    print(f"merged {len(features)} datasets, {len(summary)} summary rows into {out_dir}")
    print(dict(sorted(status_counts.items())))


if __name__ == "__main__":
    main()
