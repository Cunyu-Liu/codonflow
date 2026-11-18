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

The fixed archive and all raw official outputs remain under `/teams`; scripts, reports, and Git commits remain under `/home`. The separate CDGB source-identity audit below established no verified official repository, commit, build, or execution artifact. That bounded source finding is not a claim that the CDGB method is invalid or has no implementation.

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

The unified seven-λ actual-set matrix, dense candidate-budget comparison, functional OOD evaluation, CDGB official execution, main-baseline ranking, and SOTA assessment remain pending. The bounded CDGB source-identity audit is documented below.

## PPT record

The bounded result was recorded only after the independent 10/10 and finalization 8/8 checks passed. One slide was appended to the existing online deck as slide 71, `pgB`, revision 33. It retains the fixed commit, all three official MFE/CAI/wall-time rows, default-dangles2 MFE, the v1 scorer-convention failure, independent/finalization status, and the bounded-only scope.

`lineardesign_ppt_verification.json` records the server readback: 71 slides, all previous 70 slide IDs and semantic XML unchanged, all required values present, four speaker-note paragraphs, and no main-baseline/CDGB/OOD/SOTA claim. Code, evidence, A8 v3, and reproduction documentation were pushed in `8be5369081b614beede261b7430f1230e0783e37`; the PPT verification and handoff update are recorded separately.

---

# CDGB source-identity and official-code availability audit (2026-11-19)

## Bounded negative source result

`SOURCE_IDENTITY_UNRESOLVED_OFFICIAL_EXECUTION_NOT_AUTHORIZED` — the candidate paper identity is unresolved and its embedded DOI resolves to a different publication. Independent verification passed **8/8 checks** by recomputing all findings from the frozen raw API responses; finalization passed **6/6 checks**. This is a source-reproducibility result, not a model-performance result and not evidence that the CDGB method is invalid or that no implementation exists.

Candidate title: `CDGB: a deep learning framework for codon de-optimization directed by the protein representation model`. Candidate URL: `https://academic.oup.com/bib/article/27/4/bbaf332/8199205`. The DOI embedded in that URL, `10.1093/bib/bbaf332`, resolves in Crossref to **Multimodal zero-shot learning of previously unseen epitranscriptomes from RNA-seq data**, Briefings in Bioinformatics volume 26 issue 4, rather than the CDGB candidate title.

Nine API responses were frozen under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/cdgb_source_audit_v1/`:

| Query layer | Returned records | Exact candidate-title matches |
|---|---:|---:|
| Crossref candidate bibliographic title | 20 | 0 |
| Crossref CDGB title | 3 | 0 |
| OpenAlex CDGB title | 7 | 0 |
| Europe PMC CDGB title | 4 | 0 |
| Europe PMC codon-deoptimization title | 2 | 0 |
| GitHub CDGB+codon repositories | 0 | not applicable |
| GitHub codon-deoptimization repositories | 14 | no official ownership established |
| GitHub CDGB+protein-representation repositories | 0 | not applicable |

The ninth response is the direct Crossref DOI lookup proving the title conflict. The broad GitHub query returns other projects and cannot be promoted to an official CDGB implementation. No authoritative author list or publisher code link was established, so an author-homepage assignment would be speculative. Searches are time-dependent and non-exhaustive.

No official repository, immutable commit, source build, execution, output sequence, runtime, quality metric, main-baseline comparison, functional OOD result, or SOTA claim was produced. Official sequence-output count and performance-result count are both zero.

## Evidence and reproduction

- `cdgb_source_audit.json`, SHA256 `dd8f0a8840bbf655d2731a60b7c5e7fb296665a29f4e7eb229edbc43e1e3f691`
- `cdgb_source_independent_verification.json`, SHA256 `964e782264c8101dc55cced708be3834f66b02488f3bc0e838b8724ce4598980`
- `cdgb_source_finalization.json`, SHA256 `dc49cdc6540d9f45f2cd040518e660871fc3b0dc109e929f92f7a541e4df66b2`
- `scripts/a8_rk05_cdgb_source_audit.py`
- `scripts/a8_rk05_verify_cdgb_source_audit.py`
- `scripts/a8_rk05_finalize_cdgb_source_audit.py`
- `tests/test_a8_rk05_cdgb_source_audit.py` (8/8 PASS)

From `/home/codonflow-a8-rk`, use new output paths for a repeat audit; never overwrite the frozen v1 raw responses:

```bash
/root/miniconda3/envs/codonflow/bin/python -m unittest \
  tests.test_a8_rk05_cdgb_source_audit -v

