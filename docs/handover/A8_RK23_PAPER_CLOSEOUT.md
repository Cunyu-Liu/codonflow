# A8-RK23 working-manuscript closeout

## Integrated revision

- Source manuscript SHA256: `5c9f9619a46ed555777f6bc9e986fc873c7ff5674406d93c19d21979155096b6`.
- Updated manuscript SHA256: `168042d268da301057d9214393c25c05904c6a64d60bbb88ff265fc2cf8755b6`.
- Accepted RK23 section SHA256: `fc02dad4d31ac4f42ad4aca0751c57944cc5af14f1fb1d43bda38c40e05a9125`.
- The source manuscript is preserved outside Git at `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk23/paper_v1/CodonFlow_preprint_A8.before_rk23.md`.
- Exactly two integrations were made: insertion of Section 6.34 before Discussion and insertion of twelve evidence-hash rows. All other manuscript content, including References, is preserved by an exact reconstruction check.

## Writing workflow and verification

The English section workflow used `mode=draft`, `task_scope=section`, `needs_citation=no`, and `output_target=markdown_only`. The internal-results section contains 689 words and passed prepare and write. A separate `make status` process returned PASS with `lark=skipped_by_user`. The deliver recipe generated `paper_final.md` and then emitted the retained `finish_with_status: command not found` shell error with exit code 2. This tooling history is preserved in `deliver_console.log`; no skill script, gate, threshold, or check report was modified. No Feishu document was created or claimed.

Independent manuscript integration verification passed 41/41 checks on the first run. It verified the source and updated hashes, exact two-part reconstruction, section identity, preserved References, all primary and descriptive-secondary numeric anchors, source-data exclusions, independent science acceptance, workflow state, twelve evidence rows, and closed scientific flags.

## Scientific boundary

The revision reports the frozen Boël UH protein-OOD result without changing its negative conclusion. Logistic Spearman and MSE-improvement effects were +0.005341 and +0.000449; HistGB effects were −0.005051 and −0.028460. All four intervals crossed zero, all Holm-adjusted probabilities were 1.000, and 0/4 primary endpoints passed. Development independent acceptance was 177/177 and test independent acceptance was 275/275, with zero production-versus-independent prediction, metric, bootstrap, and permutation differences.

The descriptive simple-feature comparisons remain outside the confirmatory Holm family and cannot reverse the primary result. Optimized-construct prediction quantiles were not used as expression truth, no plotted expression was digitized, and the fixed-protein numerical test was not executed without a numeric expression table. This reused protein-OOD test is not functional untouched confirmation and does not establish fixed-protein synonymous transport, velocity, decay, CodonFlow-RK generation, or external SOTA. RK-G1 remains false, expensive generator training remains unauthorized, and the manuscript remains non-submittable.
