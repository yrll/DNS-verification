#!/usr/bin/env python3
"""Run property-aware incremental comparisons for Aether and VeriDNS."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from collections import defaultdict
from pathlib import Path

import networkx as nx

import run_incremental_all as base
from core.check_properties import check_miss_glue_record, check_rewrite_blackholing, check_rewrite_loop

csv.field_size_limit(10_000_000)


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "experiments" / "results" / "incremental_property_all"
COMMON_PROPERTIES = [
    "hops",
    "rewrites",
    "lame_delegation",
    "rewrite_blackholing",
    "rewrite_loop",
    "delegation_consistency",
]
SUMMARY_FIELDS = [
    "group", "dataset", "dataset_id", "scenario", "status",
    "zone_files", "updated_zone_file", "rr_count",
    "aether_initial_ms", "aether_incremental_ms", "veridns_initial_ms",
    "veridns_incremental_ms", "veridns_full_update_ms",
    "properties", "aether_initial_pass", "aether_incremental_pass",
    "aether_errors", "veridns_initial_pass", "veridns_incremental_pass",
    "veridns_errors", "veridns_matches_aether", "oracle", "detail",
]
RAW_FIELDS = [
    "tool", "group", "dataset", "dataset_id", "scenario", "status",
    "zone_files", "updated_zone_file", "rr_count", "initial_total_ms",
    "incremental_ms", "full_update_ms", "properties",
    "initial_property_pass", "incremental_property_pass", "initial_errors",
    "incremental_errors", "detail",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=base.CENSUS_ROOT)
    parser.add_argument("--group", action="append", choices=[*base.GROUPS, "all"], default=[])
    parser.add_argument("--dataset", action="append", default=[])
    parser.add_argument("--scenario", action="append", choices=base.SCENARIOS, default=[])
    parser.add_argument("--property", action="append", choices=COMMON_PROPERTIES, default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out-dir", type=Path, default=OUT_ROOT)
    parser.add_argument("--skip-aether", action="store_true")
    parser.add_argument("--skip-veridns", action="store_true")
    parser.add_argument("--veridns-cache-timeout", type=float, default=0.0)
    parser.add_argument("--aether-timeout", type=float, default=0.0)
    return parser.parse_args()


def selected_groups(args: argparse.Namespace) -> list[str]:
    if not args.group:
        return ["files-100-500"]
    return base.GROUPS if "all" in args.group else args.group


def selected_scenarios(args: argparse.Namespace) -> list[str]:
    return args.scenario or base.SCENARIOS


def selected_properties(args: argparse.Namespace) -> list[str]:
    return args.property or COMMON_PROPERTIES


def source_datasets(args: argparse.Namespace) -> list[tuple[str, Path]]:
    rows = []
    wanted = set(args.dataset)
    dataset_root = args.dataset_root.resolve()
    for group in selected_groups(args):
        for dataset_dir in sorted(path for path in (dataset_root / group).iterdir() if path.is_dir()):
            if wanted and dataset_dir.name not in wanted:
                continue
            rows.append((group, dataset_dir))
    rows.sort(key=lambda item: (base.GROUPS.index(item[0]), item[1].name))
    return rows[: args.limit] if args.limit else rows


def normalize_aether_error(error: str) -> str:
    if error in {"hops", "rewrites"}:
        return error
    if error.startswith("rewrite "):
        return "rewrites"
    return {
        "lame delegation": "lame_delegation",
        "rewrite blackholing": "rewrite_blackholing",
        "loop": "rewrite_loop",
        "zone loop": "rewrite_loop",
        "delegation consistency": "delegation_consistency",
    }.get(error, error)


def normalize_veridns_error(error: dict | str) -> str:
    if isinstance(error, dict):
        prop = error.get("Property", "")
        return {
            "check_miss_glue_record": "lame_delegation",
            "check_rewrite_blackholing": "rewrite_blackholing",
            "check_rewrite_loop": "rewrite_loop",
            "check_delegation_inconsistency": "delegation_consistency",
        }.get(prop, prop)
    return str(error)


def pass_bool(value) -> bool | None:
    if value in (True, "true", "True", "1"):
        return True
    if value in (False, "false", "False", "0"):
        return False
    return None


def verdict_from_errors(errors: list[str], properties: list[str]) -> dict[str, bool]:
    error_set = {normalize_aether_error(error) for error in errors if error}
    return {prop: prop not in error_set for prop in properties}


def veridns_check_graphs(graph: base.ZoneGraph, properties: list[str]) -> tuple[dict[str, bool], list[str]]:
    verdict = {prop: True for prop in properties}
    errors = []
    if "lame_delegation" in properties:
        try:
            ok, output, _ = check_miss_glue_record(graph.get_glue_graph())
            if not ok:
                verdict["lame_delegation"] = False
                errors.extend(normalize_veridns_error(item) for item in output)
        except Exception as exc:
            verdict["lame_delegation"] = False
            errors.append(f"lame_delegation:{exc!r}")
    if "rewrite_loop" in properties:
        try:
            ok, output = check_rewrite_loop(graph.get_cname_graph(), graph.get_dname_graph())
            if not ok:
                verdict["rewrite_loop"] = False
                errors.extend(normalize_veridns_error(item) for item in output)
        except Exception as exc:
            verdict["rewrite_loop"] = False
            errors.append(f"rewrite_loop:{exc!r}")
    if "rewrite_blackholing" in properties:
        try:
            ok, output = check_rewrite_blackholing(graph.get_cname_graph(), graph.get_dname_graph())
            if not ok:
                verdict["rewrite_blackholing"] = False
                errors.extend(normalize_veridns_error(item) for item in output)
        except Exception as exc:
            verdict["rewrite_blackholing"] = False
            errors.append(f"rewrite_blackholing:{exc!r}")
    return verdict, sorted(set(errors))


def run_veridns_property_case(cache: dict | None, cache_error: str | None, case: dict, properties: list[str]) -> dict:
    base_row = {
        "tool": "VeriDNS",
        "group": case["group"],
        "dataset": case["dataset"],
        "dataset_id": case["dataset_id"],
        "scenario": case["scenario"],
        "properties": "|".join(properties),
    }
    if case["status"] != "ok":
        return {**base_row, "status": "skipped", "detail": case["skipped_reason"]}
    if cache_error:
        return {**base_row, "status": "error", "detail": cache_error}
    try:
        target = cache["zones"].get(case["update"]["file_name"])
        if target is None:
            return {**base_row, "status": "error", "detail": "target zone not found"}

        initial_errors = []
        initial_pass = True
        for zone in cache["zones"].values():
            verdict, errors = veridns_check_graphs(zone["graph"], properties)
            initial_errors.extend(errors)
            initial_pass = initial_pass and all(verdict.values())

        target_records = target["records"]
        new_records = base.apply_update(target_records, case["update"])
        inc_start = time.perf_counter_ns()
        updated_graph = base.ZoneGraph(target["zone_info"].get("Origin"), new_records)
        inc_verdict, inc_errors = veridns_check_graphs(updated_graph, properties)
        inc_ms = (time.perf_counter_ns() - inc_start) / 1e6

        full_start = time.perf_counter_ns()
        full_graph = base.ZoneGraph(target["zone_info"].get("Origin"), new_records)
        full_verdict, full_errors = veridns_check_graphs(full_graph, properties)
        full_update_ms = (time.perf_counter_ns() - full_start) / 1e6

        return {
            **base_row,
            "status": "ok",
            "zone_files": len(cache["metadata"]["ZoneFiles"]),
            "updated_zone_file": case["update"]["file_name"],
            "rr_count": cache["rr_count"],
            "initial_total_ms": cache["initial_total_ms"],
            "incremental_ms": inc_ms,
            "full_update_ms": full_update_ms,
            "initial_property_pass": initial_pass,
            "incremental_property_pass": all(inc_verdict.values()) and all(full_verdict.values()),
            "initial_errors": "|".join(sorted(set(initial_errors))),
            "incremental_errors": "|".join(sorted(set(inc_errors + full_errors))),
            "detail": "",
        }
    except Exception as exc:
        return {**base_row, "status": "error", "detail": repr(exc)}


def run_aether_property_case(dataset_dir: Path, case: dict, out_dir: Path, properties: list[str], timeout_seconds: float) -> dict:
    row_base = {
        "tool": "Aether",
        "group": case["group"],
        "dataset": case["dataset"],
        "dataset_id": case["dataset_id"],
        "scenario": case["scenario"],
        "properties": "|".join(properties),
    }
    if case["status"] != "ok":
        return {**row_base, "status": "skipped", "detail": case["skipped_reason"]}
    if not base.AETHER_BIN.exists() or not os.access(base.AETHER_BIN, os.X_OK):
        return {**row_base, "status": "blocked", "detail": f"missing executable: {base.AETHER_BIN}"}

    case_dir = out_dir / "aether_cases" / case["dataset_id"].replace("/", "__") / case["scenario"]
    case_dir.mkdir(parents=True, exist_ok=True)
    input_csv = case_dir / "input.csv"
    updates_csv = case_dir / "updates.csv"
    output_csv = case_dir / "aether_raw.csv"
    stderr_log = case_dir / "stderr.log"
    jobs_file = out_dir / "properties.txt"
    with input_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["zone", "metadata"])
        writer.writerow([case["dataset_id"], dataset_dir / "metadata.json"])
    base.write_updates([case], updates_csv)
    try:
        proc = subprocess.run(
            [
                str(base.AETHER_BIN),
                "--output",
                str(output_csv.resolve()),
                "--trace",
                str((case_dir / "traces").resolve()),
                "--updates",
                str(updates_csv.resolve()),
                "--jobs",
                str(jobs_file.resolve()),
                "c",
                str(input_csv.resolve()),
            ],
            cwd=base.AETHER_DIR,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds if timeout_seconds > 0 else None,
        )
        stderr_log.write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != 0:
            return {**row_base, "status": "error", "detail": f"exit={proc.returncode}; stderr={stderr_log}"}
    except Exception as exc:
        return {**row_base, "status": "error", "detail": repr(exc)}

    raw_path = case_dir / "aether_raw.csv"
    raw_rows = list(csv.DictReader(raw_path.open(newline="", encoding="utf-8")))
    if not raw_rows:
        return {**row_base, "status": "error", "detail": "aether produced no output row"}
    raw = raw_rows[0]
    initial = sum(float(raw[col]) for col in ["io_time (ms)", "construction_time (ms)", "symbolic_time (ms)", "property_checking_time (ms)"])
    incremental = sum(float(raw[col]) for col in ["re_construction_time (ms)", "re_symbolic_time (ms)", "re_property_checking_time (ms)"])
    initial_errors = [normalize_aether_error(item) for item in raw.get("initial_errors", "").split("|") if item]
    incremental_errors = [normalize_aether_error(item) for item in raw.get("incremental_errors", "").split("|") if item]
    return {
        **row_base,
        "status": "ok",
        "zone_files": "",
        "updated_zone_file": case["update"]["file_name"],
        "rr_count": "",
        "initial_total_ms": initial,
        "incremental_ms": incremental,
        "full_update_ms": "",
        "initial_property_pass": raw.get("initial_property_pass", ""),
        "incremental_property_pass": raw.get("incremental_property_pass", ""),
        "initial_errors": "|".join(sorted(set(initial_errors))),
        "incremental_errors": "|".join(sorted(set(incremental_errors))),
        "detail": f"num_lec={raw.get('num_lec', '')}; stderr={stderr_log}",
    }


def write_jobs(path: Path, properties: list[str]) -> None:
    path.write_text("\n".join(properties) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def append_csv(path: Path, row: dict, fields: list[str]) -> None:
    with path.open("a", newline="", encoding="utf-8") as fp:
        csv.DictWriter(fp, fieldnames=fields).writerow({field: row.get(field, "") for field in fields})


def compare_verdicts(aether: dict, veridns: dict, properties: list[str]) -> tuple[bool | str, list[dict]]:
    if aether.get("status") != "ok" or veridns.get("status") != "ok":
        return "", []
    a_errors = [item for item in str(aether.get("incremental_errors", "")).split("|") if item]
    v_errors = [item for item in str(veridns.get("incremental_errors", "")).split("|") if item]
    a_verdict = verdict_from_errors(a_errors, properties)
    v_verdict = {prop: prop not in set(v_errors) for prop in properties}
    rows = []
    matches = True
    for prop in properties:
        match = a_verdict[prop] == v_verdict[prop]
        matches = matches and match
        rows.append({
            "group": aether["group"],
            "dataset": aether["dataset"],
            "dataset_id": aether["dataset_id"],
            "scenario": aether["scenario"],
            "property": prop,
            "aether_pass": a_verdict[prop],
            "veridns_pass": v_verdict[prop],
            "matches_aether": match,
            "aether_errors": "|".join(a_errors),
            "veridns_errors": "|".join(v_errors),
            "oracle": "Aether",
        })
    return matches, rows


def speedup(veridns: str, aether: str):
    try:
        v = float(veridns)
        a = float(aether)
        return v / a if a > 0 else ""
    except Exception:
        return ""


def write_advantages(summary_rows: list[dict], features_by_id: dict[str, dict], out_dir: Path) -> None:
    rows = []
    for row in summary_rows:
        if row["status"] != "ok":
            continue
        feature = features_by_id[row["dataset_id"]]
        rows.append({
            "group": row["group"],
            "dataset": row["dataset"],
            "dataset_id": row["dataset_id"],
            "category": feature["category"],
            "scenario": row["scenario"],
            "aether_incremental_ms": row["aether_incremental_ms"],
            "veridns_incremental_ms": row["veridns_incremental_ms"],
            "veridns_full_update_ms": row["veridns_full_update_ms"],
            "incremental_speedup": speedup(row["veridns_incremental_ms"], row["aether_incremental_ms"]),
            "full_update_speedup": speedup(row["veridns_full_update_ms"], row["aether_incremental_ms"]),
            "veridns_matches_aether": row["veridns_matches_aether"],
        })
    base.write_csv(out_dir / "advantage_by_case.csv", rows, [
        "group", "dataset", "dataset_id", "category", "scenario",
        "aether_incremental_ms", "veridns_incremental_ms", "veridns_full_update_ms",
        "incremental_speedup", "full_update_speedup", "veridns_matches_aether",
    ])
    for field, filename in [("category", "advantage_by_feature.csv"), ("scenario", "advantage_by_scenario.csv")]:
        buckets = defaultdict(list)
        for row in rows:
            if row["incremental_speedup"] != "":
                buckets[row[field]].append(float(row["incremental_speedup"]))
        out_rows = []
        for name, values in sorted(buckets.items()):
            values = sorted(values)
            out_rows.append({
                field: name,
                "cases": len(values),
                "mean_incremental_speedup": sum(values) / len(values),
                "median_incremental_speedup": values[len(values) // 2],
                "aether_faster_cases": sum(1 for value in values if value > 1),
            })
        base.write_csv(out_dir / filename, out_rows, [field, "cases", "mean_incremental_speedup", "median_incremental_speedup", "aether_faster_cases"])


def main() -> None:
    args = parse_args()
    properties = selected_properties(args)
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jobs(out_dir / "properties.txt", properties)

    features = []
    prepared = {}
    for group, src_dir in source_datasets(args):
        dataset_id = f"{group}/{src_dir.name}"
        features.append({"dataset_id": dataset_id, **base.summarize_features(group, src_dir)})
        prepared[dataset_id] = base.prepare_dataset(group, src_dir, out_dir)
    feature_fields = ["group", "dataset", "dataset_id", "files", "total_rr", *base.CORE_TYPES, "wildcard", "rewrite_rr", "rewrite_ratio", "delegation_rr", "delegation_ratio", "avg_rr_per_file", "max_rr_per_file", "avg_owner_depth", "max_owner_depth", "category"]
    base.write_csv(out_dir / "features.csv", features, feature_fields)
    features_by_id = {row["dataset_id"]: row for row in features}

    cases = []
    for feature in features:
        dataset_dir = prepared[feature["dataset_id"]]
        for scenario in selected_scenarios(args):
            update = base.build_update(dataset_dir, scenario)
            case = {
                "group": feature["group"],
                "dataset": feature["dataset"],
                "dataset_id": feature["dataset_id"],
                "scenario": scenario,
            }
            case.update({"status": "ok", "update": update} if update["status"] == "ok" else update)
            cases.append(case)
    base.write_updates(cases, out_dir / "updates.csv")
    base.write_skips(cases, out_dir / "skipped_updates.csv")

    for path, fields in [
        (out_dir / "summary.csv", SUMMARY_FIELDS),
        (out_dir / "aether_raw.csv", RAW_FIELDS),
        (out_dir / "veridns_raw.csv", RAW_FIELDS),
        (out_dir / "verdict_consistency.csv", ["group", "dataset", "dataset_id", "scenario", "property", "aether_pass", "veridns_pass", "matches_aether", "aether_errors", "veridns_errors", "oracle"]),
    ]:
        base.init_csv(path, fields)

    summary_rows = []
    consistency_rows = []
    cases_by_dataset = defaultdict(list)
    for case in cases:
        cases_by_dataset[case["dataset_id"]].append(case)

    for dataset_id, dataset_cases in cases_by_dataset.items():
        dataset_dir = prepared[dataset_id]
        cache = None
        cache_error = None
        if not args.skip_veridns:
            print(f"VeriDNS {dataset_id}: building initial cache", flush=True)
            try:
                cache = base.build_veridns_cache_with_timeout(dataset_dir, args.veridns_cache_timeout)
            except Exception as exc:
                cache_error = f"initial cache failed: {exc!r}"
        for case in dataset_cases:
            aether_row = {"status": "skipped"} if args.skip_aether else run_aether_property_case(dataset_dir, case, out_dir, properties, args.aether_timeout)
            veridns_row = {"status": "skipped"} if args.skip_veridns else run_veridns_property_case(cache, cache_error, case, properties)
            if not args.skip_aether:
                append_csv(out_dir / "aether_raw.csv", aether_row, RAW_FIELDS)
            if not args.skip_veridns:
                append_csv(out_dir / "veridns_raw.csv", veridns_row, RAW_FIELDS)
            matches, verdict_rows = compare_verdicts(aether_row, veridns_row, properties)
            for row in verdict_rows:
                consistency_rows.append(row)
                append_csv(out_dir / "verdict_consistency.csv", row, ["group", "dataset", "dataset_id", "scenario", "property", "aether_pass", "veridns_pass", "matches_aether", "aether_errors", "veridns_errors", "oracle"])

            status = "ok" if aether_row.get("status") == "ok" and veridns_row.get("status") == "ok" else "error"
            if case["status"] != "ok":
                status = "skipped"
            summary = {
                "group": case["group"],
                "dataset": case["dataset"],
                "dataset_id": case["dataset_id"],
                "scenario": case["scenario"],
                "status": status,
                "zone_files": veridns_row.get("zone_files", ""),
                "updated_zone_file": case.get("update", {}).get("file_name", ""),
                "rr_count": veridns_row.get("rr_count", ""),
                "aether_initial_ms": aether_row.get("initial_total_ms", ""),
                "aether_incremental_ms": aether_row.get("incremental_ms", ""),
                "veridns_initial_ms": veridns_row.get("initial_total_ms", ""),
                "veridns_incremental_ms": veridns_row.get("incremental_ms", ""),
                "veridns_full_update_ms": veridns_row.get("full_update_ms", ""),
                "properties": "|".join(properties),
                "aether_initial_pass": aether_row.get("initial_property_pass", ""),
                "aether_incremental_pass": aether_row.get("incremental_property_pass", ""),
                "aether_errors": aether_row.get("incremental_errors", ""),
                "veridns_initial_pass": veridns_row.get("initial_property_pass", ""),
                "veridns_incremental_pass": veridns_row.get("incremental_property_pass", ""),
                "veridns_errors": veridns_row.get("incremental_errors", ""),
                "veridns_matches_aether": matches,
                "oracle": "Aether" if matches != "" else "",
                "detail": f"aether={aether_row.get('detail', '')}; veridns={veridns_row.get('detail', '')}",
            }
            summary_rows.append(summary)
            append_csv(out_dir / "summary.csv", summary, SUMMARY_FIELDS)
            print(f"{dataset_id} {case['scenario']}: {status} match={matches}", flush=True)

    write_advantages(summary_rows, features_by_id, out_dir)
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
