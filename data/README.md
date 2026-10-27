# Data sources registry

## Current audit status（2026-10-26/27）

- 大文件根目录：`/teams/HoulabData_1788502323/liucunyu/codonflow`；代码 `/home/codonflow`。
- v3 包含 862,240 个清洗后输入、25 物种；该数字不是独立蛋白数。训练/验证/测试为 689,635/87,078/85,527，长度范围 300–6000nt。
- `eval_outputs/audits_20261026/v3_exact_overlap.json` 已实测 train/val/test 之间存在精确 CDS 和翻译蛋白交叉重叠；旧“零泄漏”与“family-disjoint”不再成立。
- `splits_v4_protein` 按精确翻译蛋白去重，并排除完整 benchmark 的核苷酸连通簇。它是 exact-protein + nucleotide-cluster split，不自动等于 family 或 species OOD。
- HELD18 有 17 条唯一序列而非 18；历史 HELD18 只作探索性结果。GEMORNA nanoLuc 旧硬编码输入错误，必须按 benchmark FASTA 重跑。
- 新增数据的来源 URL、下载日期、输入/保留数量、文件哈希与 split 审计随新 manifest 冻结；未记录的原始物种 URL 不从记忆补写。
- `corpora/homology_v5`（2026-10-27）：MMseqs2 18.8cc5c，identity=0.5、双向 coverage=0.8、shuffle=0。唯一蛋白与 core/unique18 benchmark 一并聚类；862,240 输入保留 776,441，85,671 精确蛋白重复，128 条 benchmark 连通簇排除，train/val/test=618,073/80,191/78,177。独立 cluster/exact-overlap/守恒审计通过；这是 protein-homology-cluster 操作划分，不是 curated family 或 species OOD。
- `eval_outputs/audits_20261026/v5_distribution.json`：v5 全量长度/GC 直方图与分位数；平均长度 1632.3/1694.5/1628.0nt，平均 GC 0.5148/0.5137/0.5146。val 的长度偏移需随下游结果披露。

## Historical source table（旧版本溯源，非当前验收声明）

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
| bench_plus_ood | bench + 3 cross-family OOD (mouse ENSMUST00000202556.4 1905nt, fly FBtr0307879 1179nt, zfish ENSDART00000133583.2 465nt) | 2026-10-05 | 5 | 5 | d908751c | OOD members chosen from test-split nucleotide clusters; not family/species disjoint |
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
