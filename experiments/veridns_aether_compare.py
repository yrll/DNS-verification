#!/usr/bin/env python3
"""Run a same-workload performance comparison between Aether and VeriDNS.

The script treats each dataset directory as one DNS configuration containing a
metadata.json plus the zone files referenced by that metadata. Aether is run via
its CLI. VeriDNS is run in-process by reusing its ZoneFileParser, ZoneGraph and
check_self implementation.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
AETHER_DIR = ROOT / "aether" / "dnsverify"
VERIDNS_SRC = ROOT / "VeriDNS" / "src_muilt"


@dataclass(frozen=True)
class Dataset:
    name: str
    path: Path
    metadata: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Aether and VeriDNS on identical metadata datasets."
    )
    parser.add_argument(
        "datasets",
        nargs="*",
        type=Path,
        default=[
            ROOT / "VeriDNS" / "xmu_dataset" / "12",
            ROOT / "VeriDNS" / "xmu_dataset" / "13",
            ROOT / "VeriDNS" / "xmu_dataset" / "14",
            ROOT / "VeriDNS" / "xmu_dataset" / "15",
            ROOT / "VeriDNS" / "xmu_dataset" / "all_correct",
        ],
        help="Dataset directories. Each must contain metadata.json.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "experiments" / "results" / "veridns_aether",
        help="Directory for generated CSV, traces and summary files.",
    )
    parser.add_argument(
        "--aether-bin",
        type=Path,
        default=None,
        help="Path to the Aether dnsv binary.",
    )
    parser.add_argument(
        "--build-aether",
        action="store_true",
        help="Build Aether in release mode before running.",
    )
    parser.add_argument(
        "--skip-aether",
        action="store_true",
        help="Only run the VeriDNS side.",
    )
    parser.add_argument(
        "--skip-veridns",
        action="store_true",
        help="Only run the Aether side.",
    )
    return parser.parse_args()


def load_datasets(paths: Iterable[Path]) -> list[Dataset]:
    datasets: list[Dataset] = []
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else ROOT / raw_path
        metadata = path / "metadata.json"
        if not metadata.exists():
            raise FileNotFoundError(f"missing metadata.json: {metadata}")
        datasets.append(Dataset(path.name, path, metadata))
    return datasets


def write_aether_input(datasets: list[Dataset], out_dir: Path) -> Path:
    csv_path = out_dir / "aether_input.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["zone", "metadata"])
        for dataset in datasets:
            writer.writerow([dataset.name, str(dataset.metadata)])
    return csv_path


def build_aether() -> None:
    if shutil.which("cargo") is None:
        raise RuntimeError("cargo not found. Install Rust/Cargo before using --build-aether.")
    subprocess.run(["cargo", "build", "--release"], cwd=AETHER_DIR, check=True)


def default_aether_binary() -> Path:
    native = AETHER_DIR / "target" / "release" / "dnsv"
    windows = AETHER_DIR / "target" / "release" / "dnsv.exe"
    if native.exists():
        return native
    return windows


def run_aether(aether_bin: Path, input_csv: Path, out_dir: Path) -> Path:
    if not aether_bin.exists():
        raise FileNotFoundError(
            f"Aether binary not found: {aether_bin}. "
            "Run with --build-aether or build aether/dnsverify first."
        )
    if not os.access(aether_bin, os.X_OK):
        raise PermissionError(f"Aether binary is not executable on this platform: {aether_bin}")
    output_csv = out_dir / "aether.csv"
    trace_dir = out_dir / "aether_traces"
    env = os.environ.copy()
    env.setdefault("RUST_LOG", "warn")
    cmd = [
        str(aether_bin),
        "--output",
        str(output_csv),
        "--trace",
        str(trace_dir),
        "c",
        str(input_csv),
    ]
    subprocess.run(cmd, cwd=AETHER_DIR, env=env, check=True)
    return output_csv


def import_veridns_modules():
    missing = [
        package
        for package, module in [
            ("networkx", "networkx"),
            ("dnspython", "dns"),
            ("pandas", "pandas"),
            ("psutil", "psutil"),
            ("PyYAML", "yaml"),
            ("matplotlib", "matplotlib"),
        ]
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        raise RuntimeError(
            "missing VeriDNS Python dependencies: "
            + ", ".join(missing)
            + ". Install them with `python3 -m pip install -r experiments/requirements-veridns.txt`."
        )
    sys.path.insert(0, str(VERIDNS_SRC))
    zone_parser = importlib.import_module("tools.zone_file_parser")
    zone_graph = importlib.import_module("core.zone_graph")
    check_config = importlib.import_module("config.check_config")
    return zone_parser.ZoneFileParser, zone_graph.ZoneGraph, check_config.check_self


def run_veridns(datasets: list[Dataset], out_dir: Path) -> tuple[Path, Path]:
    ZoneFileParser, ZoneGraph, check_self = import_veridns_modules()
    output_csv = out_dir / "veridns.csv"
    error_json = out_dir / "veridns_errors.json"
    errors = []

    with output_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(
            [
                "zone",
                "zone_file",
                "rr_count",
                "io_time (ms)",
                "construction_time (ms)",
                "property_checking_time (ms)",
                "total_time (ms)",
                "check_result_count",
            ]
        )
        for dataset in datasets:
            try:
                metadata = json.loads(dataset.metadata.read_text(encoding="utf-8"))
                zone_files = metadata.get("ZoneFiles", [])
                for entry in zone_files:
                    start = time.perf_counter_ns()
                    file_name = entry["FileName"]
                    origin = entry.get("Origin")
                    zone_path = dataset.path / file_name
                    parser = ZoneFileParser(file_name, str(zone_path), origin=origin)
                    after_io = time.perf_counter_ns()
                    records = parser.get_records()
                    graph = ZoneGraph(origin=parser.get_origin(), rr_list=records)
                    after_build = time.perf_counter_ns()
                    check_result = check_self(graph)
                    after_check = time.perf_counter_ns()
                    writer.writerow(
                        [
                            dataset.name,
                            file_name,
                            len(records),
                            ns_to_ms(after_io - start),
                            ns_to_ms(after_build - after_io),
                            ns_to_ms(after_check - after_build),
                            ns_to_ms(after_check - start),
                            len(check_result) if check_result else 0,
                        ]
                    )
            except Exception as exc:
                errors.append({"dataset": dataset.name, "error": repr(exc)})

    error_json.write_text(json.dumps(errors, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_csv, error_json


def ns_to_ms(ns: int) -> str:
    return f"{ns / 1_000_000:.6f}"


def read_float_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fp:
        return list(csv.DictReader(fp))


def summarize(out_dir: Path, aether_csv: Path | None, veridns_csv: Path | None) -> Path:
    lines = ["# VeriDNS vs Aether comparison", ""]
    if aether_csv and aether_csv.exists():
        rows = read_float_rows(aether_csv)
        initial = [
            sum(
                float(row[column])
                for column in [
                    "io_time (ms)",
                    "construction_time (ms)",
                    "symbolic_time (ms)",
                    "property_checking_time (ms)",
                ]
            )
            for row in rows
        ]
        incremental = [
            sum(
                float(row[column])
                for column in [
                    "re_construction_time (ms)",
                    "re_symbolic_time (ms)",
                    "re_property_checking_time (ms)",
                ]
            )
            for row in rows
        ]
        lines.extend(render_stats("Aether initial end-to-end time (ms)", initial))
        lines.extend(render_stats("Aether incremental time (ms)", incremental))
        lines.append("")
    if veridns_csv and veridns_csv.exists():
        rows = read_float_rows(veridns_csv)
        totals = [float(row["total_time (ms)"]) for row in rows]
        construction = [float(row["construction_time (ms)"]) for row in rows]
        checks = [float(row["property_checking_time (ms)"]) for row in rows]
        lines.extend(render_stats("VeriDNS per-zone-file total time (ms)", totals))
        lines.extend(render_stats("VeriDNS construction time (ms)", construction))
        lines.extend(render_stats("VeriDNS property checking time (ms)", checks))
        lines.append("")
    summary = out_dir / "summary.md"
    summary.write_text("\n".join(lines), encoding="utf-8")
    return summary


def render_stats(title: str, values: list[float]) -> list[str]:
    if not values:
        return [f"## {title}", "", "No data.", ""]
    sorted_values = sorted(values)
    p50 = percentile(sorted_values, 50)
    p90 = percentile(sorted_values, 90)
    p99 = percentile(sorted_values, 99)
    return [
        f"## {title}",
        "",
        f"- n: {len(values)}",
        f"- mean: {statistics.fmean(values):.6f}",
        f"- median: {p50:.6f}",
        f"- p90: {p90:.6f}",
        f"- p99: {p99:.6f}",
        f"- max: {max(values):.6f}",
        "",
    ]


def percentile(sorted_values: list[float], pct: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * pct / 100
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    datasets = load_datasets(args.datasets)
    input_csv = write_aether_input(datasets, out_dir)
    aether_bin = args.aether_bin or default_aether_binary()

    aether_csv = None
    veridns_csv = None
    if args.build_aether:
        build_aether()
    if not args.skip_aether:
        aether_csv = run_aether(aether_bin, input_csv, out_dir)
    if not args.skip_veridns:
        veridns_csv, _ = run_veridns(datasets, out_dir)
    summary = summarize(out_dir, aether_csv, veridns_csv)
    print(f"Wrote results to {out_dir}")
    print(f"Summary: {summary}")


if __name__ == "__main__":
    main()
