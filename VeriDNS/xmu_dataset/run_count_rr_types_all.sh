#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COUNTER="${SCRIPT_DIR}/count_rr_types.py"
OUTPUT="${1:-${SCRIPT_DIR}/rr_type_counts_all.csv}"

datasets=()
while IFS= read -r -d '' dataset_dir; do
  if find "${dataset_dir}" -maxdepth 1 -type f -name "*.txt" -print -quit | grep -q .; then
    datasets+=("${dataset_dir}")
  fi
done < <(find "${SCRIPT_DIR}" -mindepth 1 -maxdepth 1 -type d ! -name "__pycache__" -print0 | sort -z)

if [[ ${#datasets[@]} -eq 0 ]]; then
  echo "No dataset directories with .txt zone files found under ${SCRIPT_DIR}" >&2
  exit 1
fi

python3 "${COUNTER}" "${datasets[@]}" --output "${OUTPUT}" --summary-only
