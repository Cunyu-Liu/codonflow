#!/usr/bin/env python3
"""Finalize RK06 only after production and independent recomputation pass."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audits/20261120/RK06"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def git_bytes(revision, path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)


def main():
    protocol_path = ROOT / "configs/a8_rk06_simple_search_dense_unique18_protocol_v1.json"
    production_path = AUDIT / "simple_search_dense_unique18_v1.json"
    independent_path = AUDIT / "simple_search_dense_independent_v2.json"
    manifest_path = AUDIT / "simple_search_dense_artifact_manifest.json"
    protocol = json.loads(protocol_path.read_text())
    production = json.loads(production_path.read_text())
    independent = json.loads(independent_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    checks = []

    def check(name, condition, detail=None):
        row = {"check": name, "pass": bool(condition)}
        if detail is not None:
            row["detail"] = detail
        checks.append(row)

    check("production_overall_pass", production.get("overall_pass") is True)
    check("production_formal_panel", production.get("formal_full_panel") is True)
    check("production_status", production.get("status") == "DONE_SIMPLE_SEARCH_DENSE_DEVELOPMENT")
    check("independent_overall_pass", independent.get("overall_pass") is True)
    check("independent_status", independent.get("status") == "INDEPENDENT_PASS")
    check("protocol_hash_production", production["protocol_sha256"] == sha256(protocol_path))
    check("protocol_hash_independent", independent["protocol_sha256"] == sha256(protocol_path))
    check("production_hash_independent", independent["production_sha256"] == sha256(production_path))
    check("manifest_hash", manifest["summary_sha256"] == sha256(production_path))
    check("artifact_summary_hash", manifest["artifact_summary_sha256"] == sha256(manifest["artifact_summary_path"]))
    check("run_count", production["n_runs"] == independent["n_independent_runs"] == 216)
    check("unique_scorer_count", production["n_unique_scorer_calls"] == independent["n_recomputed_objectives"] == 108000)
    check("record_count", len({row["record_id"] for row in production["runs"]}) == 18)
    check("method_count", len({row["method"] for row in production["runs"]}) == 4)
    check("seed_count", {row["seed"] for row in production["runs"]} == {0, 1, 2})
    check("six_primary_tests", len(production["primary_tests"]) == len(independent["independent_primary_tests"]) == 6)
    check("six_dominance_comparisons", len(production["bidirectional_strict_dominance_B500"]) == len(independent["independent_dominance"]) == 6)
    check("objective_independence", independent["maximum_differences"]["objectives"] <= 1e-9, independent["maximum_differences"]["objectives"])
    check("dense_curve_independence", independent["maximum_differences"]["dense_curve"] <= 1e-9, independent["maximum_differences"]["dense_curve"])
    check("inference_independence", independent["maximum_differences"]["paired_inference"] <= 1e-12, independent["maximum_differences"]["paired_inference"])
    check("dominance_independence", independent["maximum_differences"]["dominance"] <= 1e-12, independent["maximum_differences"]["dominance"])
    check("method_summary_independence", independent["maximum_differences"]["method_summary"] <= 1e-9, independent["maximum_differences"]["method_summary"])
    check("external_dense_null", production["external_actual_set_dense_policy"]["dense_budget_step_auc_v2"] is None)
    check("no_external_dense_conversion", production["external_actual_set_dense_policy"]["independent_lambda_run_unordered"] is True)
    check("no_untouched", not production["untouched24_used"])
    check("no_functional_untouched", not production["functional_untouched_used"])
    check("no_functional_labels", not production["functional_labels_used"])
    check("no_time_matched_external_claim", not production["time_matched_external_comparison"])
    check("rk_g1_remains_open", not production["rk_g1_closed"])
    check("no_generator_authorization", not production["expensive_generator_training_authorized"])
    check("no_sota_claim", not production["sota_claim"])
    check("manuscript_remains_non_submittable", not production["manuscript_submittable"])
    smoke = json.loads((AUDIT / "simple_search_dense_smoke_v2.json").read_text())
    check("smoke_pass", smoke["overall_pass"] and smoke["status"] == "SMOKE_PASS" and smoke["n_unique_scorer_calls"] == 80)
    unit_log = (AUDIT / "simple_search_dense_unit_tests_codonflow_env.console.log").read_text()
    independent_unit_log = (AUDIT / "simple_search_dense_independent_unit_tests_v2.console.log").read_text()
    check("production_unit_tests", "Ran 13 tests" in unit_log and "OK" in unit_log)
    check("independent_unit_tests", "Ran 7 tests" in independent_unit_log and "OK" in independent_unit_log)
    check("failed_smoke_retained", (AUDIT / "simple_search_dense_smoke_v1.console.log").exists())
    check("failed_initial_test_retained", (AUDIT / "simple_search_dense_unit_tests.console.log").exists())
    code_commit = production["code_commit"]
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", code_commit, "HEAD"], cwd=ROOT).returncode == 0
    check("production_commit_ancestor", ancestor, code_commit)
    independent_code_commit = independent["code_commit"]
    independent_ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", independent_code_commit, "HEAD"], cwd=ROOT).returncode == 0
    check("independent_commit_ancestor", independent_ancestor, independent_code_commit)
    independent_blob = hashlib.sha256(git_bytes(independent_code_commit, "scripts/a8_rk06_verify_simple_search_dense_unique18.py")).hexdigest()
    check("frozen_independent_verifier_blob", independent_blob == sha256(ROOT / "scripts/a8_rk06_verify_simple_search_dense_unique18.py"), independent_blob)
    for path in ["scripts/a8_rk06_simple_search_dense_unique18.py", "configs/a8_rk06_simple_search_dense_unique18_protocol_v1.json"]:
        committed = hashlib.sha256(git_bytes(code_commit, path)).hexdigest()
        check(f"frozen_blob_{Path(path).name}", committed == sha256(ROOT / path), committed)
    check("all_run_paths_in_artifact_root", all(Path(row["path"]).is_relative_to(Path(protocol["artifact_root"])) for row in production["runs"]))
    check("independent_manifest_hash", independent["independent_objectives_manifest_sha256"] == sha256(independent["independent_objectives_manifest"]))

    primary_tests = []
    for row in independent["independent_primary_tests"]:
        primary_tests.append({
            "method": row["method"],
            "comparator": "uniform",
            "endpoint": row["endpoint"],
            "effect": row["effect"],
            "ci95": row["ci95"],
            "sign_flip_p": row["sign_flip_p"],
            "holm_p": row["holm_p"],
            "supported_advantage": row["supported_advantage"],
        })
    claims = {
        "population": "unique18 development proxy-search only",
        "design": "18 records × 3 seeds × 4 methods × 500 real unique scorer calls",
        "n_runs": 216,
        "n_unique_scorer_calls": 108000,
        "dense_metric": "sum(HV_b for b=1..499)/499; B500 is endpoint only; no synthetic origin, trapezoid, missing-budget zero fill, or external actual-set conversion",
        "method_summary": production["method_summary"],
        "primary_tests": primary_tests,
        "bidirectional_strict_dominance_B500": production["bidirectional_strict_dominance_B500"],
        "statistical_unit": "record; arithmetic mean over seeds 0/1/2 before pairing",
        "resampling": "20,000 paired record bootstrap and 20,000 paired sign-flip permutations; six Holm tests",
        "external_actual_set_dense": None,
        "time_matched_external_comparison": False,
        "scientific_gate_passed": False,
        "rk_g1_closed": False,
        "sota_claim": False,
        "boundary": "These are real development proxy-search trajectories. Effects do not establish functional effectiveness, CodonFlow-RK improvement, external SOTA, RK-G1 closure, or generator-training readiness.",
    }
    overall = all(row["pass"] for row in checks)
    report = {
        "schema": "a8-rk06-simple-search-dense-finalization-v1",
        "status": "FINALIZED_DEVELOPMENT_DENSE_EVIDENCE" if overall else "FINALIZATION_FAILED",
        "overall_pass": overall,
        "protocol_sha256": sha256(protocol_path),
        "production_sha256": sha256(production_path),
        "independent_sha256": sha256(independent_path),
        "artifact_manifest_sha256": sha256(manifest_path),
        "production_code_commit": code_commit,
        "independent_code_commit": independent_code_commit,
        "checks": checks,
        "check_counts": {"total": len(checks), "passed": sum(row["pass"] for row in checks), "failed": sum(not row["pass"] for row in checks)},
        "claims": claims,
    }
    output = AUDIT / "simple_search_dense_finalization_v1.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    claims_path = AUDIT / "simple_search_dense_claims_v1.json"
    claims_path.write_text(json.dumps({
        "schema": "a8-rk06-paper-ppt-claims-v1",
        "finalization_sha256": sha256(output),
        "finalization_overall_pass": overall,
        **claims,
    }, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "overall_pass": overall, "check_counts": report["check_counts"],
                      "finalization": str(output), "claims": str(claims_path)}))
    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
