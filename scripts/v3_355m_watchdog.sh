#!/bin/bash
# Watchdog v4 (resident): keeps BOTH pretrains alive until convergence.
# - Detects dead training (no run_pretrain process for its out-dir)
# - Relaunches on first device with enough headroom (MIG instance check
#   via per-instance occupancy; whole cards need 2 consecutive free polls)
# - Exits when converged.pt exists for both models
set -u
PY=/root/miniconda3/envs/codonflow/bin/python
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints
S=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/splits_v3
LOG=$OUT/watchdog4.log
MIG_A=MIG-10b9b777-a776-56de-9f7c-efde6c584f71   # GPU7 3g.20gb #1
MIG_B=MIG-6e59f9af-2716-5bf2-ac6e-fb05ef744585   # GPU7 3g.20gb #2
echo "=== watchdog v4 start $(date) ===" >> "$LOG"

alive() {  # $1 = d-model of model; match only real python trainer processes
  pgrep -f "miniconda3/envs/codonflow/bin/python src/codonflow/train/run_pretrain.py.*--d-model $1 " > /dev/null 2>&1
}
converged() { [ -f "$1/converged.pt" ]; }

launch() {  # $1 dev, $2 dmodel, $3 layers, $4 heads, $5 dir, $6 batch, $7 accum
  echo "$(date) launch d=$2 on $1 batch=$6 accum=$7 (resume if last.pt)" >> "$LOG"
  tmux kill-session -t "$5" 2>/dev/null
  RESUME_ARG=""
  if [ -f "$OUT/$5/last.pt" ]; then
    RESUME_ARG="--resume $OUT/$5/last.pt"
  fi
  tmux new-session -d -s "$5" "cd /home/codonflow && \
    CUDA_VISIBLE_DEVICES=$1 PYTHONPATH=src PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    $PY src/codonflow/train/run_pretrain.py \
    --train-fasta $S/train.fasta --val-fasta $S/val.fasta \
    --out-dir $OUT/$5 --d-model $2 --n-layers $3 --n-heads $4 \
    --dropout 0.0 --batch-tokens $6 --grad-accum $7 --lr 1e-5 $RESUME_ARG \
    >> $OUT/$5/train.log 2>&1; echo EXIT=\$? at \$(date) >> $OUT/$5/train.log"
}

# per-MIG occupancy: parse nvidia-smi -i 7 MIG table lines "  7 GI CI 1 |  14570MiB / 20096MiB"
mig_used() {  # $1 = CI (0 for first 3g.20gb, 1 for second)
  nvidia-smi -i 7 2>/dev/null | awk -v ci="$1" '
    /MIG devices/{seen=1; next}
    seen && NF >= 8 {
      split($4, a, "|"); gi=$2; ci_now=$4;
    }
    seen && $0 ~ /MiB \/ 20096MiB/ {
      line=$0; gsub(/[^0-9MiB \/]/, "", line);
    }
  '
  # fallback: simpler parse below
  nvidia-smi -i 7 2>/dev/null | grep "20096MiB" | awk -v k="$1" 'NR==k+1 {gsub(/[A-Za| ]/,""); print $1}'
}

gpu_free_whole() {
  local u t
  u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i "$1" | tr -d " ")
  t=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i "$1" | tr -d " ")
  echo $(( t - u ))
}

LAST_FREE=""
i=0
while [ $i -lt 1152 ]; do  # 1152 * 300s = 4 days
  if converged $OUT/p3_v3_355m && converged $OUT/p3_v3_56m; then
    echo "$(date) both converged — watchdog exits" >> "$LOG"
    break
  fi
  # 56M control (~6GB): GPU7 MIG_B if instance has >=13GB free
  if ! converged $OUT/p3_v3_56m && ! alive 768; then
    migB_used=$(nvidia-smi -i 7 2>/dev/null | grep "20096MiB" | awk "NR==2" | grep -oE "[0-9]+MiB / 20096" | grep -oE "^[0-9]+")
    [ -z "$migB_used" ] && migB_used=99999
    if [ "$migB_used" -le 12000 ]; then
      launch $MIG_B 768 8 12 p3_v3_56m 24000 1
    else
      # whole-card fallback: any card with >=12GB free (single-poll, batch 8000)
      for gi in 1 3 5 0 2 4; do
        ff=$(gpu_free_whole $gi)
        if [ "$ff" -ge 12000 ]; then
          launch $gi 768 8 12 p3_v3_56m 8000 3
          break
        fi
      done
    fi
  fi
  # 355M main (~13GB at batch 20000/accum 3)
  if ! converged $OUT/p3_v3_355m && ! alive 1280; then
    migA_used=$(nvidia-smi -i 7 2>/dev/null | grep "20096MiB" | awk "NR==1" | grep -oE "[0-9]+MiB / 20096" | grep -oE "^[0-9]+")
    [ -z "$migA_used" ] && migA_used=99999
    if [ "$migA_used" -le 6000 ]; then
      launch $MIG_A 1280 12 16 p3_v3_355m 24000 1
    else
      for gi in 0 1 2 3 4 5; do
        ff=$(gpu_free_whole $gi)
        if [ "$ff" -ge 23000 ]; then
          launch $gi 1280 12 16 p3_v3_355m 20000 3
          break
        fi
      done
    fi
  fi
  i=$((i + 1))
  sleep 300
done
echo "$(date) watchdog v4 final exit" >> "$LOG"
