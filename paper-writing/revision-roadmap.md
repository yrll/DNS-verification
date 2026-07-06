# Aether Revision Roadmap

Inputs:
- `paper-writing/nsdi26-review.txt`
- `paper-writing/sigcomm26-review.txt`
- `paper-writing/dnsverify_sigcomm26.pdf`

Mode: academic-paper / revision-coach

## Executive Diagnosis

The paper improved between the NSDI and SIGCOMM submissions: the SIGCOMM
reviews include two weak accepts and reviewers generally recognize the LEC/QRG
idea as promising. The remaining rejection reasons are now concentrated in a
small set of repeated concerns:

1. The paper still does not make the GRoot delta precise enough.
2. The EC/LEC explanation appears internally inconsistent in Section 3.2 and
   Algorithm 2.
3. "Complete verification" is vulnerable because the current model excludes
   caching/DNSSEC and uses bounds/fuel for termination.
4. The evaluation is convincing on speed but not yet convincing on
   significance, representativeness, baselines, false positives, or bug impact.
5. VeriDNS and Octopus are not positioned strongly enough, especially because
   VeriDNS also claims incremental DNS verification.
6. Several reviewers still see the paper as an optimized GRoot unless the
   manuscript shows a crisp problem formulation, correctness argument, and
   microbenchmarked causal story.

Recommended next-positioning:

> Aether is not "GRoot but faster." Aether is an LEC-native verifier for
> authoritative DNS configuration that avoids global EC refinement by preserving
> local action equivalence in a query resolution graph. This matters under
> update-heavy settings because local changes should not shatter a global label
> graph or trigger whole-namespace recomputation. The paper must prove and
> measure this claim directly.

Estimated revision effort: substantial to fundamental, about 4+ weeks if new
baselines and experiments are added.

## Review Score Trajectory

| Venue | Reviews | Main Positives | Main Blocking Reasons |
|---|---:|---|---|
| NSDI 2026 Fall | 1 weak accept, 3 weak rejects, 2 rejects | Important DNS verification problem; impressive speedups; incremental verification valuable | Novelty unclear; GRoot delta unclear; no proof/correctness; narrow evaluation; operational-track mismatch; writing/figures |
| SIGCOMM 2026 | 2 weak accepts, 3 weak rejects | Core LEC/QRG idea is reasonable; methodology readable; performance promising | EC/LEC inconsistency; performance significance; model fidelity; filtered dataset; VeriDNS missing; bug impact and prior-technique comparison |

## P1 Must Fix

### P1-1: Rewrite the core contribution around the exact GRoot delta

Reviewer sources: NSDI-B, NSDI-C, NSDI-D, NSDI-E, NSDI-F, SIGCOMM-A,
SIGCOMM-D, SIGCOMM-A1.

Problem:
Reviewers repeatedly ask what is fundamentally different from GRoot. SIGCOMM-A
understood the likely real benefit as avoiding unreachable global ECs created
by GRoot's global label graph, but this explanation is not explicit in the
paper. Several reviewers also note that GRoot already uses ECs, symbolic
execution, and data-plane analogies.

Action:
- Add an early "Why GRoot's global ECs are the bottleneck" subsection in the
  Introduction or Overview.
- Use Figure 1 to show, step by step, where GRoot creates unreachable or
  behavior-irrelevant global ECs, and where Aether avoids them.
- Add a table comparing GRoot vs Aether by unit of partitioning, refinement
  scope, graph state, rewrite handling, update invalidation unit, and
  verification cost driver.
- Replace broad claims such as "GRoot is unsound" with precise claims:
  "GRoot's implementation misses X" or "GRoot's global EC abstraction creates
  Y redundant states under condition Z."
- State whether Aether is implemented from scratch or builds on GRoot.

Target manuscript locations:
Abstract, Section 1, Section 2.2, the Figure 1 caption, and Related Work.

Evidence needed:
New subsection, revised Figure 1 explanation, and a comparison table.

Acceptance criterion:
A reviewer unfamiliar with GRoot can explain in one sentence why local
action-equivalence plus QRG changes the asymptotic or practical recomputation
behavior.

### P1-2: Resolve the Section 3.2 / Algorithm 2 LEC inconsistency

