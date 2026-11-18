# RK06 — dense-v2 evaluator and actual-set smoke evidence

## Bounded status

- **RK06a evaluator: complete.** `dense_budget_step_auc_v2` and `summarize_actual_set` were added without renaming or changing the legacy sparse `anytime_curve`.
- **RK06b raw-CDS scorer: complete for one frozen record.** Five external methods on `C01H6.8b.1`, seed 0, were independently recomputed from 286 raw CDS sequences.
- **Not complete:** real dense B=1…500 trajectories, the full external-record matrix, unified generation-cost comparisons, functional OOD gains and model-improvement claims.

Code commits:

- Evaluator, tests and synthetic audit: `db3e1667dc593b4e4e9b3605bb0eee6fc249f000`.
- Raw-CDS actual-set scorer and tests: `56a62b4415c7e0e442ff064bb6002a4aed00798a`.
- Independent real-output verifier: `scripts/a8_rk06_verify_actual_set.py` in this documentation/audit commit.

## Dense-v2 protocol

For real hypervolume observations `HV_b` at every integer budget `b=1,…,Bmax`:

```text
dense_budget_step_auc_v2 = sum(HV_b for b=1…Bmax−1) / (Bmax−1)
```

`HV_Bmax` is retained as an endpoint but is not part of the area. With `Bmax=500`, the denominator is 499. No artificial origin, zero filling or trapezoid integration is used. Missing, duplicate, zero, non-integer, out-of-range, NaN or wrong-dimensional observations are rejected.

For an external actual output set, only actual Pareto points and normalized HV are reported. `curve`, `area` and `dense_budget_step_auc_v2` remain null; an actual set is not expanded into a fabricated 500-point trajectory. Duplicate objective vectors do not create additional Pareto points.

Synthetic hand checks:

| Case | Legacy sparse area | Dense-v2 area | Dense-v2 AUC |
|---|---:|---:|---:|
| Real budgets `(1,2,3)`, HV `(1,2,3)` | 5.5, using the legacy implicit origin | 4 | 2 |
| Constant HV 2 through budget 500 | not used | 998 | 2 |

`evaluator_synthetic_verification.json`: **10/10 PASS**. Combined new and legacy tests: **18 passed + 8 subtests passed**. This verifies the protocol, not model performance.

## Raw-CDS actual-set smoke

Frozen inputs:

- Original A6 record: `/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs/a6_baselines/unique18_s0/C01H6.8b.1_s0.json`.
- Independent A7 raw recompute: `/teams/HoulabData_1788502323/liucunyu/codonflow1031/eval_outputs/a7_external_actual_budget/C01H6.8b.1/C01H6.8b.1_s0.json`.
- Benchmark: `unique18.fasta`, SHA256 `30e3dbbfc3480287b1f87177fe476d7ca283219f08949476da6d08555d0ab4e0`.
- Source SHA256 `c6001dc87303c56617b4b19bfc99f34a5cfb1a6e338732a1192533824ff5efaa`.
- Calibration SHA256 `111c8348c4fdf94e36cbecb712accae8451ddc133d580ca1b51447c54a9edb2f`.
- Required v4-train RSCU: `configs/cai_ref_v4train.json`, SHA256 `80592c4eaeab61cdfc86a6f927fb1ef3c4b409b785c73bb466078df9af71bb6f`.

The first attempted run used a D5-train RSCU with SHA256 `2a5e05ef17a03a2b3b063990fd875d565a6db3fbedebab7689bca1fa45658c5d`; the hash gate rejected it before scoring and produced no output. The successful run used the required v4-train file above.

Actual output:

`/teams/HoulabData_1788502323/liucunyu/codonflow1031/eval_outputs/a8_rk06_actual_set/C01H6.8b.1_s0.json`

SHA256: `171d0768136f318a580449be9fb367479b0ca38af4137171b06e9fc20029c718`. The file is a large data artifact and is intentionally not committed to Git. The scorer records commit `56a62b4415c7e0e442ff064bb6002a4aed00798a`, `scorer_code_dirty=false`, the original generator commit and separate reanalysis elapsed time.

