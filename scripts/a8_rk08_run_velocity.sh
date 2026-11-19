#!/usr/bin/env bash
set -euo pipefail
REPO=/home/codonflow-a8-rk
PY=/root/miniconda3/envs/llr_env/bin/python
RAW=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/clean/ribomimo_v2/ribomimo_clean.jsonl.gz
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/velocity_proxy_v1
AUDIT="$REPO/audits/20261118/RK08"
cd "$REPO"
export PYTHONPATH=src
mkdir -p "$OUT" "$AUDIT"
"$PY" scripts/a8_rk08_prepare_velocity.py \
  --input-jsonl "$RAW" --output-dir "$OUT" \
  --audit-json "$AUDIT/velocity_data_v1.json" > "$OUT/prepare.console.log" 2>&1
"$PY" scripts/a8_rk08_train_velocity.py \
  --data "$OUT/velocity_records.jsonl.gz" --config configs/a8_rk08_velocity_v1.json \
  --output-dir "$OUT/run_v1" --device cuda > "$OUT/train.console.log" 2>&1
"$PY" scripts/a8_rk08_train_velocity.py \
  --data "$OUT/velocity_records.jsonl.gz" --config configs/a8_rk08_velocity_v1.json \
  --output-dir "$OUT/retrain_v1" --device cuda > "$OUT/retrain.console.log" 2>&1
"$PY" scripts/a8_rk08_verify_velocity.py \
  --raw-jsonl "$RAW" --data "$OUT/velocity_records.jsonl.gz" \
  --data-audit "$AUDIT/velocity_data_v1.json" --config configs/a8_rk08_velocity_v1.json \
  --run-dir "$OUT/run_v1" --retrain-dir "$OUT/retrain_v1" \
  --output "$AUDIT/velocity_verification_v1.json" > "$OUT/verify.console.log" 2>&1
cp "$OUT/run_v1/run_summary.json" "$AUDIT/velocity_run_summary_v1.json"
cp "$OUT/run_v1/history.json" "$AUDIT/velocity_history_v1.json"
"$PY" scripts/a8_rk08_finalize_velocity.py \
  --data-audit "$AUDIT/velocity_data_v1.json" \
  --run-summary "$AUDIT/velocity_run_summary_v1.json" \
  --verification "$AUDIT/velocity_verification_v1.json" \
  --output "$AUDIT/velocity_finalization_v1.json" >> "$OUT/verify.console.log" 2>&1
cat "$OUT/verify.console.log"
