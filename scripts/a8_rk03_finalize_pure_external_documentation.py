#!/usr/bin/env python3
"""Close out pure-RCS documentation after acceptance and mutation tests."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

DOCS = [
    "README.md",
    "docs/handover/tasks.md",
    "docs/handover/A8_RK_PURE_EXTERNAL_RCS_tasks.md",
    "docs/handover/HANDOFF_A8_RK_20261118.md",
    "experiments/REGISTRY.md",
]
COMMITS = [
    "0a08eb90c3ee787578f5fac1d5f01a2b2fe72a5d",
    "b95e1244537a23c95cdda986cb60e343cfd7e4da",
    "d5959f73ac4f4812d614eee6d6c04d320dff38fc",
    "3460c2e07d6e44d09afa38e747db737aae939911",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    audit = root / "audits/20261120/RK03"
    verification_path = audit / "pure_external_documentation_verification_v1.json"
    correction_path = audit / "pure_external_documentation_correction_v1.json"
    initial_log_path = audit / "pure_external_documentation_tests_attempt1_v1.console.log"
    final_log_path = audit / "pure_external_documentation_tests_v1.console.log"
    verification = load(verification_path)
    correction = load(correction_path)
    initial_log = initial_log_path.read_text(encoding="utf-8")
    final_log = final_log_path.read_text(encoding="utf-8")
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any = "") -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    add("verification:status", verification["status"] == "PASS_PURE_EXTERNAL_DOCUMENTATION" and verification["overall_pass"] is True)
    add("verification:243_of_243", verification["checks_total"] == 243 and verification["checks_passed"] == 243 and verification["checks_failed"] == 0 and verification["failed_checks"] == [])
    add("verification:report_hash_matches_correction", sha256(verification_path) == correction["final_verification_sha256"])
    add("mutation_tests:final_12_pass", "Ran 12 tests" in final_log and "OK" in final_log and "FAILED" not in final_log)
    add("mutation_tests:final_log_hash", sha256(final_log_path) == correction["final_test_log_sha256"])
    add("mutation_tests:initial_failure_preserved", "FAILED (failures=1)" in initial_log and sha256(initial_log_path) == correction["initial_test_log_sha256"])
    for failed_check in correction["initial_failed_checks"]:
        add(f"correction:initial_failure_recorded:{failed_check}", failed_check in initial_log)
    add("correction:exactly_three_documentation_gaps", len(correction["initial_failed_checks"]) == 3 and correction["initial_status"] == "FAIL_PURE_EXTERNAL_DOCUMENTATION")
    add("correction:no_science_change", correction["scientific_content_changed"] is False and correction["scientific_evidence_changed"] is False and correction["protocol_or_gate_changed"] is False)
    add("correction:no_paper_or_slide_change", correction["manuscript_changed"] is False and correction["online_slide_changed"] is False)
    add("correction:final_counts", correction["final_mutation_tests"] == "12/12 PASS" and correction["final_verification_checks"] == "243/243 PASS")
    add("correction:commit_scope_hygiene", correction["unrelated_preexisting_task_changes_reverted_or_deleted"] is False and correction["unrelated_preexisting_task_changes_included_in_commit"] is False)
    add("correction:clean_evidence_root", correction["clean_evidence_root"] == str(root))

    for rel in DOCS:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        recorded = next(item for item in verification["documents"].values() if item["path"] == rel)
        add(f"document:hash:{rel}", recorded["sha256"] == sha256(path))
        add(f"document:text_integrity:{rel}", "\x00" not in text and "\r" not in text and all(line == line.rstrip() for line in text.splitlines()))
    add("document:readme_correction_hash", sha256(root / "README.md") == correction["readme_sha256"])
    add("document:registry_correction_hash", sha256(root / "experiments/REGISTRY.md") == correction["registry_sha256"])
    add("document:clean_root_tasks_hash", sha256(root / "docs/handover/tasks.md") == correction["clean_root_tasks_sha256"])
    add("document:scoped_handover_tasks_hash", sha256(root / "docs/handover/A8_RK_PURE_EXTERNAL_RCS_tasks.md") == correction["scoped_handover_tasks_sha256"])

    add("manuscript:v32", verification["manuscript"] == {"version": "v32", "sha256": "6c3d2a0329a46ca70d4dd782748a06c60fbecbf91fd8d8fe5d7ea1c42e2b73f0"})
    add("presentation:108_rev70_pZS", verification["presentation"] == {"pages": 108, "revision": 70, "last_slide_id": "pZS"})
    boundary = verification["scientific_boundary"]
    add("boundary:replacement_false", boundary["pure_external_replacement_supported_development_only"] is False)
    add("boundary:mechanism_and_rk_g1_false", boundary["mechanism_increment_pass"] is False and boundary["rk_g1_pass"] is False)
    add("boundary:test_and_generator_unauthorized", boundary["test_authorized"] is False and boundary["generator_training_authorized"] is False)
    add("boundary:full_reproduction_not_overclaimed", "not established" in verification["reproduction_boundary"])

    for commit in COMMITS:
        result = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", commit, "HEAD"], capture_output=True)
        add(f"git:ancestor:{commit[:8]}", result.returncode == 0)

    failed = [check for check in checks if not check["pass"]]
    report = {
        "schema": "codonflow.a8_rk03.pure_external_documentation_finalization.v1",
        "status": "PASS_PURE_EXTERNAL_DOCUMENTATION_CLOSEOUT" if not failed else "FAIL_PURE_EXTERNAL_DOCUMENTATION_CLOSEOUT",
        "overall_pass": not failed,
        "check_counts": {"passed": len(checks) - len(failed), "failed": len(failed), "total": len(checks)},
        "failed_checks": failed,
        "checks": checks,
        "documentation_verification_sha256": sha256(verification_path),
        "documentation_correction_sha256": sha256(correction_path),
        "documentation_verifier_sha256": sha256(root / "scripts/a8_rk03_verify_pure_external_documents.py"),
        "documentation_mutation_tests_sha256": sha256(root / "scripts/a8_rk03_test_pure_external_documents.py"),
        "documents": {rel: sha256(root / rel) for rel in DOCS},
        "manuscript": verification["manuscript"],
        "presentation": verification["presentation"],
        "scientific_boundary": boundary,
        "large_artifact_policy": "Large predictions, whole-deck XML, responses and screenshots remain under /teams/HoulabData_1788502323/liucunyu/codonflow1031/ and are not committed to Git.",
        "reproduction_boundary": verification["reproduction_boundary"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "overall_pass": report["overall_pass"], "check_counts": report["check_counts"]}, ensure_ascii=False))
    if failed:
        print(json.dumps(failed, indent=2, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
