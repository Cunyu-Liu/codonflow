# RK-02 — real functional data download, cleaning and audit

Date: 2026-11-18. Branch: `a8-rk`. Execution host: remote Matpool CPU only; no training or GPU job started.

## Final status

- **Eight official raw supporting files verified:** Boël XLSX + supplement PDF, MAGE-seq Data S1–S4 CSV, Kudla SOM PDF + degenerate-oligonucleotide TXT.
- **Five clean CSV artifacts generated:** 6,348 Boël rows + 9,344 MAGE single-codon assay rows + 8,192 codon-pair rows + 1,536 UTR rows = **25,420 unified long rows**.
- **11/11 unit tests passed.** An independent verifier, which does not import the producer module, recomputed raw/clean SHA256, row counts, Boël CDS/labels, MAGE mutation signatures, finite labels and split state: **39/39 PASS**.
- **No train/dev/test split or training was created.** Every clean row remains `UNASSIGNED`; random row splitting is forbidden.
- **Documented data gap:** Kudla's paper reports 154 constructs, but the downloaded SOM contains methods, Figs. S1–S9 and references, and the TXT contains degenerate synthesis oligos—not a 154-row sequence–expression table. Actual acquired/clean Kudla sequence–label rows are **0**. No values were inferred from plots or regression summaries.

The overall status is therefore `PARTIAL_KUDLA_ROW_DATA_UNAVAILABLE`, not “all three sources complete.” All listed raw files downloaded successfully; the unresolved item is the Kudla row-level data product, recorded in `data_product_failures.csv`.

## Reproduce

Run from `/home/codonflow-a8-rk` with the existing `/root/miniconda3/bin/python`. Production code uses only the Python standard library and does not modify the shared environment.

```bash
/root/miniconda3/bin/python -m unittest scripts.tests.test_a8_rk_functional_data

/root/miniconda3/bin/python scripts/a8_rk_functional_data.py \
  --config configs/a8_rk_functional_sources.json \
  --data-root /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional \
  --audit-dir audits/20261118/RK02 --download

/root/miniconda3/bin/python scripts/a8_rk_functional_data.py \
  --config configs/a8_rk_functional_sources.json \
  --data-root /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional \
  --audit-dir audits/20261118/RK02 --audit

/root/miniconda3/bin/python scripts/a8_rk_verify_functional_data.py \
  --data-root /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional \
  --audit-dir audits/20261118/RK02
```

The downloader writes `.part.<pid>` files, validates PDF/XLSX/CSV payloads and atomically renames successful downloads. HTTP 200 HTML/challenge pages are rejected as data. Browser-obtained official files are registered with `--register-browser-file`; their URL, local path, bytes and SHA256 are recorded in `download_manifest.json`.

## Actual counts

| dataset | raw rows/files | clean rows | independent interpretation |
|---|---:|---:|---|
| Boël Supplementary Data 2 | 6,348 rows | 6,348 | 6,348 unique names and CDS; no excluded rows; E distribution 0:1,754 / 1:131 / 2:423 / 3:896 / 4:1,171 / 5:1,973 |
| MAGE Data S1 | 4,672 rows | 9,344 assay rows | 73 positions × 64 codons; 4,599 non-WT single-codon variants; two assays per construct |
| MAGE Data S2 | 8,192 rows | 8,192 | 8,190 non-WT measurements; 8,127 unique non-WT mutation signatures; 63 repeated cross-window rows; 252 single-codon rows in the pair assay |
| MAGE Data S3 | 1,536 rows | 1,536 | 1,530 UTR variants plus 6 WT rows; replicate index preserved |
| MAGE Data S4 | 4,099 rows | excluded | Genome-wide structural context, not per-construct expression/fitness labels |
| Kudla SOM + oligos | 2 files | 0 sequence–label rows | 154 is paper-reported only; supporting material does not contain the required row-level table |
| **Unified `functional_long.csv`** | — | **25,420** | Assay-row total, not a unique-construct total |

## Artifact hashes

| clean artifact | SHA256 |
|---|---|
| Boël `sequence_expression.csv` | `f76f0988c08aa7daa01c2a0100c01682f6e205b7003ba4d8c241d2eb167ccf2d` |
| MAGE `single_codon_fitness.csv` | `83901672861d1ae672a0770259e9adcda279844ebd927257966ec220a6a48da8` |
| MAGE `codon_pair_fitness.csv` | `7acecf37b7ca432468a8e5c7a45ab6f471df41ae7d30d493cf8e4fe95e06edf1` |
| MAGE `utr_fitness.csv` | `ce4a95c8de05d50f7d405f126c5f3ec787dcba1aa8fca099f8486823bb1f0f96` |
| Unified `functional_long.csv` | `c436b758369018fe0fd121ce6e741993e90a5de80b4706ab87082f7557b6a377` |

Large raw and clean data remain outside Git under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/{raw,clean}`. Code, compact manifests and audit reports remain under `/home/codonflow-a8-rk`.

## Audit file map

- `download_manifest.json` — eight verified raw files, source URLs, roles, bytes, SHA256 and acquisition status.
- `download_failures.csv` — currently empty; `resolved_download_failures` in the summary preserves earlier remote-access failures that were later resolved through official browser downloads.
- `data_product_failures.csv` — unresolved Kudla row-level table gap and next action.
- `audit_summary.json` — paper-reported versus actual counts, clean hashes, exclusions and leakage summary.
- `protocols.csv` — source-specific host/construct/induction/time/label provenance.
- `row_exclusions.csv` — Data S4 whole-source exclusion and Kudla missing sequence–label product; no valid Boël/S1/S2/S3 row was discarded.
- `leakage_report.json` — family/construct grouping constraints and `UNASSIGNED` split state.
- `independent_verification.json` — 39 independently recomputed checks, all PASS.

See `experiments/RK_DATA_REGISTRY.md` for source licenses and full raw/clean path registration, and `experiments/REGISTRY.md` for the run record.
