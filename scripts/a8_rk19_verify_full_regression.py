#!/usr/bin/env python3
"""Independently verify the RK19 full CPU regression and dependency repair."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import xml.etree.ElementTree as ET
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ["junit", "console", "initial-log", "pip-check-log", "science-gate", "output"]:
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    junit = Path(args.junit)
    console = Path(args.console)
    initial_log = Path(args.initial_log)
    pip_check_log = Path(args.pip_check_log)
    science_gate = Path(args.science_gate)
    root = Path(__file__).resolve().parents[1]
    suite = ET.parse(junit).getroot().find("testsuite")
    assert suite is not None, "missing testsuite in JUnit XML"
    cases = suite.findall("testcase")
    skipped_cases = [case for case in cases if case.find("skipped") is not None]
    failed_cases = [case for case in cases if case.find("failure") is not None or case.find("error") is not None]
    console_text = console.read_text(encoding="utf-8")
    initial_text = initial_log.read_text(encoding="utf-8")
    pip_text = pip_check_log.read_text(encoding="utf-8")
    gate = json.loads(science_gate.read_text(encoding="utf-8"))
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("junit_counts", len(cases) == 331,
          {"suite_tests_attribute": suite.get("tests"), "testcase_elements": len(cases),
           "attribute_minus_elements": int(suite.get("tests", -1)) - len(cases)})
    check("junit_no_failures", int(suite.get("failures", -1)) == 0 and int(suite.get("errors", -1)) == 0 and not failed_cases)
    check("junit_one_skip", int(suite.get("skipped", -1)) == 1 and len(skipped_cases) == 1)
    if skipped_cases:
        skip = skipped_cases[0]
        check("expected_integration_skip", skip.get("name") == "test_queue_lifecycle_in_isolated_tmux",
              {"classname": skip.get("classname"), "name": skip.get("name"),
               "reason": skip.find("skipped").get("message")})
    else:
        check("expected_integration_skip", False)
    check("console_counts", "330 passed, 1 skipped" in console_text)
    check("collection_repaired", "collected 331 items" in console_text and "errors during collection" not in console_text)
    check("integration_marker_registered", "PytestUnknownMarkWarning" not in console_text)
    check("initial_failure_preserved", "4 errors during collection" in initial_text and "No module named 'pandas'" in initial_text and "No module named 'sklearn'" in initial_text)
    check("pip_check", "No broken requirements found." in pip_text)
    versions = {name: importlib.metadata.version(name) for name in
                ["numpy", "scipy", "pandas", "scikit-learn", "joblib", "threadpoolctl", "pytest"]}
    check("pandas_version", versions["pandas"] == "2.2.2", versions["pandas"])
    check("sklearn_version", versions["scikit-learn"] == "1.7.2", versions["scikit-learn"])
    environment_text = (root / "environment.yml").read_text(encoding="utf-8")
    pyproject_text = (root / "pyproject.toml").read_text(encoding="utf-8")
    check("conda_dependencies_declared", "pandas=2.2.2" in environment_text and "scikit-learn=1.7.2" in environment_text)
    check("test_extra_declared", 'dev = ["pytest", "pandas>=2.2", "scikit-learn>=1.7"]' in pyproject_text)
    check("analysis_extra_declared", 'analysis = ["pandas>=2.2", "scikit-learn>=1.7"]' in pyproject_text)
    check("science_gates_unchanged", all(gate["gates"][key] is False for key in
          ["velocity_mechanism_pass", "rk_g1_pass", "functional_untouched_evaluated",
           "generator_training_authorized", "external_sota_claim_authorized"]))

    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk19-full-cpu-regression-v1",
        "status": "PASS_FULL_CPU_SUITE_EXISTING_ENV" if passed == len(checks) else "FAIL_FULL_CPU_SUITE_EXISTING_ENV",
        "overall_pass": passed == len(checks),
        "check_count": len(checks),
        "passed_count": passed,
        "environment": "codonflow",
        "python": platform.python_version(),
        "device_contract": "CUDA_VISIBLE_DEVICES empty; CPU test run",
        "tests": {"collected": len(cases), "passed": len(cases) - len(skipped_cases) - len(failed_cases), "skipped": len(skipped_cases), "failed": len(failed_cases), "errors": 0},
        "junit_metadata_observation": {
            "tests_attribute": int(suite.get("tests", -1)),
            "testcase_elements": len(cases),
            "attribute_minus_elements": int(suite.get("tests", -1)) - len(cases),
            "acceptance_basis": "console summary plus independently enumerated testcase elements",
        },
        "package_versions": versions,
        "input_sha256": {
            "junit": sha256(junit), "console": sha256(console), "initial_log": sha256(initial_log),
            "pip_check_log": sha256(pip_check_log), "science_gate": sha256(science_gate),
            "environment_yml": sha256(root / "environment.yml"), "pyproject_toml": sha256(root / "pyproject.toml"),
        },
        "full_cpu_suite_pass": passed == len(checks),
        "clean_environment_reproduction": False,
        "gpu_integration_executed": False,
        "rk_g1_pass": False,
        "generator_training_authorized": False,
        "functional_untouched_evaluated": False,
        "checks": checks,
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "tests": report["tests"]}, indent=2))
    if passed != len(checks):
        for item in checks:
            if not item["pass"]:
                print("FAIL", item)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
