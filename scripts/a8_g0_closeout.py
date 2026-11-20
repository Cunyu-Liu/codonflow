#!/usr/bin/env python3
"""Execute the frozen RK-G0 cost and gate protocol without importing baseline modules."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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


def pointer(document, expression: str):
    if expression == "":
        return document
    if not expression.startswith("/"):
        raise ValueError(f"Invalid JSON pointer: {expression}")
    value = document
    for raw in expression[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            value = value[int(token)]
        else:
            value = value[token]
    return value


def evaluate(spec: dict, document):
    if "pointer" in spec:
        return pointer(document, spec["pointer"])
    if "sum_pointers" in spec:
        return sum(pointer(document, item) for item in spec["sum_pointers"])
    if "constant" in spec:
        return spec["constant"]
    if "null_reason" in spec:
        return None
    raise ValueError(f"Unknown metric specification: {spec}")


def build_report(root: Path, protocol: dict, protocol_path: Path) -> dict:
    sources = {}
    checks = []
    for alias, entry in protocol["sources"].items():
        path = root / entry["path"]
        actual = sha256(path) if path.is_file() else None
        passed = actual == entry["sha256"]
        checks.append({"check_id": f"source_sha256:{alias}", "passed": passed,
                       "actual": actual, "expected": entry["sha256"]})
        if path.is_file():
            sources[alias] = json.loads(path.read_text())

    rows = []
    seen_ids = set()
    for contract in protocol["cost_rows"]:
        row_id = contract["row_id"]
        if row_id in seen_ids:
            raise ValueError(f"Duplicate row_id: {row_id}")
        seen_ids.add(row_id)
        alias = contract["source"]
        document = sources.get(alias) if alias else None
        if alias and document is None:
            status = "SOURCE_UNAVAILABLE"
            metrics = {name: None for name in contract["metrics"]}
        else:
            status = (contract["status_constant"] if alias is None
                      else pointer(document, contract["status_pointer"]))
            metrics = {name: evaluate(spec, document)
                       for name, spec in contract["metrics"].items()}
        expected_status = contract["accepted_status"] if alias else contract["status_constant"]
        checks.append({"check_id": f"row_status:{row_id}", "passed": status == expected_status,
                       "actual": status, "expected": expected_status})
        unavailable = {}
        for name, spec in contract["metrics"].items():
            value = metrics[name]
            if "null_reason" in spec:
                unavailable[name] = spec["null_reason"]
                checks.append({"check_id": f"explicit_null:{row_id}:{name}",
                               "passed": value is None and bool(spec["null_reason"]),
                               "actual": value, "expected": None})
            elif value is None:
                checks.append({"check_id": f"unexpected_null:{row_id}:{name}",
                               "passed": False, "actual": None, "expected": "non-null"})
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                valid = math.isfinite(value) and (value >= 0 or name == "legal_rate")
                checks.append({"check_id": f"finite_nonnegative:{row_id}:{name}",
                               "passed": valid, "actual": value,
                               "expected": "finite and nonnegative"})
        rows.append({
            "row_id": row_id,
            "method": contract["method"],
            "task": contract["task"],
            "scope": contract["scope"],
            "comparison_class": contract["comparison_class"],
            "source": alias,
            "status": status,
            "metrics": metrics,
            "unavailable_reasons": unavailable,
        })

    gate_results = []
    for contract in protocol["gate_checks"]:
        document = sources.get(contract["source"])
        actual = pointer(document, contract["pointer"]) if document is not None else None
        if contract["operator"] != "eq":
            raise ValueError(f"Unsupported operator: {contract['operator']}")
        passed = actual == contract["expected"]
        result = dict(contract)
        result.update({"actual": actual, "passed": passed})
        gate_results.append(result)
        checks.append({"check_id": f"gate:{contract['check_id']}", "passed": passed,
                       "actual": actual, "expected": contract["expected"]})

    measured_wall = sum(row["metrics"].get("wall_clock_s") is not None for row in rows)
    g0_checks = [item["passed"] for item in gate_results if item["category"] == "G0"]
    boundary_checks = [item["passed"] for item in gate_results if item["category"] == "BOUNDARY"]
    technical_pass = all(item["passed"] for item in checks)
    g0_pass = bool(g0_checks) and all(g0_checks) and all(
        item["passed"] for item in checks if not item["check_id"].startswith("gate:"))
    report = {
        "schema_version": "a8-g0-closeout-production-v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_path": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "production_script_sha256": sha256(Path(__file__).resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "code_commit_at_execution": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "cost_policy": protocol["cost_policy"],
        "cost_matrix": rows,
        "summary": {
            "row_count": len(rows),
            "source_count": len(protocol["sources"]),
            "measured_wall_clock_scopes": measured_wall,
            "explicit_null_wall_clock_scopes": len(rows) - measured_wall,
            "comparison_classes": {
                name: sum(row["comparison_class"] == name for row in rows)
                for name in sorted({row["comparison_class"] for row in rows})
            },
            "global_wall_clock_sum": None,
            "global_wall_clock_sum_exclusion": "Mixed and overlapping scopes must not be summed or ranked.",
        },
        "gate_results": gate_results,
        "g0_status": protocol["g0_pass_status"] if g0_pass else "FAIL",
        "rk03_remaining_status": (protocol["rk03_remaining_status"]
                                  if all(g0_checks) else "NOT_CLOSED"),
        "technical_check_count": len(checks),
        "technical_passed_checks": sum(item["passed"] for item in checks),
        "technical_checks": checks,
        "boundary_checks_pass": all(boundary_checks),
        "overall_pass": technical_pass and g0_pass and all(boundary_checks),
        "boundaries": protocol["boundaries"],
        "scientific_conclusion": (
            "RK-G0 bounded data/baseline/evaluator readiness is supported. "
            "This is not complete SOTA, a time-matched win, full external dense coverage, "
            "RK-G1 passage, generator authorization, functional untouched evaluation, or wet-lab validation."
        ),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    protocol_path = args.protocol if args.protocol.is_absolute() else root / args.protocol
    output = args.output if args.output.is_absolute() else root / args.output
    protocol = json.loads(protocol_path.read_text())
    report = build_report(root, protocol, protocol_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output), "overall_pass": report["overall_pass"],
                      "g0_status": report["g0_status"], "rows": report["summary"]["row_count"],
                      "checks": f"{report['technical_passed_checks']}/{report['technical_check_count']}",
                      "sha256": sha256(output)}, indent=2))
    return 0 if report["overall_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
