#!/usr/bin/env python3
"""Finalize only the verified bounded LinearDesign official execution scope."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    materialization = json.loads(args.materialization.read_text())
    build = json.loads(args.build.read_text())
    smoke = json.loads(args.smoke.read_text())
    independent = json.loads(args.independent.read_text())
    checks = []

    def add(name: str, ok: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    commit = "f0126ca89a8b853088b4bccfd2cc8c378d3678be"
    add("fixed_commit", materialization["commit"] == build["commit"] == smoke["commit"] == commit, commit)
    add("archive_crc_and_hash", materialization["crc_pass"] is True and sha(Path(materialization["archive"])) == materialization["archive_sha256"], materialization["archive_sha256"])
    add("clean_build_and_official_example", build["returncode"] == 0 and build["official_example"]["pass"] is True and sha(Path(build["binary"])) == build["binary_sha256"], build["binary_sha256"])
    add("bounded_execution", smoke["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE" and smoke["run_count"] == 3 and len(smoke["runs"]) == 3, {"record_id": smoke["record_id"], "lambdas": [r["lambda"] for r in smoke["runs"]]})
    add("identity_and_scorers", all(r["protein_identity_pass"] and r["cai_abs_delta_from_rounded_official"] <= 0.00101 and r["mfe_abs_delta_from_rounded_official"] <= 0.051 for r in smoke["runs"]), {"max_cai_delta": max(r["cai_abs_delta_from_rounded_official"] for r in smoke["runs"]), "max_mfe_delta": max(r["mfe_abs_delta_from_rounded_official"] for r in smoke["runs"])})
    add("independent_verification", independent["status"] == "PASS" and independent["passed_checks"] == independent["check_count"] and independent["independent_production_import"] is False and independent["source_report_sha256"] == sha(args.smoke), {"passed": independent["passed_checks"], "total": independent["check_count"], "max_numeric_delta": independent["max_numeric_delta"]})
    add("bounded_costs", smoke["forward_calls"] is None and smoke["total_elapsed_s"] > 0 and all(r["elapsed_s"] > 0 for r in smoke["runs"]), smoke["total_elapsed_s"])
    scientific = {"official_fixed_source_built": True, "bounded_single_record_smoke_complete": True, "main_baseline_comparison": False, "dense_budget_complete": False, "functional_ood": False, "cdgb_assessed": False, "sota_claim": False}
    add("scientific_boundaries", smoke["main_baseline_comparison"] is False and smoke["sota_claim"] is False and scientific["cdgb_assessed"] is False, scientific)
    passed = sum(c["pass"] for c in checks)
    status = "BOUNDED_LINEARDESIGN_OFFICIAL_SMOKE_VERIFIED" if passed == len(checks) else "FAIL"
    output = {"protocol": "a8_rk05_lineardesign_finalization_v1", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "status": status, "check_count": len(checks), "passed_checks": passed, "checks": checks, "record_id": smoke["record_id"], "run_count": smoke["run_count"], "total_elapsed_s": smoke["total_elapsed_s"], "unique_output_sequences": smoke["unique_output_sequences"], "science_flags": scientific, "ppt_record_ready": passed == len(checks), "source_artifacts": {"materialization": {"path": str(args.materialization), "sha256": sha(args.materialization)}, "build": {"path": str(args.build), "sha256": sha(args.build)}, "smoke": {"path": str(args.smoke), "sha256": sha(args.smoke)}, "independent": {"path": str(args.independent), "sha256": sha(args.independent)}}}
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"status": status, "passed": passed, "total": len(checks)}, indent=2))
    if status == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
