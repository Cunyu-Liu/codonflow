#!/usr/bin/env python3
"""Finalize the independently verified RK04 sequence-OOD data contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True)
    parser.add_argument("--failed-verification", type=Path, required=True)
    parser.add_argument("--unit-test-log", type=Path, required=True)
    parser.add_argument("--production-script", type=Path, required=True)
    parser.add_argument("--verifier-script", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    verification = json.loads(args.verification.read_text())
    failed = json.loads(args.failed_verification.read_text())
    unit_log = args.unit_test_log.read_text()
    checks = []

    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})

    check("production_summary_pending_independent_status_preserved", summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("independent_verification_pass_37_of_37", verification["status"] == "PASS" and verification["checks_passed"] == 37 and verification["checks_total"] == 37)
    check("initial_verifier_assumption_failure_retained", failed["status"] == "FAIL" and failed["checks_passed"] == 35 and failed["checks_total"] == 36)
    check("unit_tests_13_pass", "Ran 13 tests" in unit_log and "OK" in unit_log and "FAILED" not in unit_log)
    check("production_script_hash_matches", sha256_file(args.production_script) == summary["production_code_sha256"])
    check("independent_report_production_hash_matches", sha256_file(args.production_script) == verification["production_script_sha256"])
    csv_path = Path(summary["artifacts"]["sequence_ood_csv"]["path"])
    norm_path = Path(summary["artifacts"]["train_only_normalization"]["path"])
    check("sequence_ood_csv_hash_matches", sha256_file(csv_path) == summary["artifacts"]["sequence_ood_csv"]["sha256"])
    check("normalization_hash_matches", sha256_file(norm_path) == summary["artifacts"]["train_only_normalization"]["sha256"])
    check("sequence_ood_not_evaluated", summary["sequence_ood_evaluated"] is False and verification["sequence_ood_evaluated"] is False)
    check("functional_untouched_not_evaluated", summary["functional_untouched_evaluated"] is False and verification["functional_untouched_evaluated"] is False)
    check("generator_not_authorized", summary["generator_training_authorized"] is False)
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema_version": "a8-rk04-sequence-ood-finalization-v1",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks_passed": passed, "checks_total": len(checks), "checks": checks,
        "summary": str(args.summary.resolve()), "summary_sha256": sha256_file(args.summary),
        "independent_verification": str(args.verification.resolve()), "independent_verification_sha256": sha256_file(args.verification),
        "failed_verification": str(args.failed_verification.resolve()), "failed_verification_sha256": sha256_file(args.failed_verification),
        "unit_test_log": str(args.unit_test_log.resolve()), "unit_test_log_sha256": sha256_file(args.unit_test_log),
        "production_script_sha256": sha256_file(args.production_script),
        "verifier_script_sha256": sha256_file(args.verifier_script),
        "sequence_ood_csv_sha256": sha256_file(csv_path), "normalization_sha256": sha256_file(norm_path),
        "counts": summary["counts"],
        "performance_evaluated": False, "sequence_ood_evaluated": False,
        "functional_untouched_evaluated": False, "generator_training_authorized": False,
        "scientific_scope": summary["scientific_scope"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + f".part.{os.getpid()}")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "failed": [c["name"] for c in checks if not c["pass"]]}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
