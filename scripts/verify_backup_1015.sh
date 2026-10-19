#!/bin/bash
# 2026-10-15 复现性审计收尾：等待 4 路大文件 .gz 传完 → gunzip-md5 往返校验 → 落盘日志
DEST='/Volumes/orico-disc/A100 大度盘'
DEST='/Volumes/orico-disc/A100 大量项目文件备份/CodonFlow-backup-20261013'
LOG=/tmp/verify_backup_1015.log
: > "$LOG"

declare -a FILES=(
  "corpora/splits_v3/train.fasta.gz:176273697:1696f0273b8c3f97acebe78393ad0e98:d86366a03a613f4d104cb3ad0dd2adb1:train.fasta"
  "corpora/v3_cluster/cluster_all_seqs.fasta.gz:223833465:e7d145310765f0a7f00cf7355f66f789:76aad50e0b8d9d450bab33bd6df472c5:cluster_all_seqs.fasta"
  "corpora/v3_cluster/cluster_rep_seq.fasta.gz:130129324:4d46fa8e37ac780181bfb1f7fea43835:05a0c3c5b1dacecdbcfa0f54ca236e53:cluster_rep_seq.fasta"
  "corpora/v3_all.fasta.gz:240545696:46ee820976366565fe6b57672e7be2c6:v3_all_md5_unknown:v3_all.fasta"
)

echo "[$(date +%T)] 开始轮询传输完成..." | tee -a "$LOG"
for round in $(seq 1 60); do
  ALL_DONE=1
  for e in "${FILES[@]}"; do
    IFS=':' read -r rel gzsize gzmd5 origmd5 name <<< "$e"
    F="$DEST/$rel"
    if [ ! -f "$F" ] || [ "$(stat -f%z "$F" 2>/dev/null)" != "$gzsize" ]; then ALL_DONE=0; fi
  done
  [ "$ALL_DONE" = "1" ] && break
  sleep 60
done
echo "[$(date +%T)] 传输等待结束（round=$round）" | tee -a "$LOG"

# v3_all 原始 md5 远程补取
V3ALL_REMOTE=$(ssh A100 'md5sum /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/v3_all.fasta' 2>/dev/null | awk '{print $1}')
echo "v3_all remote md5: $V3ALL_REMOTE" >> "$LOG"

PASS=0; FAIL=0
for e in "${FILES[@]}"; do
  IFS=':' read -r rel gzsize gzmd5 origmd5 name <<< "$e"
  F="$DEST/$rel"
  [ "$origmd5" = "v3_all_md5_unknown" ] && origmd5="$V3ALL_REMOTE"
  if [ ! -f "$F" ]; then echo "MISSING: $rel" | tee -a "$LOG"; FAIL=$((FAIL+1)); continue; fi
  L=$(md5 -q "$F"); S=$(stat -f%z "$F")
  GUNZIP_MD5=$(gunzip -c "$F" 2>/dev/null | md5 -q)
  if [ "$L" = "$gzmd5" ] && [ "$S" = "$gzsize" ]; then
    if [ "$GUNZIP_MD5" = "$origmd5" ]; then
      echo "PASS: $rel (gz-md5=$L, 解压 md5=$GUNZIP_MD5 == 集群原始)" | tee -a "$LOG"; PASS=$((PASS+1))
    else
      echo "GZ-OK-BUT-CONTENT-FAIL: $rel (gz ok=$L, 解压=$GUNZIP_MD5 vs 期望 $origmd5)" | tee -a "$LOG"; FAIL=$((FAIL+1))
    fi
  else
    echo "GZ-FAIL: $rel (local=$L/$S vs 期望 $gzmd5/$gzsize)" | tee -a "$LOG"; FAIL=$((FAIL+1))
  fi
done
echo "===校验汇总: PASS=$PASS FAIL=$FAIL ===" | tee -a "$LOG"
[ "$FAIL" = "0" ] && echo "ALL_VERIFIED" >> "$LOG" || echo "HAS_FAILURES" >> "$LOG"
