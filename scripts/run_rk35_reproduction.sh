#!/usr/bin/env bash
# Usage: bash run_rk35_reproduction.sh <CLEAN_FULL_SHA>
set -euo pipefail
CLEAN_SHA="$1"
SHORT="${CLEAN_SHA:0:8}"
CLEAN="/home/codonflow-rk35-clean-$SHORT"
PY=/home/codonflow-clean-env-v1/bin/python
TEAMS=/teams/HoulabData_1788502323/liucunyu/codonflow1031
REPRO="$TEAMS/rk35/coverage_transport_v1/clean_reproduction_$SHORT"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
cd "$CLEAN"
mkdir -p "$REPRO/model_results_v1"
"$PY" scripts/a8_rk35_run_coverage_transport.py \
  --protocol configs/a8_rk35_coverage_transport_protocol_v1.json \
  --output-root "$REPRO/model_results_v1" \
  --summary "$REPRO/result_v1.json"
"$PY" scripts/a8_rk35_verify_coverage_transport.py \
  --protocol configs/a8_rk35_coverage_transport_protocol_v1.json \
  --production-root "$REPRO/model_results_v1" \
  --production-summary "$REPRO/result_v1.json" \
  --report "$REPRO/independent_v1.json"
echo REPRODUCTION_DONE