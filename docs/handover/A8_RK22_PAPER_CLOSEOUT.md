# A8-RK22 working-manuscript closeout

## Integrated revision

- Source manuscript SHA256: `fe92cf4390f9cb79281002f094ca54a6cf79672895d362f4b4d1835c7d18338e`.
- Updated manuscript SHA256: `5c9f9619a46ed555777f6bc9e986fc873c7ff5674406d93c19d21979155096b6`.
- Accepted RK21/RK22 section SHA256: `43abd8934c992126adbde24735c12d6df2dd3a85e758e41de79eeed626a1ee1a`.
- The source manuscript is preserved outside Git at `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk22/paper_v1/CodonFlow_preprint_A8.before_rk22.md`.
- Exactly three integrations were made: replacement of the obsolete Kudla-unavailability paragraph, insertion of Sections 6.32 and 6.33 before Discussion, and insertion of ten evidence-hash rows. All other manuscript content, including References, is preserved by an exact reconstruction check.

## Writing workflow and verification

The English section workflow used `mode=draft`, `task_scope=section`, `needs_citation=no`, and `output_target=markdown_only`. The internal-results section contains 698 words and passed prepare and write. `make status` returned PASS with `lark=skipped_by_user`. The deliver recipe generated `paper_final.md` and then emitted a shell `finish_with_status: command not found` error; this tooling history is retained here and was not hidden. A separate `make status` process supplied the authoritative PASS state. No skill script, gate, threshold, or report was modified.

Independent manuscript integration verification passed 43/43 checks. The first verifier run failed two checks only because it compared an ASCII minus against the manuscript's Unicode minus and searched for a sentence fragment spanning different wording. The verifier alone was corrected to normalize Unicode minus signs and match the actual retained negative-result clause. The manuscript, scientific values, source backup, section source, and update report were not changed by that correction.

## Scientific boundary

The revision reports the RK21 recovery and RK22 fixed-GFP development results, including all preregistered endpoints, confidence intervals, multiplicity-adjusted probabilities, the tagged-pair analysis, 69/69 recovery acceptance, 63/63 science acceptance, and the retained verifier history. It does not claim protein OOD, velocity, decay, functional untouched performance, CodonFlow-RK superiority, external SOTA, or a sole causal MFE mediator. RK-G1 remains false, expensive generator training remains unauthorized, and the manuscript remains non-submittable.
