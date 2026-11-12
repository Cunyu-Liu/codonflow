# Finite-step synonymous editing for budget-aware multi-objective CDS optimization

> **Status: working manuscript — not for submission.** No new model has passed G1, and no learned-versus-simple-search result exists. This file contains only methods, evaluation protocol, and evidence status as of 2026-11-12. Results sections remain gated.

## Abstract

[Write after G1–G4. Do not fill with protocol smoke tests, training losses, or historical performance claims.]

## 1. Introduction

A protein can be encoded by an exponential number of synonymous coding sequences (CDS). Improving codon usage, predicted folding energy, GC composition, and motif profiles under a fixed evaluation budget is therefore a constrained multi-objective optimization problem, not merely a feasibility problem. Methods that preserve translation identity can still differ substantially in the quality and diversity of solutions reached per scorer evaluation.

We study warm-start synonymous CDS editing: given a source CDS, make finite-step synonymous changes while preserving its translated protein. Our central question is whether a learned edit proposal improves anytime multi-objective quality relative to the strongest non-learned local search under identical initialization, terminal objectives, and evaluation budgets. Short rollouts, reinforcement learning, larger models, and external comparisons are conditional on answering this question and are not assumed contributions.

## 2. Related Work

LinearDesign uses dynamic programming for codon optimization; codonGPT and GEMORNA represent generative CDS models. mRNAutilus, ProMORNA, and mRNA-GPT address broader full-length mRNA generation or reinforcement-learning settings and are not directly interchangeable with our CDS-only warm-start task. pCoMole introduced related terminal gating and Doob-style guidance concepts; AReUReDi and MOG-DFM study multi-objective discrete search and flow guidance, while TR2-D2 studies trajectory-aware training. These overlaps require direct comparison with simple search rather than claims of theoretical firstness. RayGun and SCISOR address protein editing or deletion and are excluded from synonymous CDS numerical baselines.

## 3. Method

### 3.1 Task and invariants

For source CDS $x$ encoding protein $p$, the editor outputs candidates $y$ with the same length and reading frame, identical translation $p$, and exactly one terminal stop codon. Validity follows from the synonymous edit operator, not from a post-hoc filter. ATG start is not required by the operator; non-ATG records are separately reported as possible partial CDS rather than silently discarded or mislabeled as operator-invalid.

The objective vector, written in maximization form, is

$$f(y)=\left[\mathrm{CAI}(y),-\mathrm{MFE}(y),-|\mathrm{GC}(y)-g_\star|,-\mathrm{motif}(y)/L_{\mathrm{codons}}\right].$$

All objectives are computational proxies. We use $g_\star=0.55$ as a frozen design setting, not a claim of universal biological optimality. CAI depends on a train-only or independent reference RSCU table, and MFE depends on the declared RNAfold implementation and default folding conditions.

### 3.2 Finite-step synonymous proposal

A state is a legal CDS. An elementary move selects one codon position and replaces it with an alternative synonymous codon, with an explicit stay action. Position and codon probabilities are jointly normalized. The learned proposal is evaluated against uniform synonymous moves, greedy hill-climbing, Metropolis–Hastings/annealing, and an AReUReDi-style search using the same operator and terminal scorer.

A terminal preference potential can tilt the finite-step kernel. Exact backward recursion is used only on enumerable small states. On large CDS spaces, short Monte Carlo rollouts and candidate pruning are approximations, not claims of an exact terminal distribution. We record forward calls, base-state evaluations, rollout batch forwards, rollout transitions, cache-before terminal requests, actual scorer invocations, unique scorer evaluations, and wall-clock separately.

### 3.3 Synonymous-corruption training

Development models are trained from scratch on D4 with synonymous corruption: corrupted codons are sampled only within the same amino-acid group, so both training and inference states preserve translation identity. Full-token and edited-token objectives are evaluated independently and their validation losses are not compared as if they were identical metrics. No arbitrary-corruption checkpoint is used for initialization or downstream evaluation.

