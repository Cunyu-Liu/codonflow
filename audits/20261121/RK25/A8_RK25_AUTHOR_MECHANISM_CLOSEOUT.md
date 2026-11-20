# A8-RK25 — Train-only Boël author model versus the frozen mechanism and reference models

Status: **AUTHOR_REFERENCE_SUPERIORITY_SUPPORTED; ALL_CHANNEL_MECHANISM_INCREMENT_NOT_SUPPORTED; STRONG_COMPARATOR_CHAIN_FAILED; INDEPENDENT_VERIFICATION_PASS**

Frozen sequence-OOD evidence commit: `44014ad0fc923fba65d52fcda953117d9c822051`

Development independent acceptance: **337/337**; sequence-OOD independent acceptance: **678/678**

## 1. Frozen question and decision rule

RK25 asked the unresolved strong-baseline question on the **same frozen RK20 partitions**: can the four-seed `ribokinetic_all` predictor outperform a complete Boël author multiclass model refit using train only, and does that author model in turn outperform the frozen `ridge_all` and `histgb_all` references?

The three frozen comparisons were:

1. `ribokinetic_all − boel_author`;
2. `boel_author − ridge_all`;
3. `boel_author − histgb_all`.

Each comparison had two sequence-OOD endpoints: row-level Spearman and operational-protein-cluster-balanced MSE. The estimand was the mean of the four per-training-seed effects, not an unpriced prediction ensemble. Inference used 20,000 hierarchical bootstrap replicates with seed 20261125, resampling both operational protein clusters and the four training seeds. Six endpoints formed one Holm family.

A component Gate required both endpoints to have a beneficial point effect, a 95% CI wholly in the beneficial direction and Holm-adjusted empirical p < 0.05. The strong comparator chain required all three component Gates. This was not a majority vote across six endpoints. Even a complete chain pass would not, by itself, set RK-G1 to true.

## 2. Data, fitting and leakage controls

- Frozen rows were train/dev/test/sequence-OOD = **4,019/503/490/1,336**, totaling **6,348** constructs.
- The author model used the RK24 model structure but was **refit from scratch on RK20 train only**. No RK24 fitted coefficients and no Boël Published coefficients were used for prediction.
- The 61 single-codon slopes were fit on train E0/E5; the final multinomial logistic model used all train rows, fixed L2 = 0.01 and max_iter = 4000.
- All four `ribokinetic_all` prediction files and the ridge/HistGB predictions were frozen RK20 artifacts. RK25 trained no new neural model and no generator.
- Dev was used for pipeline and independent-refit checks, not to choose whether to report sequence-OOD. Test was descriptive only. Sequence-OOD was the sole confirmatory partition and is reused research-OOD data, not functional untouched data.
- Functional untouched data were not accessed. No GPU was used.

## 3. Frozen sequence-OOD result

Differences below are **left minus right**. Positive Spearman differences and negative cluster-MSE differences favor the left model. CIs are 95% hierarchical-bootstrap intervals.

| Comparison | Left Spearman | Right Spearman | Spearman difference [95% CI] | Cluster-MSE difference [95% CI] | Component Gate |
|---|---:|---:|---:|---:|---|
| All-channel − author | 0.20927607 | 0.42739443 | **−0.21811836 [−0.27227118, −0.16334044]** | **+0.73060695 [+0.53413821, +0.92587980]** | **FAIL 0/2** |
| Author − ridge_all | 0.42739443 | 0.21787307 | **+0.20952137 [+0.15881563, +0.26029269]** | **−0.82908708 [−1.00494105, −0.65327040]** | **PASS 2/2** |
| Author − HistGB | 0.42739443 | 0.21938296 | **+0.20801147 [+0.15728927, +0.25857331]** | **−0.70471991 [−0.86722430, −0.54344876]** | **PASS 2/2** |

Absolute sequence-OOD cluster-balanced MSE was **4.01583754** for all-channel, **3.28523058** for the author model, **4.11431766** for ridge_all and **3.98995050** for HistGB.

The all-channel model therefore performed worse than the author model on both confirmatory endpoints, with both CIs excluding zero in the unfavorable direction. The author model beat both frozen references on both endpoints.

All six empirical sign-tail p values and their Holm-adjusted values were zero under the frozen estimator: no opposite-sign tail occurred in 20,000 resamples. This empirical zero does **not** rescue the mechanism comparison, whose point and interval directions fail. Four of six individual endpoints passed, but the required chain failed because the mechanism component failed.

## 4. Development and descriptive-test context

Development showed the same ordering before the OOD run:

- all-channel − author: Spearman `−0.19001336`, cluster-MSE `+0.38878885`;
- author − ridge_all: Spearman `+0.16768106`, cluster-MSE `−0.31638185`;
- author − HistGB: Spearman `+0.16239793`, cluster-MSE `−0.35436495`.

