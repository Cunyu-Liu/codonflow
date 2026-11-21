# A8-RK29 source feasibility and provenance audit

**Status:** iCodon selected for the frozen protein-cluster OOD experiment.
**Audit stage:** label-free; no `Decay_rate` or nine timepoint abundance values were extracted.
**Date:** 2026-11-21.

## Candidate review

| Candidate | Why it could discriminate | Verified access | Decision |
|---|---|---|---|
| Goodman et al. 2013, Science | Large synonymous E. coli N-terminal reporter library with RNA, protein, and translation-efficiency measurements | Publisher CSV endpoints returned HTTP 403 on both workstation and server; Europe PMC reports no PMC supplementary mirror. No valid per-variant CSV was obtained. | **Not usable in RK29.** Do not treat figure legends as observed table fields. |
| Mauger et al. 2019, PNAS | Synonymous Luc/hEpo/eGFP variants, nucleotide chemistry, and SHAPE-MaP | Europe PMC package is valid: 22,904,842 bytes, SHA256 `d7e28cfab7d2c3b5533746eb52af19a8a3f4aee3cec62329f464654896bbffcf`. `sd01` contains SHAPE tables and `sd02` 86 ORFs, but no directly joined per-variant functional outcome table was found. | **Not sufficient for the registered regression.** No figure digitization or imputation. |
| Diez et al. 2022, Scientific Reports, iCodon | 955 perfect synonymous reporters, 96 synthetic proteins, fixed initiation context, iCodon/IDT/Genewiz designs, and 2/5/8-hpi injected-mRNA decay in zebrafish embryos | Official Springer S6 plus GEO `GSE207584` perfect-variant measurements and 1,395-record reference FASTA are valid. Sequence and design coverage pass the separate label-free audit. | **Selected.** Joint host/assay/protein/outcome change remains a causal-identification boundary. |

## Authoritative selected inputs

1. **S6 outcomes and iCodon baseline**
   URL: `https://static-content.springer.com/esm/art%3A10.1038%2Fs41598-022-15526-7/MediaObjects/41598_2022_15526_MOESM7_ESM.xlsx`
   File: `41598_2022_15526_MOESM7_ESM.xlsx`
   Bytes: 143,626
   SHA256: `203e0862d807bcda4742f8e8dfb2e1c6e32aca0d69fdfab34444d365274d3e6b`
   Schema: 955 rows; `Protein_id`, `Group`, nine abundance fields, `Decay_rate`, `Predicted_mRNA_stability`.

2. **GEO perfect-variant measurements**
   URL: `https://ftp.ncbi.nlm.nih.gov/geo/series/GSE207nnn/GSE207584/suppl/GSE207584_Zebrafish-library-perfect.csv.gz`
   Bytes: 98,372
   SHA256: `44451c890db1f350b529dbdd5e49b158789d23568b1243860f5990b96698902c`
   The raw table has 10,227 rows but 955 unique `Name` values. Its auxiliary `Protein_id`/`Group` cells are redundant and inconsistent across repeated names; they are not used as samples or authoritative design labels.

3. **GEO reference FASTA**
   URL: `https://ftp.ncbi.nlm.nih.gov/geo/series/GSE207nnn/GSE207584/suppl/GSE207584_reference.fasta.gz`
   Bytes: 79,908
   SHA256: `7d2cdda973ccef47a72e66d8ddf9e200271ffa9e5855635ce19eb94dedeab49c`
   1,395 designed records; each selected record is 339 nt = fixed 33-nt 5′ context + 297-nt variable region + fixed 9-nt 3′ context.

Article and accession records:
`https://pmc.ncbi.nlm.nih.gov/articles/PMC9287306/`
`https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE207584`

## Label-free cleaning contract

- Use only the 955 unique GEO `Name` values; never interpret the 10,227 GEO rows as independent variants.
- Derive `Protein_id` and design `Group` solely from the reference naming grammar:
  - `cX-pY` → `cX_pY`;
  - terminal `r1`…`r5` → `iCodon_1`…`iCodon_5` regardless of independent run tag;
  - `rIDT_*` → `IDT`; `rGenewiz_1` → `Genewiz`.
- The resulting protein-by-design multiset must exactly equal S6's 955-row multiset.
- After the complete audit, exclude `c7_p1`, `c7_p6`, `c7_p7`, and `c7_p9` because they contain fewer than three unique variants (five rows total). The frozen analysis set is therefore 950 variants across 96 proteins; the exclusion uses no outcome values.
- Each unique name must map to exactly one FASTA sequence; all sequences must pass alphabet, fixed-context, length, and within-protein synonymous-translation checks.
- After the protocol is committed, the production process may read the nine measurements solely to establish a unique one-to-one S6-to-name assignment and to run the frozen analysis. Row-order and fuzzy joins are forbidden.

## What the selected assay can and cannot identify

The primary target is the source-published per-variant `Decay_rate`, with larger values interpreted as more stable according to the study. The assay measures injected IVT-mRNA abundance in one-cell zebrafish embryos at 2, 5, and 8 hpi; it is not a direct protein-expression or physical translation-rate measurement.

Relative to RK27/RK28, this dataset jointly changes host, assay, proteins, sequence coverage, and outcome. A positive or negative structure increment is therefore conditional on this complete experimental context and cannot isolate which joint factor drives transport failure or success.

## Passing label-free coverage report

- Status: `PASS_LABEL_FREE_COVERAGE_AUDIT_FEASIBLE`; no abundance, decay, or model-fitting values were accessed.
- Selected: 950 variants, 96 proteins, 96 evaluation groups; five low-coverage rows excluded by the frozen rule.
- Cross-protein Hamming identity ≥0.90 pairs: 0; maximum observed identity: 0.3872053872053872.
- Primary-seed fold sizes: 189, 192, 190, 190, 189.
- Structure features: four finite ViennaRNA 2.7.2 MFE values per variant at 28 °C.
- Coverage report SHA256: `29035867295f33c4c40f5b4a2a6257711a5d226fa255835cb00f74bfe9e88602`.
- Protocol SHA256: `e12a28b9ceaf3c4d8c70b78868e69ebfa2913a169dac99cac77ca20705b1c196`.
- Manifest SHA256: `ed44676dc8322a4dce8814a612feb9cb98c6f612880c836e2936c360062eca57`.
- Structure-feature table SHA256: `c4f0b2b073424b73d614463883d80e3b2f293248392853c9efa2f9e6e39671f2`.
