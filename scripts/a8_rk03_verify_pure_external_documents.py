#!/usr/bin/env python3
"""Read-only acceptance checks for the pure external-RCS handover records."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

EXPECTED_HASHES = {
    "configs/a8_rk03_mage_pure_external_nested_cv_protocol_v1.json": "9efd39ef21672722adde333e28f4e1144983949dfab5a6437a1f45a68e930b45",
    "audits/20261120/RK03/mage_pure_external_nested_cv_preparation_v1.json": "d5e8f16ac9cace99e5ca4ade08f918bcc58b6af9a2528ddb92651d711ebec63f",
    "audits/20261120/RK03/mage_pure_external_nested_cv_v1.json": "c39e3f3b42e126abdc3fdc0838c053c17b6c95374e841500e34196b340d663c9",
    "audits/20261120/RK03/mage_pure_external_nested_cv_independent_v1.json": "eb4153a3cb3109aff34a6e73006af30387409a64531d4b28143bec17f71da0d2",
    "audits/20261120/RK03/mage_pure_external_nested_cv_finalization_v1.json": "29561b13922e4319715fd511c4b2ac4fa911d893815c722df17e0a96fb58f8e0",
    "paper/CodonFlow_preprint_A8.md": "6c3d2a0329a46ca70d4dd782748a06c60fbecbf91fd8d8fe5d7ea1c42e2b73f0",
    "paper/a8_rk03_pure_external_rcs_paper_verification_v32.json": "12461ce66e44a055940c3b3a300b66f3c484d0f6703874e576ac1db94dac3d07",
    "paper/a8_rk03_pure_external_rcs_paper_update_v32.json": "d4e8a5603d2cb9b7be7b11517ae27535f52ba6638893abcff3e824ab2bc7962d",
    "audits/20261120/RK03/pure_external_ppt_candidate_verification_v01.json": "5a3e0e106a8a3424f82c1995671a277f77e93da608ee321c7742bac4e8c5bfa6",
    "audits/20261120/RK03/pure_external_ppt_postwrite_verification_v01.json": "270802767179c0526602343e798421a862a28419616b207dbe1bc761b7801fce",
    "audits/20261120/RK03/pure_external_ppt_online_visual_review_v01.json": "a283d2f4dc0286ec17976c46fbeca6c9d990cf453aed740536b97f55eedff6d9",
    "audits/20261120/RK03/pure_external_ppt_closeout_finalization_v1.json": "65cbdf405a598b20d36c55ed50b0ceb33df1c5921df6c2c353e035127ed722bc",
    "audits/20261120/RK03/pure_external_ppt_closeout_correction_v1.json": "b8d815538f325a2ee3b24ddb9de4a0445a15cea4667bded86aa65eee5ca6ed98",
}
DOC_PATHS = {
    "readme": "README.md",
    "root_tasks": "docs/handover/tasks.md",
    "handover_tasks": "docs/handover/A8_RK_PURE_EXTERNAL_RCS_tasks.md",
    "handoff": "docs/handover/HANDOFF_A8_RK_20261118.md",
    "registry": "experiments/REGISTRY.md",
}
NEW_MARKERS = {
    "readme": "## A8-RK：MAGE 纯外部 RCS 对照、v32 与 PPT108 closeout",
    "root_tasks": "## 2026-11-20：MAGE 纯外部 RCS 对照、论文 v32 与 PPT108 closeout",
    "handover_tasks": "## 2026-11-20：MAGE 纯外部 RCS 对照、论文 v32 与 PPT108 closeout",
    "handoff": "## 37. MAGE 纯外部 RCS 对照：替代失败，但不改变 full−intrinsic 非显著结论",
    "registry": "| CF-A8-RK03-MAGE-PURE-EXTERNAL-RCS |",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_verification(root: Path, asset_root: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any = "") -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    for rel, expected in EXPECTED_HASHES.items():
        path = root / rel
        add(f"hash:{rel}", path.is_file() and sha256(path) == expected,
            {"expected": expected, "actual": sha256(path) if path.is_file() else None})

    prep = load_json(root / "audits/20261120/RK03/mage_pure_external_nested_cv_preparation_v1.json")
    production = load_json(root / "audits/20261120/RK03/mage_pure_external_nested_cv_v1.json")
    independent = load_json(root / "audits/20261120/RK03/mage_pure_external_nested_cv_independent_v1.json")
    finalization = load_json(root / "audits/20261120/RK03/mage_pure_external_nested_cv_finalization_v1.json")
    paper = load_json(root / "paper/a8_rk03_pure_external_rcs_paper_verification_v32.json")
    paper_update = load_json(root / "paper/a8_rk03_pure_external_rcs_paper_update_v32.json")
    candidate = load_json(root / "audits/20261120/RK03/pure_external_ppt_candidate_verification_v01.json")
    postwrite = load_json(root / "audits/20261120/RK03/pure_external_ppt_postwrite_verification_v01.json")
    visual = load_json(root / "audits/20261120/RK03/pure_external_ppt_online_visual_review_v01.json")
    ppt_final = load_json(root / "audits/20261120/RK03/pure_external_ppt_closeout_finalization_v1.json")
    correction = load_json(root / "audits/20261120/RK03/pure_external_ppt_closeout_correction_v1.json")

    add("preparation:before_fitting", prep["status"] == "PASS_PRETRAIN_PREPARED" and prep["real_pure_external_model_fits"] == 0)
    add("preparation:test_excluded", prep["test_rows_in_oof"] == 0 and prep["test_authorized"] is False)
    add("production:fit_count", sum(production["fit_counts"].values()) == 375 and production["fit_counts"] == {"40261119": 125, "40261120": 125, "40261121": 125})
    add("production:pure_feature_contract", production["data_audit"]["pure_feature_columns"] == ["RCS", "delta_rcs_vs_wt", "abs_delta_rcs_vs_wt"] and production["data_audit"]["forbidden_intrinsic_features_used"] is False)
    add("production:test_excluded", production["data_audit"]["frozen_test_n_excluded"] == 33 and production["test_predictions_generated"] is False and production["test_metrics_generated"] is False)
    add("production:replacement_negative", production["pure_external_replacement_supported_development_only"] is False)
    add("production:mechanism_negative", production["mechanism_increment_pass"] is False and production["rk_g1_pass"] is False)
    add("production:generator_not_authorized", production["generator_training_authorized"] is False and production["test_authorized"] is False)
    add("production:runtime_recorded", production["elapsed_s"] == 94.4689605939202)
    add("independent:full_recompute", independent["overall_pass"] is True and independent["checks_total"] == 174 and independent["checks_passed"] == 174 and independent["checks_failed"] == 0)
    add("independent:fit_count_and_delta", independent["independent_fit_count"] == 375 and independent["max_numeric_delta"] == 0)
    add("independent:test_and_gates", independent["test_untouched"] is True and independent["rk_g1_pass"] is False and independent["generator_training_authorized"] is False)
    add("science_closeout:43_of_43", finalization["overall_pass"] is True and finalization["checks_total"] == 43 and finalization["checks_passed"] == 43 and finalization["status"] == "PASS_PURE_EXTERNAL_COMPARATOR_CLOSEOUT")

    comparisons = production["primary_comparisons"]
    pure = comparisons["pure_external_rcs_minus_intrinsic"]
    full = comparisons["full_mechanism_minus_pure_external_rcs"]
    augmented = comparisons["rcs_only_minus_pure_external_rcs"]
    add("comparison:pure_replacement_rejected", pure["supported_development_only"] is False and pure["delta_spearman"] < 0 and pure["delta_rmse"] > 0)
    add("comparison:full_over_pure_development_only", full["supported_development_only"] is True and full["delta_spearman"] > 0 and full["delta_rmse"] < 0)
    add("comparison:augmented_over_pure_development_only", augmented["supported_development_only"] is True and augmented["delta_spearman"] > 0 and augmented["delta_rmse"] < 0)
    add("comparison:multiplicity_and_sensitivity", all(c["bootstrap_replicates"] == 20000 and c["permutation_replicates"] == 20000 for c in comparisons.values()) and full["sensitivity_signs_ok"] is True and augmented["sensitivity_signs_ok"] is True)

    add("paper:v32_100_of_100", paper["overall_pass"] is True and paper["checks_total"] == 100 and paper["checks_passed"] == 100 and paper["status"] == "PASS_PURE_EXTERNAL_PAPER_V32")
    add("paper:exact_v31_rollback", paper["exact_rollback_to_v31"] is True and paper_update["exact_rollback_to_v31"] is True and paper_update["old_content_changed_outside_insertions"] is False)
    add("paper:no_reference_or_gate_change", paper["references_changed"] is False and paper["rk_g1_pass"] is False and paper["generator_training_authorized"] is False and paper["mechanism_increment_pass"] is False)
    add("paper:current_hash_matches", paper["after_sha256"] == EXPECTED_HASHES["paper/CodonFlow_preprint_A8.md"] and paper_update["after_sha256"] == paper["after_sha256"])

    add("ppt:candidate_227_of_227", candidate["overall_pass"] is True and candidate["checks_total"] == 227 and candidate["checks_passed"] == 227)
    add("ppt:postwrite_553_of_553", postwrite["overall_pass"] is True and postwrite["checks_total"] == 553 and postwrite["checks_passed"] == 553)
    add("ppt:108_rev70_pZS", postwrite["after_slide_count"] == 108 and postwrite["after_revision"] == 70 and postwrite["new_slide_number"] == 108 and postwrite["new_slide_id"] == "pZS")
    add("ppt:old_pages_preserved", postwrite["before_slide_count"] == 107 and postwrite["before_revision"] == 69 and postwrite["old_pages_semantically_unchanged"] == 107)
    add("ppt:online_visual_pass", visual["visual_pass"] is True and visual["no_overflow"] is True and visual["no_overlap"] is True and visual["legible"] is True and visual["slide_number"] == 108 and visual["slide_id"] == "pZS")
    add("ppt:closeout_32_of_32", ppt_final["overall_pass"] is True and ppt_final["check_counts"] == {"passed": 32, "total": 32} and ppt_final["status"] == "PASS_PURE_EXTERNAL_PPT_CLOSEOUT")
    add("ppt:correction_did_not_change_science", correction["scientific_content_changed"] is False and correction["candidate_xml_changed"] is False and correction["online_slide_changed_after_native_success"] is False)
    add("ppt:gates_remain_false", ppt_final["rk_g1_pass"] is False and ppt_final["test_authorized"] is False and ppt_final["generator_training_authorized"] is False and ppt_final["functional_untouched_evaluated"] is False)

    if asset_root is not None:
        science_postpush_path = asset_root / "postpush_independent.json"
        paper_postpush_path = asset_root / "paper_postpush_verification_v32.json"
        add("asset:science_postpush_exists", science_postpush_path.is_file(), str(science_postpush_path))
        add("asset:paper_postpush_exists", paper_postpush_path.is_file(), str(paper_postpush_path))
        if science_postpush_path.is_file():
            science_postpush = load_json(science_postpush_path)
            add("asset:science_postpush_174", science_postpush["overall_pass"] is True and science_postpush["checks_total"] == 174 and science_postpush["checks_passed"] == 174 and science_postpush["max_numeric_delta"] == 0)
        if paper_postpush_path.is_file():
            paper_postpush = load_json(paper_postpush_path)
            add("asset:paper_postpush_100", paper_postpush["overall_pass"] is True and paper_postpush["checks_total"] == 100 and paper_postpush["checks_passed"] == 100 and paper_postpush["after_sha256"] == paper["after_sha256"])

    texts = {name: (root / rel).read_text(encoding="utf-8") for name, rel in DOC_PATHS.items()}
    new_sections: dict[str, str] = {}
    for name, text in texts.items():
        marker = NEW_MARKERS[name]
        add(f"document:{name}:new_section_once", text.count(marker) == 1)
        new_sections[name] = text.split(marker, 1)[1] if marker in text else ""

    common = [
        "0a08eb90c3ee787578f5fac1d5f01a2b2fe72a5d",
        "b95e1244537a23c95cdda986cb60e343cfd7e4da",
        "d5959f73ac4f4812d614eee6d6c04d320dff38fc",
        "3460c2e07d6e44d09afa38e747db737aae939911",
        "6c3d2a0329a46ca70d4dd782748a06c60fbecbf91fd8d8fe5d7ea1c42e2b73f0",
        "174/174", "43/43", "100/100", "553/553", "32/32", "pZS",
    ]
    for name in ("readme", "root_tasks", "handover_tasks", "handoff"):
        for token in common:
            add(f"document:{name}:token:{token[:24]}", token in new_sections[name])

    summary_tokens = [
        "9efd39ef21672722adde333e28f4e1144983949dfab5a6437a1f45a68e930b45",
        "0.04929761172417739", "-0.13201530863899236", "0.03413327461240379", "0.6123990835404937",
        "-0.744414392179486", "-0.9403491867053566", "-0.5300791533185797", "0.0002999850007499625",
        "0.015164337111773597", "0.005846359530413134", "0.02506527402042598", "0.009449527523623819",
        "375", "33 个 test constructs", "replacement=false", "full−intrinsic", "Holm p=1",
        "227/227", "revision 70", "未运行完整项目 `pytest tests/`",
    ]
    for name in ("readme", "root_tasks", "handover_tasks"):
        for token in summary_tokens:
            add(f"document:{name}:summary:{token[:28]}", token in new_sections[name])

    handoff_tokens = summary_tokens + [
        "0.7673134542688491", "0.5631894046071572", "0.9532654793818945",
        "-0.015069408698577508", "-0.02544806838533774", "-0.005479110034720501",
        "0.7483679374061527", "0.539343123375721", "0.9432946055506556",
        "-0.015144837855690783", "-0.02536403898497323", "-0.00577083989049933",
        "-0.5442331298855756", "0.011016023254221755", "-0.5884455647566449", "0.011148755654897778",
        "0.022899062089363098", "-0.03790577728252063", "0.09011639336438297",
        "0.00009492841319608952", "-0.0014175669474227434", "0.0014564023955950885",
        "c39e3f3b42e126abdc3fdc0838c053c17b6c95374e841500e34196b340d663c9",
        "eb4153a3cb3109aff34a6e73006af30387409a64531d4b28143bec17f71da0d2",
        "29561b13922e4319715fd511c4b2ac4fa911d893815c722df17e0a96fb58f8e0",
        "12461ce66e44a055940c3b3a300b66f3c484d0f6703874e576ac1db94dac3d07",
        "5a3e0e106a8a3424f82c1995671a277f77e93da608ee321c7742bac4e8c5bfa6",
        "270802767179c0526602343e798421a862a28419616b207dbe1bc761b7801fce",
        "65cbdf405a598b20d36c55ed50b0ceb33df1c5921df6c2c353e035127ed722bc",
        "94.4689605939202", "codonflow-pure-rcs-20261120-v01", "不得重复追加 PPT `pZS`",
        "33 个 test constructs 不参与特征选择、拟合或评价",
    ]
    for token in handoff_tokens:
        add(f"document:handoff:detail:{token[:30]}", token in new_sections["handoff"])

    registry_tokens = [
        "CF-A8-RK18-WORKING-MANUSCRIPT-V32", "CF-A8-RK03-PURE-EXTERNAL-PPT-CLOSEOUT",
        "94.4689605939202", "227/227", "done_pure_rcs_replacement_false_mechanism_and_rk_g1_false_test_generator_unauthorized",
        "done_v32_recorded_non_submittable", "done_108_pages_rev70_pZS_old_pages_preserved_rk_g1_false",
        "0.7673134542688491", "0.7483679374061527", "33 test excluded",
    ]
    for token in common + registry_tokens:
        add(f"document:registry:token:{token[:30]}", token in new_sections["registry"])

    add("document:task_mirrors_identical", new_sections["root_tasks"] == new_sections["handover_tasks"])
    for name, section in new_sections.items():
        lowered = section.lower()
        add(f"document:{name}:no_gate_weakening", all(token not in lowered for token in ["rk_g1_pass=true", "rk_g1_pass = true", "generator_training_authorized=true", "generator_training_authorized = true", "test_authorized=true", "test_authorized = true"]))

    if (root / ".git").exists():
        for commit in ["0a08eb90c3ee787578f5fac1d5f01a2b2fe72a5d", "b95e1244537a23c95cdda986cb60e343cfd7e4da", "d5959f73ac4f4812d614eee6d6c04d320dff38fc", "3460c2e07d6e44d09afa38e747db737aae939911"]:
            result = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", commit, "HEAD"], capture_output=True)
            add(f"git:ancestor:{commit[:8]}", result.returncode == 0)

    failed = [c for c in checks if not c["pass"]]
    return {
        "schema": "codonflow.a8_rk03.pure_external_documentation_verification.v1",
        "status": "PASS_PURE_EXTERNAL_DOCUMENTATION" if not failed else "FAIL_PURE_EXTERNAL_DOCUMENTATION",
        "overall_pass": not failed,
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed),
        "checks_failed": len(failed),
        "failed_checks": failed,
        "checks": checks,
        "documents": {name: {"path": rel, "sha256": sha256(root / rel)} for name, rel in DOC_PATHS.items()},
        "manuscript": {"version": "v32", "sha256": paper["after_sha256"]},
        "presentation": {"pages": postwrite["after_slide_count"], "revision": postwrite["after_revision"], "last_slide_id": postwrite["new_slide_id"]},
        "scientific_boundary": {
            "pure_external_replacement_supported_development_only": production["pure_external_replacement_supported_development_only"],
            "mechanism_increment_pass": production["mechanism_increment_pass"],
            "rk_g1_pass": production["rk_g1_pass"],
            "test_authorized": production["test_authorized"],
            "generator_training_authorized": production["generator_training_authorized"],
        },
        "reproduction_boundary": "Full-project pytest, clean installation, and an end-to-end reproduction were not established by this record.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--asset-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_verification(args.root, args.asset_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["status", "overall_pass", "checks_total", "checks_passed", "checks_failed"]}, ensure_ascii=False))
    if not report["overall_pass"]:
        print(json.dumps(report["failed_checks"], indent=2, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
