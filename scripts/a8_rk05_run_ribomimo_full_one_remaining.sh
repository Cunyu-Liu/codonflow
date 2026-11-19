#!/usr/bin/env bash
set -euo pipefail
DATASET="${1:?dataset required}"
case "$DATASET" in
  Subtelny14) SLUG="subtelny14" ;;
  Mohammad19-1) SLUG="mohammad19_1" ;;
  Mohammad19-2) SLUG="mohammad19_2" ;;
  *) echo "Unsupported dataset: $DATASET" >&2; exit 2 ;;
esac
REPO=/home/codonflow-a8-rk
AUDIT="$REPO/audits/20261118/RK05"
ROOT=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_full_094c_v1
PROTOCOL="$AUDIT/ribomimo_full_${SLUG}_protocol_v1.json"
PROD_OUT="$ROOT/${SLUG}_v1"
RETRAIN_OUT="$ROOT/${SLUG}_retrain_v1"
PROD_REPORT="$AUDIT/ribomimo_full_${SLUG}_v1.json"
RETRAIN_REPORT="$AUDIT/ribomimo_full_${SLUG}_retrain_v1.json"
INDEP_REPORT="$AUDIT/ribomimo_full_${SLUG}_independent_v1.json"
FINAL_REPORT="$AUDIT/ribomimo_full_${SLUG}_finalization_v1.json"
PROD_FAILED="$AUDIT/ribomimo_full_${SLUG}_v1_failed.json"
RETRAIN_FAILED="$AUDIT/ribomimo_full_${SLUG}_retrain_v1_failed.json"
DRIVER="$REPO/scripts/a8_rk05_ribomimo_full_official.py"
VERIFIER="$REPO/scripts/a8_rk05_verify_ribomimo_full_generic.py"
FINALIZER="$REPO/scripts/a8_rk05_finalize_ribomimo_full_generic.py"
PY=/root/miniconda3/envs/llr_env/bin/python
cd "$REPO"

require_pass() {
  "$PY" - "$1" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text())
if not (data["status"] == "PASS" or data["status"].startswith("PASS_COMPLETE")):
    raise SystemExit(f"Not PASS: {path}: {data['status']}")
print(f"CONFIRMED {data['status']}: {path}")
PY
}

if [[ -f "$FINAL_REPORT" ]]; then
  require_pass "$FINAL_REPORT"
  exit 0
fi
for failure in "$PROD_FAILED" "$RETRAIN_FAILED"; do
  if [[ -f "$failure" ]]; then
    echo "Retained failure blocks automatic retry: $failure" >&2
    exit 1
  fi
done

if [[ ! -f "$PROD_REPORT" ]]; then
  if [[ -d "$PROD_OUT" ]] && [[ -n "$(ls -A "$PROD_OUT")" ]]; then
    echo "Nonempty production directory without a final report; retained for diagnosis: $PROD_OUT" >&2
    exit 1
  fi
  "$PY" "$DRIVER" --protocol "$PROTOCOL" --output-dir "$PROD_OUT" --report "$PROD_REPORT"
fi
require_pass "$PROD_REPORT"

if [[ ! -f "$RETRAIN_REPORT" ]]; then
  if [[ -d "$RETRAIN_OUT" ]] && [[ -n "$(ls -A "$RETRAIN_OUT")" ]]; then
    echo "Nonempty retrain directory without a final report; retained for diagnosis: $RETRAIN_OUT" >&2
    exit 1
  fi
  "$PY" "$DRIVER" --protocol "$PROTOCOL" --output-dir "$RETRAIN_OUT" --report "$RETRAIN_REPORT"
fi
require_pass "$RETRAIN_REPORT"

if [[ ! -f "$INDEP_REPORT" ]]; then
  if [[ -d "$ROOT/${SLUG}_independent_v1" ]] && [[ -n "$(ls -A "$ROOT/${SLUG}_independent_v1")" ]]; then
    echo "Nonempty independent work directory without a final report; retained for diagnosis: $ROOT/${SLUG}_independent_v1" >&2
    exit 1
  fi
  "$PY" "$VERIFIER" --production-report "$PROD_REPORT" --report "$INDEP_REPORT" --output-dir "$ROOT/${SLUG}_independent_v1"
fi
require_pass "$INDEP_REPORT"

if [[ ! -f "$FINAL_REPORT" ]]; then
  if [[ -d "$ROOT/${SLUG}_finalization_v1" ]] && [[ -n "$(ls -A "$ROOT/${SLUG}_finalization_v1")" ]]; then
    echo "Nonempty finalization work directory without a final report; retained for diagnosis: $ROOT/${SLUG}_finalization_v1" >&2
    exit 1
  fi
  "$PY" "$FINALIZER" --production-report "$PROD_REPORT" --independent-report "$INDEP_REPORT" --retrain-report "$RETRAIN_REPORT" --output-dir "$ROOT/${SLUG}_finalization_v1" --report "$FINAL_REPORT"
fi
require_pass "$FINAL_REPORT"
