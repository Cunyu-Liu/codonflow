### 6.37 Fixed-protein single-to-double synonymous OOD was not supported by MAGE pair coverage

The preceding MAGE analyses left open whether a fixed-protein pair assay could support training on synonymous single-codon changes followed by OOD evaluation on synonymous double-codon changes. RK26 examined this candidate design without repeating the earlier nested cross-validation. Because initial schema and count exploration preceded protocol freezing, the analysis was designated a retrospective data-adequacy audit rather than a preregistered mechanism experiment. The formal production and independent implementations used only codon, amino-acid, position, and wild-type annotations. Fitness, expression, relative codon-sickness scores, folding energies, RBS features, and SD-like fields were excluded from the derived fact table. Neither the original 33-construct MAGE mechanism-test set nor the RK04 functional-untouched split was accessed.

The raw pair table contained 8,192 constructs across two exhaustive 64 × 64 codon-pair contexts. Wild-type reconstruction from the standard genetic code identified `GCC;AAA` for positions 1–2 and `AAA;GAA` for positions 2–3. Mutation-order reconstruction classified the complete table into two wild-type controls, 252 single-codon variants in the pair assay, and 7,938 codon-pair variants. Fixed-protein synonymous subsets were then obtained by requiring the translated amino acid to match the corresponding wild-type residue at every changed position. The frozen feasibility rule required at least two synonymous singles and two synonymous doubles in each pair context so that the proposed OOD spread would not be defined by a singleton in either context. This was a design-feasibility rule, not a power analysis.

**Table 9**

*Fixed-Protein Synonymous Coverage in the MAGE-seq Codon-Pair Assay*

| Pair context | WT codons | All rows | All single-codon variants | All codon-pair variants | Synonymous singles | Synonymous doubles | Coverage |
|---|---|---:|---:|---:|---:|---:|---|
| 1–2 | GCC;AAA | 4,096 | 126 | 3,969 | 4 | 3 | PASS |
| 2–3 | AAA;GAA | 4,096 | 126 | 3,969 | 2 | 1 | FAIL |
| Total | — | 8,192 | 252 | 7,938 | 6 | 4 | NOT FEASIBLE |

*Note.* Synonymous subsets preserve the wild-type protein at every changed position. The coverage rule requires at least two synonymous single-codon variants and two synonymous double-codon variants within each pair context. It evaluates design feasibility only and is not a statistical power analysis. WT denotes wild type.

Only 6 synonymous single-codon variants and 4 synonymous double-codon variants remained after fixed-protein filtering (Table 9). Pair 1–2 contained 4 synonymous singles and 3 synonymous doubles and therefore passed the coverage rule. Pair 2–3 contained 2 synonymous singles but only 1 synonymous double and therefore failed. Thus, the 8,192-row assay size did not translate into an adequately covered fixed-protein interaction-OOD design; most pair constructs were not synonymous with the wild-type protein. The resulting scientific outcome was `FIXED_PROTEIN_SINGLE_TO_DOUBLE_SYNONYMOUS_OOD_NOT_SUPPORTED_BY_SAMPLE_COVERAGE`. The four synonymous double-codon constructs remain available for descriptive study, but they do not support the proposed confirmatory cross-context model comparison.

No model was fitted, no functional endpoint was evaluated, and no confidence interval or *p* value was produced. Consequently, this audit is not a negative result about the performance of positional or structural interaction models. It establishes only that the candidate confirmatory comparison could not be conducted with the required sample coverage. It also provides no evidence about protein OOD, translation velocity, mRNA decay, or spatial coupling.

Synthetic tests passed 10/10 for both the production and independent implementations. An independent verifier reconstructed all 8,192 raw rows, reconciled the clean metadata, and compared every sequence-only derived fact without using fitness or other functional measurements. Independent acceptance passed 42/42 checks, and the production and independent pair-context counts agreed exactly. Subsequent closeout and registry binding passed 54/54 checks, including source, protocol, artifact, report, scientific-commit, and claim-boundary verification.

RK26 therefore closes the proposed MAGE single-to-double synonymous OOD candidate on data-adequacy grounds while leaving the underlying mechanism question unresolved. RK-G1 remains false and expensive generator training remains unauthorized. The audit does not establish CodonFlow-RK superiority, external SOTA, functional untouched performance, or a complete mechanism result, and the manuscript remains a non-submittable working draft.
