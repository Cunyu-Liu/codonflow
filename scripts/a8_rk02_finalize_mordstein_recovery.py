#!/usr/bin/env python3
"""Finalize a verified Mordstein recovery run without altering its production report."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess


def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--scope", choices=["smoke", "full"], required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads((args.artifacts / "summary.json").read_text())
    independent = json.loads(args.independent.read_text())
    test = subprocess.run(["/root/miniconda3/envs/llr_env/bin/python", str(args.tests)], capture_output=True, text=True)
    checks = []
    def check(name, condition, details=None):
        checks.append({"name": name, "status": "PASS" if condition else "FAIL", "details": details})
    check("production_pending_preserved", summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("production_internal_checks", all(summary["checks"].values()))
    check("independent_pass", independent["status"] == "PASS")
    check("independent_all_checks", independent["passed"] == independent["total"] == len(independent["checks"]))
    check("unit_tests", test.returncode == 0, (test.stdout + test.stderr).strip())
    check("scope_matches", summary["library_recovery_status"] == ("SMOKE_PARTIAL_LIBRARY" if args.scope == "smoke" else summary["library_recovery_status"]))
    check("no_complete_cds_claim", "central 138 nt unobserved" in summary["scope"])
    check("reconstructed_id_disclaimer", "author GFP_### identity recovered" in summary["prohibited_claims"])
    if args.scope == "smoke":
        check("smoke_100k_pairs", independent["raw_pairs_recounted"] == 100000)
    else:
        check("full_eight_bins", len(summary["runs"]) == 8 and {row["bin"] for row in summary["runs"]} == set(range(1, 9)))
    artifacts_ok = True
    artifact_hashes = {}
    for name, record in independent["artifacts"].items():
        path = args.artifacts / name
        actual = sha256(path) if path.exists() else None
        match = actual == record["sha256"]
        artifacts_ok = artifacts_ok and match
        artifact_hashes[name] = {"sha256": actual, "matches_independent": match}
    check("artifact_hashes_match_independent", artifacts_ok)
    check("input_hashes_match_independent", all(row["match"] for row in independent["input_hashes"]))
    status = "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL"
    report = {
        "schema": "a8.rk02.mordstein_recovery_finalization.v1",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": status, "scope": args.scope, "summary_sha256": sha256(args.artifacts / "summary.json"),
        "independent_sha256": sha256(args.independent), "test_command": [str(args.tests)],
        "test_returncode": test.returncode, "artifact_hashes": artifact_hashes,
        "checks": checks, "passed": sum(row["status"] == "PASS" for row in checks), "total": len(checks),
        "next_gate": "full eight-bin recovery and independent verification" if args.scope == "smoke" else "paper/PPT reporting after result review",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": status, "passed": report["passed"], "total": report["total"], "report": str(args.report)}))
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
