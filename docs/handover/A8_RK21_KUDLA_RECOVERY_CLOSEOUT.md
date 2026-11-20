# A8-RK21 Kudla sequence-expression recovery closeout

## Decision

`PASS_RK21_KUDLA154_RECOVERED_TAGGED72_AVAILABLE`. The complete per-construct GFP table was recovered from Supek–Šmuc Genetics 2010 File S2 and cross-checked row by row against the independently published Fernandes–Vinga PLOS ONE 2016 S1 Software MAT copy. Independent verification passed **69/69 checks**.

This closes source recovery only. It does not claim a mechanism increment, fixed-protein sequence-OOD result, functional protein-OOD result, untouched confirmation, generator result, controlled time-matched result or SOTA.

## Verified sources

- Primary measurements: Kudla et al., Science 2009, DOI `10.1126/science.1170160`.
- Authoritative per-construct table: Supek–Šmuc, Genetics 2010, File S2, DOI `10.1534/genetics.110.115477`; XLS SHA256 `ac3325e570a7f1c0ede2ff153d8a3f70ec494f8dca01ef4dba7ae80850cea0d4`.
- Independent derivative copy: Fernandes–Vinga, PLOS ONE 2016, S1 Software, DOI `10.1371/journal.pone.0150369`; ZIP SHA256 `d18851a9f313f86445d288fceacb5d37f69a419f8bf8493bce4dd97262378759`, inner MAT SHA256 `e440aedd5c13724c5bef834137ba0cf11e4613bc9f64462456a252edfee06595`.
- Pre-registered recovery protocol and implementation were pushed at `dd00b44dfc606c772dd61a10f6220ee73171de6c` before validated table export.

All 154 XLS rows match the MAT sequence, expression and 5′ MFE fields in the same order. The second MAT copy inside S1 Software is byte-identical. ZIP CRC, raw bytes and SHA256 values were independently checked.

## Recovered data contract

| item | verified value |
|---|---:|
| Main measurement rows / unique seqIds | 154 / 154 |
| Source columns preserved | 71 |
| Unique exact CDS | 150 |
| Duplicate exact-CDS groups | 4 pairs |
| Shared 5′ UTR | 144 nt |
| CDS including terminal stop | 720 nt |
| Encoded protein excluding stop | 239 aa |
| Distinct protein sequences | 1 |
| Expression range | 43–10606 |
| Tagged paired measurements | 72 |
| Tagged source columns preserved | 62 |

Every full mRNA is 864 nt and uses the same 144-nt 5′ UTR. Every CDS starts with ATG, has exactly one terminal stop and encodes the same 239-aa protein. No figure digitization or missing-value imputation was used.

The four exact-CDS duplicate pairs are `GFP_014/GFP_018`, `GFP_105/GFP_150`, `GFP_159/GFP_162`, and `GFP_205/GFP_224`. Their measured expression values differ. All 154 measurement rows are retained, but exact CDS must remain grouped in every future split; these pairs cannot be treated as independent unique sequences or randomly separated across train and evaluation.

The 72 tagged seqIds exactly match the main-sheet `is_in_72-sequence_set=yes` flags. File S2 supplies tagged MFE, codon frequencies and expression but **no tagged nucleotide sequence**. No tagged sequence was reconstructed or imputed.

## Output identity and verification

Large raw and derived artifacts remain under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk21/kudla_recovery_v1/`.

| artifact | SHA256 |
|---|---|
| `kudla154_source.csv` | `91cd75e742f443517d3fb0ee6c031c0e6df196388c555bad7313e0468f77e95c` |
| `kudla_tagged72_source.csv` | `e6bf426a6870279b13a22d0dc12e8b54848965c7e5ca70ab1d4a8b0466531a4b` |
| `kudla154_mrna.fasta` | `1ff7a7d4de8c34c724eab60545848e60ebb3d8e728bac5a3225936fd49182445` |
| `kudla154_cds.fasta` | `0871434c7dadb1875fc6e1df247b6922ee32121622f84060f6e8372a4cd5de60` |

The independent verifier re-read the original XLS, both GFP sheets, all source cells, both FASTA files, exact-CDS groups, protein translation, MAT fields and all output hashes. Its report is `audits/20261121/RK21/rk21_kudla_independent_verification_v1.json` and is mirrored beside the derived artifacts.

## Next boundary

The 154-construct main table is ready for a separately frozen fixed-protein, exact-CDS-grouped analysis. The 72 tagged pairs are ready for a separately frozen paired 5′-structure/expression analysis. Neither analysis has been run under RK21. Functional untouched remains unread; `RK-G1=false`; expensive generation remains unauthorized.
