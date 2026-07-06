#!/usr/bin/env python3
import argparse
import csv
from collections import Counter
from pathlib import Path


DNS_CLASSES = {"IN", "CH", "HS"}
DEFAULT_DATASETS = ["12", "13", "14", "15", "all_correct", "all_correct_10000", "test_ini"]


def strip_comment(line):
    return line.split(";", 1)[0].strip()


def get_rr_type(line):
    line = strip_comment(line)
    if not line or line.startswith("$"):
        return None

    parts = line.split()
    if len(parts) < 2:
        return None

    upper_parts = [part.upper() for part in parts]
    for index, part in enumerate(upper_parts):
        if part in DNS_CLASSES and index + 1 < len(upper_parts):
            return upper_parts[index + 1]

    return None


def count_zone_file(file_path):
    counts = Counter()
    with file_path.open("r", encoding="utf-8", errors="replace") as zone_file:
        for line in zone_file:
            rr_type = get_rr_type(line)
            if rr_type:
                counts[rr_type] += 1
    return counts


def count_dataset(dataset_path):
    dataset_counts = Counter()
    file_counts = []

    for zone_file in sorted(dataset_path.glob("*.txt")):
        counts = count_zone_file(zone_file)
        dataset_counts.update(counts)
        file_counts.append((zone_file.name, counts))

    return dataset_counts, file_counts


def write_csv(output_path, dataset_results, rr_types, summary_only=False):
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        if summary_only:
            writer.writerow(["dataset", "files", "total", *rr_types])
        else:
            writer.writerow(["dataset", "file", "total", *rr_types])

        for dataset_name, dataset_counts, file_counts in dataset_results:
            if summary_only:
                writer.writerow([
                    dataset_name,
                    len(file_counts),
                    sum(dataset_counts.values()),
                    *[dataset_counts.get(rr_type, 0) for rr_type in rr_types],
                ])
                continue

            writer.writerow([
                dataset_name,
                "__TOTAL__",
                sum(dataset_counts.values()),
                *[dataset_counts.get(rr_type, 0) for rr_type in rr_types],
            ])
            for file_name, counts in file_counts:
                writer.writerow([
                    dataset_name,
                    file_name,
                    sum(counts.values()),
                    *[counts.get(rr_type, 0) for rr_type in rr_types],
                ])


def append_text(output_path, dataset_results, rr_types):
    with output_path.open("a", encoding="utf-8") as text_file:
        for dataset_name, dataset_counts, file_counts in dataset_results:
            text_file.write("\t".join([
                dataset_name,
                str(len(file_counts)),
                str(sum(dataset_counts.values())),
                *[str(dataset_counts.get(rr_type, 0)) for rr_type in rr_types],
            ]))
            text_file.write("\n")


def print_summary(dataset_results, rr_types):
    header = ["dataset", "files", "total", *rr_types]
    rows = []

    for dataset_name, dataset_counts, file_counts in dataset_results:
        rows.append([
            dataset_name,
            str(len(file_counts)),
            str(sum(dataset_counts.values())),
            *[str(dataset_counts.get(rr_type, 0)) for rr_type in rr_types],
        ])

    widths = [
        max(len(row[index]) for row in [header, *rows])
        for index in range(len(header))
    ]

    def format_row(row):
        return "  ".join(value.rjust(width) for value, width in zip(row, widths))

    print(format_row(header))
    print(format_row(["-" * width for width in widths]))
    for row in rows:
        print(format_row(row))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Count DNS resource record types in xmu_dataset directories."
    )
    parser.add_argument(
        "datasets",
        nargs="*",
        default=DEFAULT_DATASETS,
        help="Dataset directory names or paths. Defaults to common xmu_dataset directories.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="rr_type_counts.csv",
        help="CSV output path. Defaults to rr_type_counts.csv in the current directory.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Write only one aggregate CSV row per dataset directory.",
    )
    parser.add_argument(
        "--text-output",
        action="store_true",
        help="Append one tab-separated aggregate row per dataset instead of writing CSV.",
    )
    parser.add_argument(
        "--rr-types",
        nargs="*",
        help="RR type columns to use for CSV/text output. Defaults to types found in the input datasets.",
    )
    parser.add_argument(
        "--print-rr-types",
        action="store_true",
        help="Print discovered RR types one per line and do not write output.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    base_path = Path(__file__).resolve().parent
    dataset_results = []
    all_rr_types = set()

    for dataset in args.datasets:
        dataset_path = Path(dataset)
        if not dataset_path.is_absolute():
            dataset_path = base_path / dataset_path

        if not dataset_path.is_dir():
            print(f"skip missing dataset: {dataset_path}")
            continue

        dataset_counts, file_counts = count_dataset(dataset_path)
        if not file_counts:
            print(f"skip empty dataset: {dataset_path}")
            continue
        dataset_results.append((dataset_path.name, dataset_counts, file_counts))
        all_rr_types.update(dataset_counts)

    if not dataset_results:
        raise SystemExit("no valid dataset directories found")

    rr_types = args.rr_types if args.rr_types is not None else sorted(all_rr_types)
    if args.print_rr_types:
        for rr_type in rr_types:
            print(rr_type)
        return

    print_summary(dataset_results, rr_types)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    if args.text_output:
        append_text(output_path, dataset_results, rr_types)
        print(f"\nText appended to: {output_path}")
    else:
        write_csv(output_path, dataset_results, rr_types, summary_only=args.summary_only)
        print(f"\nCSV saved to: {output_path}")


if __name__ == "__main__":
    main()
