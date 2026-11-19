#!/usr/bin/env bash
set -euo pipefail

REPO=/home/codonflow-a8-rk
PY=/root/miniconda3/envs/llr_env/bin/python
ROOT=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_full_094c_v1
AUDITS="$REPO/audits/20261118/RK05"
PROTOCOL="$AUDITS/ribomimo_full_mohammad16_protocol_v2.json"
PRODUCTION="$AUDITS/ribomimo_full_mohammad16_v2.json"
PRODUCTION_FAILED="$AUDITS/ribomimo_full_mohammad16_v2_failed.json"
RETRAIN="$AUDITS/ribomimo_full_mohammad16_retrain_v1.json"
RETRAIN_FAILED="$AUDITS/ribomimo_full_mohammad16_retrain_v1_failed.json"
INDEPENDENT="$AUDITS/ribomimo_full_mohammad16_independent_v1.json"
FINALIZATION="$AUDITS/ribomimo_full_mohammad16_finalization_v1.json"

wait_for_terminal_report() {
  local report="$1"
  local failed="$2"
  local label="$3"
  for _iteration in $(seq 1 720); do
    if [[ -f "$report" ]]; then
      "$PY" - "$report" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
assert report["status"].startswith("PASS_COMPLETE_OFFICIAL_1X10FOLD_MAX100"), report["status"]
PY
      printf '%s terminal success: %s\n' "$label" "$report"
      return 0
    fi
    if [[ -f "$failed" ]]; then
      printf '%s terminal failure: %s\n' "$label" "$failed" >&2
      return 1
    fi
    sleep 30
  done
  printf '%s timed out waiting for terminal report\n' "$label" >&2
  return 1
}

printf 'Waiting for the first full production run.\n'
wait_for_terminal_report "$PRODUCTION" "$PRODUCTION_FAILED" production

printf 'Starting independent full deterministic retrain.\n'
"$PY" "$REPO/scripts/a8_rk05_ribomimo_full_official.py" \
  --protocol "$PROTOCOL" \
  --output-dir "$ROOT/mohammad16_retrain_v1" \
  --report "$RETRAIN" \
  > "$ROOT/mohammad16_retrain_v1.driver.log" 2>&1
wait_for_terminal_report "$RETRAIN" "$RETRAIN_FAILED" retrain

printf 'Starting independent two-pass checkpoint verification.\n'
"$PY" "$REPO/scripts/a8_rk05_verify_ribomimo_full.py" \
  --production-report "$PRODUCTION" \
  --output-dir "$ROOT/mohammad16_independent_v1" \
  --report "$INDEPENDENT" \
  > "$ROOT/mohammad16_independent_v1.driver.log" 2>&1
"$PY" - "$INDEPENDENT" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
assert report["status"] == "PASS", report["status"]
assert report["checks_total"] == report["checks_passed"]
PY

printf 'Starting final cross-artifact verification.\n'
"$PY" "$REPO/scripts/a8_rk05_finalize_ribomimo_full.py" \
  --production-report "$PRODUCTION" \
  --independent-report "$INDEPENDENT" \
  --retrain-report "$RETRAIN" \
  --output-dir "$ROOT/mohammad16_finalization_v1" \
  --report "$FINALIZATION" \
  > "$ROOT/mohammad16_finalization_v1.driver.log" 2>&1
"$PY" - "$FINALIZATION" <<'PY'
import hashlib
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
report = json.loads(path.read_text())
assert report["status"] == "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_INFERENCE", report["status"]
assert report["checks_total"] == report["checks_passed"]
assert report["all_checkpoints_bitwise_equal"] is True
print(json.dumps({
    "pipeline_status": "PASS",
    "final_report": str(path),
    "final_report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    "checks": [report["checks_passed"], report["checks_total"]],
}, indent=2))
PY
