# A train-only constant relative-position field outperforms both velocity predictors on Subtelny14

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
