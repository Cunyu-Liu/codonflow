#!/usr/bin/env python3
"""Independently verify the concurrent RK33 documentation closeout without adding duplicate records."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path("/home/codonflow-a8-rk")
AUDIT = Path("audits/20261121/RK33")
BUNDLE = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk33/rk33_ppt_v1_bundle.tar.gz")


def run(*args: str) -> bytes:
    return subprocess.check_output(args, cwd=ROOT)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, details: object = None) -> None:
        checks.append({"name": name, "pass": bool(ok), "details": details})

    head = run("git", "rev-parse", "HEAD").decode().strip()
    origin = run("git", "rev-parse", "origin/a8-rk").decode().strip()
    remote = run("git", "ls-remote", "origin", "refs/heads/a8-rk").decode().split()[0]
    check("origin_and_actual_remote_match", origin == remote, {"origin": origin, "remote": remote})
    ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", "5beff8ad66fc71ea28101fe39538d8e260071104", "HEAD"], cwd=ROOT).returncode
    check("concurrent_closeout_is_in_history", ancestry == 0, {"returncode": ancestry})

    registry = run("git", "show", "HEAD:experiments/REGISTRY.md").decode()
    tasks = run("git", "show", "HEAD:docs/handover/tasks.md").decode()
    check("one_rk33_registry_row", registry.count("| RK33 |") == 1, registry.count("| RK33 |"))
    check("one_concurrent_rk33_tasks_section", tasks.count("## 2026-11-22：RK33 local observed-R1") == 1, tasks.count("## 2026-11-22：RK33 local observed-R1"))
    check("no_duplicate_parallel_rk33_tasks_section", "## 2026-11-21：RK33 observed-R1" not in tasks)
    handoff = run("git", "show", "HEAD:docs/handover/HANDOFF_A8_RK33_20261122.md").decode()
    check("concurrent_handoff_present", "RK34" in handoff and "non-submittable working draft" in handoff and "RK-G1=false" in handoff, {"characters": len(handoff)})
    check("parallel_detailed_handoff_retained", bool(run("git", "show", "HEAD:docs/handover/HANDOFF_A8_RK33_20261121.md")))

    expected_hashes = {
        AUDIT / "rk33_local_coverage_result_v1.json": "d341694fb336ba579bbb990d80d7b17eafff104250052cea8577e4b927c08b64",
        AUDIT / "rk33_local_coverage_independent_v1.json": "3b53c5118bc93a71a5eaadaaaf22e48f13bc0b2d580b017308348a0ff171fa8d",
        AUDIT / "rk33_clean_reproduction_v1.json": "7808acc84567fe972be0ddb870c23bd8714da2bc1e0dbdb1421ff08a5171e455",
        AUDIT / "rk33_closeout_verification_v2.json": "ae09d302c8dd331aa59239c6e90180289e3c7ab34a030d3510e26b6af55c334b",
        Path("paper/CodonFlow_preprint_A8.md"): "1e2701a379dc362e2d1a75949ac7d20fca039ca4703e6a6f73665a09b1b0e65d",
    }
    for relative, expected in expected_hashes.items():
        actual = sha(ROOT / relative)
        check(f"sha_{relative.name}", actual == expected, actual)

    science = json.loads((ROOT / AUDIT / "rk33_local_coverage_result_v1.json").read_text())
    independent = json.loads((ROOT / AUDIT / "rk33_local_coverage_independent_v1.json").read_text())
    reproduction = json.loads((ROOT / AUDIT / "rk33_clean_reproduction_v1.json").read_text())
    closeout = json.loads((ROOT / AUDIT / "rk33_closeout_verification_v2.json").read_text())
    check("science_status_retained", science.get("status") in {"PASS", "SUCCESS", "COMPLETED"} or science.get("conclusion") is not None, {"status": science.get("status"), "conclusion": science.get("conclusion")})
    check("independent_76_of_76", independent.get("status") == "PASS" and independent.get("checks_passed") == 76 and independent.get("checks_total") == 76, {"status": independent.get("status"), "checks": f'{independent.get("checks_passed")}/{independent.get("checks_total")}'})
    check("clean_reproduction_90_of_90", reproduction.get("status") == "PASS" and reproduction.get("checks_passed") == 90 and reproduction.get("checks_total") == 90, {"status": reproduction.get("status"), "checks": f'{reproduction.get("checks_passed")}/{reproduction.get("checks_total")}'})
    check("science_closeout_22_of_22", closeout.get("status") == "PASS" and closeout.get("checks_passed") == 22 and closeout.get("checks_total") == 22, {"status": closeout.get("status"), "checks": f'{closeout.get("checks_passed")}/{closeout.get("checks_total")}'})
    tests = (ROOT / AUDIT / "rk33_project_tests_v1.log").read_text()
    check("full_project_tests_recorded", "429 passed" in tests and "1 skipped" in tests)

    ppt = json.loads((ROOT / AUDIT / "ppt_v1/rk33_ppt_closeout_remote_v2.json").read_text())
    check("ppt_21_of_21_and_155_slides", ppt.get("status") == "PASS" and ppt.get("checks_passed") == 21 and ppt.get("checks_total") == 21 and ppt.get("final_slide_count") == 155 and ppt.get("final_revision_id") == 122, {"slides": ppt.get("final_slide_count"), "revision": ppt.get("final_revision_id")})
    ppt_files = run("git", "ls-tree", "-r", "--name-only", "HEAD", str(AUDIT / "ppt_v1")).decode().splitlines()
    check("no_appledouble_in_tracked_ppt_evidence", not any(Path(p).name.startswith("._") for p in ppt_files), {"tracked_files": len(ppt_files)})
    bundle_sha = sha(BUNDLE)
    check("ppt_bundle_sha", bundle_sha == "804df9aac43aa55c93eaa78e4992fe75c056592244b1385eebad9c67b7e90a32", {"sha256": bundle_sha, "bytes": BUNDLE.stat().st_size})

    for name, relative in [
        ("production", "local_coverage_v1/model_results_v1"),
        ("independent", "local_coverage_v1/independent_v1"),
        ("clean", "local_coverage_v1/clean_reproduction_20e1ac38"),
        ("ppt", "ppt_v1"),
    ]:
        path = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk33") / relative
        files = [p for p in path.rglob("*") if p.is_file()]
        check(f"teams_{name}_artifacts_present", path.is_dir() and len(files) > 0, {"files": len(files), "bytes": sum(p.stat().st_size for p in files)})

    previous = json.loads((ROOT / AUDIT / "rk33_registration_verification_v1.json").read_text())
    check("superseded_registration_failure_retained", previous.get("status") == "FAIL" and previous.get("checks_passed") == 24 and previous.get("checks_total") == 25, {"status": previous.get("status"), "failed": [c["name"] for c in previous["checks"] if not c["pass"]]})
    check("no_unstaged_tracked_edits", not run("git", "diff", "--name-only").strip())

    report = {
        "schema": "a8-rk33-final-registration-verification-v2",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "head": head,
        "origin_a8_rk": origin,
        "actual_remote_a8_rk": remote,
        "concurrent_closeout_commit": "5beff8ad66fc71ea28101fe39538d8e260071104",
        "concurrent_archive_commit": "8203c0bbda4fa008841d11030af525bb545eb83e",
        "checks_passed": sum(bool(c["pass"]) for c in checks),
        "checks_total": len(checks),
        "checks": checks,
        "notes": [
            "The concurrent 20261122 handoff/tasks/registry closeout was audited and retained; no duplicate RK33 tasks section or PPT pages were added.",
            "The earlier parallel registration verifier v1 remains as a FAIL record for its three handoff trailing-whitespace errors; this v2 independently checks the final concurrent state.",
            "Historical dirty/untracked files were archived by the separate concurrent commit 8203c0bb; this verifier does not reverse or rewrite that history.",
            "External SOTA, unified time-matched, full seven-method dense trajectories, functional/protein OOD, prospective DBTL and RK-G1 remain open.",
        ],
    }
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        print(json.dumps([c for c in checks if not c["pass"]], ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
