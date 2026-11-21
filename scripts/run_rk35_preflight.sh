#!/usr/bin/env bash
set -euo pipefail
cd /home/codonflow-a8-rk
PY=/home/codonflow-clean-env-v1/bin/python
TEAMS=/teams/HoulabData_1788502323/liucunyu/codonflow1031
MAIN="$TEAMS/rk21/kudla_recovery_v1/derived/kudla154_source.csv"
COV=audits/20261121/RK27/rk27_sequence_coverage_v1.json
R32PRE="$TEAMS/rk32/structure_definition_v1/preflight_candidate_energies.csv"
R32RES=audits/20261121/RK32/rk32_structure_definition_result_v2.json
OUTCSV="$TEAMS/rk35/coverage_transport_v1/preflight_candidate_windows.csv"
REPORT=audits/20261122/RK35/rk35_preflight_v1.json
mkdir -p "$TEAMS/rk35/coverage_transport_v1"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
sha() { sha256sum "$1" | cut -d' ' -f1; }
"$PY" scripts/a8_rk35_preflight.py \
  --main-csv "$MAIN" --main-sha "$(sha "$MAIN")" \
  --coverage-report "$COV" --coverage-sha "$(sha "$COV")" \
  --rk32-preflight-csv "$R32PRE" --rk32-preflight-sha "$(sha "$R32PRE")" \
  --rk32-result "$R32RES" --rk32-result-sha "$(sha "$R32RES")" \
  --output-csv "$OUTCSV" --report "$REPORT"