#!/usr/bin/env python3
"""Compare Aether and VeriDNS incremental verification on 100-500-file census sets."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CENSUS_100_500 = ROOT / "census" / "files-100-500"
OUT_ROOT = ROOT / "experiments" / "results" / "incremental_100_500"
AETHER_DIR = ROOT / "aether" / "dnsverify"
AETHER_BIN = AETHER_DIR / "target" / "release" / "dnsv"
VERIDNS_SRC = ROOT / "VeriDNS" / "src_muilt"
sys.path.insert(0, str(VERIDNS_SRC))

from config.check_config import check_self  # noqa: E402
from core.check_properties import check_domain_overflow  # noqa: E402
from core.incremental_verification import IncrementalVerifier  # noqa: E402
from core.zone_graph import ZoneGraph  # noqa: E402
from entity.resource_record import ResourceRecord  # noqa: E402
from tools.zone_file_parser import ZoneFileParser  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--min-files", type=int, default=100)
    parser.add_argument("--max-files", type=int, default=500)
    parser.add_argument("--dataset", action="append", default=[])
    parser.add_argument("--out-dir", type=Path, default=OUT_ROOT)
    return parser.parse_args()


def list_datasets(args: argparse.Namespace) -> list[Path]:
    if args.dataset:
        return [(CENSUS_100_500 / name).resolve() for name in args.dataset]
    rows = []
    for path in sorted(CENSUS_100_500.iterdir()):
        if not path.is_dir():
            continue
        file_count = len(list(path.glob("*.txt")))
        if args.min_files <= file_count <= args.max_files:
            rows.append((file_count, path))
    rows.sort(key=lambda item: (item[0], item[1].name))
    return [path for _, path in rows[: args.limit]]


def infer_origin(file_path: Path) -> str:
    name = file_path.name
    if name.endswith(".txt"):
        name = name[:-4]
    while name.endswith("."):
        name = name[:-1]
    if name.endswith("."):
        return name
    return f"{name}."


def infer_top_ns(dataset_name: str) -> str:
    clean = dataset_name.rstrip(".")
    return f"ns1.{clean}."


def prepare_dataset(src_dir: Path, work_root: Path) -> Path:
    dst_dir = work_root / "datasets" / src_dir.name
    dst_dir.mkdir(parents=True, exist_ok=True)
    zone_files = []
    for txt in sorted(src_dir.glob("*.txt")):
        target = dst_dir / txt.name
        if not target.exists():
            shutil.copy2(txt, target)
        origin = infer_origin(txt)
        zone_files.append(
            {
                "FileName": txt.name,
                "NameServer": infer_top_ns(origin),
                "Origin": origin,
            }
        )
    metadata = {
        "TopNameServers": [infer_top_ns(src_dir.name)],
        "ZoneFiles": zone_files,
    }
    (dst_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return dst_dir


def load_metadata(dataset_dir: Path) -> dict:
    return json.loads((dataset_dir / "metadata.json").read_text(encoding="utf-8"))


def parse_zone(dataset_dir: Path, zone_info: dict):
    file_name = zone_info["FileName"]
    origin = zone_info.get("Origin")
    parser = ZoneFileParser(file_name, str(dataset_dir / file_name), origin=origin)
    return parser.get_records()


def make_added_record(origin: str) -> ResourceRecord:
    clean = origin.rstrip(".")
    return ResourceRecord(f"__aether_veridns_inc__.{clean}.", "A", "192.0.2.254")


def make_updated_records(records: list[ResourceRecord], origin: str) -> list[ResourceRecord]:
    if not records:
        return [make_added_record(origin)]
    old_name, old_type, _ = records[0].get_record_tuple()
    updated = ResourceRecord(old_name, old_type, f"__aether_veridns_inc__.{origin.rstrip('.')}.")
    return [updated, *records[1:]]


def record_parts(record: ResourceRecord) -> tuple[str, str, str]:
    domain, query_type, value = record.get_record_tuple()
    rtype = getattr(query_type, "value", str(query_type))
    if "." in rtype:
        rtype = rtype.rsplit(".", 1)[-1]
    return domain, rtype, value


def generate_updates(dataset_dirs: list[Path], updates_csv: Path) -> dict[str, dict]:
    updates_by_dataset = {}
    with updates_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["zone", "file", "op", "domain", "type", "rdata"])
        for dataset_dir in dataset_dirs:
            metadata = load_metadata(dataset_dir)
            selected = None
            old_record = None
            for zone_info in metadata["ZoneFiles"]:
                records = parse_zone(dataset_dir, zone_info)
                if records:
                    selected = zone_info
                    old_record = records[0]
                    break
            if selected is None or old_record is None:
                continue
            domain, rtype, old_value = record_parts(old_record)
            new_value = f"__aether_veridns_inc__.{selected.get('Origin').rstrip('.')}."
            updates_by_dataset[dataset_dir.name] = {
                "file_name": selected["FileName"],
                "old": ResourceRecord(domain, rtype, old_value),
                "new": ResourceRecord(domain, rtype, new_value),
            }
            writer.writerow([dataset_dir.name, selected["FileName"], "DEL", domain, rtype, old_value])
            writer.writerow([dataset_dir.name, selected["FileName"], "ADD", domain, rtype, new_value])
    return updates_by_dataset


def apply_update(records: list[ResourceRecord], update: dict | None, origin: str) -> list[ResourceRecord]:
    if update is None:
        return make_updated_records(records, origin)
    old_domain, old_type, old_value = update["old"].get_record_tuple()
    new_records = []
    replaced = False
    for record in records:
        if record.get_record_tuple() == (old_domain, old_type, old_value) and not replaced:
            new_records.append(update["new"])
            replaced = True
        else:
            new_records.append(record)
    if not replaced:
        new_records.append(update["new"])
    return new_records


def run_veridns(dataset_dir: Path, update: dict | None) -> dict:
    metadata = load_metadata(dataset_dir)
    start_all = time.perf_counter_ns()
    zone_results = []
    total_rr = 0
    total_delta = 0
    total_affected_nodes = 0
    total_inc_ms = 0.0
    total_full_update_ms = 0.0
    total_initial_ms = 0.0
    updated_zone_files = 0

    for zone_info in metadata["ZoneFiles"]:
        zone_start = time.perf_counter_ns()
        records = parse_zone(dataset_dir, zone_info)
        parsed = time.perf_counter_ns()
        graph = ZoneGraph(zone_info.get("Origin"), records)
        built = time.perf_counter_ns()
        check_result = check_self(graph)
        checked = time.perf_counter_ns()

        zone_update = update if update and update["file_name"] == zone_info["FileName"] else None
        if zone_update:
            updated_zone_files += 1
            new_records = apply_update(records, zone_update, zone_info.get("Origin"))
            inc_start = time.perf_counter_ns()
            verifier = IncrementalVerifier(graph.get_all_graph())
            _, affected_nodes, inc_result = verifier.incremental_verify(
                records, new_records, [check_domain_overflow]
            )
            inc_end = time.perf_counter_ns()

            full_update_start = time.perf_counter_ns()
            updated_graph = ZoneGraph(zone_info.get("Origin"), new_records)
            updated_check = check_self(updated_graph)
            full_update_end = time.perf_counter_ns()
            inc_ms = (inc_end - inc_start) / 1e6
            full_update_ms = (full_update_end - full_update_start) / 1e6
            delta_ops = inc_result.get("delta_operations", 0)
            affected_node_count = len(affected_nodes)
            updated_bug_count = len(updated_check)
        else:
            inc_ms = 0.0
            full_update_ms = 0.0
            delta_ops = 0
            affected_node_count = 0
            updated_bug_count = ""

        initial_ms = (checked - zone_start) / 1e6
        total_rr += len(records)
        total_delta += delta_ops
        total_affected_nodes += affected_node_count
        total_initial_ms += initial_ms
        total_inc_ms += inc_ms
        total_full_update_ms += full_update_ms
        zone_results.append(
            {
                "file_name": zone_info["FileName"],
                "origin": zone_info.get("Origin"),
                "rr_count": len(records),
                "parse_ms": (parsed - zone_start) / 1e6,
                "build_graph_ms": (built - parsed) / 1e6,
                "check_ms": (checked - built) / 1e6,
                "initial_total_ms": initial_ms,
                "incremental_ms": inc_ms,
                "full_update_ms": full_update_ms,
                "delta_operations": delta_ops,
                "affected_nodes": affected_node_count,
                "bug_count": len(check_result),
                "updated_bug_count": updated_bug_count,
            }
        )

    return {
        "tool": "VeriDNS",
        "dataset": dataset_dir.name,
        "status": "ok",
        "zone_files": len(metadata["ZoneFiles"]),
        "updated_zone_files": updated_zone_files,
        "rr_count": total_rr,
        "initial_total_ms": total_initial_ms,
        "incremental_ms": total_inc_ms,
        "full_update_ms": total_full_update_ms,
        "delta_operations": total_delta,
        "affected_nodes": total_affected_nodes,
        "wall_ms": (time.perf_counter_ns() - start_all) / 1e6,
        "detail": "",
        "zone_results": zone_results,
    }


def run_aether(dataset_dirs: list[Path], out_dir: Path, updates_csv: Path) -> list[dict]:
    if not AETHER_BIN.exists() or not os.access(AETHER_BIN, os.X_OK):
        detail = "blocked: missing Linux executable aether/dnsverify/target/release/dnsv"
        return [
            {
                "tool": "Aether",
                "dataset": dataset_dir.name,
                "status": "blocked",
                "zone_files": len(load_metadata(dataset_dir)["ZoneFiles"]),
                "rr_count": "",
                "initial_total_ms": "",
                "incremental_ms": "",
                "full_update_ms": "",
                "delta_operations": "",
                "affected_nodes": "",
                "wall_ms": "",
                "detail": detail,
            }
            for dataset_dir in dataset_dirs
        ]

    input_csv = out_dir / "aether_input.csv"
    output_csv = out_dir / "aether_raw.csv"
    trace_dir = out_dir / "aether_traces"
    with input_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["zone", "metadata"])
        for dataset_dir in dataset_dirs:
            writer.writerow([dataset_dir.name, dataset_dir / "metadata.json"])
    subprocess.run(
        [
            str(AETHER_BIN),
            "--output",
            str(output_csv),
            "--trace",
            str(trace_dir),
            "--updates",
            str(updates_csv),
            "c",
            str(input_csv),
        ],
        cwd=AETHER_DIR,
        check=True,
    )
    rows = []
    with output_csv.open(newline="", encoding="utf-8") as fp:
        for row in csv.DictReader(fp):
            initial = sum(
                float(row[col])
                for col in [
                    "io_time (ms)",
                    "construction_time (ms)",
                    "symbolic_time (ms)",
                    "property_checking_time (ms)",
                ]
            )
            incremental = sum(
                float(row[col])
                for col in [
                    "re_construction_time (ms)",
                    "re_symbolic_time (ms)",
                    "re_property_checking_time (ms)",
                ]
            )
            rows.append(
                {
                    "tool": "Aether",
                    "dataset": row["zone"],
                    "status": "ok",
                    "zone_files": "",
                    "rr_count": "",
                    "initial_total_ms": initial,
                    "incremental_ms": incremental,
                    "full_update_ms": "",
                    "delta_operations": "",
                    "affected_nodes": "",
                    "wall_ms": "",
                    "detail": f"num_lec={row['num_lec']}",
                }
            )
    return rows


def write_summary(rows: list[dict], path: Path) -> None:
    fields = [
        "tool",
        "dataset",
        "status",
        "zone_files",
        "updated_zone_files",
        "rr_count",
        "initial_total_ms",
        "incremental_ms",
        "full_update_ms",
        "delta_operations",
        "affected_nodes",
        "wall_ms",
        "detail",
    ]
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def write_veridns_details(veridns_rows: list[dict], out_dir: Path) -> None:
    fields = [
        "dataset",
        "file_name",
        "origin",
        "rr_count",
        "parse_ms",
        "build_graph_ms",
        "check_ms",
        "initial_total_ms",
        "incremental_ms",
        "full_update_ms",
        "delta_operations",
        "affected_nodes",
        "bug_count",
        "updated_bug_count",
    ]
    with (out_dir / "veridns_zone_details.csv").open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for dataset_row in veridns_rows:
            for detail in dataset_row["zone_results"]:
                detail = {"dataset": dataset_row["dataset"], **detail}
                writer.writerow({key: detail.get(key, "") for key in fields})


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    datasets = [prepare_dataset(path, out_dir) for path in list_datasets(args)]
    updates_csv = out_dir / "updates.csv"
    updates_by_dataset = generate_updates(datasets, updates_csv)

    rows = []
    veridns_rows = []
    for dataset_dir in datasets:
        row = run_veridns(dataset_dir, updates_by_dataset.get(dataset_dir.name))
        veridns_rows.append(row)
        rows.append({key: value for key, value in row.items() if key != "zone_results"})
        print(
            f"VeriDNS {dataset_dir.name}: zones={row['zone_files']} "
            f"rr={row['rr_count']} initial={row['initial_total_ms']:.3f}ms "
            f"inc={row['incremental_ms']:.3f}ms full_update={row['full_update_ms']:.3f}ms"
        )

    rows.extend(run_aether(datasets, out_dir, updates_csv))
    write_summary(rows, out_dir / "summary.csv")
    write_veridns_details(veridns_rows, out_dir)
    print(f"wrote {out_dir / 'summary.csv'}")
    print(f"wrote {out_dir / 'veridns_zone_details.csv'}")


if __name__ == "__main__":
    main()
