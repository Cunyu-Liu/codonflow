#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/codonflow-a8-rk
PY=/root/miniconda3/envs/llr_env/bin/python
DATA=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk04/sequence_ood_v2/functional_long_sequence_ood.csv
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/channel_screen_v1/screen
ARMS=(all none initiation_only velocity_only decay_only pair_only no_initiation no_velocity no_decay no_pair)
cd "$ROOT"
export PYTHONPATH=src
mkdir -p "$OUT"
for ARM in "${ARMS[@]}"; do
  CONFIG="configs/a8_rk08_channel_screen_${ARM}_config.json"
  DEST="$OUT/$ARM"
  LOG="$OUT/${ARM}.console.log"
  if [[ -e "$DEST" || -e "$LOG" ]]; then
    printf 'Refusing to overwrite existing channel-screen run: %s\n' "$ARM" >&2
    exit 2
  fi
  "$PY" scripts/a8_rk08_train_ribokinetic.py \
    --data "$DATA" --config "$CONFIG" --output-dir "$DEST" --device cuda > "$LOG" 2>&1
done
printf 'CHANNEL_SCREEN_TRAINING_COMPLETE arms=%s\n' "${#ARMS[@]}"
