#!/usr/bin/env bash
set -euo pipefail
cd /home/codonflow-a8-rk
PY=/home/codonflow-clean-env-v1/bin/python
TEAMS=/teams/HoulabData_1788502323/liucunyu/codonflow1031
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
"$PY" scripts/a8_rk35_run_coverage_transport.py \
  --protocol configs/a8_rk35_coverage_transport_protocol_v1.json \
  --output-root "$TEAMS/rk35/coverage_transport_v1/model_results_v1" \
  --summary audits/20261122/RK35/rk35_coverage_transport_result_v1.json