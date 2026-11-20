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

Across the ten best-validation checkpoint test folds, R² was **0.472874 ± 0.015274**, MSE was **1.591470 ± 0.100361**, and Pearson was **0.690680 ± 0.008882** (mean ± population SD). An independent post-hoc constant predictor using only each training fold's mean density gave R² **-0.000001 ± 0.000002** and MSE **3.021991 ± 0.213861**; this is a train-only reference, not an official output or a unified baseline matrix. Every eligible gene occurred in exactly one test fold. A second complete deterministic 10-fold training run produced bitwise-identical checkpoint tensors for all ten folds and identical six-decimal metrics. Independent two-pass checkpoint inference passed **94/94 checks**, finalization passed **425/425 checks**, and unit tests passed **10/10**. This closes only the official random-gene CV protocol on Mohammad16. The three remaining matrices are completed in the four-matrix extension below. Homology/protein/study/functional OOD, publication-metric reproduction, the unified-cost baseline matrix, CodonFlow-RK comparison and SOTA assessment remain pending.

**RiboMIMO complete four-matrix official cross-validation.** All four author-processed matrices have now completed the same official **1×10-fold / maximum 100 epochs / early-stop 5** random-gene protocol. The combined input is **15,669 raw records / 8,124 official-loader-eligible genes**, with **2,520,180 valid masked test codons**. The eligible count remains distinct from RK03 clean QC=8,109.

| Dataset | Raw / eligible genes | R² mean ± SD | MSE mean ± SD | Pearson mean ± SD | Train-mean baseline R² / MSE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Subtelny14 | 5,614 / 3,921 | 0.397451 ± 0.012483 | 0.592620 ± 0.020862 | 0.631848 ± 0.010285 | -0.000001 / 0.983330 |
| Mohammad19-1 | 4,147 / 1,426 | 0.461595 ± 0.011718 | 0.433084 ± 0.015037 | 0.682075 ± 0.008264 | -0.000005 / 0.804335 |
| Mohammad19-2 | 4,147 / 1,598 | 0.484536 ± 0.030081 | 0.442863 ± 0.054396 | 0.696258 ± 0.021998 | -0.000003 / 0.856575 |
| Mohammad16 | 1,761 / 1,179 | 0.472874 ± 0.015274 | 1.591470 ± 0.100361 | 0.690680 ± 0.008882 | -0.000001 / 3.021991 |

Each dataset was trained twice from the frozen protocol: **8 complete training runs, 40 bitwise-identical fold-checkpoint pairs, and 80 independent forward passes**. The independent four-matrix summary passed **39/39 checks**. Train-mean baselines use training-fold density only and are post-hoc references, not a unified strong-baseline matrix. This closes official random-gene CV on the four released matrices only; homology/protein/study/functional OOD, publication-metric reproduction, unified-cost baseline ranking, CodonFlow-RK, SOTA and wet-lab validation remain open.

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

### 6.12 Exact preference-conditioned trajectory-balance optimization

We next tested optimization on the frozen synthetic two-step system with **3,721 endpoint states**, **121 legal actions per state**, and **14,641 enumerated paths**. The target is the exact endpoint law induced by the frozen oracle energy-tilted conditional, not a naive random-walk endpoint approximation. The first reverse step deterministically returns to the unique fixed start; the second reverse step is normalized only over legal parents reachable from that start. This construction preserves all state-dependent forward normalizers and the true time support.

The fixed protocol used float64 CUDA, Adam for **4,000 steps without checkpoint selection**, and a linear learning-rate schedule from 0.05 to 0.01. The independently recomputed final path-residual loss was **1.607e-29**, maximum absolute path residual **2.487e-14**, maximum forward–target endpoint error **2.602e-18**, forward–target KL **-4.373e-17**, and maximum endpoint-reconstruction error **5.204e-18**. The learned four weights differed from the frozen oracle weights by at most **1.110e-16**. Production and a separately executed retraining had bitwise-identical weight and backward-logit tensors and identical optimization histories. A separate NumPy implementation passed **25/25 checks**, finalization passed **20/20**, and **10 unit tests** passed. The analytic oracle independently gave maximum path residual **0.000e+00**, forward–target error **2.602e-18**, and backward-normalization error **1.110e-15**. The earlier incorrect target/shared-backward version failed 2 of 10 tests and is retained rather than hidden.

This is an **exact synthetic trajectory-balance optimization check**, not biological reward learning, a trained neural CodonFlow-RK generator, functional or generation performance, physical mechanism validation, RK-G1 closure, SOTA, or authorization for expensive generation training.

### 6.13 Minimal neural legal-kernel synthetic CUDA contract

We implemented a **5,273-parameter** minimal neural potential model by reusing the unchanged RK-08 initiation/velocity/decay/pair backbone and adding explicit codon-to-three-nucleotide expansion, multi-fidelity potential supervision, and an exact no-op/synonymous-single-edit conditional kernel. For the frozen `ATG–CTT–GCT–TGA` state, the core genetic-code table gives **9 unique legal candidates**, including no-op; internal stops are forbidden and terminal TGA is fixed. The remaining-budget rule admits **5 candidates and hard-masks 4**, rather than merely adding a soft cost penalty. UTR–CDS pair tensors and all candidate potentials are auditable.

The fixed smoke used float64 CUDA, Adam for **40 steps without checkpoint selection**, and a synthetic teacher only. The heteroscedastic multi-fidelity objective changed from **0.156933581 to -0.568343801**, while unmasked teacher MSE decreased from **0.185642740 to 0.009694968**. The conditional probabilities summed to **1.0**, total probability on masked states was **0.0**, and the maximum absolute kernel-gradient entry was **1.733675e-02**. Production and a separate retrain each passed **14/14 checks**; independent recomputation passed **27/27**, with zero error for candidates, potentials, cost, deltas, and log-probabilities, and finalization passed **25/25**. Checkpoint bytes, all state tensors, kernel arrays, and deterministic numeric history matched between runs; measured elapsed times were retained rather than forced to match. The initial codon-index implementation failed 6 tests, a subsequent test setup failed 1 test, and two independent verifiers stopped at 24/27 and 25/27 before the exact history and teacher-dtype semantics were corrected; all failures are preserved.

This is a **synthetic neural contract and CUDA backward smoke**, not biological mechanism validation, functional or velocity performance, full-generator training, generation quality, RK-G1 passage, OOD, SOTA, or authorization for expensive generation training.

### 6.14 RK-12 unique18 LinearDesign and external actual-set matrix

I expanded the fixed-source LinearDesign executable from the C01 smoke to the frozen unique18 development panel at lambda = 0.0, 0.1, ..., 1.0. The formal run comprised **198 official CPU processes** (18 records x 11 lambdas) with one worker and preserved raw stdout/stderr. It produced 131 distinct record-sequence pairs and required 5459.872 s of summed official-process wall clock; independent scoring time is reported separately. All 198 outputs were protein-identical. The independent grid verifier passed 35/35 checks with zero CAI/MFE recomputation error, and the three overlapping C01 sequences were exactly identical to the earlier official smoke.

For cross-method comparison, all raw CDS outputs were rescored using the same v4-train RSCU, frozen per-record calibration and four objectives. LinearDesign outputs received the disclosed terminal TAA before evaluation. The actual-set matrix contains 18 development records and six method columns; the primary comparator set and four paired tests were frozen before full-panel scoring. Mean values below are descriptive over 18 records, not a dense-budget or SOTA ranking.

| Method | Actual outputs | Mean normalized HV | Mean pairwise NED | Minimum identity |
|---|---:|---:|---:|---:|
| lineardesign_lambda11 | 131 | 29.972887 | 0.071289 | 1.000 |
| gemorna | 1427 | 20.015288 | 0.163751 | 1.000 |
| codongpt | 1800 | 14.537219 | 0.230018 | 1.000 |
| cai_greedy | 18 | 11.523556 | 0.000000 | 1.000 |
| uniform_synonymous | 1800 | 1.718763 | 0.240783 | 1.000 |
| lineardesign_scan | 103 | 29.855894 | 0.079248 | 1.000 |

| Comparator | Effect (LinearDesign - comparator) | Mean delta | Paired-bootstrap 95% CI | Holm p (4 tests) |
|---|---|---:|---:|---:|
| gemorna | hypervolume_normalized | 9.957599 | [3.848852, 16.976281] | 0.000499975 |
| gemorna | ned | -0.092461 | [-0.115715, -0.069694] | 0.00039998 |
| codongpt | hypervolume_normalized | 15.435668 | [7.587008, 24.698096] | 0.00039998 |
| codongpt | ned | -0.158729 | [-0.175079, -0.142412] | 0.00039998 |

The independent matrix verifier recomputed every raw objective, NED, Pareto/HV value and paired interval without importing the production matrix module (139/139 PASS); finalization passed 15/15 checks and the contract tests passed 10/10. Lambda is an objective weight, not a real scorer budget, so `dense_budget_step_auc_v2` remains null. Legacy baseline cost fields are not time-matched to the new single-worker measurements. This section contains no CodonFlow-RK generator result, untouched evaluation, functional OOD, wet-lab result or SOTA claim.

### 6.15 Mordstein full eight-bin observed-end recovery

I completed the authorized full eight-bin HEK293 Flow-seq recovery only after all 16 ENA mates passed exact byte-size and MD5 gates. The calculation used `max_reads=0`, retained every scanned pair, and separately preserved exact-count caches, centroid references, variant counts and a frozen 200-read audit sample per bin. The resulting evidence is an **observed-end recovery**, not a complete-CDS or author-variant identity reconstruction.

| Quantity | Verified value |
|---|---:|
| Verified input | 8 runs / 16 mates / 5,613,006,000 bytes |
| Raw mate pairs recounted | 14,929,515 |
| ORF-valid R1 / R2 reads | 1,356,615 / 12,521 |
| R1 / R2 centroids | 162 / 17 |
| R1 variants retained at support >= 1,000 | 152 |
| Mutual-best R1-R2 links | 17 |
| R1 reads assigned to retained variants | 9,037,593 |
| Raw-read audit rows independently reassigned | 1,600 |

The independent verifier re-read every raw mate pair, recounted ORF-valid reads, checked all input and cache hashes, validated the centroid/reference/table relationships and independently reassigned all 1,600 raw-read audit rows. It passed 60/60 checks; finalization passed 11/11 checks and reran the 7 contract tests. These passes establish computational consistency, not library completeness.

