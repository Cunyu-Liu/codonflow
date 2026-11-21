# A8-RK29 pre-registration: protein-cluster OOD structure increment beyond iCodon

**Freeze rule:** This document, its JSON protocol, the label-free coverage program, and the passing coverage report must be committed to `origin/a8-rk` before the production process is called with `--authorize-outcome-read`.
**Analysis type:** retrospective, frozen-protocol, sequence-only regression; CPU only.

## 1. Scientific question

Among 950 retained perfect synonymous reporters encoding 96 held-out synthetic proteins in the Diez et al. iCodon experiment, do computational RNA secondary-structure features add out-of-protein predictive information to a strong iCodon/codon/amino-acid/design baseline for injected-mRNA decay in one-cell zebrafish embryos?

This is a transport test of a **computed-structure increment**, not a test of experimentally measured structure, protein expression, physical translation speed, mammalian transport, or prospective design.

## 2. Data, target, and isolation

- **Host/assay:** one-cell Danio rerio embryos; injected IVT mRNA; targeted RNA-seq at 2, 5, and 8 hpi; three biological replicates.
- **Target:** source-published `Decay_rate`; larger values indicate greater stability under the source convention.
- **Strong baseline:** source `Predicted_mRNA_stability`.
- **Identifier join:** canonical FASTA name → unique sequence. S6 ↔ GEO is resolved only after freeze by canonical protein/design metadata plus all nine numeric timepoint vectors; exactly 955 unique one-to-one assignments are required before selection.
- **Coverage-only selection:** exclude four proteins with fewer than three unique variants (five rows total), retaining exactly 950 variants and 96 proteins. This rule is fixed before outcome access and matches the source study's per-protein analysis context.
- **QC:** 339-nt full sequence, fixed 33/9-nt contexts, 297-nt variable region, ACGT only, no variable-region stop, and identical 99-aa translation within each protein.
- **Dynamic-range gate:** at least 100 distinct target values, positive target IQR, and positive training-fold SD.
- **Alignment diagnostic:** six prespecified first-order slope estimators are used only to check consistency with the published target (minimum absolute Pearson 0.95). The target is never replaced or transformed post hoc.

## 3. Leakage control

Initial groups are exact `Protein_id` values. Different proteins are unioned if their 297-nt variable CDS are exact duplicates or have Hamming identity ≥0.90. All rows in the resulting evaluation group stay in the same fold.

Five row-balanced folds are generated for each of ten frozen seeds. Every fold asserts disjoint train/test evaluation groups. No exact sequence, synonymous protein, high-identity cross-protein sequence, or design-source batch is allowed to define a random row-level split.

The coverage gate requires ≥500 variants, ≥60 proteins, ≥60 evaluation groups, ≥3 variants per protein, median ≥8 variants per protein, and observed iCodon-5/IDT/Genewiz designs.

## 4. Frozen features

### iCodon-only arm

- `Predicted_mRNA_stability` (1 feature).

### Simple strong-baseline arm

- iCodon score (1);
- 61 sense-codon frequencies;
- 20 amino-acid frequencies;
- variable-region GC, GC3, CpG/nt, UpA/nt (4);
- one-hot design group for iCodon 1–5, IDT, and Genewiz (7).

Total: 93 features.

### Structure arm

All 93 simple features plus four ViennaRNA MFE values at 28 °C:

1. 297-nt variable region;
2. full 339-nt context-plus-variable sequence;
3. variable-region 5′ 48 nt;
4. fixed 33-nt 5′ context plus variable-region 5′ 48 nt.

Total: 97 features. DNA T is converted to RNA U; otherwise default `fold_compound` MFE settings are used. Lengths are fixed within each definition, so no post-hoc MFE normalization or feature selection is permitted.

## 5. Models and outer evaluation

- **Backbones:** Ridge (`alpha=1`, training-fold z-score) and HistGradientBoosting (`learning_rate=0.05`, 200 iterations, 7 leaves, `min_samples_leaf=10`, L2=1, no early stopping).
- **Arms per backbone:** iCodon-only, simple, structure, and MFE-only descriptive.
- **Null:** training-fold target mean.
- **Seeds:** 20261129–20261138; primary seed 20261129.
- **Work:** 5 folds × 2 backbones × 4 feature arms × 10 seeds = **400 model fits**, plus null predictions.
- **No tuning:** no hyperparameter search, target-dependent feature selection, or split revision.

## 6. Confirmatory inference and decision

The only confirmatory contrast is `structure − simple` within each backbone. Four primary tests are:

1. Ridge pooled OOF Spearman increment;
2. Ridge pooled OOF MSE improvement;
3. HistGB pooled OOF Spearman increment;
4. HistGB pooled OOF MSE improvement.

Primary seed inference uses 10,000 evaluation-group bootstrap resamples for 95% CIs and 10,000 group-level sign-swap permutations for two-sided p-values. Holm correction is applied across exactly these four tests.

**Support requires all four tests to have:** observed effect >0, bootstrap CI lower bound >0, Holm p<0.05, and a positive effect in at least 8/10 seeds.

- All pass: `ZEBRAFISH_SYNONYMOUS_MRNA_DECAY_STRUCTURE_INCREMENT_SUPPORTED_PROTEIN_OOD`.
- Any failure: `ZEBRAFISH_SYNONYMOUS_MRNA_DECAY_STRUCTURE_INCREMENT_NOT_SUPPORTED_PROTEIN_OOD`.
- Failed source alignment or coverage: `NOT_DISCRIMINATING_SOURCE_ALIGNMENT_OR_COVERAGE_FAILED`.

## 7. Secondary descriptive analyses

- Mean within-protein OOF Spearman.
- Retrospective top-1 regret per held-out protein (lower is better), including comparison with the calibrated iCodon-only arm.
- Metrics stratified by iCodon bins, IDT, and Genewiz.

These analyses do not alter the primary gate and cannot be described as prospective design or wet-lab validation.

## 8. Independent verification and reporting

A separate verifier must re-read the raw S6/GEO/FASTA inputs, rebuild the unique mapping and features, verify all raw hashes and fold isolation, independently recompute the primary-seed OOF predictions and all four inferential tests, and compare seed-level results before finalization.

Only after verification will the result be added to the working manuscript and research slides. Negative and positive results receive the same reporting treatment. Functional untouched data remain frozen; expensive generative training remains unauthorized.

## 9. Label-free freeze evidence

The passing coverage report has SHA256 `29035867295f33c4c40f5b4a2a6257711a5d226fa255835cb00f74bfe9e88602` and binds protocol SHA256 `e12a28b9ceaf3c4d8c70b78868e69ebfa2913a169dac99cac77ca20705b1c196`. It contains 950 selected variants, 96 proteins, 96 evaluation groups, no cross-protein pair at Hamming identity ≥0.90, primary-seed fold sizes 189/192/190/190/189, and finite ViennaRNA 2.7.2 features at 28 °C. Manifest and structure-table SHA256 values are `ed44676dc8322a4dce8814a612feb9cb98c6f612880c836e2936c360062eca57` and `c4f0b2b073424b73d614463883d80e3b2f293248392853c9efa2f9e6e39671f2`, respectively.
