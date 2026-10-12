#!/bin/bash
# v3 pipeline v2 (fixes): mmseqs absolute path; include wave1+wave2 species;
# correct failed-species versions (ciona_savignyi CSAV2.0, anolis AnoCar2.0v2).
set -u
PY=/home/cunyuliu/miniconda3/envs/codonflow/bin/python
MMSEQS=/home/cunyuliu/miniconda3/envs/codonflow/bin/mmseqs
C=/mnt/cunyuliu/codonflow/corpora
LOG="$C/v3_pipeline2.log"
echo "=== v3 pipeline2 start $(date) ===" > "$LOG"

# 0) fetch the 2 corrected-species downloads
declare -A FIX=(
  [ciona_savignyi]="Ciona_savignyi.CSAV2.0"
  [anolis_carolinensis]="Anolis_carolinensis.AnoCar2.0v2"
)
for sp in "${!FIX[@]}"; do
  base="${FIX[$sp]}"
  fa="$C/${sp}_cds.fa"
  [ -s "$fa" ] && grep -q ">" "$fa" && continue
  url="https://ftp.ensembl.org/pub/release-112/fasta/${sp}/cds/${base}.cds.all.fa.gz"
  curl -s --max-time 900 -o "$C/${sp}_cds.fa.gz" "$url" && gunzip -kf "$C/${sp}_cds.fa.gz"
  echo "FETCH-FIX ${sp}: $(grep -c '>' "$fa" 2>/dev/null || echo 0)" >> "$LOG"
done

ALL_SPECIES=(
  rattus_norvegicus pan_troglodytes canis_lupus_familiaris gallus_gallus
  macaca_mulatta bos_taurus sus_scrofa xenopus_tropicalis gorilla_gorilla
  oryzias_latipes saccharomyces_cerevisiae
  felis_catus oryctolagus_cuniculus cavia_porcellus ovis_aries equus_caballus
  takifugu_rubripes ciona_intestinalis ciona_savignyi anolis_carolinensis
)

# 1) clean all species not yet cleaned
for sp in "${ALL_SPECIES[@]}"; do
  fa="$C/${sp}_cds.fa"
  out="$C/${sp}_cds_cleaned.fasta"
  [ -s "$fa" ] || { echo "MISSING raw $sp" >> "$LOG"; continue; }
  [ -s "$out" ] && continue
  n=$($PY -c "
import sys; sys.path.insert(0, '/home/cunyuliu/codonflow/src')
from codonflow.data.pipeline import clean_fasta
c = clean_fasta('$fa', '$out')
print(c['kept'])
" 2>>"$LOG")
  echo "CLEANED $sp: $n kept" >> "$LOG"
done

# 2) merge everything (v2 base 5 + 20 new species)
MERGED="$C/v3_all.fasta"
cat "$C"/gencode_v47_cds_cleaned.fasta \
    "$C"/mus_musculus_cds_cleaned.fasta \
    "$C"/drosophila_melanogaster_cds_cleaned.fasta \
    "$C"/danio_rerio_cds_cleaned.fasta \
    "$C"/caenorhabditis_elegans_cds_cleaned.fasta \
    $(for sp in "${ALL_SPECIES[@]}"; do [ -s "$C/${sp}_cds_cleaned.fasta" ] && echo "$C/${sp}_cds_cleaned.fasta"; done) \
    > "$MERGED"
TOTAL=$(grep -c ">" "$MERGED")
echo "MERGED total: $TOTAL" >> "$LOG"

# 3) cluster with absolute-path mmseqs (0.8 id, 90 threads)
CLUSTER_DIR="$C/v3_cluster"
TSV="$CLUSTER_DIR/cluster.tsv"
if [ ! -s "$TSV" ]; then
  mkdir -p "$CLUSTER_DIR"
  "$MMSEQS" easy-cluster "$MERGED" "$CLUSTER_DIR/cluster" "$CLUSTER_DIR/tmp" \
    --min-seq-id 0.8 -c 0.8 --threads 90 >> "$LOG" 2>&1
fi
if [ -s "$TSV" ]; then
  NCLUST=$(cut -f1 "$TSV" | sort -u | wc -l)
  echo "CLUSTERS: $NCLUST" >> "$LOG"
else
  echo "CLUSTER FAILED" >> "$LOG"
  tail -20 "$LOG"
  exit 1
fi

# 4) rebuild splits
SPLIT_DIR="$C/splits_v3"
if [ ! -s "$SPLIT_DIR/train.fasta" ]; then
  $PY /home/cunyuliu/codonflow/scripts/build_splits.py \
    --cleaned "$MERGED" --cluster-tsv "$TSV" --out-dir "$SPLIT_DIR" >> "$LOG" 2>&1
fi
for f in train val test; do
  n=$(grep -c ">" "$SPLIT_DIR/$f.fasta" 2>/dev/null || echo 0)
  echo "SPLIT $f: $n" >> "$LOG"
done
echo "=== v3 pipeline2 done $(date) ===" >> "$LOG"
tail -30 "$LOG"
