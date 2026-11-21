# RK34 | Equal-length start-context 2×2 ablation closeout

- **Status**: PASS; production 900 evaluated fits = 700 new + 200 accepted RK32; independent 900 fits.

- **Conclusion**: `JOINT_EXACT_CONTEXT_WITHOUT_SEPARABLE_CONTRIBUTIONS_RETROSPECTIVELY`. The exact 42-nt window improves over matched simple features in all four confirmatory tests; neither upstream-only nor start-only separability claim passes both required families.

## Family gates

| Analysis | Family | Passed / 4 | Family gate |
|---|---|---:|---|
| primary d2 | exact_vs_simple | 4 | PASS |
| primary d2 | upstream_given_start | 3 | FAIL |
| primary d2 | start_given_upstream | 2 | FAIL |
| primary d2 | start_without_upstream | 1 | FAIL |
| primary d2 | upstream_without_start | 2 | FAIL |
| sensitivity d0 | exact_vs_simple | 4 | PASS |
| sensitivity d0 | upstream_given_start | 3 | FAIL |
| sensitivity d0 | start_given_upstream | 2 | FAIL |
| sensitivity d0 | start_without_upstream | 1 | FAIL |
| sensitivity d0 | upstream_without_start | 2 | FAIL |

## Confirmatory endpoints (d2)

| Family | Model | Metric | Effect | 95% CI | Holm p | Positive seeds | Gate |
|---|---|---|---:|---|---:|---:|---|
| exact_vs_simple | ridge | spearman_effect | 0.984683 | [0.528853, 1.12965] | 0.00099995 | 10/10 | PASS |
| exact_vs_simple | ridge | mse_improvement | 0.156926 | [0.0713052, 0.214567] | 0.00959952 | 10/10 | PASS |
| exact_vs_simple | histgb | spearman_effect | 0.402747 | [0.220999, 0.523021] | 0.00179991 | 10/10 | PASS |
| exact_vs_simple | histgb | mse_improvement | 0.104263 | [0.0556641, 0.130178] | 0.00449978 | 10/10 | PASS |
| upstream_given_start | ridge | spearman_effect | 0.210417 | [0.0803052, 0.294034] | 0.00319984 | 10/10 | PASS |
| upstream_given_start | ridge | mse_improvement | 0.0413292 | [0.0275341, 0.0656489] | 0.00254987 | 10/10 | PASS |
| upstream_given_start | histgb | spearman_effect | 0.157024 | [0.0372884, 0.262445] | 0.0292485 | 10/10 | PASS |
| upstream_given_start | histgb | mse_improvement | 0.0249145 | [0.00506004, 0.0430859] | 0.138943 | 10/10 | FAIL |
| start_given_upstream | ridge | spearman_effect | 0.282371 | [0.108633, 0.369537] | 0.00449978 | 10/10 | PASS |
| start_given_upstream | ridge | mse_improvement | 0.0529097 | [0.0283543, 0.0762287] | 0.0236488 | 10/10 | PASS |
| start_given_upstream | histgb | spearman_effect | 0.17189 | [0.00188532, 0.284806] | 0.121594 | 10/10 | FAIL |
| start_given_upstream | histgb | mse_improvement | 0.0377796 | [0.00608105, 0.0547945] | 0.138943 | 10/10 | FAIL |
| start_without_upstream | ridge | spearman_effect | 0.516851 | [0.208333, 0.641511] | 0.00449978 | 10/10 | PASS |
| start_without_upstream | ridge | mse_improvement | 0.0780879 | [0.0248495, 0.114082] | 0.138943 | 10/10 | FAIL |
| start_without_upstream | histgb | spearman_effect | 0.0281918 | [-0.0963884, 0.0826917] | 1 | 10/10 | FAIL |
| start_without_upstream | histgb | mse_improvement | 0.0139488 | [-0.0210561, 0.0279593] | 1 | 10/10 | FAIL |
| upstream_without_start | ridge | spearman_effect | 0.444897 | [0.207528, 0.546831] | 0.00099995 | 10/10 | PASS |
| upstream_without_start | ridge | mse_improvement | 0.0665073 | [0.0299138, 0.0993009] | 0.0259987 | 10/10 | PASS |
| upstream_without_start | histgb | spearman_effect | 0.0133254 | [-0.0673423, 0.0668064] | 1 | 9/10 | FAIL |
| upstream_without_start | histgb | mse_improvement | 0.00108371 | [-0.013243, 0.0130745] | 1 | 8/10 | FAIL |

## Verification and boundaries

- Independent: 155/155 PASS; maximum prediction delta 1.78e-15; 40/40 test records and 82/82 inference arrays exactly equal.
- Clean reproduction: 187/187 PASS; 6/6 production CSV, 82/82 production arrays, 5/5 independent CSV and 82/82 independent arrays exact.
- Component wall time: production 298.416 s; independent 303.009 s.
- Retrospective fixed-Kudla, 37 sequence clusters, 150 exact-CDS groups, 154 measurement rows. Artificial N-masking is a computational ablation, not a biological perturbation.
- No claim of universal upstream/start mechanism, independent untouched transport, host/assay identification, functional/protein OOD, external SOTA, prospective DBTL, wet lab, or RK-G1.
- External complete SOTA, unified time-matched, seven-method common dense matrix, multi-species VeloHARMO, real functional/protein OOD, untouched and prospective validation remain open.
