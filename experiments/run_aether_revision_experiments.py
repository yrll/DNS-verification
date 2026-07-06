#!/usr/bin/env python3
"""Run Aether-only experiments for paper revision evidence."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CENSUS_ROOT = ROOT / "census"
AETHER_DIR = ROOT / "aether" / "dnsverify"
AETHER_BIN = AETHER_DIR / "target" / "release" / "dnsv"
OUT_ROOT = ROOT / "experiments" / "results" / "aether_revision"

GROUPS = ["files-100-500", "files-500-1000", "files-1000-plus", "top-10"]
SCENARIOS = [
    "A_ADD",
    "A_UPDATE",
    "NS_UPDATE",
    "GLUE_UPDATE",
    "CNAME_UPDATE",
    "DNAME_ADD",
    "DNAME_UPDATE",
    "WILDCARD_EXACT_ADD",
]
DNS_CLASSES = {"IN", "CH", "HS"}
CORE_TYPES = ["A", "AAAA", "NS", "SOA", "MX", "TXT", "CNAME", "DNAME", "PTR"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", action="append", choices=[*GROUPS, "all"], default=[])
    parser.add_argument("--dataset", action="append", default=[])
    parser.add_argument("--scenario", action="append", choices=SCENARIOS, default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--out-dir", type=Path, default=OUT_ROOT)
    parser.add_argument("--aether-bin", type=Path, default=AETHER_BIN)
    parser.add_argument("--timeout", type=float, default=0.0)
    parser.add_argument("--max-query-depth", type=int, default=10)
    parser.add_argument("--min-label-num", type=int, default=5)
    parser.add_argument("--min-label-bits", type=int, default=4)
    parser.add_argument("--storm-size", action="append", type=int, default=[])
    parser.add_argument("--microbench-only", action="store_true")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--build-aether", action="store_true")
    return parser.parse_args()


def selected_groups(args: argparse.Namespace) -> list[str]:
    if not args.group:
        return ["top-10"]
    return GROUPS if "all" in args.group else args.group


def selected_scenarios(args: argparse.Namespace) -> list[str]:
    return args.scenario or SCENARIOS


def source_datasets(args: argparse.Namespace) -> list[tuple[str, Path]]:
    rows = []
    wanted = set(args.dataset)
    for group in selected_groups(args):
        for dataset_dir in sorted(path for path in (CENSUS_ROOT / group).iterdir() if path.is_dir()):
            if wanted and dataset_dir.name not in wanted:
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
            owner = parts[0]
            rr_type = upper[index + 1]
            rdata = " ".join(parts[index + 2 :])
            return owner, rr_type, rdata
    return None


def infer_origin(file_path: Path) -> str:
    name = file_path.name[:-4] if file_path.name.endswith(".txt") else file_path.name
    return f"{name.rstrip('.')}."


def infer_top_ns(origin: str) -> str:
    return f"ns1.{origin.rstrip('.')}."


def prepare_dataset(group: str, src_dir: Path, out_dir: Path) -> Path:
    dst_dir = out_dir / "datasets" / group / src_dir.name
    dst_dir.mkdir(parents=True, exist_ok=True)
    zone_files = []
    top_ns = infer_top_ns(src_dir.name)
    for txt in sorted(src_dir.glob("*.txt")):
        origin = infer_origin(txt)
        zone_files.append({
            "FileName": str(txt.resolve()),
            "NameServer": infer_top_ns(origin),
            "Origin": origin,
        })
    (dst_dir / "metadata.json").write_text(
        json.dumps({"TopNameServers": [top_ns], "ZoneFiles": zone_files}, indent=2),
        encoding="utf-8",
    )
    return dst_dir


def summarize_features(group: str, dataset: str, dataset_dir: Path, metadata_dir: Path) -> dict:
    counts = Counter()
    wildcard = 0
    total = 0
    per_file_totals = []
    zone_paths = sorted(list(dataset_dir.glob("*.txt")) + list(dataset_dir.glob("*.zone")))
    for txt in zone_paths:
        file_total = 0
        with txt.open("r", encoding="utf-8", errors="replace") as fp:
            for line in fp:
                parsed = parse_rr_line(line)
                if not parsed:
                    continue
                owner, rr_type, _ = parsed
                counts[rr_type] += 1
                total += 1
                file_total += 1
                if owner == "*" or owner.startswith("*."):
                    wildcard += 1
        per_file_totals.append(file_total)
    rewrite_rr = counts["CNAME"] + counts["DNAME"] + wildcard
    delegation_rr = counts["NS"] + counts["SOA"]
    return {
        "group": group,
        "dataset": dataset,
        "dataset_id": f"{group}/{dataset}",
        "metadata": str((metadata_dir / "metadata.json").resolve()),
        "zone_file_count": len(per_file_totals),
        "rr_count": total,
        **{rr_type: counts[rr_type] for rr_type in CORE_TYPES},
        "wildcard": wildcard,
        "rewrite_rr": rewrite_rr,
        "rewrite_density": rewrite_rr / total if total else 0.0,
        "delegation_rr": delegation_rr,
        "delegation_density": delegation_rr / total if total else 0.0,
        "avg_rr_per_file": total / len(per_file_totals) if per_file_totals else 0.0,
        "max_rr_per_file": max(per_file_totals) if per_file_totals else 0,
    }


def load_metadata(metadata_dir: Path) -> dict:
    return json.loads((metadata_dir / "metadata.json").read_text(encoding="utf-8"))


def iter_records(metadata_dir: Path):
    metadata = load_metadata(metadata_dir)
    for zone in metadata["ZoneFiles"]:
        zone_path = Path(zone["FileName"])
        origin = zone["Origin"]
        with zone_path.open("r", encoding="utf-8", errors="replace") as fp:
            for line in fp:
                parsed = parse_rr_line(line)
                if parsed:
                    owner, rr_type, rdata = parsed
                    yield zone, owner, rr_type, rdata, origin


def first_zone(metadata_dir: Path):
    metadata = load_metadata(metadata_dir)
    return metadata["ZoneFiles"][0] if metadata["ZoneFiles"] else None


def find_record(metadata_dir: Path, rr_type: str):
    for zone, owner, parsed_type, rdata, _ in iter_records(metadata_dir):
        if parsed_type == rr_type:
            return zone, owner, parsed_type, rdata
    return None


def find_glue_record(metadata_dir: Path):
    for zone, owner, rr_type, rdata, origin in iter_records(metadata_dir):
        if rr_type in {"A", "AAAA"} and owner.rstrip(".").endswith(origin.rstrip(".")):
            return zone, owner, rr_type, rdata
    return None


def find_wildcard_zone(metadata_dir: Path):
    for zone, owner, rr_type, _, origin in iter_records(metadata_dir):
        if owner.startswith("*.") and rr_type != "DNAME":
            return zone, owner, origin
    return None


def build_update(metadata_dir: Path, scenario: str) -> dict:
    if scenario == "A_ADD":
        zone = first_zone(metadata_dir)
        if not zone:
            return {"status": "skipped", "reason": "no zone file"}
        origin = zone["Origin"].rstrip(".")
        return {
            "status": "ok",
            "file_name": Path(zone["FileName"]).name,
            "ops": [("ADD", f"rev-a-add.{origin}.", "A", "192.0.2.10")],
        }
    if scenario == "DNAME_ADD":
        zone = first_zone(metadata_dir)
        if not zone:
            return {"status": "skipped", "reason": "no zone file"}
        origin = zone["Origin"].rstrip(".")
        return {
            "status": "ok",
            "file_name": Path(zone["FileName"]).name,
            "ops": [("ADD", f"rev-dname.{origin}.", "DNAME", f"rev-target.{origin}.")],
        }
    if scenario == "WILDCARD_EXACT_ADD":
        found = find_wildcard_zone(metadata_dir)
        if not found:
            return {"status": "skipped", "reason": "no wildcard record"}
        zone, _, origin = found
        return {
            "status": "ok",
            "file_name": Path(zone["FileName"]).name,
            "ops": [("ADD", f"rev-exact.{origin.rstrip('.')}.", "A", "192.0.2.11")],
        }
    if scenario == "GLUE_UPDATE":
        found = find_glue_record(metadata_dir)
        if not found:
            return {"status": "skipped", "reason": "no glue-like A/AAAA record"}
        zone, owner, rr_type, old = found
        new = "192.0.2.12" if rr_type == "A" else "2001:db8::12"
        return {"status": "ok", "file_name": Path(zone["FileName"]).name, "ops": [("DEL", owner, rr_type, old), ("ADD", owner, rr_type, new)]}
    rr_type = {
        "A_UPDATE": "A",
        "NS_UPDATE": "NS",
        "CNAME_UPDATE": "CNAME",
        "DNAME_UPDATE": "DNAME",
    }[scenario]
    found = find_record(metadata_dir, rr_type)
    if not found:
        return {"status": "skipped", "reason": f"no {rr_type} record"}
    zone, owner, _, old = found
    suffix = zone["Origin"].rstrip(".")
    new_value = {
        "A": "192.0.2.13",
        "NS": f"ns-rev.{suffix}.",
        "CNAME": f"cname-rev.{suffix}.",
        "DNAME": f"dname-rev.{suffix}.",
    }[rr_type]
    return {"status": "ok", "file_name": Path(zone["FileName"]).name, "ops": [("DEL", owner, rr_type, old), ("ADD", owner, rr_type, new_value)]}


def write_input_csv(path: Path, dataset_id: str, metadata_path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["zone", "metadata"])
        writer.writerow([dataset_id, metadata_path.resolve()])


def write_updates(path: Path, dataset_id: str, scenario: str, update: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["zone", "file", "scenario", "op", "domain", "type", "rdata"])
        if update["status"] != "ok":
            return
        for op, domain, rr_type, rdata in update["ops"]:
            writer.writerow([dataset_id, update["file_name"], scenario, op, domain, rr_type, rdata])


def run_aether_case(args: argparse.Namespace, dataset_id: str, metadata_path: Path, scenario: str, update: dict, case_dir: Path) -> dict:
    base = {"dataset_id": dataset_id, "scenario": scenario}
    if update["status"] != "ok":
        return {**base, "status": "skipped", "detail": update["reason"]}
    case_dir.mkdir(parents=True, exist_ok=True)
    input_csv = case_dir / "input.csv"
    updates_csv = case_dir / "updates.csv"
    output_csv = case_dir / "aether_raw.csv"
    stderr_log = case_dir / "stderr.log"
    write_input_csv(input_csv, dataset_id, metadata_path)
    write_updates(updates_csv, dataset_id, scenario, update)
    command = [
        str(args.aether_bin.resolve()),
        "--output", str(output_csv.resolve()),
        "--trace", str((case_dir / "traces").resolve()),
        "--updates", str(updates_csv.resolve()),
        "--no-random-update",
        "--repeat", str(args.repeat),
        "--max-query-depth", str(args.max_query_depth),
        "--min-label-num", str(args.min_label_num),
        "--min-label-bits", str(args.min_label_bits),
        "c", str(input_csv.resolve()),
    ]
    start = time.perf_counter_ns()
    try:
        proc = subprocess.run(
            command,
            cwd=AETHER_DIR,
            text=True,
            capture_output=True,
            timeout=args.timeout if args.timeout > 0 else None,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        wall_ms = (time.perf_counter_ns() - start) / 1e6
        stderr_log.write_text((exc.stderr or "") if isinstance(exc.stderr, str) else "", encoding="utf-8")
        return {**base, "status": "timeout", "detail": f"timeout={args.timeout}s; stderr={stderr_log}", "wall_ms": wall_ms}
    wall_ms = (time.perf_counter_ns() - start) / 1e6
    stderr_log.write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        return {**base, "status": "error", "detail": f"exit={proc.returncode}; stderr={stderr_log}", "wall_ms": wall_ms}
    rows = list(csv.DictReader(output_csv.open(newline="", encoding="utf-8")))
    if not rows:
        return {**base, "status": "error", "detail": "no aether rows", "wall_ms": wall_ms}
    out_rows = []
    for repeat_index, row in enumerate(rows):
        initial_ms = sum(float(row[col]) for col in ["io_time (ms)", "construction_time (ms)", "symbolic_time (ms)", "property_checking_time (ms)"])
        incremental_ms = sum(float(row[col]) for col in ["re_construction_time (ms)", "re_symbolic_time (ms)", "re_property_checking_time (ms)"])
        out_rows.append({
            **base,
            "status": "ok",
            "repeat_index": repeat_index,
            "updated_zone_file": update["file_name"],
            "initial_total_ms": initial_ms,
            "incremental_ms": incremental_ms,
            "full_no_io_ms": float(row["construction_time (ms)"]) + float(row["symbolic_time (ms)"]) + float(row["property_checking_time (ms)"]),
            "num_lec": row["num_lec"],
            "rr_count_aether": row.get("rr_count", ""),
            "zone_file_count_aether": row.get("zone_file_count", ""),
            "trace_count": row.get("trace_count", ""),
            "log_count": row.get("log_count", ""),
            "affected_trace_count": row.get("affected_trace_count", ""),
            "update_add_count": row.get("update_add_count", ""),
            "update_del_count": row.get("update_del_count", ""),
            "update_type": row.get("update_type", ""),
            "initial_property_pass": row.get("initial_property_pass", ""),
            "initial_errors": row.get("initial_errors", ""),
            "incremental_property_pass": row.get("incremental_property_pass", ""),
            "incremental_errors": row.get("incremental_errors", ""),
            "max_query_depth": row.get("max_query_depth", args.max_query_depth),
            "min_label_num": row.get("min_label_num", args.min_label_num),
            "min_label_bits": row.get("min_label_bits", args.min_label_bits),
            "wall_ms": wall_ms,
            "detail": "",
        })
    return out_rows


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def build_microbenchmarks(root: Path) -> list[tuple[str, str, Path]]:
    cases = {
        "cname-wildcard": {
            "zone": """example.test. IN SOA ns1.example.test. admin.example.test. 1 3600 600 86400 60
