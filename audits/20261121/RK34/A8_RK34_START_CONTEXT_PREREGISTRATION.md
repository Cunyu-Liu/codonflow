# A8 / RK34 preregistration: matched start-and-upstream context ablation

Date: 2026-11-22. Status: **frozen before RK34 expression association or model fitting**.

## Scientific question and observed phenomenon

RK32 supported a retrospective local-structure increment for source/Vienna `UTR[-4:]+CDS[:38]` in the fixed Kudla GFP cohort, while RK33 showed that a different 42-nt observed-R1 slice did not transport to Mordstein. RK34 asks whether the Kudla local result specifically requires the native upstream 4 nt and/or the native start ATG when sequence length, the remaining CDS positions, model, folds, and inference are matched.

This is an `retrospective_outcome_known_coverage_followup_not_independent_confirmation`. Expression was used in earlier studies and is not independent. No result in this preregistration has been used to choose a new arm.

## Falsifiable hypotheses

- H0: after matching the 42-nt length and CDS4–38 body, native upstream/start context gives no positive OOF increment over the corresponding N-masked controls.
- H-upstream: native upstream 4 nt improves OOF both when start ATG is present (`exact_real` vs `start_only`) and when start is masked (`upstream_only` vs `neither`).
- H-start: native start ATG improves OOF both when upstream is present (`exact_real` vs `upstream_only`) and when upstream is masked (`start_only` vs `neither`).

Each directional hypothesis is falsified if its required four-endpoint families do not pass. A positive isolated correlation or an unadjusted p-value is insufficient.

## Data, split, and reuse

- Reuse the accepted RK32 Kudla source: 154 measurement rows, 150 exact-CDS groups, 37 frozen sequence clusters, 144-nt 5'UTR + 720-nt CDS = 864 nt.
- Aggregate log10 expression by arithmetic mean within exact CDS exactly as RK32. No outcome-dependent filtering, clustering, folding, arm selection, or tuning.
- Reuse RK27/RK32 whole-cluster folds: primary seed 20261221; ten seeds 20261221–20261230; five folds per seed.
- Reuse accepted RK32 simple and Vienna-local `dangles=2` OOF predictions after exact identity/hash checks. These are 200 reused fits (simple + exact for two models across 50 fold assignments).
- Functional untouched data are not read. No generator training or GPU is used.

## Matched 42-nt factorial arms

Let `U=UTR[-4:]`, `A=CDS[:3]` (required to be ATG), and `B=CDS[3:38]`.

| Context | Sequence | Upstream | Start | Length |
|---|---|---|---|---:|
| `exact_real` | `U+A+B` | native | native | 42 |
| `start_only` | `NNNN+A+B` | masked | native | 42 |
| `upstream_only` | `U+NNN+B` | native | masked | 42 |
| `neither` | `NNNN+NNN+B` | masked | masked | 42 |

Every arm retains the same native CDS4–38 body. ViennaRNA is run at 37 C on the isolated 42-nt sequence. Each context is computed with `dangles=2` and `dangles=0`.

- Confirmatory analysis: `dangles=2`, selected from the prior label-free source-provenance preflight, not expression.
- Sensitivity analysis: identical contrasts with `dangles=0`; it cannot upgrade a failed confirmatory result.
- Shared simple features: CAI, whole-CDS GC, CDS GC3. Each structure arm adds one MFE to the same simple features.
- Models are exactly RK32 Ridge and HistGB settings, CPU, one BLAS/OpenMP/MKL/NUMEXPR thread.

New fits: `10 seeds * 5 folds * 2 models * 7 non-reused arms = 700`. Evaluated total: `700 new + 200 accepted reused = 900`.

## Confirmatory comparisons and endpoints

For each model (Ridge, HistGB), evaluate five families at `dangles=2`:

1. `exact_vs_simple`: `exact_real` minus simple.
2. `upstream_given_start`: `exact_real` minus `start_only`.
3. `start_given_upstream`: `exact_real` minus `upstream_only`.
4. `start_without_upstream`: `start_only` minus `neither`.
5. `upstream_without_start`: `upstream_only` minus `neither`.

Each family has four endpoints (2 models × 2 metrics), giving 20 confirmatory tests total. For arm A vs arm B, Spearman effect is `rho(A)-rho(B)` and MSE improvement is `MSE(B)-MSE(A)`; positive always favors A.

The same 20 tests are computed at `dangles=0` and explicitly labelled sensitivity, for 40 evaluated tests overall.

## Inference and acceptance

- Primary-seed paired OOF, sequence-cluster unit; 20,000 whole-cluster bootstrap resamples (seed 20261321) and 20,000 cluster-sign-swap permutations (seed 20261322).
- Percentile 95% CI and two-sided absolute-effect permutation p with plus-one correction.
- Holm correction separately across the 20 confirmatory tests and across the 20 sensitivity tests; only the confirmatory family controls the scientific conclusion.
- An endpoint passes only with observed effect >0, CI lower bound >0, Holm p<0.05, and at least 8/10 positive seed effects.
- A family passes only if all four of its endpoints pass.
- Exact-context increment requires `exact_vs_simple` to pass.
- Upstream contribution requires both `upstream_given_start` and `upstream_without_start` to pass.
- Start contribution requires both `start_given_upstream` and `start_without_upstream` to pass.

Conclusions are limited to: no exact-context increment; joint exact context without separable upstream/start support; upstream-only separable support; start-only separable support; or both contributions supported. No partial family is promoted to a mechanistic claim.

## Required checks before fitting

1. Source/preflight/cluster/reused prediction/fold SHA256 and row identities match.
2. All four contexts are 42 nt; native start is ATG; UTR+CDS=864-nt full mRNA; CDS hash identities hold.
3. Recomputed Vienna energies match label-free candidate CSV and RK32 exact-local energies within 1e-12.
4. Recomputed folds exactly match accepted RK32 assignments and have zero cluster leakage.
5. Reused targets/OOF columns and exact-d2 identities match within 1e-12; no missing/non-finite predictions.
6. Synthetic tests cover sequence masking, effect signs, fold isolation, inference shape/bounds, Holm, fit accounting, and conclusion logic.

## Boundaries and next decision

This experiment can distinguish upstream/start coverage within one fixed GFP, one study, and one retrospective cluster-OOD split. It cannot identify host/assay effects, measured-vs-predicted structure, protein OOD, functional untouched performance, external SOTA, time-matched generation quality, or RK-G1. A negative result triggers diagnosis of definition/transport limits rather than another outcome-selected window. A positive result still requires untouched/protein/functional validation before any general mechanism claim.
