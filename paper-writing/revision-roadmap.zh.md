# Aether 修订路线图

输入文件：
- `paper-writing/nsdi26-review.txt`
- `paper-writing/sigcomm26-review.txt`
- `paper-writing/dnsverify_sigcomm26.pdf`

模式：academic-paper / revision-coach

## 总体诊断

这篇文章从 NSDI 投稿到 SIGCOMM 投稿已经有明显进步：SIGCOMM 的 review 中有两个 weak accept，reviewer 普遍认可 LEC/QRG 这个思路有潜力。现在剩下的拒稿原因集中在少数几个反复出现的问题上：

1. 文章仍然没有把和 GRoot 的核心差异讲得足够精确。
2. Section 3.2 和 Algorithm 2 中关于 EC/LEC 的解释存在内部不一致。
3. 文章使用 "complete verification" 这一表述时比较脆弱，因为当前模型排除了 caching/DNSSEC，并且使用 bound/fuel 来保证终止。
4. 评估在速度提升上有说服力，但在实际意义、代表性、baseline、false positive 和 bug impact 上还不够有说服力。
5. VeriDNS 和 Octopus 的定位不够清楚，尤其是 VeriDNS 也声称支持 incremental DNS verification。
6. 除非稿件能给出清晰的问题定义、正确性论证和 microbenchmark 级别的因果解释，否则不少 reviewer 仍会把这篇文章看成一个优化版 GRoot。

建议的下一版定位：

> Aether 不是 "GRoot but faster"。Aether 是一个面向 authoritative DNS configuration 的 LEC-native verifier，它通过在 query resolution graph 中保留 local action equivalence，避免 global EC refinement。这个差异在 update-heavy 场景下尤其重要，因为局部变更不应该打碎全局 label graph，也不应该触发 whole-namespace recomputation。论文必须直接证明并测量这一点。

预计修订工作量：substantial 到 fundamental。如果需要补新 baseline 和实验，预计 4 周以上。

## Review 分数走势

| Venue | Reviews | 主要优点 | 主要阻塞原因 |
|---|---:|---|---|
| NSDI 2026 Fall | 1 weak accept, 3 weak rejects, 2 rejects | DNS verification 问题重要；速度提升明显；incremental verification 有价值 | Novelty 不清楚；GRoot delta 不清楚；缺少 proof/correctness；evaluation 窄；operational-track mismatch；写作和图 |
| SIGCOMM 2026 | 2 weak accepts, 3 weak rejects | LEC/QRG 核心想法合理；methodology 易读；performance promising | EC/LEC 不一致；performance significance 不足；model fidelity 问题；filtered dataset；VeriDNS 缺失；bug impact 和 prior-technique comparison 不足 |

## P1 必须修

### P1-1：围绕精确的 GRoot delta 重写核心贡献

Reviewer 来源：NSDI-B, NSDI-C, NSDI-D, NSDI-E, NSDI-F, SIGCOMM-A, SIGCOMM-D, SIGCOMM-A1。

问题：
Reviewers 反复追问 Aether 和 GRoot 到底有什么本质区别。SIGCOMM-A 其实已经理解到一个可能的核心收益：Aether 避免了 GRoot global label graph 产生的 unreachable global ECs。但这个解释在论文中没有显式展开。多个 reviewer 还指出，GRoot 本身也使用 EC、symbolic execution 和 data-plane analogy。

行动：
- 在 Introduction 或 Overview 前部加入一个小节："Why GRoot's global ECs are the bottleneck"。
- 用 Figure 1 分步骤说明 GRoot 在哪里产生 unreachable 或 behavior-irrelevant global ECs，以及 Aether 如何避免这些 EC。
- 增加一张 GRoot vs Aether 对比表，比较 partitioning unit、refinement scope、graph state、rewrite handling、update invalidation unit 和 verification cost driver。
- 把 "GRoot is unsound" 这种宽泛说法替换为精确说法，例如："GRoot's implementation misses X" 或 "GRoot's global EC abstraction creates Y redundant states under condition Z"。
- 明确说明 Aether 是从零实现，还是建立在 GRoot 实现之上。

目标稿件位置：
Abstract, Section 1, Section 2.2, Figure 1 caption, Related Work。

需要的证据：
新增小节、修改后的 Figure 1 解释、一张对比表。

