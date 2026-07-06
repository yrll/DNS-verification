#!/usr/bin/env python3
"""Create a census copy without wildcard-owner and DNAME records."""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

import run_incremental_all as base


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "census"
DEFAULT_DST = ROOT / "census_no_wildcard_dname"
GROUPS = set(base.GROUPS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src-root", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--dst-root", type=Path, default=DEFAULT_DST)
    return parser.parse_args()


def should_drop(line: str) -> tuple[bool, str]:
    parsed = base.parse_rr_line(line)
    if not parsed:
        return False, ""
    owner, rr_type, _ = parsed
    if rr_type == "DNAME":
        return True, "DNAME"
    if owner == "*" or owner.startswith("*."):
        return True, "wildcard"
    return False, ""


def sanitize_file(src: Path, dst: Path) -> dict[str, int]:
    counts = {"total_lines": 0, "kept_lines": 0, "dropped_dname": 0, "dropped_wildcard": 0}
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("r", encoding="utf-8", errors="replace") as inp, dst.open("w", encoding="utf-8") as out:
        for line in inp:
            counts["total_lines"] += 1
            drop, reason = should_drop(line)
            if drop:
                if reason == "DNAME":
                    counts["dropped_dname"] += 1
                elif reason == "wildcard":
                    counts["dropped_wildcard"] += 1
                continue
            counts["kept_lines"] += 1
            out.write(line)
    return counts


def main() -> None:
    args = parse_args()
    src_root = args.src_root.resolve()
    dst_root = args.dst_root.resolve()
    if dst_root.exists():
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for group_dir in sorted(path for path in src_root.iterdir() if path.is_dir() and path.name in GROUPS):
        for dataset_dir in sorted(path for path in group_dir.iterdir() if path.is_dir()):
            aggregate = {
                "group": group_dir.name,
                "dataset": dataset_dir.name,
                "files": 0,
                "total_lines": 0,
                "kept_lines": 0,
                "dropped_dname": 0,
                "dropped_wildcard": 0,
            }
            for src_file in sorted(dataset_dir.glob("*.txt")):
                rel = src_file.relative_to(src_root)
                counts = sanitize_file(src_file, dst_root / rel)
                aggregate["files"] += 1
                for key in ["total_lines", "kept_lines", "dropped_dname", "dropped_wildcard"]:
                    aggregate[key] += counts[key]
            rows.append(aggregate)

    report_path = dst_root / "sanitize_report.csv"
    with report_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["group", "dataset", "files", "total_lines", "kept_lines", "dropped_dname", "dropped_wildcard"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {dst_root}")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
