# CodonFlow: Feasibility-Gated Codon-Level Discrete Flow for Multi-Objective mRNA Design

**Preprint draft v0.1 — 2026-10-13**
 Liu Cunyu (Zhejiang University)

---

## Abstract

Designing messenger RNA coding sequences requires simultaneously optimizing multiple competing objectives—codon adaptation, structural stability, GC content, and motif avoidance—while maintaining hard constraints: reading-frame integrity, exact protein identity, and a single terminal stop codon. Existing approaches handle these constraints in three ways—autoregressive generation with logit masking, search over a generative model, or post-hoc filtering—each of which measurably degrades either feasibility, diversity, or objective quality. We present CodonFlow, an edit-based discrete flow over a 64-codon vocabulary that moves the feasibility constraint into the terminal distribution by construction: a gated target $G(x) = \exp(\beta \cdot U(x)) \cdot \mathbb{1}[x \in \mathcal{F}]$ shapes both constraint satisfaction and multi-objective preference, while a label-free RLOO fine-tuning stage with two self-supervised rewards (edit likelihood and translation-cycle consistency) refines the base model without any human annotation. Across a four-layer benchmark—classical reporter genes, 18 held-out genes sampled with cluster-disjoint leakage protection from a 25-species corpus, cross-family OOD genes, and a 4.1 kb Cas9 probe—CodonFlow attains 100% protein identity and legality on all 4,500+ generated solutions in every scenario, with zero decay under distribution shift. On the held-out layer, it dominates its unguided base by geometric-mean hypervolume ratios of 1.27 (two-objective) and 1.44 (four-objective), and its coverage grows with sequence length relative to the dynamic-programming baseline. A mid-study audit further surfaced and repaired a degeneracy in the augmented Tchebycheff preference utility (zero-weight axes collapsing the guidance term), yielding +12% four-objective hypervolume under an otherwise identical protocol—a controlled demonstration that the gating and preference channels are independently steerable. We release all code, the 862k-sequence corpus construction pipeline, and per-experiment JSON results.

---

## 1. Introduction

A single protein can be written in on the order of $10^{100}$ synonymous nucleotide encodings. The choice among them is not cosmetic: codon usage bias governs translational efficiency, secondary structure governs stability and nuclease susceptibility, GC content governs manufacturability, and immunogenic motifs govern therapeutic safety. Codon optimization is therefore a *constrained multi-objective design* problem over the space of coding sequences (CDS).

The constraint is absolute—a synonymous redesign must translate to exactly the same protein—yet the dominant paradigms treat it as a soft or external consideration:

1. **Masked autoregressive generation** (e.g., codonGPT-style models) constrains decoding with a logit mask over synonymous codons. Masking keeps each step locally legal, but as we quantify (§5.1, EXP-1), constrained sampling measurably collapses sequence diversity relative to unconstrained sampling, and the autoregressive factorization imposes a hard context limit—on our Cas9 probe, a 1024-position GPT-2 architecture cannot emit any sequence longer than 1,023 amino acids (§5.4).
2. **Search over a generative model** (MCTG-style) samples freely and prunes by feasibility. Feasibility is then a *budget*: at fixed evaluation budget, pruning competes with objective-directed search for the same calls (§5.2, EXP-2).
3. **Post-hoc filtering** ranks an unconstrained solution pool and keeps the legal subset, paying for coverage with wasted budget.

Meanwhile, classical **dynamic programming** (LinearDesign) is near-optimal for small objective counts but degrades in wall-clock on long sequences and does not natively cover four simultaneous objectives with hard identity constraints (§5.4).

