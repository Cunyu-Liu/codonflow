#!/usr/bin/env python3
"""Integrate the accepted RK41 section without changing any prior manuscript text."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT / "CodonFlow_preprint_A8.md"
SECTION = ROOT / "paper-write-en-rk41/.workflow/paper_final.md"
SUMMARY = ROOT / "rk41_internal_basin_initialization_v1.json"
OUTPUT = ROOT / "CodonFlow_preprint_A8_RK41.md"
REPORT = ROOT / "rk41_manuscript_closeout_v1.json"
EXPECTED_ORIGINAL_SHA = "7a0a6dee54ff7e6c04199fb9b96671cecb8f4b3e8c762586a756bded44f6b1c2"


def sha_bytes(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    checks = []

    def check(name, ok, detail=None):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    original = ORIGINAL.read_text()
    section = SECTION.read_text()
    summary = json.loads(SUMMARY.read_text())
    check("original_sha256", sha_bytes(ORIGINAL) == EXPECTED_ORIGINAL_SHA, sha_bytes(ORIGINAL))
    check("single_insertion_marker", original.count("\n## 7. Discussion\n") == 1)
    check("section_not_already_present", "### 6.52 " not in original)
    check("accepted_section_heading", section.startswith("### 6.52 Internal basin selection improves simple search but does not close the common-input actual-set gap\n"))
    check("accepted_section_has_two_tables", "**Table 36**" in section and "**Table 37**" in section)
    check("accepted_section_no_placeholder", all(x not in section for x in ("TODO", "TBD", "placeholder", "citation needed")))
    workflow = SECTION.parent
    prepare = json.loads((workflow / "prepare_check.json").read_text())
    draft = json.loads((workflow / "draft_check.json").read_text())
    check("workflow_prepare_pass", prepare["status"] == "pass")
    check("workflow_write_pass", draft["status"] == "pass" and draft["result"]["word_count"] == 599)
    status = json.loads(subprocess.check_output([sys.executable, str(SECTION.parents[1] / "scripts/status.py"),
                                                   "--workflow", str(workflow)], text=True))
    check("workflow_deliver_pass", status["status"] == "PASS", status)
    check("accepted_source_matches_draft_check", sha_text(section) == draft["result"]["input_sha256"], sha_text(section))
    confirmatory = [t for t in summary["tests"] if t["confirmatory"]]
    check("six_primary_endpoints", len(confirmatory) == 6)
    for test in confirmatory:
        effect = f"{test['effect']:.6f}"
        lower, upper = (f"{x:.6f}" for x in test["ci95"])
        check(f"effect_{test['family']}_{test['endpoint']}", effect in section, effect)
        check(f"ci_{test['family']}_{test['endpoint']}", lower in section and upper in section, [lower, upper])
    for arm in ("raw_random_b11", "raw_pool_first_b11", "raw_pool_best_b11", "calibrated_pool_first_b11", "calibrated_pool_best_b11"):
        for endpoint in ("best_normalized_weighted_utility", "best_single_point_normalized_hv", "first_k_hv", "first_k_ned"):
            value = f"{summary['absolute_performance'][arm][endpoint]:.6f}"
            check(f"absolute_{arm}_{endpoint}", value in section, value)
    external = summary["external_reference"]
    for endpoint in ("best_normalized_weighted_utility", "best_single_point_normalized_hv", "first_k_hv", "first_k_ned"):
        value = f"{sum(row[endpoint] for row in external.values()) / len(external):.6f}"
        check(f"absolute_external_{endpoint}", value in section, value)
    check("internal_families_pass", summary["primary_family_pass"]["raw_common_input_basin_selection"] is True
          and summary["primary_family_pass"]["raw_common_input_sequential_advantage"] is True)
    check("external_family_fails", summary["primary_family_pass"]["common_input_actual_set_versus_linear_design"] is False
          and summary["common_input_actual_set_gate_passed"] is False)
    check("decision_reported", "leaves the common-input actual-set task unresolved" in section)
    check("independent_evidence_reported", "5,401/5,401" in section and "1,604 unique sequences" in section
          and "1,114/1,114" in section and "494 passed tests" in section)
    check("scientific_boundaries_reported", all(term in section for term in ("external SOTA", "time-matched", "functional improvement",
                                                                               "protein-OOD", "untouched-confirmation", "RK-G1",
                                                                               "manuscript-submittable")))
    integrated = original.replace("\n## 7. Discussion\n", "\n" + section.rstrip() + "\n\n## 7. Discussion\n", 1)
    prefix, suffix = original.split("\n## 7. Discussion\n", 1)
    new_prefix, new_suffix = integrated.split("\n### 6.52 ", 1)
    reconstructed_suffix = new_suffix.split("\n\n## 7. Discussion\n", 1)[1]
    check("prior_prefix_byte_preserved", new_prefix == prefix)
    check("prior_suffix_byte_preserved", reconstructed_suffix == suffix)
    check("single_new_section", integrated.count("### 6.52 ") == 1)
    check("table_sequence", integrated.index("**Table 35") < integrated.index("**Table 36**") < integrated.index("**Table 37**") < integrated.index("## 7. Discussion"))
    check("full_length", len(integrated.splitlines()) == len(original.splitlines()) + len(section.rstrip().splitlines()) + 1,
          len(integrated.splitlines()))
    result = {"schema": "a8-rk41-manuscript-closeout-v1", "original": str(ORIGINAL),
              "original_sha256": sha_bytes(ORIGINAL), "accepted_section_sha256": sha_text(section),
              "accepted_section_word_count": 599, "workflow_status": status["status"],
              "output": str(OUTPUT), "output_sha256": sha_text(integrated),
              "original_lines": len(original.splitlines()), "output_lines": len(integrated.splitlines()),
              "decision": summary["decision"], "common_input_actual_set_gate_passed": False,
              "scientific_gate_passed": False, "external_sota_authorized": False,
              "time_matched_comparison": False, "functional_untouched_evaluated": False,
              "rk_g1_pass": False, "manuscript_submittable": False,
              "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
              "n_checks": len(checks), "n_pass": sum(c["passed"] for c in checks), "checks": checks}
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] == "PASS":
        OUTPUT.write_text(integrated)
    print(json.dumps({k: result[k] for k in ("status", "n_checks", "n_pass", "accepted_section_sha256", "output_sha256", "output_lines")}))
    if result["status"] != "PASS":
        for item in checks:
            if not item["passed"]:
                print("FAIL", item)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
