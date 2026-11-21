# RK39 isolated English-section workflow

- Scope: Results §6.50 only; no external literature or new scientific claims.
- Inputs: frozen RK39 protocol, independently verified production report, and 830/830 clean-reproduction closeout.
- Final source: `paper_final.md`; 638 words; native Markdown Tables 32–33.
- Gates: prepare PASS; write PASS with zero failures and zero warnings; Markdown-only deliver PASS in `status.log`.
- Retained correction: the first isolated `make write` stopped because the copied workflow lacked the shared `revision_guard.py` dependency. The unmodified dependency was restored from `paper-shape`; no gate was bypassed and no scientific content changed.
- Full tooling and workflow state: `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk39/manuscript_workflow_tooling_v1/`.
- Delivery boundary: this workflow validates an isolated manuscript section, not the submittability of the full working manuscript.