验收标准：
一个不熟悉 GRoot 的 reviewer 能用一句话解释：local action-equivalence 加 QRG 为什么改变了 asymptotic 或 practical recomputation behavior。

### P1-2：解决 Section 3.2 / Algorithm 2 中的 LEC 不一致

Reviewer 来源：SIGCOMM-A, SIGCOMM-A1；同时关联 NSDI-B/E/F 的 novelty concern。

问题：
SIGCOMM-A 指出了一个严重技术歧义：前文说 Aether 会合并 identical action 的 records，但 Section 3.2 和 Algorithm 2 看起来是按相同的 `rname` 和 `rtype` 聚合，这更像 per-record，而不是 action-equivalent。Section 4.2 又说 LECs 可以 back-trace 到 specific record，进一步加强了 per-record 的理解。

行动：
- 在改 prose 之前，先 audit implementation 和 pseudocode。
- 如果 Aether 确实会合并 action-identical records，就让 Algorithm 2 明确按 action semantics 分组，而不仅是按 `rname`/`rtype`。
- 如果 Aether 实际上不会合并这类 records，就删除 "LECs merge action-identical records" 这个 claim，把收益重新表述为 local-scope partitioning 和避免 global cross-products / unreachable ECs。
- 精确定义 record、rule、space、LEC、edge、backpointer 之间的关系。merged LEC 可以保留 record backpointer，但论文必须解释它是 provenance metadata，而不是 per-record class 的证据。
- 加一个小型 worked example：两个 records 共享同一个 action 时，展示它们会产生一个 LEC 还是两个 LEC。

目标稿件位置：
Section 2.2.1, Section 3.2, Algorithm 2, Section 4.2。

需要的证据：
修正后的 pseudocode 和 worked example。

验收标准：
论文不再给出两个互相冲突的 LEC 定义故事。

### P1-3：加入 formal problem statement 和 scoped correctness argument

Reviewer 来源：NSDI-B, NSDI-C, NSDI-E, SIGCOMM-C。

问题：
Reviewers 追问 "correct" 和 "complete" 到底是什么意思。当前 claim 比较脆弱，因为模型抽象掉了 resolvers、DNSSEC、caching 和 TTL，symbolic execution 又使用 path bound/fuel parameter 和 label padding。

行动：
- 在 design 前加入 "Problem and Scope" 小节。
- 定义 input model：authoritative zonefiles、支持的 RR types、支持的 rewrite/delegation semantics、排除的 resolver-side semantics。
- 用 trace 来定义 checked properties。
- 加入 theorem-style claims：
  - LEC partition soundness：每个 modeled query 在每个 nameserver 上恰好属于一个 local action-equivalent class。
  - Trace preservation：在声明的 bounds 内，QRG 上的 symbolic execution 产生的 modeled traces 与 concrete authoritative resolution 一致。
  - Incremental soundness：update 后，从 affected QRG region 重新执行可以保持 unchanged regions 的结果，并重新计算所有 affected traces。
- 把 `k`、`n` 和 `delta` 解释成显式的 bounded-verification parameters。如果 completeness 只在这些 bounds 内成立，就直接说明。避免无条件使用 "complete verification"。
- 增加 `k` 和 `delta` 的 sensitivity analysis。

目标稿件位置：
Section 2.1, Section 2.2.2, Section 3, Section 4.1, Section 5, Conclusion。

需要的证据：
Definitions、theorem statements/proof sketches、bounds sensitivity table。

验收标准：
稿件不再让 reviewer 觉得它把 bounded model checking 称为 "complete formal verification"。

### P1-4：认真补足 VeriDNS 和 Octopus 对比

Reviewer 来源：SIGCOMM-D, SIGCOMM-E, SIGCOMM-A1, NSDI-C。

问题：
VeriDNS 也支持 incremental DNS verification。当前文本说 VeriDNS 是 "approximate"，但没有支撑这个说法。Reviewers 因此认为这是 baseline 和 positioning gap。你在 `diff-with-VeriDNS.txt` 里补充的笔记把这个 gap 说得更具体：VeriDNS 的 RSG 看起来是在遍历配置中已经出现过的 concrete domain names，而 Aether/GRoot 是对 symbolic query spaces 做推理。这会导致两个很适合写进论文的 semantic gaps：缺少 symbolic query-space coverage，以及 RSG 的精确字符串匹配难以覆盖 wildcard/DNAME 诱导出的隐式查询空间。