CodonFlow takes a different route, transplanted from the discrete-flow protein-design literature (pCoMole) and adapted to the codon setting: **make feasibility part of the target distribution itself.** We define a discrete edit flow over a 64-symbol codon vocabulary whose terminal distribution factorizes as $G(x) \propto \exp(\beta U(x)) \mathbb{1}[x\in\mathcal{F}]$, where $\mathcal{F}$ is the exact feasibility set (frame-aligned, protein-identical, single-stop) and $U$ is an augmented Tchebycheff utility over normalized objectives. A Doob-$h$ transform supplies the corresponding guidance during sampling, and a subsequent label-free RLOO stage—with a *direct* reward (model edit likelihood) and a *reverse* reward (deterministic translation-cycle consistency $\mathrm{Trans}(y)=\mathrm{Trans}(x)$)—improves the base model without wet-lab or human labels.

**Contributions.**

- **A by-construction feasibility gate for codon-level discrete flows.** To our knowledge the first instantiation where synonymous-identity, reading-frame, and single-stop constraints live natively in the terminal distribution of an edit flow over the 64-codon vocabulary, rather than in decoding masks, search layers, or filters.
- **A label-free dual-reward RLOO recipe for the codon setting**, using deterministic translation-cycle consistency as the reverse signal (predictor-free, noise-free, unlike text-domain teacher-forcing reconstruction).
- **A four-layer, leakage-audited evaluation protocol** spanning classical reporters, 18 cluster-disjoint held-out genes (9 species × 3 length bands, drawn from a 25-species / 862k-sequence corpus), cross-family OOD genes, and a 4.1 kb long-sequence probe—with equal-budget, protocol-fair comparisons against LinearDesign, codonGPT, CAI-greedy, and the unguided flow.
- **Mechanism-level evidence of separability**: a mid-study repair of a Tchebycheff degeneracy changed preference behavior (+12% S3 hypervolume) while leaving the 100% identity/legality guarantees untouched—directly supporting the claim that constraint gating and preference shaping are independent channels (H1a).
- **Honest negative findings**, reported at the same standing as positives: at 100-solution budgets CodonFlow trails LinearDesign and codonGPT on absolute hypervolume (0.22–0.53 geometric-mean ratios); single-objective scenes concede to DP as pre-registered; two-objective coverage contracts when guidance activates. These bound the current claims and motivate the capacity study (§6).

---

## 2. Related Work

**Codon optimization.** CAI-greedy is the classical frequency-matching heuristic. LinearDesign [Zhang et al., 2023] recasts codon optimization as lattice DP over a codon graph, achieving near-optimal CAI–MFE trade-offs; it remains the strongest single/double-objective engine and we adopt it as the pre-registered upper-bound anchor. GEMORNA [Zhang et al., Science 2025] frames CDS design as sequence-to-sequence translation with a transformer encoder–decoder; its public release postdates our protocol freeze and is listed as a pending baseline. codonGPT (NAR 2025) trains a GPT-2 over codon tokens and constrains decoding by logit masking; we use its released checkpoint as the AR+masking representative. mRNAutilus combines a masked diffusion model with Monte-Carlo tree guidance for full-transcript design; no public code exists at the time of writing, so per our pre-registered policy it is documented rather than run.

**Discrete flow / guided discrete diffusion.** pCoMole (NeurIPS 2026) demonstrated terminal-distribution gating and Doob-$h$ guidance for protein design; CodonFlow transfers the machinery to the mRNA codon domain with a synonymous-edit (fixed-length) process and a codon-indexed vocabulary. GrammarRL supplies the label-free dual-reward RLOO recipe (direct + reverse), with reported ablations showing single-reward collapse; we mirror its equal-weight configuration and reproduce the same qualitative pattern in the codon domain (§5.3).

**Multi-objective scalarization.** Our utility is an augmented Tchebycheff on min–max normalized objectives [Zhang & Li, 2007, MOEA/D]. §5.5 documents a degeneracy we introduced and later repaired—an instructive case where textbook formulas interact badly with sparse preference vectors, quantified with a before/after controlled rerun.

---

## 3. Method

### 3.1 Problem setting

