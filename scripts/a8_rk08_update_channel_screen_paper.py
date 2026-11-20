#!/usr/bin/env python3
"""Append the independently verified RK08 channel screen to an exact manuscript base."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

MARKER = "Development-selected mechanism-channel screen"
SOURCE_HEADING = "# Development-selected mechanism-channel screen"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--expected-base-sha", required=True)
    ap.add_argument("--base-version", default="v30")
    ap.add_argument("--new-version", default="v31")
    args = ap.parse_args()
    if not re.fullmatch(r"[0-9a-f]{64}", args.expected_base_sha):
        raise SystemExit("invalid base SHA")
    root = Path(args.root)
    paper = root / "paper/CodonFlow_preprint_A8.md"
    audit = root / "audits/20261118/RK08"
    source_section = root / "paper/a8_rk08_channel_screen_section_v31.md"
    prepare_path = root / "paper/a8_rk08_channel_screen_prepare_check_v31.json"
    draft_path = root / "paper/a8_rk08_channel_screen_draft_check_v31.json"
    status_path = root / "paper/a8_rk08_channel_screen_workflow_status_v31.json"
    protocol_path = root / "configs/a8_rk08_channel_screen_protocol_v1.json"
    preparation_path = audit / "channel_screen_preparation_v1.json"
    selection_path = audit / "channel_screen_selection_v1.json"
    evaluation_path = audit / "channel_screen_evaluation_v1.json"
    independent_path = audit / "channel_screen_independent_v1.json"
    final_path = audit / "channel_screen_finalization_v1.json"
    unit_path = audit / "channel_screen_unit_tests_v1.console.log"

    base = paper.read_text(encoding="utf-8")
    if sha(paper) != args.expected_base_sha:
        raise SystemExit("manuscript base SHA mismatch")
    if MARKER in base:
        raise SystemExit("channel-screen section already exists")
    if base.count("\n## 7. Discussion") != 1 or base.count("\n\nA7 is retained as the prior manuscript snapshot.") != 1:
        raise SystemExit("unexpected manuscript structure")
    source = source_section.read_text(encoding="utf-8")
    if not source.startswith(SOURCE_HEADING + "\n"):
        raise SystemExit("unexpected source-section heading")
    prepare, draft, workflow = map(load, [prepare_path, draft_path, status_path])
    if prepare.get("status") != "pass" or draft.get("status") != "pass" or workflow.get("status") != "PASS":
        raise SystemExit("academic writing workflow did not pass")
    if draft["result"]["input_sha256"] != sha(source_section):
        raise SystemExit("writing check does not bind source section")
    selection, evaluation, independent, final = map(load, [selection_path, evaluation_path, independent_path, final_path])
    preparation = load(preparation_path)
    if selection["status"] != "PASS_CHANNEL_SELECTION_FROZEN" or selection["selected_arm"] != "all":
        raise SystemExit("invalid frozen selection")
    if independent["status"] != "PASS_CHANNEL_SCREEN_INDEPENDENT" or not independent["overall_pass"]:
        raise SystemExit("independent scientific verification failed")
    if independent["check_counts"] != {"passed": 320, "total": 320}:
        raise SystemExit("independent check count mismatch")
    if final["status"] != "PASS_CHANNEL_SCREEN_CLOSEOUT" or final["check_counts"] != {"passed": 42, "total": 42}:
        raise SystemExit("scientific closeout failed")
    if evaluation["channel_screen_gate_pass"] or evaluation["rk_g1_pass"] or evaluation["expensive_generation_authorized"]:
        raise SystemExit("scientific boundary changed")
    if evaluation["functional_untouched_evaluated"] or selection["test_or_ood_used_for_selection"] is not False:
        raise SystemExit("held-out boundary changed")
    if independent["hashes"]["selection"] != sha(selection_path) or independent["hashes"]["evaluation"] != sha(evaluation_path):
        raise SystemExit("independent hash chain mismatch")
    if final["hashes"]["independent"] != sha(independent_path):
        raise SystemExit("finalization hash chain mismatch")
    if len(selection["development_table"]) != 10 or any(row["parameters"] != 4997 for row in selection["development_table"]):
        raise SystemExit("arm count or parameter mismatch")
    if min(selection["development_table"], key=lambda row: (row["dev_cluster_balanced_mse"], row["tie_break_order"]))["arm"] != "all":
        raise SystemExit("selected arm is not the development minimum")
    if "8 passed" not in unit_path.read_text(encoding="utf-8"):
        raise SystemExit("targeted tests do not pass")

    section = source.replace(SOURCE_HEADING, "### 6.27 " + MARKER, 1)
    evidence = [
        ("RK08 channel-screen protocol", protocol_path),
        ("RK08 channel-screen preparation", preparation_path),
        ("RK08 channel-screen frozen selection", selection_path),
        ("RK08 channel-screen evaluation", evaluation_path),
        ("RK08 channel-screen independent verification", independent_path),
        ("RK08 channel-screen finalization", final_path),
        ("RK08 channel-screen 8-test log", unit_path),
        ("RK08 manuscript source section", source_section),
        ("RK08 manuscript writing draft check", draft_path),
        ("RK08 manuscript writing status", status_path),
    ]
    anchors = "\n" + "\n".join(f"| {label} | `{sha(path)}` |" for label, path in evidence)
    updated = base.replace("\n## 7. Discussion", "\n" + section + "## 7. Discussion", 1)
    updated = updated.replace("\n\nA7 is retained as the prior manuscript snapshot.", anchors + "\n\nA7 is retained as the prior manuscript snapshot.", 1)
    if updated.count("### 6.27 " + MARKER) != 1 or updated.count(section) != 1:
        raise SystemExit("section insertion count mismatch")
    restored = updated.replace(section, "", 1).replace(anchors, "", 1)
    if restored != base:
        raise SystemExit("internal exact-restoration check failed")

    snapshot = root / "paper/snapshots/channel_screen_v31"
    if snapshot.exists():
        raise SystemExit("snapshot directory already exists")
    snapshot.mkdir(parents=True)
    base_snapshot = snapshot / "CodonFlow_preprint_A8_v30.md"
    shutil.copy2(paper, base_snapshot)
    for _, path in evidence:
        shutil.copy2(path, snapshot / path.name)
    record = root / "paper/a8_rk08_channel_screen_paper_update_v31.json"
    verification = root / "paper/a8_rk08_channel_screen_paper_verification_v31.json"
    if record.exists() or verification.exists():
        raise SystemExit("paper update or verification record already exists")
    update = {
        "schema": "a8-rk08-channel-screen-paper-update-v1",
        "base_version": args.base_version,
        "new_version": args.new_version,
        "base_sha256": args.expected_base_sha,
        "new_sha256": hashlib.sha256(updated.encode("utf-8")).hexdigest(),
        "section_heading": "### 6.27 " + MARKER,
        "section_sha256": hashlib.sha256(section.encode("utf-8")).hexdigest(),
        "section_markdown": section,
        "anchor_markdown": anchors,
        "snapshot_directory": str(snapshot),
        "base_snapshot": str(base_snapshot),
        "source_section_sha256": sha(source_section),
        "prepare_check_sha256": sha(prepare_path),
        "draft_check_sha256": sha(draft_path),
        "workflow_status_sha256": sha(status_path),
        "protocol_sha256": sha(protocol_path),
        "preparation_sha256": sha(preparation_path),
        "selection_sha256": sha(selection_path),
        "evaluation_sha256": sha(evaluation_path),
        "independent_sha256": sha(independent_path),
        "finalization_sha256": sha(final_path),
        "unit_test_log_sha256": sha(unit_path),
        "evidence": {label: {"path": str(path), "sha256": sha(path)} for label, path in evidence},
        "selected_arm": "all",
        "channel_screen_gate_pass": False,
        "rk_g1_pass": False,
        "functional_untouched_evaluated": False,
        "generator_training_authorized": False,
        "manuscript_submittable": False,
    }
    paper.write_text(updated, encoding="utf-8")
    record.write_text(json.dumps(update, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"new_version": args.new_version, "new_sha256": update["new_sha256"], "section": update["section_heading"]}, indent=2))


if __name__ == "__main__":
    main()
