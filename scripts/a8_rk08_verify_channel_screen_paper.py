#!/usr/bin/env python3
"""Independent file-level acceptance for the RK08 channel-screen manuscript increment."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fmt(value) -> str:
    if isinstance(value, int):
        return str(value)
    if value == 0:
        return "0"
    return repr(value).replace("-", "−")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    root = Path(args.root)
    paper = root / "paper/CodonFlow_preprint_A8.md"
    update_path = root / "paper/a8_rk08_channel_screen_paper_update_v31.json"
    update = load(update_path)
    audit = root / "audits/20261118/RK08"
    selection = load(audit / "channel_screen_selection_v1.json")
    evaluation = load(audit / "channel_screen_evaluation_v1.json")
    independent = load(audit / "channel_screen_independent_v1.json")
    final = load(audit / "channel_screen_finalization_v1.json")
    preparation = load(audit / "channel_screen_preparation_v1.json")
    protocol = load(root / "configs/a8_rk08_channel_screen_protocol_v1.json")
    unit_path = audit / "channel_screen_unit_tests_v1.console.log"
    base_snapshot = Path(update["base_snapshot"])
    base = base_snapshot.read_text(encoding="utf-8")
    current = paper.read_text(encoding="utf-8")
    section = update["section_markdown"]
    anchors = update["anchor_markdown"]
    checks = []

    def ck(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    expected_hashes = {
        "protocol": "ed46e2bf5d919f57285a7fe81182f9529406512f97f45be3ece829b78af99ba4",
        "preparation": "fe36818f673f39cbad114fc219a010d84ea71074553e9b19d53610ee7ea98d79",
        "selection": "e5ce7720485e569febf4656ab9289d12393aac04dd1642ca017dd1f53a0b26a5",
        "evaluation": "825bb36e0f8bc24586f614916a2090dd22d2fe6162d65508dc7d036250ea45ed",
        "independent": "3a5c0c5342e3421fa81298fc893655055c112425551bcc36c1c1c7f200a8565f",
    }
    evidence_paths = {
        "protocol": root / "configs/a8_rk08_channel_screen_protocol_v1.json",
        "preparation": audit / "channel_screen_preparation_v1.json",
        "selection": audit / "channel_screen_selection_v1.json",
        "evaluation": audit / "channel_screen_evaluation_v1.json",
        "independent": audit / "channel_screen_independent_v1.json",
    }
    for key, expected in expected_hashes.items():
        ck(f"frozen_{key}_sha", sha(evidence_paths[key]) == expected, sha(evidence_paths[key]))
    ck("finalization_sha", update["finalization_sha256"] == sha(audit / "channel_screen_finalization_v1.json") and bool(re.fullmatch(r"[0-9a-f]{64}", update["finalization_sha256"])))
    ck("update_record_sha", update["new_sha256"] == sha(paper), sha(paper))
    ck("base_snapshot_sha", sha(base_snapshot) == update["base_sha256"] == "6ab241c672ced7ec5f770d324487cc5deb742c0d3697afb5418d7f2b11c3024a", sha(base_snapshot))
    ck("exact_base_restoration", current.replace(section, "", 1).replace(anchors, "", 1) == base)
    ck("section_single", current.count("### 6.27 Development-selected mechanism-channel screen") == 1)
    ck("section_after_g0", current.index("### 6.26 Bounded RK-G0 readiness") < current.index("### 6.27 Development-selected") < current.index("## 7. Discussion"))
    ck("prior_g0_preserved", "### 6.26 Bounded RK-G0 readiness and unified cost ledger" in current)
    ck("working_manuscript_status", "not for submission" in current and "No SOTA claim" in current)
    ck("source_section_sha", update["section_sha256"] == hashlib.sha256(section.encode("utf-8")).hexdigest())
    source_path = root / "paper/a8_rk08_channel_screen_section_v31.md"
    draft = load(root / "paper/a8_rk08_channel_screen_draft_check_v31.json")
    prepare = load(root / "paper/a8_rk08_channel_screen_prepare_check_v31.json")
    workflow = load(root / "paper/a8_rk08_channel_screen_workflow_status_v31.json")
    ck("writing_prepare_pass", prepare.get("status") == "pass")
    ck("writing_draft_pass", draft.get("status") == "pass" and not draft.get("failures"))
    ck("writing_status_pass", workflow.get("status") == "PASS" and workflow.get("lark") == "skipped_by_user")
    ck("writing_binds_source", draft["result"]["input_sha256"] == sha(source_path) == update["source_section_sha256"])
    ck("source_heading_transform", section == source_path.read_text(encoding="utf-8").replace("# Development-selected mechanism-channel screen", "### 6.27 Development-selected mechanism-channel screen", 1))
    ck("workflow_snapshot_hashes", update["prepare_check_sha256"] == sha(root / "paper/a8_rk08_channel_screen_prepare_check_v31.json") and update["draft_check_sha256"] == sha(root / "paper/a8_rk08_channel_screen_draft_check_v31.json") and update["workflow_status_sha256"] == sha(root / "paper/a8_rk08_channel_screen_workflow_status_v31.json"))

    arms = ["all", "none", "initiation_only", "velocity_only", "decay_only", "pair_only", "no_initiation", "no_velocity", "no_decay", "no_pair"]
    ck("protocol_arm_count", protocol["arms_in_tie_break_order"] == arms, protocol["arms_in_tie_break_order"])
    ck("preparation_complete", preparation["status"] == "PASS_CHANNEL_SCREEN_PREPARATION" and len(preparation["config_hashes"]) == 10)
    ck("all_arms_screen_train_dev_only", protocol["screen"]["include_splits"] == ["train", "dev"] and preparation["screen_include_splits"] == ["train", "dev"] and preparation["test_or_ood_loaded"] is False and selection["screen_rows"] == {"train": 4019, "dev": 503})
    ck("selected_arm_all", selection["selected_arm"] == "all" and selection["status"] == "PASS_CHANNEL_SELECTION_FROZEN")
    ck("selection_test_ood_unused", selection["test_or_ood_used_for_selection"] is False)
    ck("development_partition", selection["screen_rows"]["dev"] == 503 and all(row["dev_n_rows"] == 503 and row["dev_n_clusters"] == 447 for row in selection["development_table"]))
    ck("ten_arms_4997", len(selection["development_table"]) == 10 and all(row["parameters"] == 4997 for row in selection["development_table"]))
    minimum = min(selection["development_table"], key=lambda row: (row["dev_cluster_balanced_mse"], row["tie_break_order"]))
    ck("independent_minimum_all", minimum["arm"] == "all")
    for row in selection["development_table"]:
        ck(f"dev_value_{row['arm']}", f"| {row['arm']} | {repr(row['dev_cluster_balanced_mse'])} | {row['selected_epoch']} |" in section)
    for arm in arms:
        ck(f"arm_prose_{arm}", f"`{arm}`" in section)

    comparisons = {}
    sequence_rows = [row for row in evaluation["comparisons"] if row["partition"] == "sequence_ood"]
    right_names = {"ribokinetic_none": "selected_minus_none", "ridge_all": "selected_minus_ridge_all", "ridge_gc": "selected_minus_ridge_gc"}
    for source in sequence_rows:
        name = right_names[source["right"]]
        row = comparisons.setdefault(name, {})
        prefix = "delta_spearman" if source["metric"] == "spearman" else "delta_cb_mse"
        row[prefix] = source["point_delta"]
        row[prefix + "_ci95"] = [source["ci95_low"], source["ci95_high"]]
        row[prefix + "_p_holm"] = source["holm_pvalue_within_partition"]
        row["bootstrap_valid"] = source["bootstrap_valid"]
    ck("sequence_ood_partition", evaluation["metrics"]["sequence_ood"]["ribokinetic_selected"]["n_rows"] == 1336 and evaluation["metrics"]["sequence_ood"]["ribokinetic_selected"]["n_clusters"] == 1110)
    ck("bootstrap_unit", evaluation["bootstrap"]["replicates"] == 2000 and evaluation["bootstrap"]["seed"] == 20261120 and evaluation["bootstrap"]["method"] == "operational_protein_cluster_resampling")
    ck("holm_six_per_partition", len(sequence_rows) == 6 and "six-comparison partition" in section)
    ck("comparison_count", len(comparisons) == 3)
    for name in ["selected_minus_none", "selected_minus_ridge_all", "selected_minus_ridge_gc"]:
        row = comparisons[name]
        label = name.replace("selected_minus_", "selected − ")
        rho = f"{fmt(row['delta_spearman'])} [{fmt(row['delta_spearman_ci95'][0])}, {fmt(row['delta_spearman_ci95'][1])}]"
        mse = f"{fmt(row['delta_cb_mse'])} [{fmt(row['delta_cb_mse_ci95'][0])}, {fmt(row['delta_cb_mse_ci95'][1])}]"
        expected = f"| {label} | {rho} | {fmt(row['delta_spearman_p_holm'])} | {mse} | {fmt(row['delta_cb_mse_p_holm'])} |"
        ck(f"sequence_ood_row_{name}", expected in section, expected)
    none, full, gc = (comparisons[key] for key in ["selected_minus_none", "selected_minus_ridge_all", "selected_minus_ridge_gc"])
    def supported(row):
        return (row["delta_spearman"] > 0 and row["delta_cb_mse"] < 0 and
                row["delta_spearman_ci95"][0] > 0 and row["delta_cb_mse_ci95"][1] < 0 and
                row["delta_spearman_p_holm"] < 0.05 and row["delta_cb_mse_p_holm"] < 0.05)
    ck("none_supported", supported(none))
    ck("gc_supported", supported(gc))
    ck("ridge_all_not_supported", not supported(full) and full["delta_spearman_p_holm"] == 0.532 and full["delta_cb_mse_p_holm"] == 0.636)
    ck("ridge_all_intervals_cross_zero", full["delta_spearman_ci95"][0] < 0 < full["delta_spearman_ci95"][1] and full["delta_cb_mse_ci95"][0] < 0 < full["delta_cb_mse_ci95"][1])
    ck("channel_gate_false", evaluation["channel_screen_gate_pass"] is False and "channel-screen gate therefore remained false" in section)
    ck("rk_g1_false", evaluation["rk_g1_pass"] is False and "cannot close RK-G1" in section)
    ck("generator_unauthorized", evaluation["expensive_generation_authorized"] is False and "generator training remains unauthorized" in section)
    ck("functional_untouched", evaluation["functional_untouched_evaluated"] is False and "19,072 functional-untouched" in section and "Functional untouched was not evaluated" in section)
    ck("velocity_boundary", "earlier velocity endpoint remains failed" in section)
    ck("no_overclaim", "no functional, wet-lab, complete-SOTA, or submittable-manuscript claim is made" in section)
    ck("not_causal", "does not isolate a replacement single-channel mechanism" in section and "nor does it show that the combined mechanism channels add robust predictive information beyond the full-proxy ridge" in section)
    ck("bitwise_diagnostic", "bitwise-equal state dictionaries" in section and "byte-identical" in section and "rather than a new performance claim" in section)

    ck("independent_320", independent["check_counts"] == {"passed": 320, "total": 320} and "320/320 checks" in section)
    ck("independent_delta", abs(independent["max_numeric_delta"] - 1.9095836023552692e-14) == 0 and repr(independent["max_numeric_delta"]) in section)
    ck("independent_hash_chain", independent["hashes"]["selection"] == sha(audit / "channel_screen_selection_v1.json") and independent["hashes"]["evaluation"] == sha(audit / "channel_screen_evaluation_v1.json"))
    ck("finalization_42", final["status"] == "PASS_CHANNEL_SCREEN_CLOSEOUT" and final["check_counts"] == {"passed": 42, "total": 42} and "42/42 checks" in section)
    ck("unit_tests_8", "8 passed" in unit_path.read_text(encoding="utf-8") and "8/8 tests" in section)
    ck("finalization_head", final["git_head_at_finalization"] == "9fc6353399db2e33ccb56c2a6b1afbd4d4340170")

    for label, info in update["evidence"].items():
        path = Path(info["path"])
        ck(f"evidence_path_{label}", path == root / path.relative_to(root) if path.is_absolute() else False)
        ck(f"evidence_sha_{label}", path.is_file() and sha(path) == info["sha256"])
        snapshot = Path(update["snapshot_directory"]) / path.name
        ck(f"snapshot_{label}", snapshot.is_file() and sha(snapshot) == info["sha256"])
        ck(f"anchor_{label}", f"| {label} | `{info['sha256']}` |" in current)
    ck("update_hash_fields", update["protocol_sha256"] == expected_hashes["protocol"] and update["selection_sha256"] == expected_hashes["selection"] and update["evaluation_sha256"] == expected_hashes["evaluation"] and update["independent_sha256"] == expected_hashes["independent"])
    ck("update_boundaries", update["channel_screen_gate_pass"] is False and update["rk_g1_pass"] is False and update["functional_untouched_evaluated"] is False and update["generator_training_authorized"] is False and update["manuscript_submittable"] is False)

    passed = sum(row["pass"] for row in checks)
    result = {
        "schema": "a8-rk08-channel-screen-paper-verification-v1",
        "status": "PASS_RK08_CHANNEL_SCREEN_PAPER_V31" if passed == len(checks) else "FAIL",
        "overall_pass": passed == len(checks),
        "check_counts": {"passed": passed, "total": len(checks)},
        "paper_sha256": sha(paper),
        "base_sha256": sha(base_snapshot),
        "update_sha256": sha(update_path),
        "selected_arm": "all",
        "channel_screen_gate_pass": False,
        "rk_g1_pass": False,
        "functional_untouched_evaluated": False,
        "generator_training_authorized": False,
        "manuscript_submittable": False,
        "checks": checks,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "check_counts": result["check_counts"], "paper_sha256": result["paper_sha256"]}, indent=2))
    if passed != len(checks):
        for row in checks:
            if not row["pass"]:
                print("FAIL", row)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