Reviewer sources: SIGCOMM-A, SIGCOMM-A1; also connects to NSDI-B/E/F novelty
concerns.

Problem:
SIGCOMM-A flags a serious technical ambiguity: early text says Aether merges
records with identical actions, but Section 3.2 and Algorithm 2 appear to
aggregate by the same `rname` and `rtype`, which looks per-record rather than
action-equivalent. Section 4.2 then says LECs can back-trace to a specific
record, reinforcing the per-record interpretation.

Action:
- Audit the implementation and pseudocode before editing prose.
- If Aether truly merges action-identical records, make Algorithm 2 explicitly
  group by action semantics, not only by `rname`/`rtype`.
- If Aether does not merge such records, remove the claim that LECs merge
  action-identical records and reframe the benefit as local-scope partitioning
  and avoidance of global cross-products/unreachable ECs.
- Define the exact relation among record, rule, space, LEC, edge, and
  backpointer. A backpointer to records can coexist with merged LECs, but the
  paper must explain it as provenance metadata rather than evidence of
  per-record classes.
- Add a small worked example where two records share an action and show whether
  they produce one LEC or two LECs.

Target manuscript locations:
Section 2.2.1, Section 3.2, Algorithm 2, Section 4.2.

Evidence needed:
Corrected pseudocode and a worked example.

Acceptance criterion:
The paper no longer gives two incompatible stories about what an LEC is.

### P1-3: Add a formal problem statement and scoped correctness argument

Reviewer sources: NSDI-B, NSDI-C, NSDI-E, SIGCOMM-C.

Problem:
Reviewers ask what "correct" and "complete" mean. Current claims are vulnerable
because the model abstracts resolvers, DNSSEC, caching, and TTL, and symbolic
execution uses a path bound/fuel parameter and label padding.

Action:
- Add a "Problem and Scope" subsection before the design.
- Define the input model: authoritative zonefiles, supported RR types,
  supported rewrite/delegation semantics, excluded resolver-side semantics.
- State the checked properties in terms of traces.
- Add theorem-style claims:
  - LEC partition soundness: every modeled query belongs to exactly one local
    action-equivalent class at each nameserver.
  - Trace preservation: symbolic execution over the QRG produces the same
    modeled traces as concrete authoritative resolution, within the declared
    bounds.
  - Incremental soundness: after an update, re-execution from the affected QRG
    region preserves results for unchanged regions and recomputes all affected
    traces.
- Explain `k`, `n`, and `delta` as explicit bounded-verification parameters.
  If completeness only holds within these bounds, say so. Avoid unqualified
  "complete verification."
- Add sensitivity analysis for `k` and `delta`.

Target manuscript locations:
Section 2.1, Section 2.2.2, Section 3, Section 4.1, Section 5, Conclusion.

Evidence needed:
Definitions, theorem statements/proof sketches, and a bounds sensitivity table.

Acceptance criterion:
The manuscript no longer invites the critique that it calls bounded model
checking "complete formal verification."

### P1-4: Provide a serious VeriDNS and Octopus comparison

Reviewer sources: SIGCOMM-D, SIGCOMM-E, SIGCOMM-A1, NSDI-C.

Problem:
VeriDNS also supports incremental DNS verification. Current text says VeriDNS
is "approximate" but does not substantiate the claim. Reviewers see this as a
baseline and positioning gap. The updated notes in `diff-with-VeriDNS.txt`
make this gap more concrete: VeriDNS's RSG appears to traverse concrete domain
names that already appear in the configuration, whereas Aether/GRoot reason
over symbolic query spaces. This creates two likely semantic gaps that the next
paper version should demonstrate carefully rather than merely assert.

Action:
- Expand Related Work into a concrete prior-work positioning section.
- Add a comparison table: GRoot, Liu et al. SIGCOMM 2023, Octopus, VeriDNS,
  and Aether.
- Compare along these axes: query-space coverage, symbolic query support,
  per-query vs symbolic traversal, local aggregation, cross-zone behavior,
  incremental update granularity, completeness/approximation, supported bug
  classes, deployment model.
- Use the existing note in `diff-with-VeriDNS.txt` as a starting hypothesis:
  VeriDNS appears to lack symbolic query-space exploration, models each record
  as an RSG edge rather than aggregating action-equivalent records, and may not
  cross zone boundaries in the same way. Verify these claims against the
  VeriDNS paper before finalizing.
