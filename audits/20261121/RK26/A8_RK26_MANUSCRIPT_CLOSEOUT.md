# A8-RK26 English working-manuscript closeout

## Scope and scientific boundary

This update records RK26 as draft section 6.37 and Table 9 of `paper/CodonFlow_preprint_A8.md`. It is a 595-word, Markdown-only manuscript-section update with no new references. The section reports a retrospective data-adequacy audit, not a preregistered mechanism experiment. The original 33-construct MAGE mechanism-test set and the RK04 functional-untouched split were not accessed.

The verified sample chain is 8,192 total rows, 2 WT constructs, 252 single-codon variants, 7,938 double-codon variants, 6 fixed-protein synonymous single-codon variants, and 4 fixed-protein synonymous double-codon variants. Pair contexts 1–2 and 2–3 respectively contain 4/3 and 2/1 synonymous singles/doubles. Context 2–3 fails the frozen requirement for at least two synonymous doubles. This is a design-feasibility rule, not a power analysis. No model was fitted, no functional endpoint was evaluated, and no confidence interval or p-value was produced. The audit is not a negative result about positional or structural interaction performance. RK-G1 remains false and generator training remains unauthorized.

## Writing workflow

- `prepare`: PASS; no citation verification was required because no new reference was introduced.
- `write`: PASS; draft mode, section scope, research article, APA7 metadata, 595 words, native Table 9.
- `status`: PASS; `paper_final.md` was generated and Feishu delivery was skipped by the Markdown-only configuration.
- The initial `make deliver` returned code 2 because its shell reported `finish_with_status: command not found` after generating `paper_final.md`. The complete log is retained; the independent `make status` result is PASS. This engineering error is not represented as a successful online-document delivery.
- The first prepare attempt failed because the Makefile could not parse the absolute workflow path containing spaces. A no-space `/tmp` alias to the same working directory was used for the successful retry; both logs are retained.

## Insertion-only manuscript update

- Frozen pre-RK26 manuscript SHA256: `46db82d54dcc2e87c4f8bf3a71017b8dd9fe921eb18c337b8e81f96784902578`.
- Updated working-manuscript SHA256: `91e8bf226225d6d621617128618012b9333086646af9cd315b34be156f130f9a`.
- Section/paper-final SHA256: `de359b8383544347f3a5edf9628a1b1147f4e27df273b08061ddec40a1db57e4`.
- Exactly one section and nine RK26 evidence-ledger rows were inserted. Removing those insertions reconstructs the frozen pre-RK26 manuscript byte-for-byte.
- The frozen pre-RK26 manuscript is preserved at `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk26/manuscript_v1/CodonFlow_preprint_A8.before_rk26.md` with the original hash above.
- The first insertion attempt stopped before writing because an extra blank line prevented exact reconstruction. Only the insertion code was corrected; the manuscript was not modified by that failed attempt. The initial log is retained.

## Independent acceptance and remote reproduction

The independent manuscript verifier checks the section text, every Table 9 value, workflow state, science hashes, evidence-ledger hashes, insertion-only reconstruction, negative boundaries, and zero model/endpoint counts.

- Local acceptance: **57/57 PASS**.
- Remote acceptance before replacing the formal working manuscript: **57/57 PASS**.
- Local and remote verification reports are byte-identical, SHA256 `ef7952e530215c97a345bd3a33cd5f5181cb0e337d93b4cd981d4d76188aa744`.
- Candidate and final working-manuscript SHA256: `91e8bf226225d6d621617128618012b9333086646af9cd315b34be156f130f9a`.
- The first verifier attempt stopped on an incorrect report-field name (`production_result_sha256` instead of `production_report_sha256`). The verifier was corrected without changing the manuscript; its initial traceback is retained.

Canonical code and evidence:

| Artifact | SHA256 |
|---|---|
| `scripts/a8_rk26_update_manuscript.py` | `2e4d6835a73f5ae28cb1a672fc524fad425143362e8b7f7ac62b54397430f865` |
| `scripts/a8_rk26_verify_manuscript.py` | `094fc99f4b2afd95909dd6ccf43fb91224cb06078fdd5a917cf6042301257e4b` |
| `audits/20261121/RK26/rk26_manuscript_section_v1.md` | `de359b8383544347f3a5edf9628a1b1147f4e27df273b08061ddec40a1db57e4` |
| `paper/CodonFlow_preprint_A8.md` | `91e8bf226225d6d621617128618012b9333086646af9cd315b34be156f130f9a` |
| `audits/20261121/RK26/rk26_manuscript_update_v1.json` | `46395df212f79f4de13fbba291edeb32b390aa345b2cac909ded56c5a1f0e610` |
| `audits/20261121/RK26/rk26_manuscript_verification_v1.json` | `ef7952e530215c97a345bd3a33cd5f5181cb0e337d93b4cd981d4d76188aa744` |
| `audits/20261121/RK26/rk26_manuscript_verification_remote_v1.json` | `ef7952e530215c97a345bd3a33cd5f5181cb0e337d93b4cd981d4d76188aa744` |
| `audits/20261121/RK26/rk26_manuscript_prepare_check_v1.json` | `14af12ea04778f7848d230b1a06ec1b423004ce81e0b0ed1ad7246592a324e2d` |
| `audits/20261121/RK26/rk26_manuscript_draft_check_v1.json` | `da521151b9ac06ee88f40f221d3c79552b8a5bd7864de91093efb8966a30510a` |
| `audits/20261121/RK26/rk26_manuscript_status_v1.json` | `03f3d50a3438b29b803777f6e15d837ec97450a22720e0d5619968e861b566d9` |
| `audits/20261121/RK26/rk26_manuscript_deliver_console_v1.log` | `5b5b456ae8ab0556d1b672fbe8a4aca366a74bc8bf8a721131bbc2768806d4d6` |

## Remaining manuscript status

This remains a **non-submittable working manuscript**. The RK26 update does not supply the missing main figures, complete claim–evidence matrix, final strong-baseline main table, main CodonFlow-RK model, unified time-matched comparison, functional-untouched evaluation, or prospective validation. No new PPT page was added during manuscript integration; the independently verified RK26 PPT page remains the record closed by commit `e7cc88ad1c53f01b8b03b0dde0bba7f576f0e8e5`.

The manuscript artifacts, this closeout, and the RK26-PAPER registry row are committed together. A separate post-commit binder records the resulting manuscript commit without altering the verified manuscript or this closeout.
