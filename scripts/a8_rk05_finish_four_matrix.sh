#!/usr/bin/env bash
set -euo pipefail
REPO=/home/codonflow-a8-rk
AUDIT="$REPO/audits/20261118/RK05"
ROOT=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_full_094c_v1
PY=/root/miniconda3/envs/llr_env/bin/python
FINAL="$AUDIT/ribomimo_full_mohammad19_2_finalization_v1.json"
while [[ ! -f "$FINAL" ]]; do
  sleep 60
done
cd "$REPO"
"$PY" scripts/a8_rk05_ribomimo_full_four_matrix_summary.py --repo "$REPO" 2>&1 | tee "$ROOT/four_matrix_summary.console.log"
"$PY" scripts/a8_rk05_verify_ribomimo_full_four_matrix_summary.py --repo "$REPO" 2>&1 | tee "$ROOT/four_matrix_summary_verification.console.log"
"$PY" scripts/a8_rk05_ribomimo_full_four_matrix_paper_addition.py --repo "$REPO" 2>&1 | tee "$ROOT/four_matrix_paper_v15.console.log"
"$PY" scripts/a8_rk05_verify_ribomimo_full_four_matrix_paper.py --repo "$REPO" 2>&1 | tee "$ROOT/four_matrix_paper_v15_verification.console.log"
echo "FOUR_MATRIX_SUMMARY_AND_A8_V15_COMPLETE"