- Add two targeted semantic counterexamples/microbenchmarks:
  - Wildcard after rewrite: a query is rewritten by CNAME to `a.b.c`, while the
    target zone contains only `*.b.c`. A concrete-string RSG traversal that
    searches only for `a.b.c` would terminate, while Aether/GRoot semantics
    should match the wildcard and continue.
  - DNAME hidden query space: a zone contains `b.c DNAME bb.c`; the behavior of
    `x.b.c` matters even though `x.b.c` does not explicitly occur in the
    configuration. VeriDNS may only check `b.c`, whereas Aether/GRoot-style
    symbolic queries such as `alpha.b.c` cover the affected subspace.
- Turn these examples into a "semantic coverage" table with columns:
  concrete query required, wildcard support, DNAME subspace support,
  cross-zone continuation, symbolic all-domain query, and expected outcome.
- If possible, run VeriDNS on these examples. If not feasible, explain the
  artifact availability or compatibility barrier and present the examples as a
  semantics-level comparison, clearly marking claims that are inferred from the
  VeriDNS design.
- Avoid saying VeriDNS is merely "syntax-level" unless the VeriDNS paper
  supports that wording. A safer claim is: VeriDNS's RSG-based concrete
  traversal can miss behaviors induced by wildcard/DNAME semantics unless those
  behaviors are explicitly represented in the traversed concrete names.

Target manuscript locations:
Section 1, Section 6, Section 7.

Evidence needed:
New comparison table, two semantic counterexamples, and ideally an experiment
or artifact-backed reproduction.

Acceptance criterion:
The paper can answer: "Why not just use VeriDNS?" without relying on a single
unsupported sentence.

### P1-5: Rebuild the evaluation around causal evidence, not maximum speedups

Reviewer sources: NSDI-A, NSDI-E, NSDI-F, SIGCOMM-A, SIGCOMM-C, SIGCOMM-D,
SIGCOMM-E, SIGCOMM-A1.

Problem:
Reviewers accept that Aether is faster, but question why, when it matters, and
whether the speedups are outliers or implementation artifacts. SIGCOMM-A also
argues that 65 ms to 12 ms may not matter. SIGCOMM-D asks for mean/geomean and
for speedup variation by zone characteristics.

Action:
- Report mean, median, geomean, p90/p95/p99, min/max, and confidence intervals
  for full and incremental verification.
- Add an ablation table:
  - no local aggregation / raw rules
  - no BDD encoding
  - no prefix filter
  - no visited-state cache
  - no parallel LEC construction
  - full recomputation vs incremental recomputation
- Separate algorithmic improvements from parallelization and engineering
  optimizations.
- Add correlation/stratification by zone characteristics: number of records,
  number of shared actions, rewrite density, delegation fanout, nested zones,
  wildcard/DNAME/CNAME usage, number of nameservers.
- Add a stress experiment motivated by `nsdi27.txt`: update storms or CI/CD
  deployment pipelines where many small changes arrive continuously and
  verification latency affects usability.
- Reframe performance claims around incremental-update throughput and
  tail-latency under update storms, not only one-zone millisecond savings.

Target manuscript locations:
Section 6.2, Figures 4-5, Abstract, Conclusion.

Evidence needed:
New figures/tables and revised evaluation narrative.

Acceptance criterion:
The performance section demonstrates why Aether wins and why the win matters.

### P1-6: Fix dataset filtering, representativeness, and bug-impact concerns

Reviewer sources: SIGCOMM-B, SIGCOMM-C, SIGCOMM-E, SIGCOMM-A1, NSDI-F.

Problem:
SIGCOMM-C criticizes filtering 180,000 zones that fail `named-checkzone`.
SIGCOMM-B/E question whether found bugs are substantive, active, or detectable
by prior tools. NSDI-F says evaluation is too narrow.

Action:
- Add a dataset-validity subsection.
- Categorize the 180K filtered zones by error type and count.
- Report whether Aether rejects, classifies, or could gracefully handle each
  invalid category. Do not simply drop them without analysis.
- If invalid zones are outside the model, say so and make them a separate
  robustness/diagnostic workload.
