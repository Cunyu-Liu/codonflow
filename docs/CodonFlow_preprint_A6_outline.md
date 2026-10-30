# CodonFlow A6 preprint skeleton v2 (2026-10-31)

Status: evidence-gated skeleton. Not a submission draft. Every section states what it is allowed to
claim today; anything not yet gated stays unwritten.

Working title: **Finite-step synonymous Markov editing for auditable multi-objective mRNA coding-sequence design**

Central question: can a probability-defined synonymous editor learn useful multi-objective preferences
while preserving exact protein identity, and can its advantage (or its absence) be measured under a
frozen, reproducible budget?

---

## 1. Three falsifiable hypotheses

| ID | Hypothesis | Falsified if |
|---|---|---|
| H1 | A finite-step single-codon synonymous kernel with an exact terminal tilt approximates `q_G ∝ q_base · G`; short rollouts and candidate pruning are approximations, not equalities | Exact enumerable-state check fails, or the real short-rollout arm is worse than the immediate arm at equal budget |
| H2 | On a protein-deduplicated, cluster-disjoint test split, training (and path-RLOO) improves joint HV over the frozen base without losing identity, legality or diversity | Converged arm shows no HV gain, or identity/legal/NED regresses |
| H3 | Against DP / AR / greedy / uniform, the method wins only where the objective is multi-objective and the budget is explicit; single-objective and very long sequences may be lost | Joint HV shows no win in any pre-registered cell, or wins only by violating equal budget |

Not hypotheses: "first", "SOTA", "capacity bottleneck", "RL saturates with pretraining". None of these
may appear in the text unless a new controlled comparison supports it.

---

## 2. The five-link chain (each link is forced by the previous one)

**① Measurement — 没有可复现的测量，"更好"不可比。**
Claim: before comparing methods, the corpus, the split level, the metric definitions and the
normalization domain must be fixed and re-computable from frozen artifacts.
Required phenomenon: independent re-computation reproduces the same number; exact cross-split
overlap is zero; every method's objectives live in one reference domain.
Status: **closed.** v4 exact-protein split (776,474; 621,306 / 76,444 / 78,724), v5 homology-cluster
split (776,441; 618,073 / 80,191 / 78,177) with five independent audit checks true; six metric
definitions and four pass lines frozen; joint-HV protocol unified to `(points − ref)/scale` with
`ref = min − 5%·(max−min)`, `scale = q95 − min` (`scripts/a6_joint_hv.py`, 5 contract tests).
Evidence: `audits_20261026/*.json`, `docs/handover/RUNBOOK_NEXT.md` §G3.

**② Mechanism — 约束若靠后处理，多样性与预算必然付代价；所以要写进核。**
Claim: feasibility is carried by the operator (valid source + single-codon synonymous jumps + explicit
stay) and the preference by a terminal tilt; the resulting cost is countable.
Required phenomenon: exact terminal law on enumerable states; closed-form forward count on the real
trajectory (T=4, C=4 → 17 first step, 38 per path); legality never needs a post-filter.
Status: **closed for the mechanism, explicitly approximate for large state spaces.**
Evidence: `tests/test_synonymous_markov.py`, `fig_a6_mechanism_costs`, `runbook_smoke` cost traces.

**③ Learning — 只有"学到偏好"才配叫生成模型，否则只是采样器。**
Claim: the trained arm beats the frozen base at equal budget on independent test sequences.
Required phenomenon: a **converged** checkpoint (three consecutive epochs with <0.1% relative val
drop), then a paired three-arm comparison (base / immediate / short-rollout) with identical initial
states, terminal potential and solution count.
Status: **open.** full-token e8 and edited-token e7 are still descending; no `converged.pt` exists.
Evidence to be produced: `RUNBOOK_NEXT.md` G0 → G2.

