#!/bin/bash
# EXP-4 seed sweep: enqueue (group, seed) RLOO jobs across free MIG slots.
# Each job ~10 min (ungated RLOO converges by plateau ~iter 111).
# Slots: rotate through GPU6 1g.5gb MIGs + reuse freed slots.

cd /home/cunyuliu/codonflow
PY=/home/cunyuliu/miniconda3/envs/codonflow/bin/python
LOGDIR=/mnt/cunyuliu/codonflow/logs
CKPTDIR=/mnt/cunyuliu/codonflow/checkpoints
BASE=/mnt/cunyuliu/codonflow/checkpoints/p2_pretrain_768d/converged.pt
MIGS=(
  MIG-69a32e2d-cdb9-54e2-bdde-3228e0195de7
  MIG-4c9214e6-acd9-5d8a-98a6-feb9c94236c8
  MIG-d2b486bc-d56f-58b3-af42-3850d1d80684
  MIG-121d5489-2cf9-5fb7-9309-ff6fe5ec112d
  MIG-e157a761-6823-5540-b865-d296b8443d38
  MIG-27707c52-3cf5-55f8-858f-1419d97bbdf3
)
CPUS=(0-15 16-31 32-47 48-63 64-79 80-95)

# (lambda, group-name, seed) — seed 1 and seed 2 rows
JOBS=(
  "0.5 v4s1_equal 1"
  "0.25 v4s1_lam025 1"
  "0.75 v4s1_lam075 1"
  "0.0 v4s1_direct 1"
  "0.5 v4s2_equal 2"
  "0.25 v4s2_lam025 2"
  "0.75 v4s2_lam075 2"
  "0.0 v4s2_direct 2"
)

i=0
for job in "${JOBS[@]}"; do
  set -- $job
  lam=$1; name=$2; seed=$3
  mig=${MIGS[$(( i % ${#MIGS[@]} ))]}
  cpu=${CPUS[$(( i % ${#CPUS[@]} ))]}
  out=$CKPTDIR/p3_${name}
  log=$LOGDIR/rloo_${name}.log
  echo "[$(date +%H:%M)] launching $name (lambda=$lam seed=$seed) on $mig cpu=$cpu"
  CUDA_VISIBLE_DEVICES=$mig PYTHONPATH=src taskset -c $cpu \
    $PY -u src/codonflow/train/rloo_finetune.py \
    --benchmark-fasta /mnt/cunyuliu/codonflow/corpora/bench.fasta \
    --checkpoint $BASE --out-dir $out --ungated-rollout \
    --lmbda $lam --seed $seed --max-iters 1000 --plateau-patience 15 \
    > $log 2>&1 &
  i=$((i+1))
  # stagger launches to avoid simultaneous sigma-calibration CPU spikes
  sleep 20
done
wait
echo "all seed jobs done at $(date)"
