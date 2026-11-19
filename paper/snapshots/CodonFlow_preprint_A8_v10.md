# Learning structure–translation–decay coupling for synonymous mRNA design

> **Status: A8-RK working manuscript — not for submission.** Verified data, operational split, bounded cross-protein diagnostic, and bounded baseline-execution audits are recorded; core mechanism, model, main baseline matrix, OOD, generator, and wet-lab closure remain incomplete. No SOTA claim.

## Abstract

[Write only after RK-G0–G4. The final abstract must follow: limitation of independent proxies → evidence for spatial coupling on real synonymous variants → mechanism-derived model → strongest-baseline results with OOD and cost → independent functional validation. Do not substitute training loss, legal generation, or planned wet-lab work for results.]

## 1. Introduction

A protein can be encoded by an exponential number of synonymous coding sequences (CDSs), but synonymous variants are not functionally interchangeable. Their differences arise from processes operating at distinct spatial and kinetic scales: RNA structures control access to the translation-initiation region, codon-dependent elongation shapes ribosome traffic and co-translational folding, and translation-coupled decay alters transcript lifetime. These processes are coupled through the complete transcript and host context. A design framework based on independent global scores may therefore miss the determinants that distinguish functional synonymous sequences.

Controlled experiments motivate this concern. Kudla et al. measured a synthetic library of 154 GFP variants and found large expression differences without a significant CAI association, whereas folding near the ribosome-binding region had substantial explanatory power [kudla2009coding]. Boël et al. analyzed 6,348 experiments and linked codon content to protein expression, mRNA abundance and lifetime, with folding effects concentrated near the initial codons [boel2016codon]. MAGE-seq further showed that distant synonymous substitutions can affect fitness by disrupting native 5′ RNA conformations [kelsic2016mage]. These observations do not imply one universal mechanism across hosts and assays. They instead expose a testable gap: can spatially coupled structural and translational variables explain held-out synonymous function better than independent scalar proxies?

We propose to study this question under fixed protein, UTR, host and assay contexts. The intended contribution is not another codon language model with an auxiliary reward. It is a mechanism-derived model, CodonFlow-RK, that represents each synonymous choice on its legal simplex, explicitly models UTR–CDS and long-range CDS interactions, and learns initiation, elongation and decay potentials from structural, Ribo-seq and experimentally measured synonymous-variant data. A preference- and budget-conditioned Markov generator then uses only the potentials supported by out-of-distribution experiments.

The investigation proceeds as a linked chain. First, we quantify where common proxies fail on real variants. Second, we test which mechanistic components add out-of-protein and out-of-study information. Third, we derive the generator from those components and compare it with the strongest task-specific methods under matched quality and time budgets. Fourth, corresponding predictive and generative ablations test whether the same mechanisms explain both function and design gains. Finally, untouched proteins, studies and hosts define the generalization boundary, and independent functional measurements determine biological validity. Prospective design–build–test–learn validation remains necessary for a translational or therapeutic claim.

## 2. Related Work

### 2.1 Codon and CDS design

LinearDesign jointly optimizes codon usage and RNA structure using dynamic programming and lattice parsing [zhang2023lineardesign]. EnsembleDesign extends structure-aware design to ensemble free energy [dai2025ensembledesign]. CodonTransformer learns multispecies codon preferences from more than one million DNA–protein pairs [fallahpour2025codontransformer]. codonGPT combines a codon language model, synonymous logit masking and reinforcement learning [rajbanshi2025codongpt]. GEMORNA uses deep generative models for CDS and UTR design [zhang2025gemorna]. CAGFN applies curriculum-augmented GFlowNets to codon-level multi-objective generation [laajil2025cagfn].

More recent methods are direct competitors rather than background citations. RNARL combines ESM2-conditioned generation, mixture-of-experts layers, length-aware sampling and GRPO across six species and multiple RNA types [lin2026rnarl]. ID3 performs constrained gradient-based input optimization with hard synonymous parameterizations and compares against GA, SA and enumerable small-window optima [li2026id3]. COformer learns from outputs of commercial optimization tools and validates several designs experimentally, but those computational outputs are proxy targets rather than large-scale functional ground truth [kim2026coformer]. VeloHARMO uses organism-specific Ribo-seq models and genetic search to harmonize translation-velocity profiles, while noting the limited amount of quantitative experimental validation [bian2026veloharmo]. CHARMING, tAI-based harmonization, ICOR and frequency-based codon samplers define additional task-specific controls.

Full-transcript methods, including mRNAutilus and ProMORNA, jointly consider CDS and UTRs and add predicted functional objectives and experimental validation [patel2026mrnautilus, shao2026promorna]. They are compared only when UTR, inputs and costs can be made equivalent; otherwise they define an external task boundary rather than entries in a fabricated CDS-only ranking.

### 2.2 Multi-objective discrete generation

AReUReDi, MOG-DFM and pCoMole provide related multi-objective discrete-search or flow formulations [chen2025areuredi, chen2025mogdfm, chen2026pcomole]. GFlowNet trajectory balance, discrete flow matching, ESM embeddings, attention and reinforcement learning are therefore not treated as novel contributions in isolation. The candidate contribution under test is the experimentally supported structure–translation–decay potential and its integration with full-transcript context in a synonymous legal space.

## 3. Data and Scientific Tasks

### 3.1 External data and verified availability

