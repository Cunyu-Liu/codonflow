#!/usr/bin/env python3
"""Close out the independently verified development-only pure-RCS comparator."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/home/codonflow-a8-rk")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    config_path = root / "configs/a8_rk03_mage_pure_external_nested_cv_protocol_v1.json"
    production_path = root / "audits/20261120/RK03/mage_pure_external_nested_cv_v1.json"
    independent_path = root / "audits/20261120/RK03/mage_pure_external_nested_cv_independent_v1.json"
    preparation_path = root / "audits/20261120/RK03/mage_pure_external_nested_cv_preparation_v1.json"
    cfg = json.loads(config_path.read_text())
    production = json.loads(production_path.read_text())
    independent = json.loads(independent_path.read_text())
    preparation = json.loads(preparation_path.read_text())
    old = json.loads(Path(cfg["source"]["nested_report"]).read_text())
    checks = []

    def check(name: str, condition: bool, detail: object = None) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("pre_registration_head", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip() == "0a08eb90c3ee787578f5fac1d5f01a2b2fe72a5d")
    check("preparation_pass", preparation["status"] == "PASS_PRETRAIN_PREPARED")
    check("preparation_zero_real_fits", preparation["real_pure_external_model_fits"] == 0)
    check("protocol_still_frozen", cfg["frozen_before_pure_external_model_fitting"] is True)
    check("production_binds_protocol", production["protocol_sha256"] == sha256(config_path))
    check("independent_binds_protocol", independent["protocol_sha256"] == sha256(config_path))
    check("independent_binds_production", independent["production_report_sha256"] == sha256(production_path))
    check("source_oof_unchanged", sha256(cfg["source"]["oof_csv"]) == cfg["source"]["oof_csv_sha256"])
    check("source_raw_features_unchanged", sha256(cfg["source"]["raw_feature_csv"]) == cfg["source"]["raw_feature_csv_sha256"])
    check("old_nested_report_unchanged", sha256(cfg["source"]["nested_report"]) == cfg["source"]["nested_report_sha256"])
    check("old_nested_code_unchanged", sha256(cfg["source"]["nested_production_script"]) == cfg["source"]["nested_production_script_sha256"])
    check("development_n", production["development_n"] == 131)
    check("development_split_counts", production["data_audit"]["original_split_counts"] == {"train": 98, "dev": 33})
    check("production_fit_count", sum(production["fit_counts"].values()) == 375)
    check("independent_fit_count", independent["independent_fit_count"] == 375)
    check("independent_overall_pass", independent["overall_pass"] is True)
    check("independent_174_checks", independent["checks_total"] == 174 and independent["checks_passed"] == 174 and independent["checks_failed"] == 0)
    check("independent_numeric_exact", independent["max_numeric_delta"] == 0.0)
    check("pure_feature_schema", production["data_audit"]["pure_feature_columns"] == ["RCS", "delta_rcs_vs_wt", "abs_delta_rcs_vs_wt"])
    check("no_categorical_or_intrinsic_features", production["data_audit"]["categorical_feature_columns"] == [] and production["data_audit"]["forbidden_intrinsic_features_used"] is False)
    artifact = Path(cfg["outputs"]["large_artifact_root"]) / "pure_external_oof_predictions.csv"
    check("large_prediction_artifact_hash", sha256(artifact) == production["artifact_files"][artifact.name]["sha256"])
    replacement = production["primary_comparisons"]["pure_external_rcs_minus_intrinsic"]
    check("pure_replacement_not_supported", production["pure_external_replacement_supported_development_only"] is False and replacement["supported_development_only"] is False)
    check("pure_replacement_spearman_worse", replacement["delta_spearman"] < 0 and replacement["delta_spearman_ci95"][1] < 0)
    check("pure_replacement_rmse_worse", replacement["delta_rmse"] > 0 and replacement["delta_rmse_ci95"][0] > 0)
    check("pure_replacement_holm_significant_adverse", replacement["holm_p_spearman"] < 0.05 and replacement["holm_p_rmse"] < 0.05)
    check("pure_replacement_sensitivity_not_favorable", replacement["sensitivity_signs_ok"] is False)
    for seed in cfg["nested_cv"]["sensitivity_outer_seeds"]:
        point = production["sensitivity"][seed]["comparisons"]["pure_external_rcs_minus_intrinsic"]
        check(f"pure_replacement_adverse_sign_{seed}", point["delta_spearman"] < 0 and point["delta_rmse"] > 0)
    check("full_over_pure_supported_bounded", production["full_over_pure_supported_development_only"] is True)
    check("intrinsic_augmentation_over_pure_supported_bounded", production["intrinsic_augmentation_over_pure_supported_development_only"] is True)
    old_contrast = old["primary_comparisons"]["full_mechanism_minus_intrinsic"]
    check("old_full_intrinsic_ci_cross_zero", old_contrast["delta_spearman_ci95"][0] < 0 < old_contrast["delta_spearman_ci95"][1] and old_contrast["delta_rmse_ci95"][0] < 0 < old_contrast["delta_rmse_ci95"][1])
    check("old_full_intrinsic_holm_one", old_contrast["holm_p_spearman"] == 1.0 and old_contrast["holm_p_rmse"] == 1.0)
    check("old_no_go_retained", old["status"] == "DEV_NO_GO_TEST_UNTOUCHED" and old["development_go"] is False)
    for key in ("test_predictions_generated", "test_metrics_generated", "original_dev_no_go_modified", "test_authorized", "mechanism_increment_pass", "rk_g1_pass", "generator_training_authorized"):
        check(f"boundary_{key}", production[key] is False)
    check("test_feature_rows_zero", production["test_construct_feature_rows_selected"] == 0)
    check("functional_untouched_not_evaluated", cfg["gate_and_interpretation"]["functional_untouched_evaluated"] is False)
    check("complete_sota_not_claimed", cfg["gate_and_interpretation"]["complete_sota"] is False)

    passed = sum(row["pass"] for row in checks)
    failed = len(checks) - passed
    report = {
        "schema": "a8-rk03-mage-pure-external-nested-cv-finalization-v1",
        "status": "PASS_PURE_EXTERNAL_COMPARATOR_CLOSEOUT" if failed == 0 else "FAIL_PURE_EXTERNAL_COMPARATOR_CLOSEOUT",
        "overall_pass": failed == 0,
        "checks_total": len(checks),
        "checks_passed": passed,
        "checks_failed": failed,
        "pre_registration_commit": "0a08eb90c3ee787578f5fac1d5f01a2b2fe72a5d",
        "protocol_sha256": sha256(config_path),
        "production_report_sha256": sha256(production_path),
        "independent_report_sha256": sha256(independent_path),
        "preparation_report_sha256": sha256(preparation_path),
        "scientific_conclusion": {
            "pure_external_feature_arm_closed": True,
            "pure_external_rcs_replacement_supported": False,
            "pure_external_rcs_is_significantly_worse_than_intrinsic_on_reused_development": True,
            "full_and_intrinsic_plus_rcs_outperform_pure_rcs": True,
            "these_pure_rcs_contrasts_establish_full_over_intrinsic": False,
            "old_full_over_intrinsic_mechanism_increment_established": False,
            "interpretation": "The pure external-RCS feature arm does not replace the intrinsic baseline. Contrasts against this weak pure arm do not rescue the prior non-significant full-versus-intrinsic mechanism comparison. Development-only no-go and test/generator prohibitions remain unchanged."
        },
        "verified_primary_models": production["primary_models"],
        "verified_primary_comparisons": production["primary_comparisons"],
        "old_full_mechanism_minus_intrinsic": old_contrast,
        "large_artifacts": {artifact.name: {"path": str(artifact), "sha256": sha256(artifact), "bytes": artifact.stat().st_size}},
        "test_untouched": True,
        "functional_untouched_evaluated": False,
        "mechanism_increment_pass": False,
        "rk_g1_pass": False,
        "generator_training_authorized": False,
        "complete_sota": False,
        "checks": checks,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "pure_external_replacement_supported": False, "rk_g1_pass": False}, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
