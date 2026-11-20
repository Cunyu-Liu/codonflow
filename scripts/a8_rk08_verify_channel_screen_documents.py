#!/usr/bin/env python3
"""Independently verify RK08 handover documents against frozen evidence."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    checks = []

    def check(name, condition, detail=""):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    paths = {
        "README": root / "README.md",
        "root_tasks": root / "tasks.md",
        "handover_tasks": root / "docs/handover/tasks.md",
        "handoff": root / "docs/handover/HANDOFF_A8_RK_20261118.md",
        "registry": root / "experiments/REGISTRY.md",
        "protocol": root / "configs/a8_rk08_channel_screen_protocol_v1.json",
        "preparation": root / "audits/20261118/RK08/channel_screen_preparation_v1.json",
        "selection": root / "audits/20261118/RK08/channel_screen_selection_v1.json",
        "evaluation": root / "audits/20261118/RK08/channel_screen_evaluation_v1.json",
        "independent": root / "audits/20261118/RK08/channel_screen_independent_v1.json",
        "science_finalization": root / "audits/20261118/RK08/channel_screen_finalization_v1.json",
        "manuscript": root / "paper/CodonFlow_preprint_A8.md",
        "paper_report": root / "paper/a8_rk08_channel_screen_paper_verification_v31.json",
        "paper_failed_report": root / "paper/a8_rk08_channel_screen_paper_verification_v31_failed_literal_check.json",
        "ppt_candidate": root / "audits/20261118/RK08/channel_screen_ppt_candidate_verification_v01.json",
        "ppt_report": root / "audits/20261118/RK08/channel_screen_ppt_verification_v01.json",
        "ppt_finalization": root / "audits/20261118/RK08/channel_screen_ppt_closeout_finalization_v1.json",
        "ppt_visual": root / "audits/20261118/RK08/channel_screen_ppt_visual_review_v01.json",
        "ppt_correction": root / "audits/20261118/RK08/channel_screen_ppt_closeout_correction_v1.json",
    }
    archive = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/channel_screen_ppt_v1")
    paths.update({
        "ppt_before_xml": archive / "rk08_source_v02.xml",
        "ppt_after_xml": archive / "rk08_after_v01.xml",
        "ppt_candidate_xml": archive / "rk08_slide_v01.xml",
    })
    for name, path in paths.items():
        check(f"exists:{name}", path.is_file(), str(path))
    if any(not c["pass"] for c in checks):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"status": "FAIL_MISSING_INPUTS", "checks": checks}, indent=2) + "\n")
        raise SystemExit(1)

    docs = {name: paths[name].read_text() for name in ("README", "root_tasks", "handover_tasks", "handoff", "registry")}
    data = {name: load_json(paths[name]) for name in (
        "protocol", "preparation", "selection", "evaluation", "independent", "science_finalization",
        "paper_report", "paper_failed_report", "ppt_candidate", "ppt_report", "ppt_finalization",
        "ppt_visual", "ppt_correction",
    )}
    hashes = {name: sha256(path) for name, path in paths.items()}

    expected_hashes = {
        "protocol": "ed46e2bf5d919f57285a7fe81182f9529406512f97f45be3ece829b78af99ba4",
        "preparation": "fe36818f673f39cbad114fc219a010d84ea71074553e9b19d53610ee7ea98d79",
        "selection": "e5ce7720485e569febf4656ab9289d12393aac04dd1642ca017dd1f53a0b26a5",
        "evaluation": "825bb36e0f8bc24586f614916a2090dd22d2fe6162d65508dc7d036250ea45ed",
        "independent": "3a5c0c5342e3421fa81298fc893655055c112425551bcc36c1c1c7f200a8565f",
        "manuscript": "9c0b453d5b3fbc0e2672dc776fa718d13cc50dcc072ab654aafdfcbe3e0a3c1a",
        "paper_report": "245d848ab6e8e70c30e13c8efc0a799f3765a7c0b8150d387179943849c89491",
        "paper_failed_report": "ffde5c0e08683b53bf8ed5f76f5ec0ed00e12a23b26c4385888b057f67ca57a7",
        "ppt_candidate": "cd1967296e631c79e826061bfbb9914c048aa5eb0ac24df401d40a838989989a",
        "ppt_report": "427ec28db95f31f27241adb22cd2eaf9e639253e5d9e0c9a3e2d9d46f0824bc8",
        "ppt_finalization": "0ce1a5c7fb58860d2ca9bea092d363065940c6934c10adb77acf301fafe86aa8",
        "ppt_visual": "83e3863404f7e51c12adaf246902ae8d689e40e4406e9a15b06d7d6e0171fd6c",
        "ppt_correction": "5f711fcf3b15ea90a33ee1a3ccb6e0b72712493eda9d81e8112565d4b36b8353",
        "ppt_before_xml": "11960a4ec12d74c9d61702a04481c2c7dc4094f6e7d8309f254e4db5a35cb5a9",
        "ppt_after_xml": "4f33d571c16d072f993e7143faa7398b6345d22ae332ab0e409c79d32479be1b",
        "ppt_candidate_xml": "a5cfba63c9b540d1a7783732d02b04c301130bebf01ad7914c8194ae6dd6aa99",
    }
    for name, expected in expected_hashes.items():
        check(f"immutable_sha256:{name}", hashes[name] == expected, f"{hashes[name]} != {expected}")

    selection = data["selection"]
    evaluation = data["evaluation"]
    independent = data["independent"]
    science_final = data["science_finalization"]
    check("selection:status", selection["status"] == "PASS_CHANNEL_SELECTION_FROZEN")
    check("selection:ten_arms", len(selection["development_table"]) == 10)
    check("selection:selected_all", selection["selected_arm"] == "all")
    check("selection:no_test_or_ood", selection["test_or_ood_used_for_selection"] is False)
    check("selection:untouched_false", selection["functional_untouched_evaluated"] is False)
    check("selection:gate_pending_before_evaluation", selection["channel_screen_gate_pass"] is None)
    check("selection:rk_g1_false", selection["rk_g1_pass"] is False)
    check("selection:generator_false", selection["expensive_generation_authorized"] is False)
    check("selection:protocol_binding", selection["protocol_sha256"] == hashes["protocol"])
    check("selection:preparation_binding", selection["preparation_sha256"] == hashes["preparation"])
    check("evaluation:selection_binding", evaluation["selection_sha256"] == hashes["selection"])
    check("evaluation:selected_all", evaluation["selected_arm"] == "all")
    check("evaluation:gate_false", evaluation["channel_screen_gate_pass"] is False)
    check("evaluation:rk_g1_false", evaluation["rk_g1_pass"] is False)
    check("evaluation:untouched_false", evaluation["functional_untouched_evaluated"] is False)
    check("evaluation:generator_false", evaluation["expensive_generation_authorized"] is False)
    check("independent:320_of_320", independent["check_counts"] == {"passed": 320, "total": 320})
    check("independent:overall_pass", independent["overall_pass"] is True)
    check("independent:max_delta", independent["max_numeric_delta"] == 1.9095836023552692e-14)
    check("independent:gate_false", independent["channel_screen_gate_pass"] is False)
    check("science_final:42_of_42", science_final["check_counts"] == {"passed": 42, "total": 42})
    check("science_final:status", science_final["status"] == "PASS_CHANNEL_SCREEN_CLOSEOUT")
    check("science_final:no_full_pytest", science_final["full_project_pytest_run"] is False)
    check("science_final:no_clean_install", science_final["clean_environment_install_run"] is False)

    dev_sorted = sorted(selection["development_table"], key=lambda row: row["dev_cluster_balanced_mse"])
    check("development:unique_selected_minimum", dev_sorted[0]["arm"] == "all" and dev_sorted[0]["dev_cluster_balanced_mse"] < dev_sorted[1]["dev_cluster_balanced_mse"])
    handoff_normalized = docs["handoff"].replace("−", "-")
    for rank, row in enumerate(dev_sorted, 1):
        check(f"handoff:dev_rank_{rank}_{row['arm']}", f"| {rank} | `{row['arm']}` | {repr(row['dev_cluster_balanced_mse'])} |" in handoff_normalized)
    ood = [row for row in evaluation["comparisons"] if row["partition"] == "sequence_ood"]
    check("evaluation:six_ood_comparisons", len(ood) == 6)
    for row in ood:
        metric_label = "Spearman" if row["metric"] == "spearman" else "CB-MSE"
        comparator_label = "none" if row["right"] == "ribokinetic_none" else row["right"]
        lines = [line for line in handoff_normalized.splitlines() if line.startswith("| ") and f"`{comparator_label}`" in line and metric_label in line]
        check(f"handoff:ood_row:{row['right']}:{row['metric']}", len(lines) == 1)
        if len(lines) == 1:
            cells = [cell.strip() for cell in lines[0].strip().strip("|").split("|")]
            ci = [float(value.strip()) for value in cells[3].strip("[]").split(",")]
            check(f"handoff:ood_value:{row['right']}:{row['metric']}:point_delta", float(cells[2]) == row["point_delta"], lines[0])
            check(f"handoff:ood_value:{row['right']}:{row['metric']}:ci95_low", ci[0] == row["ci95_low"], lines[0])
            check(f"handoff:ood_value:{row['right']}:{row['metric']}:ci95_high", ci[1] == row["ci95_high"], lines[0])
            check(f"handoff:ood_value:{row['right']}:{row['metric']}:holm_pvalue_within_partition", float(cells[4]) == row["holm_pvalue_within_partition"], lines[0])

    paper = data["paper_report"]
    check("paper:115_of_115", paper["check_counts"] == {"passed": 115, "total": 115})
    check("paper:overall_pass", paper["overall_pass"] is True)
    check("paper:manuscript_binding", paper["paper_sha256"] == hashes["manuscript"])
    check("paper:gate_false", paper["channel_screen_gate_pass"] is False and paper["rk_g1_pass"] is False)
    check("paper:untouched_false", paper["functional_untouched_evaluated"] is False)
    check("paper:generator_false", paper["generator_training_authorized"] is False)
    check("paper:not_submittable", paper["manuscript_submittable"] is False)
    check("paper:section_6_27", "### 6.27 Development-selected mechanism-channel screen" in paths["manuscript"].read_text())
    check("paper:failed_113_of_115", data["paper_failed_report"]["check_counts"] == {"passed": 113, "total": 115})

    candidate = data["ppt_candidate"]
    ppt = data["ppt_report"]
    ppt_final = data["ppt_finalization"]
    visual = data["ppt_visual"]
    check("ppt_candidate:103_of_103", candidate["check_counts"] == {"passed": 103, "total": 103})
    check("ppt_candidate:pass", candidate["overall_pass"] is True)
    check("ppt:223_of_223", ppt["check_counts"] == {"passed": 223, "total": 223})
    check("ppt:slide_pZZ", ppt["slide_id"] == "pZZ")
    check("ppt:revision_69", ppt["revision_id"] == 69)
    check("ppt:source_binding", ppt["source_sha256"] == hashes["ppt_before_xml"])
    check("ppt:after_binding", ppt["after_sha256"] == hashes["ppt_after_xml"])
    check("ppt:gate_false", ppt["channel_screen_gate_pass"] is False and ppt["rk_g1_pass"] is False)
    check("ppt:untouched_false", ppt["functional_untouched_evaluated"] is False)
    check("ppt:generator_false", ppt["generator_training_authorized"] is False)
    check("ppt_final:18_of_18", ppt_final["check_counts"] == {"passed": 18, "total": 18})
    check("ppt_final:page_107", ppt_final["page"] == 107 and ppt_final["slide_id"] == "pZZ")
    check("ppt_final:revision_69", ppt_final["revision_id"] == 69)
    check("ppt_final:candidate_binding", ppt_final["candidate_verification_sha256"] == hashes["ppt_candidate"])
    check("ppt_final:report_binding", ppt_final["verification_sha256"] == hashes["ppt_report"])
    check("ppt_final:visual_binding", ppt_final["visual_review_sha256"] == hashes["ppt_visual"])
    check("ppt_final:source_binding", ppt_final["source_xml_sha256"] == hashes["ppt_before_xml"])
    check("ppt_final:after_binding", ppt_final["after_xml_sha256"] == hashes["ppt_after_xml"])
    check("ppt_visual:pass", visual["visual_pass"] is True)
    check("ppt_visual:page_107", visual["page"] == 107 and visual["slide_id"] == "pZZ")
    check("ppt_visual:no_overflow", visual["no_overflow"] is True and visual["no_overlap"] is True)
    check("ppt_visual:legible", visual["legible"] is True and visual["font_rendering_pass"] is True)

    common_tokens = [
        "RK08", "ridge_all", "3.761769367012553", "0.532", "0.636", "320/320", "42/42",
        "115/115", "223/223", "18/18", "pZZ", "107", "v31",
        "9fc6353399db2e33ccb56c2a6b1afbd4d4340170",
        "d628fb8b71f5a9a264dcc14952d6f3b7eccf8a6f",
        "7d5e51a17f93218e831bc22b845c030065362a35",
        "d4afbf79e55da335f66b05507448ecd6e2fbc798",
    ]
    for doc_name, text in docs.items():
        for token in common_tokens:
            check(f"document:{doc_name}:contains:{token}", token in text)
        check(f"document:{doc_name}:negative_gate", "channel_screen_gate_pass=false" in text or "channel_screen_gate_pass` 为 false" in text or "channel_screen_gate_false" in text)
        check(f"document:{doc_name}:rk_g1_negative", "rk_g1_pass=false" in text or "RK-G1=false" in text or "rk_g1_false" in text)
        check(f"document:{doc_name}:untouched_boundary", "untouched" in text)
        check(f"document:{doc_name}:generator_boundary", "生成训练" in text or "generator" in text)
        for forbidden in (
            "channel_screen_gate_pass=true", "channel_screen_gate_pass`=true", "rk_g1_pass=true",
            "RK-G1=true", "generator_training_authorized=true", "expensive_generation_authorized=true",
            "functional_untouched_evaluated=true", "complete_sota=true",
        ):
            check(f"document:{doc_name}:forbid:{forbidden}", forbidden not in text)

    for token in (
        hashes["protocol"], hashes["preparation"], hashes["selection"], hashes["evaluation"],
        hashes["independent"], hashes["manuscript"], hashes["paper_report"], hashes["paper_failed_report"],
        hashes["ppt_report"], hashes["ppt_finalization"], hashes["ppt_before_xml"], hashes["ppt_after_xml"],
    ):
        check(f"handoff:immutable_hash_recorded:{token}", token in docs["handoff"])
    check("README:documentation_verifier_command", "a8_rk08_verify_channel_screen_documents.py" in docs["README"])
    check("README:ppt_verifier_command", "a8_rk08_verify_channel_screen_ppt.py" in docs["README"])
    check("README:large_artifact_root", "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/" in docs["README"])
    check("handoff:section_36_once", docs["handoff"].count("## 36. RK08") == 1)
    check("root_tasks:rk08_section_once", docs["root_tasks"].count("## 2026-11-20：RK08") == 1)
    check("handover_tasks:rk08_section_once", docs["handover_tasks"].count("## 2026-11-20：RK08") == 1)
    check("README:rk08_section_once", docs["README"].count("## A8-RK：RK08") == 1)

    registry_rows = {
        "CF-A8-RK08-CHANNEL-SCREEN": 1,
        "CF-A8-RK18-WORKING-MANUSCRIPT-V31": 1,
        "CF-A8-RK08-CHANNEL-SCREEN-PPT-CLOSEOUT": 1,
    }
    for run_id in registry_rows:
        lines = [line for line in docs["registry"].splitlines() if line.startswith(f"| {run_id} |")]
        check(f"registry:{run_id}:exactly_once", len(lines) == 1)
        if len(lines) == 1:
            check(f"registry:{run_id}:eleven_columns", len(lines[0].split("|")) - 2 == 11)
            check(f"registry:{run_id}:done", lines[0].rstrip().endswith("|") and "done" in lines[0].split("|")[-2])
    check("registry:preserves_g0_row", "| CF-A8-RK-G0-PPT-CLOSEOUT |" in docs["registry"])
    check("registry:preserves_rk06_row", "| CF-A8-RK06-SIMPLE-SEARCH-DENSE-UNIQUE18 |" in docs["registry"])

    failures = [c for c in checks if not c["pass"]]
    report = {
        "schema": "a8_rk08_channel_screen_documentation_verification_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_RK08_CHANNEL_SCREEN_DOCUMENTATION" if not failures else "FAIL_RK08_CHANNEL_SCREEN_DOCUMENTATION",
        "overall_pass": not failures,
        "check_counts": {"passed": len(checks) - len(failures), "total": len(checks)},
        "failures": failures,
        "document_sha256": {name: hashes[name] for name in docs},
        "evidence_sha256": {name: hashes[name] for name in expected_hashes},
        "selected_arm": selection["selected_arm"],
        "channel_screen_gate_pass": evaluation["channel_screen_gate_pass"],
        "rk_g1_pass": evaluation["rk_g1_pass"],
        "functional_untouched_evaluated": evaluation["functional_untouched_evaluated"],
        "generator_training_authorized": evaluation["expensive_generation_authorized"],
        "checks": checks,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "check_counts": report["check_counts"], "failures": len(failures), "output": str(output)}, indent=2))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
