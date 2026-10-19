#!/bin/bash
# v7: post-crash watchdog. FIXED slots, 5-min poll, resume-until-convergence.
# 56M -> first free of GPU0/GPU4 (>=14GB); 355M -> first free of GPU3/GPU4/GPU5 (>=10GB, small batch 4000x15)
PY=/root/miniconda3/envs/codonflow/bin/python
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints
S=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/splits_v3
LOG=$OUT/watchdog7.log
echo "=== watchdog v7 start $(date) ===" >> $LOG
alive() { pgrep -f "run_pretrain.py.*--d-model $1 " > /dev/null 2>&1; }
converged() { [ -f "$1/converged.pt" ]; }
free_mi() { u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $1 | tr -d ' '); echo $((40960-u)); }
launch56() { gi=$1; echo "$(date) launch 56m on $gi" >> $LOG; tmux kill-session -t p3_v3_56m 2>/dev/null; tmux new-session -d -s p3_v3_56m "cd /home/codonflow && CUDA_VISIBLE_DEVICES=$gi PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY src/codonflow/train/run_pretrain.py --train-fasta $S/train.fasta --val-fasta $S/val.fasta --out-dir $OUT/p3_v3_56m --d-model 768 --n-layers 8 --n-heads 12 --dropout 0.0 --batch-tokens 24000 --grad-accum 1 --lr 1e-5 --resume $OUT/p3_v3_56m/last.pt >> $OUT/p3_v3_56m/train.log 2>&1"; }
launch355() { gi=$1; echo "$(date) launch 355m on $gi" >> $LOG; tmux kill-session -t p3_v3_355m 2>/dev/null; tmux new-session -d -s p3_v3_355m "cd /home/codonflow && CUDA_VISIBLE_DEVICES=$gi PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY src/codonflow/train/run_pretrain.py --train-fasta $S/train.fasta --val-fasta $S/val.fasta --out-dir $OUT/p3_v3_355m --d-model 1280 --n-layers 12 --n-heads 16 --dropout 0.0 --batch-tokens 4000 --grad-accum 15 --lr 1e-5 --resume $OUT/p3_v3_355m/last.pt >> $OUT/p3_v3_355m/train.log 2>&1"; }
while :; do
  if converged $OUT/p3_v3_355m && converged $OUT/p3_v3_56m; then echo "$(date) both converged — exit" >> $LOG; break; fi
  if ! converged $OUT/p3_v3_56m && ! alive 768; then
    for gi in 0 4 2 5; do f=$(free_mi $gi); if [ $f -ge 14000 ]; then launch56 $gi; break; fi; done
  fi
  if ! converged $OUT/p3_v3_355m && ! alive 1280; then
    for gi in 3 4 5 0; do f=$(free_mi $gi); if [ $f -ge 10000 ]; then launch355 $gi; break; fi; done
  fi
  sleep 300
done