/root/miniconda3/envs/codonflow/bin/python \
  scripts/a8_rk05_cdgb_source_audit.py \
  --output-dir <NEW_RAW_API_RESPONSE_DIR> \
  --report <NEW_CDGB_AUDIT_JSON>

/root/miniconda3/envs/codonflow/bin/python \
  scripts/a8_rk05_verify_cdgb_source_audit.py \
  --audit <NEW_CDGB_AUDIT_JSON> \
  --output <NEW_CDGB_INDEPENDENT_JSON>

/root/miniconda3/envs/codonflow/bin/python \
  scripts/a8_rk05_finalize_cdgb_source_audit.py \
  --audit <NEW_CDGB_AUDIT_JSON> \
  --verification <NEW_CDGB_INDEPENDENT_JSON> \
  --output <NEW_CDGB_FINALIZATION_JSON>
```

A repeat query reflects the then-current APIs and need not reproduce the same hit counts. The frozen v1 responses and byte hashes are the authoritative evidence for this report. Before any future CDGB execution, obtain an authoritative citation whose title and authors match CDGB, an author/publisher-linked official repository and immutable commit, and official build instructions with a documented minimal input.

## PPT record and independent readback

The existing online deck advanced from **71 slides at revision 33** to **72 slides at revision 34** by appending only slide `pgR`. `cdgb_ppt_verification.json` is **PASS, 10/10 checks**: all previous 71 slide IDs and ID-independent semantic XML are unchanged; the new page contains the frozen KPI values, DOI conflict title, exact 4×3 evidence table, boundary statements, page number 72, and four speaker-note paragraphs. All new-page objects lie inside the 960×540 canvas. Baseline/readback XML and their complete responses are preserved under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/cdgb_ppt_verification_v1/`.

Operational note: the first local slide-only preflight command referenced a non-existent local evidence-JSON relative path and did not complete, while the subsequent add request in the same shell returned `pgR`. No duplicate slide was appended. Acceptance therefore uses the independent server readback and the authoritative frozen reports in `/home`, not the incomplete local preflight.

Reproduce the readback verification with the preserved XML snapshots:

```bash
/root/miniconda3/envs/codonflow/bin/python \
  scripts/a8_rk05_verify_cdgb_ppt.py \
  --baseline-xml /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/cdgb_ppt_verification_v1/cdgb-baseline-v01.xml \
  --baseline-response /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/cdgb_ppt_verification_v1/cdgb-baseline-response-v01.json \
  --readback-xml /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/cdgb_ppt_verification_v1/cdgb-readback-v01.xml \
  --readback-response /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/cdgb_ppt_verification_v1/cdgb-readback-response-v01.json \
  --audit audits/20261118/RK05/cdgb_source_audit.json \
  --verification audits/20261118/RK05/cdgb_source_independent_verification.json \
  --finalization audits/20261118/RK05/cdgb_source_finalization.json \
  --expected-new-slide-id pgR \
  --evidence-commit ea806ff10f331ae2831cef9c9d15ddb2c3252902 \
  --output audits/20261118/RK05/cdgb_ppt_verification.json
```

---

# EnsembleDesign official bounded execution (2026-11-18)

