### 6.44 A 42-nt local MFE does not add robust observed-R1 structure signal under matched sequence-cluster holdout

RK32 established that local start-aware definitions can carry expression signal in the fixed Kudla GFP library, but it could not transport that result to Mordstein because the observed R1 fragment begins at CDS position 4. RK33 therefore asked a narrower, directly executable question: within the same observed-R1 representation, does a 42-nt CDS4–45 minimum free energy (MFE) add robust signal beyond the existing sequence and full-fragment definitions? This was a retrospective, outcome-known coverage follow-up, not an independent confirmation or a test of RNA velocity. The same 152 HEK293 variants, 74 whole-sequence clusters, 1,520 seed–fold assignments, simple sequence features, Ridge and histogram gradient-boosting models, and statistical inference were held fixed.

Four arms were frozen before model fitting: simple sequence only; simple plus one local42 MFE; simple plus one full-300 MFE (full1); and the previously accepted RK28 full-300 plus 48-nt minimum/mean MFE three-feature arm (full3). ViennaRNA was evaluated at 37 °C with dangling ends disabled. Only local42 and full1 required new fitting, giving 10 seeds × 5 folds × 2 models × 2 arms = 200 new fits; 200 accepted simple/full3 fits were reused, for 400 evaluated fits. Three paired comparison families—local42 versus simple, full1, and full3—each contained Ridge Spearman, Ridge MSE improvement, HistGB Spearman, and HistGB MSE improvement endpoints. Each endpoint required a positive observed effect, a whole-cluster bootstrap lower confidence limit above zero, a unified Holm-adjusted cluster-swap permutation p-value below 0.05, and at least eight positive seeds. All 12 endpoints were required for structural support.

The label-free preflight passed 21/21 checks, including 152 unique 300-nt sequences, 93 unique local42 subsequences, fold sizes of 30/31/31/30/30 variants, and zero whole-cluster leakage across all 50 seed–fold assignments. Both synthetic production suites passed 18/18 checks. The first production attempt stopped before any new model fit because a zero-tolerance CSV target comparison was sensitive to floating-point text round trips. The correction changed only this identity comparison to a 1e-12 absolute tolerance; feature definitions, folds, models, endpoints, and seeds were unchanged, and the failed console log was retained.

**The prespecified decision was not supported: 0/12 endpoints passed and all three family gates were false (Table 21).** Every 95% confidence interval crossed zero, and every unified Holm-adjusted p-value was 1.0. The minimum unadjusted cluster-swap p-value was 0.167992, so the negative decision was not produced solely by multiplicity correction. For local42 versus simple, Ridge effects were negative, whereas HistGB point estimates were positive but highly uncertain. For local42 versus full1, Ridge again favored neither local coverage nor the full fragment, and HistGB intervals included both directions. Local42 versus full3 produced several positive point estimates and as many as 9/10 positive seeds for HistGB Spearman, but its confidence interval still crossed zero and its adjusted p-value remained 1.0. Seed direction alone therefore cannot be interpreted as a structural advantage.

Table 21. Frozen paired primary endpoints for the 42-nt local MFE. Effects are local42 minus comparator; MSE improvement is comparator MSE minus local42 MSE. CI denotes the 95% whole-cluster bootstrap interval, and Holm p is adjusted across all 12 tests.

| Comparison | Model | Metric | Observed effect | 95% CI | Raw p | Holm p | Positive seeds | Pass |
|---|---|---|---:|---|---:|---:|---:|---|
| local42−simple | Ridge | Spearman | -0.017568 | [-0.049283, 0.008892] | 0.167992 | 1.000000 | 0/10 | No |
| local42−simple | Ridge | MSE improvement | -0.010966 | [-0.057616, 0.033547] | 0.639968 | 1.000000 | 2/10 | No |
| local42−simple | Histgb | Spearman | 0.023830 | [-0.084681, 0.123269] | 0.720614 | 1.000000 | 8/10 | No |
| local42−simple | Histgb | MSE improvement | 0.009639 | [-0.300304, 0.287966] | 0.952202 | 1.000000 | 7/10 | No |
| local42−full1 | Ridge | Spearman | -0.009363 | [-0.058560, 0.040377] | 0.693865 | 1.000000 | 1/10 | No |
| local42−full1 | Ridge | MSE improvement | -0.008150 | [-0.088892, 0.074175] | 0.846208 | 1.000000 | 1/10 | No |
| local42−full1 | Histgb | Spearman | 0.035356 | [-0.071714, 0.132185] | 0.537973 | 1.000000 | 7/10 | No |
| local42−full1 | Histgb | MSE improvement | 0.081083 | [-0.254741, 0.402542] | 0.636868 | 1.000000 | 6/10 | No |
| local42−full3 | Ridge | Spearman | 0.021696 | [-0.030247, 0.077535] | 0.451477 | 1.000000 | 8/10 | No |
| local42−full3 | Ridge | MSE improvement | 0.071139 | [-0.036986, 0.174668] | 0.224939 | 1.000000 | 8/10 | No |
| local42−full3 | Histgb | Spearman | 0.049361 | [-0.062458, 0.158578] | 0.371981 | 1.000000 | 9/10 | No |
| local42−full3 | Histgb | MSE improvement | 0.143489 | [-0.186507, 0.489119] | 0.408480 | 1.000000 | 5/10 | No |

