import argparse
import csv
import json
import sys
from pathlib import Path
from time import perf_counter_ns


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src_muilt"
sys.path.insert(0, str(SRC))

from config.check_config import check_self  # noqa: E402
from core.zone_graph import ZoneGraph  # noqa: E402
from tools.zone_file_parser import ZoneFileParser  # noqa: E402


def run_zone(dataset_dir, zone_info):
    file_name = zone_info["FileName"]
    origin = zone_info.get("Origin")
    zone_file_path = dataset_dir / file_name

    start = perf_counter_ns()
    parser = ZoneFileParser(
        zone_name=file_name,
        zone_file_path=str(zone_file_path),
        origin=origin,
    )
    records = parser.get_records()
    parsed = perf_counter_ns()

    graph = ZoneGraph(origin=origin, rr_list=records)
    built = perf_counter_ns()

    check_result = check_self(graph)
    checked = perf_counter_ns()

    return {
        "file_name": file_name,
        "origin": origin,
        "rr_count": len(records),
        "parse_ms": (parsed - start) / 1e6,
        "build_graph_ms": (built - parsed) / 1e6,
        "check_ms": (checked - built) / 1e6,
        "total_ms": (checked - start) / 1e6,
        "bug_count": len(check_result),
        "bugs": check_result,
    }


def load_zone_files(dataset_dir):
    metadata_path = dataset_dir / "metadata.json"
    with metadata_path.open("r", encoding="utf-8") as fp:
        metadata = json.load(fp)
    return metadata.get("ZoneFiles", [])


def write_outputs(results, csv_path, bugs_path):
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "file_name",
                "origin",
                "rr_count",
                "parse_ms",
                "build_graph_ms",
                "check_ms",
                "total_ms",
                "bug_count",
            ],
        )
        writer.writeheader()
        for row in results:
            writer.writerow({key: row[key] for key in writer.fieldnames})

    bug_rows = [
        {
            "file_name": row["file_name"],
            "origin": row["origin"],
            "bugs": row["bugs"],
        }
        for row in results
        if row["bugs"]
    ]
    with bugs_path.open("w", encoding="utf-8") as fp:
        json.dump(bug_rows, fp, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dataset",
        nargs="?",
        default=str(ROOT / "xmu_dataset" / "test_ini"),
        help="Dataset directory containing metadata.json and zone files.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "experiment_results"),
        help="Directory for CSV timing and bug JSON outputs.",
    )
    args = parser.parse_args()

    dataset_dir = Path(args.dataset).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    results = [run_zone(dataset_dir, zone) for zone in load_zone_files(dataset_dir)]

    dataset_name = dataset_dir.name
    csv_path = out_dir / f"{dataset_name}_offline_times.csv"
    bugs_path = out_dir / f"{dataset_name}_offline_bugs.json"
    write_outputs(results, csv_path, bugs_path)

    for row in results:
        print(
            f"{row['file_name']}: rr={row['rr_count']} "
            f"parse={row['parse_ms']:.3f}ms "
            f"graph={row['build_graph_ms']:.3f}ms "
            f"check={row['check_ms']:.3f}ms "
            f"bugs={row['bug_count']}"
        )
    print(f"wrote {csv_path}")
    print(f"wrote {bugs_path}")


if __name__ == "__main__":
    main()
