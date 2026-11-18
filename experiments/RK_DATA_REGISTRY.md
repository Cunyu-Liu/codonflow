# A8-RK public functional data registry

Updated: 2026-11-18 (RK-02 final audit). Data root: `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional`.

`paper_reported` and `actual_download_or_clean` are separate fields. A reported paper count is never used as an acquired row count. No simulated labels or figure-digitized expression values are present. Full artifact metadata and machine checks are in `audits/20261118/RK02/`.

| source_id | priority | landing_url | license | raw_path | raw_sha256 | clean_path | clean_sha256 | actual_download_or_clean | paper_reported | row_exclusion | split_assignment |
|---|---|---|---|---|---|---|---|---|---|---|---|
| kudla_2009_gfp | P1 | https://www.science.org/doi/10.1126/science.1170160 | Publisher supporting material; no open reuse license asserted | `raw/kudla_2009_gfp/som_pdf.pdf`; `raw/kudla_2009_gfp/oligos_txt.txt` | SOM `8b3d78c7489e941b8d57fd0edb7fa0d2daf2d061308e3294b57828cf0d1e1ec5`; oligos `e108c3991b817719a345ad085cfa23e9f9910a6fd3563017a819a84c87061d7d` | None | None | 2 supporting files; **0 row-level sequence–expression records** | 154 synonymous EGFP constructs | Entire sequence–label product unavailable: SOM is methods/Figs. S1–S9/references; TXT is degenerate synthesis oligos | UNASSIGNED; no Kudla rows |
| boel_2016_nesg6348 | P1 | https://www.nature.com/articles/nature16509 | Publisher supplement; Europe PMC marks article not open access; no CC license asserted | `raw/boel_2016_nesg6348/protein_dataset_xlsx.xlsx`; `raw/boel_2016_nesg6348/supplement_pdf.pdf` | XLSX `7e32a22549f4565a08284e64f4187c5562181b909bfb382849cd9227fe4ef978`; PDF `220f95efe292385455c0a5f992e339f438adb20fd878b40bb0070aa42ef03ab2` | `clean/boel_2016_nesg6348/sequence_expression.csv` | `f76f0988c08aa7daa01c2a0100c01682f6e205b7003ba4d8c241d2eb167ccf2d` | raw 6,348; clean 6,348; 6,348 unique names and CDS; 0 exclusions | 6,348 non-redundant heterologous proteins | 0 | UNASSIGNED; protein-family mapping still required |
| kelsic_2016_mage_seq | P1 | https://pmc.ncbi.nlm.nih.gov/articles/PMC5234859/ | Author-manuscript supplement; no open reuse license asserted | `raw/kelsic_2016_mage_seq/data_s{1,2,3,4}_*.csv` | S1 `ba9090668178ae0b95e5eadf161c90f611227fb2d505d538f4766670151c1368`; S2 `873f4ef0b410fb1299217d7c5cf0ffd5c78947591c9f944da867c428bdf93672`; S3 `58759029fa3ce44644d35ba115de7273aec5b449c323160c19e41d7e2591882b`; S4 `62b8dc92e47b94b5d8d540e9f254517aecdc76acb4bd3e07b8d514a15328e391` | `clean/kelsic_2016_mage_seq/{single_codon,codon_pair,utr}_fitness.csv`; unified `clean/functional_long.csv` | See detailed artifact table below | S1 raw 4,672 → long 9,344; S2 raw/long 8,192, 8,127 unique non-WT signatures; S3 raw/long 1,536; S4 raw 4,099, excluded from sequence–label table | 4,599 single-codon variants; 8,127 codon-pair constructs; 12,726 total in situ codon mutants | S4 all rows: genomic structural context, not per-construct labels; no valid S1–S3 row exclusions | UNASSIGNED; all infA measurements must stay in one fixed partition or be grouped by construct signature |
| kudla_2006_bicistronic | P2 | https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.0040180 | Read PLOS license before reuse | Not downloaded | — | Not generated | — | Candidate only; 0 downloaded rows | Bicistronic GFP/RFP library | N/A | UNASSIGNED |
| welch_2009_bicistronic | P2 | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0007002 | Read PLOS license before reuse | Not downloaded | — | Not generated | — | Candidate only; 0 downloaded rows | Bicistronic expression dataset | N/A | UNASSIGNED |
| fath_2011_bicistronic | P2 | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0017596 | Read PLOS license before reuse | Not downloaded | — | Not generated | — | Candidate only; 0 downloaded rows | Bicistronic expression dataset | N/A | UNASSIGNED |

## Clean artifacts

All paths are relative to the data root. The unified long table is assay-row level, not a unique-construct count.

| artifact | rows | bytes | SHA256 |
|---|---:|---:|---|
| `clean/boel_2016_nesg6348/sequence_expression.csv` | 6,348 | 12,424,986 | `f76f0988c08aa7daa01c2a0100c01682f6e205b7003ba4d8c241d2eb167ccf2d` |
| `clean/kelsic_2016_mage_seq/single_codon_fitness.csv` | 9,344 | 7,073,640 | `83901672861d1ae672a0770259e9adcda279844ebd927257966ec220a6a48da8` |
| `clean/kelsic_2016_mage_seq/codon_pair_fitness.csv` | 8,192 | 6,738,823 | `7acecf37b7ca432468a8e5c7a45ab6f471df41ae7d30d493cf8e4fe95e06edf1` |
| `clean/kelsic_2016_mage_seq/utr_fitness.csv` | 1,536 | 1,196,814 | `ce4a95c8de05d50f7d405f126c5f3ec787dcba1aa8fca099f8486823bb1f0f96` |
| `clean/functional_long.csv` | **25,420** | 27,433,093 | `c436b758369018fe0fd121ce6e741993e90a5de80b4706ab87082f7557b6a377` |

## Protocol and leakage boundaries

- Boël: BL21(DE3), full-length NESG proteins, N-terminal His6 tag, 3×3′UTR tiles, 0.2 mM IPTG, 18°C for Gz48v; labels are direct integer E calls from Supplementary Data 2. Family labels are not present in that workbook; no family split is claimed.
- MAGE-seq: one shared infA gene, 1 mM IPTG, 37°C, 1 h; M9 and LB assays. Data S1 expands one construct into two assay rows; Data S2 retains all measurement rows while independently reporting 8,127 unique non-WT mutation signatures and 63 repeated cross-window rows. MAGE rows carry codon/UTR mutation representations, not fabricated full construct sequences.
- No train/dev/test split has been created. Random row splitting is forbidden. See `audits/20261118/RK02/leakage_report.json` and `protocols.csv`.
