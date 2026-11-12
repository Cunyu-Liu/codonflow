# Finite-step synonymous editing for budget-aware multi-objective CDS optimization

> **Status: working manuscript — not for submission.** No new model has passed G1, and no learned-versus-simple-search result exists. This file contains only methods, evaluation protocol, and evidence status as of 2026-11-13. Results sections remain gated.

## Abstract

[Write after G1–G4. Do not fill with protocol smoke tests, training losses, or historical performance claims.]

## 1. Introduction

A protein can be encoded by an exponential number of synonymous coding sequences (CDS). Improving codon usage, predicted folding energy, GC composition, and motif profiles under a fixed evaluation budget is therefore a constrained multi-objective optimization problem, not merely a feasibility problem. Methods that preserve translation identity can still differ substantially in the quality and diversity of solutions reached per scorer evaluation.

We study warm-start synonymous CDS editing: given a source CDS, make finite-step synonymous changes while preserving its translated protein. Our central question is whether a learned edit proposal improves anytime multi-objective quality relative to the strongest non-learned simple search under identical initialization, terminal objectives, and evaluation budgets. Short rollouts, reinforcement learning, larger models, and external comparisons are conditional on answering this question and are not assumed contributions.

## 2. Related Work

LinearDesign uses dynamic programming for joint codon-use and RNA-structure optimization [zhang2023lineardesign]; codonGPT applies reinforcement learning to generative mRNA design [rajbanshi2025codongpt], while GEMORNA uses deep generative models for CDS and UTR design [zhang2025gemorna]. mRNAutilus jointly generates coding and untranslated regions using discrete diffusion and Monte Carlo tree guidance [patel2026mrnautilus]. ProMORNA uses cold-start supervised fine-tuning followed by multi-objective reinforcement learning [shao2026promorna], and mRNA-GPT uses full-length pretraining and PPO-based optimization [li2026mrnagpt]. These full-transcript tasks are not directly interchangeable with our CDS-only warm-start task. pCoMole combines a feasibility-gated terminal distribution, augmented Tchebycheff utility, Doob-h transformation, and short Monte Carlo rollouts for variable-length biomolecular editing [chen2026pcomole]. AReUReDi combines Tchebycheff scalarization, locally balanced proposals, and annealed Metropolis–Hastings updates [chen2025areuredi]; MOG-DFM uses hybrid rank-directional scores and an adaptive hypercone filter for multi-objective discrete flow guidance [chen2025mogdfm]. TR2-D2 instead uses tree-search replay buffers for trajectory-aware fine-tuning [tang2025tr2d2]. These overlaps require direct comparison with simple search rather than claims of theoretical firstness. Our AReUReDi-style baseline is an internal synonymous-search implementation, not an official reproduction. RayGun miniaturizes and modifies natural proteins [devkota2026raygun], while SCISOR learns insertion–deletion distributions for protein shrinking [baron2025scisor]. Neither is a synonymous CDS editor, so both are excluded from synonymous CDS numerical baselines.

## 3. Method

### 3.1 Task and invariants

For source CDS $x$ encoding protein $p$, the editor outputs candidates $y$ with the same length and reading frame, identical translation $p$, and exactly one terminal stop codon. Validity follows from the synonymous edit operator, not from a post-hoc filter. ATG start is not required by the operator; non-ATG records are separately reported as possible partial CDS rather than silently discarded or mislabeled as operator-invalid.

The objective vector, written in maximization form, is

$$f(y)=\left[\mathrm{CAI}(y),-\mathrm{MFE}(y),-|\mathrm{GC}(y)-g_\star|,-\mathrm{motif}(y)/L_{\mathrm{codons}}\right].$$

All objectives are computational proxies. We use $g_\star=0.55$ as a frozen design setting, not a claim of universal biological optimality. CAI follows Sharp and Li's geometric mean of relative synonymous codon adaptiveness [sharp1987cai] and depends on a train-only or independent reference RSCU table. MFE depends on the declared ViennaRNA implementation and default folding conditions [lorenz2011viennarna].

### 3.2 Finite-step synonymous proposal

