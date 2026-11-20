# A8-RK24 — Boël author-model strong baseline

Status: **PRIMARY_AUTHOR_MODEL_INCREMENT_SUPPORTED_LIMITED_SCOPE; INDEPENDENT_VERIFICATION_PASS**

Frozen test evidence commit: `b4c04d2935015386603a5dff8b1f8c9247295b5a`

Development independent acceptance: **97/97**; test independent acceptance: **153/153**

## 1. Frozen question and falsification rule

RK24 asked whether the complete Boël author-model structure, refit using train only, improves protein-cluster out-of-distribution expression prediction over the frozen RK23 base + UH comparator. The comparator contains CAI, GC, full-CDS MFE per nucleotide, 5′-48-nt MFE, `source_Gz48v` and log length. The author models add the paper's codon, amino-acid, regional and sequence-derived terms reconstructed from the CDS.

The four confirmatory endpoints were binary AUC gain, binary log-loss improvement, multiclass Spearman gain and multiclass MSE improvement. Every endpoint required a positive effect, a protein-cluster bootstrap 95% CI entirely above zero and Holm-adjusted p < 0.05 across the four tests. Inference used 20,000 protein-cluster bootstrap replicates and 20,000 within-cluster paired-prediction exchange permutations on each evaluated split.

Published Boël coefficients were not used for prediction because they were fit on all source E0/E5 data and would leak dev/test labels. Instead, all 61 single-codon slopes and both author binary models were fit only on train E0/E5 by unregularized binary logistic regression. The multiclass models used all train rows and fixed L2 = 0.01 multinomial logistic regression. No hyperparameter search was performed.

## 2. Data, scope and leakage controls

- The frozen partition contains **6,348** complete real expression rows: train/dev/test = **5,079/635/634**, with **5,554** operational protein clusters overall.
- Test contains **398** binary E0/E5 rows in **364** clusters and **634** multiclass rows in **556** clusters.
- The author features were reconstructed from each CDS; terminal stop and the C-terminal LEHHHHHH tag were excluded. Static-feature validation passed for all 6,348 rows.
- The 62% versus 65% GC2–6 threshold wording difference in the paper's sources produces the same 558 positive rows in this data set, so it has no numerical effect here.
- This is a **cross-protein, non-synonymous, ordinal-expression** benchmark. It is not a fixed-protein synonymous perturbation experiment.
- Only train was used for fitting. Dev was evaluated before the single protocol-governed frozen-test evaluation. This test is reused project evaluation data, not the global functional untouched set.
- Functional untouched data were not accessed; no GPU was used.

## 3. Frozen test result: all four primary endpoints pass

Log-loss and MSE improvements are base minus author, so positive values favor the author model.

| Track | Endpoint | Base + UH | Author model | Effect | 95% cluster-bootstrap CI | Holm p | Decision |
|---|---|---:|---:|---:|---:|---:|---|
| Binary | AUC | 0.60090514 | 0.78822816 | +0.18732302 | [0.13324636, 0.24212345] | 0.00019999 | PASS |
| Binary | Log-loss | 0.68478730 | 0.55384658 | +0.13094073 | [0.08246948, 0.17778181] | 0.00019999 | PASS |
| Multiclass | Spearman | 0.12858011 | 0.43059088 | +0.30201076 | [0.22739421, 0.37520097] | 0.00019999 | PASS |
| Multiclass | MSE | 4.33112937 | 3.55929151 | +0.77183786 | [0.56306007, 0.98378739] | 0.00019999 | PASS |

All four effects are positive, every CI excludes zero in the favorable direction, and every Holm-adjusted p value is `0.000199990000499975`. The frozen decision is therefore **4/4 PASS**.

Development independently gave the same directional decision: AUC gain `+0.1325352455`, log-loss improvement `+0.1002718966`, Spearman gain `+0.2049765809`, and MSE improvement `+0.4412221131`; all four development endpoints passed.

## 4. Pre-registered descriptive HistGB comparator

A supplementary comparison against the frozen RK23 HistGB + UH model was registered after RK24 dev and before RK24 test. It does not add a confirmatory p-value family or alter the four-endpoint Gate.

