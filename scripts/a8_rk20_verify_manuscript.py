#!/usr/bin/env python3
"""Independently verify the RK20 manuscript-only synchronization."""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path


EXPECTED_BEFORE = "69dca1082bf7ca1edac69d94f80df018b26e723fbc19832da1df618a5a649dfe"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in [
        "before", "after", "source-section", "prepare-check", "draft-check",
        "status", "comparison", "independent", "finalization",
        "finalization-verification", "full-regression-log", "closeout", "output",
    ]:
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    paths = {name: Path(getattr(args, name.replace("-", "_"))) for name in [
        "before", "after", "source-section", "prepare-check", "draft-check",
        "status", "comparison", "independent", "finalization",
        "finalization-verification", "full-regression-log", "closeout",
    ]}
    before = paths["before"].read_text(encoding="utf-8")
    after = paths["after"].read_text(encoding="utf-8")
    section = paths["source-section"].read_text(encoding="utf-8")
    comparison = json.loads(paths["comparison"].read_text(encoding="utf-8"))
    independent = json.loads(paths["independent"].read_text(encoding="utf-8"))
    finalization = json.loads(paths["finalization"].read_text(encoding="utf-8"))
    final_verification = json.loads(paths["finalization-verification"].read_text(encoding="utf-8"))
    prepare = json.loads(paths["prepare-check"].read_text(encoding="utf-8"))
    draft = json.loads(paths["draft-check"].read_text(encoding="utf-8"))
    writing_status = json.loads(paths["status"].read_text(encoding="utf-8"))
    regression = paths["full-regression-log"].read_text(encoding="utf-8")
    closeout = paths["closeout"].read_text(encoding="utf-8")
    checks = []

    def check(name, condition, detail=""):
        checks.append({"name": name, "passed": bool(condition), "detail": detail})

    check("frozen_before_hash", sha256(paths["before"]) == EXPECTED_BEFORE)
    check("single_new_results_section", after.count("### 6.30 Four-seed functional robustness") == 1)
    check("source_section_embedded_verbatim", section.strip() in after)
    check("single_discussion_section", after.count("## 7. Discussion") == 1)
    check("working_manuscript_not_submittable", "non-submittable working manuscript" in after)
    start = after.index("### 6.30 Four-seed functional robustness")
    discussion = after.index("## 7. Discussion", start)
    without_section = after[:start] + after[discussion:]
    without_anchors = "\n".join(
        line for line in without_section.split("\n") if not line.startswith("| RK20 ")
    )
    check("only_section_and_rk20_anchors_added", without_anchors == before)
    check("prepare_pass", prepare.get("status") == "pass")
    check("draft_pass", draft.get("status") == "pass" and not draft.get("failures"))
    check("draft_word_count", draft.get("result", {}).get("word_count") == 522)
    check("writing_status_pass", writing_status.get("status") == "PASS")
    check("source_hash_matches_draft", draft.get("result", {}).get("input_sha256") == sha256(paths["source-section"]))
    check("robustness_gate_failed", comparison.get("functional_robustness_pass") is False)
    check("two_of_eight_pass", finalization.get("fully_passed_sequence_ood_tests") == "2/8")
    check("independent_77_of_77", independent.get("status") == "PASS_INDEPENDENT_VERIFICATION" and independent.get("checks_total") == 77 and independent.get("checks_passed") == 77)
    check("finalization_67_of_67", final_verification.get("status") == "PASS_RK20_FINALIZATION" and final_verification.get("checks_total") == 67 and final_verification.get("checks_passed") == 67)
    check("finalization_gate_failed", finalization.get("functional_robustness_pass") is False)
    check("rk_g1_remains_false", finalization.get("rk_g1_pass") is False)
    check("untouched_not_accessed", finalization.get("functional_untouched_evaluated") is False)
    check("generator_not_authorized", finalization.get("expensive_generation_authorized") is False)
    check("sota_not_authorized_or_claimed", finalization.get("external_sota_authorized") is False and finalization.get("sota_claimed") is False)
    check("full_regression_counts", "340 passed" in regression and "1 skipped" in regression and "5 subtests passed" in regression)
    check("closeout_status", "PASS_RK20_COMPLETE_ROBUSTNESS_NOT_PASSED" in closeout)

    paired = {(r["left"], r["right"], r["metric"]): r for r in finalization["sequence_ood_primary_and_secondary_comparisons"]}
    expected_fragments = []
    for right, spear_p, mse_p in [
        ("ribokinetic_none", "0.126", "0.620"),
        ("ridge_all", "1.000", "0.620"),
        ("ridge_gc", "< 0.001", "< 0.001"),
        ("histgb_all", "1.000", "1.000"),
    ]:
        for endpoint, p_text in [
            ("spearman", spear_p),
            ("cluster_balanced_mse", mse_p),
        ]:
            row = paired[("ribokinetic_all", right, endpoint)]
            for key in ["delta", "ci95"]:
                values = [row[key]] if key == "delta" else row[key]
                for value in values:
                    text = f"{float(value):+.6f}".replace("-", "−")
                    expected_fragments.append(text)
            expected_fragments.append(p_text)
    check("rounded_effects_and_holm_values_present", all(fragment in section for fragment in expected_fragments), str(expected_fragments))

    anchor_files = {
        "RK20 functional multi-seed comparison summary": paths["comparison"],
        "RK20 independent raw-prediction verification": paths["independent"],
        "RK20 finalization": paths["finalization"],
        "RK20 finalization verification": paths["finalization-verification"],
        "RK20 full CPU-suite console log": paths["full-regression-log"],
        "RK20 closeout": paths["closeout"],
        "RK20 manuscript source section": paths["source-section"],
        "RK20 manuscript prepare check": paths["prepare-check"],
        "RK20 manuscript draft check": paths["draft-check"],
        "RK20 manuscript writing status": paths["status"],
    }
    for label, path in anchor_files.items():
        digest = sha256(path)
        check("anchor_" + label, f"| {label} | `{digest}` |" in after, digest)

    report = {
        "schema_version": "a8-rk20-manuscript-verification-v1",
        "status": "pass" if all(item["passed"] for item in checks) else "fail",
        "n_checks": len(checks),
        "n_passed": sum(item["passed"] for item in checks),
        "before_sha256": sha256(paths["before"]),
        "after_sha256": sha256(paths["after"]),
        "checks": checks,
        "claim_boundary": "Manuscript synchronization only; scientific gates and non-submittable status are unchanged.",
    }
    paths_out = Path(args.output)
    paths_out.parent.mkdir(parents=True, exist_ok=True)
    paths_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["status", "n_checks", "n_passed", "after_sha256"]}, indent=2))
    if report["status"] != "pass":
        for item in checks:
            if not item["passed"]:
                print("FAILED", item)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
