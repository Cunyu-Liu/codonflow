#!/bin/bash
# v6: FIXED-PLACEMENT watchdog (no dynamic card picking — that caused flapping)
# 56M -> GPU2 whole card batch 24000; 355M -> GPU1 whole card batch 4000x15
# resume-if-dead, per-5min, time-gate 2330 (no new launches after 23:30)
PY=/home/cunyuliu/miniconda3/envs/codonflow/bin/python
OUT=/mnt/cunyuliu/codonflow/checkpoints
S=/mnt/cunyuliu/codonflow/corpora/splits_v3
LOG=$OUT/watchdog6.log
echo "=== watchdog v6 start $(date) ===" >> $LOG

alive() { pgrep -f "run_pretrain.py.*--d-model $1 " > /dev/null 2>&1; }
converged() { [ -f "$1/converged.pt" ]; }

i=0
while [ $i -lt 2000 ]; do
  HHMM=$(date +%H%M)
  if [ "$HHMM" -ge 2330 ] 2>/dev/null; then
    echo "$(date) time-gate 2330 — exit" >> $LOG
    break
  fi
  if ! converged $OUT/p3_v3_56m && ! alive 768; then
    echo "$(date) relaunch 56m on GPU2 (resume)" >> $LOG
    tmux kill-session -t p3_v3_56m 2>/dev/null
    RA=""; [ -f $OUT/p3_v3_56m/last.pt ] && RA="--resume $OUT/p3_v3_56m/last.pt"
    tmux new-session -d -s p3_v3_56m "cd /home/cunyuliu/codonflow && CUDA_VISIBLE_DEVICES=2 PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY src/codonflow/train/run_pretrain.py --train-fasta $S/train.fasta --val-fasta $S/val.fasta --out-dir $OUT/p3_v3_56m --d-model 768 --n-layers 8 --n-heads 12 --dropout 0.0 --batch-tokens 24000 --grad-accum 1 --lr 1e-5 $RA >> $OUT/p3_v3_56m/train.log 2>&1; echo EXIT=$? at $(date) >> $OUT/p3_v3_56m/train.log"
  fi
  if ! converged $OUT/p3_v3_355m && ! alive 1280; then
    echo "$(date) relaunch 355m on GPU1 (resume)" >> $LOG
    tmux kill-session -t p3_v3_355m 2>/dev/null
    RA=""; [ -f $OUT/p3_v3_355m/last.pt ] && RA="--resume $OUT/p3_v3_355m/last.pt"
    tmux new-session -d -s p3_v3_355m "cd /home/cunyuliu/codonflow && CUDA_VISIBLE_DEVICES=1 PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY src/codonflow/train/run_pretrain.py --train-fasta $S/train.fasta --val-fasta $S/val.fasta --out-dir $OUT/p3_v3_355m --d-model 1280 --n-layers 12 --n-heads 16 --dropout 0.0 --batch-tokens 4000 --grad-accum 15 --lr 1e-5 $RA >> $OUT/p3_v3_355m/train.log 2>&1; echo EXIT=$? at $(date) >> $OUT/p3_v3_355m/train.log"
  fi
  if converged $OUT/p3_v3_355m && converged $OUT/p3_v3_56m; then echo "$(date) both converged — exit" >> $LOG; break; fi
  i=$((i+1)); sleep 300
done
