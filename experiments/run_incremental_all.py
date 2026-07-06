#!/usr/bin/env python3
"""Run multi-scenario incremental comparisons for Aether and VeriDNS."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CENSUS_ROOT = ROOT / "census"
OUT_ROOT = ROOT / "experiments" / "results" / "incremental_all"
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


GROUPS = ["files-100-500", "files-500-1000", "files-1000-plus", "top-10"]
SCENARIOS = ["A_ADD", "A_UPDATE", "NS_UPDATE", "CNAME_UPDATE"]
DNS_CLASSES = {"IN", "CH", "HS"}
CORE_TYPES = ["A", "AAAA", "NS", "SOA", "MX", "TXT", "CNAME", "DNAME"]
SUMMARY_FIELDS = [
    "tool", "group", "dataset", "dataset_id", "scenario", "status",
    "zone_files", "updated_zone_file", "rr_count", "initial_total_ms",
    "incremental_ms", "full_update_ms", "delta_operations", "affected_nodes",
    "wall_ms", "detail",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--group",
        action="append",
        choices=[*GROUPS, "all"],
        default=[],
        help="Dataset group(s) to run. Defaults to files-100-500.",
    )
    parser.add_argument("--dataset", action="append", default=[])
    parser.add_argument("--scenario", action="append", choices=SCENARIOS, default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out-dir", type=Path, default=OUT_ROOT)
    parser.add_argument("--skip-aether", action="store_true")
    parser.add_argument("--skip-veridns", action="store_true")
    parser.add_argument("--veridns-cache-timeout", type=float, default=0.0, help="Seconds allowed for one VeriDNS dataset initial cache; 0 disables the limit.")
    parser.add_argument("--aether-timeout", type=float, default=0.0, help="Seconds allowed for one Aether case; 0 disables the limit.")
    return parser.parse_args()


def selected_groups(args: argparse.Namespace) -> list[str]:
    if not args.group:
        return ["files-100-500"]
    if "all" in args.group:
        return GROUPS
    return args.group


def selected_scenarios(args: argparse.Namespace) -> list[str]:
    return args.scenario or SCENARIOS


def source_datasets(args: argparse.Namespace) -> list[tuple[str, Path]]:
    rows = []
    for group in selected_groups(args):
        group_dir = CENSUS_ROOT / group
        for dataset_dir in sorted(path for path in group_dir.iterdir() if path.is_dir()):
            if args.dataset and dataset_dir.name not in set(args.dataset):
                continue
            rows.append((group, dataset_dir))
    rows.sort(key=lambda item: (GROUPS.index(item[0]), item[1].name))
    return rows[: args.limit] if args.limit else rows


def strip_comment(line: str) -> str:
    return line.split(";", 1)[0].strip()


def parse_rr_line(line: str):
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


def summarize_features(group: str, src_dir: Path) -> dict:
    counts = Counter()
    wildcard = 0
    depths = []
    per_file_totals = []
    for zone_file in sorted(src_dir.glob("*.txt")):
        file_total = 0
        with zone_file.open("r", encoding="utf-8", errors="replace") as fp:
            for line in fp:
                parsed = parse_rr_line(line)
                if not parsed:
                    continue
                owner, rr_type, _ = parsed
                counts[rr_type] += 1
                file_total += 1
                if owner == "*" or owner.startswith("*."):
                    wildcard += 1
                depths.append(domain_depth(owner))
        per_file_totals.append(file_total)
    files = len(per_file_totals)
    total = sum(counts.values())
    rewrite = counts["CNAME"] + counts["DNAME"] + wildcard
    delegation = counts["NS"] + counts["SOA"]
    return {
        "group": group,
        "dataset": src_dir.name,
        "files": files,
        "total_rr": total,
        **{rr_type: counts[rr_type] for rr_type in CORE_TYPES},
        "wildcard": wildcard,
        "rewrite_rr": rewrite,
        "rewrite_ratio": rewrite / total if total else 0.0,
        "delegation_rr": delegation,
        "delegation_ratio": delegation / total if total else 0.0,
        "avg_rr_per_file": total / files if files else 0.0,
        "max_rr_per_file": max(per_file_totals) if per_file_totals else 0,
        "avg_owner_depth": sum(depths) / len(depths) if depths else 0.0,
        "max_owner_depth": max(depths) if depths else 0,
        "category": classify(total, counts, wildcard, files),
    }


def infer_origin(file_path: Path) -> str:
    name = file_path.name[:-4] if file_path.name.endswith(".txt") else file_path.name
    return f"{name.rstrip('.')}."


def infer_top_ns(dataset_name: str) -> str:
    return f"ns1.{dataset_name.rstrip('.')}."


def prepare_dataset(group: str, src_dir: Path, out_dir: Path) -> Path:
    dst_dir = out_dir / "metadata" / group / src_dir.name
    dst_dir.mkdir(parents=True, exist_ok=True)
    zone_files = []
    for txt in sorted(src_dir.glob("*.txt")):
        origin = infer_origin(txt)
        zone_files.append({
            "FileName": str(txt.resolve()),
            "NameServer": infer_top_ns(origin),
            "Origin": origin,
        })
    (dst_dir / "metadata.json").write_text(
        json.dumps({"TopNameServers": [infer_top_ns(src_dir.name)], "ZoneFiles": zone_files}, indent=2),
        encoding="utf-8",
    )
    return dst_dir


def load_metadata(dataset_dir: Path) -> dict:
    return json.loads((dataset_dir / "metadata.json").read_text(encoding="utf-8"))


def parse_zone(dataset_dir: Path, zone_info: dict) -> list[ResourceRecord]:
    zone_path = Path(zone_info["FileName"])
    if not zone_path.is_absolute():
        zone_path = dataset_dir / zone_info["FileName"]
    parser = ZoneFileParser(
        zone_info["FileName"],
        str(zone_path),
        origin=zone_info.get("Origin"),
    )
    return parser.get_records()


def record_parts(record: ResourceRecord) -> tuple[str, str, str]:
    domain, query_type, value = record.get_record_tuple()
    rtype = getattr(query_type, "value", str(query_type))
    if "." in rtype:
        rtype = rtype.rsplit(".", 1)[-1]
    return domain, rtype, value


def find_record(dataset_dir: Path, rr_type: str):
    metadata = load_metadata(dataset_dir)
    for zone_info in metadata["ZoneFiles"]:
        records = parse_zone(dataset_dir, zone_info)
        for record in records:
            _, rtype, _ = record_parts(record)
            if rtype == rr_type:
                return zone_info, record
    return None, None


def first_zone(dataset_dir: Path):
    metadata = load_metadata(dataset_dir)
    for zone_info in metadata["ZoneFiles"]:
        records = parse_zone(dataset_dir, zone_info)
        if records:
            return zone_info, records
    return None, []


def build_update(dataset_dir: Path, scenario: str) -> dict:
    if scenario == "A_ADD":
        zone_info, records = first_zone(dataset_dir)
        if not zone_info:
            return {"status": "skipped", "skipped_reason": "no parsable records"}
        origin = zone_info["Origin"].rstrip(".")
        return {
            "status": "ok",
            "scenario": scenario,
            "file_name": Path(zone_info["FileName"]).name,
            "ops": [("ADD", ResourceRecord(f"__aether_veridns_inc__.{origin}.", "A", "192.0.2.254"))],
        }

    rr_type = {"A_UPDATE": "A", "NS_UPDATE": "NS", "CNAME_UPDATE": "CNAME"}[scenario]
    zone_info, old_record = find_record(dataset_dir, rr_type)
    if not old_record:
        return {"status": "skipped", "skipped_reason": f"no {rr_type} record"}
    domain, rtype, _ = record_parts(old_record)
    suffix = zone_info["Origin"].rstrip(".")
    new_value = {
        "A": "192.0.2.253",
        "NS": f"ns-inc.{suffix}.",
        "CNAME": f"cname-inc.{suffix}.",
    }[rr_type]
    new_record = ResourceRecord(domain, rtype, new_value)
    return {
        "status": "ok",
        "scenario": scenario,
        "file_name": Path(zone_info["FileName"]).name,
        "old": old_record,
        "new": new_record,
        "ops": [("DEL", old_record), ("ADD", new_record)],
    }


def write_updates(update_rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["dataset", "zone_file", "scenario", "op", "domain", "type", "rdata"])
        for row in update_rows:
            if row["status"] != "ok":
                continue
            for op, record in row["update"]["ops"]:
                domain, rtype, value = record_parts(record)
                writer.writerow([row["dataset_id"], row["update"]["file_name"], row["scenario"], op, domain, rtype, value])


def write_skips(update_rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["group", "dataset", "dataset_id", "scenario", "status", "skipped_reason"])
        writer.writeheader()
        for row in update_rows:
            if row["status"] == "skipped":
                writer.writerow({key: row.get(key, "") for key in writer.fieldnames})


def apply_update(records: list[ResourceRecord], update: dict) -> list[ResourceRecord]:
    new_records = list(records)
    for op, record in update["ops"]:
        if op == "DEL":
            target = record.get_record_tuple()
            removed = False
            kept = []
            for current in new_records:
                if current.get_record_tuple() == target and not removed:
                    removed = True
                    continue
                kept.append(current)
            new_records = kept
        elif op == "ADD":
            new_records.append(record)
    return new_records


def run_veridns_case(dataset_dir: Path, case: dict) -> dict:
    base = {
        "tool": "VeriDNS",
        "group": case["group"],
        "dataset": case["dataset"],
        "dataset_id": case["dataset_id"],
        "scenario": case["scenario"],
    }
    if case["status"] != "ok":
        return {**base, "status": "skipped", "detail": case["skipped_reason"]}
    try:
        metadata = load_metadata(dataset_dir)
        start_all = time.perf_counter_ns()
        initial_total_ms = 0.0
        target_records = None
        target_zone = None
        for zone_info in metadata["ZoneFiles"]:
            zone_start = time.perf_counter_ns()
            records = parse_zone(dataset_dir, zone_info)
            graph = ZoneGraph(zone_info.get("Origin"), records)
            check_self(graph)
            initial_total_ms += (time.perf_counter_ns() - zone_start) / 1e6
            if Path(zone_info["FileName"]).name == case["update"]["file_name"]:
                target_records = records
                target_zone = zone_info
                target_graph = graph

        if target_records is None or target_zone is None:
            return {**base, "status": "error", "detail": "target zone not found after parsing"}

        new_records = apply_update(target_records, case["update"])
        inc_start = time.perf_counter_ns()
        verifier = IncrementalVerifier(target_graph.get_all_graph())
        _, affected_nodes, inc_result = verifier.incremental_verify(target_records, new_records, [check_domain_overflow])
        inc_ms = (time.perf_counter_ns() - inc_start) / 1e6

        full_start = time.perf_counter_ns()
        updated_graph = ZoneGraph(target_zone.get("Origin"), new_records)
        check_self(updated_graph)
        full_update_ms = (time.perf_counter_ns() - full_start) / 1e6

        return {
            **base,
            "status": "ok",
            "zone_files": len(metadata["ZoneFiles"]),
            "updated_zone_file": case["update"]["file_name"],
            "rr_count": sum(len(parse_zone(dataset_dir, z)) for z in metadata["ZoneFiles"]),
            "initial_total_ms": initial_total_ms,
            "incremental_ms": inc_ms,
            "full_update_ms": full_update_ms,
            "delta_operations": inc_result.get("delta_operations", 0),
            "affected_nodes": len(affected_nodes),
            "wall_ms": (time.perf_counter_ns() - start_all) / 1e6,
            "detail": "",
        }
    except Exception as exc:
        return {**base, "status": "error", "detail": repr(exc)}


def build_veridns_cache(dataset_dir: Path) -> dict:
    metadata = load_metadata(dataset_dir)
    initial_total_ms = 0.0
    rr_count = 0
    zones = {}
    for zone_info in metadata["ZoneFiles"]:
        zone_start = time.perf_counter_ns()
        records = parse_zone(dataset_dir, zone_info)
        graph = ZoneGraph(zone_info.get("Origin"), records)
        check_self(graph)
        initial_total_ms += (time.perf_counter_ns() - zone_start) / 1e6
        rr_count += len(records)
        zones[Path(zone_info["FileName"]).name] = {
            "zone_info": zone_info,
            "records": records,
            "graph": graph,
        }
    return {
        "metadata": metadata,
        "zones": zones,
        "initial_total_ms": initial_total_ms,
        "rr_count": rr_count,
    }


def build_veridns_cache_with_timeout(dataset_dir: Path, timeout_seconds: float) -> dict:
    deadline = time.perf_counter() + timeout_seconds if timeout_seconds > 0 else None
    metadata = load_metadata(dataset_dir)
    initial_total_ms = 0.0
    rr_count = 0
    zones = {}
    for index, zone_info in enumerate(metadata["ZoneFiles"], start=1):
        if deadline and time.perf_counter() > deadline:
            raise TimeoutError(f"VeriDNS initial cache exceeded {timeout_seconds}s after {index - 1}/{len(metadata['ZoneFiles'])} zone files")
        zone_start = time.perf_counter_ns()
        records = parse_zone(dataset_dir, zone_info)
        graph = ZoneGraph(zone_info.get("Origin"), records)
        check_self(graph)
        initial_total_ms += (time.perf_counter_ns() - zone_start) / 1e6
        rr_count += len(records)
        zones[Path(zone_info["FileName"]).name] = {
            "zone_info": zone_info,
            "records": records,
            "graph": graph,
        }
    return {
        "metadata": metadata,
        "zones": zones,
        "initial_total_ms": initial_total_ms,
        "rr_count": rr_count,
    }


def run_veridns_case_cached(cache: dict | None, cache_error: str | None, case: dict) -> dict:
    base = {
        "tool": "VeriDNS",
        "group": case["group"],
        "dataset": case["dataset"],
        "dataset_id": case["dataset_id"],
        "scenario": case["scenario"],
    }
    if case["status"] != "ok":
        return {**base, "status": "skipped", "detail": case["skipped_reason"]}
    if cache_error:
        return {**base, "status": "error", "detail": cache_error}
    try:
        start_all = time.perf_counter_ns()
        target = cache["zones"].get(case["update"]["file_name"])
        if target is None:
            return {**base, "status": "error", "detail": "target zone not found after parsing"}

        target_records = target["records"]
        target_zone = target["zone_info"]
        target_graph = target["graph"]
        new_records = apply_update(target_records, case["update"])

        inc_start = time.perf_counter_ns()
        verifier = IncrementalVerifier(target_graph.get_all_graph())
        _, affected_nodes, inc_result = verifier.incremental_verify(target_records, new_records, [check_domain_overflow])
        inc_ms = (time.perf_counter_ns() - inc_start) / 1e6

        full_start = time.perf_counter_ns()
        updated_graph = ZoneGraph(target_zone.get("Origin"), new_records)
        check_self(updated_graph)
        full_update_ms = (time.perf_counter_ns() - full_start) / 1e6

        return {
            **base,
            "status": "ok",
            "zone_files": len(cache["metadata"]["ZoneFiles"]),
            "updated_zone_file": case["update"]["file_name"],
            "rr_count": cache["rr_count"],
            "initial_total_ms": cache["initial_total_ms"],
            "incremental_ms": inc_ms,
            "full_update_ms": full_update_ms,
            "delta_operations": inc_result.get("delta_operations", 0),
            "affected_nodes": len(affected_nodes),
            "wall_ms": (time.perf_counter_ns() - start_all) / 1e6,
            "detail": "",
        }
    except Exception as exc:
        return {**base, "status": "error", "detail": repr(exc)}


def run_aether_case(dataset_dir: Path, case: dict, out_dir: Path, timeout_seconds: float = 0.0) -> dict:
    base = {
        "tool": "Aether",
        "group": case["group"],
        "dataset": case["dataset"],
        "dataset_id": case["dataset_id"],
        "scenario": case["scenario"],
    }
    if case["status"] != "ok":
        return {**base, "status": "skipped", "detail": case["skipped_reason"]}
    if not AETHER_BIN.exists() or not os.access(AETHER_BIN, os.X_OK):
        return {**base, "status": "blocked", "detail": f"missing executable: {AETHER_BIN}"}

    case_dir = out_dir / "aether_cases" / case["dataset_id"].replace("/", "__") / case["scenario"]
    case_dir.mkdir(parents=True, exist_ok=True)
    input_csv = case_dir / "input.csv"
    updates_csv = case_dir / "updates.csv"
    output_csv = case_dir / "aether_raw.csv"
    stderr_log = case_dir / "stderr.log"
    with input_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["zone", "metadata"])
        writer.writerow([case["dataset_id"], dataset_dir / "metadata.json"])
    write_updates([case], updates_csv)
    try:
        proc = subprocess.run(
            [
                str(AETHER_BIN),
                "--output",
                str(output_csv.resolve()),
                "--trace",
                str((case_dir / "traces").resolve()),
                "--updates",
                str(updates_csv.resolve()),
                "c",
                str(input_csv.resolve()),
            ],
            cwd=AETHER_DIR,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds if timeout_seconds > 0 else None,
        )
        stderr_log.write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != 0:
            return {**base, "status": "error", "detail": f"exit={proc.returncode}; stderr={stderr_log}"}
        rows = list(csv.DictReader(output_csv.open(newline="", encoding="utf-8")))
        if not rows:
            return {**base, "status": "error", "detail": "aether produced no output row"}
        row = rows[0]
        initial = sum(float(row[col]) for col in ["io_time (ms)", "construction_time (ms)", "symbolic_time (ms)", "property_checking_time (ms)"])
        incremental = sum(float(row[col]) for col in ["re_construction_time (ms)", "re_symbolic_time (ms)", "re_property_checking_time (ms)"])
        return {
            **base,
            "status": "ok",
            "zone_files": "",
            "updated_zone_file": case["update"]["file_name"],
            "rr_count": "",
            "initial_total_ms": initial,
            "incremental_ms": incremental,
            "full_update_ms": "",
            "delta_operations": "",
            "affected_nodes": "",
            "wall_ms": "",
            "detail": f"num_lec={row['num_lec']}; stderr={stderr_log}",
        }
    except Exception as exc:
        return {**base, "status": "error", "detail": repr(exc)}


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def init_csv(path: Path, fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fp:
        csv.DictWriter(fp, fieldnames=fieldnames).writeheader()


def append_csv(path: Path, row: dict, fieldnames: list[str]) -> None:
    with path.open("a", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writerow({key: row.get(key, "") for key in fieldnames})


def speedup(veridns: str, aether: str):
    try:
        v = float(veridns)
        a = float(aether)
        if a <= 0:
            return ""
        return v / a
    except Exception:
        return ""


def write_advantages(summary_rows: list[dict], features_by_id: dict[str, dict], out_dir: Path) -> None:
    pairs = {}
    for row in summary_rows:
        if row["status"] != "ok":
            continue
        key = (row["dataset_id"], row["scenario"])
        pairs.setdefault(key, {})[row["tool"]] = row

    advantage_rows = []
    for (dataset_id, scenario), tools in pairs.items():
        if "Aether" not in tools or "VeriDNS" not in tools:
            continue
        aether = tools["Aether"]
        veridns = tools["VeriDNS"]
        feature = features_by_id[dataset_id]
        advantage_rows.append({
            "group": feature["group"],
            "dataset": feature["dataset"],
            "dataset_id": dataset_id,
            "category": feature["category"],
            "scenario": scenario,
            "aether_incremental_ms": aether["incremental_ms"],
            "veridns_incremental_ms": veridns["incremental_ms"],
            "veridns_full_update_ms": veridns["full_update_ms"],
            "incremental_speedup": speedup(veridns["incremental_ms"], aether["incremental_ms"]),
            "full_update_speedup": speedup(veridns["full_update_ms"], aether["incremental_ms"]),
        })

    write_csv(out_dir / "advantage_by_case.csv", advantage_rows, [
        "group", "dataset", "dataset_id", "category", "scenario",
        "aether_incremental_ms", "veridns_incremental_ms", "veridns_full_update_ms",
        "incremental_speedup", "full_update_speedup",
    ])

    for field, filename in [("category", "advantage_by_feature.csv"), ("scenario", "advantage_by_scenario.csv")]:
        buckets = defaultdict(list)
        for row in advantage_rows:
            if row["incremental_speedup"] != "":
                buckets[row[field]].append(float(row["incremental_speedup"]))
        aggregate = []
        for name, values in sorted(buckets.items()):
            values = sorted(values)
            aggregate.append({
                field: name,
                "cases": len(values),
                "mean_incremental_speedup": sum(values) / len(values),
                "median_incremental_speedup": values[len(values) // 2],
                "aether_faster_cases": sum(1 for value in values if value > 1.0),
            })
        write_csv(out_dir / filename, aggregate, [field, "cases", "mean_incremental_speedup", "median_incremental_speedup", "aether_faster_cases"])


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = source_datasets(args)
    features = []
    prepared = {}
    for group, src_dir in selected:
        dataset_id = f"{group}/{src_dir.name}"
        features.append({"dataset_id": dataset_id, **summarize_features(group, src_dir)})
        prepared[dataset_id] = prepare_dataset(group, src_dir, out_dir)

    feature_fields = ["group", "dataset", "dataset_id", "files", "total_rr", *CORE_TYPES, "wildcard", "rewrite_rr", "rewrite_ratio", "delegation_rr", "delegation_ratio", "avg_rr_per_file", "max_rr_per_file", "avg_owner_depth", "max_owner_depth", "category"]
    write_csv(out_dir / "features.csv", features, feature_fields)
    features_by_id = {row["dataset_id"]: row for row in features}

    cases = []
    for feature in features:
        dataset_dir = prepared[feature["dataset_id"]]
        for scenario in selected_scenarios(args):
            update = build_update(dataset_dir, scenario)
            case = {
                "group": feature["group"],
                "dataset": feature["dataset"],
                "dataset_id": feature["dataset_id"],
                "scenario": scenario,
            }
            if update["status"] == "ok":
                case.update({"status": "ok", "update": update})
            else:
                case.update(update)
            cases.append(case)
    write_updates(cases, out_dir / "updates.csv")
    write_skips(cases, out_dir / "skipped_updates.csv")

    summary_path = out_dir / "summary.csv"
    veridns_path = out_dir / "veridns_raw.csv"
    aether_path = out_dir / "aether_raw.csv"
    for path in [summary_path, veridns_path, aether_path]:
        init_csv(path, SUMMARY_FIELDS)

    summary_rows = []
    cases_by_dataset = defaultdict(list)
    for case in cases:
        cases_by_dataset[case["dataset_id"]].append(case)

    for dataset_id, dataset_cases in cases_by_dataset.items():
        dataset_dir = prepared[dataset_id]
        veridns_cache = None
        veridns_cache_error = None
        if not args.skip_veridns:
            print(f"VeriDNS {dataset_id}: building initial cache", flush=True)
            try:
                veridns_cache = build_veridns_cache_with_timeout(dataset_dir, args.veridns_cache_timeout)
            except Exception as exc:
                veridns_cache_error = f"initial cache failed: {exc!r}"
                print(f"VeriDNS {dataset_id}: error {veridns_cache_error}", flush=True)

        for case in dataset_cases:
            if not args.skip_veridns:
                row = run_veridns_case_cached(veridns_cache, veridns_cache_error, case)
                summary_rows.append(row)
                append_csv(summary_path, row, SUMMARY_FIELDS)
                append_csv(veridns_path, row, SUMMARY_FIELDS)
                print(f"VeriDNS {case['dataset_id']} {case['scenario']}: {row['status']} inc={row.get('incremental_ms', '')}", flush=True)
            if not args.skip_aether:
                row = run_aether_case(dataset_dir, case, out_dir, args.aether_timeout)
                summary_rows.append(row)
                append_csv(summary_path, row, SUMMARY_FIELDS)
                append_csv(aether_path, row, SUMMARY_FIELDS)
                print(f"Aether {case['dataset_id']} {case['scenario']}: {row['status']} inc={row.get('incremental_ms', '')}", flush=True)

    write_advantages(summary_rows, features_by_id, out_dir)
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
