#!/usr/bin/env python3
"""Finalize the bounded RK09 mathematical-kernel evidence bundle."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--initial-production-failure", type=Path, required=True)
    parser.add_argument("--initial-independent-failure", type=Path, required=True)
    parser.add_argument("--unit-console", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    initial_production = json.loads(args.initial_production_failure.read_text())
    initial_independent = json.loads(args.initial_independent_failure.read_text())
    unit = args.unit_console.read_text(errors="replace")
    checks = []

    def check(name, condition, detail):
        checks.append({"id": name, "pass": bool(condition), "detail": detail})

    check("protocol_hash", production["protocol_sha256"] == independent["protocol_sha256"] == sha(args.protocol), "one frozen protocol across production and independent reports")
    check("implementation_hash", production["implementation_sha256"] == independent["implementation_sha256"] == sha(args.implementation), "one implementation across production and independent reports")
    check("production_complete", production["all_pass"] and production["checks_passed"] == production["checks_total"] == 22, "22/22 production checks")
    check("independent_complete", independent["all_pass"] and independent["checks_passed"] == independent["checks_total"] == 16, "16/16 independent checks")
    check("production_identity", independent["production_sha256"] == sha(args.production), "independent verifier read the final production report")
    check("naive_bias_reproduced", abs(production["metrics"]["naive_two_step_total_variation_vs_uniform"] - independent["independent_metrics"]["naive_two_step_total_variation"]) <= 1e-14, "two-step TV agrees")
    check("all_paths_reproduced", production["metrics"]["telescope"]["path_count"] == independent["independent_metrics"]["path_count"] == 14641, "14,641 paths independently enumerated")
    check("telescope_exact", max(production["metrics"]["telescope"]["max_telescope_error"], independent["independent_metrics"]["max_path_telescope_error"]) <= 1e-12, "path telescoping within 1e-12")
    check("endpoint_exact", max(production["metrics"]["telescope"]["max_endpoint_reconstruction_error"], independent["independent_metrics"]["max_endpoint_recovery_error"]) <= 1e-12, "endpoint reconstruction within 1e-12")
    failed_production = {row["id"] for row in initial_production["checks"] if not row["pass"]}
    check("initial_production_failure_retained", initial_production["checks_passed"] == 19 and initial_production["checks_total"] == 22 and failed_production == {"path_logprob_telescope", "path_endpoint_reconstruction", "event_time_monte_carlo"}, "initial 19/22 report and three failed checks retained")
    failed_independent = {row["id"] for row in initial_independent["checks"] if not row["pass"]}
    check("initial_independent_failure_retained", initial_independent["checks_passed"] == 15 and initial_independent["checks_total"] == 16 and failed_independent == {"forward_stop_mask_reference"}, "initial independent 15/16 mask failure retained")
    test_count = re.search(r"Ran (\d+) tests", unit)
    check("unit_tests", bool(test_count and test_count.group(1) == "10" and re.search(r"^OK$", unit, re.MULTILINE)), "10 unittest tests passed")
    check("scope_unchanged", all(value is False for value in production["prohibited_claims"].values()) and not any(protocol["prohibited_claims"].values()), "no training, functional, generation, RK-G1 or SOTA authorization")
    check("negative_history_preserved", not initial_production["all_pass"] and not initial_independent["all_pass"] and production["all_pass"] and independent["all_pass"], "both failed histories and both corrected final reports coexist")

    result = {
        "schema": "a8-rk09-minimal-codonflow-finalization-v1",
        "protocol_id": protocol["protocol_id"],
        "evidence_sha256": {
            "protocol": sha(args.protocol),
            "implementation": sha(args.implementation),
            "production": sha(args.production),
            "independent": sha(args.independent),
            "initial_production_failure": sha(args.initial_production_failure),
            "initial_independent_failure": sha(args.initial_independent_failure),
            "unit_console": sha(args.unit_console),
        },
        "checks": checks,
        "checks_passed": sum(row["pass"] for row in checks),
        "checks_total": len(checks),
        "all_pass": all(row["pass"] for row in checks),
        "scientific_status": "mathematical_kernel_verified_only",
        "model_training_executed": False,
        "functional_or_generation_performance_evaluated": False,
        "rk_g1_gate_modified": False,
        "expensive_generation_authorized": False,
        "sota_claimed": False,
    }
    temporary = args.report.with_name(args.report.name + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.report)
    print(json.dumps({"all_pass": result["all_pass"], "checks": f"{result['checks_passed']}/{result['checks_total']}", "report": str(args.report)}))
    if not result["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
