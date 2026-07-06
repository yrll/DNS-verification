#!/usr/bin/env python3
"""Merge staged property-aware incremental experiment outputs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from run_incremental_property_all import RAW_FIELDS, SUMMARY_FIELDS, write_advantages, write_csv


ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = ROOT / "experiments" / "results"
DEFAULT_INPUTS = [
    RESULTS_ROOT / "incremental_property_files_100_500",
    RESULTS_ROOT / "incremental_property_files_500_1000",
    RESULTS_ROOT / "incremental_property_files_1000_plus",
    RESULTS_ROOT / "incremental_property_top_10",
]
DEFAULT_OUT = RESULTS_ROOT / "incremental_property_all"
CONSISTENCY_FIELDS = ["group", "dataset", "dataset_id", "scenario", "property", "aether_pass", "veridns_pass", "matches_aether", "aether_errors", "veridns_errors", "oracle"]


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


def unique(rows: list[dict], keys: list[str]) -> list[dict]:
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

    features, updates, skips, summary, aether, veridns, consistency = [], [], [], [], [], [], []
    for input_dir in input_dirs:
        features.extend(read_rows(input_dir / "features.csv"))
        updates.extend(read_rows(input_dir / "updates.csv"))
        skips.extend(read_rows(input_dir / "skipped_updates.csv"))
        summary.extend(read_rows(input_dir / "summary.csv"))
        aether.extend(read_rows(input_dir / "aether_raw.csv"))
        veridns.extend(read_rows(input_dir / "veridns_raw.csv"))
        consistency.extend(read_rows(input_dir / "verdict_consistency.csv"))

    features = unique(features, ["dataset_id"])
    updates = unique(updates, ["dataset", "zone_file", "scenario", "op", "domain", "type", "rdata"])
    skips = unique(skips, ["dataset_id", "scenario"])
    summary = unique(summary, ["dataset_id", "scenario"])
    aether = unique(aether, ["tool", "dataset_id", "scenario"])
    veridns = unique(veridns, ["tool", "dataset_id", "scenario"])
    consistency = unique(consistency, ["dataset_id", "scenario", "property"])

    write_csv(out_dir / "features.csv", features, list(features[0].keys()))
    write_csv(out_dir / "updates.csv", updates, ["dataset", "zone_file", "scenario", "op", "domain", "type", "rdata"])
    write_csv(out_dir / "skipped_updates.csv", skips, ["group", "dataset", "dataset_id", "scenario", "status", "skipped_reason"])
    write_csv(out_dir / "summary.csv", summary, SUMMARY_FIELDS)
    write_csv(out_dir / "aether_raw.csv", aether, RAW_FIELDS)
    write_csv(out_dir / "veridns_raw.csv", veridns, RAW_FIELDS)
    write_csv(out_dir / "verdict_consistency.csv", consistency, CONSISTENCY_FIELDS)
    write_advantages(summary, {row["dataset_id"]: row for row in features}, out_dir)

    print(f"merged {len(features)} datasets and {len(summary)} cases into {out_dir}")


if __name__ == "__main__":
    main()
