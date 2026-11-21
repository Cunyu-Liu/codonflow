# A8-RK29 research-slide closeout

**Status:** `PASS_RK29_PPT_READBACK`
**Date:** 2026-11-21
**Presentation:** https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g

## Scientific gate before reporting

The slide was created only after the independent raw-source verifier returned `PASS_INDEPENDENT_ALIGNMENT_FAILURE_VERIFICATION`. It records a source-identifiability failure, not a negative or positive structure-increment result.

Verified values used on the slide are 950 retained variants, 96 proteins/evaluation groups, 715/955 ambiguous outcome rows, 338/578 protein-by-design groups with multiple valid assignments, 10,227/10,227 independently rechecked Cartesian pairs, and zero model fits/endpoints.

## Single-page write and readback

- Baseline: 120 pages, revision 83, last slide `pZC` (RK28).
- Write: one page appended, new slide `pZx`, revision 84.
- Final deck: 121 pages; the first 120 slide IDs and their order are unchanged.
- Normalized XML comparison confirms that all prior slide content and attributes are unchanged; the only raw difference was trailing whitespace at the old final-slide boundary.
- New-page readback contains the required title, KPI values, audit table, boundary cards, four speaker-note paragraphs, and footer `121 · RK29`.
- All top-level objects are defined and lie within the native 960×540 canvas. The page inherits the preceding RK28 visual system: light background, Inter typography, restrained amber status accents, four KPI cards, one audit table, and two concise boundary cards.
- No second append or online page repair was performed. The editing workflow used server XML readback and native-canvas bounds; no screenshot-based visual claim is made.

## Evidence hashes

- Baseline full-deck XML SHA256: `2c08b092c9f2782c869b581306317f68f34cb65af6d68ee613bc6ca5865c7fea`.
- Read back RK29 slide XML SHA256: `9f4ac5800bf71a515fbc1f3ae1a4cd378263389490fe0cb01f589d5ea0458a07`.
- Final full-deck XML SHA256: `500f0e02a4b4efe3692eb4a642e49775dc7ac02f54a193c61304d7d4699bc815`.
- Machine-readable verification: `audits/20261121/RK29/RK29_PPT_VERIFICATION.json`.

Large baseline/write/readback XML and response files are archived under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk29/icodon_decay_cluster_ood_v1/ppt/`.

## Scope

RK27 and RK28 remain unchanged. Functional untouched data were not accessed, expensive generator training was not performed, and the working manuscript was not modified because RK29 generated no new structure-increment scientific result.
