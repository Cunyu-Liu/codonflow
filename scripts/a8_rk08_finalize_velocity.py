#!/usr/bin/env python3
"""Finalize reproducibility status without overriding a negative mechanism gate."""
import argparse
import json
import subprocess
from pathlib import Path

from codonflow.data.ribokinetic import file_sha256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-audit", required=True)
    parser.add_argument("--run-summary", required=True)
    parser.add_argument("--verification", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.data_audit).read_text())
    run = json.loads(Path(args.run_summary).read_text())
    verification = json.loads(Path(args.verification).read_text())
    source_hashes_match = all(
        file_sha256(path) == value
        for path, value in [
            ("scripts/a8_rk08_prepare_velocity.py", verification["source_hashes"]["prepare_script_sha256"]),
            ("scripts/a8_rk08_train_velocity.py", verification["source_hashes"]["train_script_sha256"]),
            ("scripts/a8_rk08_verify_velocity.py", verification["source_hashes"]["verify_script_sha256"]),
        ]
    )
    checks = {
        "independent_verification_pass": verification["status"] == "PASS",
        "independent_no_failures": not verification["failures"],
        "formal_uncapped_data": data["max_records_per_study"] is None,
        "primary_exact_cds_disjoint": data["subtelny14_exact_cds_overlap_with_any_mohammad16_split"] == 0,
        "functional_ood_not_accessed": not data["functional_ood_accessed"],
        "no_homology_overclaim": not data["homology_ood_claimed"],
        "source_hashes_match": source_hashes_match,
        "mechanism_gate_consistent": run["velocity_mechanism_pass"] == verification["velocity_mechanism_pass"],
        "no_rk_g1_overclaim": not run["rk_g1_pass"] and not verification["rk_g1_pass"],
        "no_generator_authorization": not run["expensive_generation_authorized"] and not verification["expensive_generation_authorized"],
        "functional_transfer_remains_open": not run["functional_transfer_closed"] and not verification["functional_transfer_closed"],
        "cross_head_consistency_remains_open": not run["cross_head_consistency_closed"] and not verification["cross_head_consistency_closed"],
    }
    failures = [name for name, passed in checks.items() if not passed]
    gate = bool(verification["velocity_mechanism_pass"])
    report = {
        "status": "PASS" if not failures else "FAIL",
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "checks": checks,
        "failures": failures,
        "velocity_mechanism_pass": gate,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "functional_transfer_closed": False,
        "cross_head_consistency_closed": False,
        "git_head_at_finalization": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "conclusion": (
            "Velocity-proxy training and independent verification are reproducible; the primary OOD mechanism gate passed. "
            "This is not yet functional transfer, RK-G1, cross-head consistency, or generator authorization."
            if gate else
            "Velocity-proxy training and independent verification are reproducible, but the primary OOD mechanism gate did not pass. "
            "The negative or uncertain result is retained; no functional transfer or generator claim is authorized."
        ),
    }
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
