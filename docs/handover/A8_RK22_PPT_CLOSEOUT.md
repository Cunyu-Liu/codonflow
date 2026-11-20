# A8-RK22 PPT closeout

## Delivered state

- Presentation: `https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g`
- Existing page count before editing: 113, revision 76, final slide `pZw`.
- Appended exactly one new page at the end: page 114, slide `pZl`, revision 77.
- Candidate verification: 45/45 checks passed.
- Online verification: 57/57 checks passed, including preservation of the IDs, order, semantic XML and notes of all 113 existing slides.

## Scientific content

The page is bound to `rk22_analysis_summary_v1.json` and the 63/63 independent science verification. It reports the HistGB Spearman gain of 0.262115, MSE improvement of 0.062073, Ridge Spearman gain of 0.718436, paired tagged Spearman of 0.565992, adjusted paired coefficient of 0.098815, confidence intervals, Holm-adjusted p-values and the fixed-GFP development scope. It explicitly preserves `protein OOD=false`, `RK-G1=false`, functional untouched unread, and generator training unauthorized.

## Write history

1. Saved full pre-edit XML and response; no concurrent edit was observed.
2. The first CLI attempt used unsupported `--position` and `--url` flags. Argument validation failed before any network write; the failure response is retained in the large-artifact evidence directory.
3. The second attempt used the documented `--presentation`, `--slide @file` and `--no-lint` arguments and returned `ok=true`, slide `pZl`, revision 77.
4. Full XML was read back after the write. An optional summary/content command was unavailable and stopped that chained command after the successful XML read; it did not alter the presentation. Verification therefore used the authoritative full XML and response.
5. No screenshot-based post-write self-check was used; the PPT workflow reserves screenshots for source/template inspection or explicit previews. Acceptance is based on semantic XML, layout bounds, font sizes, scientific anchors and old-slide preservation.

## Evidence locations

- Candidate XML, independent verifier, candidate and online reports, successful add response and source/online responses are committed under `audits/20261121/RK22/ppt/` and `scripts/a8_rk22_verify_ppt.py`.
- Full pre-edit and post-edit XML, all responses and working evidence are retained under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk22/ppt_v1/`.
- Source commit for the frozen protocol: `48eea1e2bd194b80e9c169e9420a3185e65fcb85`.
- Source commit for verified scientific evidence: `b506bf4deca5eb229bf683ceb7ebb12ef1141833`.

This PPT record does not change the scientific gates or authorize generator training.
