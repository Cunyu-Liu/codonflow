#!/usr/bin/env python3
"""Audit RK34 manuscript insertion against source JSON and workflow gates."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    base = args.base
    original_path = base / "CodonFlow_preprint_A8.pre_rk34.md"
    updated_path = base / "CodonFlow_preprint_A8.md"
    section_path = base / "academic_workflow/paper-write-en/.workflow/paper_final.md"
    integration = json.loads((base / "rk34_manuscript_integration_v1.json").read_text())
    workflow = json.loads((base / "rk34_academic_workflow_status_v1.json").read_text())
    closeout = json.loads((base / "rk34_closeout_v2.json").read_text())
    expected = base / "rk34_manuscript_expected.tmp.md"
    subprocess.run([sys.executable, str(base / "build_rk34_manuscript_section.py"), "--base", str(base), "--output", str(expected), "--metadata", str(base / "rk34_manuscript_expected.tmp.json")], check=True, stdout=subprocess.DEVNULL)
    original, updated, section = original_path.read_text(), updated_path.read_text(), section_path.read_text()
    checks = []
    def check(name, ok, details):
        checks.append({"name": name, "pass": bool(ok), "details": details})
    check("source_generated_section_exact", section == expected.read_text(), {"expected_sha256": sha(expected), "observed_sha256": sha(section_path)})
    check("integration_pass", integration["status"] == "PASS" and integration["non_insertion_content_preserved_exactly"], integration)
    check("workflow_deliver_pass", workflow["status"] == "PASS" and workflow["stage"] == "deliver", workflow)
    check("closeout_pass", closeout["status"] == "PASS", closeout["status"])
    check("updated_hash", sha(updated_path) == integration["updated_sha256"], sha(updated_path))
    check("original_hash", sha(original_path) == integration["original_sha256"], sha(original_path))
    check("section_hash", sha(section_path) == integration["section_sha256"], sha(section_path))
    inserted = section.strip() + "\n\n"
    check("insertion_only_recovery", updated.count(inserted) == 1 and updated.replace(inserted, "", 1) == original, updated.count(inserted))
    check("section_before_discussion", updated.count("### 6.45 ") == 1 and updated.index("### 6.45 ") < updated.index("## 7. Discussion"), updated.count("### 6.45 "))
    check("table_23_rows", sum(line.startswith(("| exact−simple |", "| upstream |", "| start |")) for line in section.splitlines()) == 20, "20 confirmatory endpoint rows")
    check("table_24_rows", sum(line.startswith(("| Intercept |", "| Ridge |", "| HistGB |")) for line in section.splitlines()) == 19, "19 absolute-performance rows")
    required = ["12/20 positive endpoints overall", "exact local context passed 4/4", "none of the four separability families passed", "upstream-given-start passed 3/4", "start-given-upstream 2/4", "start-without-upstream 1/4", "upstream-without-start 2/4", "155/155 checks", "4533dd1794fa1dc6fd7519b3b3131463b1ae826e", "455 passed, one skipped, and five passing subtests", "700 new + 200 reused = 900 evaluated fits", "Functional untouched data were not read", "expensive generator training was not authorized", "retrospective, fixed-Kudla", "not a biological perturbation", "RK-G1"]
    for text in required:
        check("required_" + text[:40], text in section, text)
    report = {"schema": "a8-rk34-manuscript-audit-v1", "status": "PASS" if all(row["pass"] for row in checks) else "FAIL", "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks), "failed_checks": [row["name"] for row in checks if not row["pass"]], "manuscript_sha256": sha(updated_path), "section_sha256": sha(section_path), "original_sha256": sha(original_path), "manuscript_status": "non_submittable_working_draft"}
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f'{report["checks_passed"]}/{report["checks_total"]}', "failed": report["failed_checks"], "manuscript_sha256": report["manuscript_sha256"]}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
