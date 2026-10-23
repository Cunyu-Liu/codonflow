#!/bin/bash
# v8-5090: RTX 5090 32GB single-GPU. 5-min poll, resume-until-convergence.
# vs 4090 版: free_mi 阈值 32607; batch-tokens 4000->12000 (占满 32GB)
# 等效 batch 保持: 12000 tokens x 5 accum = 60000 = 原 4000x15
PY=/root/miniconda3/envs/codonflow/bin/python
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints
S=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/splits_v3
LOG=$OUT/watchdog8.log
echo "=== watchdog v8-5090 start $(date) ===" >> $LOG
alive() { pgrep -f "run_pretrain.py.*--d-model $1 " > /dev/null 2>&1; }
converged() { [ -f "$1/converged.pt" ]; }
free_mi() { u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d " "); echo $((32607-u)); }
launch355() { gi=$1; echo "$(date) launch 355m on GPU$gi (5090 32GB profile)" >> $LOG; tmux kill-session -t p3_v3_355m 2>/dev/null; tmux new-session -d -s p3_v3_355m "cd /home/codonflow && CUDA_VISIBLE_DEVICES=$gi PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY src/codonflow/train/run_pretrain.py --train-fasta $S/train.fasta --val-fasta $S/val.fasta --out-dir $OUT/p3_v3_355m --d-model 1280 --n-layers 12 --n-heads 16 --dropout 0.0 --batch-tokens 20000 --grad-accum 3 --lr 1e-5 --resume $OUT/p3_v3_355m/last.pt >> $OUT/p3_v3_355m/train.log 2>&1"; }
while :; do
  if converged $OUT/p3_v3_355m; then echo "$(date) 355m converged — exit" >> $LOG; break; fi
  if ! alive 1280; then
    f=$(free_mi 0)
    if [ $f -ge 20000 ]; then launch355 0; fi
  fi
  sleep 300
done
