<!-- A8_RK32_START -->
### 6.43 Structure increments depended on start-aware local coverage

RK32 asked whether the incremental predictive value of mRNA structure depended on structure provenance, coordinate system, or coverage within one fixed Kudla exact-CDS cohort. A label-free preflight read sequences and source-reported structure fields but no expression outcomes and fit no predictive model. The 864-nt source transcript comprised a 144-nt 5′UTR and a 720-nt CDS. Among prespecified local candidates, UTR[-4:] + CDS[:38] with ViennaRNA dangles=2 at 37 °C had the lowest RMSE against the source local field (Pearson *r* = 0.948727582; RMSE = 1.35489238 kcal/mol). The complete 864-nt transcript with dangles=2 was closest to the source full field (Pearson *r* = 0.994375347; RMSE = 1.98788071 kcal/mol). These comparisons established provenance rather than outcome-selected arms; source and Vienna values were retained separately because they were not numerically identical.

The frozen analysis reused 150 exact-CDS groups from 154 measurement rows and the RK27 37 whole-sequence clusters without reclustering or outcome-dependent filtering. CAI, GC, and GC3 formed the common simple backbone. Six structure arms added source local MFE, Vienna local MFE, source full MFE, Vienna full-CDS MFE, Vienna full-mRNA MFE, or the Mordstein-like combination of CDS[:300] MFE and 48-nt-window minimum and mean MFE. Ridge and HistGB were evaluated over 10 seeds and 5 whole-cluster folds per seed, yielding 700 real CPU fits: 10 × 5 × 2 × (1 shared simple + 6 structure arms).

For each structure arm and model, ΔSpearman was structure minus simple and MSE improvement was simple minus structure. The resulting 24 endpoints formed one Holm family. Inference used 20,000 whole-cluster bootstraps and 20,000 cluster sign-swap permutations at frozen primary seed 20261221. Each endpoint required a positive observed effect, a 95% CI lower bound above zero, Holm *p* < 0.05, and at least 8/10 positive seeds. An arm passed only when all four endpoints passed. The analysis was retrospective and outcome-known, not an independent untouched confirmation.

**Table 19**

*Structure-Definition Increment Endpoints Under Whole-Cluster OOD*

| Model | Structure arm | Endpoint | Observed effect | 95% CI | Holm *p* | Positive seeds | Decision |
|---|---|---|:---:|:---:|:---:|:---:|:---:|
| Ridge | Source local | ΔSpearman | 0.955051216 | [0.493814333, 1.10683284] | 0.00119994 | 10/10 | PASS |
| Ridge | Source local | MSE improvement | 0.157488705 | [0.07131334, 0.212686099] | 0.01359932 | 10/10 | PASS |
| Ridge | Vienna local | ΔSpearman | 0.984682834 | [0.528852934, 1.12965312] | 0.00119994 | 10/10 | PASS |
| Ridge | Vienna local | MSE improvement | 0.156925835 | [0.0713051614, 0.214567242] | 0.01359932 | 10/10 | PASS |
| Ridge | Source full | ΔSpearman | 0.153271221 | [-0.0562670044, 0.3310289] | 0.518024099 | 10/10 | FAIL |
| Ridge | Source full | MSE improvement | 0.0193970832 | [-0.0183097302, 0.0374633353] | 1 | 10/10 | FAIL |
| Ridge | Vienna full CDS | ΔSpearman | 0.12473121 | [-0.0764309563, 0.318480615] | 0.898155092 | 10/10 | FAIL |
| Ridge | Vienna full CDS | MSE improvement | 0.0254664104 | [-0.00995662572, 0.0437405283] | 1 | 10/10 | FAIL |
| Ridge | Vienna full mRNA | ΔSpearman | 0.233893686 | [-0.0111389774, 0.426929871] | 0.138743063 | 10/10 | FAIL |
| Ridge | Vienna full mRNA | MSE improvement | 0.032179994 | [-0.0182605522, 0.0549924842] | 1 | 10/10 | FAIL |
| Ridge | Mordstein-like | ΔSpearman | 0.613264447 | [0.199750612, 0.89994281] | 0.01259937 | 10/10 | PASS |
| Ridge | Mordstein-like | MSE improvement | 0.111043252 | [0.0395160754, 0.160466415] | 0.178491075 | 10/10 | FAIL |
| HistGB | Source local | ΔSpearman | 0.412577935 | [0.208827912, 0.520317751] | 0.00314984251 | 10/10 | PASS |
| HistGB | Source local | MSE improvement | 0.10590706 | [0.0422788346, 0.140561063] | 0.0123493825 | 10/10 | PASS |
| HistGB | Vienna local | ΔSpearman | 0.402746947 | [0.220998682, 0.523020516] | 0.00219989001 | 10/10 | PASS |
| HistGB | Vienna local | MSE improvement | 0.104263307 | [0.0556641446, 0.130178064] | 0.00599970001 | 10/10 | PASS |
| HistGB | Source full | ΔSpearman | -0.0726139034 | [-0.180931195, 0.0360563175] | 1 | 1/10 | FAIL |
| HistGB | Source full | MSE improvement | -0.003660366 | [-0.0389718174, 0.016237744] | 1 | 7/10 | FAIL |
| HistGB | Vienna full CDS | ΔSpearman | -0.061798755 | [-0.148418884, 0.0457714536] | 1 | 3/10 | FAIL |
| HistGB | Vienna full CDS | MSE improvement | -0.00305204746 | [-0.0331182873, 0.0135379952] | 1 | 8/10 | FAIL |
| HistGB | Vienna full mRNA | ΔSpearman | -0.0579532734 | [-0.160667108, 0.0311995235] | 1 | 0/10 | FAIL |
| HistGB | Vienna full mRNA | MSE improvement | 0.00500366777 | [-0.0353734692, 0.0254171311] | 1 | 10/10 | FAIL |
| HistGB | Mordstein-like | ΔSpearman | 0.131561578 | [-0.0366203414, 0.288915644] | 1 | 10/10 | FAIL |
| HistGB | Mordstein-like | MSE improvement | 0.0703324595 | [3.45108646e-05, 0.109972176] | 0.929453527 | 10/10 | FAIL |

