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

## Boundary

This closes the full CPU suite in the repaired existing environment. It is not yet a fresh clean-environment reproduction, and the opt-in tmux integration test was not executed. RK-G1 remains false; functional untouched remains unevaluated; generator training remains unauthorized.
