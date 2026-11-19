#!/usr/bin/env bash
set -euo pipefail
cd /home/codonflow-a8-rk
export PYTHONPATH=/home/codonflow-a8-rk${PYTHONPATH:+:$PYTHONPATH}
PY=/root/miniconda3/envs/codonflow/bin/python
AUDIT=audits/20261118/RK12
GRID=$AUDIT/lineardesign_unique18_grid_v1.json
GRID_IND=$AUDIT/lineardesign_unique18_grid_independent_v1.json
MATRIX=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk12/actual_set_matrix_v1/unique18_actual_set_matrix.json
MATRIX_IND=$AUDIT/actual_set_matrix_independent_v1.json
FINAL=$AUDIT/rk12_finalization_v1.json
STATUS=$AUDIT/rk12_full_evaluation_status_v1.json
stage=waiting_for_grid
write_status() {
  local state=$1
  STAGE="$stage" STATE="$state" python3 - <<'PY'
import datetime as dt,json,os
from pathlib import Path
p=Path('audits/20261118/RK12/rk12_full_evaluation_status_v1.json')
d={'schema':'a8-rk12-full-evaluation-controller-v1','updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'state':os.environ['STATE'],'stage':os.environ['STAGE'],'pid':os.getppid()}
t=p.with_suffix('.tmp');t.write_text(json.dumps(d,indent=2)+'\n');t.replace(p)
PY
}
trap 'rc=$?; if [[ $rc -ne 0 ]]; then write_status FAILED; fi; exit $rc' EXIT
write_status WAITING
for _ in $(seq 1 1440); do
  [[ -f "$GRID" ]] && break
  sleep 30
done
[[ -f "$GRID" ]] || { echo "Timed out waiting for $GRID" >&2; exit 1; }
stage=grid_independent
write_status RUNNING
$PY scripts/a8_rk12_verify_lineardesign_unique18.py \
  --protocol configs/a8_rk12_lineardesign_unique18_protocol_v1.json \
  --production "$GRID" \
  --materialization audits/20261118/RK05/lineardesign_materialization.json \
  --build-report audits/20261118/RK05/lineardesign_build.json \
  --output "$GRID_IND" \
  > "$AUDIT/lineardesign_unique18_grid_independent_v1.console.log" 2>&1
stage=actual_set_matrix
write_status RUNNING
PYTHONPATH=src $PY scripts/a8_rk12_score_actual_set_matrix.py \
  --protocol configs/a8_rk12_actual_set_matrix_protocol_v1.json \
  --grid-protocol configs/a8_rk12_lineardesign_unique18_protocol_v1.json \
  --grid-report "$GRID" \
  --output "$MATRIX" \
  --audit "$AUDIT/actual_set_matrix_v1.json" \
  > "$AUDIT/actual_set_matrix_v1.console.log" 2>&1
stage=matrix_independent
write_status RUNNING
PYTHONPATH=src $PY scripts/a8_rk12_verify_actual_set_matrix.py \
  --protocol configs/a8_rk12_actual_set_matrix_protocol_v1.json \
  --grid-report "$GRID" \
  --matrix "$MATRIX" --output "$MATRIX_IND" \
  > "$AUDIT/actual_set_matrix_independent_v1.console.log" 2>&1
stage=finalization
write_status RUNNING
$PY scripts/a8_rk12_finalize.py \
  --grid-protocol configs/a8_rk12_lineardesign_unique18_protocol_v1.json \
  --grid "$GRID" --grid-independent "$GRID_IND" \
  --matrix-protocol configs/a8_rk12_actual_set_matrix_protocol_v1.json \
  --matrix "$MATRIX" --matrix-independent "$MATRIX_IND" \
  --prior-smoke audits/20261118/RK05/lineardesign_official_smoke_v2.json \
  --tests-log "$AUDIT/lineardesign_unique18_unit_tests.console.log" \
  --output "$FINAL" > "$AUDIT/rk12_finalization_v1.console.log" 2>&1
stage=complete
write_status PASS
trap - EXIT
