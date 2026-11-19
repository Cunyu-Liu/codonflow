#!/usr/bin/env bash
set -euo pipefail
REPO=/home/codonflow-a8-rk
AUDIT="$REPO/audits/20261118/RK10"
ROOT=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk10/exact_trajectory_balance_v1
PY=/root/miniconda3/envs/llr_env/bin/python
PREREQ="$REPO/audits/20261118/RK05/ribomimo_full_mohammad19_2_finalization_v1.json"
mkdir -p "$AUDIT" "$ROOT"
START_WAIT=$(date +%s)
while [[ ! -f "$PREREQ" ]]; do
  if (( $(date +%s) - START_WAIT > 86400 )); then
    echo "Timed out waiting for nonconcurrent GPU execution: $PREREQ" >&2
    exit 1
  fi
  echo "Waiting for RiboMIMO GPU work to finish before RK10 exact CUDA optimization."
  sleep 60
done
"$PY" - "$PREREQ" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text())
if data.get("status") != "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_INFERENCE":
    raise SystemExit(f"Unexpected prerequisite status: {data.get('status')}")
print("RiboMIMO GPU prerequisite completed; starting RK10 without GPU contention.")
PY
cd "$REPO"
"$PY" -m pytest -q scripts/tests/test_a8_rk10_exact_tb.py 2>&1 | tee "$AUDIT/exact_tb_unit_tests.console.log"
"$PY" scripts/a8_rk10_train_exact_tb.py \
  --protocol configs/a8_rk10_exact_tb_protocol_v1.json \
  --output-dir "$ROOT/run_v1" \
  --report "$AUDIT/exact_tb_v1.json" \
  --device cuda 2>&1 | tee "$ROOT/run_v1.console.log"
"$PY" scripts/a8_rk10_train_exact_tb.py \
  --protocol configs/a8_rk10_exact_tb_protocol_v1.json \
  --output-dir "$ROOT/retrain_v1" \
  --report "$AUDIT/exact_tb_retrain_v1.json" \
  --device cuda 2>&1 | tee "$ROOT/retrain_v1.console.log"
"$PY" scripts/a8_rk10_verify_exact_tb.py \
  --production-report "$AUDIT/exact_tb_v1.json" \
  --output-dir "$ROOT/independent_v1" \
  --report "$AUDIT/exact_tb_independent_v1.json" 2>&1 | tee "$ROOT/independent_v1.console.log"
"$PY" scripts/a8_rk10_finalize_exact_tb.py \
  --production-report "$AUDIT/exact_tb_v1.json" \
  --retrain-report "$AUDIT/exact_tb_retrain_v1.json" \
  --independent-report "$AUDIT/exact_tb_independent_v1.json" \
  --unit-test-log "$AUDIT/exact_tb_unit_tests.console.log" \
  --output-dir "$ROOT/finalization_v1" \
  --report "$AUDIT/exact_tb_finalization_v1.json" 2>&1 | tee "$ROOT/finalization_v1.console.log"
echo "RK10_EXACT_TRAJECTORY_BALANCE_COMPLETE"
