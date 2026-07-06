# Aether 修订路线图


## 总体诊断

这篇文章从 NSDI 投稿到 SIGCOMM 投稿已经有明显进步：SIGCOMM 的 review 中有两个 weak accept，reviewer 普遍认可 LEC/QRG 这个思路有潜力。现在剩下的拒稿原因集中在少数几个反复出现的问题上：

1. 文章仍然没有把和 GRoot 的核心差异讲得足够精确。
2. Section 3.2 和 Algorithm 2 中关于 EC/LEC 的解释存在内部不一致。
3. 文章使用 "complete verification" 这一表述时比较脆弱，因为当前模型排除了 caching/DNSSEC，并且使用 bound/fuel 来保证终止。
4. 评估在速度提升上有说服力，但在实际意义、代表性、baseline、false positive 和 bug impact 上还不够有说服力。
5. VeriDNS 和 Octopus 的定位不够清楚，尤其是 VeriDNS 也声称支持 incremental DNS verification。
6. 除非稿件能给出清晰的问题定义、正确性论证和 microbenchmark 级别的因果解释，否则不少 reviewer 仍会把这篇文章看成一个优化版 GRoot。

下一版定位：

> Aether 不是 "GRoot but faster"。Aether 是一个面向 authoritative DNS configuration 的 LEC-native verifier，它基于 LEC 构造 query resolution graph，避免 global EC refinement。这个差异在 update-heavy 场景下尤其重要，因为局部变更不应该打碎全局 label graph，也不应该触发 whole-namespace recomputation。论文必须直接证明并测量这一点。


## Review 分数走势

| Venue | Reviews | 主要优点 | 主要阻塞原因 |
|---|---:|---|---|
| NSDI 2026 Fall | 1 weak accept, 3 weak rejects, 2 rejects | DNS verification 问题重要；速度提升明显；incremental verification 有价值 | Novelty 不清楚；GRoot delta 不清楚；缺少 proof/correctness；evaluation 窄；operational-track mismatch；写作和图 |
| SIGCOMM 2026 | 2 weak accepts, 3 weak rejects | LEC/QRG 核心想法合理；methodology 易读；performance promising | EC/LEC 不一致；performance significance 不足；model fidelity 问题；filtered dataset；VeriDNS 缺失；bug impact 和 prior-technique comparison 不足 |

## Revision Plan

### P1：Motivation & 核心设计/贡献

**Reviewer 来源**：NSDI-B, NSDI-C, NSDI-D, NSDI-E, NSDI-F, SIGCOMM-A, SIGCOMM-D, SIGCOMM-A1。

**问题**：
Reviewers 反复追问 Aether 和 GRoot 到底有什么本质区别。SIGCOMM-A 其实已经理解到一个可能的核心收益：Aether 避免了 GRoot global label graph 产生的 unreachable global ECs。但这个解释在论文中没有显式展开。多个 reviewer 还指出，GRoot 本身也使用 EC、symbolic execution 和 data-plane analogy。

**TODO**：

- 重点说明 "Why GRoot's global ECs are the bottleneck" 以及 LEC 的优势 (在 Introduction 或 Overview 前部加入一个小节 ?)

  - 非更新场景下：GRoot 的 global refinement 会放大 EC 数量 (举例说明)
    - 配置里有 went.com, went.net, where.went.com。GRoot 会生成 where.went.net 这样的EC，但这种 EC 实际是冗余的
  - 更新场景下：
    - EC 数量增长 远大于 LEC 数量的增长 (update record 类型和 LEC/EC 增长数量级的表格)
    - 某些 EC 会被重复 traverse，以及这部分 traverse 的时间占占总时间的比例多少 (实验说明)


----------------
----------------

