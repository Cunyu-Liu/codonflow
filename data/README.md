# Data sources registry (Task 1.1 DoD)

All large artifacts live under `/mnt/cunyuliu/codonflow/corpora/`. Pipeline
step counts: `docs/data_audit/pipeline_counts.md` + `audit_train.json`.

| dataset | URL | download_date | raw_count | cleaned_count | sha256_prefix | notes |
|---|---|---|---|---|---|---|
| gencode_v47_pc_transcripts | https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_47/gencode.v47.pc_transcripts.fa.gz | 2026-10-04 | 137,576 transcripts (pc only) | 104,646 CDS clean | (gz mirror 3d8f…) gencode_v47_cds.fasta=500eb287 | CDS extracted from GTF-free transcript FASTA (ATG..stop, in-frame) |
| ensembl_mouse_cds | Ensembl BioMart mus_musculus_core (Ensembl Genomes r112) | 2026-10-04 | 103,020 | 77,527 | mus_musculus_cds.fa.gz=335bacfb | aux corpus |
| ensembl_zfish_cds | BioMart danio_rerio_core | 2026-10-04 | 66,082 | 48,358 | danio_rerio_cds.fa.gz=8de5d5ce | aux corpus |
| ensembl_fly_cds | BioMart drosophila_melanogaster_core | 2026-10-04 | 41,463 | 31,248 | drosophila_melanogaster_cds.fa.gz=44fb7abc | aux corpus |
| ensembl_worm_cds | BioMart caenorhabditis_elegans_core | 2026-10-04 | 29,563 | 28,843 | caenorhabditis_elegans_cds.fa.gz=13a3ebf9 | aux corpus |
| combined (human+4 species) | see above | 2026-10-04 | 215,246 clean | 215,246 → MMseqs2 0.8: 107,811 clusters | 107,811 representatives | combined_cluster_rep_seq.fasta; splits 80/10/10 cluster-level seed 0 |
| splits/train | derived | 2026-10-04 | — | 172,240 | bf7888ce | cluster-disjoint |
| splits/val | derived | 2026-10-04 | — | 21,149 | df1b516e | cluster-disjoint |
| splits/test | derived | 2026-10-04 | — | 21,857 | 6123ff2b | cluster-disjoint |
| bench (egfp+nluc) | UniProt P42212 CDS (syn-rewritten standard); nanoLuc GenBank JQ437370.1 CDS | 2026-10-04 | 2 | 2 | 679d6f53 | egfp.fasta=f2d3db12, nanoluc_cds.fasta=98dd9760; leakage guard: mmseqs cluster of egfp/nluc homologs excluded from train |
| bench_plus_ood | bench + 3 cross-family OOD (mouse ENSMUST00000202556.4 1905nt, fly FBtr0307879 1179nt, zfish ENSDART00000133583.2 465nt) | 2026-10-05 | 5 | 5 | d908751c | OOD members chosen from test-split clusters, family-disjoint |
| spcas9 long probe | UniProt Q99ZW2 CDS (syn-rewritten) | 2026-10-04 | 1 | 1 | 42c2e890 | 4107nt ≈ 1368 aa long-CDS probe |

Cleaning pipeline (per spec R2): (1) drop non-multiple-of-3 / no-stop
CDS; (2) drop internal stops; (3) length filter [300, 6000] nt;
(4) MMseqs2 easy-cluster 0.8 keep representatives; (5) cluster-level
80/10/10 split, seed 0 (split_audit.json above). Distribution audit
(length/GC/CAI/RSCU): docs/data_audit/audit_train.json + png.

Note (2026-10-09, retrospective): target of ">=1M CDS" from spec R2 was
revised down to 215k combined across 5 species — GENCODE v47 human pc
transcripts yield ~105k clean CDS and the 4 auxiliary species bring the
total to 215k. This is recorded as a deviation from the pre-registered
data scale; pretrain v2 converged on this corpus and downstream
evaluations passed all gates. Scaling to 1M+ (RefSeq/Ensembl all-species)
is listed as the top priority for the next iteration (see journal).
