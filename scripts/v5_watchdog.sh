#!/bin/bash
# v5 watchdog: resume-until-convergence, per-5min, hardstop-safe
PY=/home/cunyuliu/miniconda3/envs/codonflow/bin/python
OUT=/mnt/cunyuliu/codonflow/checkpoints
S=/mnt/cunyuliu/codonflow/corpora/splits_v3
LOG=$OUT/watchdog5.log
echo "=== watchdog v5 start $(date) ===" >> $LOG

alive() { pgrep -f "run_pretrain.py.*--d-model $1 " > /dev/null 2>&1; }
converged() { [ -f "$1/converged.pt" ]; }

gpu_free_whole() {
  u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i "$1" | tr -d " ")
  t=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i "$1" | tr -d " ")
  echo $(( t - u ))
}

launch() {  # $1 dev $2 dmodel $3 layers $4 heads $5 tag $6 batch $7 accum
  echo "$(date) launch d=$2 on $1 batch=$6 accum=$7 (resume)" >> $LOG
  tmux kill-session -t "$5" 2>/dev/null
  RA=""
  [ -f "$OUT/$5/last.pt" ] && RA="--resume $OUT/$5/last.pt"
  tmux new-session -d -s "$5" "cd /home/cunyuliu/codonflow &&     CUDA_VISIBLE_DEVICES=$1 PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True     $PY src/codonflow/train/run_pretrain.py     --train-fasta $S/train.fasta --val-fasta $S/val.fasta     --out-dir $OUT/$5 --d-model $2 --n-layers $3 --n-heads $4     --dropout 0.0 --batch-tokens $6 --grad-accum $7 --lr 1e-5 $RA     >> $OUT/$5/train.log 2>&1; echo EXIT=$? at $(date) >> $OUT/$5/train.log"
}

i=0
while [ $i -lt 2000 ]; do
  HHMM=$(date +%H%M)
  if [ "$HHMM" -ge 2330 ] 2>/dev/null; then
    echo "$(date) time-gate 2330 — no new launches" >> $LOG
    break
  fi
  # 56M: prefer whole GPU with >=10GB free (speed), fallback GPU6 MIG dev2 (4.6GB)
  if ! converged $OUT/p3_v3_56m && ! alive 768; then
    PLACED=0
    for gi in 0 4 2 5 3; do
      ff=$(gpu_free_whole $gi)
      if [ "$ff" -ge 10000 ]; then launch $gi 768 8 12 p3_v3_56m 20000 1; PLACED=1; break; fi
    done
    if [ $PLACED -eq 0 ]; then
      u6=$(nvidia-smi -i 6 2>/dev/null | grep '  6    9 ' | grep -oE '^\|  6    9   0   2  \| *[0-9]+' | grep -oE '[0-9]+$')
      u6=$(nvidia-smi -i 6 2>/dev/null | sed -n 's/^|  6    9   0   2  *| *\([0-9]*\)MiB.*/\1/p')
      [ -z "$u6" ] && u6=99999
      if [ "$u6" -le 500 ]; then launch MIG-4c9214e6-acd9-5d8a-98a6-feb9c94236c8 768 8 12 p3_v3_56m 8000 3; PLACED=1; fi
    fi
  fi
  # 355M: whole card >=11GB free, batch 4000x15 (small footprint, contention-resistant)
  if ! converged $OUT/p3_v3_355m && ! alive 1280; then
    for gi in 1 0 4 2 5 3; do
      ff=$(gpu_free_whole $gi)
      if [ "$ff" -ge 11000 ]; then launch $gi 1280 12 16 p3_v3_355m 4000 15; break; fi
    done
  fi
  if converged $OUT/p3_v3_355m && converged $OUT/p3_v3_56m; then
    echo "$(date) both converged — exit" >> $LOG; break
  fi
  i=$((i+1)); sleep 300
done
