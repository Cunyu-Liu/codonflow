### 6.48 Local codon-context ridge did not improve cross-study translation-occupancy prediction over constant or position controls

The RK36 eligibility audit triggered a data-supported pivot, and the earlier Mohammad16-to-Subtelny14 benchmark supplied a discriminating translation-occupancy problem rather than a claim about physical elongation velocity. In that benchmark, official RiboMIMO had higher transcript-balanced mean squared error (TB-MSE) than both a source-fitted position ridge and a constant predictor, while its mean within-transcript Pearson correlation was approximately zero. RK37 therefore asked whether a preregistered local codon-context representation could simultaneously improve TB-MSE over the constant control and mean Pearson correlation over the existing position ridge. The target was normalized ribosome-occupancy density; it was not a direct kinetic rate or a protein-expression endpoint.

The protocol was frozen before any target normalized outcome was read. Mohammad16 supplied 1,179 eligible source transcripts and Subtelny14 supplied 3,921 eligible target transcripts, with zero exact-CDS overlap. The 86-dimensional position representation reproduced RK05, whereas the 477-dimensional local representation encoded seven codons at offsets −3 through +3, window-validity indicators, 20 relative-position bins, relative position and log length. Raw and transcript-centered targets were distinguished. Deployment anchoring used only the source-training global mean, leaving within-transcript correlation unchanged. Three source split seeds, four feature/target families and four ridge penalties produced exactly 48 unique source fits. All penalties and deployed arms were selected on source validation before target evaluation. The two confirmatory endpoints used 20,000 transcript-paired bootstraps and 20,000 sign-flip permutations at primary seed 1234, two-side Holm correction and two sensitivity seeds.

**Both confirmatory endpoints failed, and both effects were adverse (Table 28).** The primary local-centered-anchored model increased rather than decreased TB-MSE relative to constant, with an improvement effect of -0.75522894 and a 95% interval entirely below zero. It also reduced mean Pearson correlation relative to position raw by 0.03302839. Both sensitivity-seed effects were negative for both endpoints. Small Holm-adjusted p values therefore do not denote success: the resampling evidence supported degradation in the direction opposite to the preregistered gate. The decision remained `CROSS_STUDY_TRANSLATION_TASK_UNRESOLVED_COMPONENT_DIAGNOSIS_REQUIRED`.

**Table 28**

*Preregistered RK37 Dual Diagnostic Endpoints*

| Endpoint | Effect | 95% CI | Holm *p* | Sensitivity effects | Gate |
|---|---|---|---|---|---|
| TB-MSE improvement over constant | -0.75522894 | [-0.76259746, -0.74800535] | 9.9995e-05 | -0.69005569; -0.68900532 | Fail |
| Mean Pearson improvement over position raw | -0.03302839 | [-0.03575801, -0.03029614] | 9.9995e-05 | -0.03432728; -0.03461406 | Fail |

*Note.* Effects are improvements, so positive values were required. CI = transcript-paired bootstrap 95% confidence interval. Holm correction covered the two confirmatory endpoints. Sensitivity effects are reported for seeds 2345 and 3456. Each gate additionally required a positive effect, a positive CI lower bound, Holm *p* < .05 and two positive sensitivity effects.

The absolute metrics localized the failure beyond a single penalty choice (Table 29). At primary seed 1234, local-centered anchoring gave TB-MSE 1.722144918 and mean Pearson r 0.004471764, compared with 0.966915981 and 0.037500150 for the respective controls. Although source validation selected local α = 0.1 at seed 1234 and α = 100 at the other seeds, the α = 100 sensitivity runs still gave local-centered TB-MSE 1.656965266 and 1.655912418, with mean Pearson r only 0.003161618 and 0.003706826. The failure therefore was not rescued by the alternate frozen-seed penalty. Position centering increased mean Pearson by only 0.000487636 and did not beat constant TB-MSE. Anchoring RiboMIMO reduced TB-MSE from 2.186608221 to 2.158079586, but this remained far above constant. No target-selected replacement arm was introduced.

**Table 29**

*Primary-Seed Absolute Cross-Study Occupancy Metrics*

