# A8-RK19 full CPU regression closeout

Date: 2026-11-20
Branch: `a8-rk`

## Scope

Repair the declared scientific/test dependencies and run the complete project CPU test suite in the existing `codonflow` environment. No model training, functional-untouched evaluation, generator execution, or scientific gate change was performed.

## Repair

The initial run collected 297 tests but stopped with four collection errors because `pandas` and `sklearn` were unavailable. The environment now contains:

- `pandas==2.2.2`
- `scikit-learn==1.7.2`
- `numpy==2.2.6`
- `scipy==1.15.3`

`pip check` reports no broken requirements. `environment.yml` pins the two added packages. The `dev` and `analysis` extras in `pyproject.toml` declare them, and the pytest `integration` marker is registered.

## Verified result

- Final collection: 331 tests.
- Final result: **330 passed, 1 skipped, 0 failed, 0 errors**.
- Runtime: 27.12 seconds.
- Device contract: `CUDA_VISIBLE_DEVICES` empty; CPU execution.
- Independent verification: 15/15 PASS.
- The only skip is `tests/test_gpu_queue_integration.py::test_queue_lifecycle_in_isolated_tmux`, with reason `explicit tmux integration opt-in`.
- The unknown-integration-marker warning is removed. Eleven scientific/runtime warnings remain visible and are not suppressed.

The JUnit header says `tests=336`, while the same file contains 331 testcase elements and the console reports 331 collected tests. This five-count metadata discrepancy is recorded explicitly in the verification report. Acceptance uses the console summary plus independently enumerated testcase elements, not the inconsistent header attribute.

## Files

- `environment.yml`
- `pyproject.toml`
- `tests/test_rk19_environment_contract.py`
- `scripts/a8_rk19_verify_full_regression.py`
- `audits/20261120/RK19/rk19_full_cpu_regression_v2.json`

Console logs, JUnit XML, installation logs, the initial collection failure, and the rejected first verifier report are under:

`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk19/full_regression_20261120_v1/`

## Fresh clean-prefix CPU-suite reproduction

A separate conda prefix, `/home/codonflow-rk19-clean-explicit-v2`, was created from the retained 25-URL explicit base specification. The conda package cache had to remain on the POSIX `/home` filesystem because `/teams` rejected conda archive backward seeks; the failed attempts and successful transaction log are retained. Project and scientific dependencies were installed from the declared `dev`, `eval`, and `baselines` extras using a recovered local wheelhouse plus explicitly logged gap downloads.

The clean prefix contains Python 3.10.22, torch 2.11.0+cu128, numpy 2.2.6, scipy 1.15.3, pandas 2.2.2, scikit-learn 1.7.2, pytest 9.1.1, ViennaRNA 2.7.2, pymoo 0.6.2, RapidFuzz 3.14.5, and transformers 4.46.3. This is a fresh reproduction within declared compatible dependency ranges, not an exact copy of the repaired environment's torch 2.14.1+cu132 / transformers 5.20.2 stack.

- `pip check`: no broken requirements.
- Full CPU suite: **331 collected; 330 passed, 1 skipped, 0 failed, 0 errors** in 15.91 seconds.
- Independent clean-environment verification: **24/24 PASS** (`PASS_CLEAN_CPU_SUITE`).
- The only skip remains the explicit opt-in isolated tmux integration test; no opt-in tmux/GPU integration was executed.
- The JUnit header again reports 336 while containing 331 testcase elements; the same metadata observation is retained, and acceptance uses the console and enumerated cases.
- The verifier confirmed an isolated executable/prefix, no external `PYTHONPATH`, site-packages under the clean prefix, official conda package URLs, all scientific imports, and unchanged scientific gates.

New tracked files:

- `scripts/a8_rk19_verify_clean_environment.py`
- `audits/20261120/RK19/rk19_clean_cpu_suite_v1.json` (SHA256 `1519bb89f528d1f04801fdf945900c3d9f8c22fa2766c80b426f6428a798ca6f`)

The successful environment-creation log, explicit specification, package freeze/list, import audit, pip-check log, full console/JUnit outputs, recovered-wheelhouse logs, all failed installation attempts, and the retained verifier-schema failure are under the RK19 artifact directory above. The verifier-schema failure was a wrong input-report selection (`gates` absent), not a test or environment failure; the corrected run uses the exact-commit post-push science-gate report.

## Boundary

This closes both the repaired-existing-environment and fresh-clean-prefix **CPU test-suite** reproductions. It does not close full experimental reproduction, model/data artifact regeneration, opt-in tmux/GPU integration, RK-G1, functional untouched, generator authorization, or external-SOTA authorization. All those scientific gates remain false or unexecuted as recorded in the independent report.