At the frozen support threshold of 1,000 assigned R1 reads, **152 R1 variants** were retained and **17 mutual-best R1-R2 links** were formed. The scientific library status therefore remains `REVIEW_REQUIRED_COUNT_NOT_217`; it is not evidence that 217 candidates were recovered. Support-threshold sensitivity (threshold: retained R1 variants) was 20: 162, 50: 162, 100: 162, 200: 161, 500: 156, 1000: 152, 2000: 147, 5000: 132. Only the observed 5′ 300-nt and linked 3′ 279-nt ends are supported directly. The central **138 nt / 46 codons** remain unobserved and are represented by Ns in paired-end references. Reconstructed `CF_MORD_*` identifiers are not author `GFP_###` identities. This result supplies no complete-CDS claim, independent functional validation, generator-readiness claim or SOTA claim.

### 6.16 Fixed-GFP observed-end proxy associations and robustness

I next asked whether the recovered observed ends contain any simple sequence signal at all. The frozen primary analysis used the 152 R1 variants passing the original total-read support threshold of at least 1,000 and the R1-assigned HEK293 intronless Flow-seq score, defined as the read-count-weighted mean of fluorescence-bin indices 1–8. The feature window was observed CDS 4–303 only. Two primary hypotheses tested Spearman associations for GC3 and GC, using 20,000 paired-variant bootstraps for percentile 95% CIs, 20,000 label permutations for two-sided p values, and Holm correction across exactly those two hypotheses. Pearson correlations and CpG density were secondary.

| Feature / metric | Correlation | 95% CI | Multiplicity |
|---|---:|---:|---:|
| GC3 / Spearman | 0.355974146 | [0.200764350, 0.498474931] | Holm p=9.99950002e-05 |
| GC3 / Pearson | 0.343495820 | [0.192066273, 0.482747188] | secondary |
| GC / Spearman | 0.358184001 | [0.204755397, 0.499192256] | Holm p=9.99950002e-05 |
| GC / Pearson | 0.341083543 | [0.192869026, 0.478265126] | secondary |
| CpG density / Spearman | 0.372594586 | [0.222352063, 0.509056593] | secondary; unadjusted |

Both primary associations were positive with CIs excluding zero. Thus, within this fixed-GFP observed-end dataset, GC3 and GC are **not uninformative proxies**. This is an association result, not evidence that a mechanism model adds predictive value beyond GC/GC3, CAI, folding or other simple features; no such incremental model comparison was performed here.

A separately frozen **post-hoc** robustness analysis repeated the Spearman estimates at total-read thresholds 1000, 2000, 5000, 10000, 20000, 50000, 100000. The corresponding sample sizes were 152, 147, 132, 112, 82, 51, 23. It also quantified the association between log10(total reads) and score (Spearman=-0.213817071, 95% CI [-0.362103560, -0.054639398]) and computed descriptive partial Spearman correlations after rank-residual adjustment for read depth.

| Feature | Observed Spearman range across 7 support thresholds | All 7 CI lower bounds > 0 | Depth-adjusted partial Spearman [95% CI] |
|---|---:|---:|---:|
| GC3 | 0.355974146 to 0.505308009 | false | 0.354487537 [0.198693664, 0.498803645] |
| GC | 0.358184001 to 0.513774842 | false | 0.356657456 [0.200763479, 0.498848517] |

The robustness analysis did not alter the primary endpoints or create a new acceptance gate. All results remain limited to recovered observed ends from one GFP library: they do not establish complete CDS sequence, author `GFP_###` identity, causality, protein/study OOD transfer, functional generation quality or SOTA. They do not close RK-G1 or authorize expensive generator training. Independent recomputation passed 18/18 primary checks and 8/8 robustness checks; finalization passed 12/12 and 8/8, respectively.

### 6.17 Frozen MAGE synonymous-mechanism development gate

I evaluated the prespecified synonymous-mechanism increment on the fixed infA MAGE data. From 179 eligible constructs across all positions, the primary rich-medium analysis retained 164 constructs at positions 10–71. The SHA256-ordered split, frozen before model fitting, assigned 98/33/33 constructs to train/dev/test. Four sparse ridge feature sets were compared over the same alpha grid, with alpha selected only by dev RMSE. RCS was treated as the published supervised structure score, not as an unsupervised physical ground truth.

| Feature set | Selected alpha | Dev RMSE | Dev Spearman |
|---|---:|---:|---:|
| intrinsic | 1 | 0.023268023767 | 0.632115745255 |
| local_mfe | 1 | 0.024321948639 | 0.617738079534 |
| rcs_only | 1 | 0.024482257578 | 0.635793752765 |
| full_mechanism | 1 | 0.025468752399 | 0.618239626013 |

The full mechanism model did not achieve the frozen requirement of strictly lower dev RMSE than both the intrinsic and local-MFE feature sets. The test split was therefore not authorized: no test predictions, test metrics, paired test intervals, minimal-medium transport or N-terminal transport were generated. The formal state is `DEV_NO_GO_TEST_UNTOUCHED`; this is a development-gate result, not a claim that mechanism is universally falsified. Independent raw-data and model-matrix reconstruction passed 39/39 checks with maximum numeric delta 4.83724171829e-13, and finalization passed 12/12 checks. This result does not close RK-G1 or authorize generator-training claims.

### 6.18 RK-13 EnsembleDesign and seven-method actual-set comparison

I added the fixed-source EnsembleDesign baseline to the same unique18 development panel. The frozen protocol used 18 per-record official CPU processes and **198 generator runs** (11 per protein), with four internal threads per process, beam size 100, learning rate 0.03, epsilon 0.5 and three iterations. The raw runs yielded 192 unique record-sequence pairs after within-record deduplication and required 6001.057 s of summed official-process wall clock. Every official CDS was protein-identical before the disclosed terminal TAA used only for shared evaluation. The independent raw-file verifier passed with a maximum official-versus-ViennaRNA EFE discrepancy of 0.00511841 kcal/mol.

The first verification attempt was stopped when unscaled ViennaRNA `pf()` returned its `100000.0` failure sentinel for `C41G7.2.1`; the failed report and all raw files were preserved unchanged. A separately frozen recovery applied MFE-based fold-compound rescaling consistently to every selected output and reexecuted `C41G7.2.1` plus the six not-yet-run records in a new output root. The selected evidence therefore contains 18 official processes and 198 generator runs, while 25 official processes and 209 generator runs were executed across the failed and recovery attempts. The EFE tolerance was not changed.

The seven-method matrix preserves all six RK-12 method fields exactly, binds their prior 139/139 independent PASS by hash, and recomputes only the new EnsembleDesign objectives from raw CDS using the same RSCU, per-record calibration and four objectives. The reference, six comparators, two metrics and Holm family of 12 paired tests were frozen before EnsembleDesign generation. Mean values remain descriptive over 18 development records. For NED, a positive LinearDesign-minus-comparator effect means greater sequence diversity, not better functional performance.

| Method | Actual outputs | Mean normalized HV | Mean pairwise NED | Minimum identity |
|---|---:|---:|---:|---:|
| lineardesign_lambda11 | 131 | 29.972887 | 0.071289 | 1.000 |
| ensembledesign_11run | 192 | 16.693982 | 0.045804 | 1.000 |
| gemorna | 1427 | 20.015288 | 0.163751 | 1.000 |
| codongpt | 1800 | 14.537219 | 0.230018 | 1.000 |
| cai_greedy | 18 | 11.523556 | 0.000000 | 1.000 |
| uniform_synonymous | 1800 | 1.718763 | 0.240783 | 1.000 |
| lineardesign_scan | 103 | 29.855894 | 0.079248 | 1.000 |

| Comparator | Effect (LinearDesign - comparator) | Mean delta | Paired-bootstrap 95% CI | Holm p (12 tests) |
|---|---|---:|---:|---:|
| codongpt | hypervolume_normalized | 15.435668 | [7.476256, 24.887069] | 0.00119994 |
| codongpt | ned | -0.158729 | [-0.175127, -0.142600] | 0.00119994 |
| gemorna | hypervolume_normalized | 9.957599 | [3.944589, 16.891854] | 0.00119994 |
| gemorna | ned | -0.092461 | [-0.115724, -0.070216] | 0.00119994 |
| cai_greedy | hypervolume_normalized | 18.449331 | [11.791770, 26.478799] | 0.00119994 |
| cai_greedy | ned | 0.071289 | [0.056190, 0.086800] | 0.00119994 |
| uniform_synonymous | hypervolume_normalized | 28.254124 | [18.216800, 40.434737] | 0.00119994 |
| uniform_synonymous | ned | -0.169494 | [-0.185799, -0.153683] | 0.00119994 |
| lineardesign_scan | hypervolume_normalized | 0.116993 | [0.059973, 0.179610] | 0.00119994 |
| lineardesign_scan | ned | -0.007959 | [-0.010177, -0.005775] | 0.00119994 |
| ensembledesign_11run | hypervolume_normalized | 13.278905 | [6.905804, 20.778993] | 0.00119994 |
| ensembledesign_11run | ned | 0.025486 | [0.004243, 0.047556] | 0.0176991 |

For the direct EnsembleDesign comparison, LinearDesign-minus-EnsembleDesign normalized HV was 13.278905 (95% CI [6.905804, 20.778993], Holm p=0.00119994). The descriptive highest mean-HV method was `lineardesign_lambda11`; this is not a SOTA designation. The independent matrix verifier passed 218/218 checks, recomputed all new raw objectives, HV, NED, Pareto counts and 12 paired intervals, and confirmed exact preservation of the six base-method fields. Measured generation time was 5459.872 s for the single-worker LinearDesign grid and 6001.057 s for EnsembleDesign with four internal threads; these costs are reported but are not unified or time-matched. Independent runs are not successive real-scorer budget checkpoints, so `dense_budget_step_auc_v2` remains null. This section contains no CodonFlow-RK main-generator result, functional OOD, wet-lab result or SOTA claim.

### 6.19 CAGFN official-source bounded train-generate-audit chain

I evaluated the public CAGFN source tree (Laajil et al., 2025) at commit `952ccf9682988ef88cf1251877e918b85fbee9e9`. The public tree contained no pretrained weights, so a real training run was required. The associated OpenReview page is marked rejected and is not treated as peer-reviewed acceptance. The published environment declared TorchGFN 1.1.1, but that version lacks the imported `MLP` class; versions 1.2 and 2.0.1 also failed the disclosed import or estimator checks. I therefore retained the unmodified CAGFN source and used TorchGFN 2.1.0 at commit `1fab00a1f388aba902b5c9c1b778f4d0ae6e18a0` as a dependency-compatibility recovery, not as the original author environment or an author-endorsed correction.

The successful process executed the official unconditional `main.py` on the 33-codon small-protein configuration with an explicit MLP override, two iterations, 20 samples, batch size 16, seed 42 and one CPU thread. Three earlier bounded attempts were retained unchanged: a wrapper interpreter-path failure, an unconditional estimator assertion under TorchGFN 2.0.1, and a conditional-entry import failure under TorchGFN 2.0.1. The recovered process completed in 47.556746 s of total wall clock, including 11.01 s reported for training and 6.68 s for sampling, and saved a real checkpoint with two finite loss and reward entries.

