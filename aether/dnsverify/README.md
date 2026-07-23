# Aether DNS 验证原型

本仓库是论文 **"Scalable DNS Configuration Verification via the LEC-native Query Resolution Graph"** 对应的 Rust 原型实现。

Aether 将权威 DNS 解析建模为 query resolution graph。系统会为每个 nameserver 构建 local equivalence classes，即 LEC，然后通过符号执行探索所有可能的 DNS 解析路径，检查配置属性，并模拟一次 zone file 增量更新来测量增量验证开销。

## 目录结构

```text
.
|-- Cargo.toml              # Rust 包配置和依赖
|-- Cargo.lock              # 依赖锁定文件
|-- build_release.sh        # Linux/macOS 下的 release 构建脚本
|-- diff-with-VeriDNS.txt   # 与 VeriDNS 设计差异相关的笔记
`-- src
    |-- main.rs             # CLI 入口
    |-- lib.rs              # 端到端验证流程
    |-- zonefile_parser.rs  # DNS zone file 解析器
    |-- record.rs           # DNS record 数据结构
    |-- utils.rs            # metadata 解析和域名辅助函数
    `-- lec/                # LEC 构建、符号执行、属性检查
```

## 环境要求

- Rust stable 工具链和 Cargo。
- 一个 shell 环境。Windows PowerShell 可以直接运行 Cargo 命令；`build_release.sh` 适合 bash 类 shell。
- 待验证的 DNS zone files，以及每个待验证 zone 对应的 metadata JSON 文件。

如果本机没有 `cargo` 命令，请先从 <https://rustup.rs/> 安装 Rust。

## 构建

在本目录下运行：

```bash
cargo build --release
```

构建后的二进制文件位于：

```text
target/release/dnsv
```

开发阶段可以运行：

```bash
cargo check
cargo test
```

注意：仓库里的 `build_release.sh` 当前假设二进制文件名等于目录名。但 Cargo 包名是 `dnsv`，目录名是 `dnsverify`，两者不一致。因此在脚本修复前，建议直接使用 `cargo build --release`。

## 输入格式

当前实现的 CLI 主要通过 CSV 批量运行。CSV 每一行指定一个 zone 名称，以及这个 zone 对应的 metadata JSON 文件。

### 批量 CSV

CSV 由 Rust 的 `csv` crate 读取，建议带 header。程序实际使用前两列：

```csv
zone,metadata
example.com,path/to/example.com/metadata.json
```

路径解析规则：

- CSV 路径相对于当前工作目录解析。
- metadata 路径按照 CSV 中写入的路径直接解析。
- metadata 内部的 zone file 路径相对于 metadata JSON 所在目录解析。

### Metadata JSON

每个 metadata JSON 的格式如下：

```json
{
  "TopNameServers": ["ns1.example.net"],
  "ZoneFiles": [
    {
      "FileName": "example.com.zone",
      "NameServer": "ns1.example.net",
      "Origin": "example.com"
    }
  ]
}
```

字段含义：

- `TopNameServers`：符号执行 DNS 解析时的入口 nameserver。
- `ZoneFiles`：参与验证的权威 zone files。
- `FileName`：zone file 路径，相对于 metadata JSON 所在目录。
- `NameServer`：托管该 zone file 的逻辑 nameserver 名称。
- `Origin`：可选的 zone origin。如果省略，解析器会尝试从 zone file 中的 `$ORIGIN` 或 SOA record 推断。

### Zone File

当前 parser 支持常见的权威 DNS zone file 结构：

- 指令：`$ORIGIN`、`$TTL`、`$INCLUDE`
- 记录类型：`A`、`AAAA`、`CNAME`、`DNAME`、`MX`、`NS`、`PTR`、`SOA`、`TXT`
- 带括号的多行 record
- 以 `;` 开头的注释
- 相对 owner name 和绝对 owner name

parser 会静态拒绝以下配置：

- DNAME 自环
- wildcard DNAME record
- 同一个 owner name 下重复的 CNAME record
- 同一个 owner name 下 CNAME 与其他类型 record 共存

## 运行

