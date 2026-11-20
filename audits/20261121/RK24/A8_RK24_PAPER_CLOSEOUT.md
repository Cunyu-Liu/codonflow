# A8-RK24 working-manuscript closeout

## Integrated revision

- Source manuscript SHA256: `168042d268da301057d9214393c25c05904c6a64d60bbb88ff265fc2cf8755b6`.
- Updated manuscript SHA256: `12949c09f3b4707c87bfdd4486d1ad761762a81264d1b9da6a5df9fbef4d6643`.
- Accepted RK24 section SHA256: `f23926a336ecc1502e622e228a3cbf7b04577cb757c63e5695afb69a1505a2bd`.
- Update report SHA256: `7abb1b4362c6da98b804bf59aec681c9b083a828dee6560083e60440e32ebdbd`.
- Independent verification report SHA256: `9018f7287d09f0d4670438ad48b29732abc72c12afa8e1d3c8e0733965c0c774`.
- The source manuscript is preserved outside Git at `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk24/paper_v1/CodonFlow_preprint_A8.before_rk24.md`.
- Exactly two integrations were made: insertion of Section 6.35 before Discussion and insertion of sixteen evidence-hash rows. Exact reconstruction confirmed that all other manuscript content, including Section 6.34 and References, is preserved.

## Writing workflow and verification

The English section workflow used `mode=draft`, `task_scope=section`, `needs_citation=no`, and `output_target=markdown_only`. The internal-results section contains 699 words and passed prepare and write. A separate status process returned PASS with `lark=skipped_by_user`; `paper_final.md` is identical to the accepted section. No Feishu manuscript was created or claimed.

The first writing check stopped before draft validation because the isolated skill copy lacked `revision_guard`. The unchanged dependency was restored from the sibling `paper-shape` package without modifying any checker, threshold, or report. The captured failure is retained in `rk24_write_console_failed_missing_revision_guard.log`. The deliver recipe generated `paper_final.md` and then emitted the known `finish_with_status: command not found` shell error with exit code 2; the complete console is retained in `rk24_deliver_console.log`.

Independent manuscript integration verification passed 58/58 checks on the first run. It verified the source and updated hashes, exact two-part reconstruction, section identity, preserved RK23 section and References, all primary numeric anchors, descriptive HistGB anchors, independent science acceptance, workflow state, sixteen evidence rows, and closed scientific flags.

## Scientific boundary

The revision reports the frozen train-only Boël author-structure baseline without changing its limited-scope conclusion. On test, binary AUC increased by 0.187323, binary log loss improved by 0.130941, multiclass Spearman increased by 0.302011, and multiclass MSE improved by 0.771838. All four confidence intervals excluded zero, all rounded Holm-adjusted probabilities were 0.000200, and 4/4 primary endpoints passed. Development independent acceptance was 97/97 and test independent acceptance was 153/153.

The author model is a stronger reference for subsequent CodonFlow comparisons, not evidence that CodonFlow-RK has outperformed it. The HistGB comparison remains descriptive and outside the confirmatory endpoint family. This cross-protein, nonsynonymous ordinal-expression comparison does not establish fixed-protein synonymous causality, translation velocity, mRNA decay, the complete spatial-coupling mechanism, external SOTA, or functional untouched performance. RK-G1 remains false, expensive generator training remains unauthorized, functional untouched data were not accessed, and the manuscript remains non-submittable.
