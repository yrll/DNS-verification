# Aether-only revision experiments

This harness runs only `aether/dnsverify/target/release/dnsv`. It does not import
or execute VeriDNS, GRoot, or Octopus.

## Build

```bash
cd aether/dnsverify
cargo build --release
```

## Smoke tests

```bash
python3 experiments/run_aether_revision_experiments.py \
  --microbench-only \
  --scenario A_ADD \
  --scenario DNAME_ADD \
  --repeat 3 \
  --out-dir experiments/results/aether_revision_micro_smoke

python3 experiments/merge_aether_revision_results.py \
  --in-dir experiments/results/aether_revision_micro_smoke

python3 experiments/plot_aether_revision_results.py \
  --in-dir experiments/results/aether_revision_micro_smoke
```

## Real workload example

```bash
python3 experiments/run_aether_revision_experiments.py \
  --real-only \
  --group files-100-500 \
  --limit 10 \
  --repeat 3 \
  --out-dir experiments/results/aether_revision_files_100_500
```

## Bound sensitivity example

Run the same workload with different output directories:

```bash
python3 experiments/run_aether_revision_experiments.py \
  --real-only \
  --group files-100-500 \
  --limit 10 \
  --max-query-depth 6 \
  --out-dir experiments/results/aether_revision_depth6

python3 experiments/run_aether_revision_experiments.py \
  --real-only \
  --group files-100-500 \
  --limit 10 \
  --max-query-depth 10 \
  --out-dir experiments/results/aether_revision_depth10
```

## Main outputs

- `aether_raw.csv`: one row per Aether run/repeat.
- `features.csv`: dataset characteristics used for correlation analysis.
- `skipped_updates.csv`: scenarios skipped because a dataset lacks the required record type.
- `summary_distribution.csv`: mean, median, geomean, percentiles, and CI.
- `feature_correlations.csv`: Pearson and Spearman correlations.
- `summary_by_case.csv`: per-case speedup against Aether full verification.
- `plots/`: generated figures when `pandas` and `matplotlib` are available.