行动：
- 把 Related Work 扩展成具体的 prior-work positioning section。
- 增加对比表：GRoot、Liu et al. SIGCOMM 2023、Octopus、VeriDNS 和 Aether。
- 按以下维度比较：query-space coverage、symbolic query support、per-query vs symbolic traversal、local aggregation、cross-zone behavior、incremental update granularity、completeness/approximation、supported bug classes、deployment model。
- 把 `diff-with-VeriDNS.txt` 中已有笔记作为初始假设：VeriDNS 似乎缺少 symbolic query-space exploration，将每条 record 建模为 RSG 中的一条 edge，而不是像 LEC 那样聚合 action-equivalent records，并且可能不能以同样方式跨 zone。最终写进论文前必须对照 VeriDNS 论文确认。
- 增加两个有针对性的 semantic counterexamples/microbenchmarks：
  - Wildcard after rewrite：某个 query 被 CNAME 重写成 `a.b.c`，但目标 zone 里只有 `*.b.c`。如果 RSG 只按 concrete string 查找 `a.b.c`，遍历会终止；而按 Aether/GRoot semantics 应该匹配 wildcard 并继续解析。
  - DNAME hidden query space：zone 中存在 `b.c DNAME bb.c`，那么 `x.b.c` 的行为也很重要，即使 `x.b.c` 并没有显式出现在配置中。VeriDNS 可能只检查 `b.c`，而 Aether/GRoot 风格的 symbolic query，比如 `alpha.b.c`，会覆盖这个受影响的 subspace。
- 把这些例子做成一张 "semantic coverage" 表，列包括：concrete query required、wildcard support、DNAME subspace support、cross-zone continuation、symbolic all-domain query、expected outcome。
- 如果可行，在这些例子上运行 VeriDNS。如果不可行，解释 artifact availability 或 compatibility barrier，并把这些例子作为 semantics-level comparison，同时清楚标注哪些 claim 是从 VeriDNS design 推断出来的。
- 避免直接说 VeriDNS 只是 "syntax-level"，除非 VeriDNS 论文能支撑这个措辞。更稳妥的说法是：VeriDNS 的 RSG-based concrete traversal 可能漏掉 wildcard/DNAME semantics 诱导出的 behaviors，除非这些 behaviors 已经显式表示在被遍历的 concrete names 中。

目标稿件位置：
Section 1, Section 6, Section 7。

需要的证据：
新的 comparison table、两个 semantic counterexamples，最好再加一个实验或 artifact-backed reproduction。

验收标准：
论文可以回答 "Why not just use VeriDNS?"，而不是只依赖一句 unsupported sentence。

### P1-5：围绕因果证据重建 evaluation，而不是只报 maximum speedups

Reviewer 来源：NSDI-A, NSDI-E, NSDI-F, SIGCOMM-A, SIGCOMM-C, SIGCOMM-D, SIGCOMM-E, SIGCOMM-A1。

问题：
Reviewers 接受 Aether 更快，但质疑为什么更快、什么时候重要、speedups 是否只是 outliers 或 implementation artifacts。SIGCOMM-A 还认为 65 ms 到 12 ms 未必有实际意义。SIGCOMM-D 要求 mean/geomean 和按 zone characteristics 分析 speedup variation。

行动：
- 对 full verification 和 incremental verification 报告 mean、median、geomean、p90/p95/p99、min/max 和 confidence intervals。
- 增加 ablation table：
  - no local aggregation / raw rules
  - no BDD encoding
  - no prefix filter
  - no visited-state cache
  - no parallel LEC construction
  - full recomputation vs incremental recomputation
- 把算法改进和 parallelization/engineering optimization 分开。
- 按 zone characteristics 做 correlation/stratification：record 数量、shared actions 数量、rewrite density、delegation fanout、nested zones、wildcard/DNAME/CNAME 使用、nameserver 数量。
- 加一个由 `nsdi27.txt` 启发的 stress experiment：update storms 或 CI/CD deployment pipelines，即大量小变更连续到达，verification latency 会影响 usability 的场景。
- 把 performance claim 重心从单个 zone 省几毫秒，改成 incremental-update throughput 和 update storms 下的 tail-latency。

