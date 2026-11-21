#!/usr/bin/env bash
# Usage: bash run_rk35_compare.sh <CLEAN_FULL_SHA>
set -euo pipefail
cd /home/codonflow-a8-rk
CLEAN_SHA="$1"
SHORT="${CLEAN_SHA:0:8}"
PY=/home/codonflow-clean-env-v1/bin/python
TEAMS=/teams/HoulabData_1788502323/liucunyu/codonflow1031
PROD="$TEAMS/rk35/coverage_transport_v1/model_results_v1"
REPRO="$TEAMS/rk35/coverage_transport_v1/clean_reproduction_$SHORT"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
"$PY" scripts/a8_rk35_compare_reproduction.py \
  --production-root "$PROD" \
  --reproduction-root "$REPRO/model_results_v1" \
  --production-summary audits/20261122/RK35/rk35_coverage_transport_result_v1.json \
  --reproduction-summary "$REPRO/result_v1.json" \
  --production-independent audits/20261122/RK35/rk35_coverage_transport_independent_v2.json \
  --reproduction-independent "$REPRO/independent_v1.json" \
  --report audits/20261122/RK35/rk35_reproduction_comparison_v2.json