Given a source CDS $x$ encoding protein $p$, produce a set $Y$ of synonymous variants such that every $y\in Y$ satisfies the hard feasibility predicate

$$\mathcal{F}(x) = \{y : \text{len}(y)\equiv 0 \pmod 3,\ \mathrm{Trans}(y)=p,\ y \text{ ends in exactly one stop codon}\},$$

while maximizing a coverage measure (hypervolume) of the objective vector

$$f(y) = \big(\mathrm{CAI}(y),\ -\mathrm{MFE}(y),\ -|\mathrm{GC}(y)-0.55|,\ -\mathrm{motif}(y)\big)$$

under an equal sampling/evaluation budget shared by all methods.

### 3.2 Gated terminal distribution and edit flow

CodonFlow is a token-level discrete flow on the 64-codon vocabulary (plus BOS/EOS). The model $q_\theta$ is a transformer over codon tokens; training minimizes the edit-flow objective on corruption-style episodes: at corruption level $t\sim U[0,1]$, a random subset of $t\cdot L$ codons of the true sequence is replaced by uniform synonymous draws, and the model learns to denoise both *which* positions were corrupted and *what* the true codons were. This corruption pretraining was adopted after an information-theoretic audit showed that naive masking degenerates into a marginal codon frequency table (validation loss $\approx$ marginal entropy; §5.6).

The terminal distribution used at sampling time is

$$G(x) \;\propto\; \exp\!\big(\beta\,U(x)\big)\,\mathbb{1}[x\in\mathcal{F}],$$

with $U$ the augmented Tchebycheff utility of §3.3. Because the sampler only ever proposes synonymous single-codon edits (§3.4), path feasibility holds by construction and the indicator acts through the reward at the terminal (and lookahead) level.

### 3.3 Augmented Tchebycheff utility (and the degeneracy we fixed)

Objectives are min–max normalized to $[0,1]$ with calibration quantiles (5%/95%) frozen on a baseline solution pool before any evaluation. With preference vector $\omega \in \Delta_3$ (three active objectives; motif weight fixed at 0.5),

$$U(f) = \min_{k:\,\omega_k>0} \omega_k f_k \;+\; \rho \textstyle\sum_k \omega_k f_k .$$

The min runs over **active axes only**. In our first implementation it ran over all axes; since $0\cdot f_k = 0$ always wins the min under sparse $\omega$, 28 of 29 scan directions had $|U|\approx 0.01$ versus 0.22 for the all-positive direction—the Doob-$h$ guidance was effectively switched off outside the balanced direction. §5.5 reports the controlled repair: identical seeds, protocol, and budget; only the utility changed; S3 hypervolume rose +12.2% (eGFP) / +12.8% (nanoLuc), while identity/legality stayed at exactly 100%. RLOO training used an all-positive $\omega$ throughout and is bit-identical under the fix.

### 3.4 Batched guided sampler

At each of $T$ steps the sampler (i) proposes $C$ candidate synonymous edits, (ii) scores them with a single forward pass (token logits cover all positions), (iii) evaluates the lookahead reward $r(y')=\beta U(y')$ on the edited sequences with a shared MFE cache, and (iv) applies the top-$k$ ($k=4$) edits sampled from the Doob-weighted pool $\propto \exp(\log u + \log h)$. When $\omega_{\mathrm{MFE}}=0$, MFE folding is provably skipped (bit-identical utility); final solution pools are folded in batch.

### 3.5 Label-free RLOO fine-tuning

Following GrammarRL, we fine-tune with leave-one-out baselines over groups of $N=3$ policy rollouts plus one LinearDesign solution mixed at equal weight into the baseline (not as an imitation target). The reward combines a *direct* term (length-normalized edit log-likelihood) and a *reverse* term (translation-cycle consistency, deterministic under the standard genetic code), combined with a frozen regularizer $\beta=0.02$ against the reference policy. The pre-registered equal-weight ($\lambda=0.5$) configuration is the main model; $\lambda\in\{0,0.25,0.75,1\}$ form the ablation row.