目标稿件位置：
Section 6.2, Figures 4-5, Abstract, Conclusion。

需要的证据：
新的 figures/tables 和修改后的 evaluation narrative。

验收标准：
Performance section 能说明 Aether 为什么赢，以及为什么这个赢法重要。

### P1-6：修复 dataset filtering、representativeness 和 bug-impact 问题

Reviewer 来源：SIGCOMM-B, SIGCOMM-C, SIGCOMM-E, SIGCOMM-A1, NSDI-F。

问题：
SIGCOMM-C 批评论文过滤掉了 180,000 个无法通过 `named-checkzone` 的 zones。SIGCOMM-B/E 质疑发现的 bugs 是否有实质影响、是否 active、是否能被 prior tools 发现。NSDI-F 认为 evaluation 太窄。

行动：
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

目标稿件位置：
Section 6.1, Section 6.2, Ethics, Artifact appendix if available。

需要的证据：
Dataset filtering table、bug validation table、false-positive discussion。

验收标准：
Reviewers 不再认为 evaluation 是 cherry-picked，或只基于 private anecdotal bugs。

### P1-7：澄清 DNSSEC、caching、TTL 和 resolver state 的模型边界

Reviewer 来源：NSDI-E, SIGCOMM-B, SIGCOMM-C, SIGCOMM-A1。

问题：
论文当前排除了 DNS caching 和 DNSSEC。Reviewers 原则上可以接受 scope 限制，但当前文本仍然使用较强 correctness language，并且没有足够有说服力地解释 extension path。

行动：
- 加一个 "Scope and Extensions" 小节，而不是只写一小段。
- 说明 Aether 验证的是 authoritative DNS configuration semantics，不是完整 recursive-resolution behavior。
- 分别讨论 TTL/caching 和 DNSSEC：
  - 需要建模什么 state 或 cryptographic validation；
  - 哪些内容可以表示成 QRG nodes/edges 或 match conditions；
  - 哪些内容需要不同 abstraction。
- 不要过度声称 caches "simply dynamic records"，除非能够支持 TTL expiration、resolver cache policy、negative caching 和 multi-resolver divergence。
- 如果可行，加入一个小型 extension sketch 或 prototype experiment。

目标稿件位置：
Section 2.1, Section 7 或新的 Discussion section, Conclusion。

需要的证据：
Scope table 和 extension discussion。

验收标准：
这个 limitation 被塑造成 deliberate boundary，而不是 correctness claim 中未处理的漏洞。

## P2 应该修

### P2-1：加强 related work section

Reviewer 来源：NSDI-C, NSDI-F, SIGCOMM-D, SIGCOMM-E。

行动：
- 保留 dedicated Related Work section，但让它更像分析，而不是文献列表。
- 增加 DNS configuration verification、DNS semantics/formal models、distributed DNS verification、DPV/incremental verification 等子段。
- 明确连接每条 prior work line 和 Aether 的 design choice。

### P2-2：解释 logs、traces，以及为什么 traces 重要

Reviewer 来源：NSDI-C。

行动：
- 用紧凑表格定义 log fields。
- 解释为什么 final answer alone 不够：loops、blackholing、delegation inconsistency、rewrite chains、hop count warnings 和 path-level properties 都需要 trace evidence。

### P2-3：详细说明 visited-state cache 和 incremental execution

Reviewer 来源：NSDI-C, SIGCOMM-D。

行动：
- 把 visited-state cache 从 Introduction-only text 移到 Section 4 中详细说明。
- 在 Section 5 展示 update 后到底哪些 QRG nodes/edges/LECs 会 invalidated。
- 如果当前有句子暗示 "regenerate all traces from scratch"，而方法其实是 incremental，就必须修正。

### P2-4：加入 implementation overhead 和 operational integration 讨论

Reviewer 来源：NSDI-A。

行动：
- 报告 memory usage、BDD size、construction overhead、update bookkeeping state 和 integration cost。
- 如果下一次不投 operational track，就把它控制成一个短的 "Deployment considerations" 小节。

### P2-5：把 error diagnosis/repair 作为有边界的 future work

Reviewer 来源：NSDI-A。

