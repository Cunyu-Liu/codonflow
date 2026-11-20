### 6.34 Boël initiation folding did not improve the frozen protein-OOD comparison

The RK07 proxy comparison used folding energies computed from the CDS alone and therefore did not test the initiation feature supplied by Boël et al. We recovered the author-provided `Gz48v` field, defined in the source study as the UH folding energy for the pET21 5′ UTR together with the first 48 CDS nucleotides. The field was complete for all 6,348 records. These data compare different proteins and nonsynonymous constructs on a 0–5 expression scale; they are not a fixed-protein synonymous library and cannot isolate a causal UTR effect.

Before model fitting, we froze a feature-increment comparison on the existing protein-separated split. The base model contained CAI, GC, full-CDS MFE per nucleotide, local 5′-CDS MFE over 48 nucleotides, and log length; the augmented model added only `source_Gz48v`. We used a fixed multinomial logistic expected-score model with L2 = 0.01 and a fixed histogram gradient-boosting regressor, without hyperparameter search. Train, development, and test contained 5,079, 635, and 634 rows, respectively, and each operational partition contained 556 protein clusters. The four primary endpoints were the augmented-minus-base Spearman correlation and MSE improvement for the two model families. Inference used 20,000 operational-protein-cluster bootstrap replicates, 20,000 within-cluster prediction-swap permutations, and Holm correction across the four tests. Every endpoint required a positive effect, a 95% confidence interval above zero, and Holm-adjusted *p* < 0.05. Development effects were positive but all four intervals crossed zero; development was not used to retune the feature set or models.

The frozen test comparison did not support an initiation-folding increment (Table 6). Logistic Spearman changed from 0.123239 to 0.128580 and MSE from 4.331579 to 4.331129. HistGB Spearman changed from 0.205786 to 0.200735 and MSE from 4.297686 to 4.326146. All four confidence intervals crossed zero, all Holm-adjusted *p* values were 1.000, and none of the four primary endpoints passed. The resulting state is `PROTEIN_OOD_INITIATION_STRUCTURE_INCREMENT_NOT_FULLY_SUPPORTED`.

**Table 6**

*Frozen Protein-OOD Effects of Adding Boël UH Folding Energy*

| Model | Endpoint | Base | Augmented | Effect | 95% CI | Holm *p* |
|---|---|---:|---:|---:|---:|---:|
| Logistic | Spearman | 0.123239 | 0.128580 | +0.005341 | [−0.028391, 0.038772] | 1.000 |
| Logistic | MSE improvement | 4.331579 | 4.331129 | +0.000449 | [−0.058058, 0.059025] | 1.000 |
| HistGB | Spearman | 0.205786 | 0.200735 | −0.005051 | [−0.038226, 0.027886] | 1.000 |
| HistGB | MSE improvement | 4.297686 | 4.326146 | −0.028460 | [−0.130563, 0.073041] | 1.000 |

*Note.* Base and augmented values for MSE rows are MSE; effect is base MSE minus augmented MSE, so positive values indicate improvement. Base features are CAI, GC, full-CDS MFE per nucleotide, local 5′-CDS MFE over 48 nucleotides, and log length. Augmented features add author-provided UH folding energy. CI denotes confidence interval; MSE denotes mean squared error.

A secondary comparison that replaced the base feature set with CAI, GC, and log length was descriptive only. Its test point estimates were positive: HistGB gained 0.061364 Spearman and 0.180757 MSE improvement, while logistic gained 0.009044 Spearman and 0.021717 MSE improvement. These comparisons were outside the preregistered four-test Holm family, received no confirmatory significance claim, and cannot reverse the negative primary result. They also do not establish superiority over the stronger preregistered base model.

We separately audited the optimized-construct and Figure 5 source tables for a possible fixed-protein numerical check. The optimized-construct sheet contained 25 rows, 24 unique construct names, and five protein groups, with one duplicated `RSP_2139-31C-FO/31C-FO` row. Its `p025`, `p50`, and `p975` fields are model prediction quantiles rather than measured expression. Figure 5 provided numerical growth curves for RSP_2139 and SRU_1983 but no fixed-protein expression table. We therefore did not execute that numerical mechanism test, digitize plotted expression values, or recycle model predictions as functional ground truth.

Independent implementations retrained every model and regenerated all development and test predictions, metrics, bootstrap arrays, and permutation arrays without importing the RK23 or RK07 production modules. Development acceptance passed 177/177 checks and test acceptance passed 275/275 checks; maximum production-versus-independent differences were zero for predictions, metrics, bootstrap results, and permutation results. The retained history includes two pre-resampling interface corrections, 14/14 synthetic tests, and a verifier-only correction after it initially assumed that length and GC included the terminal stop codon. These corrections did not alter the frozen scientific features, labels, models, endpoints, or outputs.

This test is a reused protein-OOD evaluation, not global untouched confirmation. It does not contradict the distinct fixed-GFP development result in Section 6.33, because the datasets, contrasts, and estimands differ. It establishes neither velocity nor decay mechanisms, fixed-protein synonymous transport, functional untouched performance, CodonFlow-RK generation, or external SOTA. RK-G1 remains false, expensive generator training remains unauthorized, functional untouched data were not accessed, and the manuscript remains non-submittable.
