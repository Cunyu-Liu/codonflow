# A8-RK20 manuscript and PPT synchronization closeout

Status: **PASS_RK20_MANUSCRIPT_AND_PPT_SYNC**
Date: 2026-11-20
Scientific result commit: `09383437fe71ce65ddbfd4769dd32695d07aa35d`
Manuscript synchronization commit: `1e86aa8df3ee2d038db15822a21cad8ee010f45a`

## Scope completed

- Added manuscript section 6.30, "Four-seed functional robustness did not establish a stable mechanism increment," including the frozen design, all eight sequence-OOD comparisons, strong-baseline interpretation, independent verification, full CPU-suite result, and claim boundaries.
- Added the corresponding RK20 evidence-anchor hashes without changing the prior manuscript text. Independent manuscript verification passed **33/33 checks** and proved that removing section 6.30 and the RK20 anchor rows exactly restores the frozen before-manuscript.
- The English section-writing workflow passed prepare and draft checks; its authoritative status is **PASS**. The Markdown-only deliver shell emitted the previously observed `finish_with_status: command not found` after generating the final file; a separate authoritative `make status` returned PASS and is preserved.
- Appended one online research-deck page: slide **111**, ID **pZn**, revision **73**. It contains four run/acceptance KPIs, the four comparator rows with effect estimates, 95% CIs and Holm-adjusted p-values, supported/unsupported conclusion cards, and the closed-gate strip.
- Post-write full-deck readback confirmed **111 pages**, new last slide `pZn`, revision 73, and **byte-identical raw XML for every one of the previous 110 slides**. The new slide contains speaker notes and all required scientific boundaries.

## Verified scientific content

- Four fixed seeds: 20261119, 20261120, 20261121, 20261122; six new training runs; dev-only checkpoint selection.
- Only **2/8** sequence-OOD tests passed: all-feature versus GC-only ridge on Spearman and cluster-balanced MSE.
- All-feature did not significantly outperform full-proxy ridge or HistGB on either gated endpoint.
- All-versus-none Spearman did not pass eight-test Holm correction; CB-MSE crossed zero and reversed for seed 20261122.
- Independent scientific verification: **77/77**. Finalization binding: **67/67**. Full CPU suite: **340 passed, 1 skipped, 5 subtests passed** in 27.51 s.
- Shared-GPU runtimes remain robustness-run costs only, not controlled time-matched SOTA evidence.

## Evidence

- Manuscript before SHA256: `69dca1082bf7ca1edac69d94f80df018b26e723fbc19832da1df618a5a649dfe`.
- Manuscript after SHA256: `26377af298518e6f3e04d7569be78aa57ce3ce298471cc1fafcf150e8462929d`.
- Manuscript verification: `audits/20261120/RK20/rk20_manuscript_verification_v1.json`, 33/33 PASS.
- Online deck: `https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g`.
- New-slide source: `audits/20261120/RK20/rk20_ppt_slide111_v1.xml`.
- Add-slide response: `audits/20261120/RK20/rk20_ppt_add_response_v1.json`.
- PPT readback verification: `audits/20261120/RK20/rk20_ppt_verification_v1.json`.
- Full before/after XML and CLI responses are retained under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk20/functional_multiseed_v1/` with `ppt_rk20_` prefixes.
- Post-write deck XML SHA256: `0c4d5e6d9301ef1ecb26668ae3fa61f15c3c03a0ecf6540c593c5dbbbccf304a`.

## Unchanged boundaries

`functional_robustness_pass=false`, `rk_g1_pass=false`, `functional_untouched_evaluated=false`, `expensive_generation_authorized=false`, `external_sota_authorized=false`, and `sota_claimed=false`. The manuscript remains non-submittable. This closeout records manuscript and presentation synchronization only; it does not close mechanism, generator, unified time-matched baseline, full experimental regeneration, untouched confirmation, or wet-lab validation.
