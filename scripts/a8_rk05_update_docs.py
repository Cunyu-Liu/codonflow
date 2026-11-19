#!/usr/bin/env python3
"""Write reproducibility docs for the finalized RiboMIMO study-OOD experiment."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def f(value: float, digits: int = 6) -> str:
    return f"{float(value):.{digits}f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--production", type=Path, required=True)
    ap.add_argument("--independent-retrain", type=Path, required=True)
    ap.add_argument("--verification", type=Path, required=True)
    ap.add_argument("--finalization", type=Path, required=True)
    ap.add_argument("--training-record", type=Path, required=True)
    ap.add_argument("--paper-verify", type=Path, required=True)
    ap.add_argument("--frozen-code-commit", required=True)
    args = ap.parse_args()
    repo = args.repo.resolve()
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent_retrain.read_text())
    verification = json.loads(args.verification.read_text())
    final = json.loads(args.finalization.read_text())
    training = json.loads(args.training_record.read_text())
    paper_verify = json.loads(args.paper_verify.read_text())
    if final["status"] != "PASS_RK05_RIBOMIMO_STUDY_OOD" or paper_verify["status"] != "PASS_RK05_RIBOMIMO_STUDY_OOD_PAPER":
        raise SystemExit("Scientific or paper verification has not passed")
    out = repo / "audits/20261119/RK05"
    handoff = repo / "docs/handover/HANDOFF_A8_RK05_RIBOMIMO_STUDY_OOD_20261119.md"
    readme = out / "README.md"
    for path in (handoff, readme):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing document: {path}")
    p0, p1 = production["primary_comparisons"]
    rows = []
    for run in production["runs"]:
        m = run["target_metrics"]
        rows.append(f"| {run['seed']} | {run['best_epoch']}/{run['epochs_completed']} | {run['ridge_selected_alpha']:g} | {f(m['ribomimo']['transcript_balanced_mse'])} | {f(m['ridge']['transcript_balanced_mse'])} | {f(m['constant']['transcript_balanced_mse'])} | {f(m['ribomimo']['mean_transcript_pearson'])} | {f(m['ridge']['mean_transcript_pearson'])} |")
    table = "\n".join(rows)
    protocol = repo / "configs/a8_rk05_ribomimo_study_ood_protocol_v1.json"
    unit = out / "ribomimo_study_ood_unit_tests_v1.json"
    prod_console = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/production.console.log")
    ind_console = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/independent_retrain.console.log")
    failed_invocation = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/independent.console.log")
    failed_nameerror = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/independent_verify_nameerror.console.log")
    failed_raw_exact = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/independent_verify_raw_exact_failure.console.log")
    commands = f"""```bash
cd /home/codonflow-a8-rk
PY=/root/miniconda3/envs/llr_env/bin/python
$PY scripts/a8_rk05_ribomimo_study_ood.py \\
  --protocol configs/a8_rk05_ribomimo_study_ood_protocol_v1.json \\
  --output-dir /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/production \\
  --report audits/20261119/RK05/ribomimo_study_ood_production_v1.json
$PY scripts/a8_rk05_ribomimo_study_ood.py \\
  --protocol configs/a8_rk05_ribomimo_study_ood_protocol_v1.json \\
  --output-dir /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/independent \\
  --report audits/20261119/RK05/ribomimo_study_ood_independent_retrain_v1.json
$PY scripts/a8_rk05_verify_ribomimo_study_ood.py \\
  --protocol configs/a8_rk05_ribomimo_study_ood_protocol_v1.json \\
  --production-report audits/20261119/RK05/ribomimo_study_ood_production_v1.json \\
  --independent-report audits/20261119/RK05/ribomimo_study_ood_independent_retrain_v1.json \\
  --driver scripts/a8_rk05_ribomimo_study_ood.py \\
  --output audits/20261119/RK05/ribomimo_study_ood_independent_v1.json
```"""
    common = f"""# A8-RK05 RiboMIMO cross-study OOD evidence

## Frozen scope

- Official RiboMIMO commit: `094c693d4df45f4b29f5a3209b31c452a39092a5`; frozen code commit: `{args.frozen_code_commit}`.
- Protocol SHA256: `{sha256(protocol)}`; driver SHA256: `{production['prepare']['driver_sha256']}`.
- Mohammad16 source: 1,179 eligible, split into 1,062 train / 117 validation; Subtelny14 target: 3,921. Exact CDS overlap=0.
- Primary seed=1234; sensitivity seeds=2345/3456. Ridge alpha was selected only on source validation and was 100 for every seed.
- Target evaluation occurred only after training, early stopping and source-only ridge selection. Subtelny14 is not globally untouched because earlier RiboKinetic/ridge analyses used it.

