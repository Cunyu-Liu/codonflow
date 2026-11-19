#!/usr/bin/env python3
"""Finalize verification, not scientific success, of the fixed-GFP development structure pilot."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import subprocess


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--production", type=Path, required=True)
    ap.add_argument("--independent", type=Path, required=True)
    ap.add_argument("--unit-tests", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    protocol = json.loads(args.protocol.read_text())
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    tests = json.loads(args.unit_tests.read_text())
    checks = []
    def check(name, condition, details=None):
        checks.append({"name": name, "pass": bool(condition), "details": details})
    check("protocol_frozen_before_production", protocol["created_before_production"] is True)
    check("explicit_development_not_confirmatory", protocol["confirmatory_independent_test"] is False and production["analysis_status"] == independent["analysis_status"] == "DEVELOPMENT_ONLY_NOT_CONFIRMATORY_INDEPENDENT_TEST")
    check("production_pending_status", production["status"] in {"DEV_STRUCTURE_INCREMENT_PASS_PENDING_INDEPENDENT", "DEV_STRUCTURE_INCREMENT_NO_GO_PENDING_INDEPENDENT"})
    check("independent_pass", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] == len(independent["checks"]))
    check("unit_tests_pass", tests["status"] == "PASS" and tests["failed"] == 0 and tests["passed"] >= 10)
    check("protocol_hash_chain", production["protocol_sha256"] == independent["protocol_sha256"] == sha256(args.protocol))
    check("production_hash_chain", independent["production_sha256"] == sha256(args.production))
    check("population_152", production["n_variants"] == independent["n_variants"] == 152)
    check("raw_feature_independent_recompute", independent["verification"]["external_cai_recomputed"] and independent["verification"]["viennarna_recomputed"] and max(independent["feature_max_abs_delta"].values()) <= 1e-10)
    check("oof_independent_recompute", independent["verification"]["oof_predictions_recomputed_without_sklearn"] and max(independent["prediction_max_abs_delta"].values()) <= 1e-9)
    effects_match = True
    for endpoint in ("delta_spearman", "delta_mse"):
        p, q = production["primary_effects"][endpoint], independent["primary_effects"][endpoint]
        effects_match = effects_match and abs(p["observed"] - q["observed"]) <= 1e-10
        effects_match = effects_match and max(abs(a - b) for a, b in zip(p["ci95_percentile"], q["ci95_percentile"])) <= 1e-10
        effects_match = effects_match and p["permutation_p_two_sided"] == q["permutation_p_two_sided"] and p["holm_p"] == q["holm_p"] and p["direction_pass"] == ((q["ci95_percentile"][0] > 0 if endpoint == "delta_spearman" else q["ci95_percentile"][1] < 0) and q["holm_p"] < .05)
    check("resampling_independent_recompute", independent["verification"]["bootstrap_and_sign_flip_recomputed"] and effects_match)
    check("same_scientific_gate", production["structure_increment_pass"] == independent["structure_increment_pass"])
    check("five_folds_complete", sum(production["fold_sizes"].values()) == 152 and len(production["fold_sizes"]) == 5)
    for model in ("depth_only", "simple", "simple_plus_structure"):
        check("finite_metrics_" + model, all(math.isfinite(v) for v in production["model_metrics"][model].values()))
    for endpoint in ("delta_spearman", "delta_mse"):
        check("primary_effect_" + endpoint, endpoint in production["primary_effects"] and math.isfinite(production["primary_effects"][endpoint]["observed"]))
    boundary_keys = ["confirmatory_test", "protein_ood_evaluation", "study_ood_evaluation", "functional_untouched_evaluation", "complete_cds_analysis", "author_identity_mapping", "causal_inference", "full_rk_g1_gate", "generator_training_authorized", "sota_claim"]
    check("protocol_boundaries_closed", all(protocol["boundaries"].get(k) is False for k in boundary_keys))
    interpretation_keys = ["confirmatory_test", "functional_untouched_access", "protein_ood_evaluation", "complete_cds_analysis", "causal_inference", "full_rk_g1_gate", "generator_training_authorized", "sota_claim"]
    check("production_boundaries_closed", all(production["scientific_interpretation"].get(k) is False for k in interpretation_keys))
    head = subprocess.check_output(["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True).strip()
    ancestor = subprocess.run(["git", "-C", str(args.repo), "merge-base", "--is-ancestor", production["code_commit"], "HEAD"]).returncode == 0
    check("production_code_commit_is_ancestor_of_head", ancestor and production["tracked_tree_clean_at_launch"] is True, {"head": head, "production_code_commit": production["code_commit"]})
    passed = sum(c["pass"] for c in checks)
    gate = production["structure_increment_pass"]
    report = {
        "schema": "a8.rk02.mordstein_structure_increment_dev_finalization.v1",
        "status": "PASS_RK02_MORDSTEIN_STRUCTURE_INCREMENT_DEV" if passed == len(checks) else "FAILED",
        "scientific_result": "FIXED_GFP_OBSERVED_R1_STRUCTURE_INCREMENT_PASS_DEVELOPMENT_ONLY" if gate else "FIXED_GFP_OBSERVED_R1_STRUCTURE_INCREMENT_NO_GO_DEVELOPMENT_ONLY",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "checks_passed": passed, "checks_total": len(checks), "checks": checks,
        "protocol_sha256": sha256(args.protocol), "production_sha256": sha256(args.production), "independent_sha256": sha256(args.independent), "unit_tests_sha256": sha256(args.unit_tests),
        "n_variants": 152, "model_metrics": production["model_metrics"], "primary_effects": production["primary_effects"], "structure_increment_pass": gate,
        "completion": {"development_analysis_closed": passed == len(checks), "functional_untouched_used": False, "protein_ood_closed": False, "complete_cds_closed": False, "full_rk_g1_gate": False, "generator_training_authorized": False, "sota_claim": False},
        "note": "PASS denotes production/independent/statistical verification only. The scientific gate may be pass or no-go; neither result authorizes full RK-G1 or generator training."
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "scientific_result": report["scientific_result"], "checks": f"{passed}/{len(checks)}", "output": str(args.output)}))
    if passed != len(checks):
        for c in checks:
            if not c["pass"]:
                print("FAIL", c)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
