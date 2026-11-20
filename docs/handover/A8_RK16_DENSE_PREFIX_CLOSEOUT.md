# A8-RK16 real dense-prefix closeout

Status: **PASS_RK16_DENSE_PREFIX_TIME_MATCHED_OPEN**
Date: 2026-11-20
Preregistration commit: `a8bbcd67136ffb34d036935cb1d05e473d570ed5`
Final scoring-code commit: `3273211e026b79e7d81aa1afa8a55e6f676f98b6`
Independent-verifier commit: `795ad1807f6ee9fcb5061cb606fd7be3a2d08d03`

## Scope and frozen design

- Used the same 18 development records, seed-0 outputs, frozen objective values, and frozen normalized-hypervolume references as RK12/RK13. No new labels, functional test rows, OOD rows, or model training were introduced.
- Primary budget semantics are real ordered generation calls B=1,...,11. Repeated sequences remain at their original call positions; no deduplication-induced shift, padding, synthetic origin, or zero-filled budgets are allowed.
- Primary methods: LinearDesign-11, codonGPT, uniform synonymous sampling, and EnsembleDesign-11. Primary endpoints are B1..B10 dense budget-step AUC and B11 normalized hypervolume.
- GEMORNA and the legacy LinearDesign scan are excluded because repeated raw calls were not retained; CAI-greedy is excluded because only one real output exists. They remain in the RK13 terminal actual-set matrix, not in this four-method dense ranking.
- Statistics were frozen before scoring: LinearDesign minus each of three comparators, two endpoints, 18 paired records, 20,000 bootstrap resamples, and a six-test Holm family.

## Verified result

`dense_prefix_superiority_pass=true`: **6/6 primary tests passed**. Every effect is positive, every percentile 95% CI lies above zero, and every Holm-adjusted two-sided p-value is `0.000599970001499925`.

| Comparator | LinearDesign mean AUC | Comparator mean AUC | AUC effect [95% CI] | B11 HV effect [95% CI] |
|---|---:|---:|---:|---:|
| codonGPT | 22.7946063164 | 5.2054440256 | +17.5891622908 [+11.3344430513, +24.6211936951] | +21.9836761798 [+12.6138759620, +32.9067480072] |
| Uniform synonymous | 22.7946063164 | 0.7029515246 | +22.0916547919 [+15.1359151062, +30.5021547665] | +29.0062696025 [+18.9763330004, +41.5148969569] |
| EnsembleDesign-11 | 22.7946063164 | 14.8962344188 | +7.8983718976 [+4.2140600934, +12.0232104554] | +13.2789054093 [+6.9334345805, +20.7950860491] |

LinearDesign mean B11 HV is 29.9728874903. Comparator means are 7.9892113104 (codonGPT), 0.9666178878 (uniform), and 16.6939820810 (EnsembleDesign). Descriptive B1..B99 AUC is 11.8517962889 for codonGPT and 1.3301558985 for uniform; their B100 HV means are 14.5372191792 and 1.7187632111. These long curves do not enter the primary Holm family and do not create a common B100 comparison against methods lacking 100 retained raw calls.

## Acceptance and reproduction

- Structural preflight: 18 records and 3,996 raw generation-call positions bound to the previously verified objective maps.
- Primary scored curve rows: 792. Secondary B100 scored curve rows: 3,600.
- Independent trajectory/statistics verification: **88/88 PASS**, including raw hashes, repeated-call positions, all HV/AUC values, paired effects, six Holm adjustments, and CSV numeric binding.
- Full project CPU regression: **347 passed, 1 skipped, 11 warnings, 5 subtests passed in 27.39s**.
- Four pre-result schema/status failures and one verifier field-mapping failure are preserved in `rk16_engineering_failures_v1.json`. No failure changed the scientific protocol, input data, primary statistics, or an existing result report.

## Unchanged boundaries

This is a surrogate-objective, common-generation-budget comparison on 18 development records. `time_matched_comparison=false`: the sole RTX 5090 had unrelated real workloads, so no controlled exclusive-hardware timing was claimed and no process was killed. `scientific_gate_passed=false`, `codonflow_rk_evaluated=false`, `functional_ood_evaluated=false`, `functional_untouched_evaluated=false`, `rk_g1_pass=false`, `expensive_generation_authorized=false`, `external_sota_authorized=false`, and `sota_claimed=false`. The result does not establish functional improvement, CodonFlow-RK superiority, full seven-method dense coverage, or external SOTA.

## Evidence

- Protocol: `configs/a8_rk16_dense_prefix_protocol_v1.json`.
- Full curves: `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk16/dense_prefix_v1/rk16_dense_prefix_matrix_v1.json`.
- Summary and comparisons: `audits/20261120/RK16/rk16_dense_prefix_audit_v1.json` and `rk16_primary_comparisons_v1.csv`.
- Independent acceptance: `audits/20261120/RK16/rk16_independent_verification_v1.json`.
- Full regression: `audits/20261120/RK16/rk16_full_regression_v1.console.log`.
- Engineering failures: `audits/20261120/RK16/rk16_engineering_failures_v1.json`.
