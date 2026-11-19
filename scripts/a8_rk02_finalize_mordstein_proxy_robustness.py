#!/usr/bin/env python3
"""Finalize post-hoc robustness without changing the primary gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--tests-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    primary_finalization = json.loads((args.repo / protocol["primary_finalization"]).read_text())
    tests_text = args.tests_log.read_text()
    match = re.search(r"(\d+) passed", tests_text)
    tests = int(match.group(1)) if match else 0
    head = subprocess.check_output(["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(args.repo), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    checks = {
        "production_pending": production["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "independent_8_of_8_pass": independent["status"] == "PASS" and independent["checks_total"] == independent["checks_passed"] == 8 and not independent["failed_checks"],
        "production_and_protocol_hashes": independent["production_sha256"] == sha256(args.production) and independent["protocol_sha256"] == sha256(args.protocol) == production["protocol_sha256"],
        "primary_finalization_unchanged": primary_finalization["status"] == "PASS" and production["primary_finalization_sha256"] == sha256(args.repo / protocol["primary_finalization"]),
        "three_contract_tests": tests == 3 and " failed" not in tests_text and "ERROR" not in tests_text,
        "code_commit_and_tracked_tree": production["code_commit"] == head and not dirty,
        "posthoc_not_new_primary_gate": production["analysis_status"] == "POST_HOC_EXPLORATORY_NOT_PRIMARY_NOT_A_NEW_GATE" and protocol["boundaries"]["changes_primary_analysis"] is False,
        "no_causal_ood_generator_or_sota_upgrade": production["boundaries"]["causal_inference"] is False and production["boundaries"]["protein_ood_evaluation"] is False and production["boundaries"]["generator_training_authorized"] is False and production["boundaries"]["sota_claim"] is False,
    }
    failed = [key for key, passed in checks.items() if not passed]
    payload = {
        "schema": "a8.rk02.mordstein_proxy_robustness_finalization.v1",
        "status": "PASS" if not failed else "FAIL",
        "checks_total": len(checks), "checks_passed": len(checks) - len(failed), "checks": checks, "failed_checks": failed,
        "production_sha256": sha256(args.production), "independent_sha256": sha256(args.independent),
        "tests_log_sha256": sha256(args.tests_log), "tests_passed": tests, "code_commit": head,
        "next_gate": "Report as post-hoc robustness alongside the finalized fixed-GFP observed-end association; no causal/OOD/generator upgrade",
    }
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps({"status": payload["status"], "checks": f"{payload['checks_passed']}/{payload['checks_total']}", "failed": failed}))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