行动：
- 不要把论文扩展成 repair paper。可以增加一种 output format，将每个 detected error 映射到 trace/log evidence 和 likely root-cause records。
- 除非已经有轻量 suggestion system，否则 automated repair 留到 future work。

### P2-6：收紧 security/privacy 和 responsible disclosure

Reviewer 来源：NSDI-A, SIGCOMM-B/C。

行动：
- 增加一段短讨论：sensitive zone data handling、anonymization、responsible disclosure，以及为什么 private campus data 不能 release。
- 把这段和 Ethics paragraph 连接起来。

## P3 编辑和呈现层面的修复

Reviewer 来源：NSDI-B, NSDI-C, NSDI-E, SIGCOMM-A。

行动：
- 放大 Figure 3 的文字；检查所有图在 grayscale 和打印版 PDF 中都可读。
- 修复 reviewers 指出的 typo："aciton", "Thees", "zonfile", "prevoius", "acheives", "support" vs "supports", "a a mechanism"，以及 "GRoot10^4s" 附近的语法。
- 修复 NSDI-C 指出的 algorithm typo：Algorithm 2 line 6 很可能应该调用 `GetSpace(...)`，而不是直接赋 tuple fields。
- 清理 "And the" 这类 sentence fragments。
- 澄清 dataset 命名：university vs laboratory vs campus dataset。
- 把 conclusion 从一个很短的段落扩展为对 problem、design、guarantees 和 empirical takeaways 的简洁总结。
- 删除 "unsound" 这类带情绪或过宽的说法，除非后面立刻跟上精确 claim 和证据。

## 建议修订顺序

1. 先 audit 真实的 LEC algorithm 和 implementation。整个 roadmap 取决于 Aether 到底是真的合并 action-identical records，还是主要避免了 GRoot global cross-products。
2. 重写 paper story：problem formulation、GRoot delta、QRG/LEC definitions 和 claim boundaries。
3. 加入 partitioning、symbolic execution 和 incremental recomputation 的 formal definitions 与 proof sketches。
4. 设计并运行补充 evaluation：ablations、geomean/means、update-storm workload、invalid-zone analysis、bug-impact validation，以及可行时的 VeriDNS comparison。
5. 围绕 GRoot、Liu et al.、Octopus、VeriDNS、DNSSEC/caching 和 DPV 修改 Related Work 与 Discussion。
6. 等 technical story 稳定后，再统一 polish figures、grammar 和 conclusion。

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

## 未来 rebuttal 的回应策略

不要把 rebuttal 空间花在防守宽泛 claim 上。要用它指向精确证据。

针对 GRoot：
- "We added Section X and Table Y, which show the exact partitioning and update invalidation differences."
- "The main reduction comes from local action-equivalence and avoiding global refinement that creates unreachable/redundant ECs, not merely from parallelization."

针对 VeriDNS：
- "We added Table Y and microbenchmarks Z1/Z2. They show that a concrete-name RSG traversal can miss wildcard-after-rewrite and DNAME-induced query subspaces, while Aether symbolically explores these spaces through LEC/QRG semantics. We verified this against VeriDNS's design/artifact where possible; otherwise we mark it as a semantic comparison."

针对 completeness：
- "We now use the term scoped completeness: complete for the stated authoritative-DNS model and explicit bounds. We moved DNSSEC/caching to Discussion and no longer claim full recursive-DNS verification."

针对 performance significance：
- "We added mean/geomean/tail metrics and an update-storm workload showing that the benefit is in throughput and tail latency under frequent updates, not simply saving a few milliseconds in one isolated zone."

针对 invalid zones：
- "We categorized the filtered zones and report how Aether handles or rejects them. They are no longer silently removed from the evaluation story."

## Commitment Ledger

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

## Pushback / Disagreement 指南

可以合理 push back 的点：
- "Aether must support full DNSSEC/caching now." 回应：承认其重要性，澄清 paper scope，并提供 extension path。不要声称当前 artifact 已经完整解决它。
- "Operational track mismatch"，如果下一次目标不是 operational track。回应：修改 framing，转投 research/system-design track。
- "Repair is required." 回应：增加 diagnosis/root-cause evidence，把 automated repair 留作 future work。

没有新证据时，不建议 push back：
- VeriDNS comparison。
- Dataset filtering。
- GRoot delta。
- Complete verification terminology。
- Performance significance。

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