The A8-RK audit separates verified data artifacts from model evidence. RiboMIMO contributes **15,669 raw records** and **8,109 clean records** across four author-processed codon-level A-site-count datasets; the independent verifier passed **13/13 checks**. These files do not contain UTRs or raw reads, so they do not authorize an independent P-site remapping analysis. The clean rule requires aligned lengths, canonical CDS translation, finite nonnegative counts, strict coverage, and exact translated-reference protein matching.

CodonTransformer training-table QC read **1,001,197 raw rows** and retained **449,655 clean rows**; organism counts changed from **164 raw** to **40 clean**. Finalization passed with **8/8 independent checks**. The raw-table SHA256 is `b319f975f4cd9814bf111a59b80000c001987abf33f3e52e77c4d96d434b4fa9`. This artifact supports only a bounded natural DNA–protein sequence-distribution corpus; it does not provide host-matched functional labels, a trained model, functional OOD evidence, or a baseline ranking.

The functional long table contains **25,420 rows** and has SHA256 `c436b758369018fe0fd121ce6e741993e90a5de80b4706ab87082f7557b6a377`. It comprises the verified Boël cross-protein records and MAGE construct-assay rows. The row-level Kudla 154-variant sequence–expression table remains unavailable; supporting methods and degenerate oligos are not substitutes for that table.

The RNARL official 21-file pair table contains **260,754 raw rows**, **256,578 clean rows**, and **128,289 clean pairs**. Raw cross-split exact-CDS overlap comprised **22 keys / 44 rows**; production QC excluded the whole protein pairs, and independent clean-table rescanning found zero exact-CDS and zero protein-sequence cross-split keys. The corrected independent verifier passed **8/8 checks** with maximum numeric delta **0.0**, and recovery finalization passed **10/10 checks**. The initial order-based verifier failure and recovery failure remain preserved. This is only a publisher-provided LinearDesign-like pair table: it does not establish natural-CDS provenance, lambda strata, UTR/raw-read remapping, functional training, functional OOD, official-model reproduction, or a baseline ranking.

VeloHARMO was audited at fixed commit `38b48079856aeb9d33a1b10844d77aa8f6640032`. Its processed E. coli matrix has **1,170 raw = 1,170 clean records**, **0 duplicate gene IDs**, and **6 numeric features**. Independent verification passed **7/7 checks** with maximum numeric delta **0.0**, and finalization passed **8/8 checks**. The official `VeloGRU/VeloGRU_data.py::load_data` returned finite tensors `x=[1170, 1520, 111]`, `density=[1170, 1520, 1]`, and `length=[1170, 1]`. Only the processed E. coli matrix plus E. coli/yeast weights were materialized; **five-species processed matrices are not available** because Pseudomonas, Drosophila, human, and yeast matrices are missing. No five-species dataset closure, raw-read remapping, training, cross-validation, publication-metric, functional-OOD, or SOTA claim is authorized.

### 3.2 Leakage-controlled generalization tasks

Exact CDS, exact protein, identifiers, operational protein-homology clusters and functional source proteins are audited across splits. Variants of the same protein never cross random train/test partitions. Functional prediction uses protein-level OOD; Ribo-seq models additionally use study-level OOD; natural sequence models retain homology-cluster OOD. Length and GC strata evaluate difficult regimes rather than define new tuning sets.

D4 contains 621,306/76,444/78,724 train/validation/test records. D5 contains 618,073/80,191/78,177 records and uses MMseqs2 identity 0.5 with bidirectional coverage 0.8. These are operational splits, not curated family- or species-level proof. The existing unique18 set is development-only. Untouched24 and a separate functional untouched set are evaluated once after all choices are frozen.

**RK04 frozen operational split.** MMseqs2 clustering used identity **0.50**, bidirectional coverage **0.80**, and seed **20261118**. The Boël rows were assigned to train/dev/test = **5,079/635/634**, while **19,072 MAGE rows** remained untouched. Independent verification passed **33/33 checks**, including zero overlap for exact CDS, exact protein/derived infA, source protein ID, operational cluster, construct-signature group, and nonblank mutation signature. These are operational MMseqs2 clusters, not curated protein families. The split is leakage-controlled but is not itself training-ready evidence: MAGE was not evaluated, and no generator or SOTA claim is authorized.

### 3.3 Task-specific comparisons

Functional and fitness prediction is compared with CAI, GC, local/global MFE, Boël's codon-influence models and reproducible sequence or velocity models. Velocity prediction uses RiboMIMO, iXnos, ROSE, VeloGRU and VeloBERT. Harmonization uses VeloHARMO, CHARMING, tAI, ICOR, frequency-based methods and RNARL. Accessibility design uses ID3, GA, SA and C10/C10-CAI, including exact enumeration when feasible. CDS multi-objective design uses LinearDesign, EnsembleDesign, RNARL, CAGFN, codonGPT, GEMORNA, CodonTransformer, COformer and strong internal stochastic searches.

A task is declared superior only when the prespecified effect and its paired confidence-interval lower bound exceed the strongest comparable baseline under the same protocol. Otherwise it remains unresolved; baselines are not replaced with weaker alternatives after seeing results.

## 4. CodonFlow-RK

### 4.1 Synonymous constraint space and transcript context

For target amino acids $a=(a_1,\ldots,a_L)$, each codon belongs to its synonymous set $c_i\in C(a_i)$. This parameterization preserves translation, length and terminal stop by construction. The model conditions on the current synonymous state, protein context, fixed 5′/3′UTRs, host, objective preference and remaining budget. UTR generation is outside the present task.

