# RK05 · RNARL fixed-source availability audit (2026-11-18)

## Result

`PASS_NEGATIVE_REPRODUCIBILITY_AUDIT` — 16/16 independent checks passed. This is a **negative availability result**, not a model-performance result.

Fixed source: `ShenggengLin/RNARL` commit `88428e5d24fb2a16c29cc4dfbbfef51bd990a3d5`. The local clone's configured origin is preserved in the smoke JSON and was not silently treated as identical to another namespace. Ten source/example files in an isolated `git archive` export matched the fixed Git blobs byte-for-byte; the three official example CSVs each contain 9 rows.

Actual import/constructor execution after an isolated dependency overlay found:

- `ActorModel_encoder_esm2`: the exact constructor call in `actor_train.py` omits required `esm2_dim` and `device`; `TrainingManager.evaluate` is called but not defined.
- `RewardModel_encoder`: the exact constructor call in `reward_train.py` omits required `device`.
- `GRPOTrainer`: 9 called methods are absent; `load_and_preprocess_data` and `save_model` are absent; `policy_optimization_step` loads `rewards` without a local assignment.
- The independent verifier recomputed these findings from AST and fixed Git blobs without importing the production smoke module.

## Evidence

- `rnarl_official_contract_smoke.json`: first runtime attempt; actor/GRPO imports were blocked by the pre-existing environment's `huggingface-hub==2.2.0`, while the reward constructor failure was already observable.
- `rnarl_official_contract_smoke_v2.json`: imports unblocked with an isolated overlay containing `transformers==4.46.3` and `huggingface-hub==0.27.0`; all source-contract failures recorded.
- `rnarl_official_independent_verification.json`: independent AST/source/environment/scope checks, 16/16 PASS.

The smoke environment used the existing `llr_env` (`torch==2.11.0+cu128`, `pandas==2.2.2`, `numpy==2.2.6`) plus the two-package overlay. It is **not** a claim that the complete official environment was reproduced. Constructor signature and missing-symbol checks do not depend on GPU execution.

## Reproduction

Source export (create a new empty target; do not overwrite another export):

```bash
git -C /home/codonflow-a8-rk-external/RNARL archive \
  88428e5d24fb2a16c29cc4dfbbfef51bd990a3d5 \
  README.md environment.yml scripts example_data | tar -x -C <NEW_SOURCE_EXPORT>
```

Run the bounded contract smoke and independent verification with new audit paths:

```bash
PYTHONPATH=/home/codonflow-a8-rk-smoke/rnarl_python_deps \
/root/miniconda3/envs/llr_env/bin/python scripts/a8_rk05_rnarl_official_smoke.py \
  --source-root <NEW_SOURCE_EXPORT> \
  --git-repository /home/codonflow-a8-rk-external/RNARL \
  --commit 88428e5d24fb2a16c29cc4dfbbfef51bd990a3d5 \
  --audit <NEW_SMOKE_JSON>

PYTHONPATH=/home/codonflow-a8-rk-smoke/rnarl_python_deps \
/root/miniconda3/envs/llr_env/bin/python scripts/a8_rk05_verify_rnarl_official_smoke.py \
  --source-root <NEW_SOURCE_EXPORT> \
  --git-repository /home/codonflow-a8-rk-external/RNARL \
  --commit 88428e5d24fb2a16c29cc4dfbbfef51bd990a3d5 \
  --smoke-v1 audits/20261118/RK05/rnarl_official_contract_smoke.json \
  --smoke-v2 <NEW_SMOKE_JSON> \
  --audit <NEW_VERIFICATION_JSON>
```

No ESM-2 weight download, official checkpoint, full actor/reward/GRPO training, generation, paper-metric reproduction, SOTA claim, or baseline main comparison was performed or authorized. Fixing the public source would be a new implementation and must be evaluated separately rather than relabeled as the unchanged official result.

---

# ID3 / DeepRaccess fixed-source quick-test (2026-11-18)

## Bounded result

`BOUNDED_OFFICIAL_QUICK_TEST_COMPLETE_WITH_CPC_STE_TRAJECTORY_DEFECT` — the official CPU quick-test executed 12/12 configurations with zero failed jobs, and all 12 final sequences and final DeepRaccess scores were independently verified. This is not a full metric-payload PASS and not a main-baseline result.