Primary-seed absolute performance provides context for these paired increments (Table 22). Ridge simple achieved Spearman 0.349548 and MSE 2.057832; local42 did not improve either value. HistGB local42 gave a modest absolute increase over simple (Spearman 0.262811 versus 0.238982), but the paired whole-cluster interval was compatible with no gain. Full3 did not outperform the simpler backbones in absolute primary-seed scores. These descriptive values explain the direction of individual fits but do not replace the paired uncertainty analysis or establish a practically useful expression predictor.

Table 22. Absolute held-out observed-R1 performance for the frozen primary seed 20261222.

| Model | Arm | Spearman | MSE |
|---|---|---:|---:|
| Ridge | simple | 0.349548 | 2.057832 |
| Ridge | simple + local42 MFE | 0.331980 | 2.068798 |
| Ridge | simple + full-300 MFE | 0.341343 | 2.060648 |
| Ridge | simple + full-300/window48 MFEs | 0.310284 | 2.139937 |
| Histgb | simple | 0.238982 | 2.585560 |
| Histgb | simple + local42 MFE | 0.262811 | 2.575921 |
| Histgb | simple + full-300 MFE | 0.227455 | 2.657005 |
| Histgb | simple + full-300/window48 MFEs | 0.213450 | 2.719411 |

An independently written implementation rebuilt the cluster definitions, folds, target, local/full MFE features, model predictions, seed effects, and all inference from the source tables. It passed 76/76 checks and returned the identical three-family decision and all 12 endpoint gates. A separate no-hardlinks clean checkout of `20e1ac389313fc21c36e82a5745be3d89bf0dffa` then repeated production and independent verification. The reproduction comparison passed 90/90 checks: 12/12 CSV files were byte-identical and 52/52 NPZ arrays were exactly equal. Original/clean production took 154.170620/158.617696 s; original/clean independent verification took 213.348891/190.443288 s. The complete project suite reported 429 passed and one skipped test.

The evidence boundary is narrower than a universal claim that local structure is uninformative. The observed fragment lacks the start ATG, four upstream nucleotides, complete UTR–CDS context, and measured structure; consequently, RK33 cannot identify start-aware folding, host, assay, measured-versus-predicted structure, or dangling-end effects. It also does not measure RNA decay, nuclear export, translation velocity, functional rescue, or protein OOD. A full UTR–CDS remap and an independent untouched evaluation remain necessary before transporting the RK32 local mechanism across datasets. External SOTA, unified time-matched and seven-method dense-trajectory comparisons, multispecies VeloHARMO, prospective DBTL, and RK-G1 remain open. Functional untouched data were not read, expensive generator training was not authorized, and no wet-lab experiment was performed.

::: {.evidence-anchor #sec-6-44}
| Field | Evidence |
|---|---|
| Code commits | `20e1ac389313fc21c36e82a5745be3d89bf0dffa` (accepted science); `20e1ac389313fc21c36e82a5745be3d89bf0dffa` (clean reproduction) |
| Code | `scripts/a8_rk33_run_local_coverage.py`; `scripts/a8_rk33_verify_local_coverage.py`; `scripts/a8_rk33_compare_reproduction.py`; `scripts/a8_rk33_closeout.py` |
| Protocol | `audits/20261121/RK33/a8_rk33_local_coverage_protocol_v1.json` |
| Results | `audits/20261121/RK33/rk33_local_coverage_result_v1.json`; `rk33_local_coverage_independent_v1.json`; `rk33_closeout_verification_v2.json` |
| SHA256 | protocol `d5a3282f0d03a384b3d77c3d30d2a98b315c0624d16e6d97563d09cee60a96fe`; result `d341694fb336ba579bbb990d80d7b17eafff104250052cea8577e4b927c08b64`; independent `3b53c5118bc93a71a5eaadaaaf22e48f13bc0b2d580b017308348a0ff171fa8d`; reproduction `7808acc84567fe972be0ddb870c23bd8714da2bc1e0dbdb1421ff08a5171e455`; closeout `ae09d302c8dd331aa59239c6e90180289e3c7ab34a030d3510e26b6af55c334b` |
| Analysis | 152 retrospective outcome-known observed-R1 variants; 74 whole-sequence clusters; 10 seeds × 5 folds; 200 new fits + 200 reused fits; 20,000 cluster bootstraps and 20,000 cluster-swap permutations |
| Scope | Local/full coverage and one-/three-feature comparisons only; no exact Kudla start-aware transport, independent untouched, functional/protein OOD, RNA velocity, decay, generator, or wet-lab claim |
:::
