#!/bin/bash
# E5 OOD launcher: usage launch_e5ood.sh <mig_uuid> <fasta> <ckpt> <tag> <n_sol> <n_seeds> [extra args...]
set -u
MIG=$1; FASTA=$2; CKPT=$3; TAG=$4; NSOL=$5; NSEED=$6; shift 6
PY=/root/miniconda3/envs/codonflow/bin/python
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs/E5_ood_${TAG}.json
LOG=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/logs/e5_ood_${TAG}.log
cd /home/codonflow
mkdir -p /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/logs /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs
echo "=== launch $(date) MIG=$MIG TAG=$TAG ===" > $LOG
CUDA_VISIBLE_DEVICES=$MIG PYTHONPATH=src exec $PY scripts/run_exp5_ood.py \
  --benchmark-fasta $FASTA --checkpoint $CKPT \
  --n-solutions $NSOL --n-seeds $NSEED --out $OUT "$@" >> $LOG 2>&1
echo "EXIT=$?" >> $LOG
