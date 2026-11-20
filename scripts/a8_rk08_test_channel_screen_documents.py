#!/usr/bin/env python3
"""Mutation tests for the RK08 documentation verifier; real inputs stay read-only."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--artifacts", default="/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/channel_screen_documentation_tests_v1")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    verifier = root / "scripts/a8_rk08_verify_channel_screen_documents.py"
    doc_files = {
        "README": Path("README.md"),
        "root_tasks": Path("tasks.md"),
        "handover_tasks": Path("docs/handover/tasks.md"),
        "handoff": Path("docs/handover/HANDOFF_A8_RK_20261118.md"),
        "registry": Path("experiments/REGISTRY.md"),
    }

    def prepare(temp_root):
        for directory in ("configs", "audits", "paper"):
            (temp_root / directory).symlink_to(root / directory, target_is_directory=True)
        for relative in doc_files.values():
            destination = temp_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / relative, destination)

    def run(temp_root, report_path):
        process = subprocess.run([
            sys.executable, str(verifier), "--root", str(temp_root), "--output", str(report_path),
        ], text=True, capture_output=True)
        report = json.loads(report_path.read_text())
        return process.returncode, report

    cases = []

    def mutate_text(temp_root, doc_name, old, new, count=1):
        path = temp_root / doc_files[doc_name]
        text = path.read_text()
        assert old in text, (doc_name, old)
        path.write_text(text.replace(old, new, count))

    def execute_case(name, doc_name, old, new, expected_failure, count=1):
        with tempfile.TemporaryDirectory(prefix=f"rk08-doc-test-{name}-") as temporary:
            temp_root = Path(temporary)
            prepare(temp_root)
            mutate_text(temp_root, doc_name, old, new, count)
            report_path = artifacts / f"{name}.json"
            returncode, report = run(temp_root, report_path)
            failure_names = {failure["name"] for failure in report["failures"]}
            passed = returncode == 1 and not report["overall_pass"] and expected_failure in failure_names
            cases.append({
                "name": name,
                "pass": passed,
                "expected_failure": expected_failure,
                "observed_failures": sorted(failure_names),
                "report": str(report_path),
                "report_sha256": sha256(report_path),
            })

    with tempfile.TemporaryDirectory(prefix="rk08-doc-test-baseline-") as temporary:
        temp_root = Path(temporary)
        prepare(temp_root)
        baseline_path = artifacts / "baseline.json"
        baseline_code, baseline = run(temp_root, baseline_path)
        baseline_pass = baseline_code == 0 and baseline["overall_pass"] and baseline["check_counts"] == {"passed": 310, "total": 310}

    execute_case(
        "readme_gate_true", "README", "channel_screen_gate_pass=false", "channel_screen_gate_pass=true",
        "document:README:forbid:channel_screen_gate_pass=true",
    )
    execute_case(
        "handoff_full_proxy_delta", "handoff", "−0.025779039513507546", "0",
        "handoff:ood_value:ridge_all:spearman:point_delta",
    )
    execute_case(
        "registry_remove_science_row", "registry",
        next(line for line in (root / "experiments/REGISTRY.md").read_text().splitlines() if line.startswith("| CF-A8-RK08-CHANNEL-SCREEN |")) + "\n",
        "", "registry:CF-A8-RK08-CHANNEL-SCREEN:exactly_once",
    )
    selection_hash = "e5ce7720485e569febf4656ab9289d12393aac04dd1642ca017dd1f53a0b26a5"
    execute_case(
        "handoff_selection_hash", "handoff", selection_hash, "0" * 64,
        f"handoff:immutable_hash_recorded:{selection_hash}",
    )
    execute_case(
        "root_tasks_slide_id", "root_tasks", "`pZZ`", "`pZy`",
        "document:root_tasks:contains:pZZ",
    )
    execute_case(
        "registry_gate_status", "registry", "done_channel_screen_gate_false_rk_g1_false_generator_not_authorized", "done",
        "document:registry:negative_gate",
    )
    execute_case(
        "handover_tasks_ppt_count", "handover_tasks", "223/223", "22/22",
        "document:handover_tasks:contains:223/223", count=-1,
    )
    paper_line = next(line for line in (root / "experiments/REGISTRY.md").read_text().splitlines() if line.startswith("| CF-A8-RK18-WORKING-MANUSCRIPT-V31 |"))
    malformed_paper_line = paper_line.replace(" | done_v31_recorded_non_submittable |", " |")
    execute_case(
        "registry_column_count", "registry", paper_line, malformed_paper_line,
        "registry:CF-A8-RK18-WORKING-MANUSCRIPT-V31:eleven_columns",
    )

    failures = [case for case in cases if not case["pass"]]
    if not baseline_pass:
        failures.append({"name": "baseline", "pass": False})
    report = {
        "schema": "a8_rk08_channel_screen_documentation_mutation_tests_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_RK08_CHANNEL_SCREEN_DOCUMENTATION_MUTATIONS" if not failures else "FAIL_RK08_CHANNEL_SCREEN_DOCUMENTATION_MUTATIONS",
        "overall_pass": not failures,
        "check_counts": {"passed": (1 if baseline_pass else 0) + len(cases) - len([case for case in cases if not case["pass"]]), "total": 1 + len(cases)},
        "baseline": {"pass": baseline_pass, "report": str(baseline_path), "report_sha256": sha256(baseline_path)},
        "mutations": cases,
        "failures": failures,
        "real_documents_modified": False,
        "scientific_evidence_modified": False,
        "online_slides_modified": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "check_counts": report["check_counts"], "output": str(output)}, indent=2))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
