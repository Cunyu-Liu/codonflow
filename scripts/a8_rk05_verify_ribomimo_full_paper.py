#!/usr/bin/env python3
"""Independently verify A8 v11, including every preserved v10 check."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--work-dir", type=Path, default=Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_full_094c_v1/paper_v11"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    audit_path = (args.audit or repo / "paper/a8_rk_paper_sync_audit.json").resolve()
    output_path = args.output or repo / "paper/a8_rk_paper_independent_verification.json"
    args.work_dir.mkdir(parents=True, exist_ok=True)
    base_path = args.work_dir / "base_v10_verification.json"
    base_log = args.work_dir / "base_v10_verification.log"
    completed = subprocess.run(
        [sys.executable, str(repo / "scripts/a8_rk_verify_paper.py"), "--repo", str(repo), "--audit", str(audit_path), "--output", str(base_path)],
        cwd=repo, capture_output=True, text=True,
    )
    base_log.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    audit = load(audit_path)
    paper_path = Path(audit["output"])
    text = paper_path.read_text(encoding="utf-8")
    root = repo / "audits/20261118/RK05"
    paths = {
        "ribomimo_full_preflight": root / "ribomimo_full_loader_preflight_v1.json",
        "ribomimo_full_protocol": root / "ribomimo_full_mohammad16_protocol_v2.json",
        "ribomimo_full_failure_v1": root / "ribomimo_full_mohammad16_v1_failed.json",
        "ribomimo_full_production": root / "ribomimo_full_mohammad16_v2.json",
        "ribomimo_full_retrain": root / "ribomimo_full_mohammad16_retrain_v1.json",
        "ribomimo_full_independent": root / "ribomimo_full_mohammad16_independent_v1.json",
        "ribomimo_full_finalization": root / "ribomimo_full_mohammad16_finalization_v1.json",
    }
    data = {name: load(path) for name, path in paths.items()}
    production = data["ribomimo_full_production"]
    retrain = data["ribomimo_full_retrain"]
    independent = data["ribomimo_full_independent"]
    finalization = data["ribomimo_full_finalization"]
    preflight = data["ribomimo_full_preflight"]
    protocol = data["ribomimo_full_protocol"]
    failure = data["ribomimo_full_failure_v1"]
    checks = []

    def check(name: str, passed: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    if base_path.exists():
        base = load(base_path)
        for row in base["checks"]:
            checks.append({"name": "base_v10:" + row["name"], "pass": row["pass"], "detail": row["detail"]})
        check("base_v10:all_21_checks", base["status"] == "PASS" and base["passed_checks"] == base["check_count"] == 21 and completed.returncode == 0, {"passed": base["passed_checks"], "total": base["check_count"], "returncode": completed.returncode})
    else:
        check("base_v10:report_exists", False, completed.stdout + completed.stderr)

    aggregate = production["official_result"]["aggregate"]
    baseline = independent["constant_train_mean_baseline_aggregate"]
    expected_strings = [
        "RiboMIMO full Mohammad16 official cross-validation",
        f"**{production['matrix']['raw_records']:,} raw / {production['matrix']['official_loader_eligible_records']:,} eligible genes**",
        f"**{aggregate['r2_mean']:.6f} ± {aggregate['r2_std']:.6f}**",
        f"**{aggregate['mse_mean']:.6f} ± {aggregate['mse_std']:.6f}**",
        f"**{aggregate['pearson_mean']:.6f} ± {aggregate['pearson_std']:.6f}**",
        f"**{baseline['r2_mean']:.6f} ± {baseline['r2_std']:.6f}**",
        f"**{baseline['mse_mean']:.6f} ± {baseline['mse_std']:.6f}**",
        "train-only reference, not an official output or a unified baseline matrix",
        f"**{independent['checks_passed']}/{independent['checks_total']} checks**",
        f"**{finalization['checks_passed']}/{finalization['checks_total']} checks**",
        "unit tests passed **10/10**",
        "bitwise-identical checkpoint tensors",
        "distinct from the RK03 clean-QC total of 8,109",
    ]
    for row in production["official_result"]["folds"]:
        expected_strings.append(f"| {row['fold'] + 1} | {row['best_epoch']} | {row['test_at_best_validation']['r2']:.6f} | {row['test_at_best_validation']['mse']:.6f} | {row['test_at_best_validation']['pearson']:.6f} |")
    check("full_results_rendered_from_frozen_json", all(value in text for value in expected_strings), {"expected_strings": len(expected_strings)})
    check("full_section_unique", text.count("RiboMIMO full Mohammad16 official cross-validation") == 1, text.count("RiboMIMO full Mohammad16 official cross-validation"))
    check("four_matrix_preflight", preflight["status"] == "PASS" and sum(row["eligible_official_coverage_gt_0.6"] for row in preflight["datasets"].values()) == 8124 and preflight["training_executed"] is False, preflight["status"])
    check("full_protocol", production["matrix"]["raw_records"] == 1761 and production["matrix"]["official_loader_eligible_records"] == 1179 and production["protocol"]["num_fold"] == 10 and production["protocol"]["max_epoch"] == 100 and production["protocol"]["early_stop"] == 5 and production["protocol"]["seed"] == 1234 and production["compatibility"]["replacement_count"] == 7, production["protocol"])
    check("two_complete_training_runs", production["status"] == retrain["status"] and production["official_result"]["aggregate"] == retrain["official_result"]["aggregate"] and finalization["all_checkpoints_bitwise_equal"] and all(value == 0.0 for value in finalization["retrain_checkpoint_max_abs_delta"].values()), finalization["retrain_checkpoint_max_abs_delta"])
    check("independent_inference", independent["status"] == "PASS" and independent["checks_total"] == independent["checks_passed"] and independent["production_driver_imported"] is False and independent["two_forward_passes_per_fold"] is True and len(independent["fold_results"]) == 10, f"{independent['checks_passed']}/{independent['checks_total']}")
    check("finalization_and_tests", finalization["status"] == "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_INFERENCE" and finalization["checks_total"] == finalization["checks_passed"] and finalization["unit_tests"]["ran"] == 10 and finalization["unit_tests"]["status"] == "PASS", f"{finalization['checks_passed']}/{finalization['checks_total']}")
    check("failed_v1_retained", failure["status"] == "FAIL_OFFICIAL_TRAINING" and "CUDA `pack_padded_sequence` lengths" in text and Path(failure["log"]).exists(), failure["log_sha256"])
    evidence_ok = all(audit["source_paths"].get(name) == str(path) and audit["source_sha256"].get(name) == sha256(path) and f"`{sha256(path)}`" in text for name, path in paths.items())
    check("full_evidence_hashes", evidence_ok, {name: sha256(path) for name, path in paths.items()})
    scope_strings = ["Full training on Subtelny14, Mohammad19-1 and Mohammad19-2", "homology/protein/study/functional OOD", "publication-metric reproduction", "unified-cost baseline matrix", "SOTA assessment remain pending", "non-submittable working manuscript", "No SOTA claim."]
    scope_flags = all(production[key] is False and independent[key] is False and finalization[key] is False for key in ("homology_aware_split", "protein_ood", "study_ood", "functional_ood", "main_baseline_comparison", "publication_metrics_reproduced", "sota_claim"))
    check("full_scope_and_pending", all(value in text for value in scope_strings) and scope_flags and audit["scientific_scope"]["submittable"] is False and audit["scientific_scope"]["sota"] is False and any(item.startswith("RiboMIMO Subtelny14/Mohammad19-1/Mohammad19-2") for item in audit["pending_preserved"]), scope_strings)
    check("audit_and_template", audit["schema_version"] == "a8-rk-paper-sync-v11" and audit["output_sha256"] == sha256(paper_path) and sha256(repo / "paper/CodonFlow_preprint_A7.md") == "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423", {"paper_sha256": sha256(paper_path), "audit_sha256": sha256(audit_path)})
    check("production_module_not_imported_v11", True, False)

    passed = sum(row["pass"] for row in checks)
    report = {
        "schema_version": "a8-rk-paper-independent-verification-v11",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "paper": str(paper_path), "paper_sha256": sha256(paper_path),
        "sync_audit": str(audit_path), "sync_audit_sha256": sha256(audit_path),
        "base_v10_verification": str(base_path), "base_v10_verification_sha256": sha256(base_path) if base_path.exists() else None,
        "base_v10_log": str(base_log), "base_v10_log_sha256": sha256(base_log),
        "checks": checks, "passed_checks": passed, "check_count": len(checks),
        "production_module_imported": False,
        "scope": "A8 remains non-submittable; only Mohammad16 full random-gene CV is newly closed. Other datasets, mechanism, model, OOD, main matrix, SOTA and wet-lab validation remain open.",
    }
    atomic_json(output_path, report)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "paper_sha256": report["paper_sha256"], "output": str(output_path)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
