<!-- A8_RK31_START -->
### 6.42 Known-context gating did not support broad MFE applicability

RK31 asked whether explicit context-dependent MFE slopes improved variant-level out-of-distribution prediction when the three Mordstein contexts were known but sequence clusters were held out jointly. It reused the independently verified RK30 analysis table containing 126 variants in 69 clusters and did not download new reads, recluster variants, or select variants by outcome. The analysis was registered as a retrospective outcome-known follow-up, not an independent untouched confirmation or an unseen-context transport experiment.

The simple features were GC3, GC, CpG, and CAI. Full arms added full-fragment MFE and 48-nt-window minimum and mean MFE. Shared-simple and shared-full models pooled contexts with two nonreference context indicators. The context-gated-full arm added six context-by-MFE interactions while retaining shared simple-feature slopes. Separate no-transport-simple and no-transport-full models were fit within each context, and a training-fold context mean supplied a descriptive null reference. Ridge used the RK30 fold-internal scaling and a frozen alpha of 1.0 without hyperparameter search. The frozen evaluation used 10 seeds, 5 whole-cluster folds per seed, and 450 real CPU fits. A cluster held out in one context was excluded from training in every context, and outcomes of held-out variants in other contexts were never predictors.

The candidate was context-gated full. It was compared with shared simple, shared full, no-transport simple, and no-transport full using Spearman effects and MSE improvement in each context. The resulting 24 endpoints formed one Holm family. Inference used 10,000 whole-cluster bootstraps and 10,000 cluster sign-swap permutations. An endpoint required a positive primary-seed observed effect, a 95% CI lower bound above zero, Holm *p* < 0.05, and at least 8/10 positive seeds. Broad known-context applicability required all 24 endpoints to pass; the six gated-versus-shared-full endpoints were also examined separately as the direct gating subset.

**Table 17**

*Known-Context Gated-MFE Primary Endpoints*

| Context | Baseline | Endpoint | Observed effect | 95% CI | Holm *p* | Positive seeds | Decision |
|---|---|---|:---:|:---:|:---:|:---:|:---:|
| HeLa no intron | Shared simple | ΔSpearman | 0.0215613048 | [-0.0658072199, 0.114118811] | 1 | 4/10 | FAIL |
| HeLa no intron | Shared simple | MSE improvement | 0.000805353385 | [-0.0539636114, 0.0592069245] | 1 | 1/10 | FAIL |
| HeLa no intron | Shared full | ΔSpearman | 0.0517555306 | [0.00127547868, 0.114513377] | 1 | 10/10 | FAIL |
| HeLa no intron | Shared full | MSE improvement | 0.0220560745 | [-0.0132333254, 0.0630287391] | 1 | 10/10 | FAIL |
| HeLa no intron | No-transport simple | ΔSpearman | -0.032575928 | [-0.168529633, 0.0912518755] | 1 | 0/10 | FAIL |
| HeLa no intron | No-transport simple | MSE improvement | -0.0187220395 | [-0.0985962484, 0.0615569618] | 1 | 0/10 | FAIL |
| HeLa no intron | No-transport full | ΔSpearman | -0.00493738283 | [-0.108270435, 0.0888721086] | 1 | 3/10 | FAIL |
| HeLa no intron | No-transport full | MSE improvement | -0.00122546886 | [-0.0607184996, 0.0563998466] | 1 | 6/10 | FAIL |
| HeLa with intron | Shared simple | ΔSpearman | -0.244457443 | [-0.505408325, 0.0581034677] | 1 | 0/10 | FAIL |
| HeLa with intron | Shared simple | MSE improvement | -0.0119289677 | [-0.148275389, 0.121883885] | 1 | 1/10 | FAIL |
| HeLa with intron | Shared full | ΔSpearman | -0.258309711 | [-0.512513887, 0.0176412035] | 1 | 0/10 | FAIL |
| HeLa with intron | Shared full | MSE improvement | -0.0126477864 | [-0.149180503, 0.11735717] | 1 | 4/10 | FAIL |
| HeLa with intron | No-transport simple | ΔSpearman | -0.367604049 | [-0.633698274, -0.0900242775] | 0.223077692 | 0/10 | FAIL |
| HeLa with intron | No-transport simple | MSE improvement | -0.120715339 | [-0.222005479, -0.0199667055] | 0.541145885 | 0/10 | FAIL |
| HeLa with intron | No-transport full | ΔSpearman | -0.368035996 | [-0.591063437, -0.136843507] | 0.0311968803 | 0/10 | FAIL |
| HeLa with intron | No-transport full | MSE improvement | -0.0838776759 | [-0.215786264, 0.0359966968] | 1 | 0/10 | FAIL |
| HEK293 no intron | Shared simple | ΔSpearman | -0.0605384327 | [-0.14921863, 0.0225858849] | 1 | 0/10 | FAIL |
| HEK293 no intron | Shared simple | MSE improvement | -0.0777553167 | [-0.169821533, 0.0236011558] | 1 | 0/10 | FAIL |
| HEK293 no intron | Shared full | ΔSpearman | 0.0172538433 | [-0.0276009825, 0.0707085402] | 1 | 10/10 | FAIL |
| HEK293 no intron | Shared full | MSE improvement | -0.0276153957 | [-0.111650076, 0.0635911502] | 1 | 4/10 | FAIL |
| HEK293 no intron | No-transport simple | ΔSpearman | -0.0893708286 | [-0.186834147, 0.00464313018] | 1 | 0/10 | FAIL |
| HEK293 no intron | No-transport simple | MSE improvement | -0.102358146 | [-0.231276001, 0.0364778435] | 1 | 0/10 | FAIL |
| HEK293 no intron | No-transport full | ΔSpearman | -0.0798860142 | [-0.195649443, 0.0262154085] | 1 | 0/10 | FAIL |
| HEK293 no intron | No-transport full | MSE improvement | -0.0505305939 | [-0.203415228, 0.104344649] | 1 | 0/10 | FAIL |

