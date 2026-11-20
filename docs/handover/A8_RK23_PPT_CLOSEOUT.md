# A8-RK23 — online PPT closeout

Status: **PASS_RK23_ONLINE_REPORTING**

- Presentation: `https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g`
- Before: **114 slides**, revision **77**, last slide `pZl`
- After: **115 slides**, revision **78**, appended slide `pZN`
- Scientific decision shown: **0/4 primary endpoints PASS; protein-OOD UH increment not supported**
- Independent scientific acceptance shown: **275/275**
- Candidate acceptance: **62/62**; online readback acceptance: **73/73**
- All first 114 pages and their notes were semantically preserved; the new page's visible text and notes exactly match the accepted candidate.

## Reporting content

The appended page reports the frozen 634-construct/556-protein-cluster test, both models' Spearman and MSE primary effects with 95% intervals, all four Holm-adjusted p values of 1.0, and the independent 275/275 reproduction. It explicitly labels the simple-only contrast as descriptive rather than confirmatory. It keeps RK-G1 false, generator training unauthorized and functional untouched unread; it makes no velocity, decay, CodonFlow-RK or SOTA claim.

## Retained verification corrections

1. The first candidate failed 7/62 checks because MSE effect intervals were not directly visible and full-precision base/augmented MSE values were absent from the notes. The candidate was corrected; the failed XML and 55/62 report are retained. Final candidate acceptance is 62/62.
2. The first online report failed 2/73 checks because the service merged two adjacent equal-width `140` columns into one `span=2` column. Weighted table width remains 864, all text and notes are unchanged, and all old pages are preserved. The verifier was corrected to canonicalize this equivalent server representation and to compute width using column spans. No page edit or second append was performed. The initial 71/73 report is retained; final online acceptance is 73/73.

## Evidence hashes

- Accepted candidate XML SHA256: `5c5f68e3b06a5b2c90f49161070bab661f97029ed2cb3138e064889f4c072489`
- Pre-append 114-page XML SHA256: `d1244b8b64b6af70a4667c4e7843f9380951b4106ebaaa65b6f85ce353cb3e6e`
- Post-write 115-page XML SHA256: `acabea9986eeede5949f023d216731afeb2badf99252a9bc4323371ce1582b5e`
- Add response SHA256: `14b45ca99359d55d29d98ba0570a415cd59ce50b4765ec438dfbcaeedf5d154b`
- Final candidate report SHA256: `1e4f26ac3504e88b61e30e8b64ad192e055ef461b4e13c16f56897e47891ead1`
- Final online report SHA256: `92ea720d2b0851abc127ecb2482efc2458ac20dbc1417d48d98ccce674157559`

Large before/after XML, content/summary inspections, candidates and responses are archived under:

`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk23/ppt_v1/`

The independent slide verifier is `scripts/a8_rk23_verify_ppt.py`. Small final and retained-failure reports are under `audits/20261121/RK23/`.