Convergence requires three consecutive epochs with less than 0.1% relative validation improvement. There is no maximum-epoch stopping rule. We freeze best, last, optimizer/RNG training state, converged weights, complete configuration, and SHA256 hashes. Convergence alone is insufficient: the model must also pass non-degeneracy checks on at least three development genes with 100 paired samples per gene, including 100% identity/legal, at least 95% non-source outputs, at least 80 unique terminal sequences per 100, and maximum single-sequence frequency at most 20%.

## 4. Evaluation Protocol

### 4.1 Data versions and provenance

D4 contains 621,306/76,444/78,724 train/validation/test unique proteins with zero exact CDS or protein overlap across splits. D5 uses operational protein-homology-cluster isolation with MMseqs2 identity 0.5 and bidirectional coverage 0.8, yielding 618,073/80,191/78,177 records. D5 does not establish curated family- or species-level out-of-distribution generalization.

The source corpus contains 862,240 records from 25 species using Ensembl release 112. Recovery artifacts retain URLs, retrieval timestamps, raw and cleaned hashes, and per-rule cleaning counts without claiming the original download dates. A release-116 human recovery was evaluated and isolated because it introduced 227,289 additional base identifiers and was not the closest source match. Non-ATG sequences are reported separately. Standard genetic code table 1 is used throughout.

The development benchmark consists of eGFP, nanoLuc, and the repeatedly used unique18 set. It is not an untouched test set. A separate 24-gene D5 confirmation set was selected using only length, GC, identifiers, and cluster membership, with exact CDS/protein and homology exclusions. It is reserved for final confirmation and not used for model tuning.

### 4.2 Independent reference domains and objectives

CAI/RSCU tables are built only from the corresponding training split or an independent public reference. D4 and D5 tables are never mixed. Each gene's hypervolume reference point and scale come from an independent calibration pool, not from evaluated test outputs. Degenerate calibration axes are rejected. The same normalization is used for search utility and anytime hypervolume AUC.

The primary endpoint is hypervolume AUC over unique terminal-scorer budgets $B=50,100,500$. Secondary endpoints include raw Pareto fronts, per-objective best-at-budget, non-dominated metrics, and length-normalized NED. Output count, scorer count, and wall-clock are separate budgets; solutions are never randomly padded to match another method.

### 4.3 Comparisons and statistics

Internal comparisons use identical source CDS, paired initialization, synonymous operator, terminal objective, scorer/cache, and at least three sampling seeds. The strongest simple-search baseline is selected independently per gene. Genes—not seeds—are the independent statistical units. We report median relative effect, gene-level paired bootstrap 95% confidence intervals, Wilcoxon signed-rank tests, and Holm multiple-comparison correction.

External methods are assessed by task and input type. Natural-source warm-start and protein-only initialization are reported separately. Unavailable costs are `null`, and architectural exclusions or missing methods are explicit rather than scored as zero. Third-party pretraining overlap that cannot be audited is reported as a limitation.

### 4.4 Evidence gates

G0 requires complete data provenance, distribution and metadata audits, development/confirmation protocols, independent calibration, result schemas, baseline resources, and actual synchronized CUDA matmul evidence. G1 requires convergence and non-degeneracy. G2 requires learned proposals to improve the primary endpoint by at least 10% median relative effect with a positive paired-bootstrap lower bound, corrected $p<0.05$, full identity/legal, and adequate diversity. G3 tests whether short-rollout benefits exceed costs. G4 repeats the comparison in the untouched confirmation set and assesses external boundaries. G5 permits scientific results and release claims only after the corresponding evidence exists.

## 5. Results

### 5.1 Mechanism and non-degeneracy

[Requires G1.]

### 5.2 Learned proposal versus simple search

[Requires G2. This is the central result and may be negative.]

### 5.3 Immediate versus short-rollout editing

[Requires G3.]

### 5.4 Independent confirmation and external boundaries

[Requires G4.]

## 6. Discussion

[Write after G2–G4. Discuss failure regions, proxy limitations, missing baselines, and the distinction between computational objectives and biological efficacy.]

## 7. Reproducibility statement

Every result is linked to its run ID, data and code hashes, dirty-tree status, immutable checkpoint path and SHA256, configuration, seeds, and frozen JSON artifacts. Failed runs, partial outputs, negative results, and unavailable baselines are retained. Current source audits and seed-0 protocol checks do not constitute learned-model performance evidence.
