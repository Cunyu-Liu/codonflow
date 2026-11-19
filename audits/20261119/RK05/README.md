# A8-RK05 RiboMIMO cross-study OOD evidence

## Frozen scope

- Official RiboMIMO commit: `094c693d4df45f4b29f5a3209b31c452a39092a5`; frozen code commit: `5c85e5847dbad0300f2d967dd769b7cce00c2ad3`.
- Protocol SHA256: `99f7dd5c80044d04d97f64c24dca28a764c2df7ecac013375d44b5bb86fa46e5`; driver SHA256: `556172d7f7f84393a16b74dd0ac3eea238edaeeb98ea30bd0b84882bef1112ad`.
- Mohammad16 source: 1,179 eligible, split into 1,062 train / 117 validation; Subtelny14 target: 3,921. Exact CDS overlap=0.
- Primary seed=1234; sensitivity seeds=2345/3456. Ridge alpha was selected only on source validation and was 100 for every seed.
- Target evaluation occurred only after training, early stopping and source-only ridge selection. Subtelny14 is not globally untouched because earlier RiboKinetic/ridge analyses used it.

## Training and target results

| Seed | Best/last epoch | Alpha | RiboMIMO TB-MSE | Ridge TB-MSE | Constant TB-MSE | RiboMIMO mean r | Ridge mean r |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1234 | 10/15 | 100 | 2.186608 | 1.006967 | 0.966916 | -0.001008 | 0.037500 |
| 2345 | 10/15 | 100 | 2.074145 | 1.006788 | 0.966910 | 0.004477 | 0.037489 |
| 3456 | 13/18 | 100 | 2.040441 | 1.005552 | 0.966907 | 0.011053 | 0.038321 |

Primary TB-MSE delta (RiboMIMO-ridge)=1.179641679102, 95% CI=[1.162686548692, 1.196288203749], sign-flip p=0.000499750125, Holm p=0.000999500250. Primary mean-transcript-Pearson delta=-0.038507716462, 95% CI=[-0.041406161945, -0.035536052126], sign-flip p=0.000499750125, Holm p=0.000999500250.

**Result:** ridge significantly outperformed RiboMIMO on both frozen primary endpoints in this direction and setup. The constant baseline also had lower TB-MSE than both learned models for every seed; ridge's relative win is not strong absolute transfer. This is an occupancy-derived study-OOD result, not physical velocity, functional/homology/protein OOD, RK-G1 closure, generator authorization or SOTA.

## Verification

- Unit tests: 10/10 PASS (`ribomimo_study_ood_unit_tests_v1.json`).
- Production: three complete runs (`ribomimo_study_ood_production_v1.json`).
- Independent retrain: three complete runs in separate directories (`ribomimo_study_ood_independent_retrain_v1.json`).
- Independent raw-data/statistical verification: 203/203 PASS; model/ridge independent/ridge raw-refit maximum differences=0/1.51e-07/1.51e-07.
- Finalization: 30/30 PASS (`ribomimo_study_ood_finalization_v1.json`).
- Training record: `ribomimo_study_ood_training_record_v1.json` and `.md`; full per-epoch histories and official logs are retained.
- Manuscript: A8 v25, still non-submittable; paper verification 44/44 PASS and candidate facts 20/20 PASS.
- Online PPT: candidate facts 33/33 PASS; page 101 (`pgI`), revision 63; full readback 206/206 PASS with all 100 prior slides semantically unchanged. The six strict XML differences are only declared server defaults (five table-column `span=1` attributes and speaker-note body style removal).
- Shared-GPU timings are observed wall times only, not unified single-worker/time-matched cost evidence.

## Reproduction

```bash
cd /home/codonflow-a8-rk
PY=/root/miniconda3/envs/llr_env/bin/python
$PY scripts/a8_rk05_ribomimo_study_ood.py \
  --protocol configs/a8_rk05_ribomimo_study_ood_protocol_v1.json \
  --output-dir /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/production \
  --report audits/20261119/RK05/ribomimo_study_ood_production_v1.json
$PY scripts/a8_rk05_ribomimo_study_ood.py \
  --protocol configs/a8_rk05_ribomimo_study_ood_protocol_v1.json \
  --output-dir /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/independent \
  --report audits/20261119/RK05/ribomimo_study_ood_independent_retrain_v1.json
$PY scripts/a8_rk05_verify_ribomimo_study_ood.py \
  --protocol configs/a8_rk05_ribomimo_study_ood_protocol_v1.json \
  --production-report audits/20261119/RK05/ribomimo_study_ood_production_v1.json \
  --independent-report audits/20261119/RK05/ribomimo_study_ood_independent_retrain_v1.json \
  --driver scripts/a8_rk05_ribomimo_study_ood.py \
  --output audits/20261119/RK05/ribomimo_study_ood_independent_v1.json
```

The finalizer binds protocol/driver hashes, the frozen Git commit, both production reports, independent raw-data/statistical checks, both consoles, unit tests and target-prediction hashes. Large matrices, runtimes, checkpoints and predictions remain under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/`; code and small reports remain under `/home/codonflow-a8-rk`.

## Retained engineering failure

The first verifier invocation used unsupported CLI arguments and exited before training or verification; its log is retained at `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/independent.console.log`. A later verifier implementation failed on an undefined parameter-count variable before producing a verification report; that log is retained at `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/independent_verify_nameerror.console.log`. A subsequent raw-data verifier pass completed 200/203 checks but incorrectly required bit-exact raw ridge refitting; its log is retained at `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/independent_verify_raw_exact_failure.console.log` and its failed report is preserved as `audits/20261119/RK05/ribomimo_study_ood_independent_raw_exact_failure_v1.json`. The corrected verifier resolves official-runner relative paths, checks checkpoint parameter tensors directly, requires exact model/checkpoint reproduction, and applies a declared 1e-6 absolute numerical tolerance to both independent and raw-refit ridge predictions because separate LSQR/BLAS runs differ in floating-point reductions (observed maximum 1.51e-7). Record identity, offsets, positions and targets remain exact; all scientific metrics and primary inference are independently recomputed. No scientific output was overwritten by these failed invocations, and the tolerance is an engineering reproducibility criterion rather than a target-dependent scientific threshold.

## Open gates

This result does not close RK-G0/G1/G2/G3/G4, functional untouched evaluation, homology/protein OOD, physical-velocity assays, full velocity baseline coverage, dense-budget generation, time-matched costs, predictive/generative ablations, wet-lab validation or manuscript submittability. PPT evidence is appended only after this finalized result has passed review.