- For campus/university errors, report:
  - whether domains/subdomains are active,
  - whether errors are injected or real,
  - whether operators confirmed them,
  - severity/impact,
  - which prior tools would detect each error,
  - false positives after manual/operator validation.
- Add a larger or public error-detection dataset if possible. If privacy
  prevents release, provide a sanitized artifact or reproducible synthetic
  workload.

Target manuscript locations:
Section 6.1, Section 6.2, Ethics, Artifact appendix if available.

Evidence needed:
Dataset filtering table, bug validation table, false-positive discussion.

Acceptance criterion:
Reviewers no longer see the evaluation as cherry-picked or limited to private
anecdotal bugs.

### P1-7: Clarify model boundaries for DNSSEC, caching, TTL, and resolver state

Reviewer sources: NSDI-E, SIGCOMM-B, SIGCOMM-C, SIGCOMM-A1.

Problem:
The paper currently excludes DNS caching and DNSSEC. Reviewers accept scoping
in principle, but the current text still uses strong correctness language and
does not explain extension paths convincingly.

Action:
- Add a "Scope and Extensions" subsection, not only a short paragraph.
- Explain that Aether verifies authoritative DNS configuration semantics, not
  full recursive-resolution behavior.
- Discuss TTL/caching and DNSSEC separately:
  - What state or cryptographic validation would need to be modeled.
  - What can be represented as QRG nodes/edges or match conditions.
  - What would require a different abstraction.
- Avoid overclaiming that caches are "simply dynamic records" unless you can
  support TTL expiration, resolver cache policy, negative caching, and
  multi-resolver divergence.
- Add one small extension sketch or prototype experiment if feasible.

Target manuscript locations:
Section 2.1, Section 7 or a new Discussion section, Conclusion.

Evidence needed:
Scope table and extension discussion.

Acceptance criterion:
The limitation is framed as a deliberate boundary, not as an unexamined hole in
the correctness claim.

## P2 Should Fix

### P2-1: Add a stronger related work section

Reviewer sources: NSDI-C, NSDI-F, SIGCOMM-D, SIGCOMM-E.

Action:
- Keep the dedicated Related Work section but make it analytical rather than
  list-like.
- Add subparagraphs for DNS configuration verification, DNS semantics/formal
  models, distributed DNS verification, and DPV/incremental verification.
- Explicitly connect each prior line to Aether's design choice.

### P2-2: Explain logs, traces, and why traces matter

Reviewer sources: NSDI-C.

Action:
- Define log fields in a compact table.
- Explain why final answer alone is insufficient: loops, blackholing,
  delegation inconsistency, rewrite chains, hop count warnings, and path-level
  properties require trace evidence.

### P2-3: Detail visited-state cache and incremental execution

Reviewer sources: NSDI-C, SIGCOMM-D.

Action:
- Move the visited-state cache from Introduction-only text into Section 4.
- In Section 5, show exactly which QRG nodes/edges/LECs are invalidated after
  an update.
- Fix any sentence implying "regenerate all traces from scratch" if the method
  is incremental.

### P2-4: Add implementation overhead and operational integration discussion

Reviewer sources: NSDI-A.

Action:
- Report memory usage, BDD size, construction overhead, update bookkeeping
  state, and integration cost.
- If not targeting an operational track, keep this as a short "Deployment
  considerations" subsection.

### P2-5: Add error diagnosis/repair as bounded future work

Reviewer sources: NSDI-A.

Action:
- Do not overexpand the paper into repair. Add an output format that maps each
  detected error to trace/log evidence and likely root-cause records.
- Leave automated repair to future work unless a lightweight suggestion system
  already exists.

### P2-6: Tighten security/privacy and responsible disclosure

Reviewer sources: NSDI-A, SIGCOMM-B/C.

Action:
- Add a short paragraph on sensitive zone data handling, anonymization,
  responsible disclosure, and why private campus data cannot be released.
- Link this to the Ethics paragraph.

## P3 Editorial and Presentation Fixes

Reviewer sources: NSDI-B, NSDI-C, NSDI-E, SIGCOMM-A.

Actions:
- Enlarge Figure 3 text; verify all figures are readable in grayscale and
  printed PDF.