**④ Boundary — 单目标必输给 DP；胜场只能锚在多目标覆盖与成本。**
Claim: under one frozen checkpoint, one budget and one joint reference domain, the method's HV is
reported next to LinearDesign, codonGPT, GEMORNA, CAI-greedy and uniform synonymous, with every
missing or architecturally excluded method listed.
Required phenomenon: joint-HV matrix + four cost units + paired statistics, with no random padding
and no silent deletion.
Status: **open.** Baselines are ready (unique18 12/18 done, core five methods audited); the
CodonFlow column cannot be filled before ③.
Evidence to be produced: `RUNBOOK_NEXT.md` G1 → G3.

**⑤ Claim — 用能力边界替代 SOTA 断言；负结果与失败模式同等重要。**
Claim: the paper states where the method wins, where it loses, and why, with failure modes archived.
Required phenomenon: length / objective / split-stratified table plus explicit failure cases
(architectural exclusion, degenerate axis, empty reference domain).
Status: **open, depends on ③④.**

---

## 3. Section skeleton and what may be written today

| Section | Allowed now | Blocked on |
|---|---|---|
| 1 Introduction | Yes (constraint-as-operator framing, no performance claims) | — |
| 2 Method | Yes (kernel, terminal potential, tilt, cost formula, approximation boundary) | — |
| 3 Evaluation protocol | Yes (data versions, splits, baselines, metrics, joint-HV definition, gate list) | — |
| 4.1 Mechanism verification | Yes (enumerable-state check, cost accounting) | — |
| 4.2 Data integrity | Yes (v3 → v4 → v5 audit narrative) | — |
| 4.3 Controlled pretraining + inference arms | **No** | G0 + G2 |
| 4.4 Baselines, joint HV, cost | **No** | G1 + G3 |
| 4.5 Negative results and boundary | Partly (protocol-level negatives are safe) | G3 for the definitive version |
| 5 Discussion | **No** (must follow 4.3–4.5) | G3 |
| 6 Methods | Yes (same content as 2–3, expanded) | — |

---

## 4. Figure list (one claim per figure)

| Fig | Claim | Source | Status |
|---|---|---|---|
| F1 | Exact-protein deduplication closes the silent leakage channel | `fig_a6_data_audit` | done |
| F2 | Splits match in bulk; the 18-record benchmark is length-stratified, not a random sample | `fig_a6_split_distributions` | done |
| F3 | Feasibility is by operator; rollout cost is countable | `fig_a6_mechanism_costs` | done |
| F4 | Baselines span different CAI–MFE trade-offs with identity = 1.0 | `fig_a6_baseline_objectives` | done |
| F5 | Two objectives descend without a plateau yet (no convergence claim) | `checkpoints/*/log.jsonl` | plottable now, must be labelled *in progress* |
| F6 | At equal budget, short-rollout vs immediate vs base differ, with cost attached | G2 output | blocked |
| F7 | Joint HV across six methods in one reference domain | G3 output | blocked |
| F8 | Boundary and failure modes by length, objective and split level | G3 output | blocked |

---

## 5. Red lines (cannot be written even if asked)

1. No SOTA / scaling law / RL-saturation / masking-causality claims without the matching controlled comparison.
2. No legacy numbers: the 22–53% coverage ratio, HV 128.1±16.6, "Cas9 9.5 vs 3,200", "+0.85 HV".
   Slide 36's L1 rows were reproducibly recomputed (31.9±5.9 / 112.9±21.5); L2–L4 and the per-gene
   table have no surviving source JSON and are marked non-citable.
3. No computed proxy (CAI / MFE / GC / motif) presented as expression or stability evidence.
4. No v5 claim promoted to curated family or species OOD.
5. No cross-arm comparison of validation-loss magnitudes (edited-token and full-token losses are
   different objectives).
6. No live `best.pt` used across time; every comparison names a frozen checkpoint and its SHA256.

---

## 6. Mapping to the midterm deck

- Slide 45 (logic chain) = section 2 of this document.
- Slide 19 (what is verified / what is missing) = status of links ③④.
- Slide 43 (real baselines, CodonFlow absent) = the empty slot that link ④ must fill.
- Slide 36/37 = legacy tables; kept only as history, flagged non-citable.
