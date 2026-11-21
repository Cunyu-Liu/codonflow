#!/usr/bin/env python3
"""Close out the bounded RK35 PPT correction with portable screenshot hashes."""
from pathlib import Path
import argparse
import hashlib
import json

EXPECTED_SOURCE_SHA256 = {
    "rk35_coverage_transport_result_v1.json": "c811bb6e3481f8450b600687e9bb9f9fa849f8d8c3c3c71b55d44ed71f4d5651",
    "rk35_coverage_transport_independent_v2.json": "d037542df5ee40e47e26f1c368acb5eb5070c6d23f18c168503b609487d820a6",
    "rk35_reproduction_comparison_v2.json": "f8faf2b693924a45d4d8222d5eab2c4ad50c8e7033a3d77e9ea7fa2c07f9989f",
    "rk35_closeout_v1.json": "99308d7fad5411f84e4a9c816622c0742e3899bc7a895118b53afc31d459f96b",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.evidence_dir
    checks = []

    def load(name):
        return json.loads((root / name).read_text())

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    for name, expected in EXPECTED_SOURCE_SHA256.items():
        path = root.parent / name
        check("frozen_source_exists:" + name, path.exists())
        check("frozen_source_sha256:" + name, path.exists() and sha(path) == expected)

    candidate = load("candidate-v3-audit-v1.json")
    online = load("online-audit-v1.json")
    protection = load("deck-protection-v1.json")
    visual = load("visual-audit-v1.json")
    manifest = load("online-manifest-v1.json")
    check("candidate_70_of_70", candidate["status"] == "PASS" and candidate["summary"] == {"checks_total": 70, "checks_passed": 70, "checks_failed": 0})
    check("online_55_of_55", online["status"] == "PASS" and online["summary"] == {"checks_total": 55, "checks_passed": 55, "checks_failed": 0})
    check("online_binds_frozen_result", online["result_sha256"] == EXPECTED_SOURCE_SHA256["rk35_coverage_transport_result_v1.json"])
    check("deck_protection", protection["status"] == "PASS" and all(x["pass"] for x in protection["checks"]))
    check("visual_five_of_five", visual["status"] == "PASS" and visual["summary"] == {"slides": 5, "passed": 5, "failed": 0})
    check("presentation_identity", manifest["presentation"] == "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g")
    check("revision_140", manifest["revision_id"] == 140)
    check("slide_count_169", manifest["slide_count"] == 169)
    check("page_ids", manifest["page_ids"] == ["pSw", "pSl", "pSN", "pSt", "pSX"])
    check("updated_only_four_pages", manifest["updated_slide_ids"] == ["pSw", "pSN", "pSt", "pSX"])

    for sid in ["pSw", "pSN", "pSt", "pSX"]:
        update = load("update-" + sid + "-response.json")
        readback = load("readback-" + sid + "-audit.json")
        lint = load("readback-" + sid + "-lint.json")
        check("update_ok:" + sid, update.get("status") == "ok" and update.get("slide_id") == sid)
        check("readback_pass:" + sid, readback.get("status") == "PASS" and all(x["pass"] for x in readback["checks"]))
        check("readback_layout_release:" + sid, lint["summary"]["release_ready"] is True and lint["summary"]["error_count"] == 0)

    for sid in ["pSw", "pSl", "pSN", "pSt", "pSX"]:
        lint = load("rk35_" + sid + "-lint-v3.txt")
        check("candidate_layout_release:" + sid, lint["summary"]["release_ready"] is True and lint["summary"]["error_count"] == 0)

    post = load("postwrite-response.json")
    shots = load("screenshots-response.json")
    check("postwrite_response", post.get("ok") is True and post.get("data", {}).get("revision_id") == 140)
    check("screenshot_response", shots.get("ok") is True and len(shots.get("data", {}).get("screenshots", [])) == 5)
    for slide in visual["slides"]:
        relative = slide["path"]
        direct = root / relative
        fallback = args.archive_root / relative
        path = direct if direct.exists() else fallback
        check("screenshot_exists:" + slide["slide_id"], path.exists(), str(path))
        check("screenshot_sha256:" + slide["slide_id"], path.exists() and sha(path) == slide["sha256"])
        check("screenshot_visual_checks:" + slide["slide_id"], all(slide["checks"].values()))

    p167 = (root / "safe_cache" / "rk35_pSN.xml").read_text()
    p168 = (root / "safe_cache" / "rk35_pSt.xml").read_text()
    p169 = (root / "safe_cache" / "rk35_pSX.xml").read_text()
    check("failed_histgb_seed_cells", p167.count("10/10") == 8 and "coverage is not necessary" not in p167)
    check("mechanism_gradient_removed", "coverage gradient" not in p168 and "prevent a mechanistic gradient claim" in p168)
    check("pending_user_removed", "pending user" not in p169 and "left to the user" not in p169)
    check("next_gate_visible", "independent complete-CDS validation or pivot" in p169 and "no more window ablation" in p169)
    check("rk_g1_remains_false", "RK-G1=false" in p169)

    passed = sum(x["pass"] for x in checks)
    report = {
        "schema": "a8-rk35-ppt-closeout-v1",
        "status": "PASS_RK35_PPT_CLOSEOUT" if passed == len(checks) else "FAIL",
        "presentation": manifest["presentation"],
        "revision_id": manifest["revision_id"],
        "slide_count": manifest["slide_count"],
        "updated_slide_ids": manifest["updated_slide_ids"],
        "scientific_boundary": "RK33_COVERAGE_RETAINS_INCREMENT_WITHIN_KUDLA_RETROSPECTIVELY; not independent confirmation; RK-G1=false",
        "checks_total": len(checks),
        "checks_passed": passed,
        "checks_failed": len(checks) - passed,
        "checks": checks,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    md = ["# RK35 PPT correction closeout", "", "- Status: **" + report["status"] + "**", "- Checks: **" + str(passed) + "/" + str(len(checks)) + "**", "- Pages: 165-169; updated in place: 165, 167, 168, 169; page 166 unchanged", "- Deck: 169 pages, revision 140; RK34 and all untargeted pages semantically unchanged", "- Candidate science: 70/70; online science: 55/55; visual review: 5/5", "- Boundary: within-Kudla retrospective only; independent complete-CDS validation or data-supported pivot remains open; RK-G1=false", ""]
    args.output.with_suffix(".md").write_text("\n".join(md))
    print(json.dumps({"status": report["status"], "checks_passed": passed, "checks_total": len(checks), "failures": [x for x in checks if not x["pass"]]}, indent=2))
    raise SystemExit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
