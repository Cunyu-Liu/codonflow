# A8-RK25 — Online PPT closeout

Status: **PASS; ONE APPEND; 117 PAGES; OLD PAGES PRESERVED**

Online deck: https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g

Scientific evidence commit: `44014ad0fc923fba65d52fcda953117d9c822051`

Scientific closeout commit: `38ecaf7a222f5ce74ceba16f29f3043071bf5d9e`

## 1. Scope and source state

The task appended one RK25 result page to the existing research deck after the frozen sequence-OOD result had passed independent scientific verification. No earlier page was edited, repaired, moved or deleted.

- Source: **116 pages**, revision **79**, final page `pZt` (RK24).
- Candidate: one native 960 × 540 slide with Inter typography, a native 4 × 6 table, four KPI cards, two conclusion cards and five speaker-note paragraphs.
- Science inputs: `rk25_ood_result_v1.json` and its 678/678 independent OOD report; no model was rerun and functional untouched data were not accessed.

## 2. Recorded scientific content

The page title is **“Author model wins; all-channel mechanism increment fails.”** It records:

- 1,336 sequence-OOD constructs, four seeds and 20,000 hierarchical protein-cluster + seed bootstrap replicates;
- all-channel − author Spearman `−0.21812`, 95% CI `[−0.27227, −0.16334]`;
- all-channel − author cluster-balanced MSE `+0.73061`, 95% CI `[0.53414, 0.92588]`;
- mechanism component **0/2 FAIL**;
- author versus ridge_all and HistGB **4/4 PASS**;
- strong comparator chain failure, `RK-G1 = false` and generator training unauthorized;
- test descriptive only, functional untouched unread, and no velocity, decay, spatial-coupling or generator claim;
- independent OOD acceptance **678/678** and development acceptance **337/337**.

The page does not present the result as a 4/6 majority-vote success. The speaker notes retain full-precision effects, intervals, the empirical-zero p-value explanation and the complete evidence boundary.

## 3. Candidate and online verification

Candidate verification passed **90/90 checks**, including:

- source response `ok = true`, 116 pages, revision 79 and no pre-existing RK25 title;
- all six confirmatory effects and interval endpoints matched to the frozen OOD result at the displayed precision;
- absolute model Spearman values and author cluster-balanced MSE;
- native table shape, five notes, Inter fonts, minimum visible font size, canvas bounds and absence of invented IDs or external images;
- exact Gate, independent-acceptance, evidence-commit and scope-boundary text.

One `slides +add-slide --no-lint` request returned `ok = true`:

- new page ID: **`pZX`**;
- new revision: **80**;
- final page count: **117**.

Complete post-write XML readback passed **238/238 checks**, including:

- exactly one page and one revision increment;
- new page `pZX` is the final page and the only page containing the RK25 title;
- all first 116 page IDs remain in the same order;
- every one of the first 116 pages is semantically identical before and after the append;
- new-page visible paragraphs, speaker notes, direct-element geometry and native table dimensions match the candidate;
- all scientific numbers and boundary statements remain present after server normalization.

No second append or online page repair was performed.

## 4. Evidence files

Small evidence files are stored in `audits/20261121/RK25/`:

- `rk25_slide_candidate_v01.xml`, SHA256 `e8429805983f76d92ffa8a9f223a80aac8bc6b5a9152a2582bad17a13e57884b`;
- `rk25_ppt_candidate_verification_v01.json`, SHA256 `0112dca279cc78eac8ed530e882c3560ddf6ac963dd0c3e84671a1d2181619d0`;
- `rk25_ppt_online_verification_v01.json`, SHA256 `458744828ad3a5f29dfba6caf6545a72470fb56508e5d117b22ea26cd3059648`;
- `rk25_add_slide_response_v01.json`, SHA256 `140da67d35b5eeda5e539ab6e75248fbea31979c7b604b7d3cfdad809adb951e`;
- source and online response JSON files.

The verifier is `scripts/a8_rk25_verify_ppt.py`, SHA256 `128218a108be41eecb63b4902609aeb554cc4cc6f90cb9af55b64653b9a2c0b2`.

Full pre-write XML SHA256: `949d2f9bb9fe2ef2397cf8c85ce9167adad70604aa375a98dcb662b57a3a0ec9`.

Full post-write XML SHA256: `2e72d73c2acc532bf8adae9e4ea648fb21316ab26b5f82913c2c13af284c821b`.

## 5. Delivery boundary

The online deck now records the verified RK25 result, but the scientific conclusion remains limited: the author model beats ridge_all and HistGB on this sequence-OOD benchmark; all-channel does not beat the author model; the strong comparator chain fails; RK-G1 remains false. This page is not functional-untouched confirmation, CodonFlow-RK superiority, external SOTA, a time-matched result or generator authorization.
