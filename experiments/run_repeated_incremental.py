#!/usr/bin/env python3
"""Run repeated small incremental updates and aggregate per-step timings."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import run_incremental_all as base


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "experiments" / "results" / "incremental_repeated"
RATIOS = [0.10, 0.20]
AGG_FIELDS = [
    "tool", "group", "dataset", "dataset_id", "scenario", "target_ratio",
    "status", "target_rr_updates", "planned_steps", "executed_steps",
    "successful_steps", "failed_steps", "achieved_ratio", "zone_files",
    "updated_zone_file", "rr_count", "initial_total_ms", "mean_incremental_ms",
    "median_incremental_ms", "min_incremental_ms", "max_incremental_ms",
    "mean_full_update_ms", "detail",
]
STEP_FIELDS = [
    "tool", "group", "dataset", "dataset_id", "scenario", "target_ratio",
    "step", "status", "updated_zone_file", "incremental_ms",
    "full_update_ms", "detail",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", action="append", choices=[*base.GROUPS, "all"], default=[])
    parser.add_argument("--dataset", action="append", default=[])
    parser.add_argument("--scenario", action="append", choices=base.SCENARIOS, default=[])
    parser.add_argument("--ratio", action="append", type=float, default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-steps", type=int, default=100, help="0 means no cap.")
    parser.add_argument("--out-dir", type=Path, default=OUT_ROOT)
    parser.add_argument("--skip-aether", action="store_true")
    parser.add_argument("--skip-veridns", action="store_true")
    parser.add_argument("--veridns-cache-timeout", type=float, default=0.0)
    parser.add_argument("--aether-timeout", type=float, default=0.0)
    return parser.parse_args()


def selected_groups(args: argparse.Namespace) -> list[str]:
    if not args.group:
        return ["files-100-500"]
    if "all" in args.group:
        return base.GROUPS
    return args.group


def selected_scenarios(args: argparse.Namespace) -> list[str]:
    return args.scenario or base.SCENARIOS


def selected_ratios(args: argparse.Namespace) -> list[float]:
    return args.ratio or RATIOS


def source_datasets(args: argparse.Namespace) -> list[tuple[str, Path]]:
    rows = []
    wanted = set(args.dataset)
    for group in selected_groups(args):
        group_dir = base.CENSUS_ROOT / group
        for dataset_dir in sorted(path for path in group_dir.iterdir() if path.is_dir()):
            if wanted and dataset_dir.name not in wanted:
                continue
            rows.append((group, dataset_dir))
    rows.sort(key=lambda item: (base.GROUPS.index(item[0]), item[1].name))
    return rows[: args.limit] if args.limit else rows


def median(values: list[float]) -> float:
    values = sorted(values)
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def unique_records(records: list[base.ResourceRecord], rr_type: str | None = None) -> list[base.ResourceRecord]:
    seen = set()
    output = []
    for record in records:
        domain, rtype, value = base.record_parts(record)
        if rr_type and rtype != rr_type:
            continue
        key = (domain, rtype, value)
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def choose_zone_for_scenario(cache: dict, scenario: str):
    best = None
    best_records = []
    rr_type = {"A_UPDATE": "A", "NS_UPDATE": "NS", "CNAME_UPDATE": "CNAME"}.get(scenario)
    for file_name, zone in cache["zones"].items():
        records = unique_records(zone["records"], rr_type)
        if scenario == "A_ADD":
            records = unique_records(zone["records"])
        if len(records) > len(best_records):
            best = file_name
            best_records = records
    return best, best_records


def build_step_update(cache: dict, scenario: str, file_name: str, source_records: list[base.ResourceRecord], step: int) -> dict:
    zone = cache["zones"][file_name]["zone_info"]
    origin = zone["Origin"].rstrip(".")
    if scenario == "A_ADD":
        record = base.ResourceRecord(f"__repeat_{step}.{origin}.", "A", f"192.0.2.{1 + (step % 250)}")
        return {
            "status": "ok",
            "scenario": scenario,
            "file_name": file_name,
            "ops": [("ADD", record)],
        }

    old_record = source_records[step % len(source_records)]
    domain, rtype, _ = base.record_parts(old_record)
    new_value = {
        "A": f"192.0.2.{1 + (step % 250)}",
        "NS": f"ns-repeat-{step}.{origin}.",
        "CNAME": f"cname-repeat-{step}.{origin}.",
    }[rtype]
    new_record = base.ResourceRecord(domain, rtype, new_value)
    return {
        "status": "ok",
        "scenario": scenario,
        "file_name": file_name,
        "ops": [("DEL", old_record), ("ADD", new_record)],
    }


def make_case(feature: dict, scenario: str, update: dict) -> dict:
    return {
        "group": feature["group"],
        "dataset": feature["dataset"],
        "dataset_id": feature["dataset_id"],
        "scenario": scenario,
        "status": "ok",
        "update": update,
    }


def append_csv(path: Path, row: dict, fieldnames: list[str]) -> None:
    with path.open("a", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writerow({key: row.get(key, "") for key in fieldnames})


def aggregate_rows(tool: str, feature: dict, scenario: str, ratio: float, rows: list[dict], target: int, planned: int, rr_count: int, zone_files: int, file_name: str) -> dict:
    ok_rows = [row for row in rows if row["status"] == "ok"]
    values = [float(row["incremental_ms"]) for row in ok_rows if row.get("incremental_ms") not in ("", None)]
    full_values = [float(row["full_update_ms"]) for row in ok_rows if row.get("full_update_ms") not in ("", None)]
    status = "ok" if values else "error"
    if len(ok_rows) < planned:
        status = "partial" if values else "error"
    detail = "; ".join(row.get("detail", "") for row in rows if row["status"] != "ok")[:500]
    return {
        "tool": tool,
        "group": feature["group"],
        "dataset": feature["dataset"],
        "dataset_id": feature["dataset_id"],
        "scenario": scenario,
        "target_ratio": ratio,
        "status": status,
        "target_rr_updates": target,
        "planned_steps": planned,
        "executed_steps": len(rows),
        "successful_steps": len(ok_rows),
        "failed_steps": len(rows) - len(ok_rows),
        "achieved_ratio": len(ok_rows) / rr_count if rr_count else "",
        "zone_files": zone_files,
        "updated_zone_file": file_name,
        "rr_count": rr_count,
        "initial_total_ms": ok_rows[0].get("initial_total_ms", "") if ok_rows else "",
        "mean_incremental_ms": sum(values) / len(values) if values else "",
        "median_incremental_ms": median(values) if values else "",
        "min_incremental_ms": min(values) if values else "",
        "max_incremental_ms": max(values) if values else "",
        "mean_full_update_ms": sum(full_values) / len(full_values) if full_values else "",
        "detail": detail,
    }


def write_advantages(agg_rows: list[dict], features_by_id: dict[str, dict], out_dir: Path) -> None:
    pairs = {}
    for row in agg_rows:
        if row["status"] not in ("ok", "partial"):
            continue
        if row.get("mean_incremental_ms") in ("", None):
            continue
        key = (row["dataset_id"], row["scenario"], str(row["target_ratio"]))
        pairs.setdefault(key, {})[row["tool"]] = row

    advantage_rows = []
    for (dataset_id, scenario, ratio), tools in pairs.items():
        if "Aether" not in tools or "VeriDNS" not in tools:
            continue
        aether = tools["Aether"]
        veridns = tools["VeriDNS"]
        a = float(aether["mean_incremental_ms"])
        v = float(veridns["mean_incremental_ms"])
        feature = features_by_id[dataset_id]
        advantage_rows.append({
            "group": feature["group"],
            "dataset": feature["dataset"],
            "dataset_id": dataset_id,
            "category": feature["category"],
            "scenario": scenario,
            "target_ratio": ratio,
            "aether_mean_incremental_ms": a,
            "veridns_mean_incremental_ms": v,
            "incremental_speedup": v / a if a > 0 else "",
            "aether_successful_steps": aether["successful_steps"],
            "veridns_successful_steps": veridns["successful_steps"],
        })
    base.write_csv(out_dir / "advantage_by_case.csv", advantage_rows, [
        "group", "dataset", "dataset_id", "category", "scenario", "target_ratio",
        "aether_mean_incremental_ms", "veridns_mean_incremental_ms",
        "incremental_speedup", "aether_successful_steps", "veridns_successful_steps",
    ])


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    features = []
    prepared = {}
    for group, src_dir in source_datasets(args):
        dataset_id = f"{group}/{src_dir.name}"
        features.append({"dataset_id": dataset_id, **base.summarize_features(group, src_dir)})
        prepared[dataset_id] = base.prepare_dataset(group, src_dir, out_dir)

    feature_fields = ["group", "dataset", "dataset_id", "files", "total_rr", *base.CORE_TYPES, "wildcard", "rewrite_rr", "rewrite_ratio", "delegation_rr", "delegation_ratio", "avg_rr_per_file", "max_rr_per_file", "avg_owner_depth", "max_owner_depth", "category"]
    base.write_csv(out_dir / "features.csv", features, feature_fields)
    features_by_id = {row["dataset_id"]: row for row in features}
    for path, fields in [
        (out_dir / "summary.csv", AGG_FIELDS),
        (out_dir / "aether_raw.csv", AGG_FIELDS),
        (out_dir / "veridns_raw.csv", AGG_FIELDS),
        (out_dir / "step_raw.csv", STEP_FIELDS),
    ]:
        base.init_csv(path, fields)

    updates_path = out_dir / "updates.csv"
    with updates_path.open("w", newline="", encoding="utf-8") as fp:
        csv.writer(fp).writerow(["dataset", "zone_file", "scenario", "target_ratio", "step", "op", "domain", "type", "rdata"])

    agg_rows = []
    for feature in features:
        dataset_dir = prepared[feature["dataset_id"]]
        cache = None
        cache_error = None
        if not args.skip_veridns:
            print(f"VeriDNS {feature['dataset_id']}: building initial cache", flush=True)
            try:
                cache = base.build_veridns_cache_with_timeout(dataset_dir, args.veridns_cache_timeout)
            except Exception as exc:
                cache_error = f"initial cache failed: {exc!r}"
        if cache is None and not cache_error:
            try:
                cache = base.build_veridns_cache_with_timeout(dataset_dir, 0)
            except Exception as exc:
                cache_error = f"initial cache failed: {exc!r}"

        rr_count = cache["rr_count"] if cache else int(feature["total_rr"])
        zone_files = len(cache["metadata"]["ZoneFiles"]) if cache else int(feature["files"])
        for scenario in selected_scenarios(args):
            if cache_error:
                for ratio in selected_ratios(args):
                    for tool in ["VeriDNS", "Aether"]:
                        if (tool == "VeriDNS" and args.skip_veridns) or (tool == "Aether" and args.skip_aether):
                            continue
                        row = aggregate_rows(tool, feature, scenario, ratio, [], math.ceil(rr_count * ratio), 0, rr_count, zone_files, "")
                        row["detail"] = cache_error
                        agg_rows.append(row)
                        append_csv(out_dir / "summary.csv", row, AGG_FIELDS)
                        append_csv(out_dir / ("veridns_raw.csv" if tool == "VeriDNS" else "aether_raw.csv"), row, AGG_FIELDS)
                continue

            file_name, source_records = choose_zone_for_scenario(cache, scenario)
            for ratio in selected_ratios(args):
                target = max(1, math.ceil(rr_count * ratio))
                if args.max_steps > 0:
                    planned = min(target, args.max_steps)
                else:
                    planned = target
                if not file_name or (scenario != "A_ADD" and not source_records):
                    planned = 0

                veridns_rows = []
                aether_rows = []
                for step in range(planned):
                    update = build_step_update(cache, scenario, file_name, source_records, step)
                    case = make_case(feature, scenario, update)
                    with updates_path.open("a", newline="", encoding="utf-8") as fp:
                        writer = csv.writer(fp)
                        for op, record in update["ops"]:
                            domain, rtype, value = base.record_parts(record)
                            writer.writerow([feature["dataset_id"], file_name, scenario, ratio, step, op, domain, rtype, value])
                    if not args.skip_veridns:
                        row = base.run_veridns_case_cached(cache, None, case)
                        veridns_rows.append(row)
                        append_csv(out_dir / "step_raw.csv", {**row, "target_ratio": ratio, "step": step}, STEP_FIELDS)
                    if not args.skip_aether:
                        row = base.run_aether_case(dataset_dir, case, out_dir / f"ratio_{ratio}" / f"step_{step}", args.aether_timeout)
                        aether_rows.append(row)
                        append_csv(out_dir / "step_raw.csv", {**row, "target_ratio": ratio, "step": step}, STEP_FIELDS)

                for tool, rows in [("VeriDNS", veridns_rows), ("Aether", aether_rows)]:
                    if (tool == "VeriDNS" and args.skip_veridns) or (tool == "Aether" and args.skip_aether):
                        continue
                    agg = aggregate_rows(tool, feature, scenario, ratio, rows, target, planned, rr_count, zone_files, file_name or "")
                    agg_rows.append(agg)
                    append_csv(out_dir / "summary.csv", agg, AGG_FIELDS)
                    append_csv(out_dir / ("veridns_raw.csv" if tool == "VeriDNS" else "aether_raw.csv"), agg, AGG_FIELDS)
                    print(f"{tool} {feature['dataset_id']} {scenario} ratio={ratio}: {agg['status']} mean={agg['mean_incremental_ms']} steps={agg['successful_steps']}/{planned}", flush=True)

    write_advantages(agg_rows, features_by_id, out_dir)
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
