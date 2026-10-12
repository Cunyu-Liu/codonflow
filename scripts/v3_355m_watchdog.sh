#!/bin/bash
# Watchdog v2: scan for a device with >= 14GB free, then launch 355M pretrain.
# Candidates: whole GPUs 0-5 (by index, accounting per-GPU used) and GPU7 MIGs.
# Whole-GPU launch uses plain index (CUDA_VISIBLE_DEVICES=N) which is legal
# even if the GPU is MIG-enabled (GPU7 handled separately via its two MIGs).
set -u
PY=/home/cunyuliu/miniconda3/envs/codonflow/bin/python
OUT=/mnt/cunyuliu/codonflow/checkpoints
LOG=$OUT/p3_v3_355m/watchdog.log
NEED_MB=14336   # 14 GB
MODELS_LAUNCHED=0
mkdir -p "$OUT/p3_v3_355m"
echo "=== watchdog v2 start $(date) ===" >> "$LOG"

gpu_free() {  # $1 = whole-GPU index -> free MiB
  local u t
  u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i "$1" | tr -d " ")
  t=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i "$1" | tr -d " ")
  echo $(( t - u ))
}

i=0
while [ $i -lt 576 ] && [ $MODELS_LAUNCHED -eq 0 ]; do
  for gi in 0 1 2 3 4 5; do
    free=$(gpu_free $gi)
    if [ "$free" -ge "$NEED_MB" ]; then
      echo "$(date) GPU$gi free=${free}MiB -> launching 355M (whole GPU)" >> "$LOG"
      cd /home/cunyuliu/codonflow
      CUDA_VISIBLE_DEVICES=$gi PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
      $PY src/codonflow/train/run_pretrain.py \
        --train-fasta /mnt/cunyuliu/codonflow/corpora/splits_v3/train.fasta \
        --val-fasta /mnt/cunyuliu/codonflow/corpora/splits_v3/val.fasta \
        --out-dir $OUT/p3_v3_355m \
        --d-model 1280 --n-layers 12 --n-heads 16 --dropout 0.0 \
        --batch-tokens 60000 --lr 1e-5 >> $OUT/p3_v3_355m/train.log 2>&1
      echo "$(date) 355M training exited rc=$?" >> "$LOG"
      MODELS_LAUNCHED=1
      break
    fi
  done
  # GPU7: only if its physical memory has room for a 3g.20gb-style footprint
  if [ $MODELS_LAUNCHED -eq 0 ]; then
    free7=$(gpu_free 7)
    if [ "$free7" -ge 24576 ]; then
      echo "$(date) GPU7 free=${free7}MiB -> launching 355M (MIG-10b9b777)" >> "$LOG"
      cd /home/cunyuliu/codonflow
      CUDA_VISIBLE_DEVICES=MIG-10b9b777-a776-56de-9f7c-efde6c584f71 \
      PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
      $PY src/codonflow/train/run_pretrain.py \
        --train-fasta /mnt/cunyuliu/codonflow/corpora/splits_v3/train.fasta \
        --val-fasta /mnt/cunyuliu/codonflow/corpora/splits_v3/val.fasta \
        --out-dir $OUT/p3_v3_355m \
        --d-model 1280 --n-layers 12 --n-heads 16 --dropout 0.0 \
        --batch-tokens 60000 --lr 1e-5 >> $OUT/p3_v3_355m/train.log 2>&1
      echo "$(date) 355M training exited rc=$?" >> "$LOG"
      MODELS_LAUNCHED=1
    fi
  fi
  [ $MODELS_LAUNCHED -eq 1 ] && break
  i=$((i + 1))
  sleep 300
done
[ $MODELS_LAUNCHED -eq 0 ] && echo "$(date) watchdog timeout 48h" >> "$LOG"
