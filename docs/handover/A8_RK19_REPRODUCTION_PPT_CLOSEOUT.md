# A8-RK19 CPU Reproduction PPT Closeout

## Outcome

- Online deck: `https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g`
- Presentation ID: `WB1KsYGualerMUddEzMcCw1En0g`
- Added page: **110**, slide ID `pZi`, revision **72**.
- Title: **Fresh clean prefix reproduces the full CPU suite**.
- Scientific-evidence parent commit: `1368c5443ef11916fc9ec417d7dfb9052ce9ea32`.
- This PPT closeout is introduced by the Git commit containing this file; verify that commit and remote `a8-rk` HEAD after push.

## Evidence-bound result shown on the page

| Environment | CPU-suite result | Independent acceptance |
|---|---|---|
| Repaired existing environment | 331 collected; 330 passed; 1 skipped; 0 failed; 0 errors; 27.12 s | 15/15 PASS |
| Fresh clean prefix `/home/codonflow-rk19-clean-explicit-v2` | 331 collected; 330 passed; 1 skipped; 0 failed; 0 errors; 15.91 s | 24/24 PASS, repeated postpush |

The clean prefix used Python 3.10.22, torch 2.11.0+cu128, transformers 4.46.3, numpy 2.2.6, scipy 1.15.3, pandas 2.2.2, scikit-learn 1.7.2, pytest 9.1.1, ViennaRNA 2.7.2, pymoo 0.6.2 and RapidFuzz 3.14.5. It is a fresh reproduction within declared compatible ranges, not an exact package copy of the repaired environment's torch 2.14.1+cu132 / transformers 5.20.2 stack.

The sole skip was the explicit opt-in isolated tmux integration test. No opt-in tmux/GPU integration was executed. Both JUnit files contained 331 testcase elements but had a `tests=336` header; the five-count metadata discrepancy remains disclosed. Acceptance relies on the console summary and independently enumerated testcase elements.

## Candidate and online verification

- Unit tests: **3/3 PASS**.
- Builder preflight: **54/54 PASS**, `PASS_RK19_REPRODUCTION_PPT_CANDIDATE`.
- Independent candidate verification: **56/56 PASS**.
- Full online postwrite verification: **175/175 PASS**.
- The 109 pre-existing pages retained their page IDs and full XML semantic signatures, including body, notes, geometry and other XML attributes.
- The new page's visible paragraphs and five speaker-note paragraphs matched the accepted candidate exactly.
- Marker `RK19 · CPU REPRODUCTION` occurred only on page 110.
- No external image, embed, undefined object, preassigned element ID or emoji was introduced.

## Immutable hashes

- Baseline 109-page XML, revision 71: `54b100dd697c4baddc688a1b62609123a7a567737c40f3241b1d8926fd116b44`
- Accepted candidate XML: `9c949e5a281e34a25acdcf8ce05b75de7a61a01ad7c33091c32a63422b069c3d`
- Postwrite 110-page XML, revision 72: `0a62d4b1dfc2027cfae0b06985b04245dd5d9515b0e132cb9752bd468b9bf35a`
- Candidate report: `2b2d63fafb3144a386175ebaf41bb89082ca498e820945092f366d51c3715298`
- Independent candidate verification: `8156d8ec5925091765a36e7ac8fbcebbe51f335bd8b2d5d83e7c267cfd87ba46`
- Postwrite verification: `c7fbd240c0c3fdce2ff6e9be55ac87d90785cb1600742186a79f4cc518029ec3`
- Existing-environment report: `87dc09dc989b5200c1bdb3538ede9111fa79f3b2742be9dc7733846572392351`
- Clean-environment report: `1519bb89f528d1f04801fdf945900c3d9f8c22fa2766c80b426f6428a798ca6f`
- Clean-suite console: `d9dc2e421d759d3c4d4ba94cbfcefb27c1c72c8e74ef047bb3f4e18be9665d97`
- Manuscript source section: `3ffedb2efbf99754d1f5acfd8ea7c79498a45edb3752b8565487413a6c0ec6c9`

## Preserved failures and corrections

1. Candidate v1 was not written: local geometric preflight rejected a 14 px overlap between the two header text boxes. The left header width was reduced, and v2 passed all checks.
2. The first standalone verifier invocation used a script path and failed with `ModuleNotFoundError: No module named 'scripts'`; rerunning it as `python3 -m scripts.a8_rk19_verify_reproduction_ppt` resolved the import-path issue without changing evidence or XML.
3. These engineering failures are retained in the large-artifact audit directory. No failed candidate was submitted to the online deck.

## Scope and scientific boundary

This page records repaired-existing and fresh-clean **CPU test-suite reproduction only**. Full experimental artifact regeneration remains false. RK-G1 remains false; functional untouched data were not evaluated; generator training remains unauthorized; external-SOTA authorization remains false; the manuscript remains a non-submittable working draft. No causal mechanism, functional improvement, protein-OOD success or generation-readiness claim is made.

## Reproduction locations

- Code and committed reports: `/home/codonflow-a8-rk`
- Large XML snapshots, CLI responses, logs and immutable evidence: `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk19/reproduction_ppt_20261120_v1/`
- Builder: `scripts/a8_rk19_make_reproduction_ppt.py`
- Independent verifier: `scripts/a8_rk19_verify_reproduction_ppt.py`
- Unit tests: `tests/test_a8_rk19_reproduction_ppt.py`

Validation used complete XML readback and semantic comparison. No server-side screenshot inspection is claimed.