A state is a legal CDS. An elementary learned move selects one non-stop codon position and replaces it with an alternative synonymous codon, with an explicit stay action. For position $i$, current codon $c$, blank logits $a_i$, and token logits $u_{ic}$, alternatives are normalized only within the amino-acid group. All non-self (position, codon) events and the aggregated stay event are jointly normalized. The terminal stop is never edited.

The primary development evaluation uses the learned base kernel for four finite transitions ($T=4$), without terminal guidance or rollout. This isolates the value of the learned proposal. Batched paths use the same kernel and random-number stream ordering per state; vectorized local normalization changes neither the transition support nor the accounting of state transitions. A terminal preference potential can tilt the finite-step kernel. Exact backward recursion is used only on enumerable small states. On large CDS spaces, short Monte Carlo rollouts and candidate pruning are approximations, not claims of an exact terminal distribution, and are evaluated separately after the base proposal.

The learned proposal is evaluated against global uniform synonymous sampling, greedy hill-climbing, Metropolis–Hastings/annealing, and an AReUReDi-style search. The uniform baseline independently samples synonymous codons per position after scoring the paired initial state; the other non-learned methods use the same single-codon local operator as the learned kernel. Search utilities use weights $(1,1,1,0.5)$ after frozen calibration normalization; AReUReDi-style uses an augmented Tchebycheff scalarization. These are internal implementations, not claims of exact reproduction of all external algorithms.

We record forward calls, base-state evaluations, rollout batch forwards, rollout transitions, cache-before terminal requests, actual scorer invocations, unique scorer evaluations, and wall-clock separately. Each method has an independent cache with identical semantics, preventing another method's evaluations from consuming or subsidizing its budget.

### 3.3 Synonymous-corruption training

Development models are trained from scratch on D4 with synonymous corruption: corrupted codons are sampled only within the same amino-acid group, so both training and inference states preserve translation identity. Full-token and edited-token objectives are evaluated independently and their validation losses are not compared as if they were identical metrics. No arbitrary-corruption checkpoint is used for initialization or downstream evaluation.

Each arm has 56.8M parameters (width 768, 8 Transformer layers, 12 heads, no dropout) [vaswani2017attention] and uses AdamW [loshchilov2017adamw] with learning rate $10^{-5}$ and weight decay 0.03. The effective training budget is 60,000 tokens per optimizer update: full-token uses 20,000-token packed batches with three accumulation steps, and edited-token uses 10,000-token batches with six. Both use a maximum batch size of 128 and gradient clipping at 1.0. The validation packed-batch budget is 24,000 tokens, with corruption seed 1729. Each original validation batch is corrupted once; forward computation is split into 4,000-token micro-batches to bound attention memory. BCE and token losses are recombined using their respective valid-position counts, preserving the original batch's random draws and normalization.

Convergence requires three consecutive epochs with less than 0.1% relative validation improvement. There is no maximum-epoch stopping rule. We freeze best, last, optimizer/RNG training state, converged weights, complete configuration, and SHA256 hashes, and verify loading and a finite forward pass on CUDA. Convergence alone is insufficient: the model must also pass non-degeneracy checks on at least three development genes with 100 paired samples per gene, including 100% identity/legal relative to the natural source, at least 95% outputs differing from their corresponding randomized synonymous initial sequence, at least 80 unique terminal sequences per 100, and maximum single-sequence frequency at most 20%.

## 4. Evaluation Protocol

### 4.1 Data versions and provenance

D4 contains 621,306/76,444/78,724 train/validation/test unique proteins with zero exact CDS or protein overlap across splits. D5 uses operational protein-homology-cluster isolation with MMseqs2 identity 0.5 and bidirectional coverage 0.8 [steinegger2017mmseqs2], yielding 618,073/80,191/78,177 records. D5 does not establish curated family- or species-level out-of-distribution generalization.

The source corpus contains 862,240 records from 25 species using Ensembl release 112. Recovery artifacts retain URLs, retrieval timestamps, raw and cleaned hashes, and per-rule cleaning counts without claiming the original download dates. A release-116 human recovery was evaluated and isolated because it introduced 227,289 additional base identifiers and was not the closest source match. Non-ATG sequences are reported separately. Standard genetic code table 1 is used throughout.

