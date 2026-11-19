#!/usr/bin/env python3
"""Finalize the bounded Mordstein proxy diagnostic without upgrading its scientific scope."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--tests-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    protocol = json.loads(args.protocol.read_text())
    tests_text = args.tests_log.read_text()
    test_match = re.search(r"(\d+) passed", tests_text)
    tests_passed = int(test_match.group(1)) if test_match else 0
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    checks = {
        "production_pending_independent": production["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "independent_pass": independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] and not independent["failed_checks"],
        "independent_checks_total_18": independent["checks_total"] == 18,
        "production_hash_matches_independent": independent["production_sha256"] == sha256(args.production),
        "protocol_hash_matches_independent": independent["protocol_sha256"] == sha256(args.protocol) == production["protocol_sha256"],
        "six_contract_tests_passed": tests_passed == 6 and " failed" not in tests_text and "ERROR" not in tests_text,
        "code_commit_unchanged": production["code_commit"] == head,
        "tracked_tree_clean": not dirty,
        "metrics_csv_hash_current": sha256(Path(production["variant_metrics_csv"])) == production["variant_metrics_csv_sha256"],
        "scientific_library_not_forced_217": production["n_variants"] == 152 and all(not r["variant_id"].startswith("GFP_") for r in production["variant_metrics"]),
        "association_not_ood_or_sota": production["scientific_interpretation"]["association_only"] is True and production["scientific_interpretation"]["protein_ood_evaluation"] is False and production["scientific_interpretation"]["sota_claim"] is False,
        "generator_remains_unauthorized": production["scientific_interpretation"]["generator_training_authorized"] is False,
    }
    failed = [key for key, value in checks.items() if not value]
    payload = {
        "schema": "a8.rk02.mordstein_observed_end_proxy_diagnostics_finalization.v1",
        "status": "PASS" if not failed else "FAIL",
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed),
        "checks": checks,
        "failed_checks": failed,
        "protocol_id": protocol["protocol_id"],
        "production_sha256": sha256(args.production),
        "independent_sha256": sha256(args.independent),
        "tests_log_sha256": sha256(args.tests_log),
        "tests_passed": tests_passed,
        "code_commit": head,
        "next_gate": "Paper/PPT reporting after result review; fixed-protein observed-end association only; RK-G1 and generator authorization remain closed",
    }
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps({"status": payload["status"], "checks": f"{payload['checks_passed']}/{payload['checks_total']}", "failed": failed}))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