Fixed official commit: `cd9324f9574a754063d421e76670bc9fd7555324`; paper DOI: `10.1093/bioinformatics/btaf245`. The codeload ZIP contains 75 members and has SHA256 `0179bde9afb45b891c51c4577ee5c5895b1991528f3a1ac7e626450c5be474a2`. CRC, member paths, symlinks, and key-file hashes are frozen in `ensembledesign_materialization.json`. Code remains under `/home`; the archive, build logs, and raw outputs remain under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/`.

The official `setup.sh` calls three `make` commands without fail-fast, so each component's return code and log were recorded separately. A first reporting pass failed while reading the isolated `python-gflags==3.1.2` metadata; the original logs were retained and three confirmation builds were recorded. Final status is `BUILD_COMPLETE`, with hashes for EnsembleDesign, both LinearPartition binaries, and the bundled LinearDesign binary in `ensembledesign_build.json`. The official source was not modified.

The bounded protocol used `beam_size=100`, `lr=0.03`, `epsilon=0.5`, `num_iters=3`, `num_runs=2`, and `num_threads=4`. It is not the default dense 30-iteration × 20-run protocol.

| Input | Records | Runs | Unique CDSs | Aggregate wall time | Best official EFE |
|---|---:|---:|---:|---:|---|
| Official README example | 3 | 6 | 4 | 8.044503 s | seq1 `-18.00`, seq2 `-43.71`, seq3 `-70.29` kcal/mol |
| C01H6.8b.1, 135 aa | 1 | 2 | 2 | 52.650701 s | run 1, `-269.97` kcal/mol |

The three README example sequences and EFE values matched exactly. C01 produced a 405-nt best CDS encoding the 135-aa input. Official outputs contain no extra terminal stop; `TAA` may be added only for an explicitly disclosed cross-method evaluation. EFE was independently recomputed with official LinearPartition `-V -d0 -b0` and ViennaRNA 2.7.2 at 37°C with `dangles=0`. Maximum ViennaRNA differences from rounded official EFE were 0.0027606201 (example) and 0.0045483398 (C01). **EFE is not LinearDesign MFE; no direct ranking is authorized.**

The initial example wrapper v1 incorrectly required an extra terminal stop and was marked `FAILED` even though the official process returned zero. Its raw output and report are retained. Protocol v2 corrected only that wrapper contract; source, bounded parameters, and scorer tolerance were unchanged. Independent verification passed **13/13 example checks** and **13/13 C01 checks**, unit tests passed **11/11**, and finalization passed **11/11 checks** with `task_completion_authorized=true` for the bounded smoke only. No matched LinearDesign comparison, dense-budget result, main-baseline ranking, functional OOD result, or SOTA claim was produced.

From `/home/codonflow-a8-rk`:

```bash
PY=/root/miniconda3/envs/codonflow/bin/python
SRC=/home/codonflow-a8-rk-external/EnsembleDesign-cd9324f9574a754063d421e76670bc9fd7555324
DEPS=/home/codonflow-a8-rk-smoke/ensembledesign_python_deps
R=audits/20261118/RK05
ART=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05

$PY scripts/a8_rk05_ensembledesign_official_smoke.py \
  --input-fasta "$SRC/data/examples.fasta" --source-dir "$SRC" \
  --materialization "$R/ensembledesign_materialization.json" \
  --build-report "$R/ensembledesign_build.json" --python-deps "$DEPS" \
  --output-dir <NEW_EXAMPLE_OUTPUT_DIR> \
  --audit <NEW_EXAMPLE_AUDIT_JSON>

$PY scripts/a8_rk05_ensembledesign_official_smoke.py \
  --benchmark-fasta /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/a6_benchmark/unique18.fasta \
  --record-id C01H6.8b.1 --source-dir "$SRC" \
  --materialization "$R/ensembledesign_materialization.json" \
  --build-report "$R/ensembledesign_build.json" --python-deps "$DEPS" \
  --output-dir <NEW_C01_OUTPUT_DIR> \
  --audit <NEW_C01_AUDIT_JSON>

$PY scripts/a8_rk05_verify_ensembledesign_official_smoke.py \
  --report "$R/ensembledesign_official_example_smoke_v2.json" \
  --materialization "$R/ensembledesign_materialization.json" \
  --build-report "$R/ensembledesign_build.json" --source-dir "$SRC" \
  --python-deps "$DEPS" --output "$R/ensembledesign_official_example_independent_v2.json"

$PY scripts/a8_rk05_verify_ensembledesign_official_smoke.py \
  --report "$R/ensembledesign_c01_smoke_v1.json" \
  --materialization "$R/ensembledesign_materialization.json" \
  --build-report "$R/ensembledesign_build.json" --source-dir "$SRC" \
  --python-deps "$DEPS" --output "$R/ensembledesign_c01_independent_v1.json"

