### 6.31 Real generation-call dense-prefix comparison on unique18

The remaining external-baseline gap was that actual-set outputs did not show how performance accumulated across successive generation calls. We therefore froze a dense-prefix analysis before reading the results. The primary panel comprised 18 unique18 development records and four methods with complete ordered raw outputs: LinearDesign with 11 lambda values, codonGPT, uniform synonymous sampling, and the 11-run EnsembleDesign set. Each method was evaluated at budgets B=1,...,11, yielding 792 primary generation-call positions. Duplicate sequences remained at their original call positions; no deduplication, zero-filled budget, synthetic origin, or unordered-set interpolation was used. Previously accepted exact sequence objectives and per-record hypervolume calibration were reused. Dense AUC was the mean normalized hypervolume over B=1,...,10, and B=11 hypervolume was a separate endpoint. LinearDesign was compared with each of the other three methods using 20,000 record-paired bootstrap replicates, and all six primary tests were corrected together by the Holm method.

LinearDesign had the highest mean value on both primary endpoints, as summarized in Table 3. EnsembleDesign ranked second among these four methods. CodonGPT and uniform synonymous sampling had substantially lower mean dense AUC and B=11 hypervolume. A descriptive extension to B=100 was retained only for codonGPT and uniform synonymous sampling, whose raw outputs supported that range; it was not included in the primary Holm family. Over B=1,...,99, their mean dense AUC values were 11.851796 and 1.330156, respectively, and their B=100 hypervolume values were 14.537219 and 1.718763.

**Table 3**

*Mean Dense-Prefix Performance Over 18 Development Records*

| Method | Dense AUC, B=1–10 | Normalized hypervolume, B=11 |
|---|---:|---:|
| LinearDesign-11 | 22.794606 | 29.972887 |
| EnsembleDesign-11 | 14.896234 | 16.693982 |
| codonGPT | 5.205444 | 7.989211 |
| Uniform synonymous | 0.702952 | 0.966618 |

*Note.* AUC denotes area under the dense budget-step hypervolume curve, computed as the unweighted mean over B=1,...,10. Normalized hypervolume was not clipped to [0,1].

All six prespecified LinearDesign-minus-comparator effects were positive, with 95% confidence intervals entirely above zero and Holm-adjusted *p* = 0.00059997 (Table 4). The frozen two-endpoint gate therefore passed against codonGPT, uniform synonymous sampling, and EnsembleDesign. This establishes dense generation-call efficiency on the evaluated proxy objectives and development records; it does not establish that LinearDesign is faster per unit wall time or better on biological function.

**Table 4**

*Paired LinearDesign Improvements in the Frozen Primary Family*

| Comparator | Endpoint | Mean effect [95% CI] | Holm *p* |
|---|---|---:|---:|
| codonGPT | Dense AUC | +17.589162 [+11.334443, +24.621194] | 0.00059997 |
| codonGPT | B=11 hypervolume | +21.983676 [+12.613876, +32.906748] | 0.00059997 |
| Uniform synonymous | Dense AUC | +22.091655 [+15.135915, +30.502155] | 0.00059997 |
| Uniform synonymous | B=11 hypervolume | +29.006270 [+18.976333, +41.514897] | 0.00059997 |
| EnsembleDesign-11 | Dense AUC | +7.898372 [+4.214060, +12.023210] | 0.00059997 |
| EnsembleDesign-11 | B=11 hypervolume | +13.278905 [+6.933435, +20.795086] | 0.00059997 |

*Note.* Effects are LinearDesign minus the named comparator. Confidence intervals and Holm-adjusted sign-test probabilities used 20,000 record-paired bootstrap replicates.

An independent verifier reconstructed all curves, hypervolumes, dense AUC values, paired effects, intervals, and Holm adjustments from the hashed raw inputs and passed **88/88 checks**. A separate finalization binding passed **53/53 checks**, and the complete project CPU suite reported **347 passed, 1 skipped, 11 warnings, and 5 subtests passed in 27.39 s**. Legacy-schema execution failures, the verifier-only summary-field correction, and derivative-CSV line-ending normalization were retained without changing the protocol, raw inputs, primary statistics, or full scientific matrix. GEMORNA, the legacy LinearDesign scan, and CAI-greedy were excluded from dense ranking because their required repeated raw call trajectories were unavailable. This section closes only the four-method dense-prefix comparison. Unified time-matched evaluation, the complete seven-method dense panel, CodonFlow-RK generation, functional OOD and untouched evaluation, and external SOTA remain open. RK-G1 remains false, expensive generator training remains unauthorized, and the manuscript remains non-submittable.
