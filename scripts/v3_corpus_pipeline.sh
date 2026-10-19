#!/bin/bash
# v3 corpus pipeline: clean 11 new species -> merge with v2 corpus ->
# mmseqs2 re-cluster (0.8 id) -> cluster-disjoint splits (same builder).
# Runs after download_v3_species.sh. All rules identical to v2 (audit parity).
set -u
PY=/root/miniconda3/envs/codonflow/bin/python
C=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora
LOG="$C/v3_pipeline.log"
echo "=== v3 pipeline start $(date) ===" > "$LOG"

NEW_SPECIES=(
  rattus_norvegicus pan_troglodytes canis_lupus_familiaris gallus_gallus
  macaca_mulatta bos_taurus sus_scrofa xenopus_tropicalis gorilla_gorilla
  oryzias_latipes saccharomyces_cerevisiae
)

# 1) clean each new species (same clean_fasta as v2)
CLEANED=()
for sp in "${NEW_SPECIES[@]}"; do
  fa="$C/${sp}_cds.fa"
  out="$C/${sp}_cds_cleaned.fasta"
  if [ ! -s "$fa" ]; then
    echo "MISSING $fa — skipped" >> "$LOG"
    continue
  fi
  if [ -s "$out" ]; then
    echo "SKIP clean $sp" >> "$LOG"
  else
    n=$($PY -c "
import sys; sys.path.insert(0, '/home/codonflow/src')
from codonflow.data.pipeline import clean_fasta
c = clean_fasta('$fa', '$out')
print(c['kept'])
" 2>>"$LOG")
    echo "CLEANED $sp: $n kept" >> "$LOG"
  fi
  CLEANED+=("$out")
done
echo "cleaned files: ${#CLEANED[@]}" >> "$LOG"

# 2) merge with v2 cleaned corpus
MERGED="$C/v3_all.fasta"
if [ ! -s "$MERGED" ]; then
  cat "$C"/gencode_v47_cds_cleaned.fasta \
      "$C"/mus_musculus_cds_cleaned.fasta \
      "$C"/drosophila_melanogaster_cds_cleaned.fasta \
      "$C"/danio_rerio_cds_cleaned.fasta \
      "$C"/caenorhabditis_elegans_cds_cleaned.fasta \
      "${CLEANED[@]}" > "$MERGED"
fi
TOTAL=$(grep -c ">" "$MERGED")
echo "MERGED total: $TOTAL" >> "$LOG"

# 3) mmseqs2 re-cluster at 0.8 (same as v2)
CLUSTER_DIR="$C/v3_cluster"
TSV="$CLUSTER_DIR/cluster.tsv"
if [ ! -s "$TSV" ]; then
  mkdir -p "$CLUSTER_DIR"
  mmseqs easy-cluster "$MERGED" "$CLUSTER_DIR/cluster" "$CLUSTER_DIR/tmp.tsv" \
    --min-seq-id 0.8 -c 0.8 --threads 90 >> "$LOG" 2>&1
fi
NCLUST=$(cut -f1 "$TSV" | sort -u | wc -l)
echo "CLUSTERS: $NCLUST" >> "$LOG"

# 4) rebuild splits (cluster-disjoint 80/10/10, benchmark-leak protected)
SPLIT_DIR="$C/splits_v3"
if [ ! -s "$SPLIT_DIR/train.fasta" ]; then
  $PY /home/codonflow/scripts/build_splits.py \
    --cleaned "$MERGED" --cluster-tsv "$TSV" --out-dir "$SPLIT_DIR" >> "$LOG" 2>&1
fi
for f in train val test; do
  n=$(grep -c ">" "$SPLIT_DIR/$f.fasta" 2>/dev/null || echo 0)
  echo "SPLIT $f: $n" >> "$LOG"
done
echo "=== v3 pipeline done $(date) ===" >> "$LOG"
cat "$LOG"