| 更新类型 | GRoot 新增/更新的 EC 数量是否明显多于 Aether 的 LEC？ | GRoot 的 EC 影响 | Aether 的 LEC 影响 | 主要结论 |
|---|---|---|---|---|
| A/AAAA/MX/TXT 的 rdata 值更新 | 否 | 不新增 EC；相关 interpretation graph 可能失效 | 不新增 LEC；只更新本地 action | 只改变结果/action，不改变 query-space partition |
| wildcard 下插入 exact record | 否 | `O(k)` 个 EC 分裂 | 当前 nameserver 上 `O(k)` 个 LEC 分裂 | Aether 的优势主要是局部性，而不是 partition 数量更少 |
| 新增 delegation boundary | 否 | 新 delegated subtree 附近产生 `O(k)` 个 EC 分裂 | parent nameserver 上产生 `O(k)` 个 LEC 分裂 | 二者都会切分 namespace；Aether 将更新限制在局部 |
| 已有 NS/glue target 更新 | 否 | 不新增 EC；经过该 delegation 的大量 interpretation graph 可能失效 | 不新增 LEC；只更新本地 referral action | Aether 的优势是局部失效和局部重执行 |
| CNAME 更新 | 不一定 | target 侧产生 `O(k)` 个 EC 分裂；`O(n)` 个 interpretation graph 可能失效 | target nameserver 上产生 `O(k)` 个 LEC 分裂；可能重执行 `O(n)` 条 affected traces | CNAME 只作用于 exact name，因此 Aether 在 partition 数量上不一定有渐进优势 |
| DNAME 更新 | 是 | 在被 rewrite 的 source prefixes 下诱导出 `O(nk)` 个 EC 分裂 | target nameserver 上仅产生 `O(k)` 个 LEC 分裂；但可能存在 `O(nk)` 条 affected traces | 这是最清楚体现 GRoot EC 更新数量多于 Aether LEC 更新数量的场景 |

----------------
----------------

符号说明：

- `k`：新增记录数量。
- `n`：可能受影响的上游 alias/rewrite prefixes 或解析路径数量。


    



-----

### P2：Section 3.2 / Algorithm 2 中 LEC 定义/原理的不一致

**Reviewer 来源**：SIGCOMM-A, SIGCOMM-A1；同时关联 NSDI-B/E/F 的 novelty concern。

**问题**：
SIGCOMM-A 指出了一个严重技术歧义：前文说 Aether 会合并 identical action 的 records，但 Section 3.2 和 Algorithm 2 看起来是按相同的 `rname` 和 `rtype` 聚合，这更像 per-record，而不是 action-equivalent。Section 4.2 又说 LECs 可以 back-trace 到 specific record，进一步加强了 per-record 的理解。

**TODO**：
- 说明 Aether 合并 action-identical records 的原理和 DPV 是不同的，DPV 确实是 merge identical action (forwarding port)，Aether 并非简单的 merge action，而是把每个 local resolution trace 上 record 的 rname 合并



---------

### P3：completeness & scope 说明

**Reviewer 来源**：NSDI-B, NSDI-C, NSDI-E, SIGCOMM-C。

**问题**：
文中提到过模型是 "completeness"，但未 formal 解释相应含义。加上模型又抽象掉了如 resolvers、DNSSEC、caching 和 TTL 等细节，以及 (incremental) symbolic execution 又使用 path bound 和 label padding等方法。
当前排除了 DNS caching 和 DNSSEC。Reviewers 原则上可以接受 scope 限制，但当前文本仍然使用较强 correctness language，并且没有足够有说服力地解释 extension path。

**TODO**：
- 明确 completeness 的前提条件：首先 Aether 并非对整个 DNS system，而是 authoritative DNS zone files 做验证。可以在 bounded domain-name encoding 能表示的范围内，符号化覆盖所有 query names 和 query types，并检查这些 modeled authoritative nameservers 所诱导出的所有可行 resolution traces。
- 界定 scope
  - 当前支持的内容，如 record 类型，验证属性类型等
  - 当前无法支持的内容，如 DNSSEC validation 等
  - 可扩展支持的内容，如 DNS caching 等



----------------

### P4：Related work 对比

**Reviewer 来源**：SIGCOMM-D, SIGCOMM-E, SIGCOMM-A1, NSDI-C。

**问题**：
相关工作包括 GRoot、Liu et al. (SIGCOMM 2023)、Octopus、VeriDNS。其中VeriDNS 也支持 incremental DNS verification。当前文本说 VeriDNS 是 "approximate"，但没有支撑这个说法。Reviewers 因此认为这是 baseline 和 positioning gap。

