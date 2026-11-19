# Learning structure–translation–decay coupling for synonymous mRNA design

> **Status: A8-RK working manuscript — not for submission.** Verified data, operational split, sequence-OOD proxy models, bounded cross-protein diagnostics, and bounded baseline-execution audits are recorded; core mechanism, main model, main baseline matrix, remaining OOD, generator, and wet-lab closure remain incomplete. No SOTA claim.

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

**RK04 sequence-OOD proxy experiment.** Length and GC thresholds were computed only from the original training rows at the 5th/95th percentiles; any out-of-range member moved its entire operational cluster into sequence-OOD. The resulting retained train/dev/test partitions contained **4,019/503/490 rows** and **3,561/447/436 clusters**, respectively; sequence-OOD contained **1,336 rows / 1,110 clusters**. All **19,072 MAGE functional-untouched rows** remained excluded from feature computation, fitting and evaluation. The split and train-only normalization passed **37/37 independent checks** and **11/11 finalization checks**.

We fitted five frozen model families with 17 candidates: a training-weighted constant, GC-only ridge, basic-sequence-feature ridge, all-proxy-feature ridge, and all-proxy-feature histogram gradient boosting. Model fitting used retained train only; dev cluster-balanced MSE selected one candidate per family and then the overall primary family. Test and sequence-OOD were not used for selection, and no train+dev refit occurred. The selected primary was `ridge_all(alpha=100)` with dev cluster-balanced MSE **3.725576**. Final metrics were:

| Family | Test Spearman | Test R² | Test CB-MSE | OOD Spearman | OOD R² | OOD CB-MSE |
|---|---:|---:|---:|---:|---:|---:|
| constant | null | -0.004095 | 4.400064 | null | -0.057252 | 4.388894 |
| ridge_gc | 0.119209 | 0.011011 | 4.338435 | 0.071873 | -0.050378 | 4.378262 |
| ridge_basic | 0.124036 | 0.009743 | 4.292031 | 0.203876 | -0.009653 | 4.211838 |
| **ridge_all (primary)** | **0.144896** | **0.015979** | **4.257835** | **0.217873** | **0.011709** | **4.114318** |
| histgb_all | 0.203076 | 0.037747 | 4.207758 | 0.219383 | 0.032386 | 3.989950 |

For the dev-frozen primary relative to dev-selected GC-only, paired operational-cluster bootstrap with 1,000 replicates gave a retained-test Spearman difference of **+0.025687** (95% CI **[-0.066372, 0.119629]**) and CB-MSE difference of **-0.080600** (95% CI **[-0.233242, 0.078749]**); both intervals cross zero. On sequence-OOD, the corresponding differences were **+0.146000** (95% CI **[0.103896, 0.189857]**) and **-0.263944** (95% CI **[-0.374981, -0.144076]**), with both intervals excluding zero. HistGB's higher retained-test Spearman is retained as a secondary-family result and was not used to replace the dev-frozen primary post hoc. Two complete runs produced identical prediction, metric and selection hashes; independent metric/model-forward verification passed **40/40 checks** with maximum prediction delta **0.0**, finalization passed **18/18 checks**, and unit tests passed **12/12**. The initial schema failure, an incomplete multithreaded run, and the earlier constant-prediction floating-point correlation artifact are preserved; the correction did not change model selection, nonconstant results, or primary comparisons. These data establish a limited nonsynonymous cross-protein proxy signal on this sequence-OOD construction, with low absolute R². They do not establish fixed-protein synonymous mechanisms, same-backbone mechanistic increments, CodonFlow-RK generator readiness, functional-untouched performance, prospective experimental validity, or SOTA.

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

**RiboMIMO full Mohammad16 official cross-validation.** The four author-processed matrices first passed the official-loader preflight with **8,124 eligible records**; this loader count is distinct from the RK03 clean-QC total of 8,109 and the two QC conventions are not interchanged. For Mohammad16, the complete matrix contained **1,761 raw / 1,179 eligible genes**. The fixed official commit `094c693d4df45f4b29f5a3209b31c452a39092a5` executed **one repeat × ten folds, maximum 100 epochs, early stopping 5, batch size 16, seed 1234, and nucleotide+amino-acid features** on an NVIDIA GeForce RTX 5090. Seven runtime-only compatibility replacements preserve ragged arrays, numeric padding dtype and the modern PyTorch CPU-length requirement; model, optimizer, split and training logic are unchanged. The failed first run caused by CUDA `pack_padded_sequence` lengths is retained as `FAIL_OFFICIAL_TRAINING`.

