#!/bin/bash
# HARD STOP for cluster shutdown: kill watchdog + all trainings at 05:00,
# verify checkpoint files exist, dump training state evidence to logs.
# Designed for 2026-10-13 05:00 (cluster shutdown deadline 06:30).
set -u
OUT=/mnt/cunyuliu/codonflow/checkpoints
LOG=$OUT/hardstop.log
echo "=== hardstop $(date) ===" >> "$LOG"

tmux kill-session -t v3wd4 2>/dev/null && echo "watchdog killed" >> "$LOG"
tmux kill-session -t v3wd 2>/dev/null

for sess in p3_v3_355m p3_v3_56m; do
  tmux kill-session -t $sess 2>/dev/null && echo "$sess session killed" >> "$LOG"
done

pkill -f "run_pretrain" 2>/dev/null
sleep 5

echo "--- 355m dir:" >> "$LOG"
ls -la $OUT/p3_v3_355m/ >> "$LOG" 2>&1
echo "--- 56m dir:" >> "$LOG"
ls -la $OUT/p3_v3_56m/ >> "$LOG" 2>&1
echo "--- last train lines:" >> "$LOG"
tail -2 $OUT/p3_v3_355m/train.log >> "$LOG" 2>&1
tail -2 $OUT/p3_v3_56m/train.log >> "$LOG" 2>&1
echo "=== hardstop done $(date) ===" >> "$LOG"