**TODO**：
- 和 GRoot 区别：前文已说明
- 和 VeriDNS 区别 (已总结 `diff-with-VeriDNS.txt`)：但避免直接说 VeriDNS 只是 "syntax-level"，除非 VeriDNS 论文能支撑这个措辞。更稳妥的说法是：VeriDNS 的 RSG-based concrete traversal 可能漏掉 wildcard/DNAME semantics 诱导出的 behaviors，除非这些 behaviors 已经显式表示在被遍历的 concrete names 中。
- 和 Octopus 区别：【待补充】
- 和 Liu et al. (SIGCOMM 2023) 区别：【待补充】


-----

### P5：Aether 快的原因以及比 GRoot 快的原因说明（实验部分）

**Reviewer 来源**：NSDI-A, NSDI-E, NSDI-F, SIGCOMM-A, SIGCOMM-C, SIGCOMM-D, SIGCOMM-E, SIGCOMM-A1。

**问题**：
Reviewers 接受 Aether 更快，但质疑为什么更快、什么时候重要、speedups 是否只是 outliers 或 implementation artifacts。SIGCOMM-A 还认为 65 ms 到 12 ms 未必有实际意义。SIGCOMM-D 要求 mean/geomean 和按 zone characteristics 分析 speedup variation。

**TODO**：
- 对 full verification 和 incremental verification 报告 mean、median、geomean、p90/p95/p99、min/max 和 confidence intervals。
- 消融实验分析：
  - no local aggregation / raw rules
  - no BDD encoding
  - no parallel LEC construction
  - full recomputation vs incremental recomputation
- 相关性实验分析：
- record / merged records 数量
- rewrite density
- wildcard/DNAME/CNAME 数量。

- incremental-update / update storms 下的 tail-latency。


-----

### P6：数据集 filtering、representativeness 和 bug-impact 问题 (实验部分)

**Reviewer 来源**：SIGCOMM-B, SIGCOMM-C, SIGCOMM-E, SIGCOMM-A1, NSDI-F。

**问题**：
SIGCOMM-C 批评论文过滤掉了 180,000 个无法通过 `named-checkzone` 的 zones。SIGCOMM-B/E 质疑发现的 bugs 是否有实质影响、是否 active、是否能被 prior tools 发现。NSDI-F 认为 evaluation 太窄。

**TODO**：
- 增加 dataset-validity 小节。
- 按 error type 和数量分类 180K filtered zones。
- 报告 Aether 对每类 invalid category 是 reject、classify，还是可以 graceful handle。不要简单丢掉不分析。
- 如果 invalid zones 在模型范围之外，就明确说明，并把它们作为单独的 robustness/diagnostic workload。
- 对 campus/university errors 报告：
  - domains/subdomains 是否 active；
  - errors 是 injected 还是 real；
  - operators 是否 confirmed；
  - severity/impact；
  - 哪些 prior tools 能检测每类 error；
  - manual/operator validation 之后的 false positives。
- 如果可能，增加更大或公开的 error-detection dataset。如果隐私不允许 release，提供 sanitized artifact 或 reproducible synthetic workload。


------

## 建议的新论文结构

1. Introduction
   - DNS configuration verification 需要及时、反复的检查。
   - Global EC refinement 是 large 和 update-heavy DNS configurations 下的瓶颈。
   - Aether 的 thesis：local action-equivalence 加 QRG 能保留足够 semantics，同时避免 global partition explosion。
   - Contributions：QRG/LEC abstraction、带 scoped guarantees 的 symbolic execution、incremental recomputation、empirical evaluation。
2. Background and Problem Scope
   - Authoritative DNS model。
   - Supported records and properties。
   - Excluded resolver-side state, DNSSEC, caching, TTL。
   - query、log、trace、LEC、QRG 的定义。
3. Why Global ECs Fail to Scale
   - 用 running example 比较 GRoot 和 Aether。
   - Unreachable/redundant EC construction。
   - Cost model 和 update invalidation model。
4. LEC-native Query Resolution Graph
   - Encoding。
   - Match-action table computation。
   - QRG construction。
5. Symbolic Trace Generation and Property Checking
   - Algorithm。
   - Bounds 和 visited-state cache。
   - Correctness argument。
6. Incremental Verification
   - Update invalidation。
   - Incremental re-execution。
   - Correctness argument。
7. Evaluation
   - RQ1 capability and bug validation。
   - RQ2 performance distributions。
   - RQ3 ablations and causal analysis。
   - RQ4 update storm / real-time verification。
   - RQ5 comparison with GRoot and VeriDNS/Octopus where feasible。
