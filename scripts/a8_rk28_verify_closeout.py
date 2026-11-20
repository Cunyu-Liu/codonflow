#!/usr/bin/env python3
"""Evidence/commit binder for the RK28 scientific closeout."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--science-commit", default="71d27dd7610559c2781849c2be7b2a26933c3d0e")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo
    audit = repo / "audits/20261121/RK28"
    protocol_path = audit / "a8_rk28_mordstein_sequence_cluster_ood_protocol_v1.json"
    coverage_path = audit / "rk28_sequence_coverage_v1.json"
    result_path = audit / "rk28_sequence_cluster_ood_result_v1.json"
    independent_path = audit / "rk28_sequence_cluster_ood_independent_v1.json"
    initial_path = audit / "rk28_sequence_cluster_ood_independent_initial_failure_v1.json"
    closeout_path = audit / "A8_RK28_SEQUENCE_CLUSTER_OOD_CLOSEOUT.md"
    registry_path = repo / "experiments/REGISTRY.md"
    protocol = json.loads(protocol_path.read_text())
    coverage = json.loads(coverage_path.read_text())
    result = json.loads(result_path.read_text())
    independent = json.loads(independent_path.read_text())
    initial = json.loads(initial_path.read_text())
    closeout = closeout_path.read_text()
    registry = registry_path.read_text()
    checks = []

    def check(name, condition, details=None):
        checks.append({"name": name, "pass": bool(condition), "details": details})

    check("science_commit_full", len(args.science_commit) == 40, args.science_commit)
    check("science_commit_is_ancestor", subprocess.run(["git", "merge-base", "--is-ancestor", args.science_commit, "HEAD"], cwd=repo).returncode == 0, args.science_commit)
    check("protocol_hash_binding", result["protocol_sha256"] == sha256(protocol_path) == coverage["protocol_sha256"], result["protocol_sha256"])
    check("coverage_hash_binding", result["coverage_report_sha256"] == sha256(coverage_path), result["coverage_report_sha256"])
    check("production_script_hash", result["analysis_script_sha256"] == sha256(repo / "scripts/a8_rk28_run_sequence_cluster_ood.py"), result["analysis_script_sha256"])
    check("coverage_script_hash", coverage["coverage_script_sha256"] == sha256(repo / "scripts/a8_rk28_audit_sequence_coverage.py"), coverage["coverage_script_sha256"])
    check("independent_script_hash", independent["independent_script_sha256"] == sha256(repo / "scripts/a8_rk28_verify_sequence_cluster_ood.py"), independent["independent_script_sha256"])
    check("independent_production_hash_binding", independent["production_summary_sha256"] == sha256(result_path), independent["production_summary_sha256"])
    check("source_hash_binding", sha256(Path(protocol["inputs"]["main_csv"]["path"])) == protocol["inputs"]["main_csv"]["sha256"], protocol["inputs"]["main_csv"]["sha256"])
    check("frozen_before_fit", protocol["created_before_RK28_outcome_or_model_feature_read"] is True and protocol["created_before_RK28_model_fit"] is True, protocol["schema"])
    check("label_free_coverage", coverage["expression_or_model_fit_performed"] is False and coverage["outcome_or_model_feature_read"] is False and coverage["selected_min_identity"] == 0.9, coverage["selected_coverage"])
    check("coverage_feasible", coverage["coverage_feasible"] is True and len(coverage["checks"]) == 9 and all(row["pass"] for row in coverage["checks"]), coverage["status"])
    check("sample_chain", result["n_variants"] == 152 and result["n_sequence_clusters"] == 74 and coverage["selected_coverage"]["largest_cluster"] == 12, {"variants": 152, "clusters": 74, "largest": 12})
    check("training_record", result["total_model_fits"] == 300 and result["device"] == "CPU_ONLY" and result["folds_per_seed"] == 5 and len(result["seeds"]) == 10, {"fits": 300, "seeds": 10, "folds": 5})
    check("scientific_conclusion", result["scientific_conclusion"] == "FIXED_GFP_HEK293_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED", result["scientific_conclusion"])
    check("family_gate_negative", result["sequence_cluster_ood_structure_increment_pass"] is False and len(result["primary_tests"]) == 4, result["sequence_cluster_ood_structure_increment_pass"])
    expected_positive = {"ridge_spearman_effect": 0, "ridge_mse_improvement": 0, "histgb_spearman_effect": 3, "histgb_mse_improvement": 5}
    for test in result["primary_tests"]:
        name = test["test"]
        check(f"{name}_effect_negative", test["observed_effect"] < 0, test["observed_effect"])
        check(f"{name}_ci_includes_zero", test["ci95"][0] < 0 < test["ci95"][1], test["ci95"])
        check(f"{name}_holm_not_significant", test["p_holm"] > 0.05, test["p_holm"])
        check(f"{name}_seed_count", test["positive_seeds"] == expected_positive[name] and len(test["seed_effects"]) == 10, test["positive_seeds"])
        check(f"{name}_fail", test["pass"] is False, test["pass"])
    for name in ["ridge_spearman_effect", "ridge_mse_improvement"]:
        test = next(row for row in result["primary_tests"] if row["test"] == name)
        check(f"{name}_all_seeds_negative", all(value < 0 for value in test["seed_effects"]), test["seed_effects"])
    check("independent_54_of_54", independent["status"] == "PASS" and independent["n_checks"] == 54 and independent["n_passed"] == 54 and independent["independent_verification_pass"] is True, {"checks": independent["n_checks"], "passed": independent["n_passed"]})
    check("independent_conclusion_match", independent["independent_conclusion"] == result["scientific_conclusion"], independent["independent_conclusion"])
    check("independent_no_shared_modules", not independent["implementation"]["production_module_imported"] and not independent["implementation"]["coverage_module_imported"] and not independent["implementation"]["rk02_module_imported"], independent["implementation"])
    check("independent_rebuilt_everything", independent["implementation"]["clusters_rebuilt_from_raw_observed_r1"] and independent["implementation"]["features_rebuilt_from_raw_observed_r1"] and independent["implementation"]["all_models_refit"] and independent["implementation"]["all_resamples_recomputed"], independent["implementation"])
    check("initial_independent_failure_retained", initial["status"] == "FAIL" and initial["n_checks"] == 54 and initial["n_passed"] == 53, {"status": initial["status"], "passed": initial["n_passed"]})
    initial_failures = [row["name"] for row in initial["checks"] if not row["pass"]]
    check("initial_failure_only_null_literal_merge", initial_failures == ["metric_row_coverage"], initial_failures)
    synthetic = json.loads((audit / "rk28_production_synthetic_v1.json").read_text())
    check("production_synthetic_20", synthetic["status"] == "PASS" and synthetic["passed"] == 20 and synthetic["study_outcomes_read"] is False, synthetic["passed"])
    initial_synthetic_log = (audit / "rk28_production_synthetic_initial_failure_console_v1.log").read_text()
    check("initial_synthetic_failure_retained", "AssertionError: ridge learns synthetic relation" in initial_synthetic_log and "No production code" in initial_synthetic_log, "initial ridge tolerance failure")
    for name, record in result["outputs"].items():
        path = Path(record["path"])
        check(f"production_artifact_{name}", path.exists() and sha256(path) == record["sha256"] and path.stat().st_size == record["bytes"], record)
        check(f"production_artifact_location_{name}", str(path).startswith("/teams/HoulabData_1788502323/liucunyu/"), str(path))
    for name, record in independent["independent_outputs"].items():
        path = Path(record["path"])
        check(f"independent_artifact_{name}", path.exists() and sha256(path) == record["sha256"], record)

    required_closeout_tokens = [
        args.science_commit,
        "c762484fde8fb3f7b9f13912bfbd75258a7538d45b13d604d498dd4ffd64c67f",
        "edd1e14c8396b7ba3cce5b2accb94248af1020507765b8d64467a6b16e04b9d1",
        "-0.039264", "[-0.089517, 0.003815]", "-0.082105", "[-0.174100, 0.014918]",
        "-0.025531", "[-0.136859, 0.078912]", "-0.133851", "[-0.494481, 0.193206]",
        "54/54 PASS", "20/20 PASS", "40/40 PASS", "53/54", "300 次真实 CPU 模型拟合",
        "FIXED_GFP_HEK293_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED",
        "RK-G1 仍为 false，生成训练未授权", "不是独立 untouched 确认", "不是 protein OOD",
        "不是 measured structure", "不测量 translation velocity 或 mRNA decay",
    ]
    for token in required_closeout_tokens:
        check(f"closeout_contains_{token}", token in closeout, token)
    registry_rows = [line for line in registry.splitlines() if line.startswith("| RK28 |")]
    check("registry_single_RK28_row", len(registry_rows) == 1, len(registry_rows))
    if registry_rows:
        row = registry_rows[0]
        for token in [args.science_commit, "independent54/54", "0.039264", "0.025531", "RK-G1=false", "generator unauthorized", "structure transport not supported"]:
            check(f"registry_contains_{token}", token in row, token)
    flags = result["scientific_flags"]
    check("retrospective_boundaries", flags["labels_previously_used_in_RK02_development"] and not flags["independent_untouched_confirmation"], flags)
    check("global_gate_not_overclaimed", not flags["rk_g1_complete"] and not flags["generator_training_authorized"] and not flags["functional_untouched_read"], flags)
    check("fragment_structure_boundary", not flags["complete_cds_observed"] and not flags["measured_structure"] and not flags["author_gfp_identity_mapping"], flags)
    check("mechanism_scope_not_overclaimed", flags["fixed_protein"] and not flags["protein_ood"] and not flags["velocity_or_decay_measured"] and not flags["full_spatial_coupling_established"], flags)

    passed = all(row["pass"] for row in checks)
    report = {
        "schema": "a8-rk28-closeout-verification-v1", "status": "PASS" if passed else "FAIL",
        "n_checks": len(checks), "n_passed": int(sum(row["pass"] for row in checks)), "checks": checks,
        "science_commit": args.science_commit, "result_sha256": sha256(result_path),
        "independent_report_sha256": sha256(independent_path), "closeout_sha256": sha256(closeout_path),
        "registry_sha256": sha256(registry_path), "verifier_script_sha256": sha256(Path(__file__).resolve()),
        "rk_g1_complete": False, "generator_training_authorized": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "n_checks": len(checks), "n_passed": report["n_passed"], "failed": [row for row in checks if not row["pass"]], "closeout_sha256": report["closeout_sha256"]}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
