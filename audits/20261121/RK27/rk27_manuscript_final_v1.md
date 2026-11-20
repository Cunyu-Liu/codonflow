### 6.38 Measured 5′ MFE improved fixed-GFP sequence-cluster transport in a retrospective analysis

RK22 identified a strong 5′ minimum-free-energy (MFE) increment in random-fold development cross-validation, but did not test whether that increment transported across sequence clusters. RK27 therefore evaluated the same measured feature under whole-cluster holdout within the fixed GFP background. Because the expression labels had already been used for RK22 development, the analysis was prespecified as retrospective sequence-cluster transport validation, not independent untouched confirmation. Before model fitting, the coverage audit read only source-row, CDS, and protein annotations; expression and model features were excluded. The RK04 functional-untouched split was not read.

The 154 measurement rows were aggregated to 150 unique exact CDSs, all encoding the same 720-nucleotide GFP. The frozen 90% complete-linkage rule produced 37 sequence clusters, including 13 singleton clusters; the largest cluster contained 61 sequences. Primary-seed fold sizes were 23, 61, 22, 22, and 22 sequences. The simple model contained CAI, CDS GC, and CDS GC3, whereas the structure model added measured 5′ MFE. Ridge and histogram gradient boosting (HistGB) were evaluated over 10 fold-assignment seeds and five folds, giving 300 CPU model fits. MFE-only models were descriptive references. Primary inference used 20,000 sequence-cluster bootstrap replicates and 20,000 paired whole-cluster simple/structure swaps, with Holm correction across four endpoints.

**Table 10**

*Measured 5′ MFE Increment Under Fixed-GFP Sequence-Cluster OOD Evaluation*

| Model | Endpoint | Observed effect | 95% cluster-bootstrap CI | Holm *p* | Positive seeds |
|---|---|---:|---:|---:|---:|
| Ridge | ΔSpearman | 0.955051 | [0.493814, 1.106833] | 0.00019999 | 10/10 |
| Ridge | MSE improvement | 0.157489 | [0.071313, 0.212686] | 0.00129994 | 10/10 |
| HistGB | ΔSpearman | 0.412578 | [0.208828, 0.520318] | 0.00044998 | 10/10 |
| HistGB | MSE improvement | 0.105907 | [0.042279, 0.140561] | 0.00129994 | 10/10 |

*Note.* ΔSpearman = structure − simple; MSE improvement = simple − structure, so positive values favor adding measured 5′ MFE. Each endpoint required a positive effect, a 95% CI excluding zero, Holm *p* < 0.05, and the same positive direction in at least 8 of 10 fold-assignment seeds. OOD denotes out-of-distribution; MSE denotes mean squared error.

All four frozen endpoints passed, and each was positive in all 10 seeds (Table 10). Under the primary seed, ridge Spearman/MSE changed from −0.318413/0.257149 for the simple model to 0.636638/0.099660 for the structure model; the corresponding HistGB values changed from 0.302424/0.198658 to 0.715002/0.092751. Descriptive MFE-only Spearman/MSE values were 0.605020/0.111354 for ridge and 0.637557/0.101574 for HistGB. These MFE-only arms did not replace the confirmatory structure-versus-simple comparison or introduce an additional requirement that the combined model outperform MFE alone. The resulting outcome was `FIXED_PROTEIN_SEQUENCE_CLUSTER_OOD_MFE_INCREMENT_SUPPORTED_RETROSPECTIVELY`.

Production and coverage synthetic tests passed 14/14 checks, and independent-implementation synthetic tests passed 8/8. The independent verifier reconstructed clustering, aggregation, all model fits, and resampling from the raw CDSs without importing the production modules; final acceptance passed 47/47 checks. The retained initial report passed 46/47 checks because pandas interpreted the literal model-arm label `null` as missing during a metrics-table merge. Both tables actually contained 70 rows with matching keys. Only the verifier’s CSV parsing was corrected, and neither the models nor statistical results changed. Scientific closeout and registry binding passed 97/97 checks.

This result supports a measured 5′ MFE increment for retrospective sequence-cluster transport within one fixed GFP study. It is not independent external confirmation or protein OOD evidence, and it provides no measurement of translation velocity, mRNA decay, or complete spatial coupling. It does not establish CodonFlow-RK superiority, external SOTA, or functional untouched performance. RK-G1 remains false and expensive generator training remains unauthorized; the next appropriate test is an independent fixed-protein functional dataset rather than generator training. The manuscript remains a non-submittable working draft.
