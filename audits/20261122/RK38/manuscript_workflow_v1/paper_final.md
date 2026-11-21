### 6.49 A sequence-verified asset inventory resolves baseline availability but not the external or untouched scientific gates

The preceding negative generation and cross-study prediction results required an explicit separation between missing evidence and evidence that had already been generated but not inventoried under one contract. RK38 therefore performed a read-only reconstruction of the existing baseline assets and the functional-untouched partition. The protocol prohibited new model training, new external generation, outcome-label access, and any retrospective zero-filling of missing budgets or costs. It also kept protein-to-CDS external methods separate from CodonFlow's natural-source warm-start semantics. The objective was to determine which comparisons are computationally supported by real artifacts, not to manufacture a unified ranking across incompatible inputs.

The reconstruction reconciled 846 record-seed-method cells (Table 30). A7/G2 contributed 324 raw runs, including 108 learned CUDA runs and 216 shared simple-search runs; its gate remained failed. RK06 contributed 216 dense simple-search files with 500 ordered points per file and 108,000 unique terminal-scorer calls. These files describe the same shared simple-search family at finer cost resolution and were not counted as an additional independent method family. The 54 legacy A6 files, all stored in the `unique18_s0` directory with seed-specific filenames, supplied 270 record-seed-method rows. Eighteen LinearDesign-11 records and 18 EnsembleDesign records completed the inventory. Every detailed row was linked to a raw-file SHA256, record, seed, method, attempt count, unique-sequence count, duplicate-or-unreturned count, and available cost fields.

**Table 30**

*Verified RK38 Asset Coverage and Evaluation Scope*

| Evidence line | Detailed cells | Real execution content | Scientific role |
|---|---:|---|---|
| A7/G2 FULL, EDIT, and shared simple search | 324 | 108 learned CUDA runs; 216 simple-search runs | Existing generation failure and search controls |
| RK06 dense simple search | 216 | 500 ordered points per run; 108,000 unique scorer calls | Cost-resolved view of shared simple-search runs |
| A6 five legacy external methods | 270 | 18 records × 3 seeds × 5 methods | Actual-set external reference assets |
| LinearDesign-11 official grid | 18 | Seed-0 record summaries derived from 198 official runs | External actual-set reference; λ is not a scorer budget |
| EnsembleDesign 11-run recovery | 18 | Seed-0 record summaries from 18 official processes | External actual-set reference |
| RK16 B11 ordered prefixes | 4 method summaries | 792 primary real generation calls | Separate four-method proxy-budget analysis |
| Functional untouched | Metadata only | 19,072 rows; 13,569 construct-signature groups | Eligibility boundary; outcomes not opened |

*Note.* The 846 detailed cells exclude the RK16 summary-only and untouched-metadata lines. A6 = legacy external-baseline generation family. B11 = generation-call budget 11. λ = LinearDesign objective weight. RK06 and A7 shared simple search are overlapping evidence lines rather than independent biological or algorithmic replicates.

For the seed-0 external actual sets, all 126 record-method cells matched the frozen seven-method matrix at the exact DNA-sequence-set level. LinearDesign-11 had the descriptively highest mean normalized hypervolume, 29.97288749, whereas the legacy LinearDesign scan reached 29.85589404 (Table 31). These values summarize the fixed proxy objective over actual returned sets; they are not dense-budget areas under the curve, time-matched comparisons, functional outcomes, or CodonFlow-versus-external effects. GEMORNA, CAI-greedy, and the legacy LinearDesign scan lacked a common ordered dense prefix. The separate RK16 analysis retained 792 real generation calls for four methods at B11, with mean dense-prefix AUC values of 22.79460632 for LinearDesign-11, 14.89623442 for EnsembleDesign, 5.20544403 for codonGPT, and 0.70295152 for uniform sampling. No CodonFlow arm was present in either external matrix.

**Table 31**

*Seed-0 External Actual-Set Summary Under the Frozen Proxy Objective*

