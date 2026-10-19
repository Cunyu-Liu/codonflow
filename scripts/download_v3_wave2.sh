#!/bin/bash
# v3 corpus wave 2: 12 more Ensembl r112 species (verified URLs 2026-10-12).
set -u
C=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora
mkdir -p "$C"
LOG="$C/v3_download_wave2.log"
echo "=== v3 wave2 download start $(date) ===" > "$LOG"

declare -A SP=(
  [felis_catus]="Felis_catus.Felis_catus_9.0"
  [oryctolagus_cuniculus]="Oryctolagus_cuniculus.OryCun2.0"
  [cavia_porcellus]="Cavia_porcellus.Cavpor3.0"
  [ovis_aries]="Ovis_aries.Oar_v3.1"
  [equus_caballus]="Equus_caballus.EquCab3.0"
  [anolis_carolinensis]="Anolis_carolinensis.AnoCar2.0"
  [takifugu_rubripes]="Takifugu_rubripes.fTakRub1.2"
  [ciona_intestinalis]="Ciona_intestinalis.KH"
  [ciona_savignyi]="Ciona_savignyi.CSA2.0"
  [strongylocentrotus_purpuratus]="Strongylocentrotus_purpuratus.Spur_5.0"
  [hymenolepis_microstoma]="Hymenolepis_microstoma.Hm2"
  [schistosoma_mansoni]="Schistosoma_mansoni.Smale7_v1"
)

total=0
for sp in "${!SP[@]}"; do
  base="${SP[$sp]}"
  url="https://ftp.ensembl.org/pub/release-112/fasta/${sp}/cds/${base}.cds.all.fa.gz"
  gz="$C/${sp}_cds.fa.gz"
  fa="$C/${sp}_cds.fa"
  if [ -s "$fa" ] && grep -q ">" "$fa"; then
    echo "SKIP ${sp}" >> "$LOG"
    continue
  fi
  echo "GET ${sp} ..." >> "$LOG"
  ok=0
  for attempt in 1 2 3; do
    curl -s --max-time 900 -o "$gz" "$url" && gzip -t "$gz" 2>/dev/null && ok=1 && break
    echo "  retry ${attempt}" >> "$LOG"
    sleep 15
  done
  if [ "$ok" = "1" ]; then
    gunzip -kf "$gz"
    n=$(grep -c ">" "$fa")
    total=$((total + n))
    echo "OK ${sp}: ${n} seqs" >> "$LOG"
  else
    echo "FAIL ${sp}: ${url}" >> "$LOG"
  fi
done
echo "=== wave2 done $(date): total ${total} ===" >> "$LOG"
cat "$LOG"
