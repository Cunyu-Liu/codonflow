#!/usr/bin/env python3
"""Compare independent clean RK39 reproduction with production, excluding timings."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, payload: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", default="audits/20261122/RK39/rk39_common_input_actual_set_v1.json")
    parser.add_argument("--clean", default="audits/20261122/RK39/rk39_common_input_actual_set_clean_v1.json")
    parser.add_argument("--production-independent", default="audits/20261122/RK39/rk39_common_input_actual_set_independent_v1.json")
    parser.add_argument("--output", default="audits/20261122/RK39/rk39_clean_reproduction_closeout_v1.json")
    args = parser.parse_args()
    resolve = lambda value: Path(value) if Path(value).is_absolute() else ROOT / value
    production_path, clean_path, independent_path, output_path = map(
        resolve, [args.production, args.clean, args.production_independent, args.output])
    production = json.loads(production_path.read_text())
    clean = json.loads(clean_path.read_text())
    independent = json.loads(independent_path.read_text())
    checks = []

    def add(name, condition, detail=""):
        checks.append({"name": name, "passed": bool(condition), "detail": str(detail)})

    add("production_complete", production["status"] == "PASS_COMPLETE_COMMON_INPUT_EVALUATION")
    add("clean_complete", clean["status"] == "PASS_COMPLETE_COMMON_INPUT_EVALUATION")
    add("production_independent_pass", independent["status"] == "PASS" and
        independent["n_pass"] == independent["n_checks"] and
        independent["summary_sha256"] == sha(production_path))
    add("same_protocol", production["protocol_sha256"] == clean["protocol_sha256"])
    add("same_inputs", all(production[key] == clean[key] for key in
                           ["benchmark_sha256", "external_matrix_sha256", "rscu_sha256"]))
    add("same_run_count", production["n_runs"] == clean["n_runs"] == 162)
    add("same_unique_calls", production["n_unique_scorer_calls"] == clean["n_unique_scorer_calls"] == 1782)
    add("clean_launch", clean["code_tracked_dirty_at_launch"] is False)
    add("clean_not_smoke", clean["smoke"] is False)

    def keyed(summary):
        return {(row["record_id"], int(row["seed"]), row["method"]): row for row in summary["runs"]}

    p_runs, c_runs = keyed(production), keyed(clean)
    add("same_run_keys", set(p_runs) == set(c_runs) and len(p_runs) == 162)
    for key in sorted(p_runs):
        p = json.loads(Path(p_runs[key]["path"]).read_text())
        c = json.loads(Path(c_runs[key]["path"]).read_text())
        add(f"{key}_initial", p["initial_state"] == c["initial_state"] and
            p["protein_only_template"] == c["protein_only_template"])
        add(f"{key}_budgets", [row["budget"] for row in p["points"]] == [row["budget"] for row in c["points"]] == list(range(1, 12)))
        add(f"{key}_sequences", [row["sequence"] for row in p["points"]] == [row["sequence"] for row in c["points"]])
        add(f"{key}_objectives", np.allclose([row["objectives"] for row in p["points"]],
                                              [row["objectives"] for row in c["points"]], rtol=0, atol=1e-12))
        add(f"{key}_matched_metrics", p["matched_linear_design_k"] == c["matched_linear_design_k"] and
            np.isclose(p["matched_actual_set"]["hypervolume_normalized"], c["matched_actual_set"]["hypervolume_normalized"], rtol=0, atol=1e-12) and
            np.isclose(p["matched_actual_set"]["pairwise_ned"], c["matched_actual_set"]["pairwise_ned"], rtol=0, atol=1e-12))

    p_tests = {(row["method"], row["endpoint"]): row for row in production["tests"]}
    c_tests = {(row["method"], row["endpoint"]): row for row in clean["tests"]}
    add("same_test_keys", set(p_tests) == set(c_tests) and len(p_tests) == 6)
    for key in sorted(p_tests):
        p, c = p_tests[key], c_tests[key]
        add(f"test_{key}", all([
            np.isclose(p["effect"], c["effect"], rtol=0, atol=1e-12),
            np.allclose(p["ci95"], c["ci95"], rtol=0, atol=1e-12),
            p["sign_flip_p"] == c["sign_flip_p"], p["holm_p"] == c["holm_p"],
            np.allclose(p["per_record_effects"], c["per_record_effects"], rtol=0, atol=1e-12),
            np.allclose(p["seed_mean_effects"], c["seed_mean_effects"], rtol=0, atol=1e-12),
            p["supported_advantage"] == c["supported_advantage"],
        ]))
    add("same_gate", production["primary_gate_passed"] == clean["primary_gate_passed"])
    add("same_decision", production["decision"] == clean["decision"], clean["decision"])
    add("same_boundaries", all(production[key] == clean[key] == False for key in
                                ["time_matched_comparison", "functional_untouched_evaluated", "untouched24_evaluated",
                                 "new_functional_labels_read", "dense_external_curve_inferred", "external_sota_authorized",
                                 "sota_claim", "rk_g1_pass", "manuscript_submittable", "scientific_gate_passed"]))
    n_pass = sum(row["passed"] for row in checks)
    payload = {
        "schema": "a8-rk39-clean-reproduction-closeout-v1",
        "production_summary": str(production_path),
        "production_summary_sha256": sha(production_path),
        "clean_summary": str(clean_path),
        "clean_summary_sha256": sha(clean_path),
        "production_independent": str(independent_path),
        "production_independent_sha256": sha(independent_path),
        "production_code_commit": production["code_commit"],
        "clean_code_commit": clean["code_commit"],
        "protocol_sha256": production["protocol_sha256"],
        "status": "PASS" if n_pass == len(checks) else "FAIL",
        "n_pass": int(n_pass), "n_checks": int(len(checks)),
        "comparison": "Production raw was independently rescored and verified. Clean raw initial states, sequences, budgets, objective vectors to 1e-12, actual-set metrics, paired inference, decision and scientific boundaries are compared exactly with that verified production; wall times and file hashes excluded. Independent verification therefore carries to identical clean raw without redundant third-party rescoring.",
        "decision": clean["decision"],
        "primary_gate_passed": clean["primary_gate_passed"],
        "scientific_gate_passed": False,
        "checks": checks,
    }
    atomic_json(output_path, payload)
    print(json.dumps({key: payload[key] for key in ["status", "n_pass", "n_checks", "decision", "primary_gate_passed"]}, indent=2))
    if payload["status"] != "PASS":
        print(json.dumps([row for row in checks if not row["passed"]][:30], indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
