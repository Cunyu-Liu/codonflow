# A8-RK16 manuscript and research-deck closeout

Date: 2026-11-20
Status: **PASS_RK16_RECORDED_TIME_MATCHED_AND_FUNCTIONAL_OOD_OPEN**
Baseline science/manuscript commit: `4115d281abe4a798b05525dff43f751460ee03a3`

## 1. Manuscript

The English working manuscript adds section 6.31, **Real generation-call dense-prefix comparison on unique18**. It reports the four-method means, all six Holm-adjusted paired comparisons, the descriptive B1..B100 extension, independent verification, finalization, regression, and the explicit negative boundaries.

- Manuscript: `paper/CodonFlow_preprint_A8.md`.
- Independent manuscript verification: **59/59 PASS**.
- Updated manuscript SHA256: `fe92cf4390f9cb79281002f094ca54a6cf79672895d362f4b4d1835c7d18338e`.
- The manuscript remains a non-submittable working draft because functional OOD, CodonFlow-RK, unified time-matched comparison, and external-SOTA evidence remain open.

## 2. Research deck

- Online deck: https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g
- RK16 page: **slide 112**, page ID `pZo`.
- Before write: 111 slides, revision 73, last page `pZn`, XML SHA256 `0c4d5e6d9301ef1ecb26668ae3fa61f15c3c03a0ecf6540c593c5dbbbccf304a`.
- Initial append: revision 74.
- Speaker-note structure repair in place: revision 75; the visible page and page ID were preserved.
- Final readback: 112 slides, last page `pZo`, final XML SHA256 `5a8c516411033be7916c4f7bd643c8caa00ed8ebfd70df7f9a3c8c4f928bac37`.
- The first 110 pages are byte-equivalent after whitespace normalization; page 111 differs only by terminal whitespace. Semantic comparison of all 111 old pages reports **zero differences**.
- The new page contains 34 elements, a native 5-by-3 table, four KPI cards, two conclusion cards, five structured speaker-note paragraphs, and no external images. The service normalized the table to three equal 288 px columns; total table width remains 864 px.

## 3. Evidence recorded on the slide

| Method | Mean dense AUC | Mean B11 normalized HV |
|---|---:|---:|
| LinearDesign-11 | 22.794606 | 29.972887 |
| EnsembleDesign-11 | 14.896234 | 16.693982 |
| codonGPT | 5.205444 | 7.989211 |
| Uniform synonymous | 0.702952 | 0.966618 |

The slide records 18 unique18 records, 792 primary generation-call positions, 6/6 Holm tests passing, 88/88 independent verification, and 53/53 finalization. LinearDesign minus EnsembleDesign is +7.898372 AUC and +13.278905 B11 HV; all six Holm-adjusted p-values are 0.00059997.

## 4. Independent PPT acceptance

- Scientific content bound to the final remote LF-normalized evidence: **28/28 PASS**.
- Candidate structure and official raw XML inspection: **19/19 PASS**; candidate SHA256 `c68a90057fb14befa745f8d6967b264e58c41c4fc539b8de662e5830c508b146`.
- Final online readback acceptance: **23/23 PASS**.
- Final acceptance confirms required visible claims, numerical equality with the approved update, page order, old-page preservation, canvas bounds, overlap rules, Inter fonts, table geometry, structured notes, and the official raw XML inspection of slide 112.

## 5. Engineering incidents resolved without changing science

1. A local pre-LF audit copy was detected before slide writing and replaced with the final remote evidence from commit `4115d281`.
2. A 3 px title/subtitle overlap was corrected before the online append.
3. `lxml 6.1.3` was installed only in the local PPT working directory for official raw XML inspection; system Python was not modified.
4. The service normalized the initial plain-text speaker note to empty content. A readback-driven, single-page `update-slide` repaired only the note into five paragraphs and preserved all visible elements.
5. The final verifier was corrected to read service-normalized paragraph text and `col span=3`; this resolved two verifier/schema mismatches without altering the online scientific content.

## 6. Unchanged boundaries

- `dense_prefix_superiority_pass=true` only for the frozen proxy comparison.
- `time_matched_comparison=false`; no shared-GPU wall-time claim is made.
- `scientific_gate_passed=false`.
- `codonflow_rk_evaluated=false`.
- `functional_ood_evaluated=false`; `functional_untouched_evaluated=false`.
- `rk_g1_pass=false`.
- `expensive_generation_authorized=false`; `external_sota_authorized=false`; `sota_claimed=false`.

## 7. Artifact placement and reproduction

Small page sources, write responses, acceptance reports, and verifiers are tracked under `audits/20261120/RK16/` and `scripts/`. Full before/after XML, raw inspections, preview XML, source snapshots, and final readbacks are retained under:

`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk16/ppt_v1/`

Run the three verifiers with the same Python environment and:

```bash
export RK16_PPT_WORK_DIR=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk16/ppt_v1
python scripts/a8_rk16_verify_ppt_content.py
python scripts/a8_rk16_verify_ppt_candidate.py
python scripts/a8_rk16_verify_ppt.py
```