example.test. IN NS ns1.example.test.
ns1.example.test. IN A 192.0.2.1
alias.example.test. IN CNAME target.example.test.
*.example.test. IN A 192.0.2.20
""",
        },
        "dname-subspace": {
            "zone": """example.test. IN SOA ns1.example.test. admin.example.test. 1 3600 600 86400 60
example.test. IN NS ns1.example.test.
ns1.example.test. IN A 192.0.2.1
b.example.test. IN DNAME bb.example.test.
bb.example.test. IN A 192.0.2.30
*.bb.example.test. IN A 192.0.2.31
""",
        },
        "cname-loop": {
            "zone": """example.test. IN SOA ns1.example.test. admin.example.test. 1 3600 600 86400 60
example.test. IN NS ns1.example.test.
ns1.example.test. IN A 192.0.2.1
a.example.test. IN CNAME b.example.test.
b.example.test. IN CNAME a.example.test.
""",
        },
        "delegation-glue": {
            "zone": """example.test. IN SOA ns1.example.test. admin.example.test. 1 3600 600 86400 60
example.test. IN NS ns1.example.test.
ns1.example.test. IN A 192.0.2.1
child.example.test. IN NS ns1.child.example.test.
ns1.child.example.test. IN A 192.0.2.40
""",
        },
    }
    rows = []
    for name, payload in cases.items():
        case_dir = root / name
        case_dir.mkdir(parents=True, exist_ok=True)
        zone_path = case_dir / "example.test.zone"
        metadata_path = case_dir / "metadata.json"
        zone_path.write_text(payload["zone"], encoding="utf-8")
        metadata_path.write_text(json.dumps({
            "TopNameServers": ["ns1.example.test."],
            "ZoneFiles": [{
                "FileName": zone_path.name,
                "NameServer": "ns1.example.test.",
                "Origin": "example.test.",
            }],
        }, indent=2), encoding="utf-8")
        rows.append(("microbench", name, case_dir))
    return rows


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.build_aether:
        subprocess.run(["cargo", "build", "--release"], cwd=AETHER_DIR, check=True)
    if not args.aether_bin.exists():
        raise SystemExit(f"missing Aether binary: {args.aether_bin}")

    all_rows = []
    skipped_rows = []
    feature_rows = []
    if not args.microbench_only:
        for group, src_dir in source_datasets(args):
            metadata_dir = prepare_dataset(group, src_dir, args.out_dir)
            dataset_id = f"{group}/{src_dir.name}"
            feature_rows.append(summarize_features(group, src_dir.name, src_dir, metadata_dir))
            for scenario in selected_scenarios(args):
                update = build_update(metadata_dir, scenario)
                case_dir = args.out_dir / "cases" / dataset_id.replace("/", "__") / scenario
                result = run_aether_case(args, dataset_id, metadata_dir / "metadata.json", scenario, update, case_dir)
                rows = result if isinstance(result, list) else [result]
                all_rows.extend(rows)
                skipped_rows.extend(row for row in rows if row["status"] != "ok")

    if not args.real_only:
        micro_root = AETHER_DIR / "datasets" / "revision-microbench"
        for group, name, case_dir in build_microbenchmarks(micro_root):
            dataset_id = f"{group}/{name}"
            feature_rows.append(summarize_features(group, name, case_dir, case_dir))
            for scenario in selected_scenarios(args):
                update = build_update(case_dir, scenario)
                run_dir = args.out_dir / "cases" / dataset_id.replace("/", "__") / scenario
                result = run_aether_case(args, dataset_id, case_dir / "metadata.json", scenario, update, run_dir)
                rows = result if isinstance(result, list) else [result]
                all_rows.extend(rows)
                skipped_rows.extend(row for row in rows if row["status"] != "ok")

    raw_fields = [
        "dataset_id", "scenario", "status", "repeat_index", "updated_zone_file",
        "initial_total_ms", "incremental_ms", "full_no_io_ms", "num_lec",
        "rr_count_aether", "zone_file_count_aether", "trace_count", "log_count",
        "affected_trace_count", "update_add_count", "update_del_count", "update_type",
        "initial_property_pass", "initial_errors", "incremental_property_pass",
        "incremental_errors", "max_query_depth", "min_label_num", "min_label_bits",
        "wall_ms", "detail",
    ]
    feature_fields = [
        "group", "dataset", "dataset_id", "metadata", "zone_file_count", "rr_count",
        *CORE_TYPES, "wildcard", "rewrite_rr", "rewrite_density",
        "delegation_rr", "delegation_density", "avg_rr_per_file", "max_rr_per_file",
    ]
    write_csv(args.out_dir / "aether_raw.csv", all_rows, raw_fields)
    write_csv(args.out_dir / "features.csv", feature_rows, feature_fields)
    write_csv(args.out_dir / "skipped_updates.csv", skipped_rows, ["dataset_id", "scenario", "status", "detail"])
    print(f"Wrote {len(all_rows)} raw rows to {args.out_dir / 'aether_raw.csv'}")


if __name__ == "__main__":
    main()
