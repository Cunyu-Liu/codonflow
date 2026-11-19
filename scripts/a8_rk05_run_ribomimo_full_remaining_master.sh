#!/usr/bin/env bash
set -euo pipefail
REPO=/home/codonflow-a8-rk
AUDIT="$REPO/audits/20261118/RK05"
ROOT=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_full_094c_v1
CURRENT_FINAL="$AUDIT/ribomimo_full_mohammad16_finalization_v1.json"
while [[ ! -f "$CURRENT_FINAL" ]]; do
  for failed in "$AUDIT/ribomimo_full_mohammad16_v2_failed.json" "$AUDIT/ribomimo_full_mohammad16_retrain_v1_failed.json"; do
    if [[ -f "$failed" ]]; then
      echo "Mohammad16 prerequisite failed: $failed" >&2
      exit 1
    fi
  done
  if [[ -f "$ROOT/full_reproduction_pipeline.log" ]] && grep -q "FATAL:" "$ROOT/full_reproduction_pipeline.log"; then
    echo "Mohammad16 prerequisite pipeline has a retained FATAL state." >&2
    exit 1
  fi
  echo "Waiting for Mohammad16 finalization before the remaining matrices."
  sleep 60
done
/root/miniconda3/envs/llr_env/bin/python - "$CURRENT_FINAL" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text())
if data["status"] != "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_INFERENCE":
    raise SystemExit(data["status"])
print("Mohammad16 prerequisite confirmed PASS.")
PY
for dataset in Subtelny14 Mohammad19-1 Mohammad19-2; do
  slug=$(printf '%s' "$dataset" | tr '[:upper:]' '[:lower:]' | tr '-' '_')
  echo "START $dataset"
  bash "$REPO/scripts/a8_rk05_run_ribomimo_full_one_remaining.sh" "$dataset" 2>&1 | tee -a "$ROOT/${slug}.pipeline.log"
  echo "COMPLETE $dataset"
done
echo "ALL_REMAINING_MATRICES_COMPLETE_WITH_RETRAIN_INDEPENDENT_AND_FINALIZATION"
