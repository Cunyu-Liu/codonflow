# A8-RK24 — online PPT closeout

Status: **PASS_RK24_ONLINE_REPORTING**

- Presentation: `https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g`
- Before: **115 slides**, revision **78**, last slide `pZN`
- After: **116 slides**, revision **79**, appended slide `pZt`
- Scientific decision shown: **4/4 primary endpoints PASS; limited-scope author-model superiority supported**
- Independent scientific acceptance shown: **153/153 test checks**; development acceptance remains **97/97**
- Candidate acceptance: **72/72**; online readback acceptance: **83/83**
- All first 115 pages and their notes were semantically preserved; all old page IDs were unchanged. The new page's visible text and notes exactly match the accepted candidate.
- One append operation was performed. No online page repair or second append was needed.

## Reporting content

The appended page reports the frozen 634-construct/556-protein-cluster test, binary AUC and log-loss effects, multiclass Spearman and MSE effects, all four 95% protein-cluster bootstrap intervals and Holm-adjusted p values. It also reports the frozen HistGB + UH comparison as descriptive only, the independent test reproduction and the exact evidence/closeout commits.

The page explicitly limits the conclusion to the cross-protein, non-synonymous ordinal-expression comparison. It keeps RK-G1 false, generator training unauthorized and functional untouched unread; it makes no fixed-protein causal, velocity, decay, CodonFlow-RK or external-SOTA claim.

## Evidence hashes

- Accepted candidate XML SHA256: `4bdf5ca664e0a1a3c98aad0f1da3043cd37f7633003d219a9ab46c5c1e9377c3`
- Slide verifier SHA256: `6fbe3a379b39840d3655053c346a3394763ef75a1853fd9eed4395e0ba1c00d7`
- Pre-append 115-page XML SHA256: `acabea9986eeede5949f023d216731afeb2badf99252a9bc4323371ce1582b5e`
- Post-write 116-page XML SHA256: `949d2f9bb9fe2ef2397cf8c85ce9167adad70604aa375a98dcb662b57a3a0ec9`
- Add response SHA256: `8b98c6d50d76494346393f7ebde3facbfcbba0a0888682c1dc9fb304c8ff104f`
- Final candidate report SHA256: `a4b74bf06a5ee4b9feea478a664896dee5a5633da32afbcf3564935f342ed80c`
- Final online report SHA256: `e6f02c3e5ff5f9aa58a52120418cc8223932fcf8182e1c7c8ee8638256e2fe72`

Large before/after XML and complete readback responses are archived under:

`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk24/ppt_v1/`

The independent slide verifier is `scripts/a8_rk24_verify_ppt.py`. The accepted candidate, small reports and add response are under `audits/20261121/RK24/`.

Frozen test evidence commit: `b4c04d2935015386603a5dff8b1f8c9247295b5a`.

Scientific closeout commit: `a35097243e9b0f2b71786479bd981488ac3ed526`.