- ID3: `Li-Hongmin/ID3` commit `ed23037e5a74ca10953954c425ac736fb89578a8`; fixed codeload ZIP SHA256 `9566b8cc1492ed6870e792e4b8ffed00c1b08debfb1719b41de872b7107f066f`.
- DeepRaccess: `hmdlab/DeepRaccess` commit `1a37235e31e1d5a7d5e2bfb705e3a00f1cdcaa9c`; fixed ZIP SHA256 `dfcdaefe51af5a02a7a62d7a5263a261984156d4365fed86f007dbe408bf7348`. Source and all three weights were re-hashed after symlink resolution; materialization status is `PASS_FIXED_SOURCE_AND_WEIGHT_MATERIALIZATION` with 24 files.
- Actual preset: O15263, three constraints × four variants, 2 iterations, seed 42, `enable_cai=false`, CPU. The source—not the README—defines 2 quick-test iterations and 1 full-12x12 seed. Official wall time was 417.591162443161 s; orchestration wall time was 434.3220009803772 s.
- Production audit: `PASS_OFFICIAL_QUICK_TEST_SMOKE`, 43/43 checks. Independent v2: 112/116 checks, 24 discrete trajectory records recomputed, 36 recorded initial/best/final values checked. Finalization: 11/11 checks. Four failed checks remain explicit in the independent report.
- Independent final accessibility across the 12 runs: mean `2.5201897621154785`, min `1.902809500694275`, max `3.240176200866699`. The saved summary final mean/min/max match these recomputations. These are single-protein, single-seed, two-iteration smoke values only.

## Upstream CPC STE metric defect

The fixed `CodonProfileConstraint.forward()` accepts `beta` but calls `CodonPsiFunction.forward(codon_probs, self.codon_encodings)` without forwarding it; CodonPsi therefore uses its default `beta=0.0`. The fixed runner's `beta == 1.0` branch nevertheless records `accessibility_loss.item()` as though it were the hard/discrete value. The CPC source file was independently matched to the fixed ID3 ZIP, and both source patterns were detected by AST without modifying upstream.

Consequently, `cpc-01` and `cpc-11` each fail the independent initial/best numeric recomputation:

| run | field | saved | independently recomputed |
|---|---|---:|---:|
| cpc-01 | initial | 1.7490674257278442 | 3.476618766784668 |
| cpc-01 | best | 1.6879907846450806 | 2.652176856994629 |
| cpc-01 | final | 2.652176856994629 | 2.652176856994629 |
| cpc-11 | initial | 1.7701568603515625 | 2.4008736610412598 |
| cpc-11 | best | 1.6919028759002686 | 1.902809500694275 |
| cpc-11 | final | 1.902809500694275 | 1.902809500694275 |

The other 10 runs pass the full quick-test metric-payload verification. All 12 official best sequences match the independently recomputed argmin over the recorded amino-acid-preserving discrete candidates. Nevertheless, for `cpc-01/11`, saved initial/best/improvement/trajectory accessibility fields are excluded. The summary `performance_table`, `constraint_comparison`, and `variant_comparison` are also excluded because they aggregate affected best metrics. The final-only summary statistics were independently recomputed and are retained; the saved `std=0` is not used.

The original v1 independent report (`108/112`, four failed checks) is preserved as `id3_official_quick_test_independent_v1_fail_108_of_112.json`. No tolerance was relaxed, no failed check was deleted, and the official payloads and pinned upstream source were not rewritten.

## CPU execution adaptations and retained failures

The official source was not patched. The production wrapper only:

1. normalizes the default DNA-compatible UTR alphabet `T` to model-input `U`;
2. scopes `--force` to CPU execution to skip the upstream global GPU-process gate without stopping other processes;
3. hides CUDA from the CPU official subprocess so DeepRaccess automatic device selection also remains on CPU.

The three preceding failure reports are retained: `id3_official_quick_test_preflight_keyerror_T_v1.json`, `id3_official_quick_test_global_gpu_gate_v2.json`, and `id3_official_quick_test_device_mismatch_v3.json`. These are engineering failures, not scientific negative results.

## Evidence and reproduction