- Fix typos reported by reviewers: "aciton", "Thees", "zonfile",
  "prevoius", "acheives", "support" vs "supports", "a a mechanism", and
  grammar around "GRoot10^4s".
- Fix algorithm typo from NSDI-C: Algorithm 2 line 6 should likely call
  `GetSpace(...)` rather than assign tuple fields directly.
- Clean sentence fragments such as "And the".
- Clarify dataset naming: university vs laboratory vs campus dataset.
- Expand the conclusion from one short paragraph to a concise summary of
  problem, design, guarantees, and empirical takeaways.
- Remove loaded or vague language such as "unsound" unless immediately followed
  by a precise claim and evidence.

## Recommended Revision Order

1. Audit the actual LEC algorithm and implementation. The roadmap depends on
   whether Aether truly merges action-identical records or mainly avoids GRoot
   global cross-products.
2. Rewrite the paper story: problem formulation, GRoot delta, QRG/LEC
   definitions, and claim boundaries.
3. Add formal definitions and proof sketches for partitioning, symbolic
   execution, and incremental recomputation.
4. Design and run the additional evaluation: ablations, geomean/means,
   update-storm workload, invalid-zone analysis, bug-impact validation, and
   VeriDNS comparison if feasible.
5. Revise Related Work and Discussion around GRoot, Liu et al., Octopus,
   VeriDNS, DNSSEC/caching, and DPV.
6. Polish figures, grammar, and conclusion only after the technical story has
   stabilized.

## Suggested New Paper Structure

1. Introduction
   - DNS configuration verification needs timely and repeated checks.
   - Global EC refinement is the bottleneck under large and update-heavy DNS
     configurations.
   - Aether's thesis: local action-equivalence plus QRG preserves enough
     semantics while avoiding global partition explosion.
   - Contributions: QRG/LEC abstraction, symbolic execution with scoped
     guarantees, incremental recomputation, empirical evaluation.
2. Background and Problem Scope
   - Authoritative DNS model.
   - Supported records and properties.
   - Excluded resolver-side state, DNSSEC, caching, TTL.
   - Definitions of query, log, trace, LEC, QRG.
3. Why Global ECs Fail to Scale
   - Running example comparing GRoot and Aether.
   - Unreachable/redundant EC construction.
   - Cost model and update invalidation model.
4. LEC-native Query Resolution Graph
   - Encoding.
   - Match-action table computation.
   - QRG construction.
5. Symbolic Trace Generation and Property Checking
   - Algorithm.
   - Bounds and visited-state cache.
   - Correctness argument.
6. Incremental Verification
   - Update invalidation.
   - Incremental re-execution.
   - Correctness argument.
7. Evaluation
   - RQ1 capability and bug validation.
   - RQ2 performance distributions.
   - RQ3 ablations and causal analysis.
   - RQ4 update storm / real-time verification.
   - RQ5 comparison with GRoot and VeriDNS/Octopus where feasible.
8. Discussion and Limitations
   - DNSSEC/caching extension.
   - Invalid zones.
   - Operational integration and privacy.
9. Related Work
10. Conclusion

## Cross-Reviewer Pattern Matrix

| Pattern | Raised By | Priority | Main Fix |
|---|---|---:|---|
| GRoot delta unclear | NSDI-B/C/D/E/F, SIGCOMM-A/D/A1 | P1 | New GRoot-vs-Aether example, table, and precise claims |
| Novelty feels incremental | NSDI-B/E/F, SIGCOMM-D/E | P1 | Reframe around LEC-native QRG and update-locality, not generic symbolic execution |
| Correctness/proof missing | NSDI-B/C/E, SIGCOMM-C | P1 | Scoped semantics and proof sketches |
| VeriDNS missing | SIGCOMM-D/E/A1 | P1 | Semantic coverage examples for wildcard/DNAME plus empirical comparison if feasible |
| Evaluation narrow/representativeness | NSDI-A/F, SIGCOMM-B/C/E/A1 | P1 | Invalid-zone analysis, bug validation, public/synthetic workload |
| Performance significance | SIGCOMM-A/D/A1 | P1 | Mean/geomean, update-storm scenario, ablations |
| DNSSEC/caching limitation | NSDI-E, SIGCOMM-B/C/A1 | P1 | Scope and extension discussion |
| Writing/clarity/figures | NSDI-B/C/E, SIGCOMM-A | P3 | Definitions, readable figures, grammar pass |
| Operational-track mismatch | NSDI-D/F | P2/P3 | Submit as research paper unless deployment evidence is added |

