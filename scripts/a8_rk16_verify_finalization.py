"""Finalize RK16 by binding scientific results, acceptance, regression, and closeout."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

TOLERANCE = 1e-12


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a: float, b: float) -> bool:
    return math.isclose(float(a), float(b), rel_tol=TOLERANCE, abs_tol=TOLERANCE)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    repo = args.repo_root.resolve()
    audit_dir = repo / "audits/20261120/RK16"
    paths = {
        "protocol": repo / "configs/a8_rk16_dense_prefix_protocol_v1.json",
        "matrix": args.artifact_root / "rk16_dense_prefix_matrix_v1.json",
        "audit": audit_dir / "rk16_dense_prefix_audit_v1.json",
        "csv": audit_dir / "rk16_primary_comparisons_v1.csv",
        "independent": audit_dir / "rk16_independent_verification_v1.json",
        "regression": audit_dir / "rk16_full_regression_v1.console.log",
        "engineering": audit_dir / "rk16_engineering_failures_v1.json",
        "closeout": repo / "docs/handover/A8_RK16_DENSE_PREFIX_CLOSEOUT.md",
    }
    checks = []

    def check(name: str, condition: bool, evidence=None) -> None:
        checks.append({"check": name, "pass": bool(condition), "evidence": evidence})

    for name, path in paths.items():
        check(f"exists_{name}", path.is_file())
    data = {name: json.loads(path.read_text()) for name, path in paths.items() if name in ("protocol", "matrix", "audit", "independent", "engineering")}
    protocol = data["protocol"]
    matrix = data["matrix"]
    audit = data["audit"]
    independent = data["independent"]
    engineering = data["engineering"]
    closeout = paths["closeout"].read_text()

    check("protocol_schema", protocol["schema"] == "a8-rk16-dense-prefix-v1")
    check("protocol_frozen", protocol["status"] == "FROZEN_BEFORE_DENSE_PREFIX_SCORING")
    check("protocol_hash_binding", matrix["protocol_sha256"] == audit["protocol_sha256"] == independent["protocol_sha256"] == sha256(paths["protocol"]))
    check("matrix_hash_binding", audit["output_sha256"] == independent["matrix_report_sha256"] == sha256(paths["matrix"]))
    check("audit_hash_binding", independent["audit_sha256"] == sha256(paths["audit"]))
    check("csv_hash_binding", audit["comparisons_csv_sha256"] == independent["comparisons_csv_sha256"] == sha256(paths["csv"]))
    check("matrix_complete", matrix["status"] == "PASS_RK16_DENSE_PREFIX_COMPLETE")
    check("independent_pass", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] == 88, f"{independent['checks_passed']}/{independent['checks_total']}")
    check("record_count", len(matrix["records"]) == audit["record_count"] == 18)
    check("record_order", matrix["record_order"] == [record["record_id"] for record in matrix["records"]])
    check("method_count", len(matrix["primary_methods"]) == audit["primary_method_count"] == 4)
    check("primary_call_count", audit["primary_real_generation_call_count"] == 18 * 4 * 11 == 792)
    check("secondary_call_count", audit["secondary_real_generation_call_count"] == 18 * 2 * 100 == 3600)
    check("summary_binding", matrix["method_summary"] == audit["method_summary"])
    check("secondary_summary_binding", matrix["secondary_b100_descriptive_summary"] == audit["secondary_b100_descriptive_summary"])

    curve_ok = True
    for record in matrix["records"]:
        for method in matrix["primary_methods"]:
            trajectory = record["primary"][method]
            curve_ok = curve_ok and trajectory["n_real_generation_calls"] == 11 and len(trajectory["curve"]) == 11
            curve_ok = curve_ok and math.isfinite(trajectory["dense_budget_step_auc_v2"])
            curve_ok = curve_ok and not trajectory["padding_used"] and not trajectory["synthetic_origin_used"] and not trajectory["zero_filled_budgets"]
            curve_ok = curve_ok and [row["budget"] for row in trajectory["curve"]] == list(range(1, 12))
        for method in ("codongpt", "uniform_synonymous"):
            trajectory = record["secondary_b100_descriptive"][method]
            curve_ok = curve_ok and trajectory["n_real_generation_calls"] == 100 and len(trajectory["curve"]) == 100
            curve_ok = curve_ok and math.isfinite(trajectory["dense_budget_step_auc_v2"])
    check("all_dense_curves_real_and_complete", curve_ok)
    check("exclusions_bound", matrix["exclusions"] == protocol["exclusions"] and set(matrix["exclusions"]) == {"gemorna", "lineardesign_scan", "cai_greedy"})

    comparisons = matrix["primary_comparisons"]
    check("six_primary_comparisons", len(comparisons) == 6)
    check("comparison_audit_binding", comparisons == audit["primary_comparisons"])
    check("all_six_pass", all(item["pass"] for item in comparisons.values()))
    check("all_effects_positive", all(item["mean_effect"] > 0.0 for item in comparisons.values()))
    check("all_cis_above_zero", all(item["ci95"][0] > 0.0 for item in comparisons.values()))
    check("all_holm_significant", all(item["holm_p"] < protocol["holm_alpha"] for item in comparisons.values()))
    check("dense_gate_true", matrix["dense_prefix_superiority_pass"] and audit["dense_prefix_superiority_pass"])
    check("per_comparator_gate_true", all(matrix["per_comparator_two_metric_pass"].values()) and matrix["per_comparator_two_metric_pass"] == audit["per_comparator_two_metric_pass"])

    with paths["csv"].open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    csv_ok = len(rows) == 6
    for row in rows:
        key = f"{row['comparison']}:{row['metric']}"
        item = comparisons.get(key)
        if item is None:
            csv_ok = False
            continue
        for csv_key, json_key in (("new_mean", "new_mean"), ("comparator_mean", "comparator_mean"), ("mean_effect", "mean_effect"), ("bootstrap_p", "bootstrap_p_two_sided"), ("holm_p", "holm_p")):
            csv_ok = csv_ok and close(row[csv_key], item[json_key])
        csv_ok = csv_ok and close(row["ci95_low"], item["ci95"][0]) and close(row["ci95_high"], item["ci95"][1])
        csv_ok = csv_ok and ((row["pass"] == "True") == item["pass"])
    check("csv_numeric_binding", csv_ok)

    regression = paths["regression"].read_text()
    match = re.search(r"(\d+) passed, (\d+) skipped, (\d+) warnings, (\d+) subtests passed in ([0-9.]+)s", regression)
    check("full_regression_summary", match is not None)
    if match:
        check("full_regression_counts", tuple(map(int, match.groups()[:4])) == (347, 1, 11, 5), match.group(0))
        check("closeout_regression_binding", match.group(0) in closeout)
    else:
        check("full_regression_counts", False)
        check("closeout_regression_binding", False)
    check("engineering_failures_preserved", len(engineering["failures"]) == 5)
    check("engineering_science_unchanged", not engineering["scientific_protocol_changed"] and not engineering["input_data_changed"] and not engineering["primary_statistical_method_changed"] and not engineering["result_report_overwritten"])

    required_closeout_tokens = (
        "PASS_RK16_DENSE_PREFIX_TIME_MATCHED_OPEN",
        "dense_prefix_superiority_pass=true",
        "6/6 primary tests passed",
        "88/88 PASS",
        "time_matched_comparison=false",
        "scientific_gate_passed=false",
        "codonflow_rk_evaluated=false",
        "functional_untouched_evaluated=false",
        "rk_g1_pass=false",
        "external_sota_authorized=false",
        "sota_claimed=false",
    )
    for token in required_closeout_tokens:
        check(f"closeout_contains_{token}", token in closeout)

    false_flags = (
        "time_matched_comparison",
        "scientific_gate_passed",
        "codonflow_rk_evaluated",
        "functional_ood_evaluated",
        "functional_untouched_evaluated",
        "rk_g1_pass",
        "expensive_generation_authorized",
        "external_sota_authorized",
        "sota_claimed",
    )
    check("matrix_false_flags", all(not matrix[flag] for flag in false_flags))
    check("audit_false_flags", all(not audit[flag] for flag in false_flags if flag in audit))
    check("independent_false_flags", all(not independent[flag] for flag in ("time_matched_comparison", "scientific_gate_passed", "rk_g1_pass", "external_sota_authorized", "sota_claimed")))

    passed = sum(item["pass"] for item in checks)
    payload = {
        "schema": "a8-rk16-finalization-v1",
        "status": "PASS_RK16_DENSE_PREFIX_TIME_MATCHED_OPEN" if passed == len(checks) else "FAIL",
        "protocol_sha256": sha256(paths["protocol"]),
        "matrix_sha256": sha256(paths["matrix"]),
        "audit_sha256": sha256(paths["audit"]),
        "independent_sha256": sha256(paths["independent"]),
        "csv_sha256": sha256(paths["csv"]),
        "full_regression_sha256": sha256(paths["regression"]),
        "engineering_failures_sha256": sha256(paths["engineering"]),
        "closeout_sha256": sha256(paths["closeout"]),
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "dense_prefix_superiority_pass": matrix["dense_prefix_superiority_pass"],
        "rk16_dense_task_completion_authorized": passed == len(checks),
        "rk16_time_matched_completion_authorized": False,
        "time_matched_comparison": False,
        "scientific_gate_passed": False,
        "codonflow_rk_evaluated": False,
        "functional_ood_evaluated": False,
        "functional_untouched_evaluated": False,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "external_sota_authorized": False,
        "sota_claimed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"RK16 finalization: {passed}/{len(checks)}")
    if passed != len(checks):
        for item in checks:
            if not item["pass"]:
                print(json.dumps(item))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
