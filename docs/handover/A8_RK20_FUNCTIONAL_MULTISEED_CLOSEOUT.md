# A8-RK20 functional multi-seed robustness closeout

## Decision

`PASS_RK20_COMPLETE_ROBUSTNESS_NOT_PASSED`. Four frozen training seeds and all strong controls were retained. The pre-registered sequence-OOD robustness gate passed only 2/8 endpoint-comparison tests. `functional_robustness_pass=false`; `RK-G1=false`; functional untouched was not read; expensive generator training remains unauthorized.

## Frozen protocol and execution

- Pre-registration and result-blind implementation: `14760b6f7dbd952f89cad06eb01a631bc35abdeb`.
- Summary-only engineering correction before result readout: `505cd22ff51439ce12be606f51570bbf2969c38e`.
- Seeds: `20261119`, `20261120`, `20261121`, `20261122`; the original-seed predictions were reused and six new all/none runs were completed.
- Only `training.seed` changed. Architecture, data, splits, six-epoch schedule, and development cluster-balanced-MSE checkpoint selection were frozen. No test/OOD checkpoint, seed, arm, or model selection was used.
- The estimand is the mean of four per-seed effects, not an unpriced prediction ensemble.
- Two thousand hierarchical bootstraps resampled operational protein clusters and four training seeds; paired methods shared each replicate. Bootstrap seed was `20261120`; eight sequence-OOD tests used Holm correction.
- Total new training time was 458.86265110969543 s on a shared GPU. These are observed robustness-run costs, not controlled time-matched SOTA evidence.

## Sequence-OOD results

Mean per-seed metrics:

| model | Spearman | cluster-balanced MSE |
|---|---:|---:|
| RiboKinetic all | 0.209276 | 4.015838 |
| RiboKinetic none | 0.140175 | 4.136880 |
| full-proxy ridge | 0.217873 | 4.114318 |
| GC-only ridge | 0.071873 | 4.378262 |
| HistGB all | 0.219383 | 3.989950 |

Frozen paired effects (`all − comparator`; lower MSE is better):

| comparator | endpoint | delta | 95% CI | Holm p | gate |
|---|---|---:|---:|---:|---|
| none | Spearman | +0.069101 | [+0.004823, +0.162735] | 0.126 | fail |
| none | CB-MSE | −0.121042 | [−0.271335, +0.038846] | 0.620 | fail |
| ridge all | Spearman | −0.008597 | [−0.058824, +0.040279] | 1.000 | fail |
| ridge all | CB-MSE | −0.098480 | [−0.246243, +0.030588] | 0.620 | fail |
| ridge GC | Spearman | +0.137403 | [+0.093656, +0.183960] | 0.000 | pass |
| ridge GC | CB-MSE | −0.362424 | [−0.504182, −0.248157] | 0.000 | pass |
| HistGB all | Spearman | −0.010107 | [−0.068994, +0.048675] | 1.000 | fail |
| HistGB all | CB-MSE | +0.025887 | [−0.159841, +0.193449] | 1.000 | fail |

The all-minus-none Spearman deltas were positive for all four seeds (`0.199016`, `0.022652`, `0.014371`, `0.040366`), but the original none seed was an outlier and the effect did not survive Holm correction. CB-MSE deltas were `−0.276089`, `−0.227282`, `−0.056226`, and `+0.075427`; the sign reversed for seed `20261122`.

## Interpretation

The all-feature neural model robustly outperforms the GC-only ridge on both sequence-OOD endpoints. It does **not** robustly outperform the full-proxy ridge or HistGB, and the all-minus-none mechanism contrast does not pass the frozen two-endpoint robustness gate. Multi-seed evidence therefore removes the original single-seed ambiguity but does not establish a stable mechanism increment or superiority to strong all-feature baselines.

No additional seeds or test/OOD-driven tuning are authorized by this protocol. A positive functional result alone would not have overridden the failed velocity and fixed-GFP structure mechanisms; the observed negative/uncertain result likewise leaves all global gates closed.

## Verification and retained failures

- Independent raw-prediction, metric, interval, Holm, and gate recomputation: **77/77 PASS**.
- Final artifact/value/hash binding: **67/67 PASS** after a verifier-only CSV/JSON floating-point tolerance correction (`1e−12`).
- The original 50/67 exact-CSV-equality report is retained. The earlier 13/14 test failure and summary-only `gpu_cotenancy` serialization failure are also retained in `rk20_engineering_failures_v1.json`.
- Large predictions, checkpoints, run logs, manifest, and bootstrap long table remain under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk20/functional_multiseed_v1/`.
- Small authoritative summaries and audit tables are mirrored under `audits/20261120/RK20/`.

This closes RK20 as a verified robustness experiment, not as a functional-mechanism success, untouched confirmation, CodonFlow-RK generator result, or SOTA claim.
