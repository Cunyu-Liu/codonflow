#!/usr/bin/env bash
set -euo pipefail
REPO=/home/codonflow-a8-rk
PY=/root/miniconda3/envs/llr_env/bin/python
BASE=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk11/minimal_neural_contract_v1
AUDIT=$REPO/audits/20261118/RK11
PROTOCOL=$REPO/configs/a8_rk11_minimal_neural_protocol_v1.json
export PYTHONPATH=$REPO/src
export CUBLAS_WORKSPACE_CONFIG=:4096:8
cd "$REPO"
mkdir -p "$AUDIT" "$BASE"
test ! -e "$BASE/production"
test ! -e "$BASE/retrain"
$PY -m pytest -q scripts/tests/test_a8_rk11_minimal_neural.py > "$AUDIT/minimal_neural_unit_tests.console.log" 2>&1
$PY scripts/a8_rk11_train_minimal_neural.py --protocol "$PROTOCOL" --output "$BASE/production" --report "$AUDIT/minimal_neural_v1.json" --run-label production > "$AUDIT/minimal_neural_production.console.log" 2>&1
$PY scripts/a8_rk11_train_minimal_neural.py --protocol "$PROTOCOL" --output "$BASE/retrain" --report "$AUDIT/minimal_neural_retrain_v1.json" --run-label independent_retrain > "$AUDIT/minimal_neural_retrain.console.log" 2>&1
$PY scripts/a8_rk11_verify_minimal_neural.py --protocol "$PROTOCOL" --production-artifacts "$BASE/production" --production-report "$AUDIT/minimal_neural_v1.json" --retrain-artifacts "$BASE/retrain" --retrain-report "$AUDIT/minimal_neural_retrain_v1.json" --report "$AUDIT/minimal_neural_independent_v1.json" > "$AUDIT/minimal_neural_independent.console.log" 2>&1
$PY scripts/a8_rk11_finalize_minimal_neural.py --protocol "$PROTOCOL" --production-artifacts "$BASE/production" --retrain-artifacts "$BASE/retrain" --production-report "$AUDIT/minimal_neural_v1.json" --retrain-report "$AUDIT/minimal_neural_retrain_v1.json" --independent-report "$AUDIT/minimal_neural_independent_v1.json" --independent-initial-failure "$AUDIT/minimal_neural_independent_initial_failure_v1.json" --independent-second-failure "$AUDIT/minimal_neural_independent_second_failure_v1.json" --development-report "$AUDIT/minimal_neural_development_v1.json" --test-log "$AUDIT/minimal_neural_unit_tests.console.log" --initial-failure-log "$AUDIT/minimal_neural_unit_tests_initial_failure.console.log" --second-failure-log "$AUDIT/minimal_neural_unit_tests_second_failure.console.log" --model-source "$REPO/src/codonflow/models/minimal_neural.py" --training-script "$REPO/scripts/a8_rk11_train_minimal_neural.py" --report "$AUDIT/minimal_neural_finalization_v1.json" > "$AUDIT/minimal_neural_finalization.console.log" 2>&1
cat "$AUDIT/minimal_neural_production.console.log" "$AUDIT/minimal_neural_retrain.console.log" "$AUDIT/minimal_neural_independent.console.log" "$AUDIT/minimal_neural_finalization.console.log"