---

## 4. Evaluation Protocol

### 4.1 Corpus and splits

Pretraining corpus v2: 215,246 CDS from GENCODE v47 (human) + four Ensembl species (mouse, fly, zebrafish, *C. elegans*), cleaned by a fixed rule set (length 300–1800 nt, frame-aligned, ATG start, canonical single terminal stop, no ambiguous nucleotides, no internal stops), deduplicated by MMseqs2 clustering at 0.8 identity; cluster-disjoint 80/10/10 splits (107,811 clusters). Corpus v3 (capacity study): 862,240 sequences across 25 species (adds rat, chimp, dog, chicken, rhesus, cattle, pig, xenopus, gorilla, medaka, yeast, cat, rabbit, guinea pig, sheep, horse, fugu, two *Ciona*, anole), 311,228 clusters, identical cleaning and split rules.

### 4.2 Four-layer benchmark

| Layer | Content | Seeds × solutions | Purpose |
|---|---|---|---|
| L1 classic | eGFP (717 nt), nanoLuc (516 nt) | 3 × 100 | comparability with prior work |
| L2 held-out | 18 genes, 9 species, 3 length bands (315–1764 nt) | 1 × 50 | leakage-controlled generalization |
| L3 cross-family OOD | mouse, fly, zebrafish genes (465–1905 nt) | 3 × 100 | distribution-shift robustness |
| L4 long-sequence | SpCas9 (4,107 nt) | 3 × 20 | length scaling, AR arch limit |

L2 sampling: drawn from the v3 *test* split only; three-pass leakage audit—(i) direct ID overlap with train/val (v2 and v3) = 0; (ii) same-cluster neighbor exclusion at 0.8 identity (30,938 sequences removed from the candidate pool); (iii) post-selection re-audit = 0 overlap. The first draft of this layer (sampled from the pooled corpus) was discarded when the audit found 16/18 sequences inside training clusters.

Baselines: LinearDesign (official binary, 7-point $\lambda$ scan), codonGPT (released checkpoint, constrained sampling; plus a 1,000-solution 10× variant per protocol fairness for AR), CAI-greedy, and the uniform unguided edit flow (our ablation anchor). All methods receive the same solution budget; the CodonFlow arm uses an $\omega$-direction scan (1/5/7 directions for S1/S2/S3) matching the front-coverage protocol class of the LD scan and GPT sampling.

Metrics: hypervolume (HV) per scenario with fixed reference points, non-dominated share, pairwise NED (diversity), per-solution wall-clock, and the hard guarantees (identity rate, legality rate). Identity/legal are reported as *minimum over all runs*, never mean-only.

### 4.3 Pre-registered judgments

(i) Single-objective scenes may concede to DP (expected). (ii) Guidance should beat unguided flow. (iii) Hard guarantees must hold everywhere, including OOD and long sequences. (iv) A 10× AR sampling variant must be reported alongside the 100-solution comparison. Deviations and negative outcomes are reported rather than suppressed.

---

## 5. Results

### 5.1 Constraint masking collapses diversity (EXP-1)

1,000 solutions × 3 seeds per arm on eGFP/nanoLuc. KS tests on NED distributions: constrained-masked codonGPT sampling shifts NED significantly below unconstrained sampling ($p<0.05$); codon entropy under masking drops from 1.10 to 1.06 bits. Masked AR is thus diversity-limited even before objective guidance is applied.

### 5.2 Gating versus post-hoc filtering at equal budget (EXP-2)

Three arms share a 500-evaluation budget per sequence: guided-gated sampling, uniform-generate-then-filter (rank by $G$), hard mask. Across 5 families × 3 seeds, gated sampling reaches a usable (legal ∧ identity-preserving) solution with markedly fewer evaluations (time-to-first-usable, Wilcoxon $p=6.1\times10^{-5}$ on paired HV); at high budget the filter arm partially catches up on HV but never on guarantee coverage. Consistent with the pre-registered reading: by-construction gating buys *efficiency and guarantees*, not unlimited quality.

