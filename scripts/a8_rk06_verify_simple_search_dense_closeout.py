#!/usr/bin/env python3
"""Verify RK06/MAGE manuscript, slide and documentation closeout from frozen evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audits/20261120/RK06"
OUTPUT = AUDIT / "simple_search_dense_closeout_v1.json"

PRODUCTION_SHA = "d060492c1d6882ad950ccde9782ee5cf2f8b98dfd5d24b0ea16757e6a8d2a052"
INDEPENDENT_SHA = "2e24fb6434f7e2a6967bd051ca2491fcddac88a408351a2ce0dd2520546ef6df"
FINALIZATION_SHA = "bcbf1cc2bf299c212588740eb2f15d4ccc2bb693be6d672ebd46145018eab947"
CLAIMS_SHA = "ddfccf0e6dd14bb99de4623e70e9ad93fe232a4ffded027304ae3ce2d6579ba0"
PAPER_V28_SHA = "770d8feb1cbbda289fc4e13a360ca8d1a7e72604fa55fb5b93ba1096d826d5fa"
PAPER_V29_SHA = "be9fcc72f6f5b631de89084457b3011a8c966d677b916924c795753738d6d444"
PPT_CANDIDATE_SHA = "b033ed43fb4f484cd85d7136ed6324512e89ab6e5293cfc30f8e83c0d905ba1e"
PPT_FINAL_SHA = "d40919972e585953c97a2b19157772fd7b3e7ec80f36e2fdae2fa9bfe9ee6687"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def main() -> None:
    paths = {
        "production": AUDIT / "simple_search_dense_unique18_v1.json",
        "independent": AUDIT / "simple_search_dense_independent_v2.json",
        "finalization": AUDIT / "simple_search_dense_finalization_v1.json",
        "claims": AUDIT / "simple_search_dense_claims_v1.json",
        "ppt_candidate": AUDIT / "simple_search_dense_ppt_candidate_v1.json",
        "ppt_initial": AUDIT / "simple_search_dense_ppt_verification_v1.json",
        "ppt_final": AUDIT / "simple_search_dense_ppt_verification_v2.json",
        "ppt_correction": AUDIT / "simple_search_dense_ppt_verifier_correction_v1.json",
        "paper_v28_verification": ROOT / "paper/a8_rk06_simple_search_dense_paper_verification_v28.json",
        "paper_v29_verification": ROOT / "paper/a8_rk03_mage_oof_comparator_paper_verification_v29.json",
        "paper_v29_update": ROOT / "paper/a8_rk03_mage_oof_comparator_paper_update.json",
        "paper": ROOT / "paper/CodonFlow_preprint_A8.md",
        "handoff": ROOT / "docs/handover/HANDOFF_A8_RK_20261118.md",
        "tasks": ROOT / "tasks.md",
        "handoff_tasks": ROOT / "docs/handover/tasks.md",
        "registry": ROOT / "experiments/REGISTRY.md",
        "readme": ROOT / "README.md",
    }
    data = {name: load(path) for name, path in paths.items() if path.suffix == ".json"}
    text = {name: path.read_text() for name, path in paths.items() if path.suffix == ".md"}
    checks: list[dict] = []

    def check(name: str, condition: bool, detail=None) -> None:
        row = {"check": name, "pass": bool(condition)}
        if detail is not None:
            row["detail"] = detail
        checks.append(row)

    def tokens(name: str, document: str, required: list[str]) -> None:
        missing = [token for token in required if token not in text[document]]
        check(name, not missing, {"missing": missing})

    for name, expected in [
        ("production", PRODUCTION_SHA),
        ("independent", INDEPENDENT_SHA),
        ("finalization", FINALIZATION_SHA),
        ("claims", CLAIMS_SHA),
        ("ppt_candidate", PPT_CANDIDATE_SHA),
        ("ppt_final", PPT_FINAL_SHA),
        ("paper", PAPER_V29_SHA),
    ]:
        check(f"sha256_{name}", sha256(paths[name]) == expected, sha256(paths[name]))

    production = data["production"]
    independent = data["independent"]
    finalization = data["finalization"]
    claims = data["claims"]
    check("production_panel", production["overall_pass"] and production["formal_full_panel"])
    check("production_counts", production["n_runs"] == 216 and production["n_unique_scorer_calls"] == 108000)
    check("independent_counts", independent["overall_pass"] and independent["check_counts"] == {"total": 26, "passed": 26, "failed": 0})
    check("finalization_counts", finalization["overall_pass"] and finalization["check_counts"] == {"total": 44, "passed": 44, "failed": 0})
    check("claims_gate", claims["finalization_overall_pass"] and not claims["scientific_gate_passed"] and not claims["rk_g1_closed"])
    check("claims_counts", claims["n_runs"] == 216 and claims["n_unique_scorer_calls"] == 108000)
    check("primary_test_count", len(claims["primary_tests"]) == 6)
    check("primary_decision_count", sum(row["supported_advantage"] for row in claims["primary_tests"]) == 4)

    handoff = text["handoff"]
    numeric_missing = []
    for index, row in enumerate(claims["primary_tests"]):
        for key, value in [("effect", row["effect"]), ("ci95_low", row["ci95"][0]), ("ci95_high", row["ci95"][1]), ("holm_p", row["holm_p"])]:
            if repr(value) not in handoff:
                numeric_missing.append(f"primary_{index}_{key}={value!r}")
    for index, row in enumerate(claims["method_summary"]):
        for key in ["mean_dense_auc", "mean_hv_B500", "sum_wall_clock_seconds"]:
            if repr(row[key]) not in handoff:
                numeric_missing.append(f"method_{index}_{key}={row[key]!r}")
    check("handoff_exact_scientific_numbers", not numeric_missing, numeric_missing)
    check("handoff_decision_rows", handoff.count("| SUPPORTED |") == 4 and handoff.count("| NOT SUPPORTED |") == 2)

    candidate = data["ppt_candidate"]
    ppt_initial = data["ppt_initial"]
    ppt_final = data["ppt_final"]
    check("ppt_candidate_50", candidate["status"] == "PASS" and len(candidate["checks"]) == 50 and all(row["passed"] for row in candidate["checks"]))
    check("ppt_initial_14_of_16_retained", len(ppt_initial["checks"]) == 16 and sum(row["passed"] for row in ppt_initial["checks"]) == 14)
    check("ppt_final_16", ppt_final["status"] == "PASS" and len(ppt_final["checks"]) == 16 and all(row["passed"] for row in ppt_final["checks"]))
    check("ppt_page_identity", ppt_final["baseline_slide_count"] == 104 and str(ppt_final["baseline_revision_id"]) == "66" and ppt_final["postwrite_slide_count"] == 105 and str(ppt_final["postwrite_revision_id"]) == "67" and ppt_final["new_slide_id"] == "pZp")
    check("ppt_old_pages_preserved", not ppt_final["preexisting_page_mismatches"])
    check("ppt_candidate_binding", candidate["candidate_sha256"] == ppt_final["candidate_xml_sha256"])
    check("ppt_correction_retained", paths["ppt_correction"].is_file() and paths["ppt_correction"].stat().st_size > 0)

    paper_v28 = data["paper_v28_verification"]
    paper_v29 = data["paper_v29_verification"]
    paper_update = data["paper_v29_update"]
    check("paper_v28_verification", paper_v28["overall_pass"] and paper_v28["check_counts"] == {"total": 24, "passed": 24, "failed": 0} and paper_v28["candidate_fact_counts"] == {"total": 73, "passed": 73, "failed": 0})
    check("paper_v29_verification", paper_v29["overall_pass"] and paper_v29["check_counts"] == {"passed": 61, "total": 61})
    check("paper_increment_chain", paper_update["base_sha256"] == PAPER_V28_SHA and paper_update["new_sha256"] == PAPER_V29_SHA)
    check("paper_sections", text["paper"].count("### 6.24 ") == 1 and text["paper"].count("### 6.25 ") == 1)
    check("paper_gate", "non-submittable working manuscript" in text["paper"] and "DEV_NO_GO_TEST_UNTOUCHED" in text["paper"])

    common = [PAPER_V29_SHA, "0bc9ddb8a6944974ad72dce91b3eb6fd8d81690d", "a68b07b7171093b534ad7055d7fcbddea952f350", "1fa4ca2cde0c1272d382947b2d9bf765208cc2a6"]
    tokens("handoff_closeout_tokens", "handoff", common + ["## 33. RK-06", "## 34. RK-06", "105 页、revision 67、末页 `pZp`", "26/26 PASS", "44/44 PASS", "16/16 PASS", "RK-G1 仍未通过"])
    tokens("tasks_closeout_tokens", "tasks", common + ["216 runs、108,000 calls", "4/6 SUPPORTED", "第 105 页 `pZp`", "RK-G1=false", "DEV_NO_GO_TEST_UNTOUCHED"])
    tokens("handoff_tasks_closeout_tokens", "handoff_tasks", common + ["216 runs、108,000 unique synonymous scorer calls", "4/6 SUPPORTED", "第 105 页 `pZp`", "61/61 PASS"])
    tokens("registry_closeout_tokens", "registry", common + ["CF-A8-RK06-SIMPLE-SEARCH-DENSE-UNIQUE18", "CF-A8-RK18-WORKING-MANUSCRIPT-V28-V29", "105 pages/revision67/last=pZp", "done_bounded_reporting_paper_synced_v29"])
    tokens("readme_closeout_tokens", "readme", common + ["216 runs / 108,000 unique synonymous scorer calls", "--independent-root", "105 页 `pZp`、revision 67", "不得再次运行"])
    stale = ["done_bounded_reporting_paper_sync_after_rk06", "论文 section/anchors 待 RK06", "论文增量排在 RK06 当前精确基线更新之后"]
    stale_found = {name: [token for token in stale if token in body] for name, body in text.items() if name != "paper"}
    stale_found = {name: found for name, found in stale_found.items() if found}
    check("no_stale_paper_sync_pending", not stale_found, stale_found)

    overall = all(row["pass"] for row in checks)
    report = {
        "schema": "a8-rk06-simple-search-dense-closeout-v1",
        "overall_pass": overall,
        "status": "CLOSEOUT_PASS" if overall else "CLOSEOUT_FAIL",
        "check_counts": {"total": len(checks), "passed": sum(row["pass"] for row in checks), "failed": sum(not row["pass"] for row in checks)},
        "checks": checks,
        "document_sha256": {name: sha256(paths[name]) for name in ["handoff", "tasks", "handoff_tasks", "registry", "readme"]},
        "evidence_sha256": {"production": PRODUCTION_SHA, "independent": INDEPENDENT_SHA, "finalization": FINALIZATION_SHA, "claims": CLAIMS_SHA, "paper_v28": PAPER_V28_SHA, "paper_v29": PAPER_V29_SHA, "ppt_candidate": PPT_CANDIDATE_SHA, "ppt_final": PPT_FINAL_SHA},
        "deck": {"slide_count": 105, "revision_id": 67, "last_slide_id": "pZp"},
        "scientific_gate_passed": False,
        "rk_g1_closed": False,
        "manuscript_submittable": False,
        "new_scorer_calls": 0,
        "full_project_pytest_run": False,
        "clean_environment_install_run": False,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "overall_pass": overall, "check_counts": report["check_counts"], "output": str(OUTPUT)}, ensure_ascii=False))
    if not overall:
        for row in checks:
            if not row["pass"]:
                print(json.dumps(row, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