## Response Strategy for Future Rebuttal

Do not spend rebuttal space defending broad claims. Use it to point to precise
evidence.

For GRoot:
- "We added Section X and Table Y, which show the exact partitioning and update
  invalidation differences."
- "The main reduction comes from local action-equivalence and avoiding global
  refinement that creates unreachable/redundant ECs, not merely from
  parallelization."

For VeriDNS:
- "We added Table Y and microbenchmarks Z1/Z2. They show that a concrete-name
  RSG traversal can miss wildcard-after-rewrite and DNAME-induced query
  subspaces, while Aether symbolically explores these spaces through LEC/QRG
  semantics. We verified this against VeriDNS's design/artifact where possible;
  otherwise we mark it as a semantic comparison."

For completeness:
- "We now use the term scoped completeness: complete for the stated
  authoritative-DNS model and explicit bounds. We moved DNSSEC/caching to
  Discussion and no longer claim full recursive-DNS verification."

For performance significance:
- "We added mean/geomean/tail metrics and an update-storm workload showing that
  the benefit is in throughput and tail latency under frequent updates, not
  simply saving a few milliseconds in one isolated zone."

For invalid zones:
- "We categorized the filtered zones and report how Aether handles or rejects
  them. They are no longer silently removed from the evaluation story."

## Commitment Ledger

Use this as the seed for a revision-tracking table.

