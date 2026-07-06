# VeriDNS and Aether comparison experiments

This directory contains an external experiment harness for running Aether and
VeriDNS on the same `metadata.json` based workloads.

## Quick run

From the repository root:

```bash
python3 experiments/veridns_aether_compare.py --build-aether
```

Default datasets:

- `VeriDNS/xmu_dataset/12`
- `VeriDNS/xmu_dataset/13`
- `VeriDNS/xmu_dataset/14`
- `VeriDNS/xmu_dataset/15`
- `VeriDNS/xmu_dataset/all_correct`

Outputs are written to:

```text
experiments/results/veridns_aether/
|-- aether_input.csv
|-- aether.csv
|-- aether_traces/
|-- veridns.csv
|-- veridns_errors.json
`-- summary.md
```

## Notes

- Aether is measured through `aether/dnsverify/target/release/dnsv`.
- VeriDNS is measured by importing the existing Python modules under
  `VeriDNS/src_muilt` and timing parse, graph construction and `check_self`.
- Aether reports one row per dataset metadata file. VeriDNS reports one row per
  zone file referenced by that metadata, because that is the granularity exposed
  by the current VeriDNS graph builder.
- The harness does not change either prototype's verifier logic.
