# Pure external-RCS comparator on reused MAGE development folds

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
