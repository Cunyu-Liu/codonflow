#!/bin/bash
# Heldout-18 benchmark: 18 held-out genes x full method suite (E5 protocol,
# 1 seed x 50 sols, steps=10, ATC-fixed code). Splits genes across 6 GPU6
# MIG chains. Output: eval_outputs/HELD18_<gene>.json (one file per gene).
set -u
PY=/root/miniconda3/envs/codonflow/bin/python
CKPT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints/p2_pretrain_v2_corrupt/converged.pt
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs
LOG=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/logs
FASTA=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/bench_heldout18.fasta
cd /home/codonflow
mkdir -p "$OUT" "$LOG"

# per-gene fasta extraction (header carries |species|bin|len meta)
ensure_per_gene() {
  if [ ! -d /tmp/held18 ]; then
    mkdir -p /tmp/held18
    /root/miniconda3/envs/codonflow/bin/python - <<PYEOF
import os
from pathlib import Path
os.makedirs("/tmp/held18", exist_ok=True)
recs = []
h, chunks = None, []
for line in open("/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/bench_heldout18.fasta"):
    line = line.strip()
    if not line:
        continue
    if line.startswith(">"):
        if h is not None:
            recs.append((h, "".join(chunks)))
        h, chunks = line[1:], []
    else:
        chunks.append(line)
recs.append((h, "".join(chunks)))
for i, (h, s) in enumerate(recs):
    gid = h.split("|")[0].replace(".", "_")
    Path(f"/tmp/held18/g{i:02d}_{gid}.fasta").write_text(f">{h}\n{s}\n")
print("per-gene fastas:", len(recs))
PYEOF
  fi
}

run_gene() {
  local fa=$1 tag=$2 mig=$3
  if [ -f "$OUT/HELD18_${tag}.json" ]; then
    return 0
  fi
  echo "=== HELD18 ${tag} $(date) ===" > "$LOG/held18_${tag}.log"
  CUDA_VISIBLE_DEVICES=$mig MFE_PROCS=12 PYTHONPATH=src "$PY" scripts/run_exp5_ood.py \
    --benchmark-fasta "$fa" --checkpoint "$CKPT" \
    --n-solutions 50 --seeds 0 --n-steps 10 \
    --out "$OUT/HELD18_${tag}.json" >> "$LOG/held18_${tag}.log" 2>&1
  echo "EXIT=$? at $(date)" >> "$LOG/held18_${tag}.log"
}

M0=MIG-27707c52-3cf5-55f8-858f-1419d97bbdf3
M1=MIG-69a32e2d-cdb9-54e2-bdde-3228e0195de7
M2=MIG-4c9214e6-acd9-5d8a-98a6-feb9c94236c8
M3=MIG-82791eab-f55e-5e73-a1da-a8eddc196cdf
M4=MIG-d2b486bc-d56f-58b3-af42-3850d1d80684
M5=MIG-121d5489-2cf9-5fb7-9309-ff6fe5ec112d
M6=MIG-e157a761-6823-5540-b865-d296b8443d38

chain() {
  ensure_per_gene
  case "$1" in
    c0) for i in 00 01 02 03; do f=$(ls /tmp/held18/g${i}_*.fasta); run_gene "$f" "$(basename $f .fasta)" $M0; done ;;
    c1) for i in 04 05 06 07; do f=$(ls /tmp/held18/g${i}_*.fasta); run_gene "$f" "$(basename $f .fasta)" $M1; done ;;
    c2) for i in 08 09 10 11; do f=$(ls /tmp/held18/g${i}_*.fasta); run_gene "$f" "$(basename $f .fasta)" $M2; done ;;
    c3) for i in 12 13; do f=$(ls /tmp/held18/g${i}_*.fasta); run_gene "$f" "$(basename $f .fasta)" $M3; done ;;
    c4) for i in 14 15; do f=$(ls /tmp/held18/g${i}_*.fasta); run_gene "$f" "$(basename $f .fasta)" $M4; done ;;
    c5) for i in 16 17; do f=$(ls /tmp/held18/g${i}_*.fasta); run_gene "$f" "$(basename $f .fasta)" $M5; done ;;
    *) echo unknown; exit 2 ;;
  esac
}

if [ $# -ge 1 ] && [ "$1" != "launch" ]; then
  chain "$1"
  exit 0
fi

ensure_per_gene
SELF=$(readlink -f "$0")
for c in c0 c1 c2 c3 c4 c5; do
  tmux new-session -d -s h18_${c} "bash $SELF $c"
done
echo "heldout18 launched at $(date)"
tmux ls | grep h18 | wc -l