- `deepraccess_materialization.json`
- `id3_official_quick_test.json` and `id3_official_quick_test.log`
- `id3_official_quick_test_independent.json` and `id3_independent_verification.log`
- `id3_official_quick_test_finalization.json`
- `scripts/a8_rk05_materialize_deepraccess.py`
- `scripts/a8_rk05_id3_official_smoke.py`
- `scripts/a8_rk05_verify_id3_official_smoke.py`
- `scripts/a8_rk05_finalize_id3_official_smoke.py`

From `/home/codonflow-a8-rk`, using the already verified fixed materialization and a **new** output/audit path for a repeat run:

```bash
/root/miniconda3/envs/llr_env/bin/python scripts/tests/test_a8_rk05_id3_official_smoke.py

/root/miniconda3/envs/llr_env/bin/python scripts/a8_rk05_id3_official_smoke.py \
  --device cpu --official-force \
  --deepraccess-zip-sha256 dfcdaefe51af5a02a7a62d7a5263a261984156d4365fed86f007dbe408bf7348 \
  --output-dir <NEW_OFFICIAL_OUTPUT_DIR> \
  --audit-output <NEW_PRODUCTION_JSON>

/root/miniconda3/envs/llr_env/bin/python scripts/a8_rk05_verify_id3_official_smoke.py \
  --production-report <NEW_PRODUCTION_JSON> \
  --output-dir <NEW_OFFICIAL_OUTPUT_DIR> \
  --verification-output <NEW_INDEPENDENT_JSON>

/root/miniconda3/envs/llr_env/bin/python scripts/a8_rk05_finalize_id3_official_smoke.py \
  --production-report <NEW_PRODUCTION_JSON> \
  --verification-report <NEW_INDEPENDENT_JSON> \
  --output <NEW_FINALIZATION_JSON>
```

The materialization script intentionally refuses to overwrite an existing source target or audit. Large ZIPs, weights, and official outputs remain under `/teams`; source and commits remain under `/home`. No full-12x12 run, multi-seed comparison, dense-budget evaluation, functional-expression claim, main-baseline ranking, or SOTA claim is authorized.

## 8. PPT record and handoff closure

The bounded result was recorded only after the independent and finalization reports passed their scope checks. One slide was appended to the existing online deck as slide 68, `pgC`, revision 30. It retains `12/12` official runs, `112/116` independent checks, `11/11` finalization checks, all four CPC saved-to-recomputed values, the final summary statistics, the fixed-source root cause, and the exclusion boundary.

`audits/20261118/RK05/id3_ppt_verification.json` records the server readback: 68 slides, all previous 67 slide IDs and semantic XML unchanged, all required values present, five speaker-note paragraphs, and the quick-test-only boundary. Evidence and reproduction documentation were pushed in `51fcda9f95a7770cf1a4ee0f1e8b2956eab719a1`; the PPT/handoff record does not promote the smoke to a main baseline comparison.

---

# LinearDesign fixed-source bounded official execution (2026-11-18)

## Result and retained v1 failure

`BOUNDED_LINEARDESIGN_OFFICIAL_SMOKE_VERIFIED` — the fixed official source was cleanly built, its README example passed, and one frozen protein was executed at three λ values. Independent raw-output verification passed **10/10 checks** with `max_numeric_delta=0.0`; finalization passed **8/8 checks**. This is not a full actual-set baseline matrix or model ranking.

- Fixed source: `LinearDesignSoftware/LinearDesign`, commit `f0126ca89a8b853088b4bccfd2cc8c378d3678be`.
- Clean codeload ZIP: 174,011 bytes, 32 members, CRC PASS, SHA256 `c27fa2a0beefd6b20359bb9b6a4f2bc43fa70b68aa577f4cd826a4a1051b8944`.
- Compiler: `g++ 9.4.0`; built binary SHA256 `f1f22901967cb3e0f569ff2332c326800ac355727ab58e377b14514db4fe9688`.
- Official README example `MNDTEAI`: `AUGAACGAUACGGAGGCGAUC`, MFE `-1.10 kcal/mol`, CAI `0.695`, matching the official documentation.
- Frozen input: `C01H6.8b.1`, 135 aa, from the verified unique18 FASTA. The three λ outputs are unique, amino-acid preserving, and contain no stop codon; `TAA` is appended only for the disclosed cross-method evaluation convention.

