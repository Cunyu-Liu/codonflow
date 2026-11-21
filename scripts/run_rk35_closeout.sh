#!/usr/bin/env bash
# Usage: bash run_rk35_closeout.sh <CLEAN_FULL_SHA>
set -euo pipefail
cd /home/codonflow-a8-rk
CLEAN_SHA="$1"
SHORT="${CLEAN_SHA:0:8}"
PY=/home/codonflow-clean-env-v1/bin/python
TEAMS=/teams/HoulabData_1788502323/liucunyu/codonflow1031
REPRO="$TEAMS/rk35/coverage_transport_v1/clean_reproduction_$SHORT"
FREEZE=291ccdbc8637156341e9c61c25c1d9434df08ae3
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
"$PY" scripts/a8_rk35_closeout.py \
  --protocol configs/a8_rk35_coverage_transport_protocol_v1.json \
  --preflight-report audits/20261122/RK35/rk35_preflight_v1.json \
  --production-summary audits/20261122/RK35/rk35_coverage_transport_result_v1.json \
  --independent-report audits/20261122/RK35/rk35_coverage_transport_independent_v2.json \
  --reproduction-comparison audits/20261122/RK35/rk35_reproduction_comparison_v2.json \
  --reproduction-summary "$REPRO/result_v1.json" \
  --reproduction-independent "$REPRO/independent_v1.json" \
  --project-tests-json audits/20261122/RK35/rk35_project_tests_clean_v1.json \
  --rk35-tests-json audits/20261122/RK35/rk35_unit_tests_v1.json \
  --freeze-commit "$FREEZE" \
  --clean-commit "$CLEAN_SHA" \
  --report audits/20261122/RK35/rk35_closeout_v1.json