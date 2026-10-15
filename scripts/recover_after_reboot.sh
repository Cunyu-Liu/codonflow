#!/bin/bash
# CodonFlow 停机后一键恢复（2026-10-15 预案）
# 服务器重启后执行: bash /home/cunyuliu/codonflow/scripts/recover_after_reboot.sh
set -u
cd /home/cunyuliu/codonflow
OUT=/mnt/cunyuliu/codonflow/checkpoints
LOG=$OUT/recover.log
echo "=== recovery start $(date) ===" >> $LOG

# 1. 等待系统就绪（挂载 + GPU 驱动）
for i in $(seq 1 30); do
  [ -d /mnt/cunyuliu/codonflow ] && command -v nvidia-smi >/dev/null && break
  echo "[$(date +%T)] waiting mounts/gpu ($i)" >> $LOG; sleep 20
done

# 2. 起 tmux server
tmux new-session -d -s recover_init "sleep 1" 2>/dev/null || true

# 3. 355M 续训（若未收敛）
if [ ! -f $OUT/p3_v3_355m/converged.pt ]; then
  GPU=$(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | awk -F', ' '$2<10000 {print $1; exit}')
  GPU=${GPU:-3}
  tmux new-session -d -s p3_v3_355m "cd /home/cunyuliu/codonflow && CUDA_VISIBLE_DEVICES=$GPU PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True /home/cunyuliu/miniconda3/envs/codonflow/bin/python src/codonflow/train/run_pretrain.py --train-fasta /mnt/cunyuliu/codonflow/corpora/splits_v3/train.fasta --val-fasta /mnt/cunyuliu/codonflow/corpora/splits_v3/val.fasta --out-dir $OUT/p3_v3_355m --d-model 1280 --n-layers 12 --n-heads 16 --dropout 0.0 --batch-tokens 4000 --grad-accum 15 --lr 1e-5 --resume $OUT/p3_v3_355m/last.pt >> $OUT/p3_v3_355m/train.log 2>&1"
  echo "[$(date +%T)] 355M resumed on GPU$GPU from last.pt" >> $LOG
fi

# 4. v7 watchdog（兜底守直至双收敛）
tmux kill-session -t v3wd7 2>/dev/null || true
tmux new-session -d -s v3wd7 "bash /home/cunyuliu/codonflow/scripts/v7_watchdog.sh"
echo "[$(date +%T)] v7 watchdog restarted" >> $LOG

# 5. 56M 评测链（若未全部完成）
N=$(ls /mnt/cunyuliu/codonflow/eval_outputs/ 2>/dev/null | grep -c "E5_v3_56m")
if [ "$N" -lt 15 ]; then
  tmux new-session -d -s v3eval56m "bash /home/cunyuliu/codonflow/scripts/run_v3_eval.sh p3_v3_56m v3_56m launch"
  echo "[$(date +%T)] 56M eval chains relaunched (had $N/15)" >> $LOG
fi
echo "=== recovery done $(date) ===" >> $LOG