批量验证命令：

```bash
cargo run --release -- --output output.csv --trace traces c zones.csv
```

如果已经构建完成，也可以直接运行二进制：

```bash
target/release/dnsv --output output.csv --trace traces c zones.csv
```

Windows PowerShell 下：

```powershell
cargo run --release -- --output output.csv --trace traces c zones.csv
```

CLI 参数：

```text
dnsv [OPTIONS] <COMMAND>

Commands:
  c <csv>                 批量模式。CSV header: zone,metadata
  m <domain> <metadata>   metadata 模式占位；当前只会打印参数

Options:
  -j, --jobs <jobs>       可选。每行一个待检查属性名称
  -o, --output <output>   输出 CSV 路径。默认: output.csv
  -t, --trace <trace>     trace 输出目录。默认: traces
  -h, --help              显示帮助信息
```

`main.rs` 中默认的 property 列表是：

```text
hops
rewrites
too long
zone loop
delegation consistency
lame delegation
rewrite blackholing
```

注意：当前实现中，`jobs` 文件会被解析并写入日志，但还没有真正用于过滤属性检查。实际报告的检查项由 `src/lec/trace_log.rs` 中实现的 checker 决定。

## 输出

主要输出是一个性能统计 CSV。默认路径是 `output.csv`。

列名如下：

```text
zone
num_lec
io_time (ms)
construction_time (ms)
symbolic_time (ms)
property_checking_time (ms)
re_construction_time (ms)
re_symbolic_time (ms)
re_property_checking_time (ms)
```

含义：

- `zone`：批量 CSV 中的 zone 名称。
- `num_lec`：Aether 构建出的 local equivalence class 数量。
- `io_time`：读取 metadata 和解析 zone file 的时间。
- `construction_time`：初始 LEC/QRG 构建时间。
- `symbolic_time`：初始符号执行时间。
- `property_checking_time`：初始属性检查时间。
- `re_construction_time`：模拟 zone file 更新并重构受影响结构的时间。
- `re_symbolic_time`：增量符号执行时间。
- `re_property_checking_time`：增量属性检查时间。

运行日志由 `env_logger` 控制。可以通过 `RUST_LOG` 调整日志级别：

```bash
RUST_LOG=info cargo run --release -- -o output.csv -t traces c zones.csv
RUST_LOG=debug cargo run --release -- -o output.csv -t traces c zones.csv
```

PowerShell 下：

```powershell
$env:RUST_LOG = "info"
cargo run --release -- -o output.csv -t traces c zones.csv
```

## 最小示例数据

创建如下文件结构：

```text
examples/
`-- example.com/
    |-- metadata.json
    `-- example.com.zone
zones.csv
```

`zones.csv`：

```csv
zone,metadata
example.com,examples/example.com/metadata.json
```

`examples/example.com/metadata.json`：

```json
{
  "TopNameServers": ["ns1.example.com"],
  "ZoneFiles": [
    {
      "FileName": "example.com.zone",
      "NameServer": "ns1.example.com",
      "Origin": "example.com"
    }
  ]
}
```

`examples/example.com/example.com.zone`：

```zone
$ORIGIN example.com.
$TTL 3600
@ IN SOA ns1.example.com. admin.example.com. (
  2026061501 3600 1800 604800 86400
)
@ IN NS ns1.example.com.
ns1 IN A 192.0.2.1
www IN A 192.0.2.10
```

运行：

```bash
cargo run --release -- -o output.csv -t traces c examples/zones.csv
```

## 当前代码状态

这个仓库目前看起来是一个研究原型快照。原始 CLI 入口中有一段尚未完成的 trace dump 代码：它把 `run(...)` 当成会返回 trace manager 的函数使用，并访问了不存在或不可见的 `tl_mgr.traces`、`print_trace`、`lec_mgr`。当前版本已经做了最小修复：删除这段未完成的 trace dump 逻辑，保留 `run(...)` 内部的构建、符号执行、属性检查和性能 CSV 输出流程。

当前环境下已经验证通过：

```bash
cargo check
cargo build --release
target/release/dnsv.exe --help
```
