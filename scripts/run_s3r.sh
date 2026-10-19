#!/bin/bash
# S3 evaluator-domain rerun: cas9 x3 + fly x3 + yeast(g08) with obj_vectors
# storage for offline per-gene adaptive HV recomputation. GPU6 MIGs.
set -u
PY=/root/miniconda3/envs/codonflow/bin/python
CKPT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints/p2_pretrain_v2_corrupt/converged.pt
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs
LOG=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/logs
cd /home/codonflow

ensure() {
  [ -s /tmp/gene_fly.fasta ] || awk -v pat="FBtr0307879" 'index($0,">") && index($0,pat) {p=1; print; next} p && index($0,">") {p=0} p {print}' /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/ood3.fasta > /tmp/gene_fly.fasta
  [ -s /tmp/gene_yeast.fasta ] || /root/miniconda3/envs/codonflow/bin/python - <<'PYEOF'
from pathlib import Path
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
for h, s in recs:
    if "yeast" in h:
        Path("/tmp/gene_yeast.fasta").write_text(f">{h}\n{s}\n")
        print("yeast gene:", h, len(s))
PYEOF
}

run5() {  # tag fasta seed mig steps nsol extra
  local tag=$1 fasta=$2 seed=$3 mig=$4 steps=$5 nsol=$6 extra=$7
  if [ -f "$OUT/S3R_${tag}_s${seed}.json" ]; then
    return 0
  fi
  echo "=== S3R $tag s$seed $(date) ===" > "$LOG/s3r_${tag}_s${seed}.log"
  CUDA_VISIBLE_DEVICES=$mig MFE_PROCS=8 PYTHONPATH=src $PY scripts/run_exp5_ood.py \
    --benchmark-fasta "$fasta" --checkpoint "$CKPT" \
    --n-solutions "$nsol" --seeds "$seed" --n-steps "$steps" $extra \
    --out "$OUT/S3R_${tag}_s${seed}.json" >> "$LOG/s3r_${tag}_s${seed}.log" 2>&1
  echo "EXIT=$? at $(date)" >> "$LOG/s3r_${tag}_s${seed}.log"
}

M0=MIG-27707c52-3cf5-55f8-858f-1419d97bbdf3
M1=MIG-69a32e2d-cdb9-54e2-bdde-3228e0195de7
M2=MIG-4c9214e6-acd9-5d8a-98a6-feb9c94236c8
M3=MIG-82791eab-f55e-5e73-a1da-a8eddc196cdf
M5=MIG-121d5489-2cf9-5fb7-9309-ff6fe5ec112d

case "${1:-launch}" in
  c0) ensure
      run5 fly /tmp/gene_fly.fasta 0 $M0 10 100 ""
      run5 yeast /tmp/gene_yeast.fasta 0 $M0 10 50 "" ;;
  c1) ensure
      run5 fly /tmp/gene_fly.fasta 1 $M1 10 100 ""
      run5 fly /tmp/gene_fly.fasta 2 $M1 10 100 "" ;;
  c2) run5 cas9 /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/cas9_probe.fasta 0 $M2 5 20 "--n-candidates 5" ;;
  c3) run5 cas9 /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/cas9_probe.fasta 1 $M3 5 20 "--n-candidates 5" ;;
  c4) run5 cas9 /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/cas9_probe.fasta 2 $M5 5 20 "--n-candidates 5" ;;
  *)
    SELF=$(readlink -f "$0")
    for c in c0 c1 c2 c3 c4; do
      tmux new-session -d -s s3r_${c} "bash $SELF $c"
    done
    echo "launched $(date)"
    tmux ls | grep -c s3r
    ;;
esac
