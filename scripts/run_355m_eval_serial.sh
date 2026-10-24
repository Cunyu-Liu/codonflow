#!/bin/bash
# 355M 全量评测（converged 后）：单卡 5090 串行链。
# 原 run_v3_eval.sh launch 模式开 5 条并行 tmux（适合多 MIG），单卡改为串行。
# 链内容（与原 c0-c4 相同的 arm 集合）：
#   c3: egfp s0/s1/s2, nluc s0/s1/s2, zfish s0/s1/s2（轻臂，~30min each）
#   c0: mouse s0, fly s0, egfp s1（mouse 是 9h 级长臂）
#   c1: mouse s1, fly s1, egfp s2
#   c2: mouse s2, fly s2, nluc s0
#   c4: E3 scan egfp + nluc
# 单卡跑法：先 c3（全轻臂，出主表大半）→ c4（E3 扫描）→ c0/c1/c2（mouse 长尾）。
# 幂等：输出 JSON 已存在且非空则跳过（复用 run_arm 逻辑重写，与 run_v3_eval_rloo.sh 一致）。
set -u
PY=/root/miniconda3/envs/codonflow/bin/python
CKPT_DIR=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints/p3_v3_355m
TAG=v3_355m
CKPT=$CKPT_DIR/converged.pt
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs
LOG=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/logs
cd /home/codonflow
mkdir -p "$OUT" "$LOG"
[ -f "$CKPT" ] || { echo "no converged.pt in $CKPT_DIR"; exit 2; }

ensure_fastas() {
  [ -s /tmp/gene_mouse.fasta ] && return 0
  awk -v pat="ENSMUST00000202556.4" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/ood3.fasta > /tmp/gene_mouse.fasta
  awk -v pat="FBtr0307879"          'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/ood3.fasta > /tmp/gene_fly.fasta
  awk -v pat="ENSDART00000133583.2" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/ood3.fasta > /tmp/gene_zfish.fasta
  awk -v pat="egfp" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/bench_egfp.fasta > /tmp/gene_egfp.fasta
  awk -v pat="nluc" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/bench_nluc.fasta > /tmp/gene_nluc.fasta
}

run_arm() {
  local gene=$1 seed=$2
  local steps=10
  case $gene in egfp|nluc) steps=20 ;; esac
  local outjson="$OUT/E5_${TAG}_${gene}_s${seed}.json"
  if [ -s "$outjson" ]; then echo "SKIP existing $outjson"; return 0; fi
  echo "=== arm ${gene}_s${seed}_${TAG} steps=$steps $(date) ===" > "$LOG/e5o_${gene}_s${seed}_${TAG}.log"
  CUDA_VISIBLE_DEVICES=0 MFE_PROCS=12 PYTHONPATH=src "$PY" scripts/run_exp5_ood.py \
    --benchmark-fasta /tmp/gene_${gene}.fasta --checkpoint "$CKPT" \
    --n-solutions 100 --seeds "$seed" --n-steps "$steps" \
    --out "$outjson" >> "$LOG/e5o_${gene}_s${seed}_${TAG}.log" 2>&1
  echo "EXIT=$? at $(date)" >> "$LOG/e5o_${gene}_s${seed}_${TAG}.log"
}

run_e3() {
  local gene=$1
  local outjson="$OUT/E3_${TAG}_${gene}.json"
  if [ -s "$outjson" ]; then echo "SKIP existing $outjson"; return 0; fi
  echo "=== e3_${TAG}_${gene} $(date) ===" > "$LOG/e3_${TAG}_${gene}.log"
  CUDA_VISIBLE_DEVICES=0 MFE_PROCS=12 PYTHONPATH=src "$PY" scripts/run_exp3.py \
    --benchmark-fasta /tmp/gene_${gene}.fasta --checkpoint "$CKPT" \
    --n-solutions 30 --n-steps 20 \
    --out "$outjson" >> "$LOG/e3_${TAG}_${gene}.log" 2>&1
  echo "EXIT=$? at $(date)" >> "$LOG/e3_${TAG}_${gene}.log"
}

chain() {
  ensure_fastas
  case "$1" in
    c3) run_arm egfp 0; run_arm egfp 1; run_arm egfp 2; run_arm nluc 0; run_arm nluc 1; run_arm nluc 2; run_arm zfish 0; run_arm zfish 1; run_arm zfish 2 ;;
    c4) run_e3 egfp; run_e3 nluc ;;
    c0) run_arm mouse 0; run_arm fly 0; run_arm egfp 1 ;;
    c1) run_arm mouse 1; run_arm fly 1; run_arm egfp 2 ;;
    c2) run_arm mouse 2; run_arm fly 2; run_arm nluc 0 ;;
    *) echo "unknown chain"; exit 2 ;;
  esac
}

if [ $# -ge 1 ]; then
  chain "$1"
  exit 0
fi
chain c3
