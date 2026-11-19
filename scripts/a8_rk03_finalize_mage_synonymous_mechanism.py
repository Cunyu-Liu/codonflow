#!/usr/bin/env python3
"""Finalize the independently verified frozen MAGE dev no-go result."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--production-script", type=Path, required=True)
    parser.add_argument("--independent-script", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    protocol = json.loads(args.protocol.read_text())
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    artifact_root = Path(protocol["artifacts"]["large_artifact_root"])
    checks = []

    def check(name: str, passed: bool, evidence=None) -> None:
        checks.append({"check": name, "pass": bool(passed), "evidence": evidence})

    check("protocol_hash", production["protocol_sha256"] == sha256(args.protocol))
    check("independent_production_hash", independent["production_sha256"] == sha256(args.production))
    check("independent_pass", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] == 39, {"passed": independent["checks_passed"], "total": independent["checks_total"]})
    check("all_independent_checks_true", all(item["pass"] for item in independent["checks"]))
    check("numeric_tolerance", independent["max_numeric_delta"] <= independent["tolerance"] <= 2e-11, independent["max_numeric_delta"])
    selection = production["rich_dev_selection"]
    check("dev_no_go_status", production["status"] == "DEV_NO_GO_TEST_UNTOUCHED")
    check("test_not_authorized", selection["test_authorized"] is False and production["mechanism_increment_pass"] is False)
    check("no_test_or_secondary_metrics", production["primary_test"] is None and production["secondary"] is None)
    check("no_test_artifacts", not (artifact_root / "test_predictions.csv").exists() and not (artifact_root / "n_terminal_transport_predictions.csv").exists())
    for name in ("split_assignments.csv", "dev_predictions.csv"):
        path = artifact_root / name
        check("artifact_hash:" + name, path.is_file() and sha256(path) == production["artifact_files"][name]["sha256"])
    full = selection["models"]["full_mechanism"]["dev"]["rmse"]
    intrinsic = selection["models"]["intrinsic"]["dev"]["rmse"]
    local = selection["models"]["local_mfe"]["dev"]["rmse"]
    check("frozen_dev_comparison", full >= min(intrinsic, local), {"full_mechanism": full, "intrinsic": intrinsic, "local_mfe": local})
    repo = Path(__file__).resolve().parents[1]
    code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    report = {
        "schema": "a8-rk03-mage-synonymous-finalization-v1",
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "checks_passed": sum(item["pass"] for item in checks),
        "checks_total": len(checks),
        "checks": checks,
        "protocol_sha256": sha256(args.protocol),
        "production_sha256": sha256(args.production),
        "independent_sha256": sha256(args.independent),
        "production_script_sha256": sha256(args.production_script),
        "independent_script_sha256": sha256(args.independent_script),
        "code_commit": code_commit,
        "verified_result_recordable": True,
        "verified_scope": "frozen rich-medium positions-10-71 dev selection only; full mechanism did not beat intrinsic/local-MFE baselines",
        "test_result_available": False,
        "test_untouched": True,
        "sota_claim": False,
        "causal_claim": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "checks_passed", "checks_total", "code_commit")}, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
