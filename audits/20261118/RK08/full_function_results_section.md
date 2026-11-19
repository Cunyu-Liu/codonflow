### Same-backbone mechanism-channel ablation on Boël sequence-OOD

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

*Note.* CB-MSE denotes cluster-balanced mean squared error; lower values are better. Spearman and row R² were computed on the same 1,336 OOD constructs. The full-proxy ridge remained the development-selected primary baseline. HistGB is reported descriptively and was not used for post hoc primary-model selection.

Paired cluster bootstrap with 2,000 resamples supported an increment over the same-backbone no-channel model. The all-minus-none difference in Spearman was 0.199016 (95% CI [0.129283, 0.266863]), and the difference in CB-MSE was -0.276089 (95% CI [-0.377439, -0.180840]). Relative to GC-only ridge, the corresponding differences were 0.120221 (95% CI [0.082462, 0.157406]) for Spearman and -0.289516 (95% CI [-0.350624, -0.225776]) for CB-MSE. Both intervals excluded zero in the direction favoring the all-channel model.

The all-channel model did not outperform the full-proxy ridge on either OOD endpoint. Its Spearman difference was -0.025779 (95% CI [-0.071103, 0.019376]; Holm-adjusted p = 0.522), and its CB-MSE difference was -0.025572 (95% CI [-0.124069, 0.076207]; Holm-adjusted p = 0.595). Thus, the preregistered RK-G1 criterion was not met. The low absolute R² values and the more favorable HistGB point estimates further preclude an SOTA or broad superiority claim.

These results support a limited inductive-bias interpretation: the four channels improved the shared backbone relative to no channels and GC-only regression, but did not establish superiority over the full proxy set. This experiment used cross-protein, nonsynonymous constructs and function-only supervision. It therefore does not validate fixed-protein synonymous mechanisms, and the initiation, velocity, and decay outputs are not validated mechanism-specific estimates. Velocity OOD and generator readiness remain unevaluated, and expensive generation training remains unauthorized. Two complete retraining runs were bitwise identical, while independent verification passed 224 of 224 checks and finalization passed 48 of 48 checks. Clean-environment reproduction remains outstanding.
