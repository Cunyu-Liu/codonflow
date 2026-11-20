#!/usr/bin/env python3
"""Apply the verified pure-RCS section to manuscript v31, with exact rollback."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BEFORE_SHA = "9c0b453d5b3fbc0e2672dc776fa718d13cc50dcc072ab654aafdfcbe3e0a3c1a"
SCIENCE_COMMIT = "b95e1244537a23c95cdda986cb60e343cfd7e4da"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/home/codonflow-a8-rk")
    parser.add_argument("--apply", action="store_true", help="required to modify the manuscript")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify without --apply")
    root = Path(args.root)
    paper = root / "paper/CodonFlow_preprint_A8.md"
    section_path = root / "paper/a8_rk03_pure_external_rcs_section_v32.md"
    before = paper.read_bytes()
    if sha_bytes(before) != BEFORE_SHA:
        raise AssertionError(f"manuscript is not frozen v31: {sha_bytes(before)}")
    text = before.decode()
    if text.count("## 7. Discussion") != 1 or text.count("### 6.28 ") or text.count("A7 is retained as the prior manuscript snapshot.") != 1:
        raise AssertionError("unexpected manuscript insertion markers")
    section_source = section_path.read_text().strip()
    if not section_source.startswith("# Pure external-RCS comparator on reused MAGE development folds"):
        raise AssertionError("unexpected section source")
    section = section_source.replace("# Pure external-RCS comparator on reused MAGE development folds", "### 6.28 Pure external-RCS comparator on reused MAGE development folds", 1)

    status_path = root / "paper/a8_rk03_pure_external_rcs_workflow_status_v32.json"
    draft_check_path = root / "paper/a8_rk03_pure_external_rcs_draft_check_v32.json"
    prepare_check_path = root / "paper/a8_rk03_pure_external_rcs_prepare_check_v32.json"
    deliver_failure_path = root / "paper/a8_rk03_pure_external_rcs_deliver_failure_v32.log"
    status = json.loads(status_path.read_text())
    draft_check = json.loads(draft_check_path.read_text())
    prepare_check = json.loads(prepare_check_path.read_text())
    if status.get("status") != "PASS" or status.get("lark") != "skipped_by_user" or draft_check.get("status") != "pass" or prepare_check.get("status") != "pass":
        raise AssertionError("writing workflow is not PASS markdown_only")
    if not deliver_failure_path.is_file() or "finish_with_status: command not found" not in deliver_failure_path.read_text():
        raise AssertionError("retained delivery tool failure is unavailable")
    correction_path = root / "paper/a8_rk03_pure_external_rcs_delivery_correction_v32.json"
    correction = {
        "schema": "a8-rk03-pure-external-paper-delivery-correction-v32",
        "status": "PASS_MARKDOWN_WITH_RETAINED_DELIVERY_TOOL_FAILURE",
        "failure": "make deliver generated paper_final.md but its shell helper finish_with_status was not found",
        "failure_log": str(deliver_failure_path),
        "failure_log_sha256": sha(deliver_failure_path),
        "subsequent_make_status": status,
        "paper_final_equals_draft": True,
        "scientific_content_changed_by_correction": False,
        "lark_document_created_or_modified": False,
        "delivery_mode": "markdown_only",
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    dump(correction_path, correction)

    anchor_files = [
        ("RK03 pure-external-RCS frozen protocol", root / "configs/a8_rk03_mage_pure_external_nested_cv_protocol_v1.json"),
        ("RK03 pure-external-RCS preparation", root / "audits/20261120/RK03/mage_pure_external_nested_cv_preparation_v1.json"),
        ("RK03 pure-external-RCS production", root / "audits/20261120/RK03/mage_pure_external_nested_cv_v1.json"),
        ("RK03 pure-external-RCS independent verification", root / "audits/20261120/RK03/mage_pure_external_nested_cv_independent_v1.json"),
        ("RK03 pure-external-RCS finalization", root / "audits/20261120/RK03/mage_pure_external_nested_cv_finalization_v1.json"),
        ("RK03 pure-external-RCS 10-test log", root / "audits/20261120/RK03/mage_pure_external_nested_cv_tests_v1.log"),
        ("RK03 pure-external-RCS manuscript source section", section_path),
        ("RK03 pure-external-RCS manuscript prepare check", prepare_check_path),
        ("RK03 pure-external-RCS manuscript draft check", draft_check_path),
        ("RK03 pure-external-RCS manuscript writing status", status_path),
        ("RK03 pure-external-RCS retained delivery failure", deliver_failure_path),
        ("RK03 pure-external-RCS delivery correction", correction_path),
    ]
    anchor_rows = "\n".join(f"| {name} | `{sha(path)}` |" for name, path in anchor_files)
    section_insert = "\n" + section + "\n\n## 7. Discussion"
    updated = text.replace("## 7. Discussion", section_insert, 1)
    anchor_marker = "\n\nA7 is retained as the prior manuscript snapshot."
    anchor_insert = "\n\n" + anchor_rows + "\n\nA7 is retained as the prior manuscript snapshot."
    if updated.count(anchor_marker) != 1:
        raise AssertionError("evidence anchor insertion marker changed")
    updated = updated.replace(anchor_marker, anchor_insert, 1)
    restored = updated.replace(section_insert, "## 7. Discussion", 1).replace(anchor_insert, anchor_marker, 1)
    if restored != text or sha_bytes(restored.encode()) != BEFORE_SHA:
        raise AssertionError("in-memory rollback does not recover v31")

    preparation_path = root / "paper/a8_rk03_pure_external_rcs_paper_update_preparation_v32.json"
    dump(preparation_path, {
        "schema": "a8-rk03-pure-external-paper-update-preparation-v32",
        "status": "PASS_BEFORE_MANUSCRIPT_UPDATE",
        "science_commit": SCIENCE_COMMIT,
        "before_sha256": BEFORE_SHA,
        "section_sha256": sha(section_path),
        "section_insert_sha256": sha_bytes(section_insert.encode()),
        "anchor_rows_sha256": sha_bytes(anchor_rows.encode()),
        "exact_rollback_verified_before_write": True,
        "old_sections_or_references_changed": False,
        "workflow_status": status["status"],
        "output_target": "markdown_only",
        "created_utc": datetime.now(timezone.utc).isoformat(),
    })
    paper.write_text(updated)
    after = paper.read_bytes()
    reread = after.decode()
    rollback = reread.replace(section_insert, "## 7. Discussion", 1).replace(anchor_insert, anchor_marker, 1)
    if sha_bytes(rollback.encode()) != BEFORE_SHA:
        paper.write_bytes(before)
        raise AssertionError("post-write rollback failed; v31 restored")
    update_report = {
        "schema": "a8-rk03-pure-external-paper-update-v32",
        "status": "PASS_MANUSCRIPT_UPDATED_PENDING_INDEPENDENT_VERIFICATION",
        "science_commit": SCIENCE_COMMIT,
        "before_sha256": BEFORE_SHA,
        "after_sha256": sha_bytes(after),
        "section_sha256": sha(section_path),
        "section_insert_sha256": sha_bytes(section_insert.encode()),
        "anchor_rows_sha256": sha_bytes(anchor_rows.encode()),
        "preparation_report_sha256": sha(preparation_path),
        "delivery_correction_sha256": sha(correction_path),
        "exact_rollback_to_v31": True,
        "old_content_changed_outside_insertions": False,
        "new_external_references": 0,
        "rk_g1_pass": False,
        "generator_training_authorized": False,
        "submittable_manuscript": False,
    }
    update_path = root / "paper/a8_rk03_pure_external_rcs_paper_update_v32.json"
    dump(update_path, update_report)
    print(json.dumps(update_report, indent=2))


if __name__ == "__main__":
    main()
