#!/usr/bin/env python3
"""Finalize only the bounded official EnsembleDesign evidence, not a main ranking."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import zipfile
from pathlib import Path

COMMIT = "cd9324f9574a754063d421e76670bc9fd7555324"
EXPECTED = {"seq1": -18.0, "seq2": -43.71, "seq3": -70.29}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repo.resolve()
    audit = root / "audits/20261118/RK05"
    paths = {
        "production": root / "scripts/a8_rk05_ensembledesign_official_smoke.py",
        "independent_verifier": root / "scripts/a8_rk05_verify_ensembledesign_official_smoke.py",
        "finalizer": root / "scripts/a8_rk05_finalize_ensembledesign_official_smoke.py",
        "unit_tests": root / "tests/test_a8_rk05_ensembledesign_official_smoke.py",
        "unit_test_log": audit / "ensembledesign_unit_tests.txt",
        "materialization": audit / "ensembledesign_materialization.json",
        "build": audit / "ensembledesign_build.json",
        "example_failed_v1": audit / "ensembledesign_official_example_smoke.json",
        "example": audit / "ensembledesign_official_example_smoke_v2.json",
        "example_independent": audit / "ensembledesign_official_example_independent_v2.json",
        "c01": audit / "ensembledesign_c01_smoke_v1.json",
        "c01_independent": audit / "ensembledesign_c01_independent_v1.json",
    }
    checks: list[dict] = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    missing = [name for name, path in paths.items() if not path.is_file()]
    check("required_evidence_present", not missing, {"missing": missing})
    if missing:
        result = {"status": "FAIL", "checks": checks}
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        raise SystemExit(1)
    materialization = load(paths["materialization"])
    build = load(paths["build"])
    failed_v1 = load(paths["example_failed_v1"])
    example = load(paths["example"])
    example_ind = load(paths["example_independent"])
    c01 = load(paths["c01"])
    c01_ind = load(paths["c01_independent"])
    with zipfile.ZipFile(materialization["archive"]) as archive:
        members = archive.infolist()
        unsafe_members = sum(Path(info.filename).is_absolute() or ".." in Path(info.filename).parts for info in members)
        symlink_members = sum(((info.external_attr >> 16) & 0o170000) == 0o120000 for info in members)
        archive_crc_pass = archive.testzip() is None
        archive_size_pass = len(members) == materialization["member_count"] and sum(info.file_size for info in members) == materialization["uncompressed_bytes"]
    source_ok = (materialization["commit"] == build["commit"] == example["commit"] == c01["commit"] == COMMIT
                 and materialization["crc_pass"] is True and archive_crc_pass and archive_size_pass
                 and unsafe_members == 0 and symlink_members == 0 and build["status"] == "BUILD_COMPLETE"
                 and not build["missing_binaries"] and build["reporting_recovery"]["initial_logs_preserved"] is True)
    check("fixed_official_source_and_build", source_ok, {"commit": COMMIT, "archive_sha256": materialization["archive_sha256"], "archive_crc_pass": archive_crc_pass, "unsafe_members": unsafe_members, "symlink_members": symlink_members, "build_reporting_recovery": build["reporting_recovery"]})
    failure_preserved = (failed_v1["status"] == "FAILED" and failed_v1["returncode"] == 0
                         and "non-synonymous or stop-contract failure" in failed_v1["error"]
                         and Path(failed_v1["stdout_path"]).is_file() and Path(failed_v1["stderr_path"]).is_file())
    check("failed_stop_contract_v1_preserved", failure_preserved, {"v1_status": failed_v1["status"], "official_returncode": failed_v1["returncode"], "error": failed_v1["error"]})
    bounded_params = {"beam_size": 100, "lr": 0.03, "epsilon": 0.5, "num_iters": 3, "num_runs": 2, "num_threads": 4}
    bounded_ok = (example["parameters"] == c01["parameters"] == bounded_params
                  and example["protocol"] == c01["protocol"] == "a8_rk05_ensembledesign_official_smoke_v2"
                  and example["run_count"] == 6 and c01["run_count"] == 2
                  and example["input_record_count"] == 3 and c01["input_record_count"] == 1)
    check("bounded_protocol_complete", bounded_ok, {"parameters": bounded_params, "example_runs": example["run_count"], "c01_runs": c01["run_count"]})
    example_ok = (example["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE" and example["official_example"]["pass"] is True
                  and all(item["best_official_efe_kcal_mol"] == EXPECTED[item["record_id"]] for item in example["records"]))
    check("official_example_exact", example_ok, {"best_efe": {item["record_id"]: item["best_official_efe_kcal_mol"] for item in example["records"]}, "elapsed_s": example["total_elapsed_s"]})
    c01_ok = (c01["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE" and c01["benchmark"]["record_id"] == "C01H6.8b.1"
              and c01["records"][0]["protein_length_aa"] == 135)
    c01_ok = c01_ok and len(c01["records"][0]["best_sequence_rna"]) == 405
    check("c01_bounded_execution", c01_ok, {"record_id": c01["benchmark"]["record_id"], "protein_length_aa": c01["records"][0]["protein_length_aa"], "best_efe": c01["records"][0]["best_official_efe_kcal_mol"], "elapsed_s": c01["total_elapsed_s"]})
    independent_ok = (example_ind["status"] == c01_ind["status"] == "PASS"
                      and example_ind["passed_checks"] == example_ind["check_count"]
                      and c01_ind["passed_checks"] == c01_ind["check_count"]
                      and example_ind["source_report_sha256"] == sha(paths["example"])
                      and c01_ind["source_report_sha256"] == sha(paths["c01"])
                      and example_ind["independent_production_import"] is False and c01_ind["independent_production_import"] is False)
    check("independent_raw_and_scorer_verification", independent_ok, {"example": f"{example_ind['passed_checks']}/{example_ind['check_count']}", "c01": f"{c01_ind['passed_checks']}/{c01_ind['check_count']}", "example_max_production_delta": example_ind["max_numeric_delta"], "c01_max_production_delta": c01_ind["max_numeric_delta"]})
    cost_ok = (all(math.isfinite(r["total_elapsed_s"]) and r["total_elapsed_s"] > 0 for r in [example, c01])
               and all(r["forward_calls"] is None and r["per_run_elapsed_s"] is None for r in [example, c01])
               and all(r["official_generator_run_count"] == r["lineardesign_initialization_call_count"] == r["linearpartition_scoring_call_count"] == r["run_count"] for r in [example, c01]))
    check("aggregate_cost_ledger", cost_ok, {"example_elapsed_s": example["total_elapsed_s"], "c01_elapsed_s": c01["total_elapsed_s"], "per_run_elapsed_s": None})
    test_log = paths["unit_test_log"].read_text()
    test_match = re.search(r"Ran (\d+) tests?", test_log)
    tests_ok = test_match is not None and int(test_match.group(1)) >= 11 and re.search(r"^OK$", test_log, re.MULTILINE) is not None
    check("unit_tests", tests_ok, {"test_count": int(test_match.group(1)) if test_match else None})
    no_secrets = not any(token in paths[key].read_text() for key in ["production", "independent_verifier", "unit_tests"] for token in ["hi,Rz33", "BEGIN OPENSSH PRIVATE KEY", "BEGIN RSA PRIVATE KEY"])
    check("no_credentials_in_code", no_secrets, {"checked_files": ["production", "independent_verifier", "unit_tests"]})
    scope_ok = all(r["main_baseline_comparison"] is False and r["matched_lineardesign_comparison"] is False and r["dense_budget_complete"] is False and r["functional_ood"] is False and r["sota_claim"] is False for r in [example, c01])
    check("scientific_scope", scope_ok, {"bounded_official_smoke_closed": True, "main_baseline_matrix_closed": False, "matched_lineardesign_comparison": False, "sota_claim": False})
    passed = sum(c["pass"] for c in checks)
    result = {
        "protocol": "a8_rk05_ensembledesign_finalization_v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if passed == len(checks) else "FAIL",
        "scope": "bounded_official_example_and_single_c01_smoke_closed_not_main_comparison",
        "task_completion_authorized": passed == len(checks),
        "commit": COMMIT,
        "check_count": len(checks),
        "passed_checks": passed,
        "checks": checks,
        "artifacts": {name: {"path": str(path), "sha256": sha(path)} for name, path in paths.items()},
        "main_baseline_matrix_closed": False,
        "functional_ood_closed": False,
        "sota_claim": False,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "passed": passed, "total": len(checks), "task_completion_authorized": result["task_completion_authorized"]}, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