### 4.2 Dual-resolution structural representation

Codon nodes carry amino-acid, protein, host and current-state information. Each candidate codon is also expanded into three nucleotides. A pairing-constrained interaction channel represents 5′UTR–CDS and long-range CDS–CDS coupling, with high resolution around initiation and sparse or axial long-range interactions for computational tractability. This is a learned structural inductive bias, not a claim to compute an exact partition function.

### 4.3 Structure–translation–decay potentials

The shared representation predicts initiation accessibility $\Phi_{\mathrm{init}}$, an ensemble-structural term $\Phi_{\mathrm{ens}}$, a codon-resolved velocity field $v=(v_1,\ldots,v_L)$, and decay or functional outputs $\Phi_{\mathrm{decay}}$ with uncertainty. These quantities are supervised by their corresponding data layers and are included only when matched ablations show incremental out-of-distribution value. CAI and motif features serve as low-fidelity information; structure and Ribo-seq provide intermediate fidelity; measured expression, fitness or half-life provide high-fidelity supervision.

### 4.4 Preference- and budget-conditioned generation

Given a natural-prior kernel $q_0$, the proposed local transition is

$$q_\theta(y\mid x;w,b,h,u)\propto q_0(y\mid x;h,u)\exp\left[-\beta\sum_k w_k\Delta\Phi_k(x,y)-\beta_c\Delta\mathrm{cost}(x,y)\right],$$

where $w$ denotes Pareto preference, $b$ remaining budget, $h$ host and $u$ fixed UTR context. A preference-conditioned trajectory-balance or energy-tilting objective replaces natural-sequence-only cross-entropy, so terminal feedback is present during training rather than attached only at inference. Small enumerable systems will test agreement between the mathematical target and sampled distribution. If that agreement or the stated objective is not implemented, the method will not be described as a discrete flow.

### 4.5 Required ablations

All components are evaluated under matched inputs, parameter or compute budgets: no pair channel, no initiation term, no velocity field, no decay term, no natural prior, no preference conditioning and no budget conditioning. Predictive and generative ablations must tell a consistent mechanistic story; an attention map or improved scalar reward is not a mechanism demonstration.

## 5. Evaluation Protocol

### 5.1 Proxy validity and mechanistic increments

The first experiment measures proxy–function associations separately by assay and host, without pooling incompatible experimental contexts. The second compares identical backbones with and without mechanistic terms on protein- and study-level OOD. The third tests whether structural fitness, velocity and mRNA/protein outcomes show consistent cross-layer behavior. Retrospective associations are not described as causal unless supported by intervention.

### 5.2 Design quality, diversity and cost

For trajectory-based CDS search, the initial state is scored at $B=1$. The primary anytime endpoint is dense budget-step hypervolume AUC over all observed unique scorer evaluations, without an artificial $(0,0)$ point. Secondary endpoints include actual-budget Pareto fronts, per-objective best values, bidirectional strict dominance, NED and legal/translation identity. External methods with unordered actual outputs are evaluated only at their actual budgets; missing budgets are null and never zero-filled.

Cache-before requests, unique scorer calls, model forwards, generation time, scoring time, wall-clock, hardware and parallelism are reported separately. Continuous optimization and candidate pruning cannot hide internal costs. Time-matched comparisons use the same hardware and worker count. Genes, proteins or studies—not individual seeds—are the independent statistical units.

### 5.3 Hyperparameters and statistics

Learning rate, weight decay, dropout, token batch, ESM freezing, energy and preference temperatures, trajectory-loss weights, candidate count, block size, early stopping and sampling proportions are selected only on development data using bounded ASHA or small preregistered searches. Functional minimum effects are based on assay noise; design effects and cost margins are preregistered. Final results report paired bootstrap 95% confidence intervals, per-unit directions and Holm correction. Untouched data are never used for hyperparameter repair.

## 6. Results

### 6.1 Preliminary diagnosis: why the original model was redesigned

The original development models satisfied convergence and non-degeneracy checks, but these checks did not imply optimization ability. G2 completed all 324 planned runs. Relative to the strongest simple search per gene, full-token and edited-token models had median AUC changes of −94.28% and −93.47%, respectively, with negative effects in all 18 genes and Holm-adjusted $p=1.0$. The comparison also differed in terminal feedback: learned paths were open-loop, whereas iterative baselines used objective feedback.

Embedding the learned proposal in the same hill-climbing rule produced positive development associations. On the remaining 15 development genes, full-token and edited-token arms had median AUC changes of +59.95% and +68.73%, but median time ratios of 42.68 and 2.41. These results motivate separating proposal from feedback and do not establish independent generalization, practical speed or external SOTA.

The implementation provides a more fundamental diagnosis. Natural synonymous-corruption cross-entropy does not optimize terminal function, the network reads only codon identifiers, its loss is a simplified masking objective rather than a full CTMC rate loss, and its transition ignores time. Moreover, none of these experiments uses real synonymous-variant function as supervision. The remaining results therefore test a new scientific question rather than attempting to present the old checkpoint as a successful model.

### 6.2 Proxy validity: bounded cross-protein diagnostic

RK07 evaluated whether simple sequence-derived scores carry signal across different proteins in Boël et al. It is **not** a fixed-protein synonymous-library experiment. The combined model used train-only preprocessing and convex logistic fitting with the frozen feature set `cai, gc_fraction, full_cds_mfe_per_nt, mfe_5prime_48_kcal_mol, log_length_nt`; development results were frozen before test evaluation, and `functional_untouched` was not used.

