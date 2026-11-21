# Common-Input Actual-Set Evaluation

To separate search behavior from differences in native initialization and archive cardinality, we evaluated 18 development records with three seeds under the frozen RK39_COMMON_INPUT_ACTUAL_SET_V1 protocol. The native CDS was translated and then discarded as a source of synonymous choices. Every simple-search run used the same protein-derived first-synonymous-codon template, RNG-only synonymous initialization, and TAA termination; native calibration normalization was disabled during generation and restored only afterward for common evaluation. For each record-seed pair, every simple-search method contributed its first *k* unique-scorer outputs, where *k* was LinearDesign-11's observed unique-DNA output count. This cardinality-matching rule was fixed before outcome inspection and did not select the best *k* points or a favorable subset. The full factorial comprised 162 runs and 1,782 unique-scorer evaluations across hill-climbing, MH-annealing, and uniform search.

The primary comparison was hill-climbing against LinearDesign-11, with MH-annealing and uniform search prespecified as diagnostic sensitivity arms. Normalized HV and pairwise NED were co-primary endpoints. Each endpoint was averaged across seeds within a record before paired record-level inference with 20,000 bootstrap replicates, 20,000 sign-flip replicates, and Holm correction across the two endpoints. Success required a positive lower 95% confidence bound and Holm-adjusted *p* < 0.05 for both endpoints, together with a positive effect for every seed. These requirements were evaluation rules rather than claims that the proxy objectives establish biological quality.

LinearDesign-11 outperformed hill-climbing on both primary endpoints for all 18 records, and the direction was negative for every seed. The HV effect was -29.714618, with a 95% CI of [-41.925699, -19.552535], while the pairwise-NED effect was -0.066598, with a 95% CI of [-0.082247, -0.051135]. The Holm-adjusted *p* value was 9.9995 × 10^-5 for each endpoint. Thus, the primary gate failed because both effects were significantly negative, not because the estimates were inconclusive. Table 32 reports absolute performance, and Table 33 reports the paired effects.

**Table 32**

*Absolute Actual-Set Performance Under Common Protein Input and Matched Cardinality*

| Method | Normalized HV | Pairwise NED |
|:---|---:|---:|
| LinearDesign-11 | 29.972887 | 0.071289 |
| Simple-search hill-climbing | 0.258270 | 0.004692 |
| Simple-search MH-annealing | 0.259383 | 0.004857 |
| Simple-search uniform | 0.720246 | 0.240866 |

*Note.* Values are means over 18 records after averaging three seeds within each record. HV = hypervolume; NED = normalized edit distance. Simple-search archives were truncated to LinearDesign-11's observed per-record unique-DNA cardinality. These are proxy-objective measurements, not functional-expression results.

**Table 33**

*Paired Method Effects Against LinearDesign-11*

| Comparison | Endpoint | Effect | 95% CI | Holm-adjusted *p* | Records with positive effect |
|:---|:---|---:|:---:|---:|:---:|
| Hill-climbing | Normalized HV | -29.714618 | [-41.925699, -19.552535] | 9.9995 × 10^-5 | 0/18 |
| Hill-climbing | Pairwise NED | -0.066598 | [-0.082247, -0.051135] | 9.9995 × 10^-5 | 0/18 |
| MH-annealing | Normalized HV | -29.713504 | [-41.906970, -19.520039] | 9.9995 × 10^-5 | 0/18 |
| MH-annealing | Pairwise NED | -0.066432 | [-0.082086, -0.050778] | 9.9995 × 10^-5 | 0/18 |
| Uniform | Normalized HV | -29.252642 | [-41.501038, -19.021988] | 9.9995 × 10^-5 | 0/18 |
| Uniform | Pairwise NED | 0.169577 | [0.154041, 0.185631] | 9.9995 × 10^-5 | 18/18 |

*Note.* Effects are simple-search method minus LinearDesign-11 after within-record seed averaging. Confidence intervals and sign-flip tests used 20,000 replicates. Positive records are counted from record-level effects after seed averaging. The sensitivity-arm results cannot rescue the failed hill-climbing primary gate.

MH-annealing was also worse than LinearDesign-11 on both endpoints for all 18 records. Uniform search increased pairwise NED by 0.169577, with all 18 record effects positive, but simultaneously reduced normalized HV by 29.252642, with all 18 effects negative. This divergence is a proxy-level quality-diversity tradeoff, not a win on the frozen task. In particular, pairwise NED measures within-archive sequence diversity and must not be interpreted as an independent measure of functional design quality.

An independent verifier re-read all 162 raw runs, reconstructed the protein-only initial states, retranslated the proteins, recomputed all four objectives for 1,594 unique sequences, and repeated the actual-set metrics and paired inference. All 1,216 checks passed. The maximum absolute discrepancy across the four objectives was 0.0, and the independent analysis reproduced both effect estimates and the unresolved-task decision exactly.

A second complete clean execution of the verified code at commit b3f89b94 was then compared point by point with the independently verified production run. All 830 closeout checks passed, covering initial states, sequences, budgets, objective vectors within 10^-12, actual-set metrics, inference, decision, and scientific boundaries. Wall-clock time and artifact hashes were excluded from numerical equivalence.

The common-input actual-set task therefore remains unresolved. These results do not establish CodonFlow superiority, external SOTA, time-matched performance, functional improvement, protein-OOD generalization, or untouched-confirmation success. Earlier native-initialization comparisons cannot override this conclusion because they evaluated a different initialization and evaluation contract.