### Independent result

`real_actual_set_C01H6_8b_1_s0_verification_v2.json`: **44/44 PASS; all five methods PASS**. Raw sequences are exactly equal to the original payload and A7 recompute. Every recomputed CAI/MFE/GC/motif vector equals A7 exactly; maximum absolute difference is 0 for every method.

| Method | Actual outputs | Pareto points | Normalized HV |
|---|---:|---:|---:|
| LinearDesign | 5 | 4 | 13.5492 |
| codonGPT | 100 | 14 | 8.3550 |
| GEMORNA | 80 | 19 | 9.7230 |
| CAI greedy | 1 | 1 | 6.3930 |
| Uniform synonymous | 100 | 11 | 1.7268 |

These values describe one frozen record only. They are not a cross-record method ranking, dense-budget result or SOTA conclusion.

### Motif-scale diagnosis retained

The first verifier, preserved as `real_actual_set_C01H6_8b_1_s0_verification.json`, reported 41/44. CAI greedy and LinearDesign passed; codonGPT, GEMORNA and uniform synonymous failed only the original-reported objective comparison. CAI, MFE and GC matched exactly. A6 stored motif **raw counts**, while RK06/A7 store **per-codon penalties**.

The v2 verifier independently multiplies each recomputed motif penalty by that CDS's codon count and compares it with the original raw count. After this scale reconciliation, every original objective difference is 0 and the final result is 44/44 PASS. This is an explicit units reconciliation, not a looser tolerance.

Legacy generation seconds are preserved separately. Unknown wall-clock seconds, hardware and parallelism remain null. `reanalysis_elapsed_s_not_generation_cost` is not used as generation cost. Combined scorer and evaluator tests: **22 passed + 8 subtests passed**.

## Reproduction

From a clean `/home/codonflow-a8-rk` checkout with the frozen large artifacts available:

```bash
export PYTHONPATH=src
/root/miniconda3/envs/codonflow/bin/python -m pytest -q \
  scripts/tests/test_a8_dense_eval.py \
  scripts/tests/test_a8_rk06_actual_set.py \
  tests/test_anytime.py

/root/miniconda3/envs/codonflow/bin/python scripts/a8_rk06_verify_actual_set.py \
  --actual /teams/HoulabData_1788502323/liucunyu/codonflow1031/eval_outputs/a8_rk06_actual_set/C01H6.8b.1_s0.json \
  --legacy /teams/HoulabData_1788502323/liucunyu/codonflow1031/eval_outputs/a7_external_actual_budget/C01H6.8b.1/C01H6.8b.1_s0.json \
  --original /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs/a6_baselines/unique18_s0/C01H6.8b.1_s0.json \
  --expected-scorer-commit 56a62b4415c7e0e442ff064bb6002a4aed00798a \
  --output audits/20261118/RK06/real_actual_set_C01H6_8b_1_s0_verification_v2.json
```

The raw-CDS scorer refuses to overwrite an existing actual output. To reproduce scoring rather than verification, use a new output path under `/teams/HoulabData_1788502323/liucunyu/`, the required v4-train RSCU and the same frozen source, benchmark and calibration.

## PPT evidence and remaining gates

After the 44/44 result passed, two pages were appended to the existing online deck:

- Page 61, slide `pgw`: dense-v2 versus legacy and actual-set semantics.
- Page 62, slide `pgl`: the single-record 286-CDS actual-set table and explicit non-ranking boundary.

Final readback: 62 pages, revision 24. The first 60 slide IDs and semantic XML are unchanged; only a whitespace-only raw XML difference exists at the end of old page 60. `ppt_verification_v2.json` records the checks.

Before RK06 can support a main scientific comparison, it still needs real dense trajectories with complete integer budgets, all frozen external records, predeclared unified generation/scoring costs, and independent result verification. No functional OOD gain or CodonFlow-RK improvement is claimed here.