8. Discussion and Limitations
   - DNSSEC/caching extension。
   - Invalid zones。
   - Operational integration and privacy。
9. Related Work
10. Conclusion

## 跨 reviewer 模式矩阵

| Pattern | Raised By | Priority | Main Fix |
|---|---|---:|---|
| GRoot delta 不清楚 | NSDI-B/C/D/E/F, SIGCOMM-A/D/A1 | P1 | 新增 GRoot-vs-Aether example、table 和 precise claims |
| Novelty 显得 incremental | NSDI-B/E/F, SIGCOMM-D/E | P1 | 围绕 LEC-native QRG 和 update-locality 重新定位，而不是泛泛讲 symbolic execution |
| 缺少 correctness/proof | NSDI-B/C/E, SIGCOMM-C | P1 | Scoped semantics 和 proof sketches |
| VeriDNS 缺失 | SIGCOMM-D/E/A1 | P1 | 用 wildcard/DNAME 的 semantic coverage examples 加强定位，可行时补 empirical comparison |
| Evaluation 窄或代表性不足 | NSDI-A/F, SIGCOMM-B/C/E/A1 | P1 | Invalid-zone analysis、bug validation、public/synthetic workload |
| Performance significance 不足 | SIGCOMM-A/D/A1 | P1 | Mean/geomean、update-storm scenario、ablations |
| DNSSEC/caching limitation | NSDI-E, SIGCOMM-B/C/A1 | P1 | Scope and extension discussion |
| Writing/clarity/figures | NSDI-B/C/E, SIGCOMM-A | P3 | Definitions、readable figures、grammar pass |
| Operational-track mismatch | NSDI-D/F | P2/P3 | 如果没有 deployment evidence，就投 research paper |



可将以下内容作为 revision-tracking table 的种子。

