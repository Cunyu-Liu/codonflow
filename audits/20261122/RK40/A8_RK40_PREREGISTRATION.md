# A8 / RK40 PRE-REGISTRATION — Search scale, budget, and initialization discrimination

Status: **FROZEN BEFORE ANY RK40 PRODUCTION OUTCOME**  
Protocol: `configs/a8_rk40_budget_initialization_protocol_v1.json`

## 1. Scientific gap carried from RK39

RK39 established a dual-negative common-input actual-set result: protein-only random-initialized hill-climbing lost to LinearDesign-11 on normalized HV and pairwise NED in 18/18 development records. It did not identify why. Repeating the same 11-call comparison would not add mechanism evidence.

Before generating RK40 outcomes, implementation and calibration inspection identified a concrete alternative mechanism: RK39 used `SimpleSearch(normalization=None)`, so its weighted sum operated on raw units. In the existing C01H6.8b.1 calibration, for example, the CAI scale is 0.07928478595724608 whereas the negative-MFE scale is 35.700003051757804. Equal raw weights therefore need not represent equal normalized objective preferences. Short budget and initialization remain competing explanations.

## 2. Frozen factorial design

All runs use the same 18 development records, three seeds, fixed terminal TAA, synonymous protein constraint, objectives, weights, proposal operator, and hill-climbing implementation. No functional or untouched outcome is read.

The independently verified RK39 `raw_random_b11` arm is accepted as the short raw baseline. Five new arms are executed:

1. `raw_random_b101`: original raw utility and random protein-only initialization, 101 real scorer calls;
2. `calibrated_random_b11`: frozen-calibration normalized utility, the same random initialization, 11 calls;
3. `calibrated_random_b101`: normalized utility and random initialization, 101 calls;
4. `raw_external_b11`: raw utility, first frozen LinearDesign-11 actual sequence as initialization, 11 calls;
5. `calibrated_external_b11`: normalized utility, the same external initialization, 11 calls.

External-seeded arms are diagnostics of search basin and local improvement, not independent CodonFlow designs. Calibrated arms intentionally read native-source development calibration before search to diagnose scale mismatch; they are not common-input or external-SOTA evidence.

Long trajectories must reproduce the corresponding accepted short trajectory point-for-point under identical initialization, normalization, and seed. No output is overwritten and no failed smoke is deleted.

## 3. Primary endpoints avoid cardinality advantages

Both primary endpoints are maxima over one-sequence values through the real budget:

- `best_normalized_weighted_utility`: maximum normalized weighted-sum utility;
- `best_single_point_normalized_hv`: maximum product of positive normalized objective coordinates.

They do not increase merely because more sequences are reported. Multi-sequence first-k HV/NED, full-set HV/NED, and internal dense AUC are secondary diagnostics only. No external dense trajectory is inferred.

## 4. Two primary mechanism families

### Family N — normalization at short budget

Contrast: `calibrated_random_b11 - raw_random_b11`.

Question: does correcting objective-scale mismatch improve the original 11-call random-initialized search?

### Family B — budget within raw search

Contrast: `raw_random_b101 - raw_random_b11`.

Question: does increasing the original raw random-initialized search from 11 to 101 real scorer calls improve best-sequence quality?

The record is the statistical unit. Three seeds are averaged within each record before inference. Each family uses 20,000 paired bootstrap resamples, 20,000 paired sign-flip permutations, and Holm correction over its two endpoints. A family is supported only when both endpoints have effect>0, 95% CI lower bound>0, family-Holm p<0.05, and positive mean effects for every individual seed. Failure of either endpoint leaves that family unsupported.

## 5. Diagnostics cannot rescue a failed primary family

The following are diagnostic only: normalized-budget interaction, external versus random initialization under either utility, LinearDesign actual-set reference values, first-k and full-set actual-set metrics, and internal dense AUC. No diagnostic or sensitivity result can convert a failed primary family into a pass or authorize external SOTA.

Decision labels are fixed as:

- both families supported: `NORMALIZATION_AND_SHORT_BUDGET_BOTH_CONTRIBUTE`;
- only N supported: `SEARCH_SCALE_MISMATCH_SUPPORTED_AT_SHORT_BUDGET`;
- only B supported: `SHORT_BUDGET_LIMIT_SUPPORTED_WITHIN_RAW_SEARCH`;
- neither supported: `NO_RESCUE_FROM_NORMALIZATION_OR_RAW_BUDGET`.

Regardless of direction, `scientific_gate_passed=false`, `external_sota_authorized=false`, `time_matched_comparison=false`, `rk_g1_pass=false`, and `manuscript_submittable=false`.

## 6. Execution, verification, and delivery

Expected new production coverage is 270 runs and 12,690 unique-scorer calls. Smoke covers one record, one seed, five new runs, and 235 new calls and is excluded from formal evidence. Production uses four single-thread workers and records per-run wall time, objective-scoring time, proposals, cache hits, and unique-scorer calls.

Before production, protocol and implementation are committed and pushed. After production, an independent verifier will recompute sequences, objectives, calibration normalization, endpoints, trajectory identity, and inference without importing the production script. A detached clean reproduction and project-standard tests are required before manuscript and PPT updates. All large raw artifacts remain under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk40/`; code and lightweight evidence remain under `/home/codonflow-a8-rk`.