Test was not part of the confirmatory family. Its descriptive means were:

| Model | Test Spearman | Test cluster-balanced MSE |
|---|---:|---:|
| ribokinetic_all | 0.22673007 | 4.23660443 |
| boel_author | **0.40811247** | **3.63404148** |
| ridge_all | 0.14489602 | 4.25783524 |
| histgb_all | 0.20307644 | 4.20775764 |

These test values support no additional p-value claim and did not alter the frozen sequence-OOD decision.

## 5. Independent verification

The OOD verifier independently reconstructed the static author design matrix, regenerated predictions from the frozen train-only author artifact, aligned every frozen neural/reference prediction, recomputed all metrics and point effects, and reran the complete hierarchical bootstrap without calling the RK25 production fitting or bootstrap functions.

Final independent OOD acceptance passed **678/678 checks**, including:

- exact construct, split, cluster, seed and label alignment;
- dev replay maximum numerical difference **8.881784197001252e-16**, within the frozen `1e-12` round-trip tolerance;
- frozen-author versus independent-dev-refit maximum prediction difference **9.275118451057551e-10**;
- maximum all-partition prediction difference **1.021405182655144e-14**;
- maximum metric difference **4.440892098500626e-16**;
- maximum point-comparison difference **4.440892098500626e-16**;
- maximum bootstrap-array difference **1.7763568394002505e-15**;
- maximum CI/p-value difference **4.440892098500626e-16**;
- exact independent reproduction of all three Gate decisions.

Development had separately passed **337/337** independent checks after refitting all 61 single-codon models and the multinomial model from sequence and static features.

Retained engineering history includes the initial prediction-schema correction, three synthetic-fixture corrections and the gzip CSV round-trip correction. The first OOD attempt stopped before test/OOD metric computation; its predictions and console were renamed and retained but were not used for scientific conclusions. No failed run was silently overwritten or presented as evidence.

## 6. Scientific decision and boundaries

- **Supported:** on this frozen sequence-OOD benchmark, the train-only Boël author multiclass model outperforms `ridge_all` and `histgb_all` on both primary metrics.
- **Not supported:** the four-seed `ribokinetic_all` model does not outperform that stronger author baseline; it performs worse on both sequence-OOD endpoints.
- **Decision:** `mechanism_vs_author_pass = false`, `author_reference_pass = true`, and `strong_comparator_chain_pass = false`.
- `RK-G1 = false`; expensive generator training remains unauthorized.
- The result is limited to cross-protein, non-synonymous ordinal-expression prediction. It does not establish fixed-protein synonymous causality, translation velocity, mRNA decay or full spatial coupling.
- This is not functional-untouched confirmation, external SOTA, CodonFlow-RK superiority, generative quality or a time-matched efficiency result.

## 7. Evidence and reproduction

Small reports and logs are in `audits/20261121/RK25/`:

- protocol `a8_rk25_author_mechanism_protocol_v1.json`, SHA256 `26df69797a64e97db53ccb8b53255ca17d69af85f7c1ab3e76338cd500496909`;
- production OOD result `rk25_ood_result_v1.json`, SHA256 `72d0f42b30685984a6592dcb2fba208765e3663562b819d1982099226c6fdf42`;
- independent OOD report `rk25_ood_independent_verification_v1.json`, SHA256 `2fac738cc3373140de9628b069048f0e71cccd39eec95352559d0dfb9a83ab69`;
- independent dev report `rk25_dev_independent_verification_v1.json`;
- production and independent console logs, retained failed logs, schema and replay-fix reports, and synthetic test logs.

Large artifacts remain under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk25/author_mechanism_comparator_v1/`:

- frozen train-only author model SHA256 `62b2c05135a3ea3e05c646fbee8764693e7b1464878e009126ae94443b7508e4`;
- OOD prediction table SHA256 `5c289704bc23a7e85351a5f52f54089f086f38434f3a824807af4b09d457d157`;
- production sequence-OOD bootstrap SHA256 `10018793d3a24711554ce4ab1b98c76e14271c7fc1c9d2ea75ab4bf4ac41939f`;
- independent OOD bootstrap SHA256 `a86068da089f05fab00a13621e66493b2853e21197d3a491061ddce24c22c3c4`.

Primary implementation and evidence commits: protocol/tests `bd032865`; prediction-schema correction `7b694cf2`; dev independent acceptance `dd17d2f3`; replay correction `bb59d962`; independent OOD verifier `f5d8f9e6`; frozen OOD result and 678/678 acceptance `44014ad0fc923fba65d52fcda953117d9c822051`.