*Note.* ΔSpearman = structure − simple; MSE improvement = simple − structure. Observed effects and resampling inference use frozen primary seed 20261221; positive-seed counts summarize all 10 seeds. CI denotes the 95% whole-cluster bootstrap confidence interval. The Holm adjustment spans all 24 endpoints.

Both local arms passed all four endpoints, whereas all three full-coverage arms failed all four. The Mordstein-like arm passed only Ridge ΔSpearman: effect = 0.613264447, 95% CI [0.199750612, 0.89994281], Holm *p* = 0.01259937. Its Ridge MSE improvement had a CI above zero (0.111043252; 95% CI [0.0395160754, 0.160466415]) but failed multiplicity control (Holm *p* = 0.178491075). Ridge full-mRNA ΔSpearman likewise did not pass (effect = 0.233893686; 95% CI [-0.0111389774, 0.426929871]; Holm *p* = 0.138743063). The arm-level accounting was Source local 4/4; Vienna local 4/4; Source full 0/4; Vienna full CDS 0/4; Vienna full mRNA 0/4; Mordstein-like 1/4.

**Table 20**

*Absolute Structure-Definition Performance at the Primary Seed*

| Arm | Spearman | MSE |
|---|:---:|:---:|
| Null | -0.367234242 | 0.194471052 |
| Ridge simple | -0.318413223 | 0.257148783 |
| Ridge Source local | 0.636637993 | 0.0996600784 |
| Ridge Vienna local | 0.666269611 | 0.100222948 |
| Ridge Source full | -0.165142002 | 0.2377517 |
| Ridge Vienna full CDS | -0.193682013 | 0.231682373 |
| Ridge Vienna full mRNA | -0.0845195374 | 0.224968789 |
| Ridge Mordstein-like | 0.294851224 | 0.146105531 |
| HistGB simple | 0.302423883 | 0.198657755 |
| HistGB Source local | 0.715001818 | 0.0927506949 |
| HistGB Vienna local | 0.705170829 | 0.0943944478 |
| HistGB Source full | 0.229809979 | 0.202318121 |
| HistGB Vienna full CDS | 0.240625128 | 0.201709802 |
| HistGB Vienna full mRNA | 0.244470609 | 0.193654087 |
| HistGB Mordstein-like | 0.43398546 | 0.128325295 |

*Note.* Values use frozen primary seed 20261221. Null is the training-fold mean. These are retrospective fixed-GFP expression outcomes under sequence-cluster OOD, not functional or protein OOD, direct structural measurements, or an external SOTA comparison.

The resulting conclusion was `STRUCTURE_INCREMENT_DEFINITION_DEPENDENT_RETROSPECTIVELY`. Within this cohort, the evidence supports an increment for the two start-aware local definitions, not a universal structure effect or a claim that longer coverage is inherently uninformative. The exact −4…37 window cannot be reconstructed from the current Mordstein observed-R1 FASTA, which starts at CDS position 4 and lacks the start codon and four upstream nucleotides; RK32 therefore does not close cross-study local-structure transport.

Independent recomputation from the raw Kudla table rebuilt the cohort, Vienna and Mordstein-like features, 700 model fits, and all inference. It passed 23/23 checks. Maximum absolute differences were 2.84217e-14 for features, 2.66454e-15 for predictions, 1.38778e-16 for metrics, 2.35922e-16 for seed effects, 2.28983e-16 for inference arrays, and 6.245e-17 for summary values. Production and independent recomputation required 252.140414 and 443.406127 s, respectively. Release closeout passed 23/23 checks, and project testing passed 423 tests with 1 skipped.

A separate clean checkout at 469b30e4604f3545157c299b18ab24a3713cf322 repeated production and independent verification. The comparison passed 106/106 checks: all 6 CSV artifacts were byte-identical and all 50 inference arrays matched exactly. Clean production and independent verification required 236.907060 and 453.867139 s. The retained history includes a pre-fit v1 stop caused by using exact-CDS identifiers as CDS hashes and an independent-report correction for literal `null` parsing; neither engineering correction changed the scientific arms, folds, models, outcomes, inference, or acceptance gates.

RK32 does not read functional-untouched data, authorize generator training, perform wet-lab or prospective design–build–test work, establish protein OOD, close complete external SOTA or unified time-matched comparison, complete a seven-method dense generation-call matrix, or complete RK-G1. The manuscript remains a non-submittable working draft, and these open tasks are not reclassified as completed by this retrospective structure-definition result.

<!-- A8_RK32_END -->