| λ | official MFE (kcal/mol) | official CAI | wall time (s) | independent CAI | default-dangles2 MFE |
|---:|---:|---:|---:|---:|---:|
| 0.0 | -270.60 | 0.761 | 8.06250987527892 | 0.7614413928951979 | -274.29998779296875 |
| 0.5 | -269.20 | 0.791 | 8.108563175890595 | 0.7912732411920935 | -272.3999938964844 |
| 1.0 | -265.20 | 0.820 | 8.150544322095811 | 0.8196140735200668 | -268.3999938964844 |

Total official wall time is **24.321617373265326 s**. All three independently recomputed structures exactly match the official structures. Official CAI was independently reconstructed from the pinned codon table as `exp2(mean(log2(frequency / synonymous_max_frequency)))`; maximum absolute difference from the rounded official printout is `0.0004413928951978452`.

The first v1 run is retained as `lineardesign_official_smoke_v1_failure.json`. Its official λ=0 execution succeeded, but the production scorer gate failed because v1 incorrectly compared the official MFE against ViennaRNA's default `dangles=2`. The official structure and default-Vienna structure are identical, while explicit `dangles=0` gives `-270.6000061035156`, matching the official `-270.60`; default `dangles=2` gives `-274.29998779296875`. Version 2 therefore uses `dangles=0` only for official-convention consistency and also reports default `dangles=2`. No tolerance was relaxed, and the failed raw stdout/stderr remain in the separate v1 output directory.

## Evidence

- `lineardesign_materialization.json`
- `lineardesign_build.json` and `lineardesign_build.log`
- `lineardesign_official_smoke_v1_failure.json`
- `lineardesign_official_smoke_v2.json`
- `lineardesign_independent_verification_v2.json`
- `lineardesign_finalization.json`
- `scripts/a8_rk05_lineardesign_official_smoke.py`
- `scripts/a8_rk05_verify_lineardesign_official_smoke.py`
- `scripts/a8_rk05_finalize_lineardesign_official_smoke.py`
- `tests/test_a8_rk05_lineardesign_official_smoke.py` (11/11 PASS)

The fixed archive and all raw official outputs remain under `/teams`; scripts, reports, and Git commits remain under `/home`. CDGB remains unassessed: no verified official repository, commit, build, or execution artifact was established in this bounded task. That absence is not a claim that the CDGB method is invalid or has no implementation.

## Reproduction

From `/home/codonflow-a8-rk`, using the verified fixed materialization and **new** output/audit paths:

```bash
/root/miniconda3/envs/codonflow/bin/python -m unittest \
  tests.test_a8_rk05_lineardesign_official_smoke -v

/root/miniconda3/envs/codonflow/bin/python \
  scripts/a8_rk05_lineardesign_official_smoke.py \
  --benchmark-fasta /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/a6_benchmark/unique18.fasta \
  --record-id C01H6.8b.1 \
  --source-dir /home/codonflow-a8-rk-external/LinearDesign-f0126ca89a8b853088b4bccfd2cc8c378d3678be \
  --materialization audits/20261118/RK05/lineardesign_materialization.json \
  --build-report audits/20261118/RK05/lineardesign_build.json \
  --output-dir <NEW_OFFICIAL_OUTPUT_DIR> \
  --audit <NEW_SMOKE_JSON> \
  --lambdas 0 0.5 1 --timeout-s 1800

/root/miniconda3/envs/codonflow/bin/python \
  scripts/a8_rk05_verify_lineardesign_official_smoke.py \
  --report <NEW_SMOKE_JSON> \
  --materialization audits/20261118/RK05/lineardesign_materialization.json \
  --build-report audits/20261118/RK05/lineardesign_build.json \
  --source-dir /home/codonflow-a8-rk-external/LinearDesign-f0126ca89a8b853088b4bccfd2cc8c378d3678be \
  --output <NEW_INDEPENDENT_JSON>

/root/miniconda3/envs/codonflow/bin/python \
  scripts/a8_rk05_finalize_lineardesign_official_smoke.py \
  --materialization audits/20261118/RK05/lineardesign_materialization.json \
  --build audits/20261118/RK05/lineardesign_build.json \
  --smoke <NEW_SMOKE_JSON> \
  --independent <NEW_INDEPENDENT_JSON> \
  --output <NEW_FINALIZATION_JSON>
```

The unified seven-λ actual-set matrix, dense candidate-budget comparison, functional OOD evaluation, CDGB assessment, main-baseline ranking, and SOTA assessment remain pending.