| External method | Actual outputs | Mean normalized HV | Mean pairwise NED | Actual-set dense AUC |
|---|---:|---:|---:|---|
| LinearDesign-11 | 131 | 29.97288749 | 0.07128928 | Not available |
| Legacy LinearDesign scan | 103 | 29.85589404 | 0.07924804 | Not available |
| GEMORNA | 1,427 | 20.01528840 | 0.16375052 | Not available |
| EnsembleDesign 11-run | 192 | 16.69398208 | 0.04580360 | Not available |
| codonGPT | 1,800 | 14.53721918 | 0.23001838 | Not available |
| CAI-greedy | 18 | 11.52355615 | 0 | Not available |
| Uniform synonymous | 1,800 | 1.71876321 | 0.24078285 | Not available |

*Note.* HV = normalized hypervolume under the existing proxy objective; NED = normalized edit distance. Actual outputs are unique sequence counts aggregated over 18 records. Actual-set dense AUC is unavailable because these methods do not all provide a common real ordered budget trajectory. The separate RK16 B11 results must not be substituted into this column. All 126 cells had identity rate 1 under the frozen matrix.

The untouched audit did not authorize or perform an evaluation. Its 19,072-row MAGE partition contained one operational cluster and 13,569 construct-signature groups, but only 362 rows were synonymous single-codon variants. The remainder included nonsynonymous, codon-pair, and UTR variants, so the partition cannot independently support a general multi-protein fixed-protein conclusion. RK20 had passed only 2/8 sequence-OOD comparisons and had not established functional robustness. Accordingly, untouched outcomes and new file-content hashes were not read; only frozen split summaries and file metadata were used.

An independently written standard-library verifier reconstructed every detailed row and external sequence set without importing the production implementation. After retaining an initial schema-related failure, the corrected independent reports passed 1851/1851 checks in both the primary and clean roots. Clean reproduction produced byte-identical detailed and external-cell CSV files and an exact match for the summary apart from timestamps and output paths. Closeout passed 9/9 checks, and the full project suite recorded 472 passed, 1 skipped, and 5 subtests passed. These checks establish asset integrity and reproducibility only. External SOTA, a complete time-matched seven-method comparison, functional-untouched confirmation, RK-G1, and manuscript submittability remain false.

::: {.evidence-anchor #sec-6-49}
| Field | Evidence |
|---|---|
| Code commit | `83469e5b1f87f467827ecd5a09483d8f2ccc205d` |
| Protocol | `configs/a8_rk38_baseline_untouched_inventory_protocol_v1.json`; SHA256 `025006e43ec1bc5ba17c53ea1b4771cb89ffd3cb61bb4229bddf2f3a75eeaadf` |
| Production | `audits/20261122/RK38/rk38_baseline_untouched_inventory_v1.json`; SHA256 `1c0994b38582c2cae9b3e653a64f92daaf8bf306ccaba5e61855be2140f7864e` |
| Independent | `rk38_baseline_untouched_inventory_independent_v2.json`; 1851/1851 PASS; SHA256 `43299ee0243813b501a3d205e409ca84333234048aa0a540c4a4db8b3f5bb992`; retained v1 schema failure |
| Clean reproduction | Clean independent 1851/1851 PASS; closeout 9/9 PASS; SHA256 `21e9ba813d87c06bd05a5e051d2e2330ab9066a17addbf1a6b2d26e4af76cdd7` |
| Artifacts | `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk38/baseline_untouched_inventory_v1/`; detailed CSV SHA256 `e792c6dca54d1bca6f3a3c940d471ab5966a424f6edfe2549a32e29d95484df2`; external-cell CSV SHA256 `7de82e33f842016189ba4b9182e46b70c8da77a6b5e3cbff47b59507657f5a8f` |
| Tests | 472 passed, 1 skipped, 5 subtests passed |
| Scope | Read-only verified asset and eligibility inventory; no new training or generation, no untouched outcomes, no unified time match, no external SOTA, no RK-G1, and no submittable-manuscript claim |
:::