$PY scripts/a8_rk05_finalize_ensembledesign_official_smoke.py \
  --output <NEW_FINALIZATION_JSON>
$PY -m unittest discover -s tests -p 'test_a8_rk05_ensembledesign_official_smoke.py' -v
```

Evidence: `ensembledesign_materialization.json`, `ensembledesign_build.json`, retained `ensembledesign_official_example_smoke.json` (v1 failure), `ensembledesign_official_example_smoke_v2.json`, `ensembledesign_c01_smoke_v1.json`, both independent reports, `ensembledesign_finalization.json`, and `ensembledesign_unit_tests.txt`. The two independent-verifier commands above verify the frozen production reports. Use new output and audit paths for every fresh execution because the official entry point deletes a same-named record subdirectory; do not overwrite the frozen v1/v2 evidence.

## Online PPT record and verification

The verified result was appended to the existing online deck as slide 73, `pgO`, revision 35. Candidate preflight passed **8/8 checks** against the frozen JSON reports. Independent post-write verification passed **10/10 checks**: exactly one slide was appended, all previous 72 slide IDs and semantic XML remained unchanged, the four-row table was recomputed from the production reports, and the EFE/MFE and bounded-scope boundaries were retained. Scientific/A8 v5 evidence is in commit `5ba0a8848ccf701f5e070b61fe357ca6d05eeb3c`; PPT verifier/report evidence is in commit `9986974ac46cc65aaf0708e509e9ad5ff2cfb2af`.

The candidate slide, preflight log, complete baseline/readback XML, and write responses are archived under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ppt_ensembledesign_v1/`. To reproduce the independent readback audit without changing the online deck:

```bash
PPT=$ART/ppt_ensembledesign_v1
$PY scripts/a8_rk05_verify_ensembledesign_ppt.py \
  --baseline-xml "$PPT/ensembledesign-baseline-v01.xml" \
  --baseline-response "$PPT/ensembledesign-baseline-response-v01.json" \
  --readback-xml "$PPT/ensembledesign-readback-v02.xml" \
  --readback-response "$PPT/ensembledesign-readback-response-v02.json" \
  --add-response "$PPT/ensembledesign-add-response-v01.json" \
  --evidence-dir "$R" --output <NEW_PPT_VERIFICATION_JSON>
```

---

# CodonTransformer official bounded execution (2026-11-19)

Fixed official source commit: `4a447b01dab860feb81b647ff1ff88ad598517f4`. Fixed Hugging Face model revision: `9744dcc920d813066391fc828d7a590207f148e8`. All eight model files match the API byte counts; `model.safetensors` is 358,342,232 bytes with SHA256 `23994e1e7324e78c9d9da71040e8677c0a635287cf1c7c9ea5096b7eadc44dfd`. The fixed codeload ZIP has 45 members, 554,315 bytes, SHA256 `85fe55a10ad061b62034aaed90bce06d4be3eb9a2e25d40030db359b0d1fd132`, and passed CRC/path/symlink checks. `codontransformer_materialization.json` freezes the source, model files, and benchmark hashes.

Official inference used `predict_dna_sequence` with `deterministic=True`, `attention_type="original_full"`, and organism `Escherichia coli general`. The isolated environment is `/home/codonflow-a8-rk-smoke/codontransformer_venv` on an NVIDIA GeForce RTX 5090; final official import passed. Incorrect `CAI-PyPI==1.0.4` installation attempts, the missing scikit-learn import failure, and the first output-directory pre-creation failure are retained. The working dependency is `CAI-PyPI==2.0.1`, with `scikit-learn==1.4.2`.

| Input | Mode | Legal synonymous CDS | Output length | Unique within the bounded run |
|---|---|---:|---:|---:|
| Official README example | `official_default` | 1/1 | 213 nt, 70 aa | 1 |
| Official README example | `match_protein=True` | 1/1 | 213 nt, 70 aa | same as default |
| C01H6.8b.1 | `official_default` | 1/1 | 408 nt, 135 aa | 1 |
| C01H6.8b.1 | `match_protein=True` | 1/1 | 408 nt, 135 aa | same as default |

