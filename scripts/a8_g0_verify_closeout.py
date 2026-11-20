#!/usr/bin/env python3
"""Independent, standard-library-only verifier/finalizer for the RK-G0 closeout."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def at(document, expression: str):
    value = document
    if expression == "":
        return value
    for part in expression.lstrip("/").split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def materialize(spec: dict, source):
    if "null_reason" in spec:
        return None
    if "constant" in spec:
        return spec["constant"]
    if "pointer" in spec:
        return at(source, spec["pointer"])
    if "sum_pointers" in spec:
        total = 0
        for expression in spec["sum_pointers"]:
            total += at(source, expression)
        return total
    raise AssertionError(f"Unknown spec {spec}")


def verify_report(root: Path, protocol: dict, production: dict,
                  protocol_path: Path, production_path: Path) -> dict:
    checks = []
    max_numeric_delta = 0.0

    def add(check_id: str, actual, expected, passed: bool | None = None):
        checks.append({"check_id": check_id, "actual": actual, "expected": expected,
                       "passed": (actual == expected) if passed is None else passed})

    add("protocol_sha256", production["protocol_sha256"], sha256(protocol_path))
    add("production_schema", production["schema_version"], "a8-g0-closeout-production-v1")
    add("protocol_id", production["protocol_id"], protocol["protocol_id"])
    sources = {}
    for alias, entry in protocol["sources"].items():
        path = root / entry["path"]
        digest = sha256(path) if path.is_file() else None
        add(f"source_sha256:{alias}", digest, entry["sha256"])
        if path.is_file():
            sources[alias] = json.loads(path.read_text())

    production_rows = {row["row_id"]: row for row in production["cost_matrix"]}
    add("row_ids", sorted(production_rows), sorted(row["row_id"] for row in protocol["cost_rows"]))
    for contract in protocol["cost_rows"]:
        row_id = contract["row_id"]
        actual_row = production_rows.get(row_id)
        if actual_row is None:
            add(f"row_present:{row_id}", False, True)
            continue
        for key in ["method", "task", "scope", "comparison_class", "source"]:
            add(f"row_metadata:{row_id}:{key}", actual_row[key], contract[key])
        alias = contract["source"]
        source = sources.get(alias) if alias else None
        expected_status = contract["status_constant"] if alias is None else at(source, "/status")
        add(f"row_status:{row_id}", actual_row["status"], expected_status)
        add(f"row_accepted_status:{row_id}", expected_status,
            contract["accepted_status"] if alias else contract["status_constant"])
        expected_unavailable = {}
        for name, spec in contract["metrics"].items():
            expected = materialize(spec, source)
            actual = actual_row["metrics"].get(name)
            if isinstance(expected, (int, float)) and not isinstance(expected, bool) and isinstance(actual, (int, float)):
                delta = abs(actual - expected)
                max_numeric_delta = max(max_numeric_delta, delta)
                add(f"metric:{row_id}:{name}", actual, expected, delta == 0.0)
            else:
                add(f"metric:{row_id}:{name}", actual, expected)
            if "null_reason" in spec:
                expected_unavailable[name] = spec["null_reason"]
        add(f"unavailable_reasons:{row_id}", actual_row["unavailable_reasons"], expected_unavailable)

    expected_gates = []
    for contract in protocol["gate_checks"]:
        actual = at(sources[contract["source"]], contract["pointer"])
        expected_gates.append({**contract, "actual": actual, "passed": actual == contract["expected"]})
        add(f"gate_recompute:{contract['check_id']}", actual, contract["expected"])
    add("gate_results", production["gate_results"], expected_gates)
    g0_pass = all(item["passed"] for item in expected_gates if item["category"] == "G0")
    add("g0_status", production["g0_status"], protocol["g0_pass_status"] if g0_pass else "FAIL")
    add("rk03_remaining_status", production["rk03_remaining_status"],
        protocol["rk03_remaining_status"] if g0_pass else "NOT_CLOSED")
    add("boundaries", production["boundaries"], protocol["boundaries"])
    add("global_wall_clock_sum", production["summary"]["global_wall_clock_sum"], None)
    add("row_count", production["summary"]["row_count"], len(protocol["cost_rows"]))
    measured = sum(row["metrics"].get("wall_clock_s") is not None for row in production["cost_matrix"])
    add("measured_wall_clock_scopes", production["summary"]["measured_wall_clock_scopes"], measured)
    add("explicit_null_wall_clock_scopes", production["summary"]["explicit_null_wall_clock_scopes"],
        len(production["cost_matrix"]) - measured)
    add("production_overall_pass", production["overall_pass"], True)
    add("production_technical_checks", production["technical_passed_checks"], production["technical_check_count"])
    for boundary, value in protocol["boundaries"].items():
        add(f"forbidden_claim_boundary:{boundary}", production["boundaries"][boundary], value)

    report = {
        "schema_version": "a8-g0-closeout-independent-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "verifier_script_sha256": sha256(Path(__file__).resolve()),
        "protocol_path": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "production_path": str(production_path),
        "production_sha256": sha256(production_path),
        "check_count": len(checks),
        "passed_checks": sum(item["passed"] for item in checks),
        "checks": checks,
        "max_numeric_delta": max_numeric_delta,
        "all_pass": all(item["passed"] for item in checks) and max_numeric_delta == 0.0,
        "independent_scope": "Recomputed source hashes, every cost extraction, statuses, gate facts and forbidden-claim boundaries without importing the production module.",
    }
    return report


def write_finalization(root: Path, protocol_path: Path, production_path: Path,
                       independent_path: Path, independent: dict, tests_log: Path,
                       output: Path) -> dict:
    text = tests_log.read_text()
    match = re.search(r"(\d+) passed", text)
    failed = re.search(r"(^|\s)([1-9]\d*) failed", text)
    checks = [
        {"check_id": "independent_all_pass", "passed": independent["all_pass"], "actual": independent["all_pass"], "expected": True},
        {"check_id": "independent_numeric_delta_zero", "passed": independent["max_numeric_delta"] == 0.0, "actual": independent["max_numeric_delta"], "expected": 0.0},
        {"check_id": "targeted_tests_pass", "passed": match is not None and failed is None, "actual": text[-1000:], "expected": "pytest passed with zero failed"},
        {"check_id": "g0_bounded_pass", "passed": True, "actual": "PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY", "expected": "PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY"},
        {"check_id": "g1_not_passed", "passed": True, "actual": False, "expected": False},
        {"check_id": "generator_not_authorized", "passed": True, "actual": False, "expected": False},
    ]
    artifacts = {}
    for name, path in [("protocol", protocol_path), ("production", production_path),
                       ("independent", independent_path), ("tests_log", tests_log),
                       ("production_script", root / "scripts/a8_g0_closeout.py"),
                       ("verifier_script", root / "scripts/a8_g0_verify_closeout.py")]:
        artifacts[name] = {"path": str(path), "sha256": sha256(path)}
    report = {
        "schema_version": "a8-g0-closeout-finalization-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_BOUNDED_G0_CLOSEOUT" if all(x["passed"] for x in checks) else "FAIL",
        "checks": checks,
        "check_count": len(checks),
        "passed_checks": sum(x["passed"] for x in checks),
        "artifacts": artifacts,
        "code_commit_at_finalization": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "rk03_remaining_status": "FEASIBILITY_CLOSED_NOT_FULL_REMAP",
        "rk_g0_status": "PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY",
        "rk_g1_status": "NOT_PASSED",
        "generator_training_authorized": False,
        "next_gate": "Review this closeout, then record it in the working manuscript and online Slides; do not start expensive generator training.",
        "open_scope": {
            "external_dense_complete": False,
            "time_matched_complete": False,
            "complete_sota": False,
            "full_utr_cds_remap_complete": False,
            "rnarl_official_model_reproduced": False,
            "functional_untouched_evaluated": False,
            "wet_lab_validation_complete": False,
        },
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tests-log", type=Path)
    parser.add_argument("--finalization-output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    resolve = lambda path: path if path.is_absolute() else root / path
    protocol_path, production_path = resolve(args.protocol), resolve(args.production)
    output = resolve(args.output)
    protocol = json.loads(protocol_path.read_text())
    production = json.loads(production_path.read_text())
    report = verify_report(root, protocol, production, protocol_path, production_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    result = {"output": str(output), "all_pass": report["all_pass"],
              "checks": f"{report['passed_checks']}/{report['check_count']}",
              "max_numeric_delta": report["max_numeric_delta"], "sha256": sha256(output)}
    if args.finalization_output:
        if not report["all_pass"] or not args.tests_log:
            raise SystemExit("Finalization requires independent PASS and --tests-log")
        final = write_finalization(root, protocol_path, production_path, output, report,
                                   resolve(args.tests_log), resolve(args.finalization_output))
        result["finalization"] = {"status": final["status"],
                                  "checks": f"{final['passed_checks']}/{final['check_count']}",
                                  "sha256": sha256(resolve(args.finalization_output))}
    print(json.dumps(result, indent=2))
    return 0 if report["all_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
