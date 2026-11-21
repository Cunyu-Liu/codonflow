### 6.45 Exact local context adds robust signal, but matched ablation does not separably identify upstream or start-codon contributions

RK32 localized the Kudla structural increment to a 42-nt window spanning the last four 5′ UTR nucleotides, the start ATG, and CDS positions 4–38, whereas RK33 found no increment for a truncated CDS4–45 window in Mordstein observed R1. RK34 asked whether the exact local context as a whole, the upstream four nucleotides, or the start ATG accounted for the within-Kudla result. This was a retrospective, outcome-known, fixed-GFP analysis rather than an independent confirmation, biological perturbation, or cross-host transport test. The 154 measurement rows, 150 exact-CDS groups, 37 sequence clusters, seed–fold assignments, simple CAI/GC/GC3 features, Ridge and histogram gradient-boosting models, and whole-cluster inference remained fixed.

Four equal-length contexts shared the same CDS4–38 body: exact_real contained the observed upstream four nucleotides and ATG; start_only replaced the upstream nucleotides with N; upstream_only replaced ATG with NNN; and neither masked both elements. Thus every window was 42 nt, and the two factorial contrasts for each element varied only that element in the corresponding background. ViennaRNA at 37 °C with dangling ends enabled (dangles=2) defined the confirmatory analysis; dangles=0 was a prespecified sensitivity analysis that could not rescue a failed primary result. Seven new structure arms required 700 fits, while 200 accepted simple and Vienna-local exact-d2 fits were reused from RK32, yielding 900 evaluated fits.

Five paired families each contained two models × two metrics: exact_real versus simple, upstream given start, start given upstream, start without upstream, and upstream without start. The 20 confirmatory endpoints required a positive observed effect, a positive lower 95% whole-cluster bootstrap confidence limit, Holm-adjusted cluster-swap p < 0.05 across those 20 tests, and at least eight positive seeds. A family required all four endpoints. An upstream contribution required both upstream families, and a start contribution required both start families; these rules prevented a single favorable background or model from being interpreted as an independently identified component.

**The exact local context passed 4/4 endpoints, but none of the four separability families passed all four endpoints (Table 23).** In the confirmatory analysis, upstream-given-start passed 3/4, start-given-upstream 2/4, start-without-upstream 1/4, and upstream-without-start 2/4, giving 12/20 positive endpoints overall. Ridge produced several strong component contrasts, but HistGB and MSE endpoints did not consistently satisfy the joint gate. For example, upstream-given-start HistGB MSE improvement had Holm-adjusted p = 0.138943; start-given-upstream HistGB Spearman and MSE had adjusted p = 0.121594 and 0.138943; and start-without-upstream HistGB effects were near zero with adjusted p = 1.0. The sensitivity analysis retained exactly the same family-level decisions: exact_real versus simple passed 4/4, whereas the four component families did not pass. The supported conclusion is therefore a joint exact-context increment without separately identified upstream or start-codon contributions.

**Table 23**

*Confirmatory Paired Endpoints for the Equal-Length 42-nt Factorial Ablation*