The official example default sequence matched the README exactly. All four outputs passed ACGT/length/single-terminal-stop/no-internal-stop/exact-translation checks: 4/4 legal synonymous CDS and 2 unique CDS overall. Default and constrained outputs are identical for each protein; this bounded run does **not** demonstrate a benefit from `match_protein=True`. Model loading took 4.438656704965979 s and the four inferences took 2.0327787059359252 s in total, including first-call warm-up; these are not time-matched performance estimates.

The independent verifier does not import the production module. It reloads the same fixed model, recomputes source/model/input/raw/FASTA hashes and translation QC, and re-executes all four deterministic inferences. All sequences match exactly: **13/13 PASS**, `max_numeric_delta=0.0`. Unit tests passed **8/8**, and finalization passed **10/10** with status `CLOSED_BOUNDED_OFFICIAL_SMOKE`. No matched MFE/EFE comparison, dense-budget result, main-baseline ranking, functional OOD result, or SOTA claim is authorized.

From `/home/codonflow-a8-rk`, using a new empty raw-output directory and new report paths:

```bash
PY=/home/codonflow-a8-rk-smoke/codontransformer_venv/bin/python
PY_STD=/root/miniconda3/envs/codonflow/bin/python
SRC=/home/codonflow-a8-rk-external/CodonTransformer-4a447b01dab860feb81b647ff1ff88ad598517f4
MODEL=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/codontransformer_model_9744dcc920d813066391fc828d7a590207f148e8
BENCH=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/a6_benchmark/unique18.fasta
R=audits/20261118/RK05
ART=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05

$PY scripts/a8_rk05_codontransformer_official_smoke.py \
  --source-dir "$SRC" --model-dir "$MODEL" \
  --materialization "$R/codontransformer_materialization.json" \
  --benchmark "$BENCH" --record-id C01H6.8b.1 \
  --output-dir <NEW_RAW_OUTPUT_DIR> --report <NEW_PRODUCTION_JSON> --device cuda

$PY scripts/a8_rk05_verify_codontransformer_official_smoke.py \
  --source-dir "$SRC" --model-dir "$MODEL" \
  --materialization "$R/codontransformer_materialization.json" \
  --benchmark "$BENCH" --record-id C01H6.8b.1 \
  --production-report "$R/codontransformer_official_smoke_v1.json" \
  --output <NEW_INDEPENDENT_VERIFICATION_JSON> --device cuda

$PY_STD -m unittest discover -s tests \
  -p 'test_a8_rk05_codontransformer_official_smoke.py' -v
$PY_STD scripts/a8_rk05_finalize_codontransformer_official_smoke.py \
  --materialization "$R/codontransformer_materialization.json" \
  --production "$R/codontransformer_official_smoke_v1.json" \
  --verification "$R/codontransformer_independent_verification_v1.json" \
  --unit-log "$R/codontransformer_unit_tests.txt" \
  --env-dir "$ART/codontransformer_env_v1" --output <NEW_FINALIZATION_JSON>
```