### 5.3 Dual-reward necessity (EXP-4, 3 seeds)

Equal-weight RLOO yields the best downstream hypervolume (eGFP 4.43 / nanoLuc 3.30 guided-decode HV vs pretrain 3.51). Pure direct reward degrades diversity; pure reverse reward collapses the policy into a constraint indicator (HV 4.02/2.91, fastest plateau). The GrammarRL "single-reward backlash" pattern reproduces in the codon domain.

### 5.4 Four-layer main comparison (EXP-5/E7)

All numbers: mean ± std; HV; hard guarantees are *minimums* across every run.

**L1 (3 seeds × 100):**

| method | S1 (CAI) | S2 (CAI+MFE) | S3 (four-objective) |
|---|---|---|---|
| CodonFlow | 0.33±0.01 | 32.39±5.86 | **128.09±16.55** |
| LinearDesign scan | 0.37±0.01 | 108.58±15.50 | 484.31±73.97 |
| codonGPT (100) | 0.40±0.01 | 54.38±11.22 | 248.68±58.84 |
| codonGPT (10×=1000) | 0.40±0.02 | 109.74±80.44* | 456.09±282.89* |
| CAI-greedy | 0.500 | 45.77±12.42 | 201.48±59.67 |
| Uniform flow | 0.29±0.01 | 24.87±7.43 | 75.37±21.36 |

*10× values computed on 14 gene-seeds across layers; the 10× protocol is reported separately per §4.3(iv).

CodonFlow vs its own unguided base: +30% (S2) / +70% (S3) on L1; **L2 geometric-mean ratios 1.27 (S2) / 1.44 (S3), per-gene win rates 14/15 and 13/15**; identity/legal minimum = 100% on all 48 gene-scenario cells. Absolute standing vs LD/GPT: geometric-mean ratios 0.22–0.53 (S2/S3) — as pre-registered, DP and heavy AR sampling lead absolute coverage at this budget.

**L3 (cross-family OOD, 3 seeds):** identity/legal decay = **0.00 pp** in every scenario (4,500 solutions, zero violations). Length-invariant standing (CF/strongest-baseline HV ratio): no cross-family collapse; the S3 relative standing *rises* on longer OOD genes.

**L4 (Cas9 4,107 nt):** codonGPT fails at codon position 1,024 (device assertion; the AR context wall) — the only runnable learned methods are edit-based. Wall-clock: CodonFlow 310 s/solution vs LinearDesign 510 s/solution (0.61×) — the DP engine slows on long sequences while the edit flow does not; combined with L2's length trend (CF/LD ratio 0.07@375 nt → 0.32@1,764 nt) this is a consistent length-advantage signature.

### 5.5 The Tchebycheff degeneracy: a controlled before/after (mechanism evidence)

Same seeds, protocol, budgets; only the utility fix differs (§3.3). Utility magnitude per scan direction: pre-fix 28/29 directions at $|U|\approx0.01$ vs 0.216 for the balanced direction; post-fix all directions in 0.20–0.45, and S1-direction CAI responsiveness rises 64×. Downstream: S3 HV +12.2% (eGFP) / +12.8% (nanoLuc); S2 mixed (−7.5% / +2.3% — coverage contraction as guidance sharpens); **identity/legality unchanged at 100%**. This is direct evidence for H1a (independent steering of constraint and preference channels) and an instructive negative-result-turned-mechanism: a "quiet" reward-scale bug masqueraded as weak axial control until audited.

### 5.6 Pretraining pathologies and repairs (diagnostics)

