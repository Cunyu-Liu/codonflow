#!/usr/bin/env python3
"""Final acceptance checks for the full RK08 function comparison."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/home/codonflow-a8-rk")
    parser.add_argument("--independent", required=True)
    parser.add_argument("--unit-tests", required=True)
    parser.add_argument("--comparison-dir", required=True)
    parser.add_argument("--all-dir", required=True)
    parser.add_argument("--none-dir", required=True)
    parser.add_argument("--all-retrain-dir", required=True)
    parser.add_argument("--none-retrain-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    independent = json.loads(Path(args.independent).read_text())
    tests = json.loads(Path(args.unit_tests).read_text())
    summary = json.loads(Path(args.comparison_dir, "comparison_summary.json").read_text())
    checks = {}

    def check(name, condition):
        checks[name] = bool(condition)

    check("independent_verification_pass", independent["status"] == "PASS")
    check("independent_no_failures", independent["failures"] == [])
    check("unit_tests_7_of_7", tests["passed"] == 7 and tests["failed"] == 0)
    check("preregistered_protocol", summary["protocol"] == "a8_rk08_full_function_paired_v1_preregistered_before_result_readout")
    check("primary_endpoint_locked", summary["primary_endpoint"] == "sequence_ood cluster_balanced_mse")
    check("secondary_endpoint_locked", summary["secondary_endpoint"] == "sequence_ood row_spearman")
    check("bootstrap_2000", summary["bootstrap"]["replicates"] == 2000)
    check("bootstrap_cluster_level", summary["bootstrap"]["method"] == "operational_protein_cluster_resampling")
    check("no_generator_authorization", summary["expensive_generation_authorized"] is False)
    check("no_sota_claim", summary["sota_claimed"] is False)
    check("cross_protein_scope_retained", "not fixed-protein synonymous mechanism" in summary["scientific_scope"])
    check("gate_matches_independent", summary["rk_g1_pass"] == independent["rk_g1_pass"])
    check("comparison_has_12_tests", len(summary["comparisons"]) == 12)
    check("both_models_share_parameters", summary["costs"]["ribokinetic_all"]["parameters"] == summary["costs"]["ribokinetic_none"]["parameters"])
    check("deterministic_all", summary["costs"]["ribokinetic_all"]["deterministic_algorithms"] is True)
    check("deterministic_none", summary["costs"]["ribokinetic_none"]["deterministic_algorithms"] is True)
    check("math_attention_all", summary["costs"]["ribokinetic_all"]["sdp_backends"] == {"flash": False, "mem_efficient": False, "math": True})
    check("math_attention_none", summary["costs"]["ribokinetic_none"]["sdp_backends"] == {"flash": False, "mem_efficient": False, "math": True})
    for name, directory in [("all", args.all_dir), ("none", args.none_dir), ("all_retrain", args.all_retrain_dir), ("none_retrain", args.none_retrain_dir)]:
        root = Path(directory)
        run = json.loads((root / "run_summary.json").read_text())
        check(f"{name}_full_rows", run["rows"] == {"train": 4019, "dev": 503, "test": 490, "sequence_ood": 1336})
        check(f"{name}_checkpoint_present", (root / "best.pt").is_file())
        check(f"{name}_predictions_present", (root / "predictions.csv").is_file())
        check(f"{name}_checkpoint_hash", sha256(root / "best.pt") == run["hashes"]["checkpoint_sha256"])
    for name in ["comparison_summary.json", "metrics.csv", "paired_comparisons.csv", "bootstrap_deltas.csv.gz"]:
        check(f"comparison_artifact_{name}", Path(args.comparison_dir, name).is_file())
    for path in [
        "src/codonflow/models/ribokinetic.py",
        "src/codonflow/data/ribokinetic.py",
        "scripts/a8_rk08_train_ribokinetic.py",
        "scripts/a8_rk08_compare_full_function.py",
        "scripts/a8_rk08_verify_full_function.py",
        "scripts/a8_rk08_run_full_function.sh",
        "configs/a8_rk08_full_function_all_config.json",
        "configs/a8_rk08_full_function_none_config.json",
        "tests/test_a8_rk08_ribokinetic.py",
        "tests/test_a8_rk08_full_function.py",
    ]:
        check(f"tracked_source_present_{path}", Path(args.repo, path).is_file())
    failures = [name for name, passed in checks.items() if not passed]
    head = subprocess.run(["git", "-C", args.repo, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    report = {
        "status": "PASS" if not failures else "FAIL",
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
        "checks": checks,
        "git_head_at_finalization": head,
        "rk_g1_pass": summary["rk_g1_pass"],
        "manuscript_submittable": False,
        "generator_closed": False,
        "velocity_ood_closed": False,
        "sota_closed": False,
        "conclusion": "Full all/none comparison and paired uncertainty are reproducible. This does not close RK-G0, velocity OOD, the generator, or SOTA.",
    }
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks_passed": report["checks_passed"], "checks_total": report["checks_total"], "failures": failures, "rk_g1_pass": report["rk_g1_pass"]}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
