#!/bin/bash
# v8: RTX 4090 single-GPU cluster (24GB). 5-min poll, resume-until-convergence.
# 355M needs ~10GB; 56M already converged (converged.pt present, skip).
# Single GPU: run 355M training as priority; if converged, exit.
PY=/root/miniconda3/envs/codonflow/bin/python
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints
S=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/splits_v3
LOG=$OUT/watchdog8.log
echo "=== watchdog v8 start $(date) ===" >> $LOG
alive() { pgrep -f "run_pretrain.py.*--d-model $1 " > /dev/null 2>&1; }
converged() { [ -f "$1/converged.pt" ]; }
free_mi() { u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d " "); echo $((24564-u)); }
launch355() { gi=$1; echo "$(date) launch 355m on GPU$gi" >> $LOG; tmux kill-session -t p3_v3_355m 2>/dev/null; tmux new-session -d -s p3_v3_355m "cd /home/codonflow && CUDA_VISIBLE_DEVICES=$gi PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY src/codonflow/train/run_pretrain.py --train-fasta $S/train.fasta --val-fasta $S/val.fasta --out-dir $OUT/p3_v3_355m --d-model 1280 --n-layers 12 --n-heads 16 --dropout 0.0 --batch-tokens 4000 --grad-accum 15 --lr 1e-5 --resume $OUT/p3_v3_355m/last.pt >> $OUT/p3_v3_355m/train.log 2>&1"; }
while :; do
  if converged $OUT/p3_v3_355m; then echo "$(date) 355m converged — exit" >> $LOG; break; fi
  if ! alive 1280; then
    f=$(free_mi 0)
    if [ $f -ge 10000 ]; then launch355 0; fi
  fi
  sleep 300
done
