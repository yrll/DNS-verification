#!/usr/bin/env python3
import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "census" / "files-100-500"
SUMMARY_CSV = ROOT / "experiments" / "results" / "incremental_100_500" / "summary.csv"
OUTPUT_CSV = ROOT / "experiments" / "results" / "incremental_100_500" / "untested_dataset_features.csv"

DNS_CLASSES = {"IN", "CH", "HS"}
CORE_TYPES = ["A", "AAAA", "NS", "SOA", "MX", "TXT", "CNAME", "DNAME"]


def strip_comment(line: str) -> str:
    return line.split(";", 1)[0].strip()


def parse_rr(line: str):
    line = strip_comment(line)
    if not line or line.startswith("$"):
        return None
    parts = line.split()
    upper = [part.upper() for part in parts]
    for index, part in enumerate(upper):
        if part in DNS_CLASSES and index + 1 < len(parts):
            owner = parts[0]
            rr_type = upper[index + 1]
            rdata = " ".join(parts[index + 2 :])
            return owner, rr_type, rdata
    return None


def domain_depth(name: str) -> int:
    return len([label for label in name.strip(".").split(".") if label and label != "@"])


def tested_datasets() -> set[str]:
    if not SUMMARY_CSV.exists():
        return set()
    tested = set()
    with SUMMARY_CSV.open(newline="", encoding="utf-8") as fp:
        for row in csv.DictReader(fp):
            if row.get("status") == "ok" and row.get("tool") in {"Aether", "VeriDNS"}:
                tested.add(row["dataset"])
    return tested


def classify(total: int, counts: Counter, wildcard: int, files: int) -> str:
    if total == 0:
        return "empty"
    rewrite = counts["CNAME"] + counts["DNAME"] + wildcard
    delegation = counts["NS"] + counts["SOA"]
    if rewrite / total >= 0.05 or counts["DNAME"] > 0 or wildcard > 0:
        return "rewrite-heavy"
    if delegation / total >= 0.30 or counts["NS"] >= files:
        return "delegation-heavy"
    return "common-case"


def summarize_dataset(path: Path) -> dict:
    counts = Counter()
    wildcard = 0
    depths = []
    per_file_totals = []
    unsupported = Counter()

    for zone_file in sorted(path.glob("*.txt")):
        file_total = 0
        with zone_file.open("r", encoding="utf-8", errors="replace") as fp:
            for line in fp:
                parsed = parse_rr(line)
                if not parsed:
                    continue
                owner, rr_type, rdata = parsed
                counts[rr_type] += 1
                file_total += 1
                if owner.startswith("*.") or owner == "*":
                    wildcard += 1
                depths.append(domain_depth(owner))
                if rr_type not in CORE_TYPES:
                    unsupported[rr_type] += 1
        per_file_totals.append(file_total)

    files = len(per_file_totals)
    total = sum(counts.values())
    rewrite = counts["CNAME"] + counts["DNAME"] + wildcard
    delegation = counts["NS"] + counts["SOA"]
    return {
        "dataset": path.name,
        "files": files,
        "total_rr": total,
        **{rr_type: counts[rr_type] for rr_type in CORE_TYPES},
        "wildcard": wildcard,
        "rewrite_rr": rewrite,
        "rewrite_ratio": f"{rewrite / total:.6f}" if total else "0",
        "delegation_rr": delegation,
        "delegation_ratio": f"{delegation / total:.6f}" if total else "0",
        "avg_rr_per_file": f"{total / files:.6f}" if files else "0",
        "max_rr_per_file": max(per_file_totals) if per_file_totals else 0,
        "avg_owner_depth": f"{sum(depths) / len(depths):.6f}" if depths else "0",
        "max_owner_depth": max(depths) if depths else 0,
        "unsupported_rr_types": ";".join(
            f"{rr_type}:{count}" for rr_type, count in sorted(unsupported.items())
        ),
        "category": classify(total, counts, wildcard, files),
    }


def main() -> None:
    tested = tested_datasets()
    datasets = sorted(path for path in DATASET_ROOT.iterdir() if path.is_dir())
    untested = [path for path in datasets if path.name not in tested]
    rows = [summarize_dataset(path) for path in untested]
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dataset",
        "files",
        "total_rr",
        *CORE_TYPES,
        "wildcard",
        "rewrite_rr",
        "rewrite_ratio",
        "delegation_rr",
        "delegation_ratio",
        "avg_rr_per_file",
        "max_rr_per_file",
        "avg_owner_depth",
        "max_owner_depth",
        "unsupported_rr_types",
        "category",
    ]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"candidate datasets: {len(datasets)}")
    print(f"tested datasets: {len(tested)} ({', '.join(sorted(tested))})")
    print(f"untested datasets: {len(rows)}")
    print(f"wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