On the frozen test set (**n = 634**), Spearman correlations were:

| Predictor | Test Spearman |
|---|---:|
| CAI | 0.0026 |
| GC fraction (direction selected on train) | 0.0964 |
| Full-CDS MFE | 0.0463 |
| Full-CDS MFE per nt | 0.0950 |
| 5′ 48-nt MFE | 0.0777 |
| Combined logistic | 0.1232 |

The combined model had Pearson **0.1508** and RMSE **2.0812**. Its point estimate exceeded the strongest single-proxy Spearman (directional GC) by **Δρ = 0.0268**, but the paired 95% bootstrap interval was **[-0.0627, 0.1140]** and the Holm-adjusted p-value was **0.9431**. No paired Spearman comparison survived Holm correction on test (minimum adjusted **p = 0.1798**). CAI alone was effectively uncorrelated (**ρ = 0.0026**).

The independent verifier recomputed all **6,348** CAI/GC/MFE rows, model predictions, **1,000 bootstrap replicates per split**, stratified metrics, and Holm correction; **9/9 checks passed**. The supported conclusion is therefore **limited and unstable cross-protein signal**, not a decisive failure of within-protein proxies. This diagnostic does not validate a fixed-protein synonymous mechanism, functional OOD gain, generator, or external-baseline ranking.

### 6.3 Incremental evidence for spatial coupling

[Pending RK-G1. Insert matched initiation, velocity, decay and pair-channel ablations with protein/study OOD and uncertainty.]

### 6.4 Cross-layer structure–translation–decay consistency

[Pending RK-G1. Connect MAGE fitness, Ribo velocity and Boël mRNA/protein outcomes; distinguish association from causation.]

### 6.5 Baseline execution and reproducibility status

**ID3 bounded official execution.** The fixed ID3 commit `ed23037e5a74ca10953954c425ac736fb89578a8` and DeepRaccess commit `1a37235e31e1d5a7d5e2bfb705e3a00f1cdcaa9c` were materialized, and the official `cpu_v4` quick-test preset was executed. The actual protocol was **1 protein × 3 constraints × 4 variants = 12 runs**, **2 iterations**, **1 seed**, and `enable_cai=false`. The official summary recorded **12 successful / 0 failed** runs in **417.591 s**. Independent verification finished at **112/116 checks**, and finalization passed **11/11 finalization checks** with final-sequence evidence ready for recording.

This is a smoke result, not the separate full-12×12 protocol and not a main comparison. Four checks were retained as failures: `CodonProfileConstraint.forward()` omits `beta` when calling `CodonPsiFunction.forward()`, and the `beta == 1.0` runner branch records a soft-path accessibility value as a discrete score. Consequently, CPC×1 initial/best/improvement/trajectory fields and affected summary aggregates are excluded. Only the bounded final sequences and final scores are retained.

**LinearDesign bounded official execution.** The clean codeload archive at commit `f0126ca89a8b853088b4bccfd2cc8c378d3678be` was built from source, and the official README example matched its documented sequence. On frozen 135-aa protein `C01H6.8b.1`, the official binary produced three unique synonymous outputs for λ = 0/0.5/1 in **24.322 s total**:

| λ | Official MFE (kcal/mol) | Official CAI | Wall time (s) |
|---:|---:|---:|---:|
| 0.0 | -270.60 | 0.761 | 8.063 |
| 0.5 | -269.20 | 0.791 | 8.109 |
| 1.0 | -265.20 | 0.820 | 8.151 |

Independent raw-output verification passed **10/10 checks** with maximum numeric delta **0.0**, and finalization passed **8/8 checks**. Official MFE matched ViennaRNA at 37°C with `dangles=0` (maximum rounding delta 0.000012); default `dangles=2` values were also retained. The earlier default-dangles v1 failure is preserved as `FAIL_INDEPENDENT_SCORER_CONVENTION_MISMATCH` rather than erased. This remains a single-record, three-λ bounded smoke, not the full seven-λ actual-set matrix, dense-budget comparison, functional OOD evaluation, or SOTA result.

**EnsembleDesign bounded official execution.** The fixed official commit `cd9324f9574a754063d421e76670bc9fd7555324` was built without source modification. The README example completed **3 records × 2 runs = 6 runs** with **4 unique CDSs** in **8.045 s**; the official sequences and reported EFE values matched:

| Record | Protein length (aa) | Best run | Official EFE (kcal/mol) |
|---|---:|---:|---:|
| seq1 | 17 | 1 | -18.00 |
| seq2 | 27 | 1 | -43.71 |
| seq3 | 33 | 2 | -70.29 |

The same bounded protocol then executed `C01H6.8b.1` (135 aa) for **2 runs**, producing **2 unique CDSs** in **52.651 s**. Best run 1 had official EFE **-269.97 kcal/mol** and CDS length **405 nt**; no extra terminal stop was appended. Independent raw-output and scorer verification passed **13/13** example checks and **13/13** C01 checks, both with maximum numeric delta **0.0**; finalization passed **11/11 checks**. The initial stop-contract wrapper failure remains preserved. EFE is not LinearDesign MFE, so these values do not authorize a direct cross-method ranking. No matched LinearDesign comparison, dense-budget evaluation, functional OOD result, or SOTA claim was produced.

