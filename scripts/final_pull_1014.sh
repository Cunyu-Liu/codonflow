#!/bin/bash
# Final-pull for 2026-10-14 night: 56M (latest last.pt + log.jsonl + train.log tail) + 355M same.
# Run AFTER trainings finish (natural end or hardstop). Then sync to orico.
set -u
L="/Users/liucunyu/Documents/课题idea 数据 结论/浙江大学/RNA 相关模型/CodonFlow-密码子级离散流mRNA编辑器/backup_20261013/v3_final"
O="/Volumes/orico-disc/A100 大量项目文件备份/CodonFlow-backup-20261013/v3_final"

for m in v3_56m v3_355m; do
  mkdir -p "$L/$m" "$O/$m"
  echo "=== pulling $m ==="
  scp -q "A100:/mnt/cunyuliu/codonflow/checkpoints/p3_$m/last.pt" "$L/$m/last.pt" || echo "WARN: $m last.pt pull failed"
  scp -q "A100:/mnt/cunyuliu/codonflow/checkpoints/p3_$m/log.jsonl" "$L/$m/log.jsonl" || true
  scp -q "A100:/mnt/cunyuliu/codonflow/checkpoints/p3_$m/train.log" "$L/$m/train.log" || true
  scp -q "A100:/mnt/cunyuliu/codonflow/checkpoints/p3_$m/converged.pt" "$L/$m/converged.pt" 2>/dev/null && echo "$m converged.pt pulled" || echo "$m not converged (no converged.pt)"
  scp -q "A100:/mnt/cunyuliu/codonflow/checkpoints/p3_$m/converged.json" "$L/$m/converged.json" 2>/dev/null || true
  cp "$L/$m/last.pt" "$O/$m/last.pt" 2>/dev/null || true
  cp "$L/$m/log.jsonl" "$O/$m/log.jsonl" 2>/dev/null || true
  cp "$L/$m/train.log" "$O/$m/train.log" 2>/dev/null || true
  [ -f "$L/$m/converged.pt" ] && cp "$L/$m/converged.pt" "$O/$m/converged.pt"
  [ -f "$L/$m/converged.json" ] && cp "$L/$m/converged.json" "$O/$m/converged.json"
done
echo "=== md5 verify ==="
for m in v3_56m v3_355m; do
  for f in last.pt log.jsonl converged.pt; do
    [ -f "$L/$m/$f" ] || continue
    a=$(md5 -q "$L/$m/$f"); b=$(md5 -q "$O/$m/$f" 2>/dev/null)
    [ "$a" = "$b" ] && echo "OK  $m/$f $a" || echo "MISMATCH $m/$f"
  done
done
echo "=== done $(date) ==="
