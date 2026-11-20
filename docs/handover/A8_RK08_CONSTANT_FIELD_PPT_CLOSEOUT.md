# A8-RK08 constant-field PPT closeout

Date: 2026-11-20
Branch: `a8-rk`

## Scope

Record the already-frozen RK08 constant-position-field diagnostic in the online research deck. This closeout performs no model training, checkpoint selection, model forward pass, scorer call, functional-untouched evaluation, or generator training.

## Online record

- Presentation: `https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g`
- Added page: 109, slide ID `pZP`
- Revision: 70 -> 71
- The successful append used optimistic revision locking at revision 70.
- Full readback confirms 109 pages. The original 108 page IDs, visible data, speaker notes, geometry, and other XML semantics are unchanged.

## Frozen scientific result

Primary partition: `study_ood|Subtelny14`, with 3,630 transcripts and 1,444,596 observed positions. The sequence-independent constant field has 20 relative-position bins fitted only on Mohammad16 training data.

| Model | TB-MSE | Mean transcript Pearson |
|---|---:|---:|
| Learned model | 0.23056854005324243 | -0.00884488119796242 |
| Ridge | 0.1759458819436876 | 0.061698354230170255 |
| Constant field | 0.17285268431817252 | 0.12464883660898879 |

The constant field outperforms both learned models on TB-MSE and mean transcript correlation. All three preregistered support flags are false. The constant field's absolute mean correlation is only 0.12464883660898879, so this is not evidence of strong absolute transfer, causal mechanism, functional improvement, protein-OOD transport, external SOTA, or generation readiness.

`velocity_mechanism_pass=false`, `rk_g1_pass=false`, `functional_untouched_evaluated=false`, `generator_training_authorized=false`, and `external_sota_claim_authorized=false` remain unchanged.

## Verification

- New PPT unit tests: 3/3 PASS.
- Candidate generation preflight: 59/59 PASS.
- Independent candidate verification: 76/76 PASS.
- Full online postwrite verification: 194/194 PASS.
- Fresh scientific recomputation: 361/361 PASS, maximum numeric delta `6.245004513516506e-17`.
- Existing scientific independent verification: 361/361 PASS.
- Existing scientific finalization: 37/37 PASS.
- Existing scientific postpush verification: 361/361 PASS.
- Targeted scientific unit suite: 10/10 PASS.
- Remote rebuild is byte-identical to the submitted candidate XML; SHA256 `8bf03e2e9b2cd33ebba6857defc9755a63f10ac10c8ebea0e007c27a396cae2c`.

Two initial add-slide commands failed local CLI argument validation and did not issue a write. The successful command and revision-71 readback are preserved in the asset directory.

## Files

Code and tests:

- `scripts/a8_rk08_make_constant_field_ppt.py`
- `scripts/a8_rk08_verify_constant_field_ppt.py`
- `tests/test_a8_rk08_constant_field_ppt.py`

Audit records:

- `audits/20261120/RK08/constant_field_ppt_candidate_report_v1.json`
- `audits/20261120/RK08/constant_field_ppt_candidate_verification_v1.json`
- `audits/20261120/RK08/constant_field_ppt_closeout_v1.json`

Large XML snapshots, CLI responses, rebuilt candidate, and console logs are under:

`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/constant_field_ppt_20261120_v1/`

The fresh scientific recheck and its logs remain under:

`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk19/full_regression_20261120_v1/`

## Remaining boundary

This closeout validates the evidence record and its online presentation only. It does not close RK-G1, authorize generator training, or establish a complete clean-environment project reproduction. The earlier full-test collection failure caused by missing environment dependencies remains a separate open reproduction task.
