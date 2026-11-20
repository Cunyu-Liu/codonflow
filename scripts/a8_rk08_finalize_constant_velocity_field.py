#!/usr/bin/env python3
"""Fail-closed scientific closeout for the RK08 constant velocity-field control."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    protocol_path = args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    production_path = Path(protocol["audit_output"])
    independent_path = Path(protocol["independent_output"])
    output = root / "audits/20261120/RK08/constant_velocity_field_finalization_v1.json"
    if output.exists():
        raise FileExistsError(output)
    production = json.loads(production_path.read_text())
    independent = json.loads(independent_path.read_text())
    original = json.loads((root / protocol["source_run_summary"]["path"]).read_text())
    preparation = json.loads((root / "audits/20261120/RK08/constant_velocity_field_preparation_v5.json").read_text())
    checks = []

    def check(name: str, condition: bool, detail) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("protocol/hash", production["protocol_sha256"] == sha256(protocol_path) == independent["protocol_sha256"], production["protocol_sha256"])
    check("preparation/pass", preparation["status"] == "PASS_CONSTANT_VELOCITY_PREPARATION" and preparation["failed_count"] == 0, preparation["status"])
    check("preparation/checks", preparation["check_count"] == preparation["passed_count"] == 18, preparation["check_count"])
    check("production/pass", production["status"] == "PASS_CONSTANT_VELOCITY_FIELD_PRODUCTION", production["status"])
    check("independent/pass", independent["status"] == "PASS_CONSTANT_VELOCITY_INDEPENDENT" and independent["failed_count"] == 0, independent["status"])
    check("independent/all_checks", independent["check_count"] == independent["passed_count"], independent["check_count"])
    check("independent/numeric_delta", independent["max_numeric_delta"] <= 1e-12, independent["max_numeric_delta"])
    check("independent/production_hash", independent["production_sha256"] == sha256(production_path), independent["production_sha256"])
    check("support/recomputed", production["support"] == independent["recomputed_support"], production["support"])
    check("primary/recomputed", set(production["primary_comparisons"]) == set(independent["recomputed_primary_comparisons"]) and independent["max_numeric_delta"] <= 1e-12, "all comparison fields independently checked within 1e-12")
    check("cost/no_training", production["cost"]["new_model_training_runs"] == 0 and production["cost"]["new_checkpoint_selection_runs"] == 0, production["cost"])
    check("cost/no_scorer_or_forward", production["cost"]["unique_scorer_calls"] == 0 and production["cost"]["model_forward_passes"] == 0, production["cost"])
    check("field/train_only", protocol["constant_field"]["fit_split"] == "train" and protocol["constant_field"]["fit_dataset"] == "Mohammad16", protocol["constant_field"])
    check("field/no_sequence", not protocol["constant_field"]["sequence_features"] and not protocol["constant_field"]["codon_identity_features"], "sequence/codon identity excluded")
    check("field/no_evaluation_fit", protocol["constant_field"]["evaluation_target_access_for_fit"] is False, False)
    check("gate/original_negative", original["velocity_mechanism_pass"] is False and production["gates"]["velocity_mechanism_pass"] is False, False)
    check("gate/rk_g1_closed", production["gates"]["rk_g1_pass"] is False and independent["gates"]["rk_g1_pass"] is False, False)
    check("gate/no_functional", production["gates"]["functional_untouched_evaluated"] is False, False)
    check("gate/no_generator", production["gates"]["generator_training_authorized"] is False, False)
    check("gate/no_sota", production["gates"]["external_sota_claim_authorized"] is False, False)
    artifact_root = Path(protocol["artifact_root"])
    for name in ("production_report", "independent_report"):
        audit = production_path if name == "production_report" else independent_path
        team = artifact_root / f"{name}.json"
        check(f"artifact/{name}_bytes", team.read_bytes() == audit.read_bytes(), str(team))
    for key in ("per_transcript_metrics", "constant_field"):
        path = Path(production["artifacts"][key])
        check(f"artifact/{key}_hash", sha256(path) == production["artifacts"][f"{key}_sha256"], str(path))
    for version in range(1, 5):
        correction_path = root / f"audits/20261120/RK08/constant_velocity_field_correction_v{version}.json"
        correction = json.loads(correction_path.read_text())
        check(f"correction/v{version}_protocol_unchanged", correction["scientific_protocol_changed"] is False, correction["status"])
        check(f"correction/v{version}_gates_unchanged", correction["endpoint_or_gate_changed"] is False, False)
        failure_log = root / correction["failure_log"]
        check(f"correction/v{version}_log_hash", failure_log.is_file() and sha256(failure_log) == correction["failure_log_sha256"], correction["failure_log_sha256"])
    unit_log = root / "audits/20261120/RK08/constant_velocity_field_unit_tests_v5.log"
    check("tests/latest_ten_passed", "10 passed" in unit_log.read_text(), str(unit_log))
    failed = [row for row in checks if not row["pass"]]
    report = {
        "schema_version": "a8-rk08-constant-velocity-field-finalization-v1",
        "status": "PASS_CONSTANT_VELOCITY_FIELD_CLOSEOUT" if not failed else "FAIL_CONSTANT_VELOCITY_FIELD_CLOSEOUT",
        "check_count": len(checks),
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "failed_checks": failed,
        "checks": checks,
        "protocol_sha256": sha256(protocol_path),
        "production_sha256": sha256(production_path),
        "independent_sha256": sha256(independent_path),
        "support": production["support"],
        "scientific_conclusion": "No frozen comparison met both endpoint-wise support criteria. The constant-field diagnostic does not rescue the learned model, the ridge baseline, or the original model-ridge mechanism claim.",
        "velocity_mechanism_pass": False,
        "rk_g1_pass": False,
        "functional_untouched_evaluated": False,
        "generator_training_authorized": False,
        "external_sota_claim_authorized": False,
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    team_output = artifact_root / "finalization_report.json"
    team_output.write_bytes(output.read_bytes())
    print(json.dumps({key: report[key] for key in ("status", "check_count", "passed_count", "failed_count", "support")}, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