The development benchmark consists of eGFP, nanoLuc, and the repeatedly used unique18 set. It is not an untouched test set. A separate 24-gene D5 confirmation set was selected using only length, GC, identifiers, and cluster membership, with exact CDS/protein and homology exclusions. It is reserved for final confirmation and not used for model tuning.

### 4.2 Independent reference domains and objectives

CAI/RSCU tables are built only from the corresponding training split or an independent public reference. D4 and D5 tables are never mixed. For each development gene, an independent calibration pool contains 40 global-uniform runs and four axis-specific hill-climbing runs of 10 unique evaluations each (calibration seed 1729). Confirmation-gene pools use the same construction with the D5 training RSCU. No learned-model or final evaluation output contributes to these pools.

If $l_j$ and $u_j$ are the minimum and maximum of unique calibration objectives on axis $j$, the reference is $r_j=l_j-0.05(u_j-l_j)$ and the scale is $q_{0.95,j}-l_j$. Non-finite or non-positive scales are rejected. The same frozen normalization is used for search utility and anytime hypervolume AUC. The 18-gene D4 development pools have been checked against source and RSCU hashes, independently recomputed reference domains, and byte-identical regeneration of a representative pool.

The primary endpoint is hypervolume AUC over unique terminal-scorer budgets $B=50,100,500$, including the initial point at zero budget [zitzler1999hypervolume]. Secondary endpoints include raw Pareto fronts, per-objective best-at-budget, non-dominated metrics, and length-normalized NED. Output count, scorer count, and wall-clock are separate budgets; solutions are never randomly padded to match another method. Incomplete runs are retained as partial evidence and cannot enter the scientific comparison.

### 4.3 Comparisons and statistics

Internal comparisons use identical source CDS, paired initialization, terminal objective, independently initialized scorer caches with identical semantics, and seeds 0, 1, and 2. For each gene and seed, the initial CDS is a per-position uniform synonymous sample from the natural source using initialization seed $1009\times$ the run seed. All methods score that same initial state at budget one. The learned arm uses $T=4$ and 32 paths per model-forward batch. Every comparison requires 500 unique terminal evaluations per gene, seed, and method. The gate independently reconstructs paired initializations, verifies every raw sequence and its uniqueness, checks independent-calibration provenance, and recomputes NED and anytime AUC from raw points. Metadata that disagrees across genes or arms is rejected.

For each gene, the strongest simple baseline is the method with the greatest mean AUC over the three seeds. Learned and baseline AUCs are then averaged within gene. Genes—not seeds—are the independent statistical units. We report median relative effect, 10,000 gene-level paired bootstrap replicates for the 95% confidence interval, one-sided Wilcoxon signed-rank tests [wilcoxon1945ranking], and Holm correction across the full-token and edited-token arms [holm1979sequential]. NED is computed from a deterministic sample of at most 200 outputs per run and is compared with the same per-gene strongest baseline.

External methods are assessed by task and input type. Natural-source warm-start and protein-only initialization are reported separately. Unavailable costs are `null`, and architectural exclusions or missing methods are explicit rather than scored as zero. Third-party pretraining overlap that cannot be audited is reported as a limitation.

### 4.4 Evidence gates

G0 requires complete data provenance, distribution and metadata audits, development/confirmation protocols, independent calibration, result schemas, baseline resources, and actual synchronized CUDA matmul evidence. G1 requires convergence and non-degeneracy. G2 requires complete 18-gene, three-seed comparisons in both arms, at least 10% median relative improvement in the primary endpoint, a positive paired-bootstrap lower bound, Holm-corrected $p<0.05$, full identity/legal, and learned NED at least 70% of the selected strongest baseline in every gene. G3 tests whether short-rollout benefits exceed costs. G4 repeats the comparison in the untouched confirmation set and assesses external boundaries. G5 permits scientific results and release claims only after the corresponding evidence exists.

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

## 8. References

Chen, T., Holsman, M., Zhao, L., and Chatterjee, P. pCoMole: Pareto-Constrained Molecule Editing with Discrete Flows. *arXiv:2610.01663* (2026). https://arxiv.org/abs/2610.01663