| Fold | Best-validation epoch | Test R² | Test MSE | Test Pearson |
| --- | ---: | ---: | ---: | ---: |
| 1 | 11 | 0.483876 | 1.582514 | 0.696269 |
| 2 | 18 | 0.466452 | 1.522663 | 0.684214 |
| 3 | 7 | 0.453272 | 1.578519 | 0.674002 |
| 4 | 8 | 0.494533 | 1.473072 | 0.703510 |
| 5 | 12 | 0.474101 | 1.848635 | 0.689403 |
| 6 | 9 | 0.470739 | 1.632978 | 0.691442 |
| 7 | 11 | 0.441199 | 1.519269 | 0.678463 |
| 8 | 15 | 0.476994 | 1.559496 | 0.693165 |
| 9 | 9 | 0.478642 | 1.537437 | 0.696867 |
| 10 | 11 | 0.488929 | 1.660116 | 0.699465 |

Across the ten best-validation checkpoint test folds, R² was **0.472874 ± 0.015274**, MSE was **1.591470 ± 0.100361**, and Pearson was **0.690680 ± 0.008882** (mean ± population SD). An independent post-hoc constant predictor using only each training fold's mean density gave R² **-0.000001 ± 0.000002** and MSE **3.021991 ± 0.213861**; this is a train-only reference, not an official output or a unified baseline matrix. Every eligible gene occurred in exactly one test fold. A second complete deterministic 10-fold training run produced bitwise-identical checkpoint tensors for all ten folds and identical six-decimal metrics. Independent two-pass checkpoint inference passed **94/94 checks**, finalization passed **425/425 checks**, and unit tests passed **10/10**. This closes only the official random-gene CV protocol on Mohammad16. Full training on Subtelny14, Mohammad19-1 and Mohammad19-2, homology/protein/study/functional OOD, publication-metric reproduction, the unified-cost baseline matrix, CodonFlow-RK comparison and SOTA assessment remain pending.

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

The RK04 length/GC sequence-OOD partition has now been evaluated under the dev-frozen proxy-model protocol in Section 3.2: `ridge_all` improved over GC-only on sequence-OOD with bootstrap intervals excluding zero, whereas the retained-test intervals crossed zero and absolute R² remained low. This is a cluster-disjoint nonsynonymous proxy result, not functional-untouched or fixed-protein synonymous evidence. The **19,072 MAGE functional-untouched rows** remain unevaluated, and no time-matched CodonFlow-RK generator comparison has been performed. Other protein/study/host OOD and complete-cost results remain pending RK-G3.

### 6.8 Same-backbone mechanism-channel ablation on Boël sequence-OOD

We next tested whether the four information channels improved functional prediction under the frozen Boël sequence-OOD protocol. The retained train, development, and test partitions contained 4,019, 503, and 490 constructs, respectively; sequence-OOD contained 1,336 constructs from 1,110 operational protein clusters. The all-channel and no-channel models had identical architectures, 4,997 parameters, optimization settings, and dense attention computation. Only channel gating differed. Model selection used development cluster-balanced mean squared error (CB-MSE), without test or OOD selection. Training took 71.0446 seconds for the all-channel model and 67.2221 seconds for the no-channel model on the same RTX 5090, with 2,103 forward passes per run including development and final evaluation.

**Table 1**

*Functional Prediction Performance on Boël Sequence-OOD*

| Model | CB-MSE | Spearman | Row R² |
|:---|---:|---:|---:|
| RiboKinetic all channels | 4.088746 | 0.192094 | 0.010313 |
| RiboKinetic no channels | 4.364834 | -0.006922 | -0.052326 |
| GC-only ridge | 4.378262 | 0.071873 | -0.050378 |
| Full-proxy ridge (development-selected primary) | 4.114318 | 0.217873 | 0.011709 |
| Full-proxy HistGB (descriptive comparator) | 3.989950 | 0.219383 | 0.032386 |

*Note.* CB-MSE denotes cluster-balanced mean squared error; lower values are better. Spearman and row R² were computed on the same 1,336 OOD constructs. The full-proxy ridge remained the development-selected primary baseline. A separate retrospective paired diagnostic against HistGB is reported below and does not replace the preregistered gate or select a new primary model.

