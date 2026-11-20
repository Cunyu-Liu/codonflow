#!/usr/bin/env python3
"""Independently verify the bounded G0 manuscript/PPT/documentation closeout."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

DOC_PATHS = {
    "readme": "README.md",
    "tasks_root": "tasks.md",
    "tasks_handoff": "docs/handover/tasks.md",
    "handoff": "docs/handover/HANDOFF_A8_RK_20261118.md",
    "registry": "experiments/REGISTRY.md",
}
BASELINE_DOC_SHA256 = {
    "readme": "3cc3b81f2d11c5706723a590390b15870ba42e9e38573d102266f96b364b58cf",
    "tasks_root": "11f181254a02f4da4ee9294f863f5afc8f7440c4ff29d43d8a899348626096c4",
    "tasks_handoff": "eba172f2f607e84598da17a6a0ba02f373174a1f1747e0a434db474385b14ae3",
    "handoff": "9c4d5e996c9fcf2f970b1a024e75c1968c7777f68d88b01154dcdd09d6f0540c",
    "registry": "dd17d26a435fdd2a01866aa955d63cbbd167ad1d62bacb19f9af276886733427",
}
COMMITS = {
    "science": "c1f641a17f4f2157be0d498d24ba363674bd7617",
    "paper": "e8bf9d37ecee83e7caa2ec8997717e85e99f8d28",
    "ppt": "44ce165e7c74419ba26bf4b422a24fc691c3de8b",
}
PAPER_SHA = "6ab241c672ced7ec5f770d324487cc5deb742c0d3697afb5418d7f2b11c3024a"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def documentation_checks(texts: dict[str, str]):
    """Return documentation-only checks; exposed for anti-weakening unit tests."""
    checks = []

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    common = [
        COMMITS["science"], COMMITS["paper"], COMMITS["ppt"], PAPER_SHA,
        "PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY", "pZg", "RK-G1=false",
        "time-matched", "non-submittable",
    ]
    for name, text in texts.items():
        missing = [token for token in common if token not in text]
        check(f"{name}_common_anchors", not missing, missing)
        compact = "".join(text.split())
        check(f"{name}_ppt_106_revision68", "106" in text and "revision68" in compact)
        check(f"{name}_generator_unauthorized", "generator_training_authorized=false" in text
              or "generator unauthorized" in text)

    for name in ("tasks_root", "tasks_handoff"):
        text = texts[name]
        check(f"{name}_g0_section_once", text.count("## 2026-11-20：RK-G0 bounded readiness、统一成本与论文/PPT closeout") == 1)
        check(f"{name}_rk03_bounded_checked", text.count("[x] RK03-REMAINING（bounded source-feasibility）") == 1
              and "[ ] RK03-REMAINING" not in text)
        check(f"{name}_retained_failures_and_counts", all(token in text for token in [
            "KeyError: lineardesign_unique_sequences", "10 个失效指针", "179/179", "357/357",
            "9/9", "6/6", "127/127", "47/47", "10/10", "max numeric delta=0",
        ]))
        check(f"{name}_open_scope_retained", all(token in text for token in [
            "external actual-set dense 完整矩阵", "full UTR–CDS remap", "RNARL 官方模型",
            "VeloHARMO 五物种", "Kudla 逐构建序列—表达表", "functional-untouched", "wet-lab/前瞻 DBTL",
            "完整项目 `pytest tests/`", "不得启动昂贵生成训练",
        ]))

    handoff = texts["handoff"]
    check("handoff_section_35_once", handoff.count("## 35. RK-G0 bounded readiness、统一成本、v30 与 PPT106 closeout") == 1)
    check("handoff_subsections_complete", all(handoff.count(f"### 35.{i}") == 1 for i in range(1, 7)))
    check("handoff_cost_and_source_boundaries", all(token in handoff for token in [
        "5459.871640930884", "6001.057458210271", "949.7424744511954", "20,939–21,078",
        "260,754 raw rows", "128,289 clean QC pairs", "CDGB source identity unresolved",
        "COformer/CHARMING=NOT_RUN", "Kudla 逐构建序列—表达表仍不可用",
        "FEASIBILITY_CLOSED_NOT_FULL_REMAP", "960×540", "44ce165e7c74419ba26bf4b422a24fc691c3de8b",
    ]))
    check("handoff_no_duplicate_slide_or_updater", "不重复追加 `pZg`" in handoff
          and "不重复执行 RK06/MAGE/G0 updater" in handoff)

    readme = texts["readme"]
    check("readme_g0_section_once", readme.count("## A8-RK：RK-G0 bounded readiness 与统一成本 closeout") == 1)
    check("readme_readonly_reproduction", all(token in readme for token in [
        "a8_g0_verify_closeout.py", "a8_g0_verify_paper_closeout.py", "a8_g0_verify_ppt_closeout.py",
        "a8_g0_finalize_ppt_closeout.py", "a8_g0_verify_closeout_documents.py",
        "g0_recheck_independent_v1.json", "不会追加在线页面或重跑生成器",
    ]))
    check("readme_cost_policy_and_gap", all(token in readme for token in [
        "null 表示未测量或不可归因，不是 0", "不同硬件、任务和评价范围不求伪总和",
        "128,289 clean QC pairs", "完整项目 `pytest tests/`", "Kudla 逐构建表",
    ]))

    registry = texts["registry"]
    row_ids = [
        "CF-A8-RK-G0-COST-READINESS", "CF-A8-RK18-WORKING-MANUSCRIPT-V30",
        "CF-A8-RK-G0-PPT-CLOSEOUT",
    ]
    for row_id in row_ids:
        lines = [line for line in registry.splitlines() if line.startswith("| " + row_id + " |")]
        check(f"registry_{row_id}_once", len(lines) == 1)
        check(f"registry_{row_id}_schema", len(lines) == 1 and lines[0].count("|") == 12)
    check("registry_acceptance_and_open_boundaries", all(token in registry for token in [
        "179/179", "357/357", "127/127", "47/47", "10/10", "max delta=0",
        "done_bounded_g0_not_complete_sota_not_rk_g1", "old 105 pages semantically unchanged",
        "generator unauthorized", "00f64ea5719ca179740f2ab6b4ffd1fefa305feb4a7b173955af14b0035fed0e",
    ]))
    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    root = args.root.resolve()
    audit = root / "audits/20261120/RK06"
    archive = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk06/g0_closeout_ppt_v1")
    output = args.output or audit / "g0_closeout_documentation_verification_v1.json"
    checks = []

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    paths = {
        "protocol": root / "configs/a8_g0_closeout_protocol_v2.json",
        "production": audit / "g0_unified_cost_closeout_v2.json",
        "independent": audit / "g0_unified_cost_closeout_independent_v1.json",
        "science_final": audit / "g0_unified_cost_closeout_finalization_v1.json",
        "science_correction": audit / "g0_closeout_correction_v1.json",
        "tests_log": audit / "g0_closeout_targeted_tests_v1.console.log",
        "paper": root / "paper/CodonFlow_preprint_A8.md",
        "paper_verification": root / "paper/a8_g0_closeout_paper_verification_v30.json",
        "ppt_verification": audit / "g0_ppt_verification_v01.json",
        "ppt_final": audit / "g0_ppt_closeout_finalization_v1.json",
        "visual": audit / "g0_ppt_visual_review_v01.json",
        "ppt_correction": audit / "g0_ppt_closeout_correction_v1.json",
        "screenshot": archive / "g0_screenshots_v01/WB1KsYGualerMUddEzMcCw1En0g_p106_pZg.jpg",
    }
    expected_hashes = {
        "protocol": "dc173e2d7e4db7e9fd115a20be6db9ee2016c67f78ee65869963f78b7eb00558",
        "production": "c0510f528615af6ef505aed83dd1c0ec5d1fa75eb900c46f6a363521c2cdd583",
        "independent": "1bf177c3ad170d3bd0385efce488402fd8e2e74611a0dc3590499e47acd93a40",
        "science_final": "9775981553bc830b9ac27aa19bf4eab5106a09901fb3863ba8e6ea8df66e4db2",
        "science_correction": "859702316cc9ff3e5af61b1dcba49c22b7b3ba228287ed7eee2d473a66b1e0fd",
        "tests_log": "808216c1e906665a6311eea3399af7e63a60328f6537b9bcf2f6f7027e943f4a",
        "paper": PAPER_SHA,
        "ppt_verification": "11480df787565c9165f02185dde646987d51d0349c84eb1079c97689b44d04d6",
        "ppt_final": "7f9c08589d33375fa4cb9aadf5d8a6f6dcd1d070bf7f6156b4a2a86d5ed69f67",
        "visual": "634a34874f5e374b12bc9f0bfc14411da08cb8ed1e1ca0fbd6e4119561c4f8b6",
        "ppt_correction": "c374e66d738603e6a7f5a8eec9133a2fcd07eb7e8c9d4adcc2aec81339719220",
        "screenshot": "00f64ea5719ca179740f2ab6b4ffd1fefa305feb4a7b173955af14b0035fed0e",
    }
    actual_hashes = {}
    for name, path in paths.items():
        check(f"exists_{name}", path.is_file(), str(path))
        if path.is_file():
            actual_hashes[name] = sha(path)
            if name in expected_hashes:
                check(f"sha_{name}", actual_hashes[name] == expected_hashes[name], actual_hashes[name])

    prod = load(paths["production"])
    ind = load(paths["independent"])
    science_final = load(paths["science_final"])
    paper_verification = load(paths["paper_verification"])
    ppt = load(paths["ppt_verification"])
    ppt_final = load(paths["ppt_final"])
    visual = load(paths["visual"])
    rows = {row["row_id"]: row for row in prod["cost_matrix"]}
    measured = sum(row["metrics"]["wall_clock_s"] is not None for row in rows.values())
    nulls = sum(row["metrics"]["wall_clock_s"] is None for row in rows.values())
    check("production_counts_recomputed", len(rows) == 22 and len(prod["gate_results"]) == 20
          and measured == 13 and nulls == 9 and prod["summary"]["measured_wall_clock_scopes"] == measured
          and prod["summary"]["explicit_null_wall_clock_scopes"] == nulls)
    check("production_all_checks", prod["technical_check_count"] == prod["technical_passed_checks"] == 179
          and len(prod["technical_checks"]) == 179 and all(x["passed"] for x in prod["technical_checks"])
          and all(x["passed"] for x in prod["gate_results"]))
    check("independent_all_checks", ind["check_count"] == ind["passed_checks"] == 357
          and len(ind["checks"]) == 357 and all(x["passed"] for x in ind["checks"])
          and ind["max_numeric_delta"] == 0)
    check("independent_source_count", sum(x["check_id"].startswith("source_sha256:") for x in ind["checks"]) == 22)
    check("science_finalization", science_final["status"] == "PASS_BOUNDED_G0_CLOSEOUT"
          and science_final["check_count"] == science_final["passed_checks"] == 6
          and all(x["passed"] for x in science_final["checks"]))
    check("targeted_test_log", "9 passed" in paths["tests_log"].read_text())
    check("bounded_status_and_open_gates", prod["g0_status"] == "PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY"
          and prod["rk03_remaining_status"] == "FEASIBILITY_CLOSED_NOT_FULL_REMAP"
          and all(value is False for value in prod["boundaries"].values()))
    check("linear_cost", rows["lineardesign_unique18"]["metrics"]["wall_clock_s"] == 5459.871640930884
          and rows["lineardesign_unique18"]["metrics"]["actual_outputs"] == 131)
    check("ensemble_cost", rows["ensembledesign_unique18"]["metrics"]["wall_clock_s"] == 6001.057458210271
          and rows["ensembledesign_unique18"]["metrics"]["actual_outputs"] == 192)
    check("ribomimo_cost", rows["ribomimo_study_ood"]["metrics"]["wall_clock_s"] == 949.7424744511954)
    check("rnarl_qc_not_generation", rows["rnarl_availability"]["metrics"]["qc_pairs"] == 128289
          and rows["rnarl_availability"]["metrics"]["wall_clock_s"] is None)
    check("no_global_cost_sum", prod["summary"]["global_wall_clock_sum"] is None)

    paper_text = paths["paper"].read_text()
    check("paper_v30_section", paper_text.count("### 6.26 Bounded RK-G0 readiness and unified cost ledger") == 1)
    check("paper_verification_127", paper_verification["overall_pass"]
          and paper_verification["check_counts"] == {"passed": 127, "total": 127}
          and paper_verification["new_sha256"] == PAPER_SHA and paper_verification["exact_base_restoration"])
    check("ppt_47", ppt["overall_pass"] and ppt["check_counts"] == {"passed": 47, "total": 47}
          and ppt["slide_id"] == "pZg" and ppt["slide_number"] == 106
          and ppt["before_revision"] == 67 and ppt["after_revision"] == 68
          and ppt["old_pages_semantically_unchanged"] and not ppt["old_page_differences"])
    check("ppt_final_10", ppt_final["status"] == "PASS_G0_PPT_CLOSEOUT"
          and ppt_final["check_counts"] == {"passed": 10, "total": 10}
          and not ppt_final["rk_g1_passed"] and not ppt_final["generator_training_authorized"])
    check("visual_pass", visual["status"] == "PASS" and visual["reviewed_image"]
          and visual["screenshot"]["sha256"] == expected_hashes["screenshot"]
          and not visual["inspection"]["clipping_detected"] and not visual["inspection"]["overlap_detected"]
          and not visual["inspection"]["missing_glyphs_detected"])

    for label, commit in COMMITS.items():
        result = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", commit, "HEAD"],
                                capture_output=True, text=True)
        check(f"commit_{label}_ancestor", result.returncode == 0, result.stderr.strip())

    texts = {name: (root / rel).read_text() for name, rel in DOC_PATHS.items()}
    checks.extend(documentation_checks(texts))
    current_doc_hashes = {name: sha(root / rel) for name, rel in DOC_PATHS.items()}
    check("documentation_changed_from_bound_baseline", all(
        current_doc_hashes[name] != BASELINE_DOC_SHA256[name] for name in DOC_PATHS))

    report = {
        "schema": "a8-g0-closeout-documentation-verification-v1",
        "status": "PASS_BOUNDED_G0_DOCUMENTATION_CLOSEOUT" if all(c["pass"] for c in checks) else "FAIL",
        "overall_pass": all(c["pass"] for c in checks),
        "scope": "Documentation/evidence closeout only; no online slide write, model fit, generator training, baseline rerun, or full-project regression.",
        "presentation": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "slide_id": "pZg",
        "slide_number": 106,
        "revision_id": 68,
        "g0_status": prod["g0_status"],
        "rk_g1_passed": False,
        "generator_training_authorized": False,
        "check_counts": {"passed": sum(c["pass"] for c in checks), "total": len(checks)},
        "checks": checks,
        "commits": COMMITS,
        "evidence_hashes": actual_hashes,
        "baseline_document_sha256": BASELINE_DOC_SHA256,
        "current_document_sha256": current_doc_hashes,
        "full_project_pytest_run": False,
        "clean_environment_install_run": False,
        "online_slide_modified_by_this_verifier": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "check_counts": report["check_counts"],
                      "output": str(output)}, ensure_ascii=False, indent=2))
    if not report["overall_pass"]:
        for item in checks:
            if not item["pass"]:
                print("FAIL", item)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