The production wrapper requires the output directory to be absent or empty. Do not pre-create a log inside it, and do not overwrite the frozen reports or raw outputs. Code and commits remain under `/home`; the model, source archive, environment logs, raw JSON/FASTA outputs, and execution logs remain under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/`.

## A8 v6 and online PPT verification

A8 v6 was generated from the frozen evidence rather than hand-edited result numbers. It adds the four-run table, fixed source/model/materialization evidence, 13/13 independent re-execution, 10/10 finalization, unchanged default/constrained outputs, and bounded-scope guards. A7 is unchanged. A8 SHA256 is `1ac702be2b38900346064ebbc56a4b20a461089f317078db1df08c73774e0d35`; independent paper verification passed **17/17** and remains `PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE`. Scientific evidence is in commit `210d2f4c13cddc7144d1939d0ae76162d2016c8a`; A8 v6 generator/verifier evidence is in commit `f479955fefa034c5a5fde84c5f7ab37d85cf0044`.

The verified result was appended to the existing online deck as slide 74, `pgU`, revision 36. Candidate v01 failed preflight 7/8 because two table mode labels did not match the frozen JSON; it was retained and not written. Candidate v02 corrected both labels to `official_default`, passed preflight **8/8**, and was written once. Independent post-write verification passed **10/10 checks**: exactly one slide was appended, all previous 73 slide IDs/order and semantic XML remained unchanged, and the four-row table, KPI values, speaker notes, page bounds, and scientific boundaries were recomputed from the frozen reports. PPT evidence is in commit `0c33d35580c02ae06932083200bc6fbd5dd3882c`.

Reproduce the readback audit without changing the online deck:

```bash
PPT=$ART/ppt_codontransformer_v1
$PY_STD scripts/a8_rk05_verify_codontransformer_ppt.py \
  --baseline-xml "$PPT/codontransformer-baseline-v01.xml" \
  --baseline-response "$PPT/codontransformer-baseline-response-v01.json" \
  --readback-xml "$PPT/codontransformer-readback-v02.xml" \
  --readback-response "$PPT/codontransformer-readback-response-v02.json" \
  --add-response "$PPT/codontransformer-add-response-v01.json" \
  --evidence-dir "$R" --output <NEW_PPT_VERIFICATION_JSON>
```

---

# VeloHARMO fixed-source official bounded smoke

Fixed official source commit: `38b48079856aeb9d33a1b10844d77aa8f6640032`. The source archive has 31,429,853 bytes and SHA256 `68b029b667029827d9c7213249eebcac32e6152d80ef7c0e24e53d8437d5a0ef`. The E. coli processed matrix has 38,906,084 bytes and SHA256 `71008f948597daff282ccb3e124dd7e4c5b35aa92e2dbe4af43d5725d6fa740f`. Both fold-0 checkpoints are `models:BiGRU` with 105 input features, hidden size 128, two layers and 477,185 parameters. The 111-dimensional loader tensor therefore cannot be passed directly to these 105-dimensional models.

The deterministic seven-record subset contains the shortest eligible records with at least 30 codons, aligned sequence/count/feature lengths, finite nonconstant counts and at least one count greater than 0.5. Its SHA256 is `ba42db8a99b3d35e87c5c8c57d9333a7c01d62eff85aa8b3309c1bbdefef93ac`. The original GA hardcodes subset index 6, selecting C1P620 with 36 codons. The native matrix sequence has no terminal stop; final QC requires exact translation, no internal stop and preservation of the native terminal-stop convention rather than importing the C01 extra-stop contract.

## Official execution and retained failures

The unmodified `VeloGRU/run.py test` completed on `cuda:0` with return code 0. Across the seven length-selected records it produced mean Pearson `0.6044025421142578` and SD `0.17268328368663788`; direct recomputation gave the same mean, SD `0.17268326878547668`, and `metric_delta=1.4901161193847656e-08`. This is a processed-matrix, length-selected diagnostic, not held-out, OOD, five-species or publication performance.

The unmodified GA entry point failed with return code 1 and `ModuleNotFoundError: No module named 'Mimo_data'`; that evidence is retained. The production wrapper applies only seven auditable compatibility replacements: the missing import, matrix path, two checkpoint paths, plot path, population and generations. The algorithm body is unchanged. Bounded execution uses population 8, two generations, seed 20261118 and CPU single-thread execution. Official test/native prediction timings on CUDA and GA timing on CPU are separate device protocols and must not be combined into a fair cost comparison.

The GA objective is Pearson similarity between the native E. coli-model reference profile and yeast-model candidate profiles. It is a predicted-profile objective, not experimental function. Native/start/best fitness values are `-0.02560763992369175`, `0.34598612785339355` and `0.34598612785339355`. Start and best sequences are exactly identical, so iterative gain is zero. The `0.3715937677770853` best-minus-native difference describes only the initial candidate relative to native; it is neither GA improvement nor experimental functional gain. Both evaluated CDS sequences are legally synonymous and unique.

Independent re-execution passed **17/17 checks** with `max_numeric_delta=0.0`; unit tests passed **10/10**, and finalization passed **13/13** with status `CLOSED_BOUNDED_OFFICIAL_SMOKE`. Early stop-contract, patch-path/quoting, density-tolerance and CUDA/CPU failures are retained in separate raw directories. The final density comparison uses an explicit `5e-7` tolerance after quantifying the official float32 rounding difference (`1.9747801438541046e-07` maximum); the tolerance was not silently relaxed. Scientific evidence is in commit `8fce8dcaf5749d838f2378424b50042a8970cc27`.

## Reproduction

Run from `/home/codonflow-a8-rk`. Use new output/report paths for every fresh execution; do not overwrite frozen evidence or pre-create a log inside a production output directory that must be absent or empty.

```bash
PY=/root/miniconda3/envs/llr_env/bin/python
SRC=/home/codonflow-a8-rk-external/VeloHARMO-38b48079856aeb9d33a1b10844d77aa8f6640032
ART=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05
R=audits/20261118/RK05
MAT=audits/20261118/RK03/veloharmo_materialization.json

TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 $PY scripts/a8_rk05_veloharmo_official_smoke.py \
  --source-dir "$SRC" --materialization "$MAT" \
  --output-dir "$ART/veloharmo_reproduction_v1" \
  --report <NEW_PRODUCTION_REPORT> \
  --population-size 8 --generations 2 --seed 20261118

TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 $PY scripts/a8_rk05_verify_veloharmo_official_smoke.py \
  --source-dir "$SRC" --materialization "$MAT" \
  --production-report <NEW_PRODUCTION_REPORT> \
  --output-dir "$ART/veloharmo_independent_reproduction_v1" \
  --output <NEW_INDEPENDENT_REPORT>

$PY scripts/a8_rk05_finalize_veloharmo_official_smoke.py \
  --production-report <NEW_PRODUCTION_REPORT> \
  --independent-report <NEW_INDEPENDENT_REPORT> \
  --materialization-report "$MAT" \
  --loader-report audits/20261118/RK03/veloharmo_official_loader_smoke.json \
  --output <NEW_FINALIZATION_REPORT>
```

Production raw output is frozen under `$ART/veloharmo_official_smoke_38b480_v1/`; independent raw output is under `$ART/veloharmo_independent_v1/`. Final production and independent driver logs, early failure directories and thread-check diagnostics are retained separately. Code and commits remain under `/home`; matrices, checkpoints, generated FASTA/JSON/JPEG, logs and PPT raw XML remain under `/teams`.

## A8 v7 and online PPT verification

A8 v7 was generated from frozen evidence rather than hand-edited result numbers. It adds the CUDA diagnostic, CPU GA zero iterative gain, seven compatibility replacements, retained unmodified-entry failure, three VeloHARMO evidence sources and hard scope guards. A7 is unchanged. A8 SHA256 is `078228450f69c1efe6b31f7bbf7dba0d01d004c9aecdf2f330f4ad32c985fe6d`; independent paper verification passed **18/18** and remains `PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE`. A8 v7 generator/verifier evidence is in commit `9948b2ec251ae593ef9a864206cdd20672134923`.

The verified result was appended once to the existing online deck as slide 75, `pgh`, revision 37. Independent post-write verification passed **10/10 checks**: all previous 74 slide IDs/order and semantic XML remained unchanged, and the four-row native/start/best table, KPI values, notes, page bounds and scientific boundaries were recomputed from frozen evidence. The initial 9/10 report was caused only by trailing whitespace after slide 74's closing tag; its failure report and element-by-element diff are retained, and the final semantic comparison ignores only XML tail whitespace. Readback XML SHA256 is `863fb78d364a05b21a9ceceb133f72aa8751d404643d8f9b58b877953164ae12`. PPT evidence is in commit `49ed134d4966fcc5c8d70c00c654cd414b898c51`.

Reproduce the readback audit without changing the online deck:

```bash
$PY scripts/a8_rk05_verify_veloharmo_ppt.py \
  --repo /home/codonflow-a8-rk \
  --raw-dir "$ART/ppt_veloharmo_v1" \
  --output <NEW_PPT_VERIFICATION_JSON>
```

This closes only the bounded official smoke. Five-species processed matrices, formal training/cross-validation, the complete strong-baseline matrix, matched cost, functional OOD, CodonFlow-RK generation and SOTA remain open.