Independent raw-output verification passed 33/33 checks. All 20 sequences were unique, 99 nt long, protein-identical, AUG-initiated and free of internal stops. Direct CAI and bundled-RNAFolder recomputation, rather than the upstream exception-to-zero utilities, reproduced every printed value within two-decimal rounding error; no MFE or CAI value was zero. Finalization passed 22/22 checks.

| Bounded CAGFN smoke quantity | Independently recomputed value |
|---|---:|
| Unique / total sequences | 20 / 20 |
| Protein identity | 20 / 20 |
| Mean GC (%) | 47.575758 |
| Mean bundled-RNAFolder MFE (kcal/mol) | -26.760000 |
| Mean CAI using the source's human reference set | 0.456632 |
| Mean pairwise normalized edit distance | 0.252632 |

This is a bounded dependency-recovery smoke, not a converged model, full CAGFN reproduction or comparative performance result. Its MFE uses CAGFN's bundled `RNAFolder`, not the ViennaRNA-based scorer used for LinearDesign and EnsembleDesign; its CAI uses the hard-coded human reference set, not each target's natural mRNA. The MLP override also differs from the architecture named in the small-protein YAML. Accordingly, these descriptive values are not entered into the seven-method matrix, and the measured times are not time-matched costs. This section contains no functional, OOD, wet-lab or SOTA claim.

### 6.20 Fixed-GFP observed-R1 structure increment: development no-go

I next tested whether ViennaRNA folding features add predictive signal beyond sequencing depth and simple sequence features on the same 152 fixed-GFP observed-R1 variants. This was a retrospective, development-only analysis of a new feature set, not an independent confirmatory test. The frozen v2 protocol used five deterministic variant folds and ridge regression with alpha=1 and no hyperparameter search. The simple model contained log1p(total assigned reads), GC3, GC, CpG density and CAI. The treatment model added full observed 300-nt R1 MFE and the minimum and mean MFE over all contiguous 48-nt windows. Every feature and outcome scaler was fitted within the corresponding training fold.

| OOF model | Spearman | Pearson | MSE | RMSE |
|---|---:|---:|---:|---:|
| depth only | 0.197284700 | 0.162829956 | 2.167833454 | 1.472356429 |
| depth + simple sequence | 0.413234098 | 0.373938420 | 1.915420664 | 1.383987234 |
| depth + simple sequence + observed-R1 structure | 0.408983112 | 0.378327283 | 1.909992037 | 1.382024615 |

The two frozen primary endpoints compared structure-augmented with simple out-of-fold predictions using 20,000 paired-variant bootstraps and 20,000 paired sign-flip permutations, with Holm correction across exactly two hypotheses.

| Treatment-minus-simple effect | Observed | Paired-bootstrap 95% CI | Sign-flip p | Holm p |
|---|---:|---:|---:|---:|
| delta Spearman | -0.004250986 | [-0.055205392, 0.046335849] | 0.857457127 | 1.000 |
| delta MSE | -0.005428627 | [-0.089603707, 0.076765849] | 0.900154992 | 1.000 |

Neither endpoint met its prespecified direction and multiplicity gate. The small MSE decrease is uncertain, and the Spearman estimate is slightly negative; the scientific result is therefore **FIXED_GFP_OBSERVED_R1_STRUCTURE_INCREMENT_NO_GO_DEVELOPMENT_ONLY**. This does not show that RNA structure is universally uninformative. It shows no validated incremental value for these particular observed-R1 MFE features in this fixed-GFP development setup.

The CAI feature used the nine raw `def_refs` strings hard-coded in the frozen CAGFN wrapper and CAI==1.0.2 raw three-character chunking. The first raw reference contains embedded whitespace between two sequence-like segments; this was retained to reproduce the external package behavior and is a reference-quality limitation, not a validated clean human reference set. A v1 preflight stopped before structure calculation or model fitting when this raw encoding was encountered. The v2 implementation reproduced all 61 sense-codon weights from the external package with maximum absolute difference 1.11e-16 and passed 12 unit tests.

Independent verification retranslated every raw R1 sequence, recomputed every external CAI and ViennaRNA feature, regenerated all out-of-fold predictions with a separate penalized-matrix solver, and repeated both resampling analyses. It passed 12/12 checks, with maximum feature and prediction discrepancies of 2.78e-16 and 1.07e-14, respectively; finalization passed 21/21 checks. These results remain restricted to observed CDS 4-303 from one fixed-GFP library. They do not use functional untouched data, impute the central unobserved CDS, establish protein/study OOD transfer or causality, close RK-G1, authorize generator training or support a SOTA claim.

### 6.21 RiboMIMO cross-study transfer: ridge was stronger on both frozen endpoints

We next tested whether the complete official RiboMIMO recipe transferred from Mohammad16 to Subtelny14 under a protocol frozen before target readout. Official-loader eligibility yielded 1,179 source and 3,921 target transcripts. The source was divided into 1,062 training and 117 validation transcripts by the official NumPy random-split logic; all target transcripts were excluded from fitting, checkpoint selection and ridge-alpha selection. Source-target exact CDS overlap was zero. Subtelny14 had already been used in the RiboKinetic/ridge analysis, so this is not a globally untouched confirmatory test.

The official architecture, normalized ribosome-density target, mask, loss, optimizer and source-validation global-R2 checkpoint rule were retained. Seed 1234 was primary; seeds 2345 and 3456 were sensitivity analyses and were not selected by target performance. The ridge baseline used 64 codon one-hot features, 20 relative-position bins, relative position and log(length)/7. Its alpha was selected only by source-validation transcript-balanced MSE; alpha=100 was selected for every seed. Target predictions were evaluated only after source training and baseline selection.

| Seed | RiboMIMO TB-MSE | Ridge TB-MSE | Constant TB-MSE | RiboMIMO mean within-transcript r | Ridge mean within-transcript r |
|---:|---:|---:|---:|---:|---:|
| 1234 | 2.186608 | 1.006967 | 0.966916 | -0.001008 | 0.037500 |
| 2345 | 2.074145 | 1.006788 | 0.966910 | 0.004477 | 0.037489 |
| 3456 | 2.040441 | 1.005552 | 0.966907 | 0.011053 | 0.038321 |

Across seeds, RiboMIMO TB-MSE ranged from 2.040441 to 2.186608, compared with 1.005552 to 1.006967 for ridge and 0.966907 to 0.966916 for the source-train constant. Mean within-transcript Pearson ranged from -0.001008 to 0.011053 for RiboMIMO and from 0.037489 to 0.038321 for ridge. The ridge advantage over RiboMIMO therefore does not imply strong absolute transfer: the source-train constant also had lower TB-MSE than both learned models for every seed. The constant has undefined within-transcript Pearson and is therefore not a complete ranking baseline.

The two frozen primary contrasts used the primary seed, 2,000 paired-transcript bootstraps, 2,000 paired sign-flip permutations and Holm correction across exactly two hypotheses. Positive delta TB-MSE and negative delta Pearson favor ridge.

| Primary effect: RiboMIMO minus ridge | Observed | Paired-bootstrap 95% CI | Sign-flip p | Holm p |
|---|---:|---:|---:|---:|
| delta TB-MSE | 1.179641679 | [1.162686549, 1.196288204] | 0.000499750 | 0.000999500 |
| delta mean within-transcript Pearson | -0.038507716 | [-0.041406162, -0.035536052] | 0.000499750 | 0.000999500 |

Both intervals excluded zero in the direction favoring ridge, with Holm p=0.000999500 for each endpoint. The finalized result is **RIBOMIMO_STUDY_OOD_NO_UNIFORM_SIGNIFICANT_ADVANTAGE_OVER_RIDGE**; more directly, ridge significantly outperformed RiboMIMO on both prespecified primary endpoints in this Mohammad16-to-Subtelny14 setup. This is a bounded negative transfer result for an occupancy-derived target, not a physical-velocity measurement, universal assessment of RiboMIMO, functional OOD result or SOTA claim.

Independent verification reparsed both raw three-line matrices, recomputed eligibility, normalization, masks, source splits, ridge fitting, target metrics and paired inference, and retrained all three seeds in separate output directories. It passed 203/203 checks; maximum absolute production-versus-independent differences were 0 for model predictions and 1.51e-07 for ridge predictions. Finalization passed 30/30 checks. The shared-GPU wall times are retained in the training record but are not time-matched cost evidence. This experiment does not close homology/protein OOD, functional OOD, RK-G1, generator authorization or the full baseline program.

### 6.22 MAGE nested development CV: mechanism increments were small and unstable

We asked whether the original single-split MAGE development NO-GO was sensitive to the particular 33-construct development assignment. The new diagnostic used only the 131 constructs already assigned to train or development in v1 (98 train and 33 development). The 33 test constructs were excluded before constructing any development record table, fold, feature matrix, prediction or metric. Thus v1 remains **DEV_NO_GO_TEST_UNTOUCHED**, and the present analysis is a development-only diagnostic rather than an independent confirmation.

The four original feature sets and alpha grid were unchanged. Five-fold outer cross-validation produced one out-of-fold prediction per construct; four-fold inner cross-validation selected ridge alpha separately within each outer-training partition and feature set. All scaling and categorical encoding were fitted within the corresponding training partition. The primary outer seed was 40261119, with seeds 40261120 and 40261121 used only for sensitivity. Primary inference used 20,000 construct bootstraps, 20,000 paired sign-flip permutations and Holm correction across four tests (two references and two metrics).

| Feature set | Development OOF RMSE | Development OOF Spearman |
|---|---:|---:|
| intrinsic | 0.034133275 | 0.612399084 |
| local_mfe | 0.034383848 | 0.627265588 |
| rcs_only | 0.034152774 | 0.616352629 |
| full_mechanism | 0.034228203 | 0.635298146 |

| Contrast | Metric | Observed | Paired-bootstrap 95% CI | Holm p |
|---|---|---:|---:|---:|
| full minus intrinsic | delta Spearman | 0.022899062 | [-0.037905777, 0.090116393] | 1.000000 |
| full minus intrinsic | delta RMSE | 0.000094928 | [-0.001417567, 0.001456402] | 1.000000 |
| full minus local-MFE | delta Spearman | 0.008032557 | [-0.028646739, 0.048858482] | 1.000000 |
| full minus local-MFE | delta RMSE | -0.000155645 | [-0.000999395, 0.000600285] | 1.000000 |

