#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/rulan_yang/DNS-verification"
SCRIPT="${REPO_DIR}/count_rr_types.py"
CENSUS_DIR="/home/rulan_yang/dns/census"
OUTPUT_TXT="${REPO_DIR}/census_rr_type_counts.txt"
MIN_FILES=100

if [[ ! -f "${SCRIPT}" ]]; then
  echo "missing count script: ${SCRIPT}" >&2
  exit 1
fi

if [[ ! -d "${CENSUS_DIR}" ]]; then
  echo "missing census directory: ${CENSUS_DIR}" >&2
  exit 1
fi

datasets=()
rr_types=()

while IFS= read -r -d '' dataset_dir; do
  file_count=$(find "${dataset_dir}" -maxdepth 1 -type f | wc -l)
  dataset_name=$(basename "${dataset_dir}")

  if (( file_count < MIN_FILES )); then
    case "${dataset_dir}" in
      "${CENSUS_DIR}/"*)
        echo "delete ${dataset_dir} (${file_count} files < ${MIN_FILES})"
        rm -rf -- "${dataset_dir}"
        ;;
      *)
        echo "refuse to delete unexpected path: ${dataset_dir}" >&2
        exit 1
        ;;
    esac
    continue
  fi

  if [[ -f "${OUTPUT_TXT}" ]] && awk -F '\t' -v dataset="${dataset_name}" 'NR > 1 && $1 == dataset { found = 1 } END { exit !found }' "${OUTPUT_TXT}"; then
    echo "skip completed ${dataset_dir}"
    continue
  fi

  datasets+=("${dataset_dir}")
done < <(find "${CENSUS_DIR}" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)

if (( ${#datasets[@]} == 0 )); then
  echo "no pending dataset directories with at least ${MIN_FILES} files under ${CENSUS_DIR}"
  echo "results appended to: ${OUTPUT_TXT}"
  exit 0
fi

mapfile -t rr_types < <(python3 "${SCRIPT}" "${datasets[@]}" --print-rr-types)

if [[ ! -f "${OUTPUT_TXT}" ]]; then
  printf "dataset\tfiles\ttotal" > "${OUTPUT_TXT}"
  for rr_type in "${rr_types[@]}"; do
    printf "\t%s" "${rr_type}" >> "${OUTPUT_TXT}"
  done
  printf "\n" >> "${OUTPUT_TXT}"
fi

for dataset_dir in "${datasets[@]}"; do
  dataset_name=$(basename "${dataset_dir}")
  if awk -F '\t' -v dataset="${dataset_name}" 'NR > 1 && $1 == dataset { found = 1 } END { exit !found }' "${OUTPUT_TXT}"; then
    echo "skip completed ${dataset_dir}"
    continue
  fi

  file_count=$(find "${dataset_dir}" -maxdepth 1 -type f | wc -l)
  echo "count ${dataset_dir} (${file_count} files)"
  python3 "${SCRIPT}" "${dataset_dir}" --text-output -o "${OUTPUT_TXT}" --rr-types "${rr_types[@]}"
done

echo "results appended to: ${OUTPUT_TXT}"