Paired cluster bootstrap with 2,000 resamples supported an increment over the same-backbone no-channel model. The all-minus-none difference in Spearman was 0.199016 (95% CI [0.129283, 0.266863]), and the difference in CB-MSE was -0.276089 (95% CI [-0.377439, -0.180840]). Relative to GC-only ridge, the corresponding differences were 0.120221 (95% CI [0.082462, 0.157406]) for Spearman and -0.289516 (95% CI [-0.350624, -0.225776]) for CB-MSE. Both intervals excluded zero in the direction favoring the all-channel model.

The all-channel model did not outperform the full-proxy ridge on either OOD endpoint. Its Spearman difference was -0.025779 (95% CI [-0.071103, 0.019376]; Holm-adjusted p = 0.522), and its CB-MSE difference was -0.025572 (95% CI [-0.124069, 0.076207]; Holm-adjusted p = 0.595). Thus, the preregistered RK-G1 criterion was not met. The low absolute R² values and the more favorable HistGB point estimates further preclude an SOTA or broad superiority claim.

**Retrospective HistGB fairness diagnostic.** The frozen HistGB predictions had been computed but omitted from the original paired gate. Without refitting, changing splits or selecting a checkpoint, we therefore added the all-channel-minus-HistGB comparison and explicitly label it retrospective rather than preregistered. On sequence-OOD, the Spearman difference was **-0.027289** (95% CI **[-0.090520, +0.032626]**; Holm-adjusted p = 0.405), and the CB-MSE difference was **+0.098795** (95% CI **[-0.050971, +0.252057]**; Holm-adjusted p = 0.396). HistGB retained the more favorable point estimates, but both intervals include zero: neither a mechanism advantage nor a statistically resolved HistGB win is supported. The original RK-G1 remains false. Independent raw-input verification passed **84/84 checks**, finalization passed **33/33 checks**, and the retained functional-comparison tests passed **7/7**.

These results support a limited inductive-bias interpretation: the four channels improved the shared backbone relative to no channels and GC-only regression, but did not establish superiority over the full proxy set. This experiment used cross-protein, nonsynonymous constructs and function-only supervision. It therefore does not validate fixed-protein synonymous mechanisms, and the initiation, velocity, and decay outputs are not validated mechanism-specific estimates. An independent occupancy-derived velocity-proxy analysis is reported in Section 6.9; it did not pass its preregistered Subtelny14 transfer gate. Neither experiment authorizes expensive generation training. Two complete retraining runs were bitwise identical, while independent verification passed 224 of 224 checks and finalization passed 48 of 48 checks. Clean-environment reproduction remains outstanding.

### 6.9 Occupancy-derived velocity proxy: in-study fit did not transfer to Subtelny14

To test the velocity channel with direct supervision rather than function-only pooling, we used the frozen RiboMIMO author-processed normalized ribosome-density matrices. The target was `-log1p(normalized density)`, an **occupancy-derived elongation-speed proxy**, not a physical velocity measurement. The first codon and stop codon were masked. Of 8,109 clean records, 321 exceeded the frozen 1,002-codon limit, leaving 7,788. Mohammad16 was split by deterministic record-ID hash into 933/110/123 train/dev/test transcripts. Subtelny14 contributed 3,630 transcripts and had zero exact CDS overlap with any Mohammad16 split; this is exact-CDS-disjoint study/species OOD, not homology-cluster OOD.

The 24,933-parameter RiboKinetic model and the codon/relative-position/length ridge used identical observed positions. Checkpoint selection used only Mohammad16 development transcript-balanced MSE and selected epoch 16. Test and all study-OOD partitions were excluded from fitting and selection.

| Partition | Transcripts | RiboKinetic TB-MSE | Ridge TB-MSE | RiboKinetic mean within-transcript r | Ridge mean within-transcript r |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mohammad16 dev | 110 | 0.191465 | 0.233787 | 0.446130 | 0.144838 |
| Mohammad16 test | 123 | 0.193081 | 0.234951 | 0.442167 | 0.148476 |
| Mohammad19-1 study-OOD | 1,412 | 0.214932 | 0.184495 | 0.024393 | -0.089449 |
| Mohammad19-2 study-OOD | 1,580 | 0.211918 | 0.184970 | 0.057341 | -0.058339 |
| Subtelny14 study/species-OOD (primary) | 3,630 | 0.230569 | 0.175946 | -0.008845 | 0.061698 |

