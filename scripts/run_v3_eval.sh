#!/bin/bash
# v3 evaluation launcher: run after v3 pretrain converges.
# Usage: run_v3_eval.sh <ckpt_dir> <tag>   e.g. run_v3_eval.sh p3_v3_355m v3_355m
# Re-runs the protocol-fair E5 (5 genes x 3 seeds, steps parity) + E3 scan
# with the SAME code (ATC fix) and SAME protocol as the 10-12 rerun, so the
# only variable vs E5_fix_* is the base checkpoint (capacity curve point).
set -u
PY=/root/miniconda3/envs/codonflow/bin/python
CKPT_DIR=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints/$1
TAG=$2
CKPT=$CKPT_DIR/converged.pt
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs
LOG=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/logs
cd /home/codonflow
mkdir -p "$OUT" "$LOG"
[ -f "$CKPT" ] || { echo "no converged.pt in $CKPT_DIR"; exit 2; }

MIG0=0
MIG1=0
MIG2=0
MIG3=0
MIG4=0

ensure_fastas() {
  [ -s /tmp/gene_mouse.fasta ] && return 0
  awk -v pat="ENSMUST00000202556.4" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/ood3.fasta > /tmp/gene_mouse.fasta
  awk -v pat="FBtr0307879"          'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/ood3.fasta > /tmp/gene_fly.fasta
  awk -v pat="ENSDART00000133583.2" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/ood3.fasta > /tmp/gene_zfish.fasta
  awk -v pat="egfp" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/bench_egfp.fasta > /tmp/gene_egfp.fasta
  awk -v pat="nluc" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/bench_nluc.fasta > /tmp/gene_nluc.fasta
}

run_arm() {
  local gene=$1 seed=$2 mig=$3 procs=$4
  local steps=10
  case $gene in egfp|nluc) steps=20 ;; esac
  echo "=== arm ${gene}_s${seed}_${TAG} steps=$steps $(date) ===" > "$LOG/e5o_${gene}_s${seed}_${TAG}.log"
  CUDA_VISIBLE_DEVICES=$mig MFE_PROCS=$procs PYTHONPATH=src "$PY" scripts/run_exp5_ood.py \
    --benchmark-fasta /tmp/gene_${gene}.fasta --checkpoint "$CKPT" \
    --n-solutions 100 --seeds "$seed" --n-steps "$steps" \
    --out "$OUT/E5_${TAG}_${gene}_s${seed}.json" >> "$LOG/e5o_${gene}_s${seed}_${TAG}.log" 2>&1
  echo "EXIT=$? at $(date)" >> "$LOG/e5o_${gene}_s${seed}_${TAG}.log"
}

run_e3() {
  local gene=$1 mig=$2
  echo "=== e3_${TAG}_${gene} $(date) ===" > "$LOG/e3_${TAG}_${gene}.log"
  CUDA_VISIBLE_DEVICES=$mig MFE_PROCS=16 PYTHONPATH=src "$PY" scripts/run_exp3.py \
    --benchmark-fasta /tmp/gene_${gene}.fasta --checkpoint "$CKPT" \
    --n-solutions 30 --n-steps 20 \
    --out "$OUT/E3_${TAG}_${gene}.json" >> "$LOG/e3_${TAG}_${gene}.log" 2>&1
  echo "EXIT=$? at $(date)" >> "$LOG/e3_${TAG}_${gene}.log"
}

chain() {
  ensure_fastas
  case "$1" in
    c0) run_arm mouse 0 $MIG0 20; run_arm fly 0 $MIG0 16; run_arm egfp 1 $MIG0 16 ;;
    c1) run_arm mouse 1 $MIG1 20; run_arm fly 1 $MIG1 16; run_arm egfp 2 $MIG1 16 ;;
    c2) run_arm mouse 2 $MIG2 20; run_arm fly 2 $MIG2 16; run_arm nluc 0 $MIG2 16 ;;
    c3) run_arm egfp 0 $MIG3 16; run_arm nluc 1 $MIG3 16; run_arm nluc 2 $MIG3 16; run_arm zfish 0 $MIG3 16; run_arm zfish 1 $MIG3 16; run_arm zfish 2 $MIG3 16 ;;
    c4) run_e3 egfp $MIG4; run_e3 nluc $MIG4 ;;
    *) echo "unknown chain"; exit 2 ;;
  esac
}

if [ $# -ge 3 ] && [ "$3" != "launch" ]; then
  chain "$3"
  exit 0
fi

ensure_fastas
SELF=$(readlink -f "$0")
for c in c0 c1 c2 c3 c4; do
  tmux new-session -d -s v3ev_${TAG}_${c} "bash $SELF $1 $2 $c"
done
echo "launched evaluation chains for $TAG at $(date)"
tmux ls | grep "v3ev_${TAG}" | wc -l