The full-mechanism model did not improve RMSE relative to intrinsic features: the observed difference was +0.000094928, and its interval crossed zero. Its small RMSE decrease relative to local-MFE was also uncertain, with a 95% CI of [-0.000999395, 0.000600285]. Both Spearman point differences were positive, but both intervals crossed zero and all four Holm-adjusted p values were 1.0. No primary comparison met the frozen direction and multiplicity requirements.

| Sensitivity seed | Contrast | Delta Spearman | Delta RMSE |
|---:|---|---:|---:|
| 40261120 | full minus intrinsic | 0.014893200 | -0.000517121 |
| 40261120 | full minus local_mfe | -0.015306974 | 0.000374016 |
| 40261121 | full minus intrinsic | 0.024119028 | 0.000133165 |
| 40261121 | full minus local_mfe | -0.009372652 | 0.000728751 |

The sensitivity analyses did not resolve the result in favor of the mechanism model. In particular, full-minus-local-MFE Spearman was negative in both sensitivity repeats, and the RMSE direction changed across references and repeats. The prespecified sensitivity sign-consistency requirement therefore failed in addition to the primary inferential gate. These results do not show that RNA structure is universally uninformative; they show that the current full-mechanism feature set did not yield a stable increment over intrinsic or local-MFE baselines in this fixed-infA development design. RCS remains a published supervised structure score, not an unsupervised physical ground truth.

Independent raw-source verification reconstructed all 131 development records, all nested folds and alpha selections, all OOF predictions, the primary intervals and permutations, and both sensitivity repeats. It passed **96/96 checks**, with zero maximum discrepancy for predictions, metrics, inference and inner RMSE. Finalization passed **30/30 checks**. No test prediction, test metric, minimal-medium transport, N-terminal transport or generator authorization was generated. The original v1 NO-GO and all previous negative results remain unchanged; RK-G1 remains open and the manuscript remains non-submittable.

### 6.23 Metadata-only recovery of Ribo-seq sources and VeloHARMO release scope

We audited whether the processed Ribo-seq evidence and the five-organism VeloHARMO comparison could be connected to public raw sources without treating processed matrices as completed remapping. The audit froze `BianBian2021/VeloHARMO` at commit `38b48079856aeb9d33a1b10844d77aa8f6640032` and retained official PMC, GEO SOFT and SRA RunInfo responses with file hashes. It did not download FASTQ, BAM or SRA reads, construct UTR–CDS annotations, align reads or fit a model.

All five VeloHARMO source studies had public run-level records. Official titles and full text map Dunn13 to *Drosophila melanogaster* and GSE49197, and Pop14 to *Saccharomyces cerevisiae* and GSE63789. The five studies comprised 125 runs and 143,663 MB in RunInfo metadata. These sizes describe the public archives, not data transferred by this audit.

| Source study | Organism | Study accession | RunInfo accession | Runs | RunInfo size (MB) | Pinned release |
|---|---|---|---|---:|---:|---|
| Mohammad16 | Escherichia coli | GSE72899 | SRP063562 | 5 | 3,594 | matrix + GA |
| Grady17 | Pseudomonas aeruginosa | PRJNA379630 | PRJNA379630 | 24 | 58,639 | neither |
| Dunn13 | Drosophila melanogaster | GSE49197 | SRP028243 | 14 | 34,020 | neither |
| Pop14 | Saccharomyces cerevisiae | GSE63789 | SRP050443 | 10 | 13,780 | GA only |
| Battle15 | Homo sapiens | GSE61742 | SRP047476 | 72 | 33,630 | neither |

The pinned repository contained 14 tree entries and 14 materialized blob files, all with matching current SHA-256 and byte counts. Its two E. coli matrix archives were byte-identical; E. coli and yeast genetic-algorithm checkpoints were present. No harmonized matrix archive for *P. aeruginosa*, *D. melanogaster*, *S. cerevisiae* or human was present in that snapshot. Thus a public raw source and a released checkpoint must not be interpreted as a released harmonized matrix.

For the RiboMIMO source layer, Mohammad19/GSE119104 contributed 10 runs and 5,202 MB, while Subtelny14/GSE53268 contributed 3 runs and 4,034 MB through its current BioProject relation PRJNA231671. Together with the shared Mohammad16 archive, the seven distinct RunInfo accessions contained 138 runs and 152,899 MB. The additional RiboMIMO archives beyond Mohammad16 therefore contributed 13 runs and 9,236 MB.

Independent offline verification reparsed every required response, rechecked the study mappings and recomputed all run counts, sizes and materialized-file hashes. It passed **169/169 checks**, with maximum numeric discrepancy 0. Finalization passed **47/47 checks**. This closes only the bounded metadata-feasibility subtask. UTR–CDS construction, independent raw-read/P-site remapping, four non-E. coli harmonized matrices, the full natural-distribution report, mechanism validation and model training remain unperformed. Any future remapping must freeze reference versions per study and assess read length and end assignment per sample; no global P-site offset is licensed. RK-G1 remains open and the manuscript remains non-submittable.

### 6.24 Real dense-budget simple-search trajectories on unique18

We measured real anytime behavior for four non-learned simple searches on the 18 unique18 development records. The frozen panel comprised three seeds, four methods and 500 successive unique proxy-scorer evaluations per run, giving 216 runs and 108,000 scored sequences. Every sequence remained synonymous with its source. The initial state consumed budget B=1. The primary dense endpoint was sum(HV_b for b=1,...,499)/499; B=500 was retained as an endpoint and was excluded from the AUC. Normalized HV used each record's frozen calibration reference and scale and was not clipped to [0,1]. No synthetic origin, trapezoidal integration, zero-filled missing budget or conversion of unordered external actual sets was used.

| Method | Mean dense AUC | Mean HV B50 | Mean HV B100 | Mean HV B500 | Total wall time (s) |
|---|---:|---:|---:|---:|---:|
| uniform | 1.950968565 | 1.415294670 | 1.718857849 | 2.334063596 | 20945.031473771 |
| hill_climbing | 8.702457019 | 1.208588184 | 3.068278130 | 16.402767217 | 21077.843297181 |
| mh_annealing | 3.133456174 | 0.454691806 | 0.731198467 | 9.840774383 | 20939.076001615 |
| areuredi_style | 0.901603954 | 0.417154406 | 0.600703695 | 1.494733501 | 21015.123456662 |

The record was the statistical unit. For each record and method, values were first averaged arithmetically over seeds 0, 1 and 2. Paired record bootstrap used 20,000 resamples, paired sign-flip permutation used 20,000 draws, and Holm correction covered the six primary tests. A supported advantage required a positive effect, a 95% CI lower bound above zero and Holm-adjusted p<0.05.

| Method minus uniform | Endpoint | Effect | 95% CI | Holm p | Supported advantage |
|---|---|---:|---|---:|---|
| hill_climbing | dense AUC | 6.751488454 | [4.942193634, 8.753959752] | 0.00029999 | yes |
| hill_climbing | B500 normalized HV | 14.068703620 | [10.421982583, 18.135617640] | 0.00029999 | yes |
| mh_annealing | dense AUC | 1.182487609 | [0.631103879, 1.771868974] | 0.00069997 | yes |
| mh_annealing | B500 normalized HV | 7.506710787 | [5.281172524, 9.867376191] | 0.00029999 | yes |
| areuredi_style | dense AUC | -1.049364611 | [-1.273765722, -0.815195131] | 0.00029999 | no |
| areuredi_style | B500 normalized HV | -0.839330096 | [-1.079445860, -0.599015543] | 0.00029999 | no |

The frozen rule supported 4 of six comparisons: hill_climbing (dense AUC), hill_climbing (B500 HV), mh_annealing (dense AUC), mh_annealing (B500 HV). The remaining comparisons, including negative and interval-crossing effects, are retained in the table. These are development proxy-search comparisons, not functional or external SOTA results.

Secondary bidirectional strict-dominance fractions at B=500 were computed from each run's Pareto points. They describe proxy-output sets only.

| Method A | Method B | Fraction of A dominated by B | Fraction of B dominated by A |
|---|---|---:|---:|
| areuredi_style | hill_climbing | 0.790542980 | 0.012901913 |
| areuredi_style | mh_annealing | 0.907215656 | 0.009523810 |
| areuredi_style | uniform | 0.599558157 | 0.158183897 |
| hill_climbing | mh_annealing | 0.026349885 | 0.604501552 |
| hill_climbing | uniform | 0.012698413 | 0.778006462 |
| mh_annealing | uniform | 0.049405231 | 0.823351004 |

Independent verification recomputed every CAI, ViennaRNA MFE, GC and motif objective from sequence, all 500-point normalized-HV curves, secondary budgets, NED, Pareto counts, strict dominance and paired inference. It passed **26/26 checks**; the maximum absolute discrepancy was 0 for objectives, 0 for dense HV and 0 for paired inference. Finalization passed **44/44 checks**. Wall times are internal one-worker-per-run costs and are not time-matched to LinearDesign, EnsembleDesign or another external implementation. External independent-lambda outputs remain unordered actual sets, so their dense AUC remains null.

This section closes only the real dense-budget simple-search evidence gap on unique18 development proxies. It used no untouched24 record, functional-untouched assay row, MAGE mechanism-test construct or functional label; it trained no generator. It does not establish functional effectiveness, CodonFlow-RK improvement, external SOTA, RK-G1 closure or generator-training readiness. The manuscript remains non-submittable.

### 6.25 Development-only MAGE OOF comparator closure

To close a comparator gap in the existing MAGE nested-development diagnostic without fitting another model, we froze a post-hoc exploratory analysis of the existing 131-construct OOF predictions for all three outer seeds. The four original arms were unchanged. The arm named `rcs_only` contains intrinsic features plus RCS additions and is not a pure external-pretrained-model replacement. The outer-train-mean prediction for each fold was computed only from development labels outside that fold. No mechanism-test construct or new sequence/label was accessed.

For the two feature contrasts, paired inference covered both ΔSpearman and ΔRMSE. The outer-train-mean comparison used RMSE only: fold-specific training means are not a globally constant prediction vector, so their OOF Spearman is descriptive and excluded from paired inference. Five tests shared one Holm family. The primary outer seed used 20,000 construct bootstraps and 20,000 paired permutations; the other two seeds contributed point estimates only. The earlier v1 protocol failed its technical gate because it incorrectly required a null Spearman for fold-varying means; no v1 production report was written, and the correction and all failed logs are retained.

| Comparison | Metric | Effect | 95% paired CI | Holm p |
|---|---:|---:|---:|---:|
| full − RCS | ΔSpearman | 0.01894551686269652 | [-0.035360666095523505, 0.0812104898567834] | 1.0 |
| full − RCS | ΔRMSE | 7.54291571132687e-05 | [-0.001304659287456654, 0.0013410731145082557] | 1.0 |
| RCS − intrinsic | ΔSpearman | 0.003953545226666688 | [-0.0360723999783062, 0.04841834750571718] | 1.0 |
| RCS − intrinsic | ΔRMSE | 1.9499256082820826e-05 | [-0.0007529122397496208, 0.0007030615007199467] | 1.0 |
| full − outer-train mean | ΔRMSE | -0.015370339550445498 | [-0.0259385856740894, -0.005729286631198561] | 0.020748962551872408 |