| Arm | α | TB-MSE | Mean Pearson *r* | Mean Spearman ρ |
|---|---|---|---|---|
| Constant | — | 0.966915981 | 0 (degenerate) | NA |
| RiboMIMO raw | frozen | 2.186608221 | -0.001007566 | 0.015973892 |
| RiboMIMO anchored | frozen | 2.158079586 | -0.001007566 | 0.015973892 |
| Position raw | 100 | 1.006966542 | 0.037500150 | 0.046564342 |
| Position raw anchored | 100 | 1.005275138 | 0.037500150 | 0.046564342 |
| Position centered anchored | 100 | 1.005090308 | 0.037987785 | 0.047110919 |
| Local raw anchored | 0.1 | 1.722859086 | 0.004075676 | 0.006751278 |
| Local centered anchored | 0.1 | 1.722144918 | 0.004471764 | 0.007179784 |

*Note.* TB-MSE = transcript-balanced mean squared error. The constant within-transcript correlation is degenerate and is shown as zero/NA rather than interpreted as a learned association. Position and local penalties were selected using source validation only. RiboMIMO predictions were frozen from RK05. Anchoring changes calibration but not within-transcript Pearson or Spearman correlation.

An independently written implementation reconstructed the raw matrices, COO-to-CSR features, source splits, all 48 fits, target predictions, model coefficients and inference arrays without importing the production module. It passed 771/771 checks, with maximum numeric difference 3.553e-15. A detached clean checkout reproduced the production run with 877/877 comparisons, exact equality for 111 arrays and byte-identical per-transcript CSV files. The full project suite recorded 466 passed, 1 skipped and 5 subtests passed. Scientific closeout passed 90/90 checks; its earlier schema and log-format failures were retained. Production, independent and clean runtimes were 155.861, 161.451 and 159.184 seconds, respectively. These checks establish computational agreement, not biological transport.

RK37 consequently rejects this local ridge pivot for the observed Mohammad16-to-Subtelny14 direction; it does not establish a universal absence of local sequence effects. The experiment remains a retrospective follow-up on a target already observed in RK05, not untouched confirmation, protein-family OOD, physical velocity estimation, functional-expression validation or external SOTA. Functional-untouched data were not read, no generator was trained, no wet-lab or prospective DBTL experiment was performed, and RK-G1 remains false.

::: {.evidence-anchor #sec-6-48}
| Field | Evidence |
|---|---|
| Code commits | `5786ffc0` (frozen protocol and production); `b8cf49c7` (independent verifier); `066ee562` (science and independent evidence); `87a33bd4` (clean reproduction and closeout) |
| Protocol | `configs/a8_rk37_translation_pivot_protocol_v1.json`; SHA256 `e121c146fa45ea1cb24bdb59d80aea52aaf50d00494e6881875fbcf529c15447` |
| Results | `audits/20261122/RK37/rk37_translation_pivot_result_v1.json`; SHA256 `d3182b89eb27d4d69f5301a9f1e4379893134e8e8b95bce3aedeb16274929522` |
| Independent | `rk37_translation_pivot_independent_v1.json`; 771/771 PASS; SHA256 `1996a1a0c395ac267f9aa2107e1c418d6c325af705863989abe9d8a50994108e` |
| Clean reproduction | `rk37_translation_pivot_clean_result_v1.json`; SHA256 `dc3f447ebe39e681e8b017d06c650baad3dc5a6bac231e5f5ce78cff250f59f7`; comparison 877/877 PASS, SHA256 `5e0a04205feefec8b923196825dcd6468a1322a43f29486321e0e6bd1fff57b1` |
| Closeout | `rk37_science_closeout_v2.json`; 90/90 PASS; SHA256 `d63d24965a0f51df21d6cf0b879d4feb5a786fcb09984abae103a113aeb12e9d`; retained v1 = 88/90 FAIL |
| Artifacts | `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk37/translation_pivot_v1/`; 48 fits per production, independent and clean runs |
| Scope | Negative retrospective cross-study normalized-occupancy diagnostic; no physical velocity, untouched, protein-OOD, functional, SOTA, generator, wet-lab or RK-G1 claim |
:::