**CodonTransformer bounded official execution.** The fixed source commit `4a447b01dab860feb81b647ff1ff88ad598517f4` and model revision `9744dcc920d813066391fc828d7a590207f148e8` were materialized with eight model files; `model.safetensors` has **358,342,232 bytes** and SHA256 `23994e1e7324e78c9d9da71040e8677c0a635287cf1c7c9ea5096b7eadc44dfd`. Four deterministic GPU inferences covered the official README example and `C01H6.8b.1` under both the official default and `match_protein=True` modes:

| Record | Mode | Protein (aa) | CDS including stop (nt) | Translation QC |
|---|---|---:|---:|---|
| official_example | official_default | 70 | 213 | PASS |
| official_example | match_protein | 70 | 213 | PASS |
| C01H6.8b.1 | official_default | 135 | 408 | PASS |
| C01H6.8b.1 | match_protein | 135 | 408 | PASS |

The official-example default output matched the README sequence exactly. Default and constrained modes each produced **2/2 legal synonymous CDSs**, with one terminal stop and no internal stop. The two modes returned identical sequences for each protein, giving **2 unique CDSs across four runs**; this is not evidence that the constraint option improves performance. Model loading took **4.439 s** and summed inference time was **2.033 s**, including first-call warmup; these are not time-matched baseline costs. Independent deterministic re-execution and raw-output verification passed **13/13 checks**, helper tests passed **8/8**, and finalization passed **10/10 checks**. This remains an official-example plus single-C01 bounded smoke, not a matched MFE/EFE comparison, dense-budget evaluation, main baseline matrix, functional OOD result, or SOTA claim.

**VeloHARMO bounded official execution.** At fixed commit `38b48079856aeb9d33a1b10844d77aa8f6640032`, the unmodified `VeloGRU/run.py test` used the official 105-dimensional feature path and E. coli fold-0 weights on seven deterministically selected short processed-matrix records. On CUDA it reported mean Pearson **0.604403** with population SD **0.172683**; direct native-prediction recomputation agreed within **1.49e-08**. These are length-selected diagnostics, not held-out or OOD performance. The unmodified GA entry point failed on the missing `Mimo_data` import; an exact seven-item compatibility patch changed only the import, data/weight/plot paths, population, and generation budget. On `C1P620` (36 codons), the CPU GA ran with population **8**, generations **2**, and seed **20261118**. Start and best sequences were **2/2 legal synonymous CDSs** under the native terminal-stop contract. Predicted-profile fitness was native **-0.025608**, start **0.345986**, and best **0.345986**; thus `best == start`, `best − start = 0.000000`, and **no iterative improvement occurred**. The start-to-native difference is only an initial-population/model-objective contrast, not experimental functional gain. Independent re-execution passed **17/17 checks** with maximum numeric delta **0.0**, unit tests passed **10/10**, and finalization passed **13/13 checks**. This is not five-species closure, a full-budget harmonization result, main baseline comparison, functional OOD evidence, or SOTA claim.

**RiboMIMO bounded official training.** At fixed commit `094c693d4df45f4b29f5a3209b31c452a39092a5`, the official training/cross-validation entry point ran on **20 shortest eligible Mohammad16 genes** with one repeat × two folds, two epochs, batch size 4, seed **20261118**, and CPU single-thread execution. Exactly six compatibility replacements preserve ragged arrays and restore numeric padding dtype; the model, optimizer, random gene split and training logic are unchanged. Across the two best-validation checkpoint test folds, R² was **-0.047131 ± 0.043792**, MSE was **2.298945 ± 0.296874**, and Pearson was **0.015289 ± 0.007515** (mean ± population SD). Both checkpoints contain **1,860,356 parameters**. Independent retraining exactly matched checkpoint tensors, while checkpoint-level metric recomputation passed **17/17 checks** with maximum numeric delta **4.10e-07** from six-decimal log rounding; finalization passed **13/13 checks**, and unit tests passed **10/10**. The unmodified NumPy ragged failure and post-ragged object-to-Tensor failure are retained. These small-subset values are execution diagnostics, not evidence of predictive utility or a method ranking. This is not the full 10-fold × 100-epoch protocol, homology/protein/study/functional OOD, a main-baseline comparison, or a SOTA result.

**iXnos bounded official prefix-read training.** At fixed commit `1ea2337dd24d1e6fa3859f08573e99f02512810f`, the first **1,000,000 complete reads** of ENA run `SRR1049521` (all 40 nt; a prefix, not a random sample) were processed with the official Weinberg linker trimmer, rRNA/noncoding-RNA filters, Bowtie transcriptome mapping, length/frame-specific P-site offsets, and simple uniform multimapping weights rather than RSEM. Trimming retained **864,464 reads**; **756,168** entered transcriptome mapping and **723,724** had at least one alignment. A total of **1,238 genes** met the bounded thresholds (minimum 50 counts and 20 codons with data); seed **20261118** selected **20 train / 10 test genes**. The official 760-feature tanh network with 200 hidden units ran for two epochs and produced **3,816 train / 1,963 test codons** and **152,401 parameters**. At the prespecified final epoch, test R² was **0.028272**, MSE **0.910627**, Pearson **0.195228**, and Spearman **0.215997**; the train-mean constant baseline had MSE **0.937122** and R² approximately zero. Independent reprocessing/retraining passed **27/27 checks** with exact targets and checkpoint tensors, prefix/trimmed FASTQs were byte-identical and Bowtie alignment multisets matched after canonical sorting (run-specific PG metadata excluded), finalization passed **16/16 checks**, and unit tests passed **10/10**. The initial headless-backend import failure is retained. These bounded values are execution diagnostics, not paper-performance estimates. This is not the full 102,187,657-read run, RSEM workflow, 333/167-gene 60-epoch protocol, functional OOD, main-baseline comparison, or SOTA result.

