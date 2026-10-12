#!/bin/bash
# GPT10x batch: remaining 13 gene x seed arms on 5 GPU6 MIG instances.
set -u
PY=/home/cunyuliu/miniconda3/envs/codonflow/bin/python
cd /home/cunyuliu/codonflow
export PYTHONPATH=src:/home/cunyuliu/codonflow/scripts

run() {
  local gene=$1 seed=$2 mig=$3
  if [ -f /mnt/cunyuliu/codonflow/eval_outputs/GPT10x_${gene}_s${seed}.json ]; then
    return 0
  fi
  echo "=== GPT10x ${gene}_s${seed} $(date) ===" > /mnt/cunyuliu/codonflow/logs/gpt10x_${gene}_s${seed}.log
  CUDA_VISIBLE_DEVICES=$mig $PY scripts/run_gpt10x.py "$gene" "$seed" \
    >> /mnt/cunyuliu/codonflow/logs/gpt10x_${gene}_s${seed}.log 2>&1
  echo "EXIT=$?" >> /mnt/cunyuliu/codonflow/logs/gpt10x_${gene}_s${seed}.log
}

M0=MIG-27707c52-3cf5-55f8-858f-1419d97bbdf3
M1=MIG-69a32e2d-cdb9-54e2-bdde-3228e0195de7
M2=MIG-4c9214e6-acd9-5d8a-98a6-feb9c94236c8
M3=MIG-82791eab-f55e-5e73-a1da-a8eddc196cdf
M4=MIG-d2b486bc-d56f-58b3-af42-3850d1d80684

case "${1:-launch}" in
  c0) run egfp 1 $M0; run zfish 0 $M0; run zfish 1 $M0 ;;
  c1) run egfp 2 $M1; run zfish 2 $M1 ;;
  c2) run nluc 1 $M2; run fly 0 $M2 ;;
  c3) run nluc 2 $M3; run fly 1 $M3; run fly 2 $M3 ;;
  c4) run mouse 0 $M4; run mouse 1 $M4; run mouse 2 $M4 ;;
  *)
    SELF=$(readlink -f "$0")
    tmux new-session -d -s g10x_c0 "bash $SELF c0"
    tmux new-session -d -s g10x_c1 "bash $SELF c1"
    tmux new-session -d -s g10x_c2 "bash $SELF c2"
    tmux new-session -d -s g10x_c3 "bash $SELF c3"
    tmux new-session -d -s g10x_c4 "bash $SELF c4"
    echo "launched at $(date)"
    tmux ls | grep g10x | wc -l
    ;;
esac