The full model and outer-train mean had primary RMSE values of 0.03422820302559988 and 0.04959854257604538, respectively. The full−mean ΔRMSE was -0.015370339550445498, with raw permutation p=0.004149792510374482 and Holm p=0.020748962551872408; its three-seed ΔRMSE signs were −/−/−. This establishes an improvement over the fold-specific training-mean baseline on already-used development predictions, not a mechanism increment or independent confirmation.

Across seeds 40261119, 40261120, 40261121, full−RCS ΔSpearman signs were +/+/+ and ΔRMSE signs were +/−/−; RCS−intrinsic ΔSpearman signs were +/−/− and ΔRMSE signs were +/+/+. All four feature-comparison Holm p values were 1.0 and every confidence interval crossed zero; the sensitivity directions were not stable. A separately fitted constant-speed arm, a mature external-model replacement, functional-untouched evaluation, transport analysis, and generator authorization remain open.

Independent recomputation passed **24/24 checks** with maximum absolute tolerance 1e-12, and the unit suite passed **9/9 tests** (`mage_oof_comparator_closure_unit_tests_v4_python3.console.log`). The audit performed zero new fits and zero new scorer calls; its 120,000 primary resample replicates took 55.9064832450822 s. It remains development-only and post-hoc: `DEV_NO_GO_TEST_UNTOUCHED`, RK-G1=false, and the non-submittable working-manuscript status are unchanged.

### 6.26 Bounded RK-G0 readiness and unified cost ledger

We froze 20 source/gate facts and 22 explicit cost rows from 22 hashed reports. The bounded RK-G0 gate required usable real functional data with reliable splits, reproducible key baselines, and independently tested dense/actual-set evaluators. Boël sequence-OOD, MAGE development OOF, the Mordstein 16-file/eight-bin recovery, the 21-file RNARL pair-table QC, LinearDesign, EnsembleDesign, CodonTransformer, CAGFN, RiboMIMO study-OOD, and both evaluator families met their frozen technical criteria. This is a bounded readiness result, not a claim that every dataset, official model, or external dense trajectory is complete.

Costs are reported only within their original task, hardware, and execution scopes. A dash is an explicit null with a machine-readable reason in the frozen JSON; it is never zero. Training, generation/inference, scoring, unique scorer calls, and total wall time are not summed or ranked across mixed or overlapping scopes. No time-matched or complete-SOTA interpretation is authorized.

| Method | Scope | Wall (s) | Train (s) | Generation/inference (s) | Scoring/selection (s) | Calls / outputs |
|---|---|---:|---:|---:|---:|---:|
| LinearDesign | unique18, 198 runs, actual-set | 5459.871640930884 | 0.0 | 5459.871640930884 | — | 131 outputs |
| EnsembleDesign | unique18, 198 runs, actual-set | 6001.057458210271 | 0.0 | 6001.057458210271 | — | 192 outputs |
| CAGFN | bounded official toy smoke | 47.556745767593384 | 11.01 | 6.68 | — | — |
| ID3 | one protein, 2 iterations, 1 seed | 417.591162443161 | 0.0 | 417.591162443161 | — | 12 runs/seeds |
| CodonTransformer | 4 released-weight GPU inferences | 6.471435410901904 | — | 2.0327787059359252 | — | 2 outputs |
| VeloHARMO | released test + bounded GA | 5.946522436104715 | — | 1.2729171668179333 | — | — |
| iXnos | 1M-read prefix, 2 epochs | 10.537669897079468 | 6.03219199180603 | — | — | — |
| ROSE | 2 studies, released checkpoint | 112.82697493582964 | — | 105.96287328284234 | — | — |
| RiboMIMO | study-OOD, 3 independent seeds | 949.7424744511954 | 733.5893584797159 | 89.50084520922974 | 45.446167211048305 | 3 runs/seeds |
| uniform simple search | unique18 dense, 54 runs | 20945.031473771203 | 0.0 | 16.225387217942625 | 20869.626151481643 | 27000 unique scorer calls |
| hill-climbing | unique18 dense, 54 runs | 21077.843297181185 | 0.0 | 8.822805067058653 | 21020.672998382244 | 27000 unique scorer calls |
| MH-annealing | unique18 dense, 54 runs | 20939.076001615264 | 0.0 | 8.987731650937349 | 20877.88818777073 | 27000 unique scorer calls |
| AReUReDi-style | unique18 dense, 54 runs | 21015.123456662055 | 0.0 | 10.632299634162337 | 20950.513713391032 | 27000 unique scorer calls |

The five inherited external actual-set groups remain cost-null rather than cost-zero: codonGPT=1800 outputs, GEMORNA=1427, CAI greedy=18, uniform synonymous=1800, and LinearDesignScan=103. RNARL contributes 128289 clean LinearDesign-like QC pairs, not valid official-model generations. CDGB source identity remains unresolved; COformer and CHARMING remain explicitly NOT_RUN. These states are not evidence that the corresponding methods are ineffective.

The source-feasibility task is closed only as a feasibility report: iXnos executed a real 1,000,000-read prefix with independent P-site offset re-derivation, while the later source audit recovered metadata-level UTR/Ribo/VeloHARMO scope. It did not complete a full UTR–CDS remap, full SRR1049521 processing, natural-CDS eligibility, or five-species VeloHARMO matrices. The frozen status is therefore `FEASIBILITY_CLOSED_NOT_FULL_REMAP`.

Production passed **179/179 checks**. The independent standard-library verifier recomputed every extraction and gate fact and passed **357/357 checks**, with maximum numeric discrepancy 0.0; targeted tests passed **9/9**, and finalization passed **6/6 checks**. The first protocol failed on `lineardesign_unique_sequences`; a full preflight then found ten invalid pointers. The v1 protocol/log and correction record are retained. The closeout reran no baseline, added zero scorer calls, and started no generator training.

The resulting status is `PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY`. External dense coverage, time-matched evaluation, complete SOTA, full UTR–CDS remapping, RNARL official-model reproduction, functional-untouched evaluation, wet-lab validation, and RK-G1 remain unclosed. Expensive CodonFlow-RK generator training remains unauthorized, and this manuscript remains non-submittable.

### 6.27 Development-selected mechanism-channel screen

To test whether the earlier all-versus-none comparison concealed a more informative channel subset, we preregistered a ten-arm screen with identical backbone, optimization, seed, and development-checkpoint rules. The arms were `all`, `none`, `initiation_only`, `velocity_only`, `decay_only`, `pair_only`, `no_initiation`, `no_velocity`, `no_decay`, and `no_pair`; every arm had 4,997 parameters. The screen configurations exposed only 4,019 training rows and 503 development rows. Test, sequence-OOD, and the 19,072 functional-untouched rows were not loaded for arm selection. Independent recomputation of development cluster-balanced MSE selected `all` uniquely, with exact ties reserved for the preregistered arm order.

**Table 1**

*Development-Only Arm Selection*

| Arm | Development cluster-balanced MSE | Selected epoch |
|---|---:|---:|
| all | 3.761769367012553 | 2 |
| none | 3.9020595367704525 | 1 |
| initiation_only | 3.8301992553887327 | 3 |
| velocity_only | 3.8916879794475405 | 4 |
| decay_only | 3.850946340081351 | 4 |
| pair_only | 3.8281384321374885 | 4 |
| no_initiation | 3.7844715234272623 | 3 |
| no_velocity | 3.7779845961149188 | 3 |
| no_decay | 3.8131579274957996 | 4 |
| no_pair | 3.795848800821685 | 4 |

*Note.* The selection set contained 503 rows in 447 operational protein clusters. Lower cluster-balanced MSE is better. Test and sequence-OOD predictions were not used in this table.

After freezing `all` as the selected arm, we evaluated only `all` and `none` on the held-out test and sequence-OOD partitions and compared them with the frozen `ridge_all` and `ridge_gc` predictors. The primary sequence-OOD partition contained 1,336 rows in 1,110 operational protein clusters. Confidence intervals used 2,000 operational-protein-cluster bootstrap replicates, and Holm correction was applied within each six-comparison partition. Positive ΔSpearman and negative Δcluster-balanced MSE favor the selected arm.

**Table 2**

*Frozen Sequence-OOD Comparisons for the Development-Selected Arm*

| Comparison | ΔSpearman [95% CI] | Holm *p* | Δcluster-balanced MSE [95% CI] | Holm *p* |
|---|---:|---:|---:|---:|
| selected − none | 0.19901564752464795 [0.12925907591173844, 0.26781646706339085] | 0 | −0.2760885716873087 [−0.37608880535590633, −0.18123318545616485] | 0 |
| selected − ridge_all | −0.025779039513507546 [−0.0755256519724216, 0.020488139619787824] | 0.532 | −0.025572097048845777 [−0.1282439258338166, 0.07253420347846523] | 0.636 |
| selected − ridge_gc | 0.12022060447388114 [0.0819592276678431, 0.1602983907730725] | 0 | −0.2895163999162387 [−0.3565435053891241, −0.226815730607076] | 0 |

*Note.* CI denotes confidence interval. Each interval and *p* value was independently recomputed from the frozen predictions using the preregistered resampling unit and seed.

The selected arm improved both sequence-OOD endpoints relative to `none` and `ridge_gc`, but it did not establish an increment over `ridge_all`. For `selected − ridge_all`, both confidence intervals crossed zero and the Holm-adjusted *p* values were 0.532 for Spearman and 0.636 for cluster-balanced MSE. The preregistered channel-screen gate therefore remained false. This pattern does not isolate a replacement single-channel mechanism, nor does it show that the combined mechanism channels add robust predictive information beyond the full-proxy ridge.

As a leakage diagnostic rather than a new performance claim, the train/development-only `all` and `none` checkpoints had bitwise-equal state dictionaries and identical selected epochs to the corresponding earlier full-configuration runs. The post-selection predictions were also byte-identical to the earlier evaluation artifacts. Thus, merely loading test/OOD rows in the earlier configuration did not alter the learned weights; this check does not improve or reinterpret the negative full-proxy comparison.

Independent standard-library verification reconstructed arm selection, all test/OOD metrics, 2,000 bootstrap replicates, confidence intervals, sign tests, and Holm correction. It passed **320/320 checks**, with maximum numeric discrepancy 1.9095836023552692e-14; the targeted suite passed **8/8 tests**, and finalization passed **42/42 checks**. Functional untouched was not evaluated, the earlier velocity endpoint remains failed, and this screen alone cannot close RK-G1. Expensive generator training remains unauthorized, and no functional, wet-lab, complete-SOTA, or submittable-manuscript claim is made.