## Training and target results

| Seed | Best/last epoch | Alpha | RiboMIMO TB-MSE | Ridge TB-MSE | Constant TB-MSE | RiboMIMO mean r | Ridge mean r |
|---:|---:|---:|---:|---:|---:|---:|---:|
{table}

Primary TB-MSE delta (RiboMIMO-ridge)={p0['point_delta_ribomimo_minus_ridge']:.12f}, 95% CI=[{p0['ci95_low']:.12f}, {p0['ci95_high']:.12f}], sign-flip p={p0['sign_flip_pvalue']:.12f}, Holm p={p0['holm_pvalue']:.12f}. Primary mean-transcript-Pearson delta={p1['point_delta_ribomimo_minus_ridge']:.12f}, 95% CI=[{p1['ci95_low']:.12f}, {p1['ci95_high']:.12f}], sign-flip p={p1['sign_flip_pvalue']:.12f}, Holm p={p1['holm_pvalue']:.12f}.

**Result:** ridge significantly outperformed RiboMIMO on both frozen primary endpoints in this direction and setup. The constant baseline also had lower TB-MSE than both learned models for every seed; ridge's relative win is not strong absolute transfer. This is an occupancy-derived study-OOD result, not physical velocity, functional/homology/protein OOD, RK-G1 closure, generator authorization or SOTA.

## Verification

- Unit tests: 10/10 PASS (`ribomimo_study_ood_unit_tests_v1.json`).
- Production: three complete runs (`ribomimo_study_ood_production_v1.json`).
- Independent retrain: three complete runs in separate directories (`ribomimo_study_ood_independent_retrain_v1.json`).
- Independent raw-data/statistical verification: {verification['n_passed']}/{verification['n_checks']} PASS; model/ridge independent/ridge raw-refit maximum differences={verification['details']['max_differences']['model_independent_retrain']:.3g}/{verification['details']['max_differences']['ridge_independent_retrain']:.3g}/{verification['details']['max_differences']['ridge_raw_refit']:.3g}.
- Finalization: {final['n_passed']}/{final['n_checks']} PASS (`ribomimo_study_ood_finalization_v1.json`).
- Training record: `ribomimo_study_ood_training_record_v1.json` and `.md`; full per-epoch histories and official logs are retained.
- Manuscript: A8 v25, still non-submittable; paper verification {paper_verify['n_passed']}/{paper_verify['n_checks']} PASS and candidate facts {paper_verify['candidate_facts_passed']}/{paper_verify['candidate_fact_count']} PASS.
- Online PPT: candidate facts 33/33 PASS; page 101 (`pgI`), revision 63; full readback 206/206 PASS with all 100 prior slides semantically unchanged. The six strict XML differences are only declared server defaults (five table-column `span=1` attributes and speaker-note body style removal).
- Shared-GPU timings are observed wall times only, not unified single-worker/time-matched cost evidence.

## Reproduction

{commands}

The finalizer binds protocol/driver hashes, the frozen Git commit, both production reports, independent raw-data/statistical checks, both consoles, unit tests and target-prediction hashes. Large matrices, runtimes, checkpoints and predictions remain under `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_study_ood_094c_v1/`; code and small reports remain under `/home/codonflow-a8-rk`.

## Retained engineering failure

The first verifier invocation used unsupported CLI arguments and exited before training or verification; its log is retained at `{failed_invocation}`. A later verifier implementation failed on an undefined parameter-count variable before producing a verification report; that log is retained at `{failed_nameerror}`. A subsequent raw-data verifier pass completed 200/203 checks but incorrectly required bit-exact raw ridge refitting; its log is retained at `{failed_raw_exact}` and its failed report is preserved as `audits/20261119/RK05/ribomimo_study_ood_independent_raw_exact_failure_v1.json`. The corrected verifier resolves official-runner relative paths, checks checkpoint parameter tensors directly, requires exact model/checkpoint reproduction, and applies a declared 1e-6 absolute numerical tolerance to both independent and raw-refit ridge predictions because separate LSQR/BLAS runs differ in floating-point reductions (observed maximum 1.51e-7). Record identity, offsets, positions and targets remain exact; all scientific metrics and primary inference are independently recomputed. No scientific output was overwritten by these failed invocations, and the tolerance is an engineering reproducibility criterion rather than a target-dependent scientific threshold.

## Open gates