| Comparison | Model | Metric | Effect | 95% CI | Raw *p* | Holm *p* | Positive seeds | Pass |
|---|---|---|---:|---|---:|---:|---:|---|
| exact−simple | Ridge | Spearman | 0.984683 | [0.528853, 1.129653] | 0.000050 | 0.001000 | 10/10 | Yes |
| exact−simple | Ridge | MSE improvement | 0.156926 | [0.071305, 0.214567] | 0.000800 | 0.009600 | 10/10 | Yes |
| exact−simple | HistGB | Spearman | 0.402747 | [0.220999, 0.523021] | 0.000100 | 0.001800 | 10/10 | Yes |
| exact−simple | HistGB | MSE improvement | 0.104263 | [0.055664, 0.130178] | 0.000300 | 0.004500 | 10/10 | Yes |
| upstream | start | Ridge | Spearman | 0.210417 | [0.080305, 0.294034] | 0.000200 | 0.003200 | 10/10 | Yes |
| upstream | start | Ridge | MSE improvement | 0.041329 | [0.027534, 0.065649] | 0.000150 | 0.002550 | 10/10 | Yes |
| upstream | start | HistGB | Spearman | 0.157024 | [0.037288, 0.262445] | 0.003250 | 0.029249 | 10/10 | Yes |
| upstream | start | HistGB | MSE improvement | 0.024915 | [0.005060, 0.043086] | 0.027399 | 0.138943 | 10/10 | No |
| start | upstream | Ridge | Spearman | 0.282371 | [0.108633, 0.369537] | 0.000300 | 0.004500 | 10/10 | Yes |
| start | upstream | Ridge | MSE improvement | 0.052910 | [0.028354, 0.076229] | 0.002150 | 0.023649 | 10/10 | Yes |
| start | upstream | HistGB | Spearman | 0.171890 | [0.001885, 0.284806] | 0.015199 | 0.121594 | 10/10 | No |
| start | upstream | HistGB | MSE improvement | 0.037780 | [0.006081, 0.054795] | 0.022849 | 0.138943 | 10/10 | No |
| start | no upstream | Ridge | Spearman | 0.516851 | [0.208333, 0.641511] | 0.000300 | 0.004500 | 10/10 | Yes |
| start | no upstream | Ridge | MSE improvement | 0.078088 | [0.024849, 0.114082] | 0.019849 | 0.138943 | 10/10 | No |
| start | no upstream | HistGB | Spearman | 0.028192 | [-0.096388, 0.082692] | 0.721114 | 1.000000 | 10/10 | No |
| start | no upstream | HistGB | MSE improvement | 0.013949 | [-0.021056, 0.027959] | 0.516174 | 1.000000 | 10/10 | No |
| upstream | no start | Ridge | Spearman | 0.444897 | [0.207528, 0.546831] | 0.000050 | 0.001000 | 10/10 | Yes |
| upstream | no start | Ridge | MSE improvement | 0.066507 | [0.029914, 0.099301] | 0.002600 | 0.025999 | 10/10 | Yes |
| upstream | no start | HistGB | Spearman | 0.013325 | [-0.067342, 0.066806] | 0.671866 | 1.000000 | 9/10 | No |
| upstream | no start | HistGB | MSE improvement | 0.001084 | [-0.013243, 0.013074] | 0.843708 | 1.000000 | 8/10 | No |

*Note.* Effects are the first context minus the comparator; MSE improvement is comparator MSE minus context MSE. CI is the 95% whole-cluster bootstrap interval. Raw and Holm-adjusted *p*-values use 20,000 cluster-swap permutations.

Primary-seed absolute performance illustrates why the joint gate matters (Table 24). The exact-d2 arm improved Ridge Spearman from −0.318413 for simple features to 0.666270 and HistGB Spearman from 0.302424 to 0.705171, with corresponding MSE reductions. Artificial N-masked arms showed model-dependent gains and losses, however, and these absolute scores did not override the paired factorial inference. The negative Ridge simple Spearman also warns against treating a high incremental effect as evidence that either the backbone or the resulting predictor is universally strong.

**Table 24**

*Absolute Held-Out Performance for Primary Seed 20261221*

| Model | Arm | Spearman | MSE |
|---|---|---:|---:|
| Intercept | null | -0.367234 | 0.194471 |
| Ridge | simple | -0.318413 | 0.257149 |
| Ridge | exact d2 | 0.666270 | 0.100223 |
| Ridge | start only d2 | 0.455853 | 0.141552 |
| Ridge | upstream only d2 | 0.383899 | 0.153133 |
| Ridge | neither d2 | -0.060998 | 0.219640 |
| Ridge | exact d0 | 0.657926 | 0.104198 |
| Ridge | start only d0 | 0.493257 | 0.136072 |
| Ridge | upstream only d0 | 0.409918 | 0.150057 |
| Ridge | neither d0 | -0.052052 | 0.218674 |
| HistGB | simple | 0.302424 | 0.198658 |
| HistGB | exact d2 | 0.705171 | 0.094394 |
| HistGB | start only d2 | 0.548147 | 0.119309 |
| HistGB | upstream only d2 | 0.533281 | 0.132174 |
| HistGB | neither d2 | 0.519955 | 0.133258 |
| HistGB | exact d0 | 0.720422 | 0.089129 |
| HistGB | start only d0 | 0.631280 | 0.104465 |
| HistGB | upstream only d0 | 0.561427 | 0.129870 |
| HistGB | neither d0 | 0.606911 | 0.109671 |

