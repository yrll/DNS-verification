#!/usr/bin/env python3
"""Compare original and no-wildcard/DNAME property-aware results."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ORIGINAL = ROOT / "experiments" / "results" / "incremental_property_all"
DEFAULT_SANITIZED = ROOT / "experiments" / "results" / "incremental_property_no_wildcard_dname"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-dir", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--sanitized-dir", type=Path, default=DEFAULT_SANITIZED)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def consistency_summary(name: str, result_dir: Path) -> dict:
    summary = read_rows(result_dir / "summary.csv")
    verdict = read_rows(result_dir / "verdict_consistency.csv")
    mismatches = [row for row in verdict if row["matches_aether"] != "True"]
    return {
        "dataset": name,
        "cases": len(summary),
        "ok_cases": sum(1 for row in summary if row["status"] == "ok"),
        "case_match_true": sum(1 for row in summary if row["veridns_matches_aether"] == "True"),
        "case_match_false": sum(1 for row in summary if row["veridns_matches_aether"] == "False"),
        "case_uncompared": sum(1 for row in summary if row["veridns_matches_aether"] == ""),
        "verdict_rows": len(verdict),
        "verdict_mismatches": len(mismatches),
        "mismatch_rewrite_blackholing": sum(1 for row in mismatches if row["property"] == "rewrite_blackholing"),
        "mismatch_lame_delegation": sum(1 for row in mismatches if row["property"] == "lame_delegation"),
        "mismatch_rewrites": sum(1 for row in mismatches if row["property"] == "rewrites"),
    }


def winrate_rows(name: str, result_dir: Path) -> list[dict]:
    rows = read_rows(result_dir / "advantage_by_case.csv")
    buckets = {}
    for row in rows:
        scenario = row["scenario"]
        buckets.setdefault(scenario, []).append(float(row["incremental_speedup"]))
    output = []
    for scenario, values in sorted(buckets.items()):
        output.append({
            "dataset": name,
            "scenario": scenario,
            "cases": len(values),
            "aether_faster": sum(1 for value in values if value > 1),
            "veridns_faster": sum(1 for value in values if value <= 1),
            "aether_win_rate": sum(1 for value in values if value > 1) / len(values) if values else "",
        })
    return output


def main() -> None:
    args = parse_args()
    original = args.original_dir.resolve()
    sanitized = args.sanitized_dir.resolve()
    write_csv(
        sanitized / "original_vs_sanitized_consistency.csv",
        [consistency_summary("original", original), consistency_summary("no_wildcard_dname", sanitized)],
        [
            "dataset", "cases", "ok_cases", "case_match_true", "case_match_false",
            "case_uncompared", "verdict_rows", "verdict_mismatches",
            "mismatch_rewrite_blackholing", "mismatch_lame_delegation", "mismatch_rewrites",
        ],
    )
    write_csv(
        sanitized / "original_vs_sanitized_winrate.csv",
        [*winrate_rows("original", original), *winrate_rows("no_wildcard_dname", sanitized)],
        ["dataset", "scenario", "cases", "aether_faster", "veridns_faster", "aether_win_rate"],
    )
    print(f"wrote comparison CSVs to {sanitized}")


if __name__ == "__main__":
    main()
