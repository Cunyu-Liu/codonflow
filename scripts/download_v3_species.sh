#!/bin/bash
# v3 corpus expansion (Task 1.1 v3): download 11 Ensembl r112 species CDS.
# Same source/format as v2 aux species. URLs verified 2026-10-12 (HTTP 200/HEAD).
# Output: /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/<species>_cds.fa.gz + .fa
set -u
C=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora
mkdir -p "$C"
LOG="$C/v3_download.log"
echo "=== v3 corpus download start $(date) ===" > "$LOG"

declare -A SP=(
  [rattus_norvegicus]="Rattus_norvegicus.mRatBN7.2"
  [pan_troglodytes]="Pan_troglodytes.Pan_tro_3.0"
  [canis_lupus_familiaris]="Canis_lupus_familiaris.ROS_Cfam_1.0"
  [gallus_gallus]="Gallus_gallus.bGalGal1.mat.broiler.GRCg7b"
  [macaca_mulatta]="Macaca_mulatta.Mmul_10"
  [bos_taurus]="Bos_taurus.ARS-UCD1.3"
  [sus_scrofa]="Sus_scrofa.Sscrofa11.1"
  [xenopus_tropicalis]="Xenopus_tropicalis.UCB_Xtro_10.0"
  [gorilla_gorilla]="Gorilla_gorilla.gorGor4"
  [oryzias_latipes]="Oryzias_latipes.ASM223467v1"
  [saccharomyces_cerevisiae]="Saccharomyces_cerevisiae.R64-1-1"
)

total=0
for sp in "${!SP[@]}"; do
  base="${SP[$sp]}"
  url="https://ftp.ensembl.org/pub/release-112/fasta/${sp}/cds/${base}.cds.all.fa.gz"
  gz="$C/${sp}_cds.fa.gz"
  fa="$C/${sp}_cds.fa"
  if [ -s "$fa" ] && grep -q ">" "$fa"; then
    echo "SKIP ${sp} (exists, $(grep -c '>' "$fa") seqs)" >> "$LOG"
    continue
  fi
  echo "GET ${sp} ..." >> "$LOG"
  for attempt in 1 2 3; do
    curl -s --max-time 900 -o "$gz" "$url" && gzip -t "$gz" 2>/dev/null && break
    echo "  retry ${attempt} failed" >> "$LOG"
    sleep 15
  done
  if gzip -t "$gz" 2>/dev/null; then
    gunzip -kf "$gz"
    n=$(grep -c ">" "$fa")
    total=$((total + n))
    echo "OK ${sp}: ${n} seqs ($(du -h "$fa" | cut -f1))" >> "$LOG"
  else
    echo "FAIL ${sp}: $url" >> "$LOG"
  fi
done
echo "=== done $(date): new seqs total ${total} ===" >> "$LOG"
cat "$LOG"