v1 masking pretraining converged to validation loss 4.06 ≈ marginal codon entropy 4.03 (the model ignored its input); the corruption-based v2 objective reaches 2.80 with conditional gap 0.82, and downstream hypervolume rose 3.51 → 4.73. On the v3 corpus (4× data), the same 56M architecture reaches validation 2.872 in a single epoch — the data-size effect under matched protocol. (The 355M capacity tier is trained but not converged at the time of writing; §7.)

### 5.7 Known evaluator-domain limits (honest reporting)

Fixed HV reference points are calibrated on primate/vertebrate objective ranges: the yeast held-out gene and Cas9's motif axis fall outside the calibrated domain (S3 HV → 0 despite 100% identity/legality and non-degenerate solutions). These cells are excluded with footnotes rather than imputed; a length/distribution-normalized reference scheme is queued (§7).

---

## 6. Discussion

**What the evidence supports.** (i) By-construction gating delivers its advertised guarantee — perfect identity and legality on every layer, including OOD and 4.1 kb sequences, with zero decay — something no other arm achieves across all layers (the AR baseline cannot even *run* on long sequences). (ii) The preference channel demonstrably steers (before/after §5.5; uniform→guided ratios §5.4). (iii) Efficiency: gating reaches usable solutions under tight budgets (§5.2), and the edit flow's length wall-clock advantage reverses the DP comparison on 4.1 kb sequences.

**What it does not (yet) support.** Absolute multi-objective coverage at 100-solution budgets: LinearDesign's DP and codonGPT's diversity-heavy sampling maintain 2–4× higher hypervolume. Our three-layer diagnosis — protocol parity (fixed), reward utility (fixed), and now *base-model capacity* — is consistent with the scaling study (v3 corpus 4× data already recovers parity in pretraining loss in one epoch), but the converged 355M downstream evaluation remains future work. We deliberately report this as the current frontier rather than obscure it.

**Threats to validity.** (i) HV reference-point domain sensitivity (§5.7). (ii) L2 uses a single seed (budget); conclusions there rest on 16 independent genes rather than seed variance. (iii) Reverse-reward consistency is deterministic under the standard code — organisms with non-standard codes would need table-aware checks.

---

## 7. Conclusion and Future Work

CodonFlow shows that synonymous-CDS feasibility can live inside a discrete flow's terminal distribution, that label-free dual-reward RLOO transfers to the codon domain, and that a leakage-audited multi-layer benchmark with pre-registered judgments can keep honest score. The immediate roadmap: (i) finish the 355M capacity tier and complete the three-point capacity curve (data effect vs model effect); (ii) length/distribution-normalized HV references and motif penalties; (iii) GEMORNA as the generative-SOTA baseline; (iv) full-transcript (UTR-aware) extension.

Reproducibility. All code, corpus-construction scripts, per-run JSON outputs, and the backup manifest of every checkpoint are released (github.com/Cunyu-Liu/codonflow; commit 114fbb9).

---

## References (selected, to be completed)

[1] Zhang, H. et al., "LinearDesign: efficient algorithms for optimized mRNA sequence design," *Nature Methods* (2023).
[2] pCoMole: Chatterjee Lab, NeurIPS (2026). Code: huggingface.co/ChatterjeeLab/pCoMole.
[3] GrammarRL: dual self-supervised rewards with RLOO (2026).
[4] Zhang, Q., Li, H., "MOEA/D: A multiobjective evolutionary algorithm based on decomposition," *IEEE TEVC* 11(6), 2007.
[5] codonGPT, *Nucleic Acids Research* (2025). Checkpoint: naniltx/codonGPT.
[6] Zhang, H. et al., "Deep generative models design mRNA sequences with enhanced translational capacity and stability," *Science* 390(6773) (2025). Code: github.com/RainaBio/GEMORNA.
[7] Patel, S. et al., "mRNAutilus: multi-objective-guided discrete generation of mRNA," arXiv:2605.31296 (2026).
[8] GENCODE v47; Ensembl release 112 CDS repositories.
