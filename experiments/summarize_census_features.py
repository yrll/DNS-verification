#!/usr/bin/env python3
import csv
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CENSUS_ROOT = ROOT / "census"
OUT_DIR = ROOT / "experiments" / "results" / "census_features"
FEATURES_CSV = OUT_DIR / "all_dataset_features.csv"
DISTRIBUTION_CSV = OUT_DIR / "feature_distribution.csv"

DNS_CLASSES = {"IN", "CH", "HS"}
CORE_TYPES = ["A", "AAAA", "NS", "SOA", "MX", "TXT", "CNAME", "DNAME"]
GROUPS = {"files-100-500", "files-500-1000", "files-1000-plus", "top-10"}


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
            return parts[0], upper[index + 1], " ".join(parts[index + 2 :])
    return None


def domain_depth(name: str) -> int:
    return len([label for label in name.strip(".").split(".") if label and label != "@"])


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


def summarize_dataset(group: str, path: Path) -> dict:
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
                owner, rr_type, _ = parsed
                counts[rr_type] += 1
                file_total += 1
                if owner == "*" or owner.startswith("*."):
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
        "group": group,
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


def dataset_dirs():
    for group_dir in sorted(path for path in CENSUS_ROOT.iterdir() if path.is_dir()):
        if group_dir.name not in GROUPS:
            continue
        for dataset_dir in sorted(path for path in group_dir.iterdir() if path.is_dir()):
            yield group_dir.name, dataset_dir


def write_features(rows: list[dict]) -> None:
    fieldnames = [
        "group",
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
    with FEATURES_CSV.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_distribution(rows: list[dict]) -> None:
    by_group = defaultdict(Counter)
    total = Counter()
    for row in rows:
        by_group[row["group"]][row["category"]] += 1
        total[row["category"]] += 1
    categories = sorted(total)
    with DISTRIBUTION_CSV.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["group", "datasets", *categories])
        writer.writerow(["ALL", len(rows), *[total[category] for category in categories]])
        for group in sorted(by_group):
            writer.writerow([
                group,
                sum(by_group[group].values()),
                *[by_group[group][category] for category in categories],
            ])


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = [summarize_dataset(group, path) for group, path in dataset_dirs()]
    write_features(rows)
    write_distribution(rows)
    print(f"datasets: {len(rows)}")
    print(f"category distribution: {dict(Counter(row['category'] for row in rows))}")
    print(f"wrote {FEATURES_CSV}")
    print(f"wrote {DISTRIBUTION_CSV}")


if __name__ == "__main__":
    main()