On the preregistered Subtelny14 primary endpoint, the model was worse than ridge on both criteria. The model-minus-ridge TB-MSE difference was **+0.054623** (95% CI [+0.054046, +0.055192]), and the mean within-transcript Pearson difference was **-0.070543** (95% CI [-0.073248, -0.067765]). Both empirical Holm-adjusted p-values were 0 across 2,000 transcript-bootstrap resamples. Therefore `velocity_mechanism_pass=false`.

The within-study Mohammad16 test improvement is descriptive and does not rescue the primary endpoint: model/ridge TB-MSE was 0.193081/0.234951, and mean within-transcript Pearson was 0.442167/0.148476. On Mohammad19-1/2, the model had higher mean within-transcript Pearson but worse TB-MSE than ridge, so these overlapping-CDS study transfers are not robust wins. The primary negative result is retained without post-hoc model tuning.

Two complete training runs produced bitwise-identical checkpoints and prediction files. Independent raw-source verification passed **26/26 checks**, and finalization passed **12/12 checks**. This closes reproducibility of a negative velocity-proxy experiment only. It does not close RK-G1, functional transfer, cross-head mechanism consistency, physical velocity validation, homology OOD, generator readiness, SOTA or wet-lab validation; expensive generation remains unauthorized.

### 6.10 Independent functional validation

[Pending. Retrospective held-out measurements first; prospective design–build–test–learn results only when actually completed.]

### 6.11 Minimal CodonFlow-RK mathematical kernel: exact small-state verification

Before any model training, we froze and tested the legal codon simplex and conditional kernels. A state has 64 slots per position, index 63 is the terminal stop, and internal positions may use only the 61 sense-codon indices. A feasible transition is either a no-op or one internal sense-codon replacement. The base conditional is uniform over its feasible support; preference and remaining-budget terms only reweight or mask that support. On the frozen length-four example, exhaustive enumeration produced **226,981 valid states**, **181 one-step targets**, and **10,981 states reachable within two transitions**. Exhaustive rejection recovers the exactly uniform feasible-set distribution, whereas the naive two-step random walk has total-variation distance **0.324196450320** from that uniform endpoint reference.

For the length-three path example, all **14,641 paths** and **3,721 endpoints** were enumerated. Including the target endpoint mass in the backward path law makes the forward/backward log-probability ratio telescope to `log U(end) - log q_T(end)`. Maximum backward-normalization, path-telescoping and endpoint-reconstruction errors were **2.665e-15**, **8.882e-16**, and **5.963e-19**, respectively. The event-time transform `t = 1 - u^(1/kappa)` was checked against its inverse CDF; its analytic mean is `1/(kappa+1)`, not `kappa/(kappa+1)`. Production checks passed **22/22**, an independent implementation that did not import the production module passed **16/16**, finalization passed **14/14**, and **10 unit tests** passed. The initial 19/22 production failure (missing endpoint mass and reversed event-mean formula) and the independent 15/16 mask failure are retained with the corrected reports.

This is a **mathematical-kernel verification only**. It is not trained CodonFlow-RK, functional or generation performance, a mechanistic increment, RK-G1 closure, SOTA, or authorization for expensive generation training.

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
| RiboMIMO full four-matrix loader preflight | `3e9aa641c0db581fceb65075ee6ef3ed2a352fcdf8cfbbd97eb313452414e6e0` |
| RiboMIMO full Mohammad16 frozen protocol v2 | `a608e4280e6dd801ba06bf78df83576d2d359c49c379f94f4f8f5896f5171cc7` |
| RiboMIMO full Mohammad16 retained v1 failure | `8da5d10b71bd81e6c55cd0d58cce339d3b4d41541bbe0b87948de4a6bd3cbaee` |
| RiboMIMO full Mohammad16 production | `47e1a2c44e007c6413eb66efa9bd83a352745241ddcc9823b2c508ac1d292340` |
| RiboMIMO full Mohammad16 deterministic retrain | `f75fe699c25a31d1297a8b1f871d6e3819d74e10d0d91d0d8da1ce0e2a3db028` |
| RiboMIMO full Mohammad16 independent inference | `4bf2371923622ca247e4b51ccb3857a9512897f8a6dcae4b11ac3c96a3c01f4e` |
| RiboMIMO full Mohammad16 finalization | `890ef31a7bc716a9307ded9430de12b935629b8836a378ad571fa79c00624965` |
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
| RK04 sequence-OOD split CSV | `b9e29eac8eeb0adc46101d81ae8f2afa650eb3d5a37722b065e052fc669e45c6` |
| RK04 train-only normalization | `a1b2bc158a2669d8cf5db0f6f2ea26c26913a2203ed5e86ca020497458b210db` |
| RK04 sequence-OOD model protocol | `e52ed045c1fa2cf890d67f752c72a208b90220dd99be2e262501e67a7b81d926` |
| RK04 sequence-OOD model summary | `173549549c39be716b83554ba91402cfed3e496ec565255a855457f9eff79979` |
| RK04 sequence-OOD model independent verifier | `ebd1e96d3895f04f9168bbf9f39f72564324c5e853abd3a4c6c74aa7b26d63a6` |
| RK04 sequence-OOD model finalization | `5a15ae17dfbb282ab97aa954c6eaad40d064ec2251d2d080b1e7b1554e220b94` |
| RK04 sequence-OOD model deterministic retrain | `d0deb3fbe27c32afcaeb4c7ef04c8cedaab15679690d8b98f1276166328b4501` |
| RK04 sequence-OOD model predictions | `925d848d1d3fda2e2451fd383f2609a5419d691f7e24c7ea724c964c877c9e75` |
| RK04 sequence-OOD model metrics | `84b3b2068ed68a96bbbe3694509c26c9043a3d66be4d503ee805bca52e83bd34` |

