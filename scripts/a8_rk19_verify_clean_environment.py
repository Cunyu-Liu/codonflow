#!/usr/bin/env python3
"""Verify a fresh-conda-environment CPU test-suite reproduction for RK19."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import site
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ["env-prefix", "create-log", "explicit-spec", "junit", "console", "pip-check-log",
                 "existing-env-report", "science-gate", "output"]:
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    env_prefix = Path(args.env_prefix).resolve()
    create_log = Path(args.create_log)
    explicit_spec = Path(args.explicit_spec)
    junit = Path(args.junit)
    console = Path(args.console)
    pip_check_log = Path(args.pip_check_log)
    existing_env_report = Path(args.existing_env_report)
    science_gate = Path(args.science_gate)
    root = Path(__file__).resolve().parents[1]
    suite = ET.parse(junit).getroot().find("testsuite")
    assert suite is not None
    cases = suite.findall("testcase")
    skipped = [case for case in cases if case.find("skipped") is not None]
    failed = [case for case in cases if case.find("failure") is not None or case.find("error") is not None]
    console_text = console.read_text(encoding="utf-8")
    spec_text = explicit_spec.read_text(encoding="utf-8")
    create_text = create_log.read_text(encoding="utf-8")
    pip_text = pip_check_log.read_text(encoding="utf-8")
    existing = json.loads(existing_env_report.read_text(encoding="utf-8"))
    gate = json.loads(science_gate.read_text(encoding="utf-8"))
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("isolated_executable", Path(sys.executable).resolve().is_relative_to(env_prefix), sys.executable)
    check("isolated_prefix", Path(sys.prefix).resolve() == env_prefix, sys.prefix)
    check("no_external_pythonpath", not os.environ.get("PYTHONPATH"), os.environ.get("PYTHONPATH"))
    check("site_packages_under_prefix", all(Path(p).resolve().is_relative_to(env_prefix) for p in site.getsitepackages()), site.getsitepackages())
    check("conda_transaction_completed", "Executing transaction" in create_text and "done" in create_text)
    spec_lines = [line for line in spec_text.splitlines() if line and not line.startswith("#")]
    check("explicit_spec_present", "@EXPLICIT" in spec_text and len(spec_lines) > 20, len(spec_lines))
    check("official_package_urls", spec_lines and all(line.startswith("https://conda.anaconda.org/") or line.startswith("https://repo.anaconda.com/") for line in spec_lines if not line.startswith("@")))
    check("no_aliyun_package_urls", "mirrors.aliyun.com" not in spec_text)
    check("pip_check", "No broken requirements found." in pip_text)
    imports = {}
    for module in ["torch", "numpy", "scipy", "pandas", "sklearn", "RNA", "pymoo", "rapidfuzz", "pytest"]:
        try:
            imports[module] = bool(importlib.import_module(module))
        except Exception as exc:
            imports[module] = f"{type(exc).__name__}: {exc}"
        check("import_" + module, imports[module] is True, imports[module])
    check("junit_testcases", len(cases) == 331, len(cases))
    check("junit_no_failures", not failed and int(suite.get("failures", -1)) == 0 and int(suite.get("errors", -1)) == 0)
    check("one_explicit_skip", len(skipped) == 1 and skipped[0].get("name") == "test_queue_lifecycle_in_isolated_tmux")
    check("console_result", "collected 331 items" in console_text and "330 passed, 1 skipped" in console_text)
    check("existing_env_regression_bound", existing.get("overall_pass") is True and existing.get("tests", {}).get("passed") == 330)
    check("science_gates_unchanged", all(gate["gates"][key] is False for key in
          ["velocity_mechanism_pass", "rk_g1_pass", "functional_untouched_evaluated",
           "generator_training_authorized", "external_sota_claim_authorized"]))
    versions = {name: importlib.metadata.version(name) for name in
                ["torch", "numpy", "scipy", "pandas", "scikit-learn", "pymoo", "rapidfuzz", "pytest"]}
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk19-clean-cpu-suite-v1",
        "status": "PASS_CLEAN_CPU_SUITE" if passed == len(checks) else "FAIL_CLEAN_CPU_SUITE",
        "overall_pass": passed == len(checks),
        "check_count": len(checks),
        "passed_count": passed,
        "environment_prefix": str(env_prefix),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "external_pythonpath": False,
        "package_versions": versions,
        "tests": {"collected": len(cases), "passed": len(cases) - len(skipped) - len(failed),
                  "skipped": len(skipped), "failed": len(failed), "errors": 0},
        "junit_metadata_observation": {"tests_attribute": int(suite.get("tests", -1)),
                                       "testcase_elements": len(cases)},
        "input_sha256": {
            "create_log": sha256(create_log), "explicit_spec": sha256(explicit_spec),
            "junit": sha256(junit), "console": sha256(console), "pip_check_log": sha256(pip_check_log),
            "existing_env_report": sha256(existing_env_report), "science_gate": sha256(science_gate),
            "environment_yml": sha256(root / "environment.yml"), "pyproject_toml": sha256(root / "pyproject.toml"),
        },
        "clean_cpu_test_suite_reproduction": passed == len(checks),
        "full_experimental_clean_reproduction": False,
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