### 6.28 Pure external-RCS comparator on reused MAGE development folds

To resolve whether the historical `rcs_only` arm could be interpreted as a pure external predictor, we preregistered a development-only comparator before fitting any new model. The historical arm contains intrinsic features plus RCS additions, so its frozen predictions cannot answer this question. The new `pure_external_rcs` arm used only variant RCS, its difference from the matched wild-type control, and the absolute difference. It contained no position, position interaction, codon or amino-acid identity, GC, local-MFE, or other intrinsic feature. Labels, folds, and the three existing-arm predictions came from the frozen 131-construct train-plus-development artifact; the 33 test constructs were excluded from feature selection, fitting, and evaluation. The pure arm used the same five outer folds, four inner folds, three outer seeds, and six-value regularization grid as the earlier nested-CV protocol, requiring 375 new fits while leaving all old-arm predictions unchanged.

**Table 1**

*Primary Development Metrics for the Pure External-RCS Comparator*

| Arm | RMSE | MAE | Spearman |
|---|---:|---:|---:|
| intrinsic | 0.03413327461240379 | 0.022187896273263757 | 0.6123990835404937 |
| pure external RCS | 0.04929761172417739 | 0.03158281646008941 | −0.13201530863899236 |
| intrinsic + RCS | 0.034152773868486606 | 0.021816612746170472 | 0.6163526287671603 |
| full mechanism | 0.03422820302559988 | 0.0222595186439585 | 0.6352981456298568 |

*Note.* Results use primary outer seed 40261119 and 131 reused development constructs. Lower RMSE and MAE and higher Spearman are better. RCS denotes the external structure-derived feature; MAE denotes mean absolute error. These are development diagnostics, not independent test results.

The preregistered comparisons used 20,000 construct-bootstrap replicates for two-sided 95% percentile confidence intervals and 20,000 within-construct prediction-swap permutations. Holm correction covered the six tests formed by three comparisons and two endpoints. Support required both intervals to exclude zero in the favorable direction, both Holm-adjusted *p* values to be below 0.05, and favorable point-estimate signs on both sensitivity seeds.

**Table 2**

*Preregistered Pure External-RCS Comparisons on Reused Development Folds*

| Comparison | ΔSpearman [95% CI] | Holm *p* | ΔRMSE [95% CI] | Holm *p* |
|---|---:|---:|---:|---:|
| pure external RCS − intrinsic | −0.744414392179486 [−0.9403491867053566, −0.5300791533185797] | 0.0002999850007499625 | 0.015164337111773597 [0.005846359530413134, 0.02506527402042598] | 0.009449527523623819 |
| full mechanism − pure external RCS | 0.7673134542688491 [0.5631894046071572, 0.9532654793818945] | 0.0002999850007499625 | −0.015069408698577508 [−0.02544806838533774, −0.005479110034720501] | 0.009449527523623819 |
| intrinsic + RCS − pure external RCS | 0.7483679374061527 [0.539343123375721, 0.9432946055506556] | 0.0002999850007499625 | −0.015144837855690783 [−0.02536403898497323, −0.00577083989049933] | 0.009449527523623819 |

*Note.* CI denotes confidence interval. Positive ΔSpearman and negative ΔRMSE favor the first-named arm. Each p value is Holm-adjusted across six primary tests.

The pure external-RCS predictor performed significantly worse than intrinsic on both primary endpoints, with adverse point-estimate directions on both sensitivity seeds. Pure external replacement was therefore not supported. Full mechanism and intrinsic+RCS each outperformed the pure arm under the preregistered support rule, but comparisons against this weak pure predictor do not establish an increment over intrinsic. The earlier full-mechanism−intrinsic comparison remained unchanged: ΔSpearman was 0.022899062089363098 with a 95% CI of [−0.03790577728252063, 0.09011639336438297], and ΔRMSE was 0.00009492841319608952 with a 95% CI of [−0.0014175669474227434, 0.0014564023955950885]; both Holm-adjusted *p* values were 1. Thus, the new arm closes the naming and feature-composition ambiguity without rescuing the prior non-significant mechanism comparison.

An independent implementation reconstructed the external-only features, repeated all 375 fits, and recomputed predictions, model selection, metrics, intervals, permutation tests, and Holm correction. It passed **174/174 checks** with maximum numeric discrepancy 0; finalization passed **43/43 checks**. The original development no-go remains unchanged. No test or functional-untouched evaluation was performed, RK-G1 remains false, expensive generator training remains unauthorized, and no protein-OOD, causal-mechanism, complete-SOTA, or submittable-manuscript claim is made.


### 6.29 A train-only constant relative-position field outperforms both velocity predictors on Subtelny14

To test whether the frozen velocity predictors captured more than a simple positional trend, we preregistered a sequence-independent constant-field comparator before computing its readout. The field used only the Mohammad16 training partition: 933 transcripts and 267,800 observed codon positions. Relative position was calculated as codon position divided by codon count minus one and discretized into the same 20 bins used by the ridge baseline. Within each training transcript, observed targets were first averaged within each bin; these transcript-bin means were then averaged with equal transcript weight. No sequence, codon identity, host, evaluation target, new model fit, or checkpoint selection entered the comparator. Predictions were evaluated on the frozen Subtelny14 partition of 3,630 transcripts and 1,444,596 observed positions, which has zero exact-CDS overlap with all Mohammad16 splits. The target remains an occupancy-derived speed proxy rather than a physical velocity measurement.

**Table 1**

*Subtelny14 Metrics for the Frozen Velocity Predictors and the Constant Relative-Position Field*

| Predictor | Transcript-balanced MSE | Mean transcript Pearson |
|---|---:|---:|
| RiboKinetic velocity | 0.23056854005324243 | −0.00884488119796242 |
| Codon–position–length ridge | 0.1759458819436876 | 0.061698354230170255 |
| Constant relative-position field | 0.17285268431817252 | 0.12464883660898879 |

*Note.* All 3,630 transcripts had finite within-transcript Pearson values for all three predictors. Lower MSE and higher Pearson are better. The constant field was estimated from Mohammad16 training data only.

The three paired comparisons used 2,000 transcript-bootstrap replicates with the original seed 20261120. Six endpoint-wise tests were corrected together by the Holm method. Support required a transcript-balanced MSE interval entirely below zero, a mean-transcript Pearson interval entirely above zero, both Holm-adjusted *p* values below 0.05, and beneficial bootstrap-mean directions at sensitivity seeds 20261121 and 20261122.

**Table 2**

*Paired Subtelny14 Comparisons Against the Constant Relative-Position Field and the Original Ridge Comparator*

| Comparison | ΔTranscript-balanced MSE [95% CI] | Holm *p* | ΔMean transcript Pearson [95% CI] | Holm *p* |
|---|---:|---:|---:|---:|
| RiboKinetic − constant field | 0.05771585573506995 [0.05709918203103379, 0.05834085807893431] | 0 | −0.1334937178069512 [−0.13779552902338732, −0.12926709989907645] | 0 |
| Ridge − constant field | 0.003093197625515117 [0.0029514829149933754, 0.00324115839797996] | 0 | −0.06295048237881853 [−0.06590631231789056, −0.060080732289514466] | 0 |
| RiboKinetic − ridge | 0.05462265810955484 [0.05404594435779176, 0.05519200143473219] | 0 | −0.07054323542813268 [−0.07324810579112143, −0.06776526128770917] | 0 |

*Note.* CI denotes confidence interval. Negative ΔMSE and positive ΔPearson would favor the first-named predictor. Zero sign-test *p* values denote no opposing bootstrap signs in 2,000 replicates, not a continuous probability of exactly zero.

The constant field therefore had the lowest transcript-balanced MSE and the highest mean transcript Pearson among these three frozen predictors. Both RiboKinetic and ridge were significantly worse than the constant field on both endpoints, and both sensitivity seeds retained the adverse directions. Consequently, neither the model–constant nor the ridge–constant comparison met the support rule. The original model–ridge comparison also remained unfavorable and was reproduced at the frozen numerical tolerance. These results strengthen the prior negative cross-study mechanism conclusion: internal development gains did not transfer, and the codon–position–length ridge did not improve on a train-only positional field in this partition.

