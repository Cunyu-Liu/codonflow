#!/bin/bash
# HELD18 for v3 converged checkpoints (56M now; 355M after convergence).
# Single-GPU serial chain sharing the 4090 with 355M training (GPU forward ~3-4GB).
# Output tag: HELD18_V3<MODEL>_<gene>.json
set -u
PY=/root/miniconda3/envs/codonflow/bin/python
MODEL=${1:-56m}
case $MODEL in
  56m)  CKPT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints/p3_v3_56m/converged.pt; TAG=V356m ;;
  355m) CKPT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints/p3_v3_355m/converged.pt; TAG=V3355m ;;
  *) echo "usage: $0 [56m|355m]"; exit 2 ;;
esac
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs
LOG=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/logs
cd /home/codonflow
mkdir -p "$OUT" "$LOG"

# per-gene fastas (same extraction as run_held18.sh)
if [ ! -d /tmp/held18 ]; then
  mkdir -p /tmp/held18
  "$PY" - <<PYEOF
import os
from pathlib import Path
recs = []
h, chunks = None, []
for line in open("/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/bench_heldout18.fasta"):
    line = line.strip()
    if not line: continue
    if line.startswith(">"):
        if h is not None: recs.append((h, "".join(chunks)))
        h, chunks = line[1:], []
    else: chunks.append(line)
recs.append((h, "".join(chunks)))
for i, (h, s) in enumerate(recs):
    gid = h.split("|")[0].replace(".", "_")
    Path(f"/tmp/held18/g{i:02d}_{gid}.fasta").write_text(f">{h}\n{s}\n")
print("per-gene fastas:", len(recs))
PYEOF
fi

for i in $(seq -f "%02g" 0 17); do
  f=$(ls /tmp/held18/g${i}_*.fasta 2>/dev/null | head -1)
  [ -z "$f" ] && continue
  tag=$(basename "$f" .fasta)
  if [ -f "$OUT/HELD18_${TAG}_${tag}.json" ]; then continue; fi
  echo "=== HELD18 ${TAG} ${tag} $(date) ===" > "$LOG/held18_${TAG}_${tag}.log"
  CUDA_VISIBLE_DEVICES=0 MFE_PROCS=10 PYTHONPATH=src "$PY" scripts/run_exp5_ood.py \
    --benchmark-fasta "$f" --checkpoint "$CKPT" \
    --n-solutions 50 --seeds 0 --n-steps 10 \
    --out "$OUT/HELD18_${TAG}_${tag}.json" >> "$LOG/held18_${TAG}_${tag}.log" 2>&1
  echo "EXIT=$? at $(date)" >> "$LOG/held18_${TAG}_${tag}.log"
done
echo "HELD18 ${TAG} chain complete $(date)"
