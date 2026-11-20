# A8-RK26 — Online PPT closeout

Status: **PASS; ONE APPEND; 118 PAGES; OLD PAGES PRESERVED**

Online deck: https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g

Scientific evidence commit: `6c142514701188efc7cdf79dd99eaf637685434c`

Scientific closeout/registry commit: `09338fb1fb834c72550ad509db2a4692daa97969`

## 1. Scope and source state

The task appended one RK26 data-adequacy page to the existing research deck after the frozen feasibility result had passed independent scientific verification and closeout evidence binding. No earlier page was edited, repaired, moved or deleted.

- Source: **117 pages**, revision **80**, final page `pZX` (RK25).
- Candidate: one native 960 × 540 slide with Inter typography, a native 4 × 8 table, four KPI cards, two conclusion cards and five speaker-note paragraphs.
- Science inputs: `rk26_pair_feasibility_result_v1.json`, its 42/42 independent report and the 54/54 closeout verification; no model was fitted and no functional endpoint was evaluated.

## 2. Recorded scientific content

The page title is **“Only 4 synonymous doubles: interaction OOD is not supported.”** It records:

- 8,192 pair-assay constructs, reconstructed into 2 WT controls, 252 single-codon variants and 7,938 codon-pair variants;
- fixed-protein coverage of 6 synonymous singles and 4 synonymous doubles;
- pair 1–2: WT `GCC;AAA`, 4 synonymous singles and 3 synonymous doubles, coverage PASS;
- pair 2–3: WT `AAA;GAA`, 2 synonymous singles and 1 synonymous double, coverage FAIL;
- the candidate confirmatory single-to-double synonymous OOD design is not supported by sample coverage;
- 0 model fits, 0 endpoint evaluations, 0 confidence intervals or p-values;
- retrospective coverage audit only, not a power analysis or mechanism result;
- original MAGE 33-construct mechanism test and RK04 functional-untouched split unread;
- `RK-G1 = false`, generator training unauthorized, and independent acceptance 42/42 plus closeout binding 54/54.

The speaker notes retain the raw/clean source hashes, sequence-only fact hash, production and independent evidence hashes, the full scientific outcome and the complete claim boundary.

## 3. Candidate and online verification

Candidate verification passed **88/88 checks**, including:

- source response `ok = true`, 117 pages, revision 80 and no pre-existing RK26 title;
- the full 4 × 8 table matched the frozen science result, including both pair contexts and the total row;
- raw/clean hashes, fact/result/independent hashes and science/closeout commits;
- native table shape, five notes, Inter fonts, minimum visible font size, canvas bounds and absence of invented IDs or external images;
- exact feasibility, zero-fit, untouched-split, RK-G1 and generator-boundary text.

One `slides +add-slide --no-lint` request returned `ok = true`:

- new page ID: **`pZL`**;
- new revision: **81**;
- final page count: **118**.

Complete post-write XML readback passed **217/217 checks**, including:

- exactly one page and one revision increment;
- new page `pZL` is the final page and the only page containing the RK26 title;
- all first 117 page IDs remain in the same order;
- every one of the first 117 pages is semantically identical before and after the append;
- new-page visible paragraphs, speaker notes, direct-element geometry and native table dimensions match the candidate;
- the online table matches the frozen science matrix after XML indentation whitespace is excluded.

The first readback report was retained as 216/217 because the verifier included server pretty-print indentation in table-cell text. Only the verifier's whitespace normalization was corrected; the online page was not edited and no second append was performed. The final local and remote reports are byte-identical.

## 4. Evidence files

Small evidence files are stored in `audits/20261121/RK26/`:

- `rk26_slide_candidate_v01.xml`, SHA256 `52b9794c6f1a691cef24423bf0da57a8da7f071025460bdf6ac103473f46dba9`;
- `rk26_ppt_candidate_verification_v01.json`, SHA256 `1f28c6538fab1b57d966aa76ee9a87655517074927cbc27d41dc392467a786fa`;
- `rk26_ppt_online_verification_v01.json`, SHA256 `d860a87b868d98279db869db111b23abdad2b7162cd5661e32dcd60c0d4e6bea`;
- `rk26_ppt_write_response_v01.json`, SHA256 `147acda8e0f09cb211e8f4e8febac10d8d2fe90f9c0eb04ab809afaf8d9a342c`;
- candidate/online console logs, the retained initial 216/217 report and the remote verification console;
- source, write and post-write response JSON files.

The verifier is `scripts/a8_rk26_verify_ppt.py`, SHA256 `815e8c6499fcecfed9c262bd9210d6d0c5b38b1d4121d1517e956844d689f89d`.

Full pre-write XML is stored under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk26/ppt_v1/`, SHA256 `2e72d73c2acc532bf8adae9e4ea648fb21316ab26b5f82913c2c13af284c821b`.

Full post-write XML is stored in the same directory, SHA256 `322dc0e7f8c64c776b0dccdbac9c40368333f6c1a157c5c6a151a66df37e1e9b`.

Remote candidate and online reruns both passed 88/88 and 217/217; their reports are byte-identical to the canonical small evidence files.

## 5. Delivery boundary

The online deck now records the verified RK26 feasibility result, but the scientific conclusion remains limited: the MAGE pair assay does not contain enough fixed-protein synonymous single and double variants for the proposed confirmatory interaction-OOD comparison. This is not a negative mechanism-performance result, functional-untouched confirmation, CodonFlow-RK superiority, external SOTA, a time-matched result or generator authorization. RK-G1 remains false.
