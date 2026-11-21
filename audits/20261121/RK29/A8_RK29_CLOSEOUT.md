# A8-RK29 closeout — source alignment not uniquely identifiable

**Status:** `NOT_DISCRIMINATING_SOURCE_ALIGNMENT_OR_COVERAGE_FAILED`
**Independent check:** `PASS_INDEPENDENT_ALIGNMENT_FAILURE_VERIFICATION`
**Date:** 2026-11-21
**Protocol freeze:** `9496e1797470e5dd007e990d3760855f8bd43f0a` on `origin/a8-rk`.

## Decision

RK29 stopped at the preregistered outcome-alignment gate. The iCodon source package does not provide a unique mapping between the 955 S6 outcome rows and the 955 distinct FASTA sequences under the frozen, non-row-order join. No structure-increment estimate was produced.

This is a **source-identifiability result**, not a positive or negative scientific result about RNA structure. It neither supports nor contradicts RK27/RK28 and must not be presented as evidence that structure helps or fails to help mRNA-decay prediction.

## Verified sequence and coverage work before outcome access

- Official Springer S6 and GEO `GSE207584` inputs were hash-verified.
- The label-free audit retained 950 variants across 96 proteins after excluding five rows from four proteins with fewer than three variants.
- There were 96 evaluation groups, no cross-protein pair at 297-nt Hamming identity ≥0.90, and primary-seed fold sizes 189/192/190/190/189.
- Four finite ViennaRNA 2.7.2 MFE features were computed at 28 °C for all 950 retained sequences.
- Protocol, coverage code/report, production code, and nine synthetic unit tests were committed and pushed before outcome access.
- Coverage report SHA256: `29035867295f33c4c40f5b4a2a6257711a5d226fa255835cb00f74bfe9e88602`.
- Protocol SHA256: `e12a28b9ceaf3c4d8c70b78868e69ebfa2913a169dac99cac77ca20705b1c196`.

## Outcome-alignment failure

The production process stopped before creating analysis rows or fitting a model. Its first observed ambiguity was `c1_p10 / iCodon_1`: two different FASTA sequences (`rA-r1` and `rB-r1`, full-sequence Hamming distance 83) both matched both S6 measurement vectors.

A complete audit then established that the GEO perfect CSV is a within-protein Cartesian product of FASTA names and measurement vectors:

- 955 unique names and 955 S6 measurements;
- 10,227 GEO rows, exactly equal to the sum of squared per-protein variant counts;
- all 10,227 name-by-measurement pairs checked successfully;
- candidate-count distribution: 240 rows with one candidate, 598 with two, and 117 with three;
- 715/955 outcome rows have ambiguous sequence candidates;
- 338/578 protein-by-design groups have multiple valid one-to-one assignments;
- the frozen join admits approximately `10^120.355867` distinct global sequence–outcome assignments.

The nine abundance values identify a measurement vector, but they do not identify which synonymous sequence generated it. Selecting the first name, using row order, choosing by target, or revising the join after seeing outcomes would invalidate the experiment. None of these fallbacks was used.

## Independent verification

A separate verifier did not import the production or coverage modules. It independently parsed S6, GEO, and FASTA; rechecked all raw hashes; recomputed all 10,227 Cartesian pair checks, candidate counts, the number of valid global assignments, and the representative sequence difference; confirmed that the production log stopped on ambiguous assignment; and confirmed the absence of analysis, prediction, fold, metric, inference, and result files.

- Failure report SHA256: `ec1fc2c02370b21a333eb5cb38907cd3e893c4de86b95e8b8770e3033f4feb0d`.
- Verification report SHA256: `1306b5c55eb21e196561f2fd1448b46fb5e0d6d95ff3ed4c0f3062a0ecdc0d22`.
- Production stop-log SHA256: `ca28aedef3935f4f966293670374cf716f163d452b3f00ea12e694322c846c2c`.

## Output boundary

- Model fits: **0**.
- Analysis rows, OOF predictions, model metrics, bootstrap/permutation tests: **none**.
- Manuscript scientific claims: **unchanged**.
- Functional untouched data: **not accessed**.
- Expensive generative training: **not performed**.
- Large raw data and audit artifacts remain under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk29/`; code and commits remain under `/home/codonflow-a8-rk`.

A future RK29 restart requires an authoritative per-variant sequence key or explicit sequence-to-outcome mapping table and a new preregistered protocol. The current failed join must not be silently repaired with an arbitrary assignment.

## Repository evidence

- `configs/a8-rk29-icodon-decay-cluster-ood-v1.json`
- `scripts/a8_rk29_label_free_coverage.py`
- `scripts/a8_rk29_run_decay_cluster_ood.py`
- `scripts/a8_rk29_test_production.py`
- `scripts/a8_rk29_audit_outcome_alignment.py`
- `scripts/a8_rk29_verify_alignment_failure.py`
- `audits/20261121/RK29/label_free_coverage.json`
- `audits/20261121/RK29/RK29_ALIGNMENT_FAILURE.json`
- `audits/20261121/RK29/RK29_ALIGNMENT_VERIFICATION.json`
- `audits/20261121/RK29/RK29_production.log`