| Split | Metric | Frozen HistGB + UH | Author multiclass | Descriptive effect |
|---|---|---:|---:|---:|
| Dev | Spearman | 0.24155372 | 0.42833798 | +0.18678426 |
| Dev | MSE | 3.89062009 | 3.34015734 | +0.55046275 improvement |
| Test | Spearman | 0.20073508 | 0.43059088 | +0.22985579 |
| Test | MSE | 4.32614597 | 3.55929151 | +0.76685445 improvement |

The RK24 base logistic predictions are value-identical to the frozen RK23 base + UH predictions on both dev and test. The descriptive HistGB results support using the author model as a stronger future reference, but are not new confirmatory tests.

## 5. Independent verification

The independent verifier did not import the RK07, RK23 or RK24 production modules. It independently reconstructed every author feature, refit all 61 single-codon models and four final models, regenerated predictions, recomputed every metric, and reran all bootstrap and permutation arrays.

Final test report: **153/153 checks passed**, with:

- maximum static-feature difference = **7.216449660063518e-16**;
- maximum prediction difference = **2.4740689497093626e-09**;
- maximum metric difference = **5.4017679218532066e-11**;
- maximum bootstrap-array difference = **3.0417401930549204e-10**;
- maximum permutation-array difference = **2.1483925749521404e-10**;
- production and independently reconstructed four-endpoint Gate decisions identical.

Development independent acceptance separately passed **97/97**. Retained history includes a pre-fit label-field correction, a verifier-only metric-count correction and a test-verifier command-line argument correction. None changed the frozen scientific definitions, models or numerical outputs.

## 6. Scientific decision and boundaries

- **The train-only Boël author-structure model outperforms the frozen base + UH comparator on this protein-OOD benchmark.**
- The author model is now a stronger reference for future CodonFlow comparisons; this result is **not** evidence that CodonFlow-RK beats it.
- The conclusion is limited to cross-protein, non-synonymous ordinal-expression prediction. It does not establish fixed-protein synonymous causality, research OOD, translation velocity, mRNA decay or full spatial coupling.
- This is not functional-untouched confirmation, external SOTA, generative quality or a time-matched efficiency result.
- `RK-G1 = false`; expensive generator training remains unauthorized.

## 7. Evidence and reproduction

Small reports and logs are in `audits/20261121/RK24/`:

- `a8_rk24_boel_author_protocol_v1.json`, SHA256 `92135eb2e22741ad70b4de01cc04d5e0ef363a50626252071985d57ed2295ed7`;
- `rk24_test_result_v1.json`, SHA256 `c78e239edf24f299497b7e1d02c7c6ed5a22216112cf7d9ee9445b74b4d4b3fe`;
- `rk24_test_independent_verification_v1.json`, SHA256 `eb1df66dc2de506bf2bd1378c08741e50b8408ec8d60f674b66ad6db505fb254`;
- `rk24_test_histgb_comparator_v1.json`, SHA256 `fe6dc3f4ef438068da8c99ed04d5f4fb4b27e41abd13a733179c2fba8a1d782c`;
- production, independent-verification, HistGB and retained interface-failure console logs.

Large artifacts remain under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk24/author_train_refit_v1/` and `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk24/author_features_v1/`:

- static-feature table SHA256 `78105d38c96fde52924cce420cd19cd596a9b8f9c6225eeddc55aeb8aabcf0dd`;
- frozen model artifact SHA256 `26df9b51d466d4164d84bd7646133ca74c35a6a8ec0d27999c504f6fa79d3d83`;
- test prediction file SHA256 `37d7a7a6c0afcf02ddc933dbd8df2ab6b17d49cbde674fbadfac8d3d36a61055`;
- test resampling file SHA256 `09f81d4063c8744f04772067639ca211ff5d598101349118e683c1a1dfd45775`;
- independently reconstructed arrays under `test/independent/`.

Primary commits: frozen dev and dev independent acceptance `cb0aa0957c1f62afbd37cf1cdc5aaf3d94c24ebd`; frozen test and test independent acceptance `b4c04d2935015386603a5dff8b1f8c9247295b5a`.