**ROSE complete released-test single-checkpoint inference.** At fixed commit `8b86d69d89ca7ef95193729e6d1a4738bc6a4451`, the two released `best_model_0.caffemodel` checkpoints were loaded without training into the official parallel-convolution networks. Each study used one full-array CPU forward pass over the author-processed 183-nt/61-codon test tensors, with the official ATCG nested codon encoding and official float32 two-exponent probability formula. Only HDF5 paths, TEST batch sizes and CPU execution settings were adapted; network weights and algorithms were unchanged.

| Study | Records (+/−) | Parameters | ROC AUC | AP | Accuracy@0.5 | Log loss | Full forward (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Pop14 | 1,902 (951/951) | 128,834 | 0.861889 | 0.859274 | 0.778654 | 0.498731 | 10.769 |
| Battle15 | 9,980 (4,990/4,990) | 265,858 | 0.807230 | 0.794068 | 0.728156 | 0.562374 | 95.194 |

Independent codon encoding, HDF5 construction, network adaptation and second Caffe forward passed **34/34 checks**: logits and independently recomputed official-formula probabilities were exactly equal, and every primary production metric had zero delta. Finalization passed **60/60 checks**, and unit tests passed **12/12**. Stable float64 probabilities were used only as a secondary rounding/near-tie robustness check. Three earlier verifier failures caused by overly strict float64 probability/metric tolerances are retained; they did not change the scientific outputs. These are complete released-array **binary ribosome-stalling classification** results, not continuous velocity regression, 100000-iteration training, a 64-checkpoint ensemble, raw-read/P-site remapping, protein/study/functional OOD, a matched-cost baseline comparison, or a SOTA result.

**RNARL fixed-source availability audit.** At public commit `88428e5d24fb2a16c29cc4dfbbfef51bd990a3d5`, exact entry-point smoke and independent AST checks passed **16/16 checks for a negative reproducibility result**. Actor and reward constructors do not match their public entry calls, the actor lacks the called evaluation method, and GRPO lacks **9 called methods** plus its main globals. No full training, generation, paper metric, or baseline comparison was produced. This finding concerns the current public snapshot's direct executability; it does not show that the RNARL scientific method is invalid.

**CDGB source-identity audit.** The candidate title `CDGB: a deep learning framework for codon de-optimization directed by the protein representation model` was assessed through **9/9 frozen scholarly/repository API queries** across Crossref, OpenAlex, Europe PMC, and GitHub; no exact scholarly title match was found. The DOI embedded in the candidate URL, `10.1093/bib/bbaf332`, instead resolves to `Multimodal zero-shot learning of previously unseen epitranscriptomes from RNA-seq data` in Briefings in Bioinformatics volume 26 issue 4. The exact GitHub CDGB+codon and CDGB+protein-representation repository queries each returned zero records; the broader codon-deoptimization query returned 14 unrelated candidates and does not establish official ownership. Independent verification passed **8/8 checks**, and finalization passed **6/6 checks**. No official CDGB repository, immutable commit, build, execution, output sequence, or performance result was established. This bounded source audit is not evidence that the CDGB method is invalid or that no implementation exists.

The unified main-baseline matrix, dense candidate-budget comparison, functional OOD evaluation, and SOTA assessment remain pending.

### 6.6 Mechanistic ablations and failure boundaries

[Pending RK-G2. Require concordance between predictive and generative ablations and retain negative strata.]

### 6.7 Untouched generalization and time-matched performance

[Pending RK-G3. Report untouched proteins/studies, length/GC/homology strata, available hosts and complete costs.]

### 6.8 Independent functional validation

[Pending. Retrospective held-out measurements first; prospective design–build–test–learn results only when actually completed.]

## 7. Discussion

The intended scientific contribution is a testable explanation of when synonymous function depends on spatial coupling among RNA structure, translation dynamics and transcript decay. The model is a consequence of that explanation, not its starting point. If initiation accessibility dominates one assay, codon content dominates another, or velocity profiles fail to transfer across studies, those differences define biological boundaries rather than inconveniences to be hidden.

A computational Pareto improvement is also distinct from biological improvement. Strong performance on CAI, MFE, GC or a learned functional surrogate does not by itself establish expression, stability, safety or efficacy. Claims will therefore be limited to the data layer actually evaluated. Prospective experiments with wild-type and strong algorithmic controls are required for a top-journal functional conclusion.

## 8. Reproducibility Statement

Every result must link to its run ID, code and dirty-diff hash, environment, raw/clean data and split hashes, checkpoint, complete configuration, seeds, original measurements or sequences, evaluation script and artifact hash. Candidate datasets and planned experiments remain explicitly marked. Failed baselines, partial outputs, negative strata and unavailable costs are retained rather than converted to zero or removed.

### 8.1 A8-RK evidence anchors

The working-manuscript values above were rendered from the following frozen artifacts. Large CSV, prediction, and weight files remain outside Git under the project artifact root; their report-level hashes are recorded here.

| Evidence | SHA256 |
|---|---|
| RK02 functional long table | `c436b758369018fe0fd121ce6e741993e90a5de80b4706ab87082f7557b6a377` |
| RK04 split assignment table | `1ea0ff63b7f5e820abca3842b690cba0ffdfbc8b5f3f7fe4bf88a25efb94c0f8` |
| RK07 frozen result | `2ba7b1dc084172e891c8d5775790b7c94ddbca8788d8a88bbb0876f6fd289838` |
| RiboMIMO independent verifier | `256bf64fd5c51fd3c66b078339bb425fd718a3476afcf3b09de6dfea5de78ba7` |
| CodonTransformer raw table | `b319f975f4cd9814bf111a59b80000c001987abf33f3e52e77c4d96d434b4fa9` |
| ID3 independent verifier v2 | `03980d217794fcb57511be368a7f90e5f34ac0209cc4f3294ad3818ffcd3c7ae` |
| LinearDesign independent verifier v2 | `928d9cabaa906737cfffa2caa6125e67b65baccd21028c56947b5a53e5be469e` |
| LinearDesign finalization | `9a5e7e92c9578e4eda1f18774a8a21de2c8abc6bfda076f3ccafcc0a8fe61f79` |
| LinearDesign v1 retained failure | `6825a4a0326fe171cf18906acf2ecb0d6b224d10f91d6cd4d6a1e7f08195c4ca` |
| EnsembleDesign example production | `eb86291b020da35c2338715d37803882f1a05e9fe0631077e3cd20159e023e18` |
| EnsembleDesign C01 production | `b72d17ee16f4afe148430f735ee65cecbf8728fb7b98ddac23469937ee0a98b9` |
| EnsembleDesign example independent verifier | `b6c24a7f94ef5786cd3fe11a2c802bde79ea3318539279f88fb4335b4fe2a1d7` |
| EnsembleDesign C01 independent verifier | `bf73ff5156526f55e5882e94d16f511293db4421b23afca7cb38c816cbab34dd` |
| EnsembleDesign finalization | `226cf4b15b0bdfac35a846941fc17986e5f1f3a76851ed33e106946d8b8a4fde` |
| CodonTransformer materialization | `91ab29709fadcb3b75e78d779c5b03be9bb093b1e337f981a63cba7cefa90501` |
| CodonTransformer bounded production | `cbfdfeca06fdd061d0d0a09b0a57dbf614bf3b864d8554b759812d35bc6a96b1` |
| CodonTransformer independent verifier | `c9fb748bacafe6e57a548dcb0f93e882962c8605757d526b404d27e620e64d31` |
| CodonTransformer finalization | `39a02033837ca1a7c9afa79ec928b6e0167da9a674654b3e7a0a214b2ec101ac` |
| CDGB source audit | `dd8f0a8840bbf655d2731a60b7c5e7fb296665a29f4e7eb229edbc43e1e3f691` |
| CDGB independent verifier | `964e782264c8101dc55cced708be3834f66b02488f3bc0e838b8724ce4598980` |
| CDGB finalization | `dc49cdc6540d9f45f2cd040518e660871fc3b0dc109e929f92f7a541e4df66b2` |
| RNARL negative audit | `065215732f57a601431949220a4f4a25e7219d5f0cf7b22e3064288c87fdb47b` |
| RNARL full QC finalization | `42cf321c1a67082dfe526a71f3f93871ab440b5c9989357fa83f565f0aabd767` |
| RNARL corrected independent verifier | `a4064edc98a29379d7412b7e5aa73dba038efc722f6b831e3342948db8ca881c` |
| VeloHARMO E. coli matrix | `71008f948597daff282ccb3e124dd7e4c5b35aa92e2dbe4af43d5725d6fa740f` |
| VeloHARMO finalization | `faef939f00649d625fa23e98cc3d213e8488311d91bc601af3ef1f13d0c201a3` |
| VeloHARMO independent verifier | `d3bf3b05fabc58ceb745e803e64baa464c4eaafae808defa64010f07e20b528a` |
| VeloHARMO bounded official production | `9713e5d2cb6a7bd041f1abd0c6f1083e435f63193b99737b3d9e1e3c41225cb5` |
| VeloHARMO bounded independent verifier | `ca18a827ceab5b36fc76904e2b64c98e545cc0e699024bbe0fdae2ddc192c873` |
| VeloHARMO bounded finalization | `c056cc6207a15d74403926c676010a0fae50d7f7a215cb0ab19ce1fd40e609c5` |
| RiboMIMO bounded official production | `ce79120bef6f25aefcd9e3b5e440c764a300f78c6da3d6cecd01c9f55bf4a9b6` |
| RiboMIMO bounded independent verifier | `d97874904cca4b4e1589ee4eb4daac482450762c7b9d8dee840c0756eb443195` |
| RiboMIMO bounded finalization | `69c532e20612b7d8de83486f7c2ced7961ac416f7c3e5218946f2804956407d8` |
| iXnos bounded official production | `5393c5d4738031518c57c1f889b0db70109c7a626b9a6ebf8d11b2ec703bdd30` |
| iXnos bounded independent verifier | `2b7fe05d788df6474430d228ac8e597bf4aba58892f279e54a869322d1ae40cc` |
| iXnos bounded finalization | `a3fb63540d59e5f76cebcbea555bf1a4c063b19c4d3917e48304c94ef3ab1c28` |
| ROSE frozen single-checkpoint protocol | `549f9ccc268659573ef1f878611bce184090ba26b97ebe8410400dafc05e0a83` |
| ROSE complete released-test production | `03cacac5d8378bc9120fc48c78a7bc52bb24e83314543e82a03058d121194d0a` |
| ROSE independent verifier v4 | `904d370e0b6c87c86484a74c2b572dca964bdc5289110a1d37d00e4a3d378861` |
| ROSE finalization | `c1733d1c937af26892fbfebf6385bcd9ca80b9825bd07f7597e7188716d48817` |
| ROSE retained verifier failure v1 | `705fabeaa1ce70c57d0b17a3f9f7b41a02211cc5e3be8f5078a672020cf0df39` |
| ROSE retained verifier failure v2 | `9faeecabeb83b099554e2049e6b1e2f7eb33cef5d97068f3d1077ed3dd528425` |
| ROSE retained verifier failure v3 | `0b05ef4782b844544511d9c4b81be4f3bb3abd50e64025f39cf0d480c8a22f87` |

A7 is retained as the prior manuscript snapshot. This A8 file remains a **non-submittable working manuscript** until the mechanism, main model, actual-set baselines, OOD, clean-environment reproduction, and prospective validation gates are complete.

## 9. References

Bian, B., et al. VeloHARMO: a deep learning framework for mRNA coding sequence generation and design via translation velocity harmonization. *Briefings in Bioinformatics* (2026). https://pmc.ncbi.nlm.nih.gov/articles/PMC13647270/

Boël, G., Letso, R., Neely, H., et al. Codon influence on protein expression in E. coli correlates with mRNA levels. *Nature* (2016). https://doi.org/10.1038/nature16509

Chen, T., Zhang, Y., and Chatterjee, P. Multi-Objective-Guided Discrete Flow Matching for Controllable Biological Sequence Design. *arXiv:2505.07086* (2025).

Chen, T., Zhang, Y., and Chatterjee, P. AReUReDi: Annealed Rectified Updates for Refining Discrete Flows with Multi-Objective Guidance. *arXiv:2510.00352* (2025).

Chen, T., Holsman, M., Zhao, L., and Chatterjee, P. pCoMole: Pareto-Constrained Molecule Editing with Discrete Flows. *arXiv:2610.01663* (2026).

Dai, N., Zhou, T., Tang, W.-Y., et al. EnsembleDesign: messenger RNA design minimizing ensemble free energy via probabilistic lattice parsing. *Bioinformatics* (2025). https://doi.org/10.1093/bioinformatics/btaf245

Fallahpour, A., Gureghian, V., and Filion, G. J. CodonTransformer: a multispecies codon optimizer using context-aware neural networks. *Nature Communications* (2025). https://doi.org/10.1038/s41467-025-58588-7

Kelsic, E. D., Chung, H., Cohen, N., Park, J., Wang, H. H., and Kishony, R. RNA Structural Determinants of Optimal Codons Revealed by MAGE-Seq. *Cell Systems* (2016). https://doi.org/10.1016/j.cels.2016.11.004

Kim, J., Kim, J., Lee, J. W., et al. Enhancing protein expression in humans through codon optimization with transformer and contrastive learning. *Molecular Therapy Nucleic Acids* (2026). https://doi.org/10.1016/j.omtn.2026.102991

Kudla, G., Murray, A. W., Tollervey, D., and Plotkin, J. B. Coding-sequence determinants of gene expression in Escherichia coli. *Science* (2009). https://doi.org/10.1126/science.1170160

Laajil, A., et al. Curriculum-Augmented GFlowNets For mRNA Sequence Generation. *arXiv:2510.03811* (2025; v2 2026). https://arxiv.org/abs/2510.03811

Li, H., Terai, G., Otagaki, T., and Asai, K. Gradient-based optimization for mRNA sequence design. *Bioinformatics* (2026). https://doi.org/10.1093/bioinformatics/btag667

Lin, S., Tan, H., Wang, K., et al. RNARL: reinforcement learning-driven unified generative framework for multi-objective RNA codon design. *Genome Biology* (2026). https://doi.org/10.1186/s13059-026-04203-x

Patel, S., Tang, S., Kim, Y., et al. mRNAutilus: Multi-Objective-Guided Discrete Generation of mRNA with Optimized Therapeutic Properties. *arXiv:2605.31296* (2026).

Rajbanshi, B., and Guruacharya, A. codonGPT: reinforcement learning on a generative language model enables scalable mRNA design. *Nucleic Acids Research* (2025). https://doi.org/10.1093/nar/gkaf1345

Shao, Z., Wang, T., Shen, Y., Huang, T., and Xiao, Y. ProMORNA: An End-to-End Generative Framework for Full-Length mRNA Design. *arXiv:2605.01513v2* (2026).

Theodorou, E., Stadler, M., Gustafsson, C., and Welch, M. Machine learning method for optimizing coding sequences in mammalian cells. *Biology Methods and Protocols* (2026). https://doi.org/10.1093/biomethods/bpag057

Zhang, H., Zhang, L., Lin, A., et al. Algorithm for optimized mRNA design improves stability and immunogenicity. *Nature* (2023). https://doi.org/10.1038/s41586-023-06127-z

Zhang, H., Liu, H., Xu, Y., et al. Deep generative models design mRNA sequences with enhanced translational capacity and stability. *Science* (2025). https://doi.org/10.1126/science.adr8470
