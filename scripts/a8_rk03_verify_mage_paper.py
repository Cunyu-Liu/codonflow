#!/usr/bin/env python3
"""Independent exact-increment verification for the A8 MAGE dev no-go addition."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
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
    for name in ("paper", "audit", "update-report", "base-update-report", "protocol", "production", "independent", "finalization", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    update = json.loads(args.update_report.read_text())
    base_update = json.loads(args.base_update_report.read_text())
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    final = json.loads(args.finalization.read_text())
    paper = args.paper.read_text()
    audit = json.loads(args.audit.read_text())
    base_paper = Path(update["base_snapshot"]["paper"])
    base_audit = Path(update["base_snapshot"]["audit"])
    base_a7 = Path(update["base_snapshot"]["a7"])
    checks = []

    def check(name, condition, evidence=None):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    check("update_pending", update["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("paper_update_hashes", update["paper_sha256"] == sha256(args.paper) and update["audit_sha256"] == sha256(args.audit))
    check("base_update_binding", update["base_update_report_sha256"] == sha256(args.base_update_report) and base_update["paper_sha256"] == update["base_snapshot"]["paper_sha256"] and base_update["audit_sha256"] == update["base_snapshot"]["audit_sha256"])
    check("base_snapshots_exist_and_hash", sha256(base_paper) == update["base_snapshot"]["paper_sha256"] and sha256(base_audit) == update["base_snapshot"]["audit_sha256"] and sha256(base_a7) == update["base_snapshot"]["a7_sha256"])
    check("a7_unchanged_authoritative_hash", sha256(base_a7) == "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423")
    check("heading_once_before_discussion", paper.count(HEADING) == 1 and paper.index(HEADING) < paper.index("## 7. Discussion"))
    check("evidence_gates", independent["status"] == final["status"] == "PASS" and independent["checks_total"] == independent["checks_passed"] == 39 and final["checks_total"] == final["checks_passed"] == 12)
    paths = {"protocol": args.protocol, "production": args.production, "independent": args.independent, "finalization": args.finalization}
    check("final_hash_binding", final["protocol_sha256"] == sha256(args.protocol) and final["production_sha256"] == sha256(args.production) and final["independent_sha256"] == sha256(args.independent))
    check("update_hash_binding", all(update[key + "_sha256"] == sha256(path) for key, path in paths.items()))
    check("split_and_eligibility_values", all(str(value) in paper for value in (production["eligibility"]["eligible_constructs_all_positions"], production["eligibility"]["primary_constructs_positions_10_71"], *production["eligibility"]["split_counts"].values())))
    for kind in ("intrinsic", "local_mfe", "rcs_only", "full_mechanism"):
        item = production["rich_dev_selection"]["models"][kind]
        check("dev_values." + kind, fmt(item["dev"]["rmse"]) in paper and fmt(item["dev"]["spearman"]) in paper)
    check("no_go_scope", "DEV_NO_GO_TEST_UNTOUCHED" in paper and "not a claim that mechanism is universally falsified" in paper)
    check("test_untouched_scope", all(text in paper for text in ("no test predictions", "test metrics", "paired test intervals", "minimal-medium transport", "N-terminal transport")))
    check("no_generator_or_gate_upgrade", "does not close RK-G1" in paper and "authorize generator-training claims" in paper)
    check("evidence_anchors", all(paper.count(f"| {label} |") == 1 for _key, label in ANCHORS))
    stripped = paper
    start = stripped.index(HEADING)
    end = stripped.index("## 7. Discussion", start)
    stripped = stripped[:start] + stripped[end:]
    anchor_block = "\n" + "".join(f"| {label} | `{sha256(paths[key])}` |\n" for key, label in ANCHORS)
    check("anchor_block_once", stripped.count(anchor_block) == 1)
    stripped = stripped.replace(anchor_block, "", 1)
    check("only_section_and_anchors_added_to_paper", stripped == base_paper.read_text())
    base_audit_obj = json.loads(base_audit.read_text())
    reduced_audit = dict(audit)
    if "last_increment" in base_audit_obj:
        reduced_audit["last_increment"] = base_audit_obj["last_increment"]
    else:
        reduced_audit.pop("last_increment", None)
    reduced_audit["output_sha256"] = base_audit_obj["output_sha256"]
    check("only_output_and_last_increment_changed_in_audit", reduced_audit == base_audit_obj)
    increment = audit.get("last_increment", {})
    check("audit_increment_scope", increment.get("paper_sha256") == sha256(args.paper) and increment.get("submittable") is False and "test untouched" in increment.get("scientific_scope", ""))
    check("update_not_submittable", update["submittable"] is False)
    failed = [item["name"] for item in checks if not item["pass"]]
    report = {
        "schema": "a8-rk03-mage-paper-independent-verification-v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "checks_total": len(checks), "checks_passed": len(checks) - len(failed), "failed_checks": failed,
        "paper_sha256": sha256(args.paper), "audit_sha256": sha256(args.audit),
        "update_report_sha256": sha256(args.update_report), "base_update_report_sha256": sha256(args.base_update_report),
        "checks": checks, "submittable": False,
    }
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "failed": failed}, indent=2))
    raise SystemExit(0 if not failed else 1)


if __name__ == "__main__":
    main()
