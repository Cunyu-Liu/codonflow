#!/usr/bin/env python3
"""Append the finalized MAGE frozen dev no-go result to A8 after v20."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

HEADING = "### 6.17 Frozen MAGE synonymous-mechanism development gate"
ANCHORS = [
    ("protocol", "RK03 MAGE frozen protocol"),
    ("production", "RK03 MAGE dev production"),
    ("independent", "RK03 MAGE independent verification"),
    ("finalization", "RK03 MAGE finalization"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmt(value: float) -> str:
    return f"{value:.12f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("paper", "audit", "a7", "base-update-report", "protocol", "production", "independent", "finalization", "snapshot-dir", "update-report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.update_report.exists():
        raise FileExistsError(args.update_report)
    base = json.loads(args.base_update_report.read_text())
    if sha256(args.paper) != base["paper_sha256"] or sha256(args.audit) != base["audit_sha256"]:
        raise ValueError("paper/audit do not match the v20 proxy update")
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    final = json.loads(args.finalization.read_text())
    if not (independent["status"] == "PASS" and independent["checks_total"] == independent["checks_passed"] == 39):
        raise ValueError("MAGE independent gate is not 39/39 PASS")
    if not (final["status"] == "PASS" and final["checks_total"] == final["checks_passed"] == 12):
        raise ValueError("MAGE finalization is not 12/12 PASS")
    if final["production_sha256"] != sha256(args.production) or final["independent_sha256"] != sha256(args.independent) or final["protocol_sha256"] != sha256(args.protocol):
        raise ValueError("MAGE evidence hash mismatch")
    if production["status"] != "DEV_NO_GO_TEST_UNTOUCHED" or production["primary_test"] is not None or production["secondary"] is not None:
        raise ValueError("MAGE no-go/test-untouched boundary mismatch")
    text = args.paper.read_text()
    if HEADING in text:
        raise ValueError("MAGE section already exists")
    args.snapshot_dir.mkdir(parents=True, exist_ok=False)
    snapshot_paper = args.snapshot_dir / "CodonFlow_preprint_A8_v20.md"
    snapshot_audit = args.snapshot_dir / "a8_rk_paper_sync_audit_v20.json"
    snapshot_a7 = args.snapshot_dir / "CodonFlow_preprint_A7_v20base.md"
    for source, target in ((args.paper, snapshot_paper), (args.audit, snapshot_audit), (args.a7, snapshot_a7)):
        shutil.copy2(source, target)
    selection = production["rich_dev_selection"]
    rows = []
    for kind in ("intrinsic", "local_mfe", "rcs_only", "full_mechanism"):
        item = selection["models"][kind]
        rows.append(f"| {kind} | {item['selected_alpha']:g} | {fmt(item['dev']['rmse'])} | {fmt(item['dev']['spearman'])} |")
    counts = production["eligibility"]["split_counts"]
    section = f"""{HEADING}

I evaluated the prespecified synonymous-mechanism increment on the fixed infA MAGE data. From {production['eligibility']['eligible_constructs_all_positions']} eligible constructs across all positions, the primary rich-medium analysis retained {production['eligibility']['primary_constructs_positions_10_71']} constructs at positions 10–71. The SHA256-ordered split, frozen before model fitting, assigned {counts['train']}/{counts['dev']}/{counts['test']} constructs to train/dev/test. Four sparse ridge feature sets were compared over the same alpha grid, with alpha selected only by dev RMSE. RCS was treated as the published supervised structure score, not as an unsupervised physical ground truth.

| Feature set | Selected alpha | Dev RMSE | Dev Spearman |
|---|---:|---:|---:|
{chr(10).join(rows)}

The full mechanism model did not achieve the frozen requirement of strictly lower dev RMSE than both the intrinsic and local-MFE feature sets. The test split was therefore not authorized: no test predictions, test metrics, paired test intervals, minimal-medium transport or N-terminal transport were generated. The formal state is `DEV_NO_GO_TEST_UNTOUCHED`; this is a development-gate result, not a claim that mechanism is universally falsified. Independent raw-data and model-matrix reconstruction passed {independent['checks_passed']}/{independent['checks_total']} checks with maximum numeric delta {independent['max_numeric_delta']:.12g}, and finalization passed {final['checks_passed']}/{final['checks_total']} checks. This result does not close RK-G1 or authorize generator-training claims.

"""
    marker = "## 7. Discussion"
    if text.count(marker) != 1:
        raise ValueError("Discussion insertion marker missing")
    text = text.replace(marker, section + marker, 1)
    paths = {"protocol": args.protocol, "production": args.production, "independent": args.independent, "finalization": args.finalization}
    anchors = "".join(f"| {label} | `{sha256(paths[key])}` |\n" for key, label in ANCHORS)
    anchor_marker = "\nA7 is retained as the prior manuscript snapshot."
    if text.count(anchor_marker) != 1:
        raise ValueError("Evidence anchor marker missing")
    text = text.replace(anchor_marker, "\n" + anchors + anchor_marker, 1)
    args.paper.write_text(text)
    audit = json.loads(args.audit.read_text())
    audit["output_sha256"] = sha256(args.paper)
    audit["last_increment"] = {
        "section": HEADING[4:],
        "paper_sha256": sha256(args.paper),
        "protocol_sha256": sha256(args.protocol),
        "production_sha256": sha256(args.production),
        "independent_sha256": sha256(args.independent),
        "finalization_sha256": sha256(args.finalization),
        "scientific_scope": "frozen MAGE dev no-go only; test untouched; no universal mechanism/SOTA claim",
        "submittable": False,
    }
    args.audit.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    report = {
        "schema": "a8-rk03-mage-paper-update-v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "base_update_report_sha256": sha256(args.base_update_report),
        "paper_sha256": sha256(args.paper),
        "audit_sha256": sha256(args.audit),
        "base_snapshot": {
            "paper": str(snapshot_paper), "paper_sha256": sha256(snapshot_paper),
            "audit": str(snapshot_audit), "audit_sha256": sha256(snapshot_audit),
            "a7": str(snapshot_a7), "a7_sha256": sha256(snapshot_a7),
        },
        **{key + "_sha256": sha256(paths[key]) for key, _label in ANCHORS},
        "submittable": False,
    }
    args.update_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