| RK08 full comparison summary | `ff97cc8ae4093ac24fe475d30bce2db6707c2635d9de572286c1f69d9f8579cb` |
| RK08 full independent verifier | `190b7f93ccecc393d6f1b5846c78f8be176d72e9597593e74d61edc9bde060fa` |
| RK08 full finalization | `47a52e28816fa4524e0b124ee4ea705a079edeb3bbf4a809b6686e6e91eb83e2` |
| RK08 full artifact manifest | `dce4cbc03c826124de3706222bd844495250fc3da19a2ef42512043124c16f4b` |
| RK08 HistGB diagnostic summary | `0b321d71dfa4ff183b0d013531b5bfdbe168cf39d4e847b21f504d3ac6ee401a` |
| RK08 HistGB diagnostic independent verifier | `c20899713fb4dba7865dca481bda2d8b58356eb6d411b65d5ee7705a541884ce` |
| RK08 HistGB diagnostic finalization | `3a48f0571dfae2f4c7edbbf955cdc1ff9e3d061bac3b6747269e9c28817e68b9` |
| RK08 all-channel checkpoint | `7e581b2b49fd4f4aba723ce497e6f3369acb7ed54f278c6b377fef37a6417c61` |
| RK08 no-channel checkpoint | `aa54bfc78ce3a50e70302ae0530a0be29656514988bddab051527a912c73dee7` |
| rk08_velocity_data | `61ced22f2f077fa4e89b25c5b48ddf4730630e9f1bd01a58b22463879f1d89d9` |
| rk08_velocity_protocol | `cd5dc89ef5865e11cc11e7378a0d016e8dd0e791015355e3af556850a271298e` |
| rk08_velocity_production | `235201ea570fb5fccaf99c51259247a0e4428e4e9ea11a09946a0b491f3f9ddc` |
| rk08_velocity_retrain | `cc0559be2a84d1556c24a389cd56d7321f4fa7ee4acc653af0eefdfba1161495` |
| rk08_velocity_independent | `a1e2e5ea78f3fe9d5bbaf3081dd0957045491388dbcf033ea7673f06bc361340` |
| rk08_velocity_finalization | `ac8b87ae2bf56c2deba7ac7078d62c737df469228189cf931e25b6db3ce87062` |
| RK09 minimal-kernel protocol | `4b59194ad55699274a123cd662e6c4eb1d3b583068e0c7b027aabd27b5e15822` |
| RK09 minimal-kernel production | `dfeb60b4139d97e888ebc0f06385ea038c1c6f671d1445110ee3b14874247cbd` |
| RK09 minimal-kernel independent verifier | `0c54db32ad2c19bf4b8d3e16b9da955a57555e2ccbf407150d56909fceccc960` |
| RK09 minimal-kernel finalization | `a683fc72d123314baa27ffd2d692a8dfed0d2556a7466d90044b3dced9425ef0` |
| RK09 retained initial production failure | `6cd9e801b792f91694cf34125b29d865c747f1f5682669c6037a0533f784fede` |
| RK09 retained initial independent failure | `d988a3ee7bd773d0eb1d8e653a07633a561e6ee8d9659e188556eee6e3b0a5df` |

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
