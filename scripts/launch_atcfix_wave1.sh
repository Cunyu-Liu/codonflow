#!/bin/bash
# ATC-fix rerun wave 1 (2026-10-11). Subcommand pattern: tmux calls this script
# with a chain name; bare invocation launches all tmux chains.
#   bash launch_atcfix_wave1.sh            -> launch everything
#   bash launch_atcfix_wave1.sh c0         -> run chain c0 only (used by tmux)
# Pre-fix results preserved in eval_outputs/prefix_atc_bug/.
set -u
PY=/home/cunyuliu/miniconda3/envs/codonflow/bin/python
CKPT=/mnt/cunyuliu/codonflow/checkpoints/p2_pretrain_v2_corrupt/converged.pt
CKPT_V4=/mnt/cunyuliu/codonflow/checkpoints/p3_rloo_v4_ungated/converged.pt
OUT=/mnt/cunyuliu/codonflow/eval_outputs
LOG=/mnt/cunyuliu/codonflow/logs
SELF=$(readlink -f "$0")
cd /home/cunyuliu/codonflow
mkdir -p "$OUT" "$LOG"

MIG0=MIG-27707c52-3cf5-55f8-858f-1419d97bbdf3
MIG1=MIG-69a32e2d-cdb9-54e2-bdde-3228e0195de7
MIG2=MIG-4c9214e6-acd9-5d8a-98a6-feb9c94236c8
MIG3=MIG-82791eab-f55e-5e73-a1da-a8eddc196cdf
MIG4=MIG-d2b486bc-d56f-58b3-af42-3850d1d80684
MIG5=MIG-121d5489-2cf9-5fb7-9309-ff6fe5ec112d
MIG6=MIG-e157a761-6823-5540-b865-d296b8443d38
MIG7A=MIG-6e59f9af-2716-5bf2-ac6e-fb05ef744585
MIG7B=MIG-10b9b777-a776-56de-9f7c-efde6c584f71

ensure_fastas() {
  [ -s /tmp/gene_mouse.fasta ] && return 0
  awk -v pat="ENSMUST00000202556.4" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /mnt/cunyuliu/codonflow/corpora/ood3.fasta > /tmp/gene_mouse.fasta
  awk -v pat="FBtr0307879"          'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /mnt/cunyuliu/codonflow/corpora/ood3.fasta > /tmp/gene_fly.fasta
  awk -v pat="ENSDART00000133583.2" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /mnt/cunyuliu/codonflow/corpora/ood3.fasta > /tmp/gene_zfish.fasta
  awk -v pat="egfp" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /mnt/cunyuliu/codonflow/corpora/bench_egfp.fasta > /tmp/gene_egfp.fasta
  awk -v pat="nluc" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /mnt/cunyuliu/codonflow/corpora/bench_nluc.fasta > /tmp/gene_nluc.fasta
}

run_arm() {
  local gene=$1 seed=$2 mig=$3 procs=$4
  local fa=/tmp/gene_${gene}.fasta
  local tag=${gene}_s${seed}_fix
  # protocol parity with pre-fix runs: egfp/nluc steps=20 (E5' protocol),
  # mouse/fly/zfish steps=10 (ood3 protocol) — only ATC fix may differ.
  local steps=10
  case $gene in egfp|nluc) steps=20 ;; esac
  echo "=== arm ${tag} MIG=${mig} steps=${steps} start $(date) ===" > "$LOG/e5o_${tag}.log"
  CUDA_VISIBLE_DEVICES=$mig MFE_PROCS=$procs PYTHONPATH=src "$PY" scripts/run_exp5_ood.py \
    --benchmark-fasta "$fa" --checkpoint "$CKPT" \
    --n-solutions 100 --seeds "$seed" --n-steps "$steps" \
    --out "$OUT/E5_fix_${gene}_s${seed}.json" >> "$LOG/e5o_${tag}.log" 2>&1
  echo "EXIT=$? at $(date)" >> "$LOG/e5o_${tag}.log"
}

run_e3() {
  local gene=$1 mig=$2
  echo "=== e3_fix_${gene} MIG=${mig} start $(date) ===" > "$LOG/e3_fix_${gene}.log"
  CUDA_VISIBLE_DEVICES=$mig MFE_PROCS=16 PYTHONPATH=src "$PY" scripts/run_exp3.py \
    --benchmark-fasta /tmp/gene_${gene}.fasta --checkpoint "$CKPT_V4" \
    --n-solutions 30 --n-steps 20 \
    --out "$OUT/E3_fix_${gene}.json" >> "$LOG/e3_fix_${gene}.log" 2>&1
  echo "EXIT=$? at $(date)" >> "$LOG/e3_fix_${gene}.log"
}

run_cas9() {
  local seed=$1 mig=$2
  echo "=== cas9_fix_s${seed} MIG=${mig} start $(date) ===" > "$LOG/e5o_cas9_s${seed}_fix.log"
  CUDA_VISIBLE_DEVICES=$mig MFE_PROCS=20 PYTHONPATH=src "$PY" scripts/run_exp5_ood.py \
    --benchmark-fasta /mnt/cunyuliu/codonflow/corpora/cas9_probe.fasta --checkpoint "$CKPT" \
    --n-solutions 20 --seeds "$seed" --n-steps 5 --n-candidates 5 \
    --out "$OUT/E5_fix_cas9_s${seed}.json" >> "$LOG/e5o_cas9_s${seed}_fix.log" 2>&1
  echo "EXIT=$? at $(date)" >> "$LOG/e5o_cas9_s${seed}_fix.log"
}

chain() {
  ensure_fastas
  case "$1" in
    c0) run_arm mouse 0 $MIG0 20; run_arm fly 0 $MIG0 16; run_arm egfp 1 $MIG0 16 ;;
    c1) run_arm mouse 1 $MIG1 20; run_arm fly 1 $MIG1 16; run_arm egfp 2 $MIG1 16 ;;
    c2) run_arm mouse 2 $MIG2 20; run_arm fly 2 $MIG2 16; run_arm nluc 0 $MIG2 16 ;;
    c3) run_arm egfp 0 $MIG3 16; run_arm nluc 1 $MIG3 16; run_arm nluc 2 $MIG3 16; run_arm zfish 0 $MIG3 16; run_arm zfish 1 $MIG3 16; run_arm zfish 2 $MIG3 16 ;;
    c4) run_e3 egfp $MIG4; run_e3 nluc $MIG4 ;;
    c5) run_cas9 0 $MIG7A ;;
    c6) run_cas9 1 $MIG7B; run_cas9 2 $MIG7B ;;
    *) echo "unknown chain $1"; exit 2 ;;
  esac
}

if [ $# -ge 1 ] && [ "$1" != "launch" ]; then
  chain "$1"
  exit 0
fi

ensure_fastas
for f in mouse fly zfish egfp nluc; do
  n=$(grep -c ">" /tmp/gene_${f}.fasta)
  echo "gene_${f}: ${n} record(s)"
done
tmux new-session -d -s atx_c0 "bash $SELF c0"
tmux new-session -d -s atx_c1 "bash $SELF c1"
tmux new-session -d -s atx_c2 "bash $SELF c2"
tmux new-session -d -s atx_c3 "bash $SELF c3"
tmux new-session -d -s atx_c4 "bash $SELF c4"
tmux new-session -d -s atx_c5 "bash $SELF c5"
tmux new-session -d -s atx_c6 "bash $SELF c6"
echo "launched at $(date):"
tmux ls
