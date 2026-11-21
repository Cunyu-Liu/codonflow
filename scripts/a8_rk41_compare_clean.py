#!/usr/bin/env python3
"""Compare a clean RK41 reproduction with independently verified production."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def close(a, b):
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-12)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", required=True)
    parser.add_argument("--clean", required=True)
    parser.add_argument("--production-independent", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    production_path, clean_path, independent_path = Path(args.production), Path(args.clean), Path(args.production_independent)
    production = json.loads(production_path.read_text())
    clean = json.loads(clean_path.read_text())
    independent = json.loads(independent_path.read_text())
    checks = []

    def check(name, ok, detail=None):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    check("production_independent_pass", independent["status"] == "PASS")
    check("independent_binds_production", independent["summary_sha256"] == sha(production_path))
    check("protocol_identity", production["protocol_sha256"] == clean["protocol_sha256"])
    check("input_identities", all(production[k] == clean[k] for k in ("benchmark_sha256", "external_matrix_sha256", "rk40_summary_sha256", "rk40_independent_sha256")))
    check("run_accounting", production["n_new_runs"] == clean["n_new_runs"] == 216
          and production["n_new_unique_scorer_calls"] == clean["n_new_unique_scorer_calls"] == 2376
          and production["n_accepted_rk40_runs"] == clean["n_accepted_rk40_runs"] == 108)
    script = "scripts/a8_rk41_internal_basin_initialization.py"
    production_script = subprocess.check_output(["git", "show", f"{production['code_commit']}:{script}"], cwd=ROOT)
    clean_script = subprocess.check_output(["git", "show", f"{clean['code_commit']}:{script}"], cwd=ROOT)
    check("production_script_byte_identical_across_commits", production_script == clean_script)
    p_runs = {(r["record_id"], r["seed"], r["arm"]): r for r in production["runs"]}
    c_runs = {(r["record_id"], r["seed"], r["arm"]): r for r in clean["runs"]}
    check("run_key_identity", set(p_runs) == set(c_runs))
    metric_names = ("best_normalized_weighted_utility", "best_single_point_normalized_hv", "first_k_hv", "first_k_ned",
                    "terminal_full_hv", "terminal_full_ned", "dense_internal_auc")
    for key in sorted(p_runs):
        p = json.loads(Path(p_runs[key]["path"]).read_text())
        c = json.loads(Path(c_runs[key]["path"]).read_text())
        same = p["initial_state"] == c["initial_state"] and len(p["points"]) == len(c["points"])
        for pp, cp in zip(p["points"], c["points"]):
            same = same and pp["budget"] == cp["budget"] and pp["sequence"] == cp["sequence"]
            same = same and np.allclose(pp["objectives"], cp["objectives"], rtol=0, atol=1e-12)
        same = same and p["unique_scorer_calls"] == c["unique_scorer_calls"]
        check(f"raw_points_{key}", same)
        pd, cd = p_runs[key], c_runs[key]
        check(f"metrics_{key}", all(close(pd[m], cd[m]) for m in metric_names))
        if key[2].endswith("pool_first_b11") or key[2].endswith("pool_best_b11"):
            check(f"pool_semantics_{key}", all(p[k] == c[k] for k in ("initialization_pool", "pool_generation_seeds",
                                                                         "pool_selection_index", "initial_state", "search_normalization",
                                                                         "common_input", "native_calibration_read_before_search",
                                                                         "external_initialization", "terminal_stop", "terminal_evaluations", "cache_hits")))
            check(f"initial_metrics_{key}", close(pd["initial_normalized_weighted_utility"], cd["initial_normalized_weighted_utility"])
                  and close(pd["initial_single_point_normalized_hv"], cd["initial_single_point_normalized_hv"]))
    check("pool_identity", production["pool_identity"] == clean["pool_identity"])
    p_tests = {(t["family"], t["endpoint"]): t for t in production["tests"]}
    c_tests = {(t["family"], t["endpoint"]): t for t in clean["tests"]}
    check("test_key_identity", set(p_tests) == set(c_tests))
    for key in sorted(p_tests):
        p, c = p_tests[key], c_tests[key]
        same = close(p["effect"], c["effect"]) and close(p["sign_flip_p"], c["sign_flip_p"])
        same = same and np.allclose(p["ci95"], c["ci95"], rtol=0, atol=1e-12)
        same = same and np.allclose(p["per_record_effects"], c["per_record_effects"], rtol=0, atol=1e-12)
        same = same and np.allclose(p["seed_mean_effects"], c["seed_mean_effects"], rtol=0, atol=1e-12)
        if p["confirmatory"]:
            same = same and close(p["holm_p"], c["holm_p"]) and p["supported_advantage"] == c["supported_advantage"]
        check(f"inference_{key}", same)
    check("decision_identity", production["decision"] == clean["decision"]
          and production["primary_family_pass"] == clean["primary_family_pass"]
          and production["primary_gate_passed"] == clean["primary_gate_passed"]
          and production["common_input_actual_set_gate_passed"] == clean["common_input_actual_set_gate_passed"])
    check("absolute_performance_identity", all(close(production["absolute_performance"][arm][endpoint], clean["absolute_performance"][arm][endpoint])
                                                for arm in production["absolute_performance"] for endpoint in production["absolute_performance"][arm]))
    check("external_reference_identity", all(close(production["external_reference"][record][endpoint], clean["external_reference"][record][endpoint])
                                              for record in production["external_reference"]
                                              for endpoint in ("best_normalized_weighted_utility", "best_single_point_normalized_hv", "first_k_hv", "first_k_ned")))
    for field in ("scientific_gate_passed", "external_sota_authorized", "time_matched_comparison",
                  "functional_untouched_evaluated", "rk_g1_pass", "manuscript_submittable"):
        check(f"boundary_{field}", production[field] is False and clean[field] is False)
    result = {"schema": "a8-rk41-clean-reproduction-closeout-v1", "production": str(production_path),
              "production_sha256": sha(production_path), "clean": str(clean_path), "clean_sha256": sha(clean_path),
              "production_independent": str(independent_path), "production_independent_sha256": sha(independent_path),
              "production_code_commit": production["code_commit"], "clean_code_commit": clean["code_commit"],
              "decision": production["decision"], "primary_family_pass": production["primary_family_pass"],
              "common_input_actual_set_gate_passed": production["common_input_actual_set_gate_passed"],
              "scientific_gate_passed": False, "external_sota_authorized": False, "time_matched_comparison": False,
              "functional_untouched_evaluated": False, "rk_g1_pass": False, "manuscript_submittable": False,
              "timing_fields_excluded": True, "run_file_hashes_excluded": True,
              "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
              "n_checks": len(checks), "n_pass": sum(c["passed"] for c in checks), "checks": checks}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({k: result[k] for k in ("status", "n_checks", "n_pass", "decision", "primary_family_pass")}))
    if result["status"] != "PASS":
        for item in checks:
            if not item["passed"]:
                print("FAIL", item)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
