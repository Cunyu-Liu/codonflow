#!/bin/bash
# HARD STOP v2: kill watchdog FIRST (process + tmux), then trainings.
# v1 bug: watchdog survives tmux kill and auto-resumes training.
set -u
OUT=/mnt/cunyuliu/codonflow/checkpoints
LOG=$OUT/hardstop.log
echo "=== hardstop v2 $(date) ===" >> "$LOG"

pkill -f "v5_watchdog.sh" 2>/dev/null && echo "watchdog process killed" >> "$LOG"
tmux kill-session -t v3wd5 2>/dev/null && echo "watchdog tmux killed" >> "$LOG"
tmux kill-session -t v3wd 2>/dev/null

for sess in p3_v3_355m p3_v3_56m; do
  tmux kill-session -t $sess 2>/dev/null && echo "$sess session killed" >> "$LOG"
done

pkill -f "run_pretrain" 2>/dev/null && echo "pretrain procs killed" >> "$LOG"
sleep 5

if pgrep -f "run_pretrain" > /dev/null 2>&1; then
  pkill -9 -f "run_pretrain" 2>/dev/null
  echo "force-killed remnant pretrain" >> "$LOG"
fi

echo "--- 355m dir:" >> "$LOG"
ls -la $OUT/p3_v3_355m/ >> "$LOG" 2>&1
echo "--- 56m dir:" >> "$LOG"
ls -la $OUT/p3_v3_56m/ >> "$LOG" 2>&1
echo "--- last train lines:" >> "$LOG"
tail -2 $OUT/p3_v3_355m/train.log >> "$LOG" 2>&1
tail -2 $OUT/p3_v3_56m/train.log >> "$LOG" 2>&1
echo "=== hardstop v2 done $(date) ===" >> "$LOG"