```yaml
- concern_id: P1-1-groot-delta
  reviewers: [NSDI-B, NSDI-C, NSDI-D, NSDI-E, NSDI-F, SIGCOMM-A, SIGCOMM-D, SIGCOMM-A1]
  commitment_extracted:
    - commitment_text: "Clarify the main differences with GRoot, especially EC generation and configurations where Aether helps most."
      commitment_type: add_clarification
      required_evidence_type: new_section
    - commitment_text: "Add a GRoot vs Aether comparison through the running example."
      commitment_type: add_analysis
      required_evidence_type: new_figure

- concern_id: P1-2-lec-consistency
  reviewers: [SIGCOMM-A]
  commitment_extracted:
    - commitment_text: "Resolve the inconsistency between action-equivalence claims and Algorithm 2 grouping by rname/rtype."
      commitment_type: restructure
      required_evidence_type: prose_edit
    - commitment_text: "Add a worked example showing whether action-identical records merge into one LEC."
      commitment_type: add_clarification
      required_evidence_type: new_figure

- concern_id: P1-3-correctness-scope
  reviewers: [NSDI-B, NSDI-C, NSDI-E, SIGCOMM-C]
  commitment_extracted:
    - commitment_text: "Define correctness, completeness, supported inputs, and checked properties."
      commitment_type: add_clarification
      required_evidence_type: new_section
    - commitment_text: "Add proof sketches for LEC partitioning, symbolic trace preservation, and incremental soundness."
      commitment_type: add_analysis
      required_evidence_type: new_section
    - commitment_text: "Clarify k, n, and delta as bounded verification parameters."
      commitment_type: add_clarification
      required_evidence_type: methods_paragraph

- concern_id: P1-4-veridns
  reviewers: [SIGCOMM-D, SIGCOMM-E, SIGCOMM-A1]
  commitment_extracted:
    - commitment_text: "Describe the differences with VeriDNS in more detail."
      commitment_type: add_analysis
      required_evidence_type: new_table
    - commitment_text: "Compare Aether and VeriDNS empirically or explain artifact barriers and provide semantic examples."
      commitment_type: add_experiment
      required_evidence_type: new_table
    - commitment_text: "Add a wildcard-after-CNAME-rewrite example showing whether VeriDNS covers implicit wildcard matches."
      commitment_type: add_analysis
      required_evidence_type: new_figure
    - commitment_text: "Add a DNAME hidden-query-space example showing why symbolic all-domain coverage matters."
      commitment_type: add_analysis
      required_evidence_type: new_figure

- concern_id: P1-5-evaluation-causal
  reviewers: [NSDI-A, NSDI-E, NSDI-F, SIGCOMM-A, SIGCOMM-D, SIGCOMM-A1]
  commitment_extracted:
    - commitment_text: "Report mean/geomean and explain whether speedups are outliers."
      commitment_type: add_analysis
      required_evidence_type: new_table
    - commitment_text: "Add ablations separating algorithmic gains from implementation optimizations and parallelism."
      commitment_type: add_experiment
      required_evidence_type: new_table
    - commitment_text: "Describe scenarios where reducing verification time affects usability."
      commitment_type: add_clarification
      required_evidence_type: discussion_paragraph

- concern_id: P1-6-dataset-bugs
  reviewers: [SIGCOMM-B, SIGCOMM-C, SIGCOMM-E, SIGCOMM-A1, NSDI-F]
  commitment_extracted:
    - commitment_text: "Justify why the dataset remains representative after removing 180K syntax-problem zones."
      commitment_type: add_analysis
      required_evidence_type: new_table
    - commitment_text: "Clarify whether found bugs are real, active, significant, and detectable by prior tools."
      commitment_type: add_analysis
      required_evidence_type: new_table
    - commitment_text: "Discuss false positives and validation process."
      commitment_type: add_clarification
      required_evidence_type: methods_paragraph

- concern_id: P1-7-dnssec-caching
  reviewers: [NSDI-E, SIGCOMM-B, SIGCOMM-C, SIGCOMM-A1]
  commitment_extracted:
    - commitment_text: "Explain how Aether could be extended to DNSSEC and caching."
      commitment_type: add_clarification
      required_evidence_type: discussion_paragraph
    - commitment_text: "State that current guarantees apply to authoritative DNS configuration semantics, not full recursive DNS behavior."
      commitment_type: add_clarification
      required_evidence_type: prose_edit

- concern_id: P2-related-work
  reviewers: [NSDI-C, NSDI-F, SIGCOMM-D, SIGCOMM-E]
  commitment_extracted:
    - commitment_text: "Add a proper related work section that positions DNS verification and DPV literature."
      commitment_type: add_citation
      required_evidence_type: new_citation

- concern_id: P2-logs-traces
  reviewers: [NSDI-C]
  commitment_extracted:
    - commitment_text: "Clarify what query logs and traces contain and why traces matter."
      commitment_type: add_clarification
      required_evidence_type: methods_paragraph

- concern_id: P2-operational-security
  reviewers: [NSDI-A, NSDI-D, NSDI-F]
  commitment_extracted:
    - commitment_text: "Discuss implementation overhead, integration, privacy, and security considerations."
      commitment_type: add_clarification
      required_evidence_type: discussion_paragraph

- concern_id: P3-editorial
  reviewers: [NSDI-B, NSDI-C, NSDI-E, SIGCOMM-A]
  commitment_extracted:
    - commitment_text: "Fix typos, grammar, algorithm typo, small fonts, dataset naming, and conclusion length."
      commitment_type: other
      required_evidence_type: prose_edit
```

## Pushback / Disagreement Guidance

Reasonable to push back:
- "Aether must support full DNSSEC/caching now." Response: acknowledge
  importance, clarify paper scope, and provide extension path. Do not claim the
  current artifact fully solves it.
- "Operational track mismatch" if the next target is not an operational track.
  Response: revise framing and target a research/system-design track.
- "Repair is required." Response: add diagnosis/root-cause evidence and leave
  automated repair as future work.

Do not push back without new evidence:
- VeriDNS comparison.
- Dataset filtering.
- GRoot delta.
- Complete verification terminology.
- Performance significance.

## Immediate To-Do Checklist

- [ ] Decide the true technical story of LEC construction after auditing code.
- [ ] Create a GRoot-vs-Aether table and update Figure 1 explanation.
- [ ] Draft scoped formal definitions and proof sketches.
- [ ] Prepare VeriDNS comparison from paper/code/artifact.
- [ ] Build two VeriDNS semantic examples: wildcard after CNAME rewrite, and DNAME hidden query space.
- [ ] Add evaluation scripts for geomean/mean/tail metrics and ablations.
- [ ] Categorize the 180K invalid zones.
- [ ] Validate campus bug impact and prior-tool coverage.
- [ ] Add DNSSEC/caching scope and extension discussion.
- [ ] Fix figure readability and all reported typos.