*Note.* Dangles=0 arms are sensitivity analyses and are shown for completeness rather than as replacements for the confirmatory dangles=2 comparisons.

An independently written raw-source implementation reconstructed the windows, energies, clusters, folds, all 900 fits, seed statistics, 40 primary-plus-sensitivity tests, and 82 inference arrays. It passed 155/155 checks; the maximum absolute prediction difference was 1.78e-15, and all 40 test records and 82 arrays matched within the frozen numerical criteria. The initial independent run retained a single schema failure because the null-baseline arm label became an empty CSV field on readback; only that identifier was canonicalized in verifier v2, with the numerical tolerances and scientific outputs unchanged. A no-hardlinks clean checkout of `4533dd1794fa1dc6fd7519b3b3131463b1ae826e` then repeated production and independent verification. The comparison passed 187/187 checks: 6/6 production CSV files, 82/82 production arrays, 5/5 independent CSV files, and 82/82 independent arrays were exactly reproduced. The full project suite reported 455 passed, one skipped, and five passing subtests.

These findings support only a retrospective, fixed-Kudla, sequence-cluster-OOD increment for the exact local context. N-masking is a computational ablation, not a biological perturbation, and the unmatched model behavior leaves interaction, background dependence, nonlinear feature use, and limited cluster-level precision as competing explanations. The experiment does not establish independent upstream or ATG necessity, universal initiation mechanisms, measured-structure validity, host or assay identification, functional or protein OOD, external SOTA, or RK-G1. Independent complete-CDS transport, unified time-matched and seven-method dense comparisons, multispecies VeloHARMO, prospective DBTL, and wet-lab validation remain open. Functional untouched data were not read, and expensive generator training was not authorized.

::: {.evidence-anchor #sec-6-45}
| Field | Evidence |
|---|---|
| Code commits | `4533dd1794fa1dc6fd7519b3b3131463b1ae826e` (accepted science); `cb8c1976d18a2acfe7b92f3039933a0701bc1c13` (clean reproduction and closeout) |
| Code | `scripts/a8_rk34_run_start_context.py`; `scripts/a8_rk34_verify_start_context_independent.py`; `scripts/a8_rk34_compare_reproduction.py`; `scripts/a8_rk34_closeout.py` |
| Protocol | `audits/20261121/RK34/a8_rk34_start_context_protocol_v2.json` |
| Results | `audits/20261121/RK34/rk34_start_context_result_v2.json`; `rk34_start_context_independent_v2.json`; `rk34_clean_reproduction_comparison_v1.json`; `rk34_closeout_v2.json` |
| SHA256 | protocol `5e75d50c65d5fea2c27aa92e287d72607af6cb709866384030583ddb7ba91ef4`; result `5eaddc34e9a69b79c4c595c83d4afd8beb4df51925171559fb6c864e2a4b2e12`; independent `7f7f6d105560da3e24b8653d0d0fbff52cef0947a4c7b336f69cae98c4d687b8`; reproduction `546619f08850c8306bf475f881882b6db3bad335b4cfb95b590738a4e30e6ff7`; closeout `b9473cf36ba331e105b8f58af35821367c728c37277352f12b4942cebe96f4d6` |
| Analysis | 154 retrospective measurement rows; 150 exact-CDS groups; 37 sequence clusters; 10 seeds × 5 folds; 700 new + 200 reused = 900 evaluated fits; 20 confirmatory + 20 sensitivity tests |
| Scope | Fixed-Kudla exact local context and artificial matched ablation only; no separable biological mechanism, independent transport, functional/protein OOD, generator, or wet-lab claim |
:::