Chen, T., Zhang, Y., and Chatterjee, P. AReUReDi: Annealed Rectified Updates for Refining Discrete Flows with Multi-Objective Guidance. *arXiv:2510.00352* (2025). https://arxiv.org/abs/2510.00352

Chen, T., Zhang, Y., Tang, S., and Chatterjee, P. Multi-Objective-Guided Discrete Flow Matching for Controllable Biological Sequence Design. *arXiv:2505.07086* (2025). https://arxiv.org/abs/2505.07086

Tang, S., Zhu, Y., Tao, M., and Chatterjee, P. TR2-D2: Tree Search Guided Trajectory-Aware Fine-Tuning for Discrete Diffusion. *arXiv:2509.25171* (2025). https://arxiv.org/abs/2509.25171

Zhang, H., Zhang, L., Lin, A., et al. Algorithm for optimized mRNA design improves stability and immunogenicity. *Nature* (2023). https://doi.org/10.1038/s41586-023-06127-z

Rajbanshi, B., and Guruacharya, A. codonGPT: reinforcement learning on a generative language model enables scalable mRNA design. *Nucleic Acids Research* (2025). https://doi.org/10.1093/nar/gkaf1345

Zhang, H., Liu, H., Xu, Y., et al. Deep generative models design mRNA sequences with enhanced translational capacity and stability. *Science* (2025). https://doi.org/10.1126/science.adr8470

Patel, S., Tang, S., Kim, Y., et al. mRNAutilus: Multi-Objective-Guided Discrete Generation of mRNA with Optimized Therapeutic Properties. *arXiv:2605.31296* (2026). https://arxiv.org/abs/2605.31296

Shao, Z., Wang, T., Shen, Y., Huang, T., and Xiao, Y. ProMORNA: An End-to-End Generative Framework for Full-Length mRNA Design. *arXiv:2605.01513* (2026). https://arxiv.org/abs/2605.01513

Li, S., Chauvin, P., Gross, O., Bailey, M., and Jager, S. mRNA-GPT: A Generative Model for Full-Length mRNA Design and Optimization. *bioRxiv* (2026). https://doi.org/10.64898/2026.03.31.715707

Devkota, K., Shonai, D., Mao, J., et al. Miniaturizing and modifying natural proteins with Raygun. *Nature* (2026). https://doi.org/10.1038/s41586-026-10842-8

Baron, E., Amin, A. N., Weitzman, R., Marks, D., and Wilson, A. G. A Diffusion Model to Shrink Proteins While Maintaining Their Function. *arXiv:2511.07390* (2025). https://arxiv.org/abs/2511.07390

Sharp, P. M., and Li, W.-H. The codon adaptation index—a measure of directional synonymous codon usage bias, and its potential applications. *Nucleic Acids Research* (1987). https://doi.org/10.1093/nar/15.3.1281

Lorenz, R., Bernhart, S. H., Höner zu Siederdissen, C., et al. ViennaRNA Package 2.0. *Algorithms for Molecular Biology* (2011). https://doi.org/10.1186/1748-7188-6-26

Vaswani, A., Shazeer, N., Parmar, N., et al. Attention Is All You Need. *arXiv:1706.03762* (2017). https://arxiv.org/abs/1706.03762

Loshchilov, I., and Hutter, F. Decoupled Weight Decay Regularization. *arXiv:1711.05101* (2017). https://arxiv.org/abs/1711.05101

Steinegger, M., and Söding, J. MMseqs2 enables sensitive protein sequence searching for the analysis of massive data sets. *Nature Biotechnology* (2017). https://doi.org/10.1038/nbt.3988

Zitzler, E., and Thiele, L. Multiobjective evolutionary algorithms: a comparative case study and the strength Pareto approach. *IEEE Transactions on Evolutionary Computation* (1999). https://doi.org/10.1109/4235.797969

Wilcoxon, F. Individual Comparisons by Ranking Methods. *Biometrics Bulletin* (1945). https://doi.org/10.2307/3001968

Holm, S. A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 6(2), 65–70 (1979). https://www.jstor.org/stable/4615733