*Note.* ΔSpearman = candidate − baseline; MSE improvement = baseline − candidate. Observed effects and resampling inference use frozen primary seed 20261222; positive-seed counts summarize all 10 seeds. CI denotes the 95% whole-cluster bootstrap confidence interval. The family-wise Holm adjustment spans all 24 endpoints. The literal null arm is a valid model label, not missing data.

No primary endpoint passed, and the context-level decision was false for HeLa no intron, HeLa with intron, and HEK293 no intron. The direct gating subset also failed. A descriptive positive point pattern did not override this decision: in HeLa no intron, gated full versus shared full had a primary-seed Spearman effect of 0.0517555306, a 95% CI of [0.00127547868, 0.114513377], 10/10 positive seeds, and Holm *p* = 1. The corresponding MSE improvement was 0.0220560745, with a 95% CI of [-0.0132333254, 0.0630287391], 10/10 positive seeds, and Holm *p* = 1. Both endpoints failed the frozen joint rule.

An adverse comparison was also retained rather than removed. In HeLa with intron, gated full versus no-transport full had a primary-seed Spearman effect of -0.368035996, a 95% CI of [-0.591063437, -0.136843507], Holm *p* = 0.0311968803, and 0/10 positive seeds. This result does not identify a causal mechanism, but it directly contradicts interpreting the gated model as a uniformly beneficial applicability strategy.

**Table 18**

*Absolute Known-Context Variant-OOD Performance at the Primary Seed*

| Context | Arm | Spearman | MSE |
|---|---|:---:|:---:|
| HeLa no intron | Null | -0.219966927 | 1.20918171 |
| HeLa no intron | Shared simple | 0.28208174 | 1.08573753 |
| HeLa no intron | Shared full | 0.251887514 | 1.10698825 |
| HeLa no intron | No-transport simple | 0.336218973 | 1.06621013 |
| HeLa no intron | No-transport full | 0.308580427 | 1.0837067 |
| HeLa no intron | Context-gated full | 0.303643045 | 1.08493217 |
| HeLa with intron | Null | -0.207509961 | 1.12987 |
| HeLa with intron | Shared simple | -0.0492388451 | 1.23319815 |
| HeLa with intron | Shared full | -0.0353865767 | 1.23247933 |
| HeLa with intron | No-transport simple | 0.0739077615 | 1.12441178 |
| HeLa with intron | No-transport full | 0.0743397075 | 1.16124944 |
| HeLa with intron | Context-gated full | -0.293696288 | 1.24512712 |
| HEK293 no intron | Null | -0.119711162 | 1.82869 |
| HEK293 no intron | Shared simple | 0.291464567 | 1.68510592 |
| HEK293 no intron | Shared full | 0.213672291 | 1.73524584 |
| HEK293 no intron | No-transport simple | 0.320296963 | 1.66050309 |
| HEK293 no intron | No-transport full | 0.310812148 | 1.71233065 |
| HEK293 no intron | Context-gated full | 0.230926134 | 1.76286124 |

*Note.* Values use frozen primary seed 20261222. Null is the training-fold context mean. These are retrospective fixed-Flow-seq outcomes, not direct RFU, translation velocity, mRNA decay, functional validation, or an external SOTA comparison.

The resulting conclusion was `KNOWN_CONTEXT_GATED_MFE_APPLICABILITY_NOT_SUPPORTED`. This rejects the frozen broad known-context applicability claim; it does not establish that every possible context-dependent mechanism is ineffective. Production required 76.856193 s and independent recomputation required 88.271249 s. The independent implementation did not import production or RK28 helpers and passed 177/177 checks. Maximum absolute differences were 7.90479e-14 for predictions, 1.24345e-14 for metrics, 1.17198e-14 for seed effects, 1.64868e-14 for inference arrays, and 1.17129e-14 for primary confidence intervals. Release closeout passed 22/22 checks, and project testing passed 423 tests with one skipped test.

A separate clean checkout at 414b30d267039cc1cdf3fdb26ebf2e5f2a0756b7 repeated the complete analysis and independent verification. The clean comparison passed 77/77 checks: all five CSV artifacts were byte-identical and all 54 inference arrays matched exactly. Clean production and independent verification required 84.648084 and 77.688392 s, respectively. The retained history includes an initial provenance-gate stop before any fit and an initial independent-report failure caused by literal `null` being parsed as missing; the corrected provenance check and literal-null parsing did not alter the scientific definitions or production artifacts.

RK31 does not read functional-untouched data, authorize generator training, perform wet-lab or prospective design–build–test work, establish protein OOD, close complete external SOTA, or complete RK-G1. The manuscript remains a non-submittable working draft. Complete external SOTA, unified time-matched comparison, dense budget-step trajectories, functional OOD, and the RK-G1 generation decision remain open rather than being reclassified as completed by this retrospective result.

<!-- A8_RK31_END -->
