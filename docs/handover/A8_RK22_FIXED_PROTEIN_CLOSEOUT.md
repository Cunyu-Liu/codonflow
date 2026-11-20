# A8-RK22 — Kudla fixed-protein and paired-leader structure analysis

Status: **PASS_RK22_FIXED_PROTEIN_DEVELOPMENT_NOT_PROTEIN_OOD**  
Science commit: `48eea1e2bd194b80e9c169e9420a3185e65fcb85` (protocol and analysis implementation, frozen before model fitting)  
Verification: **63/63 independent checks passed**

## 1. Pre-registered question and falsification rule

The development analysis asked whether measured 5′ MFE adds expression signal beyond CAI, CDS GC and CDS GC3, and whether paired addition of a 5′ leader produces expression changes that track the measured MFE change. The protocol, seeds, model hyperparameters, primary endpoints, bootstrap, exact/permutation tests, Holm correction and pass rules were committed before any model fit or association calculation.

Falsification would occur if any of the four main endpoints failed to show a positive structure increment with at least 8/10 positive seeds, a bootstrap 95% CI above zero and Holm-adjusted p<0.05, or if either tagged endpoint failed the corresponding positive-effect, CI and adjusted-p requirements.

## 2. Data and leakage controls

- Main: 154 measurement rows aggregated to **150 exact-CDS groups**; replicate expression values were averaged on the log10 scale. CAI, MFE and sequence-derived features were required to be identical within each exact-CDS group.
- Tagged: 72 measurement rows aggregated to **71 exact-CDS groups**. Per-seqId tagged-minus-main differences were computed before within-CDS averaging.
- Main evaluation: 10 pre-registered seeds × shuffled 5-fold OOF on the 150 exact-CDS groups. Every group had exactly one OOF prediction per seed/model/feature set.
- The simple predictors were CAI, CDS GC and CDS GC3. The structure predictor set added the measured 5′ MFE. Ridge scaling was fit within each training fold. HistGB used the frozen hyperparameters without tuning on test folds.
- Tagged analysis did not invent ΔCAI or ΔGC. The tagged sheet has no CAI or tagged nucleotide sequence, and its within-amino-acid codon frequencies do not reconstruct overall tagged GC.
- No functional untouched data were read; no GPU was used.

## 3. Main fixed-protein OOF results

Mean values across the 10 frozen seeds:

| Model | Predictors | OOF Spearman | OOF MSE (log10²) |
|---|---|---:|---:|
| Ridge | CAI + GC + GC3 | -0.039653 | 0.174779 |
| Ridge | simple + 5′ MFE | **0.678782** | **0.090442** |
| HistGB | CAI + GC + GC3 | 0.455130 | 0.147232 |
| HistGB | simple + 5′ MFE | **0.717246** | **0.085159** |

Positive effects favor adding 5′ MFE; MSE improvement is simple MSE minus structure MSE.

| Primary endpoint | Mean effect | 95% bootstrap CI | Positive seeds | Holm p | Decision |
|---|---:|---:|---:|---:|---|
| Ridge ΔSpearman | +0.718436 | [0.682482, 0.755274] | 10/10 | 0.0078125 | PASS |
| Ridge MSE improvement | +0.084337 | [0.082928, 0.085557] | 10/10 | 0.0078125 | PASS |
| HistGB ΔSpearman | +0.262115 | [0.230765, 0.292225] | 10/10 | 0.0078125 | PASS |
| HistGB MSE improvement | +0.062073 | [0.055539, 0.069029] | 10/10 | 0.0078125 | PASS |

Exact two-sided sign-flip tests used all 1,024 sign patterns; the CIs are percentile bootstrap intervals over the 10 seed-level paired effects (20,000 resamples). Multiplicity was controlled across the four primary endpoints.

## 4. Tagged paired results

`ΔMFE5 = tagged MFE5 − main MFE5`; positive values mean weaker predicted 5′ structure. Both endpoints were positive and passed their pre-registered criteria:

| Endpoint | Estimate | 95% paired-group bootstrap CI | Permutations | Holm p | Decision |
|---|---:|---:|---:|---:|---|
| Spearman(ΔMFE5, Δlog10 expression) | **0.565992** | [0.378594, 0.706085] | 100,000 | 0.0000199998 | PASS |
| OLS ΔMFE5 coefficient adjusted for main CAI/GC/GC3 | **0.098815** log10 per kcal/mol | [0.064230, 0.133576] | 20,000 | 0.0000499975 | PASS |

This is paired intervention evidence in a development subset: expression tends to increase when leader addition weakens the measured 5′ structure. It is not proof that MFE is the sole causal mediator because the leader also changes other sequence properties.

## 5. Independent verification

The final independent verifier passed **63/63 checks**. It re-derived both group tables, refit every one of the 10×5 folds, reproduced all 7,500 OOF predictions, recomputed seed metrics and effects, repeated the exhaustive sign-flip and bootstrap procedures, regenerated all tagged permutation and bootstrap arrays, and checked every output hash and scientific flag.

The first verification attempt stopped before numerical comparison because pandas interpreted the literal model name `null` as a missing value when reading the prediction CSV. The verifier was corrected to use `keep_default_na=False`; the scientific outputs were not changed. The completed verification then reproduced all predictions and statistics.

Commands:

```bash
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
/root/miniconda3/envs/codonflow/bin/python scripts/a8_rk22_run_fixed_protein.py \
  --protocol audits/20261121/RK22/a8_rk22_fixed_protein_protocol_v1.json
/root/miniconda3/envs/codonflow/bin/python scripts/a8_rk22_verify_fixed_protein.py \
  --protocol audits/20261121/RK22/a8_rk22_fixed_protein_protocol_v1.json \
  --summary audits/20261121/RK22/rk22_analysis_summary_v1.json \
  --output audits/20261121/RK22/rk22_independent_verification_v1.json
```

## 6. Scientific decision and boundaries

- **Development fixed-protein 5′ structure increment: PASS.**
- **Tagged paired structure–expression coupling: PASS.**
- This result narrows the earlier proxy-failure concern: CAI/GC/GC3 alone are insufficient here, while 5′ MFE carries substantial fixed-GFP expression signal.
- This is one fixed GFP protein with exact-CDS grouped OOF, **not protein OOD** and not research OOD. It does not establish velocity, decay or full spatial coupling.
- It does not evaluate CodonFlow-RK, functional untouched, external generation, time-matched performance or SOTA.
- `RK-G1=false`; expensive generator training remains unauthorized. The next scientific requirement is an external/protein-OOD test and cross-layer consistency, not immediate generator scaling.

## 7. Artifacts

Large tables and randomization arrays are under:

`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk22/fixed_protein_v1/`

Key files: `main_exact_cds_150.csv`, `tagged_exact_cds_71.csv`, `main_fold_assignments.csv`, `main_oof_predictions.csv`, `main_seed_metrics.csv`, `main_seed_effects.csv`, `tagged_randomization_arrays.npz`, and `rk22_analysis_summary.json`.

Small analysis and verification reports are under `audits/20261121/RK22/`. The verification report is mirrored beside the large scientific artifacts.