An independent implementation checked every prediction target against the raw records, refit the field, and recomputed all metrics, bootstrap comparisons, sensitivity analyses, and Holm adjustments. It passed **361/361 checks**, with maximum numeric discrepancy **6.245004513516506 × 10⁻¹⁷**; scientific closeout passed **37/37 checks**, and an exact-commit post-push rerun again passed **361/361 checks**. The production analysis required **25.81757343420759 s**, with no new training, model forward pass, checkpoint selection, or scorer call. This retrospective comparator does not establish homology-cluster OOD, causal velocity regulation, biological function, or external SOTA. Functional-untouched data were not accessed, RK-G1 remains false, and generator training remains unauthorized.

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
| RiboMIMO full subtelny14 frozen protocol | `e8ffe1d9646162dcbe9ca40733f0866cf65796446dcd956825cf0b5ba051fc7c` |
| RiboMIMO full subtelny14 production | `41797891a9da5a497e71c165e7bcd38f219ed9eddd3d1ebefdf76173ff738d7e` |
| RiboMIMO full subtelny14 deterministic retrain | `d1f1a2d843113b561fee390cf1c2dfaea251e9c8a0337cec4099c57579163758` |
| RiboMIMO full subtelny14 independent inference | `59a5797c1b497659eefbf3e4edaf4823f8328b8fbf7102777341016ac062bbf5` |
| RiboMIMO full subtelny14 finalization | `b839e0b3e8129c4f342c8eb505296e382798549bdcac9301cb4e8b1107edd957` |
| RiboMIMO full mohammad19_1 frozen protocol | `39213ac1783309903f8bdac918f12f09ef32168b9d1b32868298e7057afbbdf2` |
| RiboMIMO full mohammad19_1 production | `cabd7f1ff81946d7841fbc6855a887d28a938b96188384de8a85a90c0b6adc66` |
| RiboMIMO full mohammad19_1 deterministic retrain | `fc0205d97de8ad902b88364f3e6cf5a183f5de15aab24dfdf66617d9eda64a49` |
| RiboMIMO full mohammad19_1 independent inference | `89dda7f90bb4ba75bfef5083e1435c2c423701d58481dfbf9d7e3dbb5b0ffb2a` |
| RiboMIMO full mohammad19_1 finalization | `d556413566c19f1012a4bea147045e1b28fb106cfc3a80e81a7248f3792850ea` |
| RiboMIMO full mohammad19_2 frozen protocol | `907ba6b6d284c120167253126936f5c5c147271efed0e9e8a70a8fdc35521afb` |
| RiboMIMO full mohammad19_2 production | `5b64a26b1cf4127285223227b979d8e3c639f064bc31e8039c8490d1b1d569e7` |
| RiboMIMO full mohammad19_2 deterministic retrain | `a0f181adf7652b1903241fcac72605659006cfcbeae60afbd9e61f0db1c36267` |
| RiboMIMO full mohammad19_2 independent inference | `9f44aa9809e3117a15e6a91413094809385e787e20ef592ab63783ab09ba33b6` |
| RiboMIMO full mohammad19_2 finalization | `97cf23283c5cafecff00759fb8801d3bc7d74c3a4534939ed0b8b20e9a231662` |
| RiboMIMO full four-matrix summary | `6ff6456f3cb196586dd2fae8910f6424a1077e9d5caf7e9a85287549dbc36967` |
| RiboMIMO full four-matrix summary verification | `80829018aba54ad0d66b81de8d19e9879757db4d58f54354a4d3ecd382d32507` |
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
| RK10 exact trajectory-balance protocol | `38d4c782c18e79ead595d28dc0075512afeb7ea74fc99bcf521e8e6028e2c434` |
| RK10 exact trajectory-balance production | `64af5c02e05932a37611c4863c7b67ef97bfd88a1cb27d893ba0ce766a20c76f` |
| RK10 exact trajectory-balance retrain | `44b50177f0693c562a593b844abdf8313915991a9c5d4407ccc91a6f12207390` |
| RK10 independent NumPy and analytic-oracle verification | `b65b299faff58dbd4214b858c0aafc76da75ab915b88fa9eca6ff31d25e8628a` |
| RK10 exact trajectory-balance finalization | `e5109116088e5cfe76b0b9b3328e320e95ec4027253b20ba7f8d4291012fe4ea` |
| RK10 final unit-test log | `7f6b969142a2d530b443885024e3b22b4bd5368889f18288cba94af528f9d739` |
| RK10 retained initial failed unit-test log | `acb2c82cd461e7336b3ae0c25d97bf95e1caaf255ebf28d8ed1135cd5730c394` |
| RK-11 frozen synthetic neural protocol | `6d4a319df4efe2a59b8997a967b7a2c148ea8595b9e150b0fbac112bd2d67725` |
| RK-11 production CUDA contract | `24efa0bb9f2b33a422428539714b38d17e9f85807878228609003482bffee344` |
| RK-11 independent retrain | `b31bdef74afd94fcbd992242d1af920ba77b4d68a718e72ed2609749a702d628` |
| RK-11 independent numerical verification | `0cca47dd90b3001215311dea2c8fa5c3f001e69eb1162e38b99f79c798c6a6e0` |
| RK-11 finalization | `6d690854f42c59491992a7c46c5f5490de212f625f74ca839c68965bc3b8fbd4` |
| RK-11 final unit tests | `1258d622099e870cbd0972710af0463212e968e58a7fb04bc795e9c977a26aec` |
| RK-11 initial codon-mapping failure | `17fad64b83149d2aa389d1943cb815a47b4283bd14b69d3577cf5e3dd3bdd9c9` |
| RK-11 second test-setup failure | `ae55b3d23510df3a9febcbd4a8062e332aa94919d74a59a441750f47f9ee8bf9` |
| RK-11 first independent failure | `01d4e0bb3dd35a37d700a4fbcbab0283e044fbd20f3d6536987aa6350ef9b3f0` |
| RK-11 second independent failure | `a906fcc8d0eecf05838974b6e255e32358069c4c0c26f411d26074b12f2d27e4` |
| RK-11 development CUDA smoke | `b21808814c3a02f6bff4df52c32ff00907a50ea40321b43d495f8a0ca729cae1` |

| RK-12 frozen LinearDesign grid protocol | `030248d286b668101e274a937f83e7acc30b2ea46d929f8a225777d3d2500b99` |
| RK-12 official unique18 grid | `f983f8bd32750b32900e9e061979a2ee655cda42788477b13049a8e50898eda6` |
| RK-12 independent grid verification | `851c3134c13be682adf58b47c2350c92c11b51dcb47a9ecb9629656514daeded` |
| RK-12 frozen actual-set matrix protocol | `3b9c3d31f996a56b66fe7df6572bd4af00eea660fc43ceb979e708adccdd3709` |
| RK-12 full actual-set matrix | `09f3d1ce9c269408aa4e0a08198faa5316fce7fcbbdefe82d1721cfad31770b6` |
| RK-12 independent actual-set matrix verification | `27c9b9c17692451328b989d25a1a536849aad665f56755740dc4a556c9267f0a` |
| RK-12 finalization | `0eb96092a3e7ee59dd6b91a4d5c7be276407a1b6825a305b305c18248430d1d6` |

| RK02 Mordstein complete 16-file download finalization | `c60a269c31ac49580dded3f98dc14bc1a22b95db3d0f146c20278597da2d62b7` |
| RK02 Mordstein full observed-end production summary | `95fe458fed4d7e37b69d4ec85a8637650207198e8bf4dcaa9aadf0bc10f80177` |
| RK02 Mordstein full observed-end independent verification | `bb7d4e69ec492e550c9e4f58be9ac3c6c93ea2dcdccbd8fad0fcea68ac5b6190` |
| RK02 Mordstein full observed-end finalization | `026e5a4d272d40e6d834de932b9be332869ad1ce5309770e4d5b2e1f9f72d889` |

| RK02 fixed-GFP proxy primary production | `d991aded0e735f700882f4490d34c55af98763064156ede1da1a558f2177f952` |
| RK02 fixed-GFP proxy primary independent verification | `897292a17e06b07c7b76d3d73f8a7815efcb7673fccef86a1a6c931840e027c8` |
| RK02 fixed-GFP proxy primary finalization | `5f1946a4e3d4664feba7d8d68502082938e0020813d2c2d01ec0edb9c5b1ce2f` |
| RK02 fixed-GFP proxy robustness production | `6bfd1381d1bd65b80a42238724b651e6ccce7b7f1c1d5c693568ebce25f55f40` |
| RK02 fixed-GFP proxy robustness independent verification | `abee78c8f5b8aff87af9ef25674a98ccfc2eb9532775ce2a6f8b89e468f23688` |
| RK02 fixed-GFP proxy robustness finalization | `fd49cc491e92fd3a4a6555a6c3a0ee0b3cae6a5f2fb95f09706e4a9a61389d61` |

| RK03 MAGE frozen protocol | `ced52285bd70488c6da6955a1d1f16cdb169a5908ff2cf1e3695b8c059157116` |
| RK03 MAGE dev production | `16b9e17628f56bc413faea0e3bd14f69671fef2f5c0527c19d7587f8617e5f7b` |
| RK03 MAGE independent verification | `b74f4b5365418cc672b60b0bd1e2c8225f4dba32507e02c7513c714b7efe4489` |
| RK03 MAGE finalization | `05b0fd7cc4dd0a022cb932e2fbd8e7af9e4d15d056b666f936a2779512b8d57b` |

| RK-13 frozen EnsembleDesign unique18 protocol | `b449c04d148569d2e626728485a75f6edac21dcbae87ca3c4a48957506e294cd` |
| RK-13 frozen recovery protocol | `3e9a12347ceb9b498e5f099ca43c49ca9fdb47587d39590f7d539c9672465f52` |
| RK-13 preserved failed v1 report | `7414d314823568765bf3b48b936829e314eceebbba6683786339461a0334be96` |
| RK-13 official EnsembleDesign unique18 report | `bbdc24bdf72331e7cb0ceb30d75d152ab88ae2efb5705d00f449560d67922fe2` |
| RK-13 independent EnsembleDesign verification | `288c74d61e8f35f023a6f64d56bbe4d4c93ae416420db14aceb6e166953fd15e` |
| RK-13 frozen seven-method matrix protocol | `f644ed5defa3330b71817387277faf4e2668ffda3f8637638aa1ff7ff8fb313a` |
| RK-13 seven-method actual-set matrix | `29f5c0839135d5ff1bf53141c5016c4495b52ee466bcda6ca3a69f86c320b877` |
| RK-13 independent seven-method matrix verification | `e7ecf5c99b9667ae19a81cd2875e1a892c849f885c9ef3e890ecc1b4875ce17b` |
| RK-13 finalization | `cc2f9aa87b7ed511a087313a12e222259b9e3e34713c36835f67ed9c56479a5b` |

| RK05 CAGFN v4 frozen protocol | `8c8013e0deb3b4f23d35012cf3649ed188dd0a613e38d1528249be7dc62156fa` |
| RK05 CAGFN retained v1 failure | `4444cdc3f9a24ebebc7e5e1cb77e1628c0304a590a2a2848517157e4528fd0a3` |
| RK05 CAGFN retained v2 failure | `7e1ef8c75b0b21bb967bbacb3e3d284dfab72ffaf44901954535ebaddc8b86c4` |
| RK05 CAGFN retained v3 failure | `f70aed80085eb678e391a273cf60505bc2d7041df4201214d7ab31782fb09d2a` |
| RK05 CAGFN official bounded production | `c169931fb8227b349148800b7d5136dede98f18fa31a1fd9b91c8eeeb7fe8b4d` |
| RK05 CAGFN independent raw-output verification | `d5c43d879255104d99c0c05b6e9c5f4a8a47e16e0fa446878b7de0b5430f50ab` |
| RK05 CAGFN finalization | `1a2accb76ad8bd95d4e2dbebe2001f40664c7e79ae3a7cfdfa162fe1decd7acb` |

| RK02 structure-increment frozen protocol v2 | `f3e1911b4c72f34257c998b736b70ca76734c1586f04e40dd48c03f265d9bdb6` |
| RK02 structure-increment retained v1 preflight failure | `7f14453b47f1baf0f6f7f91653b663d3016e03b24cb0a56ebf1a9a9d1aff4a29` |
| RK02 structure-increment production | `eead79375e43f11b22c968a31d41010f8509f03289b8c5c833ecb571bcb4acc3` |
| RK02 structure-increment independent verification | `5d3868ba037877b5952376c7a4db85fa33df5ed3014abc141b728acc50296170` |
| RK02 structure-increment finalization | `c8fca9ae49706dfa7ef1d026cefde922ef461eb1fcfb5a7dab742b370637a1fc` |
| RK02 structure-increment unit tests and CAI cross-check | `5960def1db264c6ce8fe9161ae6505e4b274d0c67903f3953f12c91e692aa603` |

