#!/bin/bash
# Watchdog v3: two-stage. Stage 1: GPU7 physical card < 10GB used (MIGs
# recoverable) -> launch BOTH pretrains (355M on MIG-10b9b777 batch 24000,
# 56M on MIG-6e59f9af batch 24000). Stage 2: any whole GPU0-5 with >= 22GB
# free for 2 consecutive polls -> 355M there (batch 20000, accum 3).
# Exits once a training launches (tmux session keeps the training alive).
set -u
PY=/home/cunyuliu/miniconda3/envs/codonflow/bin/python
OUT=/mnt/cunyuliu/codonflow/checkpoints
S=/mnt/cunyuliu/codonflow/corpora/splits_v3
LOG=$OUT/p3_v3_355m/watchdog.log
echo "=== watchdog v3 start $(date) ===" >> "$LOG"

gpu_used() {
  nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i "$1" | tr -d " "
}

pretrain_355() {  # $1 = CUDA device spec, $2 = batch tokens, $3 = accum
  echo "$(date) launching 355M on $1 batch=$2 accum=$3" >> "$LOG"
  cd /home/cunyuliu/codonflow
  CUDA_VISIBLE_DEVICES=$1 PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  $PY src/codonflow/train/run_pretrain.py \
    --train-fasta $S/train.fasta --val-fasta $S/val.fasta \
    --out-dir $OUT/p3_v3_355m \
    --d-model 1280 --n-layers 12 --n-heads 16 --dropout 0.0 \
    --batch-tokens $2 --grad-accum $3 --lr 1e-5 >> $OUT/p3_v3_355m/train.log 2>&1
  echo "$(date) 355M exited rc=$?" >> "$LOG"
}

pretrain_56() {  # $1 = CUDA device spec, $2 = batch tokens, $3 = accum
  echo "$(date) launching 56M on $1 batch=$2 accum=$3" >> "$LOG"
  cd /home/cunyuliu/codonflow
  CUDA_VISIBLE_DEVICES=$1 PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  $PY src/codonflow/train/run_pretrain.py \
    --train-fasta $S/train.fasta --val-fasta $S/val.fasta \
    --out-dir $OUT/p3_v3_56m \
    --d-model 768 --n-layers 8 --n-heads 12 --dropout 0.0 \
    --batch-tokens $2 --grad-accum $3 --lr 1e-5 >> $OUT/p3_v3_56m/train.log 2>&1
  echo "$(date) 56M exited rc=$?" >> "$LOG"
}

LAUNCHED=0
i=0
while [ $i -lt 576 ] && [ $LAUNCHED -eq 0 ]; do
  u7=$(gpu_used 7)
  if [ "$u7" -lt 10000 ]; then
    tmux new-session -d -s v3tr355 "$(declare -f pretrain_355); pretrain_355 MIG-10b9b777-a776-56de-9f7c-efde6c584f71 24000 1"
    LAUNCHED=1
    break
  fi
  if [ "$u7" -lt 26000 ]; then
    # one MIG may be usable: try 56M on 6e59f9af (needs ~6GB at batch 24000)
    tmux new-session -d -s v3tr56 "$(declare -f pretrain_56); pretrain_56 MIG-6e59f9af-2716-5bf2-ac6e-fb05ef744585 24000 1"
    echo "$(date) GPU7 partial (${u7}MiB): 56M launched on 6e59f9af, keep waiting for 355M space" >> "$LOG"
  fi
  if [ $LAUNCHED -eq 0 ]; then
    for gi in 0 1 2 3 4 5; do
      free=$(( 40960 - $(gpu_used $gi) ))
      if [ "$free" -ge 22000 ]; then
        tmux new-session -d -s v3tr355 "$(declare -f pretrain_355); pretrain_355 $gi 20000 3"
        LAUNCHED=1
        break
      fi
    done
  fi
  [ $LAUNCHED -eq 1 ] && break
  i=$((i + 1))
  sleep 300
done
[ $LAUNCHED -eq 0 ] && echo "$(date) watchdog v3 timeout" >> "$LOG"
echo "$(date) watchdog v3 exiting" >> "$LOG"
