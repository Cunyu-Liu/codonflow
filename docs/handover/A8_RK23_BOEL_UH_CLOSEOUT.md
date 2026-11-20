# A8-RK23 — Boël initiation-structure protein-OOD test

Status: **PRIMARY_PROTEIN_OOD_INCREMENT_NOT_SUPPORTED; INDEPENDENT_VERIFICATION_PASS**

Frozen test evidence commit: `a180c596b42f187ae46d6bd8d3607f1d2f2acb4d`

Development independent acceptance: **177/177**; test independent acceptance: **275/275**

## 1. Frozen question and falsification rule

RK23 asked whether the Boël author-provided pET21 5′ UTR + first 48 CDS nucleotides folding feature (`Gz48v`, the paper's UH folding-energy feature) adds protein-cluster out-of-distribution expression signal beyond the existing RK07 combined predictors: CAI, GC, full-CDS MFE per nucleotide, 5′-48-nt MFE and log length.

The primary contrast compared that combined set with the same set plus `Gz48v`, using the frozen multinomial logistic expected-score model (L2 = 0.01) and HistGradientBoostingRegressor. No hyperparameter search was performed. The four confirmatory endpoints were the two models' Spearman gains and MSE improvements. Every endpoint had to have a positive effect, a protein-cluster bootstrap 95% CI entirely above zero and Holm-adjusted p < 0.05 across the four tests.

The protocol was committed before model fitting (`a503564d1472b2b5d715bbad80e87e379cc5e442`). Two pre-training interface corrections (`d6322dd5f70a5dff4359f8f9fe51f6277d2a0b98`, `14c431c5b0095c8d10e29fc61f0363d1e8694f4c`) fixed split-hash mapping and prediction/resampling keys without changing features, labels, models or endpoints. Fourteen synthetic tests passed.

## 2. Data, scope and leakage controls

- Boël Protein Data Set: **6,348** complete real expression rows, split into train/dev/test = **5,079/635/634** by the frozen protein-cluster partition; dev and test each contain **556 operational protein clusters**.
- This is a **cross-protein, non-synonymous, ordinal 0–5 expression** data set. It can test protein-OOD feature transport, not fixed-protein synonymous causality.
- Only train was used for fitting. Dev was frozen before the single protocol-governed test evaluation. The test is reused project evaluation data, not the global functional untouched set.
- Inference used 20,000 protein-cluster bootstrap replicates and 20,000 within-cluster paired-prediction exchange permutations for each evaluated dev/test split.
- The optimized-construct sheet's `p025/p50/p975` fields are model prediction quantiles, not measured expression. Fig. 5 growth curves likewise do not supply fixed-protein expression labels. No image digitization or prediction-as-label substitution was performed.
- Functional untouched data were not accessed; no GPU was used.

## 3. Frozen test result: all four primary endpoints fail

MSE improvement is base MSE minus augmented MSE, so positive values favor adding the UH feature.

| Model | Endpoint | Base | + UH feature | Effect | 95% cluster-bootstrap CI | Holm p | Decision |
|---|---|---:|---:|---:|---:|---:|---|
| Logistic | Spearman | 0.12323867 | 0.12858011 | +0.00534144 | [-0.02839122, 0.03877199] | 1.0 | FAIL |
| Logistic | MSE improvement | 4.33157857 | 4.33112937 | +0.00044920 | [-0.05805848, 0.05902495] | 1.0 | FAIL |
| HistGB | Spearman | 0.20578583 | 0.20073508 | -0.00505075 | [-0.03822625, 0.02788615] | 1.0 | FAIL |
| HistGB | MSE improvement | 4.29768631 | 4.32614597 | -0.02845966 | [-0.13056306, 0.07304107] | 1.0 | FAIL |

All four confidence intervals cross zero; both HistGB point estimates are negative. Therefore the pre-registered protein-OOD initiation-structure increment is **not supported**. Dev was also non-significant for all four primary endpoints and was not used to tune the analysis.

The secondary simple-feature/HistGB contrast gave descriptive test point estimates of +0.06136398 Spearman gain and +0.18075736 MSE improvement; the corresponding logistic estimates were +0.00904404 and +0.02171694. These were explicitly descriptive, outside the primary Holm family, and do not reverse or weaken the primary negative decision.

## 4. Independent verification

The independent verifier did not import the RK23/RK07 production modules. It independently loaded the frozen data, refit every model, regenerated train/dev/test predictions, recomputed every metric and reran all dev/test bootstrap and permutation arrays.

Final test report: **275/275 checks passed**, with:

- maximum prediction difference = **0**;
- maximum metric difference = **0**;
- maximum bootstrap-array difference = **0**;
- maximum permutation-array difference = **0**;
- production and independently reconstructed Gate decisions identical.

The development verifier passed **177/177** after correcting only the verifier's RK07 length/GC convention to exclude the stop codon. Scientific outputs were unchanged.

## 5. Scientific decision and boundaries

- **Primary RK23 protein-OOD UH increment: NOT SUPPORTED.**
- The result does not show that initiation structure is universally uninformative; it shows no stable incremental transport under this frozen cross-protein comparison and these two model families.
- RK22's fixed-GFP development result answers a different question and is not overturned by this cross-protein, non-synonymous test.
- This is not fixed-protein synonymous OOD, research OOD, velocity, decay, full spatial-coupling, CodonFlow-RK, external SOTA or functional-untouched evidence.
- `RK-G1 = false`; generator training remains unauthorized. The descriptive secondary contrast cannot reopen the Gate.

## 6. Evidence and reproduction

Small reports and logs are in `audits/20261121/RK23/`:

- `a8_rk23_boel_uh_protocol_v1.json`, SHA256 `dd5f921190ee7107a1354432680847ee211ce817927c45dd751ff343611fd645`;
- `rk23_test_result_v1.json`, SHA256 `878322c8a2105b750059cce95aac16fa1249930b57404d7020a3672f81ad6373`;
- `rk23_test_independent_verification_v1.json`, SHA256 `d1ec5e61ff3d37c8f3dc06d3c19ee457c642c808b4196f2de37f45b2c495f0e1`;
- `rk23_test_console.log` and `rk23_test_independent_console.log`.

Large artifacts remain under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk23/protein_ood_v1/`:

- frozen model artifact SHA256 `17ca8844bde48ed5eeafe488b86134502a5399bda5bcaebbe621cb02ccf085f8`;
- test prediction file SHA256 `fdc2e2e81b10faf9b0b053ab820925efcdb9fbcb2c364328848dd9e23207dd00`;
- test resampling file SHA256 `249c84004ed4571c8e7e482efc8f6791cba7963ca1643f2e5437cd9f8ba06250`;
- independent arrays under `test/independent/`.

Primary commits: protocol `a503564d`; interface corrections `d6322dd5`, `14c431c5`; frozen dev `f655ca0a`; dev independent acceptance `434307fd`; frozen test and independent acceptance `a180c596`.
