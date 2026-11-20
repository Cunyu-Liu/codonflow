# A8-RK26 — MAGE synonymous single-to-double OOD feasibility closeout

## Decision

**FIXED_PROTEIN_SINGLE_TO_DOUBLE_SYNONYMOUS_OOD_NOT_SUPPORTED_BY_SAMPLE_COVERAGE.**

The exhaustive MAGE-seq codon-pair table contains 8,192 constructs, but only **6 synonymous single-codon variants** and **4 synonymous double-codon variants** remain when fixed-protein identity and mutation order are reconstructed from the raw WT rows. The 2–3 pair context has only **1 synonymous double-codon variant**, failing the frozen requirement of at least two in each pair context. The proposed confirmatory single-to-double OOD model comparison was therefore **not run**.

This is a **retrospective data-adequacy audit**, not a preregistered mechanism experiment, a power analysis, or a negative functional/mechanism result. Four double-synonymous constructs can still support descriptive biology, but not the proposed confirmatory cross-context model comparison.

## Raw-to-clean sample chain

| Pair context | WT codons | Total rows | WT | All singles | All doubles | Synonymous singles | Synonymous doubles | Coverage rule |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 1–2 | GCC;AAA | 4,096 | 1 | 126 | 3,969 | 4 | 3 | PASS |
| 2–3 | AAA;GAA | 4,096 | 1 | 126 | 3,969 | 2 | 1 | FAIL |
| **Total** | — | **8,192** | **2** | **252** | **7,938** | **6** | **4** | **NOT FEASIBLE** |

The raw amino-acid labels were checked against standard genetic-code translations. Mutation order was recomputed from the unique WT in each pair context, and all 8,192 raw rows were reconciled against the clean construct metadata. The clean table's large number of pair variants is mostly non-synonymous and must not be interpreted as fixed-protein interaction coverage.

## Analysis boundary

The formal production audit loaded only `codon1`, `aa1`, `pos1`, `codon2`, `aa2`, `pos2`, and `is_wt` from the raw table. Its derived fact table contains sequence/annotation fields only: no fitness, expression, RCS, MFE, RBS, or SD-like feature/outcome column.

- Model fits: **0**.
- Functional endpoint evaluations: **0**.
- Confidence intervals or p-values: **0**.
- Original MAGE 33-construct mechanism test accessed: **false**.
- RK04 functional-untouched split accessed: **false**.
- Protein-OOD, velocity, decay, or spatial-coupling claim: **false**.
- RK-G1 remains **false**; generator training remains **unauthorized**.

## Independent verification

- Production/independent synthetic tests: **10/10 PASS**.
- Independent raw-source verification: **42/42 PASS**.
- Exact raw reconstruction and clean reconciliation: **8,192/8,192 rows**.
- Independent synonymous counts: **6 singles; 4 doubles**.
- Pair 1–2: **4 singles; 3 doubles; rule PASS**.
- Pair 2–3: **2 singles; 1 double; rule FAIL**.
- Deterministic sequence-only fact artifact: **8,192 rows**.

## Evidence and hashes

| Artifact | SHA256 |
|---|---|
| Frozen reproducibility protocol | `c49140ae2fe1ebbefa40290caa6b55774f16ae1949168936cb2c69bd205540b4` |
| Production result | `264d6a6dd4df2cd52738f9f465d6d0bcc67bb9784cb59304e733d7f55f519851` |
| Independent 42/42 report | `5a61826999015bc448636812e104ed0ff84a20f21b5efc522bf7be5a636632f0` |
| Production script | `22fa9202fd843bef69520c2d351c4bd5632d6b1b1641c3ff2bed917574f84799` |
| Independent verifier | `7e209a13576795655dd7a28e6531e1c076aa89007745fbc482510bbeb03bd68e` |
| Synthetic tests | `3c4419edbeb4f4e46644afb4ee5f2ff94386d98e7bdea5b674738021ddd03c96` |
| Test console | `f8d687234809ac6738f036c365377a8165b8dac6dd17c049765d908f202ab144` |
| Sequence-only facts, 8,192 rows | `ad96263a513c986abcd62b71c7927704b927422be383dc5bc71d60abc4c4b531` |
| Pair-context counts | `a3b3c5665f039917b6ffc36e8b3789884921760ac91469fd50c0dee668ec9b24` |

Large derived artifacts are under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk26/mage_pair_feasibility_v1/`; code and small reports are under `/home/codonflow-a8-rk/`.

Protocol/implementation freeze commit: `af338407392db625a3deaa76aab923ff1298fe3d`.

## Carry-forward

Do not present MAGE's 8,192 pair constructs or the earlier 12,726-construct asset count as usable fixed-protein double-synonymous OOD coverage. A future interaction study needs a new, genuinely synonymous multi-site dataset with adequate per-context coverage and a separately preregistered train/OOD protocol.