```yaml
- concern_id: P1-1-groot-delta
  reviewers: [NSDI-B, NSDI-C, NSDI-D, NSDI-E, NSDI-F, SIGCOMM-A, SIGCOMM-D, SIGCOMM-A1]
  commitment_extracted:
    - commitment_text: "澄清 Aether 与 GRoot 的主要差异，尤其是 EC generation 过程，以及 Aether 在哪些配置中最有优势。"
      commitment_type: add_clarification
      required_evidence_type: new_section
    - commitment_text: "通过 running example 增加 GRoot vs Aether 的对比。"
      commitment_type: add_analysis
      required_evidence_type: new_figure

- concern_id: P1-2-lec-consistency
  reviewers: [SIGCOMM-A]
  commitment_extracted:
    - commitment_text: "解决 action-equivalence claim 与 Algorithm 2 按 rname/rtype 分组之间的不一致。"
      commitment_type: restructure
      required_evidence_type: prose_edit
    - commitment_text: "增加 worked example，展示 action-identical records 是否会合并为一个 LEC。"
      commitment_type: add_clarification
      required_evidence_type: new_figure

- concern_id: P1-3-correctness-scope
  reviewers: [NSDI-B, NSDI-C, NSDI-E, SIGCOMM-C]
  commitment_extracted:
    - commitment_text: "定义 correctness、completeness、supported inputs 和 checked properties。"
      commitment_type: add_clarification
      required_evidence_type: new_section
    - commitment_text: "增加 LEC partitioning、symbolic trace preservation 和 incremental soundness 的 proof sketches。"
      commitment_type: add_analysis
      required_evidence_type: new_section
    - commitment_text: "澄清 k、n 和 delta 是 bounded verification parameters。"
      commitment_type: add_clarification
      required_evidence_type: methods_paragraph

- concern_id: P1-4-veridns
  reviewers: [SIGCOMM-D, SIGCOMM-E, SIGCOMM-A1]
  commitment_extracted:
    - commitment_text: "更详细地描述 Aether 与 VeriDNS 的差异。"
      commitment_type: add_analysis
      required_evidence_type: new_table
    - commitment_text: "对比 Aether 和 VeriDNS，若不能实验比较，则说明 artifact 障碍并提供 semantic examples。"
      commitment_type: add_experiment
      required_evidence_type: new_table
    - commitment_text: "增加 wildcard-after-CNAME-rewrite example，展示 VeriDNS 是否覆盖隐式 wildcard matches。"
      commitment_type: add_analysis
      required_evidence_type: new_figure
    - commitment_text: "增加 DNAME hidden-query-space example，展示为什么 symbolic all-domain coverage 重要。"
      commitment_type: add_analysis
      required_evidence_type: new_figure

- concern_id: P1-5-evaluation-causal
  reviewers: [NSDI-A, NSDI-E, NSDI-F, SIGCOMM-A, SIGCOMM-D, SIGCOMM-A1]
  commitment_extracted:
    - commitment_text: "报告 mean/geomean，并解释 speedups 是否是 outliers。"
      commitment_type: add_analysis
      required_evidence_type: new_table
    - commitment_text: "增加 ablations，区分 algorithmic gains 与 implementation optimizations/parallelism。"
      commitment_type: add_experiment
      required_evidence_type: new_table
    - commitment_text: "描述 verification time 降低会影响 usability 的实际场景。"
      commitment_type: add_clarification
      required_evidence_type: discussion_paragraph

- concern_id: P1-6-dataset-bugs
  reviewers: [SIGCOMM-B, SIGCOMM-C, SIGCOMM-E, SIGCOMM-A1, NSDI-F]
  commitment_extracted:
    - commitment_text: "解释为什么移除 180K syntax-problem zones 后，dataset 仍具有代表性。"
      commitment_type: add_analysis
      required_evidence_type: new_table
    - commitment_text: "澄清发现的 bugs 是否真实、active、有影响，以及是否能被 prior tools 检测到。"
      commitment_type: add_analysis
      required_evidence_type: new_table
    - commitment_text: "讨论 false positives 和 validation process。"
      commitment_type: add_clarification
      required_evidence_type: methods_paragraph

- concern_id: P1-7-dnssec-caching
  reviewers: [NSDI-E, SIGCOMM-B, SIGCOMM-C, SIGCOMM-A1]
  commitment_extracted:
    - commitment_text: "解释 Aether 如何扩展到 DNSSEC 和 caching。"
      commitment_type: add_clarification
      required_evidence_type: discussion_paragraph
    - commitment_text: "说明当前 guarantees 只适用于 authoritative DNS configuration semantics，而不是完整 recursive DNS behavior。"
      commitment_type: add_clarification
      required_evidence_type: prose_edit

- concern_id: P2-related-work
  reviewers: [NSDI-C, NSDI-F, SIGCOMM-D, SIGCOMM-E]
  commitment_extracted:
    - commitment_text: "增加 proper related work section，用于定位 DNS verification 和 DPV literature。"
      commitment_type: add_citation
      required_evidence_type: new_citation

- concern_id: P2-logs-traces
  reviewers: [NSDI-C]
  commitment_extracted:
    - commitment_text: "澄清 query logs 和 traces 包含什么，以及为什么 traces 重要。"
      commitment_type: add_clarification
      required_evidence_type: methods_paragraph

- concern_id: P2-operational-security
  reviewers: [NSDI-A, NSDI-D, NSDI-F]
  commitment_extracted:
    - commitment_text: "讨论 implementation overhead、integration、privacy 和 security considerations。"
      commitment_type: add_clarification
      required_evidence_type: discussion_paragraph

- concern_id: P3-editorial
  reviewers: [NSDI-B, NSDI-C, NSDI-E, SIGCOMM-A]
  commitment_extracted:
    - commitment_text: "修复 typos、grammar、algorithm typo、小字体、dataset naming 和 conclusion length。"
      commitment_type: other
      required_evidence_type: prose_edit
```



## 立即待办清单

- [ ] 审计代码后，决定 LEC construction 的真实技术故事。
- [ ] 创建 GRoot-vs-Aether table，并更新 Figure 1 explanation。
- [ ] 起草 scoped formal definitions 和 proof sketches。
- [ ] 从 paper/code/artifact 准备 VeriDNS comparison。
- [ ] 构造两个 VeriDNS semantic examples：wildcard after CNAME rewrite，以及 DNAME hidden query space。
- [ ] 增加 geomean/mean/tail metrics 和 ablations 的 evaluation scripts。
- [ ] 分类 180K invalid zones。
- [ ] 验证 campus bug impact 和 prior-tool coverage。
- [ ] 增加 DNSSEC/caching scope 和 extension discussion。
- [ ] 修复 figure readability 和所有 reviewers 指出的 typos。
