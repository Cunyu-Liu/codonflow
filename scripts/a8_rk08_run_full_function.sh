#!/usr/bin/env bash
set -euo pipefail
REPO=/home/codonflow-a8-rk
PYTHON=/root/miniconda3/envs/llr_env/bin/python
DATA=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk04/sequence_ood_v2/functional_long_sequence_ood.csv
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08
BASELINE=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk04/sequence_ood_model_v2/predictions.csv.gz
cd "$REPO"
export PYTHONPATH=src
run_one() {
  local config=$1
  local destination=$2
  local log=$3
  "$PYTHON" scripts/a8_rk08_train_ribokinetic.py \
    --data "$DATA" --config "$config" --output-dir "$destination" --device cuda > "$log" 2>&1
}
run_one configs/a8_rk08_full_function_all_config.json "$OUT/full_function_all_v2" "$OUT/full_function_all_v2.console.log"
run_one configs/a8_rk08_full_function_none_config.json "$OUT/full_function_none_v1" "$OUT/full_function_none_v1.console.log"
run_one configs/a8_rk08_full_function_all_config.json "$OUT/full_function_all_v2_retrain" "$OUT/full_function_all_v2_retrain.console.log"
run_one configs/a8_rk08_full_function_none_config.json "$OUT/full_function_none_v1_retrain" "$OUT/full_function_none_v1_retrain.console.log"
"$PYTHON" scripts/a8_rk08_compare_full_function.py \
  --data "$DATA" \
  --all-dir "$OUT/full_function_all_v2" \
  --none-dir "$OUT/full_function_none_v1" \
  --baseline-predictions "$BASELINE" \
  --train-script scripts/a8_rk08_train_ribokinetic.py \
  --output-dir "$OUT/full_function_comparison_v1" \
  --bootstrap 2000 --seed 20261119 > "$OUT/full_function_comparison_v1.console.log" 2>&1
