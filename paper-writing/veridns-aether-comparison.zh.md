# VeriDNS 和 Aether 对比实验说明

## 实验目标

该实验用于回答 reviewer 对 “为什么不直接使用 VeriDNS” 的问题。对比重点不是把 VeriDNS 描述成简单的语法检查器，而是明确区分两类能力：

- VeriDNS：基于已有 zone file 中的具体域名记录构建 zone graph / RSG，并对这些具体配置对象执行检查。
- Aether：基于每个 nameserver 的 LEC 和 QRG 做符号化 query-space 探索，覆盖未显式出现在 zone file 中但会被 wildcard、DNAME rewrite、delegation 等语义影响的查询空间。

## 可复现实验入口

脚本位置：

```bash
experiments/veridns_aether_compare.py
```

默认运行：

```bash
python3 experiments/veridns_aether_compare.py --build-aether
```

当前环境预检结果：

- Aether：当前机器没有 `cargo`，且已有 release 目录里只有 Windows 产物 `dnsv.exe`，不能在当前 Linux 环境直接执行。
- VeriDNS：当前 Python 环境缺少 `networkx`、`dnspython`、`pandas`、`psutil`。

安装 VeriDNS 依赖：

```bash
python3 -m pip install -r experiments/requirements-veridns.txt
```

安装 Rust/Cargo 后，可用 `--build-aether` 生成 Linux release 二进制。

## 输出指标

Aether 输出一行对应一个 metadata workload：

- `io_time (ms)`
- `construction_time (ms)`
- `symbolic_time (ms)`
- `property_checking_time (ms)`
- `re_construction_time (ms)`
- `re_symbolic_time (ms)`
- `re_property_checking_time (ms)`
- `num_lec`

VeriDNS 输出一行对应 metadata 中的一个 zone file：

- `io_time (ms)`
- `construction_time (ms)`
- `property_checking_time (ms)`
- `total_time (ms)`
- `rr_count`
- `check_result_count`

这个粒度差异来自两个 artifact 的当前接口：Aether 的 CLI 以整个 metadata workload 为单位，VeriDNS 当前 graph builder 暴露的是每个 zone file 的 parse/build/check 时间。

## 论文中建议报告方式

建议把实验分成两层报告：

1. Artifact-level performance comparison：在相同 metadata workload 上报告 Aether 和 VeriDNS 的构建、检查、端到端时间。明确说明 VeriDNS 当前可测粒度为 per-zone-file，而 Aether 为 per-workload。
2. Semantics-level coverage comparison：用 wildcard 和 DNAME 例子说明 Aether 的符号 query-space 探索可以覆盖未显式出现在配置中的查询，而 VeriDNS 的 RSG/zone-graph artifact 更接近具体配置对象上的检查。

谨慎措辞：

- 可以说 “VeriDNS artifact exposes concrete-record / concrete-zone-file oriented checking granularity.”
- 不建议直接说 “VeriDNS is only syntax-level”，除非重新核对论文和 artifact 后有明确证据。
- 如果 artifact 依赖或运行环境无法完全复现，应写成 artifact barrier，而不是把未跑通当作负面结果。
