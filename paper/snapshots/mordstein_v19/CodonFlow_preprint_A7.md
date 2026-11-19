# Learning structure–translation–decay coupling for synonymous mRNA design

> **Status: A8-RK working manuscript — not for submission.** CodonFlow-RK and its functional/mechanistic experiments are proposed, not completed. The original A7 open-loop model failed G2; learned-hill showed positive but costly development associations. No SOTA, independent generalization, biological-function improvement, or prospective experimental claim is currently authorized.

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

### 3.1 Natural, mechanistic and functional data

Natural CDS–protein pairs provide sequence and host priors, not functional labels. In addition to the audited D4/D5 corpora, candidate external corpora include CodonTransformer and RNARL datasets. Mechanistic data include the five-organism Ribo-seq resources used by VeloHARMO, fixed UTR–CDS contexts and structural/accessibility measurements or calculations. Ribo occupancy is interpreted as a relative, experiment-dependent proxy for translation dynamics rather than an absolute elongation rate.

Functional supervision is restricted to experimentally measured synonymous variants with traceable sequence and assay context. Priority datasets are the 154 GFP variants from Kudla et al., the Protein Data Set underlying the 6,348 experiments of Boël et al., and the 12,726 infA codon mutants from MAGE-seq. Published LinearDesign, GEMORNA or COformer sequences are included only when sequence and measurement context can be recovered. The primary Dasher and six-protein data from Theodorou et al. are not publicly available and are not used [theodorou2026machine].

Every external dataset remains `candidate` until actual download, translation checks, sample reconciliation and hash registration are complete. Functional values retain their original units, replicate noise, assay, batch, vector, UTR and host. Normalization is performed within `protein×host×assay×batch` groups and fitted only on training data.

### 3.2 Leakage-controlled generalization tasks

Exact CDS, exact protein, identifiers, operational protein-homology clusters and functional source proteins are audited across splits. Variants of the same protein never cross random train/test partitions. Functional prediction uses protein-level OOD; Ribo-seq models additionally use study-level OOD; natural sequence models retain homology-cluster OOD. Length and GC strata evaluate difficult regimes rather than define new tuning sets.

D4 contains 621,306/76,444/78,724 train/validation/test records. D5 contains 618,073/80,191/78,177 records and uses MMseqs2 identity 0.5 with bidirectional coverage 0.8. These are operational splits, not curated family- or species-level proof. The existing unique18 set is development-only. Untouched24 and a separate functional untouched set are evaluated once after all choices are frozen.

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

### 6.2 Proxy validity on real synonymous variants

[Pending RK-G0/G1. Report every assay and OOD split, including cases where simple proxies work.]

### 6.3 Incremental evidence for spatial coupling

[Pending RK-G1. Insert matched initiation, velocity, decay and pair-channel ablations with protein/study OOD and uncertainty.]

### 6.4 Cross-layer structure–translation–decay consistency

[Pending RK-G1. Connect MAGE fitness, Ribo velocity and Boël mRNA/protein outcomes; distinguish association from causation.]

### 6.5 Task-specific strongest-baseline comparisons

[Pending RK-G2. Use separate tables for function, velocity, harmonization, accessibility and multi-objective CDS design. Do not pool incompatible tasks into one rank.]

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
