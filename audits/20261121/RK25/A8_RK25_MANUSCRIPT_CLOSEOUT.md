# A8-RK25 — English manuscript closeout

Status: **PASS (draft, Markdown-only); INSERTION-ONLY FULL MANUSCRIPT UPDATE**

The A8 English working manuscript now contains Section 6.36, **“The complete author model outperformed all-channel on sequence-OOD,”** and Table 8. The update records the frozen RK25 comparator result without changing the scientific gates or promoting the manuscript to a submittable final paper.

## 1. Manuscript changes

The update adds one 684-word Results subsection, one native Markdown data table and eight RK25 evidence-anchor rows. It reports the shared RK20 partitions and four seeds, the train-only author refit, the reused all-channel/ridge_all/HistGB predictions, the mean per-seed estimands, 20,000 hierarchical protein-cluster-and-seed bootstrap replicates, and the six-test sequence-OOD Holm family.

The scientific result is preserved exactly: all-channel versus author fails both endpoints; author versus ridge_all and HistGB passes all four endpoints; the strong comparator chain fails; RK-G1 remains false; generator training remains unauthorized. Test remains descriptive and functional untouched data were not read. The text also explains that empirical zero sign-tail values are not literal zero probabilities and that the gate is not a six-endpoint majority vote.

The manuscript remains explicitly **non-submittable**. The section does not claim fixed-protein synonymous causality, velocity, decay, complete spatial coupling, CodonFlow-RK superiority, external SOTA or functional untouched performance.

## 2. Original-manuscript protection

Pre-update manuscript SHA256: `12949c09f3b4707c87bfdd4486d1ad761762a81264d1b9da6a5df9fbef4d6643`.

Updated manuscript SHA256: `46db82d54dcc2e87c4f8bf3a71017b8dd9fe921eb18c337b8e81f96784902578`.

Independent verification removed only the inserted RK25 section and its eight evidence-ledger rows and recovered the pre-update manuscript byte-for-byte. RK24 and all earlier scientific text, numbers, tables, references and boundary statements were not rewritten.

## 3. Writing workflow and retained failures

The task was completed as a single-section append. Two initial attempts to run the entire long working manuscript through the checker were rejected: the `revise` scope required line-level authorization for new numerical content and detected the manuscript's existing nonstandard section dependency; the full-manuscript `section` attempt also exceeded the generic 15,000-word section limit. No existing headings or scientific text were changed to bypass those checks. The actual 684-word section was then checked directly.

Single-section preparation and writing checks passed. The section source and generated `paper_final.md` are byte-identical, with SHA256 `7506392f196deb4d0bf3445742a4b8c07d78b60606125c2f8ba8d462fa76fe24`.

The `make deliver` Markdown-only branch generated the final file but its shell function was out of scope and returned `finish_with_status: command not found`. The complete failure console is retained in `rk25_manuscript_deliver_console_v1.log`; no gate script was edited. A separate `make status` returned **PASS**, stage `deliver`, with `lark = skipped_by_user`. The mode remains `draft`, not a submission-ready final.

The first independent manuscript-verifier run passed 75/76 checks because the verifier expected `does not imply` where the grammatically correct source text says `do not imply`. The failed report is retained as `rk25_manuscript_verification_failed_required_phrase_v1.json`. Only that verifier phrase was corrected; the manuscript and scientific values were unchanged. The rerun passed **76/76 checks**.

## 4. Evidence binding

The independent manuscript report verifies:

- all six frozen effects and both confidence-interval endpoints at six-decimal display precision;
- all sequence-OOD and descriptive test Spearman and cluster-balanced MSE values;
- the independent development 337/337, OOD 678/678 and closeout 89/89 acceptance statements;
- production-versus-independent numerical magnitudes;
- exact false/true/false Gate states and all scope boundaries;
- the frozen protocol, result, predictions, production bootstrap, independent report, independent bootstrap, scientific closeout and manuscript-section hashes;
- writing-workflow preparation, draft and three-state PASS reports.

Key hashes:

- prepare check: `d5db334b575dc178ac4df024ec4dbff3e47fc190dc28a9bf3c3bd1aedf9f3cc8`;
- draft check: `4ed279c6a04e7ac06a6a4796591752550f3295aafcad8e1ecfdf5b5ae5a94ebf`;
- writing status: `03f3d50a3438b29b803777f6e15d837ec97450a22720e0d5619968e861b566d9`;
- manuscript verifier: `866dae4e63537ef84d32e544df03ba178a7e3b2f06d50f14b1089e0570dd9406`;
- final manuscript verification: `0493d4db48e9bd8c2ae9d391a1c65c7931383e8e46550846267675d14498dc3b`.

## 5. Remaining manuscript boundary

This closes the RK25 Results-section update only. The full paper still lacks its final figure set, complete claim–evidence matrix, final strong-baseline synthesis, resolved mechanism result, main CodonFlow-RK evaluation, unified time-matched comparison, full experimental reproduction and prospective validation. Those omissions remain visible; the working manuscript is not represented as a completed preprint.