| RK05 RiboMIMO study-OOD frozen protocol | `99f7dd5c80044d04d97f64c24dca28a764c2df7ecac013375d44b5bb86fa46e5` |
| RK05 RiboMIMO study-OOD unit tests | `cf8bd1cc2db3a0707b13543517dfb2f9bd2ff804422ad5b67aa14d00be2c30a5` |
| RK05 RiboMIMO study-OOD production | `0b78fe4cb06294a572928adab63e5f840f13f308274d7a8dbfd0efdb5f85d239` |
| RK05 RiboMIMO study-OOD independent retrain | `d1fec0d5b1341cb3e1c283b2b39dc51dcf8466ff07589625e0008e428718c035` |
| RK05 RiboMIMO study-OOD independent verification | `5cbfcaa35828042a0cb1abda20c7e60e6d6094ad8a0d3407c3f114fd621869e1` |
| RK05 RiboMIMO study-OOD finalization | `1f247fb05c08ff4499be50a6ab5b551d1b76db154cf9f9f882b72af4a9016d0e` |
| RK05 RiboMIMO study-OOD training record | `b8692e0e9811533c78864aaf10abf70cae0f9963b2800abf53a9fd055156a95e` |

| RK03 MAGE nested-development frozen protocol v2 | `e53f9a7de0f79b6ecc992845324d8b1baa6d2f516522403da5522a46f0b89afd` |
| RK03 MAGE nested-development production | `bc87238f21db4cd1cee47b83b12427e5978749369c6593f5b3874e3871b4c18c` |
| RK03 MAGE nested-development independent verification | `3ffe88f6174f415902645c2a649a44ee2e72c1b889aa4933cec9b93c1e3917b7` |
| RK03 MAGE nested-development finalization | `846d79183f1f7a02f7b0f7c9569f33597fd6caaf067adf1d446c7cb82f251599` |
| RK03 MAGE nested-development unit tests | `f6ccd8a8f65c2925285e86cae8b55a1e72f3e6cf7f9a5b119334cd42c6c2a3eb` |

| RK03 source-feasibility frozen protocol | `788f60af14a5b38f5a110cf859017943a0641d388485b017db68ec5254bd93ca` |
| RK03 source-feasibility production | `bc66f985ad6e579f34ac4d03ea04738531788072134ba2c94fac59e512b1441c` |
| RK03 source-feasibility independent verification | `d74484ae5d65c094c9a3d274d96eefa88b293f460c20799235c94d2f823bfdcd` |
| RK03 source-feasibility finalization | `d1c62a3817db05b353d9574dda5a33fa5d316326bd193f07e645b9f5e9067e41` |
| RK03 source-feasibility unit tests | `b9e965dc0529c60f882a5c950ded3a24ea8cc009d968cf3ec12f9b3ddbbbca87` |
| RK03 source-feasibility artifact manifest | `4bc61c4243ae5e350801bd89d691b239f15a456596220f3fe7522b3285c1bf7d` |
| RK06 simple-search dense frozen protocol | `f144397909b6961d961dd86727003accc63f3fa4d316019686f4c649b52d95fb` |
| RK06 simple-search dense production | `d060492c1d6882ad950ccde9782ee5cf2f8b98dfd5d24b0ea16757e6a8d2a052` |
| RK06 simple-search dense independent verification | `2e24fb6434f7e2a6967bd051ca2491fcddac88a408351a2ce0dd2520546ef6df` |
| RK06 simple-search dense finalization | `bcbf1cc2bf299c212588740eb2f15d4ccc2bb693be6d672ebd46145018eab947` |
| RK06 simple-search dense claims | `ddfccf0e6dd14bb99de4623e70e9ad93fe232a4ffded027304ae3ce2d6579ba0` |
| RK03 MAGE OOF comparator protocol v2 | `e5e570e862e20a65b50bf9cb6677aef053c89f974171505d9f2a47f450217c0b` |
| RK03 MAGE OOF comparator production | `50273b7831da130ae74122c0d8d4463f6f472a10eafde2d9dec964dfcd2142ad` |
| RK03 MAGE OOF comparator independent verification | `bbe8a7dc75f8573435b7d4cb5f97360be88c77f7caa60bacf6ac0d310957c745` |
| RK03 MAGE OOF comparator correction record | `ff77c83bfc43072721ed0e38bd2325b56b8151d01d6bfc9d64458b7f6c295297` |
| RK03 MAGE OOF comparator 9-test log | `2ca4618c190e3f0f03d43d794031a634e1c70010f3ea76e0528928151b7fd13b` |
| G0 closeout protocol v2 | `dc173e2d7e4db7e9fd115a20be6db9ee2016c67f78ee65869963f78b7eb00558` |
| G0 unified cost production | `c0510f528615af6ef505aed83dd1c0ec5d1fa75eb900c46f6a363521c2cdd583` |
| G0 independent verification | `1bf177c3ad170d3bd0385efce488402fd8e2e74611a0dc3590499e47acd93a40` |
| G0 finalization | `9775981553bc830b9ac27aa19bf4eab5106a09901fb3863ba8e6ea8df66e4db2` |
| G0 correction record | `859702316cc9ff3e5af61b1dcba49c22b7b3ba228287ed7eee2d473a66b1e0fd` |
| G0 retained v1 protocol | `335158cdb300e1715feaf4d6c45d794c3958d788872cd0cb291309b6ae962710` |
| G0 retained v1 failure log | `fac0023b71b79daaf54e1b7ba5d5f1d4e32573a6df11b73a72247f788395ca83` |
| G0 targeted 9-test log | `808216c1e906665a6311eea3399af7e63a60328f6537b9bcf2f6f7027e943f4a` |
| RK08 channel-screen protocol | `ed46e2bf5d919f57285a7fe81182f9529406512f97f45be3ece829b78af99ba4` |
| RK08 channel-screen preparation | `fe36818f673f39cbad114fc219a010d84ea71074553e9b19d53610ee7ea98d79` |
| RK08 channel-screen frozen selection | `e5ce7720485e569febf4656ab9289d12393aac04dd1642ca017dd1f53a0b26a5` |
| RK08 channel-screen evaluation | `825bb36e0f8bc24586f614916a2090dd22d2fe6162d65508dc7d036250ea45ed` |
| RK08 channel-screen independent verification | `3a5c0c5342e3421fa81298fc893655055c112425551bcc36c1c1c7f200a8565f` |
| RK08 channel-screen finalization | `49d2cefd3e224ce7f2786b4e1e4bdc5c7565a21b21311bd0f04c4e284e8259fe` |
| RK08 channel-screen 8-test log | `1ac5097f9b1721141d775b64948fe62ef3d9d5a6178aa307ca1635084b174b78` |
| RK08 manuscript source section | `47aa365a8a2362b78cc815aa3502a551348fdf48cd9f8e5a6ead182720299a20` |
| RK08 manuscript writing draft check | `a9e62bc5371167bcaaa97a40cd94c0ff8662b4b6a4f5a2eb8bc299df8c7ef534` |
| RK08 manuscript writing status | `03f3d50a3438b29b803777f6e15d837ec97450a22720e0d5619968e861b566d9` |

| RK03 pure-external-RCS frozen protocol | `9efd39ef21672722adde333e28f4e1144983949dfab5a6437a1f45a68e930b45` |
| RK03 pure-external-RCS preparation | `d5e8f16ac9cace99e5ca4ade08f918bcc58b6af9a2528ddb92651d711ebec63f` |
| RK03 pure-external-RCS production | `c39e3f3b42e126abdc3fdc0838c053c17b6c95374e841500e34196b340d663c9` |
| RK03 pure-external-RCS independent verification | `eb4153a3cb3109aff34a6e73006af30387409a64531d4b28143bec17f71da0d2` |
| RK03 pure-external-RCS finalization | `29561b13922e4319715fd511c4b2ac4fa911d893815c722df17e0a96fb58f8e0` |
| RK03 pure-external-RCS 10-test log | `080a6aa9c2cb20d1418801980b49581c773f7e67bfccccf769f4b0a82e3905d2` |
| RK03 pure-external-RCS manuscript source section | `a6848a76b74eff95325de5298458c44794813f74f4afcfb986d486b8f979e4c0` |
| RK03 pure-external-RCS manuscript prepare check | `f7e16584dd7c5e9afa9db6c81342ca0a5bb4facc7cb8889508b751b67718dc06` |
| RK03 pure-external-RCS manuscript draft check | `9001fd2a65dc4a6202f5c763389695acda2b295a580f6edae87ba89445b146f8` |
| RK03 pure-external-RCS manuscript writing status | `03f3d50a3438b29b803777f6e15d837ec97450a22720e0d5619968e861b566d9` |
| RK03 pure-external-RCS retained delivery failure | `a21fde3b388c16e354cf1c79793afa54e7e7efb7d59f883198fff9e28161f97e` |
| RK03 pure-external-RCS delivery correction | `ebcf2fdd95cef0664ac3916e80b5168d246a0903108edc77d23e7da6b4578318` |

| RK08 constant-field frozen protocol | `66ad7cb7b3776b32d0160c9f0bf2ec8bd2a57b64d2a421c7b16070710040f00a` |
| RK08 constant-field preparation | `528c57b2189d5e322ae49d452f54eff29394c6f4610d0bacf45a17ffd1b3dcdb` |
| RK08 constant-field production | `8b064345503e2551be63632632c49d108af020b6a49263d9d87becec4ae883eb` |
| RK08 constant-field independent verification | `e4e4d70b6e517b6428a91e795ee273a555a53c043051942951fc82d28b643f27` |
| RK08 constant-field finalization | `ec67656bf3307540d7191f02b640804ad30fbfc35233bcdd5170caffcac92d1a` |
| RK08 constant-field exact-commit post-push verification | `72ec5e9c4b085846d78c462cb35c3aca023db3a22d4cedf621823d4b066bac81` |
| RK08 constant-field 10-test log | `633e94b1f5f31868282c3747277fb33b0560f329488e867ba094a51daf3f39df` |
| RK08 constant-field manuscript source section | `e54e33ea497f43e6c7462d3c6ee429239fd7d4a712208c68ab759ed023c328e1` |
| RK08 constant-field manuscript prepare check | `f7e16584dd7c5e9afa9db6c81342ca0a5bb4facc7cb8889508b751b67718dc06` |
| RK08 constant-field manuscript draft check | `454fa2b13f27ccae1d30df0147db819a5be0ee8f36dddd3d43df7ca7f31e9ac2` |
| RK08 constant-field manuscript writing status | `03f3d50a3438b29b803777f6e15d837ec97450a22720e0d5619968e861b566d9` |
| RK08 constant-field retained delivery failure | `005a32493c6ac34f03ae91ca8f57940962623381ee2d6bc39dee9bf49bc40b69` |
| RK08 constant-field delivery correction | `321bd948b5c53c2f61b0fb9715d4b0729b058b9864f298d87cc309b54ad45b00` |

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
