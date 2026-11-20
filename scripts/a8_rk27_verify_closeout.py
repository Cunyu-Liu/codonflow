#!/usr/bin/env python3
"""Evidence/commit binder for the RK27 scientific closeout."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--science-commit", default="8a62836bb73b34bcae529bae6a21f6e3eefc85d1")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo
    audit = repo / "audits/20261121/RK27"
    protocol_path = audit / "a8_rk27_kudla_sequence_cluster_ood_protocol_v1.json"
    coverage_path = audit / "rk27_sequence_coverage_v1.json"
    result_path = audit / "rk27_sequence_cluster_ood_result_v1.json"
    independent_path = audit / "rk27_sequence_cluster_ood_independent_v1.json"
    initial_path = audit / "rk27_sequence_cluster_ood_independent_initial_v1.json"
    closeout_path = audit / "A8_RK27_SEQUENCE_CLUSTER_OOD_CLOSEOUT.md"
    registry_path = repo / "experiments/REGISTRY.md"
    protocol = json.loads(protocol_path.read_text())
    coverage = json.loads(coverage_path.read_text())
    result = json.loads(result_path.read_text())
    independent = json.loads(independent_path.read_text())
    initial = json.loads(initial_path.read_text())
    closeout = closeout_path.read_text()
    registry = registry_path.read_text()
    checks = []

    def check(name: str, condition: bool, details: object = None) -> None:
        checks.append({"name": name, "pass": bool(condition), "details": details})

    check("science_commit_full", len(args.science_commit) == 40, args.science_commit)
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", args.science_commit, "HEAD"], cwd=repo).returncode == 0
    check("science_commit_is_ancestor", ancestor, args.science_commit)
    check("protocol_hash_binding", result["protocol_sha256"] == sha256(protocol_path) == coverage["protocol_sha256"], result["protocol_sha256"])
    check("coverage_hash_binding", result["coverage_report_sha256"] == sha256(coverage_path), result["coverage_report_sha256"])
    check("production_script_hash", result["analysis_script_sha256"] == sha256(repo / "scripts/a8_rk27_run_sequence_cluster_ood.py"), result["analysis_script_sha256"])
    check("coverage_script_hash", coverage["coverage_script_sha256"] == sha256(repo / "scripts/a8_rk27_audit_sequence_coverage.py"), coverage["coverage_script_sha256"])
    check("independent_script_hash", independent["independent_script_sha256"] == sha256(repo / "scripts/a8_rk27_verify_sequence_cluster_ood.py"), independent["independent_script_sha256"])
    check("independent_production_hash_binding", independent["production_summary_sha256"] == sha256(result_path), independent["production_summary_sha256"])
    check("source_hash_binding", sha256(Path(protocol["inputs"]["main_csv"]["path"])) == protocol["inputs"]["main_csv"]["sha256"], protocol["inputs"]["main_csv"]["sha256"])
    check("frozen_before_fit", protocol["status"] == "FROZEN_BEFORE_ANY_RK27_MODEL_FIT_OR_NEW_EXPRESSION_ASSOCIATION", protocol["status"])
    check("label_free_coverage", coverage["expression_or_model_fit_performed"] is False and coverage["selected_min_identity"] == 0.9, coverage["selected_coverage"])
    check("sample_chain", result["n_measurement_rows"] == 154 and result["n_exact_cds_groups"] == 150 and result["n_sequence_clusters"] == 37, {"rows": 154, "groups": 150, "clusters": 37})
    check("training_record", result["total_model_fits"] == 300 and result["device"] == "CPU_ONLY" and result["folds_per_seed"] == 5 and len(result["seeds"]) == 10, {"fits": 300, "seeds": 10, "folds": 5})
    check("scientific_conclusion", result["scientific_conclusion"] == "FIXED_PROTEIN_SEQUENCE_CLUSTER_OOD_MFE_INCREMENT_SUPPORTED_RETROSPECTIVELY", result["scientific_conclusion"])
    check("family_gate", result["sequence_cluster_ood_mfe_increment_pass"] is True and len(result["primary_tests"]) == 4, result["sequence_cluster_ood_mfe_increment_pass"])
    for test in result["primary_tests"]:
        name = test["test"]
        check(f"{name}_positive", test["observed_effect"] > 0, test["observed_effect"])
        check(f"{name}_ci_excludes_zero", test["ci95"][0] > 0, test["ci95"])
        check(f"{name}_holm_significant", test["p_holm"] < 0.05, test["p_holm"])
        check(f"{name}_seed_stable", test["positive_seeds"] == 10 and len(test["seed_effects"]) == 10 and all(x > 0 for x in test["seed_effects"]), test["positive_seeds"])
        check(f"{name}_pass", test["pass"] is True, test["pass"])
    check("independent_47_of_47", independent["status"] == "PASS" and independent["n_checks"] == 47 and independent["n_passed"] == 47 and independent["independent_verification_pass"] is True, {"checks": independent["n_checks"], "passed": independent["n_passed"]})
    check("independent_conclusion_match", independent["independent_conclusion"] == result["scientific_conclusion"], independent["independent_conclusion"])
    check("independent_no_shared_modules", not independent["implementation"]["production_module_imported"] and not independent["implementation"]["coverage_module_imported"], independent["implementation"])
    check("independent_rebuilt_everything", independent["implementation"]["clusters_rebuilt_from_raw_cds"] and independent["implementation"]["all_models_refit"] and independent["implementation"]["all_resamples_recomputed"], independent["implementation"])
    check("initial_independent_failure_retained", initial["status"] == "FAIL" and initial["n_checks"] == 47 and initial["n_passed"] == 46, {"status": initial["status"], "passed": initial["n_passed"]})
    initial_failures = [row["name"] for row in initial["checks"] if not row["pass"]]
    check("initial_failure_only_null_literal_merge", initial_failures == ["metric_row_coverage"], initial_failures)
    check("production_synthetic_log", "14 passed" in (audit / "rk27_synthetic_tests_v1.log").read_text(), "14 passed")
    check("independent_synthetic_log", "8 passed" in (audit / "rk27_independent_synthetic_tests_v1.log").read_text(), "8 passed")
    abort = json.loads((audit / "rk27_production_thread_aborted_v1.json").read_text())
    check("initial_execution_abort_safe", abort["result_used"] is False and abort["prediction_table_produced"] is False and abort["scientific_protocol_changed"] is False, abort)

    for name, record in result["outputs"].items():
        path = Path(record["path"])
        check(f"production_artifact_{name}", path.exists() and sha256(path) == record["sha256"] and path.stat().st_size == record["bytes"], record)
        check(f"production_artifact_location_{name}", str(path).startswith("/teams/HoulabData_1788502323/liucunyu/"), str(path))
    for name, record in independent["independent_outputs"].items():
        path = Path(record["path"])
        check(f"independent_artifact_{name}", path.exists() and sha256(path) == record["sha256"], record)

    required_closeout_tokens = [
        args.science_commit,
        "b601db3b0a5bec6b228492846f0058a0d959439c0eeebada05b749daa366ed5e",
        "1e657146110a553071b169578839cbd0c45e357d9d4ff32394f297848d2df5f4",
        "0.955051", "[0.493814, 1.106833]", "0.157489", "[0.071313, 0.212686]",
        "0.412578", "[0.208828, 0.520318]", "0.105907", "[0.042279, 0.140561]",
        "47/47 PASS", "14/14 PASS", "8/8 PASS", "46/47", "300 次真实 CPU 模型拟合",
        "回顾性固定蛋白序列簇运输证据", "RK-G1 仍为 false", "生成训练未授权",
        "不是独立 untouched 确认", "不是 protein OOD", "不测量 velocity 或 decay",
    ]
    for token in required_closeout_tokens:
        check(f"closeout_contains_{token}", token in closeout, token)
    registry_rows = [line for line in registry.splitlines() if line.startswith("| RK27 |")]
    check("registry_single_RK27_row", len(registry_rows) == 1, len(registry_rows))
    if registry_rows:
        row = registry_rows[0]
        for token in [args.science_commit, "independent47/47", "0.955051", "0.412578", "RK-G1=false", "generator unauthorized", "retrospective fixed-protein sequence-cluster transport supported"]:
            check(f"registry_contains_{token}", token in row, token)
    flags = result["scientific_flags"]
    check("retrospective_boundaries", flags["labels_previously_used_in_RK22_development"] and not flags["independent_untouched_confirmation"], flags)
    check("global_gate_not_overclaimed", not flags["RK_G1_complete"] and not flags["generator_training_authorized"] and not flags["functional_untouched_read"], flags)
    check("mechanism_scope_not_overclaimed", flags["fixed_protein"] and flags["sequence_cluster_ood"] and not flags["protein_ood"] and not flags["velocity_or_decay_measured"] and not flags["full_spatial_coupling_established"], flags)

    passed = all(row["pass"] for row in checks)
    report = {
        "schema": "a8-rk27-closeout-verification-v1",
        "status": "PASS" if passed else "FAIL",
        "n_checks": len(checks),
        "n_passed": int(sum(row["pass"] for row in checks)),
        "checks": checks,
        "science_commit": args.science_commit,
        "result_sha256": sha256(result_path),
        "independent_report_sha256": sha256(independent_path),
        "closeout_sha256": sha256(closeout_path),
        "registry_sha256": sha256(registry_path),
        "verifier_script_sha256": sha256(Path(__file__).resolve()),
        "RK_G1_complete": False,
        "generator_training_authorized": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "n_checks": len(checks), "n_passed": report["n_passed"], "failed": [row for row in checks if not row["pass"]], "closeout_sha256": report["closeout_sha256"]}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
