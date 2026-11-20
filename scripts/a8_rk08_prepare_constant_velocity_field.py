#!/usr/bin/env python3
"""Fail-closed preparation checks before the RK08 constant-field readout."""
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
    parser.add_argument("--unit-test-log", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    protocol_path = args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    output = args.output or root / "audits/20261120/RK08/constant_velocity_field_preparation_v1.json"
    if not output.is_absolute():
        output = root / output
    if output.exists():
        raise FileExistsError(output)
    checks = []

    def check(name: str, condition: bool, detail) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("protocol/frozen", protocol["status"] == "FROZEN_BEFORE_CONSTANT_FIELD_READOUT", protocol["status"])
    check("protocol/six_primary_tests", len(protocol["primary_comparisons"]) * len(protocol["primary_metrics"]) == 6, 6)
    check("protocol/no_functional_access", protocol["boundaries"]["functional_untouched_evaluated"] is False, False)
    check("protocol/no_generator_authorization", protocol["boundaries"]["generator_training_authorized"] is False, False)
    check("protocol/original_gate_closed", protocol["boundaries"]["velocity_mechanism_pass_remains"] is False, False)
    for name in ("velocity_records", "frozen_predictions"):
        path = Path(protocol[name]["path"])
        actual = sha256(path)
        check(f"input/{name}_hash", actual == protocol[name]["sha256"], {"path": str(path), "sha256": actual})
    source = root / protocol["source_run_summary"]["path"]
    actual = sha256(source)
    check("input/source_summary_hash", actual == protocol["source_run_summary"]["sha256"], actual)
    unit_text = args.unit_test_log.read_text()
    check("tests/ten_passed", "10 passed" in unit_text, unit_text.strip().splitlines()[-1])
    check("readout/production_absent", not Path(protocol["audit_output"]).exists(), protocol["audit_output"])
    check("readout/independent_absent", not Path(protocol["independent_output"]).exists(), protocol["independent_output"])
    artifact_root = Path(protocol["artifact_root"])
    for filename in ("production_report.json", "independent_report.json", "per_transcript_metrics.csv.gz", "constant_field.json"):
        check(f"readout/{filename}_absent", not (artifact_root / filename).exists(), str(artifact_root / filename))
    code_hashes = {}
    for relative in (
        "scripts/a8_rk08_constant_velocity_field.py",
        "scripts/a8_rk08_verify_constant_velocity_field.py",
        "tests/test_a8_rk08_constant_velocity_field.py",
    ):
        path = root / relative
        code_hashes[relative] = sha256(path)
        check(f"code/{relative}_present", path.is_file(), code_hashes[relative])
    failed = [row for row in checks if not row["pass"]]
    report = {
        "schema_version": "a8-rk08-constant-velocity-field-preparation-v1",
        "status": "PASS_CONSTANT_VELOCITY_PREPARATION" if not failed else "FAIL_CONSTANT_VELOCITY_PREPARATION",
        "protocol_sha256": sha256(protocol_path),
        "code_sha256": code_hashes,
        "check_count": len(checks),
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "checks": checks,
        "constant_field_readout_started": False,
        "new_model_fits": 0,
        "new_checkpoint_selections": 0,
        "functional_untouched_evaluated": False,
        "generator_training_authorized": False,
        "rk_g1_pass": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "check_count", "passed_count", "failed_count")}, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
