#!/usr/bin/env python3
"""Finalize the G0 online-slide closeout from independently stored checks."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=str(Path(__file__).resolve().parent))
    args = ap.parse_args()
    root = Path(args.workdir).resolve()
    verification_path = root / "g0_ppt_verification_v01.json"
    visual_path = root / "g0_ppt_visual_review_v01.json"
    verification = load(verification_path)
    visual = load(visual_path)
    screenshot = root / visual["screenshot"]["path"]
    paper = load(root / "a8_g0_closeout_paper_verification_v30.json")
    production = load(root / "g0_unified_cost_closeout_v2.json")
    independent = load(root / "g0_unified_cost_closeout_independent_v1.json")
    science_final = load(root / "g0_unified_cost_closeout_finalization_v1.json")
    checks = []

    def check(name, passed):
        checks.append({"name": name, "pass": bool(passed)})

    check("slide_verification_47", verification["overall_pass"] and verification["check_counts"] == {"passed": 47, "total": 47})
    check("old_105_pages_preserved", verification["old_pages_semantically_unchanged"] and not verification["old_page_differences"])
    check("live_page_and_revision", verification["slide_id"] == "pZg" and verification["slide_number"] == 106
          and verification["before_revision"] == 67 and verification["after_revision"] == 68)
    check("visual_review", visual["status"] == "PASS" and visual["reviewed_image"]
          and not visual["inspection"]["clipping_detected"] and not visual["inspection"]["overlap_detected"]
          and not visual["inspection"]["missing_glyphs_detected"])
    check("screenshot_hash", screenshot.exists() and sha(screenshot) == visual["screenshot"]["sha256"])
    check("paper_127", paper["overall_pass"] and paper["check_counts"] == {"passed": 127, "total": 127})
    check("science_179_357_6", production["technical_passed_checks"] == 179 and independent["passed_checks"] == 357
          and independent["max_numeric_delta"] == 0 and science_final["passed_checks"] == 6)
    check("verification_input_hashes", all((root / name).exists() and sha(root / name) == value
          for name, value in verification["hashes"].items()))
    check("research_gate_unchanged", not production["boundaries"]["rk_g1_passed"]
          and not production["boundaries"]["generator_training_authorized"])
    check("closeout_bounded", production["g0_status"] == "PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY"
          and not production["boundaries"]["complete_sota"] and not production["boundaries"]["time_matched_complete"])
    report = {
        "schema": "a8-g0-ppt-closeout-finalization-v1",
        "status": "PASS_G0_PPT_CLOSEOUT" if all(c["pass"] for c in checks) else "FAIL",
        "overall_pass": all(c["pass"] for c in checks),
        "presentation": verification["presentation"],
        "slide_id": verification["slide_id"],
        "slide_number": verification["slide_number"],
        "revision_id": verification["after_revision"],
        "old_pages_semantically_unchanged": verification["old_pages_semantically_unchanged"],
        "visual_review_pass": visual["status"] == "PASS",
        "paper_version": "v30",
        "science_commit": "e8bf9d37ecee83e7caa2ec8997717e85e99f8d28",
        "g0_status": production["g0_status"],
        "rk_g1_passed": False,
        "generator_training_authorized": False,
        "check_counts": {"passed": sum(c["pass"] for c in checks), "total": len(checks)},
        "checks": checks,
        "evidence": {
            "slide_verification": {"path": str(verification_path), "sha256": sha(verification_path)},
            "visual_review": {"path": str(visual_path), "sha256": sha(visual_path)},
            "screenshot": {"path": str(screenshot), "sha256": sha(screenshot)},
        },
    }
    output = root / "g0_ppt_closeout_finalization_v1.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "check_counts": report["check_counts"],
                      "output": str(output)}, indent=2))
    if not report["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
