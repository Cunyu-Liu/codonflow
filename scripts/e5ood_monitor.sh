#!/bin/bash
# E5 OOD monitor: checks 4 arms alive + progress; writes snapshot; alerts on death/OOM
LOGDIR=/mnt/cunyuliu/codonflow/logs
WATCH=/mnt/cunyuliu/codonflow/logs/e5ood_watch.log
HEARTBEAT=/mnt/cunyuliu/codonflow/logs/gpu_heartbeat.csv
echo "=== $(date +%F_%T) ===" >> $WATCH
for t in egfp_s0 egfp_s1 egfp_s2 nluc_s0 nluc_s1 nluc_s2 ood; do
  TLOG=$LOGDIR/e5_ood_${t}.log
  JSON=/mnt/cunyuliu/codonflow/eval_outputs/E5_ood_${t}.json
  alive=$(tmux has-session -t e5o_${t} 2>/dev/null && echo ALIVE || echo GONE)
  last=$(tail -1 $TLOG 2>/dev/null | head -c 120)
  json_time=$(stat -c %y $JSON 2>/dev/null | cut -d. -f1)
  echo "[$t] $alive | json_mtime=$json_time | last: $last" >> $WATCH
  if [ "$alive" == "GONE" ] && ! grep -q "wrote /mnt" $TLOG 2>/dev/null; then
    echo "[$t] ALERT: session died WITHOUT final write. Tail:" >> $WATCH
    tail -5 $TLOG 2>/dev/null >> $WATCH
  fi
done
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader >> $WATCH
echo "---" >> $WATCH
