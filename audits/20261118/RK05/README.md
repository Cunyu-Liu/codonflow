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