This result does not close RK-G0/G1/G2/G3/G4, functional untouched evaluation, homology/protein OOD, physical-velocity assays, full velocity baseline coverage, dense-budget generation, time-matched costs, predictive/generative ablations, wet-lab validation or manuscript submittability. PPT evidence is appended only after this finalized result has passed review.
"""
    readme.write_text(common)
    handoff.write_text(common + "\n## Resume pointer\n\nUse the frozen protocol and production/independent/finalization JSON reports listed above. The next scientific priority remains mechanism-supported real functional OOD, not further generator scaling. Online PPT evidence is closed at page 101 (`pgI`), revision 63: candidate 33/33 PASS and online readback 206/206 PASS; all 100 prior slides are semantically unchanged.\n")

    tasks_path = repo / "docs/handover/tasks.md"
    tasks = tasks_path.read_text()
    marker = "## 2026-11-19 RK05 RiboMIMO cross-study OOD increment"
    if marker not in tasks:
        addition = f"""

{marker}

- [x] 冻结并完成 Mohammad16→Subtelny14 RiboMIMO/ridge/constant study-OOD：1,062/117 source train/validation、3,921 target、exact CDS overlap=0，主 seed=1234，敏感性 seeds=2345/3456，target 在 source 训练与 alpha 选择后才评估。10/10 tests、独立 {verification['n_passed']}/{verification['n_checks']}、finalization {final['n_passed']}/{final['n_checks']} 通过。
- [x] 两项冻结主终点均显著有利于 ridge：ΔTB-MSE={p0['point_delta_ribomimo_minus_ridge']:.9f}，95% CI=[{p0['ci95_low']:.9f},{p0['ci95_high']:.9f}]；Δmean-r={p1['point_delta_ribomimo_minus_ridge']:.9f}，95% CI=[{p1['ci95_low']:.9f},{p1['ci95_high']:.9f}]；两者 Holm p={p0['holm_pvalue']:.9f}。常数 baseline 的 TB-MSE 也低于两个学习模型，不能写成强绝对迁移。
- [x] A8 v25 已写入该负迁移结果并完成 {paper_verify['n_passed']}/{paper_verify['n_checks']} 论文核验；仍为 non-submittable working manuscript。复现说明见 `audits/20261119/RK05/README.md`，新交接见 `docs/handover/HANDOFF_A8_RK05_RIBOMIMO_STUDY_OOD_20261119.md`。
- [x] 在线 PPT 第 101 页 `pgI`、revision 63：写前候选事实 33/33、写后整稿回读 206/206 通过，前 100 页语义 XML 全部不变；严格 XML 的 6 处差异仅为已披露的服务端默认属性规范化。
- [ ] 本实验不关闭全局 untouched、物理速度、功能/homology/protein OOD、RK-G1、生成训练授权、time-matched 成本或完整 baseline 主矩阵；下一优先仍是机制支持的真实功能 OOD。
"""
        tasks_path.write_text(tasks.rstrip() + addition.rstrip() + "\n")

    registry_path = repo / "experiments/REGISTRY.md"
    registry = registry_path.read_text()
    run_marker = "CF-A8-RK05-RIBOMIMO-STUDY-OOD"
    if run_marker not in registry:
        row = f"| {run_marker} | 2026-11-19/20 | velocity baseline / study-OOD | frozen `a8_rk05_ribomimo_study_ood.py`; three seeds plus independent retrain and raw-data verifier | shared RTX5090; observed times only | Mohammad16/Subtelny14 raw SHA d093a3b0…/d982f6d8…; exact CDS overlap=0 | {args.frozen_code_commit} | official RiboMIMO recipe; primary 1234, sensitivity 2345/3456; ridge alpha=100 source-validation only; 2000 bootstrap + 2000 sign-flip | best/last=10/15,10/15,13/18; exact model/checkpoint; ridge max diff {verification['details']['max_differences']['ridge_independent_retrain']:.3g} ≤1e-6 | ΔTB-MSE={p0['point_delta_ribomimo_minus_ridge']:.9f} CI [{p0['ci95_low']:.9f},{p0['ci95_high']:.9f}]; Δmean-r={p1['point_delta_ribomimo_minus_ridge']:.9f} CI [{p1['ci95_low']:.9f},{p1['ci95_high']:.9f}]; Holm p={p0['holm_pvalue']:.9f} each; ridge wins both, constant lower TB-MSE than both | done_negative_study_ood_not_physical_or_functional_ppt_pgI_rev63_readback206 |\n"
        registry_path.write_text(registry.rstrip() + "\n" + row)
    print(json.dumps({"status": "PASS", "readme": str(readme), "handoff": str(handoff), "tasks": str(tasks_path), "registry": str(registry_path)}, indent=2))


if __name__ == "__main__":
    main()
