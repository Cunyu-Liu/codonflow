#!/usr/bin/env python3
"""Prepare and verify the RK33 registry/tasks/handoff commit without mixing prior worktree edits."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path("/home/codonflow-a8-rk")
EXPECTED_HEAD = "a028d1986e05e7ece66fce6bc5d3a3dd06d1567f"
EXPECTED_TASKS_DIFF_SHA = "62aad6674b5a41af4ac1d9aa0f7ee8ed61e77684addb232cd4d63fd3c06a304c"
REGISTRY = Path("experiments/REGISTRY.md")
TASKS = Path("docs/handover/tasks.md")
HANDOFF = Path("docs/handover/HANDOFF_A8_RK33_20261121.md")
AUDIT = Path("audits/20261121/RK33")
ROW = AUDIT / "rk33_registry_row.md"
APPEND = AUDIT / "rk33_tasks_append.md"
REPORT = AUDIT / "rk33_registration_verification_v1.json"
BUNDLE = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk33/rk33_ppt_v1_bundle.tar.gz")
PRODUCTION_ROOT = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk33/local_coverage_v1/model_results_v1")
CLEAN_ROOT = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk33/local_coverage_v1/clean_reproduction_20e1ac38")
PPT_ROOT = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk33/ppt_v1")


def run(*args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.check_output(args, cwd=ROOT, input=input_bytes)


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def reconstruct_original_tasks_diff(worktree_tasks: bytes, append: bytes) -> tuple[bytes, bytes]:
    """Recreate the pre-RK33 worktree patch without modifying the real index or worktree."""
    if worktree_tasks.endswith(append):
        original = worktree_tasks[:-len(append)]
    else:
        original = worktree_tasks
    with tempfile.TemporaryDirectory(prefix="rk33-original-tasks-") as temporary:
        root = Path(temporary)
        fake_worktree = root / "worktree"
        target = fake_worktree / TASKS
        target.parent.mkdir(parents=True)
        target.write_bytes(original)
        env = os.environ.copy()
        env["GIT_DIR"] = str(ROOT / ".git")
        env["GIT_WORK_TREE"] = str(fake_worktree)
        env["GIT_INDEX_FILE"] = str(root / "index")
        subprocess.check_output(["git", "read-tree", EXPECTED_HEAD], cwd=ROOT, env=env)
        diff = subprocess.check_output(["git", "diff", "--", str(TASKS)], cwd=ROOT, env=env)
    return original, diff


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.prepare == args.verify_only:
        raise SystemExit("Choose exactly one of --prepare or --verify-only")

    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, details: object = None) -> None:
        checks.append({"name": name, "pass": bool(ok), "details": details})

    head = run("git", "rev-parse", "HEAD").decode().strip()
    head_registry = run("git", "show", f"HEAD:{REGISTRY}")
    head_tasks = run("git", "show", f"HEAD:{TASKS}")
    row = (ROOT / ROW).read_bytes()
    append = (ROOT / APPEND).read_bytes()
    marker = "## 2026-11-21：RK33 observed-R1".encode()

    if args.prepare:
        check("expected_pre_registration_head", head == EXPECTED_HEAD, head)
        check("registry_row_not_already_in_head", row not in head_registry)
        check("tasks_section_not_already_in_head", marker not in head_tasks)
        worktree_registry = (ROOT / REGISTRY).read_bytes()
        worktree_tasks = (ROOT / TASKS).read_bytes()
        resumed = row in worktree_registry and marker in worktree_tasks
        if resumed:
            check("resume_has_exactly_one_registry_row", worktree_registry.count(row) == 1, worktree_registry.count(row))
            check("resume_has_exactly_one_tasks_section", worktree_tasks.count(marker) == 1, worktree_tasks.count(marker))
        else:
            check("registry_row_not_already_in_worktree", row not in worktree_registry)
            check("tasks_section_not_already_in_worktree", marker not in worktree_tasks)
        if not all(c["pass"] for c in checks):
            raise SystemExit(json.dumps({"status": "FAIL", "checks": checks}, ensure_ascii=False, indent=2))

        original_tasks, before_diff = reconstruct_original_tasks_diff(worktree_tasks, append)
        check("reconstructed_preexisting_tasks_diff_sha_before", sha_bytes(before_diff) == EXPECTED_TASKS_DIFF_SHA, {"sha256": sha_bytes(before_diff), "bytes": len(before_diff), "resumed": resumed})
        if sha_bytes(before_diff) != EXPECTED_TASKS_DIFF_SHA:
            raise SystemExit("Reconstructed pre-existing tasks.md patch does not match its frozen SHA; aborting without additional writes")

        if not resumed:
            with (ROOT / REGISTRY).open("ab") as handle:
                handle.write(row)
            with (ROOT / TASKS).open("ab") as handle:
                handle.write(append)

        run("git", "add", str(REGISTRY), str(HANDOFF), str(ROW), str(APPEND), "scripts/a8_rk33_register.py")
        staged_tasks = head_tasks + append
        blob = run("git", "hash-object", "-w", "--stdin", input_bytes=staged_tasks).decode().strip()
        run("git", "update-index", "--cacheinfo", f"100644,{blob},{TASKS}")
    else:
        head_handoff = run("git", "show", f"HEAD:{HANDOFF}")
        check("registration_commit_contains_handoff", head_handoff == (ROOT / HANDOFF).read_bytes(), {"bytes": len(head_handoff)})

    staged_registry = run("git", "show", f":{REGISTRY}") if args.prepare else run("git", "show", f"HEAD:{REGISTRY}")
    staged_tasks = run("git", "show", f":{TASKS}") if args.prepare else run("git", "show", f"HEAD:{TASKS}")
    check("registry_row_exactly_once", staged_registry.count(row) == 1, staged_registry.count(row))
    check("tasks_append_exactly_once", staged_tasks.count(marker) == 1, staged_tasks.count(marker))
    if args.prepare:
        check("tasks_commit_is_head_plus_append_only", staged_tasks == head_tasks + append)
    else:
        check("tasks_append_present_in_postcommit_head", marker in head_tasks)
    check("handoff_exists_and_nonempty", (ROOT / HANDOFF).stat().st_size > 1000, (ROOT / HANDOFF).stat().st_size)

    current_tasks = (ROOT / TASKS).read_bytes()
    original_tasks, original_diff = reconstruct_original_tasks_diff(current_tasks, append)
    after_diff = run("git", "diff", "--", str(TASKS))
    check("preexisting_tasks_patch_preserved", sha_bytes(original_diff) == EXPECTED_TASKS_DIFF_SHA and current_tasks == original_tasks + append, {"reconstructed_original_sha256": sha_bytes(original_diff), "reconstructed_original_bytes": len(original_diff), "postappend_diff_sha256": sha_bytes(after_diff), "postappend_diff_bytes": len(after_diff), "worktree_is_original_plus_rk33_append": current_tasks == original_tasks + append})

    expected_hashes = {
        AUDIT / "rk33_local_coverage_result_v1.json": "d341694fb336ba579bbb990d80d7b17eafff104250052cea8577e4b927c08b64",
        AUDIT / "rk33_local_coverage_independent_v1.json": "3b53c5118bc93a71a5eaadaaaf22e48f13bc0b2d580b017308348a0ff171fa8d",
        AUDIT / "rk33_clean_reproduction_v1.json": "7808acc84567fe972be0ddb870c23bd8714da2bc1e0dbdb1421ff08a5171e455",
        AUDIT / "rk33_closeout_verification_v2.json": "ae09d302c8dd331aa59239c6e90180289e3c7ab34a030d3510e26b6af55c334b",
        Path("paper/CodonFlow_preprint_A8.md"): "1e2701a379dc362e2d1a75949ac7d20fca039ca4703e6a6f73665a09b1b0e65d",
    }
    for relative, expected in expected_hashes.items():
        actual = sha_file(ROOT / relative)
        check(f"sha_{relative.name}", actual == expected, actual)

    ppt = json.loads((ROOT / AUDIT / "ppt_v1/rk33_ppt_closeout_remote_v2.json").read_text())
    check("remote_ppt_closeout_21_of_21", ppt.get("status") == "PASS" and len(ppt.get("checks", [])) == 21 and all(c.get("pass") for c in ppt["checks"]), {"revision": ppt.get("final_revision_id"), "slides": ppt.get("final_slide_count")})
    bundle_sha = sha_file(BUNDLE)
    check("ppt_bundle_sha", bundle_sha == "804df9aac43aa55c93eaa78e4992fe75c056592244b1385eebad9c67b7e90a32", {"sha256": bundle_sha, "bytes": BUNDLE.stat().st_size})
    for name, path in [("production", PRODUCTION_ROOT), ("clean", CLEAN_ROOT), ("ppt", PPT_ROOT)]:
        files = [p for p in path.rglob("*") if p.is_file()]
        check(f"teams_{name}_artifacts_present", path.is_dir() and len(files) > 0, {"path": str(path), "files": len(files), "bytes": sum(p.stat().st_size for p in files)})

    for relative in [Path("docs/handover/A8_RK_tasks.md"), Path("audits/20261121/RK32/a8_rk32_run_structure_definition.py")]:
        check(f"preexisting_untracked_preserved_{relative.name}", (ROOT / relative).is_file())

    if args.prepare:
        allowed = {str(REGISTRY), str(TASKS), str(HANDOFF), str(ROW), str(APPEND), "scripts/a8_rk33_register.py", str(REPORT)}
        staged_names = set(run("git", "diff", "--cached", "--name-only").decode().splitlines())
        check("only_allowed_paths_staged_before_report", staged_names <= allowed, sorted(staged_names))
        diff_check = subprocess.run(["git", "diff", "--cached", "--check"], cwd=ROOT, capture_output=True)
        check("staged_diff_check", diff_check.returncode == 0, diff_check.stderr.decode(errors="replace"))

    report = {
        "schema": "a8-rk33-registration-verification-v1",
        "mode": "prepare" if args.prepare else "verify-only",
        "head": head,
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "checks_passed": sum(bool(c["pass"]) for c in checks),
        "checks_total": len(checks),
        "checks": checks,
        "nonclaims": "Registration verifies evidence and worktree hygiene only; it does not close external SOTA, time-matched, full seven-method dense, functional/protein OOD, prospective DBTL or RK-G1.",
    }
    if args.prepare:
        (ROOT / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        run("git", "add", str(REPORT))
        staged_names = set(run("git", "diff", "--cached", "--name-only").decode().splitlines())
        if staged_names != {str(REGISTRY), str(TASKS), str(HANDOFF), str(ROW), str(APPEND), "scripts/a8_rk33_register.py", str(REPORT)}:
            raise SystemExit("Unexpected final staged set: " + repr(sorted(staged_names)))
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
