# A8-RK29 — reproduction and test closeout

Date: 2026-11-21
Science HEAD tested: `3f75dc79cab881eb18eb65e10b15e0a5c0345dc8`
Status: **PASS — full project suite plus clean-clone RK29 reproduction**

## 1. Authoritative full project suite

The complete repository suite was run in `/home/codonflow-a8-rk` with the existing validated scientific environment:

```bash
/home/codonflow-clean-env-v1/bin/python -m pytest tests/
```

Result: **423 passed, 1 skipped, 11 warnings in 31.84 s**; exit code 0. The pre-existing skip was not removed or reinterpreted. Log: `reproduction/project_pytest_v1.log`, SHA256 `6f7b75587f8dc464174e6e06c9b2cbeee742577fa620c6700750d6b091c43f1a`.

## 2. Independent clone and clean RK29 environment

A fresh clone at `/home/codonflow-a8-rk29-repro` was fixed to science HEAD `3f75dc79cab881eb18eb65e10b15e0a5c0345dc8`. It had zero dirty files before and after reproduction.

A separate Python 3.10.22 environment, `/home/codonflow-rk29-minimal-env-py310`, was created without system site packages. The project was installed with `--no-deps`; only the dependencies required by the RK29 scripts/tests were installed. The resulting package versions match the validated scientific environment: NumPy 2.2.6, pandas 2.3.3, SciPy 1.15.3, scikit-learn 1.7.2, pytest 9.2.0 and ViennaRNA 2.7.2. Torch is intentionally absent; RK29 performed no model fitting or Torch execution. The pip warning that the no-deps `codonflow` distribution declares Torch is expected and is not presented as a full-project clean installation.

The server `/teams` filesystem rejected venv symlinks (`Errno 38`), so environments and clones remain under `/home`; the wheelhouse and all logs/reports remain under `/teams`. A full dependency install began downloading 554.6 MB of Torch and was deliberately stopped because RK29 does not use Torch. Two slow/stalled online minimal installs were also stopped. Offline attempts v3–v5 exposed missing `exceptiongroup`, `typing-extensions` and `cloudpickle`; those failures are retained rather than rewritten as passes.

The final wheelhouse contains 20 wheels. Its dependency closure was computed recursively from installed distribution metadata, then installed with `--no-index` in v6. Final import validation passed and confirmed no system site packages or Torch. Relevant logs:

- `local_wheelhouse_build_v1.log`, SHA256 `880bc69af3aa8dc325b54b2095c127055b0619bd146d1a22c8ae245c955b3a3e`
- `clean_minimal_offline_install_v6.log`, SHA256 `f11e91bcf421d10240b6e0d06bdf3acdd6a76bee1388f4ca2a35cba4f8d1ea21`

## 3. Clean-clone RK29 checks

From the independent clone and clean environment:

1. `scripts/a8_rk29_test_production.py`: **9/9 tests passed**. Log `clean_rk29_unit_v1.log`, SHA256 `823dd68d09c6ffe8563d457c87f3d60674382bd048519b6fad35b188350b9191`.
2. `scripts/a8_rk29_verify_alignment_failure.py`: independently reparsed S6, GEO CSV and FASTA, rechecked all **10,227/10,227** name–measurement pairs and reproduced the alignment-failure evidence without importing production or coverage modules.
3. Twenty declared scientific/audit fields were compared between the original and clean verification reports: all matched. These include raw hashes, candidate distribution `{1:240, 2:598, 3:117}`, 715 ambiguous S6 rows, 338 ambiguous protein×design groups, the exact global assignment count, representative sequence difference, production-stop hash, and absence of all model outputs.
4. Clean report status: `PASS_INDEPENDENT_ALIGNMENT_FAILURE_VERIFICATION`; `model_fit_or_scientific_result_found=false`, `rk29_result_json_absent=true`.

Clean report: `clean_RK29_ALIGNMENT_VERIFICATION.json`, SHA256 `d6a2e125e5a3f6a79663bff07aab79ad399480de905230ab727157c5b879df05`. Its stdout copy is `clean_independent_verifier_v1.log` with the same SHA256.

## 4. Reproduction boundary

The clean reproduction verifies the RK29 synthetic tests and the independent raw-source alignment-failure audit. It does not turn the stopped RK29 experiment into a fitted scientific result. The full project suite was run separately in the validated full scientific environment, not in the intentionally minimal RK29 environment. No generative training, functional-untouched access, model fitting or RK29 endpoint estimation occurred.

All paths under `reproduction/` in this document are relative to:

`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk29/icodon_decay_cluster_ood_v1/reproduction/`
