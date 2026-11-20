# Development-selected mechanism-channel screen

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
