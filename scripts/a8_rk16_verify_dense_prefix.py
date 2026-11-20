"""Independently recompute RK16 raw-prefix curves, paired statistics, and bindings."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from codonflow.eval.anytime import FrozenReference, dense_budget_step_auc_v2

TOLERANCE = 1e-12


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode()).hexdigest()


def close(actual: float, expected: float) -> bool:
    return math.isclose(float(actual), float(expected), rel_tol=TOLERANCE, abs_tol=TOLERANCE)


def independent_bootstrap(new_values, comparator_values, resamples: int, seed: int) -> dict:
    effects = np.asarray(new_values, dtype=float) - np.asarray(comparator_values, dtype=float)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, 18, size=(resamples, 18))
    samples = effects[indices].mean(axis=1)
    quantiles = np.quantile(samples, [0.025, 0.975])
    p_left = (1 + np.count_nonzero(samples <= 0.0)) / (resamples + 1)
    p_right = (1 + np.count_nonzero(samples >= 0.0)) / (resamples + 1)
    return {
        "new_mean": float(np.mean(new_values)),
        "comparator_mean": float(np.mean(comparator_values)),
        "mean_effect": float(np.mean(effects)),
        "median_effect": float(np.median(effects)),
        "sd_effect": float(np.std(effects, ddof=1)),
        "ci95": quantiles.tolist(),
        "bootstrap_p_two_sided": float(min(1.0, 2.0 * min(p_left, p_right))),
        "per_record_effects": effects.tolist(),
    }


def independent_holm(p_values: dict[str, float]) -> dict[str, float]:
    result = {}
    previous = 0.0
    ordered = sorted(p_values, key=p_values.get)
    for rank, key in enumerate(ordered):
        previous = max(previous, min(1.0, (len(ordered) - rank) * p_values[key]))
        result[key] = previous
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--matrix-report", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--comparisons-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    checks = []

    def check(name: str, condition: bool, evidence=None) -> None:
        checks.append({"check": name, "pass": bool(condition), "evidence": evidence})

    protocol_path = args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    report = json.loads(args.matrix_report.read_text())
    audit = json.loads(args.audit.read_text())
    check("protocol_schema", protocol["schema"] == "a8-rk16-dense-prefix-v1")
    check("protocol_frozen_before_scoring", protocol["status"] == "FROZEN_BEFORE_DENSE_PREFIX_SCORING")
    check("protocol_hash", report["protocol_sha256"] == sha256(protocol_path) == audit["protocol_sha256"])
    check("report_hash", audit["output_sha256"] == sha256(args.matrix_report))
    check("csv_hash", audit["comparisons_csv_sha256"] == sha256(args.comparisons_csv))
    check("report_complete", report["status"] == "PASS_RK16_DENSE_PREFIX_COMPLETE")
    check("record_count", len(report["records"]) == report.get("record_count", 18) or len(report["records"]) == 18, len(report["records"]))
    check("record_order", report["record_order"] == [record["record_id"] for record in report["records"]])
    check("primary_methods", report["primary_methods"] == protocol["primary_methods"])
    check("primary_budget", report["primary_max_budget"] == 11)

    def repo_path(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else REPO / path

    input_paths = {key: repo_path(protocol["inputs"][key]["path"]) for key in ("matrix", "lineardesign_report", "ensemble_report", "legacy_manifest")}
    for key, path in input_paths.items():
        check(f"input_hash_{key}", sha256(path) == protocol["inputs"][key]["sha256"])
    matrix = json.loads(input_paths["matrix"].read_text())
    ld_report = json.loads(input_paths["lineardesign_report"].read_text())
    ensemble_report = json.loads(input_paths["ensemble_report"].read_text())
    manifest = json.loads(input_paths["legacy_manifest"].read_text())
    check("matrix_source_complete", matrix["status"] == "PASS_RK13_COMPLETE" and len(matrix["records"]) == 18)
    check("ld_source_complete", ld_report["status"] == "COMPLETE_UNIQUE18_OFFICIAL_LINEARDESIGN_LAMBDA_GRID" and len(ld_report["runs"]) == 198)
    check("ensemble_source_complete", ensemble_report["status"] == "PASS_ENSEMBLEDESIGN_UNIQUE18_RECOVERY" and len(ensemble_report["records"]) == 18)
    check("legacy_manifest_count", manifest["file_count"] == 18 and len(manifest["files"]) == 18)
    check("report_matches_frozen_matrix_order", report["record_order"] == [record["record_id"] for record in matrix["records"]])

    code_commit = report["code_commit"]
    try:
        ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", code_commit, "HEAD"], cwd=REPO).returncode == 0
        committed_scorer = subprocess.check_output(["git", "show", f"{code_commit}:scripts/a8_rk16_score_dense_prefix.py"], cwd=REPO)
        current_scorer = (REPO / "scripts/a8_rk16_score_dense_prefix.py").read_bytes()
        scorer_unchanged = committed_scorer == current_scorer
    except Exception:
        ancestor = False
        scorer_unchanged = False
    check("scoring_commit_is_ancestor", ancestor, code_commit)
    check("scoring_code_unchanged", scorer_unchanged)

    recomputed = {method: {"dense_budget_step_auc_v2": [], "endpoint_hypervolume_normalized_b11": []} for method in protocol["primary_methods"]}
    duplicate_positions = 0
    all_curve_checks = True
    all_secondary_checks = True
    all_raw_hash_checks = True
    all_reference_checks = True
    for index, (matrix_record, output_record) in enumerate(zip(matrix["records"], report["records"])):
        record_id = matrix_record["record_id"]
        if output_record["record_id"] != record_id:
            all_curve_checks = False
            continue
        legacy_path = Path(manifest["root"]) / f"{record_id}_s0.json"
        if sha256(legacy_path) != manifest["files"][f"{record_id}_s0.json"]:
            all_raw_hash_checks = False
            continue
        legacy = json.loads(legacy_path.read_text())
        calibration = Path(matrix_record["calibration"])
        if sha256(calibration) != matrix_record["reference_sha256"] or output_record["reference_sha256"] != matrix_record["reference_sha256"]:
            all_reference_checks = False
            continue
        reference = FrozenReference.from_dict(json.loads(calibration.read_text()))

        ld_runs = [run for run in ld_report["runs"] if run["record_id"] == record_id]
        ld_by_lambda = {round(float(run["lambda"]), 1): run for run in ld_runs}
        ensemble_record = next(record for record in ensemble_report["records"] if record["record_id"] == record_id)
        ensemble_by_id = {int(run["run_id"]): run for run in ensemble_record["runs"]}
        raw = {
            "lineardesign_lambda11": [ld_by_lambda[value]["evaluation_sequence_dna"] for value in protocol["lineardesign_lambda_order"]],
            "codongpt": legacy["methods"]["codongpt"]["solutions"],
            "uniform_synonymous": legacy["methods"]["uniform_synonymous"]["solutions"],
            "ensembledesign_11run": [ensemble_by_id[run_id]["evaluation_sequence_dna"] for run_id in protocol["ensemble_run_order"]],
        }
        for method in protocol["primary_methods"]:
            points = matrix_record["methods"][method]["points"]
            by_sequence = {point["sequence"]: point["objectives"] for point in points}
            sequences = raw[method][:11]
            records = [{"budget": budget, "objectives": by_sequence[sequence]} for budget, sequence in enumerate(sequences, start=1)]
            dense = dense_budget_step_auc_v2(records, reference, max_budget=11)
            actual = output_record["primary"][method]
            if not close(actual["dense_budget_step_auc_v2"], dense["auc"]):
                all_curve_checks = False
            if not close(actual["endpoint_hypervolume_normalized"], dense["curve"][-1]["hv"]):
                all_curve_checks = False
            seen = set()
            for budget, (sequence, actual_row, expected_row) in enumerate(zip(sequences, actual["curve"], dense["curve"]), start=1):
                digest = sequence_sha256(sequence)
                novel = digest not in seen
                seen.add(digest)
                if not novel:
                    duplicate_positions += 1
                valid = (
                    actual_row["budget"] == budget
                    and actual_row["n_scored"] == budget
                    and actual_row["sequence_sha256"] == digest
                    and actual_row["novel_sequence"] == novel
                    and actual_row["n_unique_so_far"] == len(seen)
                    and actual_row["objectives"] == by_sequence[sequence]
                    and close(actual_row["hypervolume_normalized"], expected_row["hv"])
                )
                if not valid:
                    all_curve_checks = False
            if actual["n_real_generation_calls"] != 11 or actual["n_unique_terminal"] != len(seen) or actual["padding_used"] or actual["synthetic_origin_used"] or actual["zero_filled_budgets"]:
                all_curve_checks = False
            recomputed[method]["dense_budget_step_auc_v2"].append(dense["auc"])
            recomputed[method]["endpoint_hypervolume_normalized_b11"].append(dense["curve"][-1]["hv"])

        for method in protocol["secondary_methods"]:
            by_sequence = {point["sequence"]: point["objectives"] for point in matrix_record["methods"][method]["points"]}
            sequences = raw[method][:100]
            records = [{"budget": budget, "objectives": by_sequence[sequence]} for budget, sequence in enumerate(sequences, start=1)]
            dense = dense_budget_step_auc_v2(records, reference, max_budget=100)
            actual = output_record["secondary_b100_descriptive"][method]
            valid = close(actual["dense_budget_step_auc_v2"], dense["auc"]) and close(actual["endpoint_hypervolume_normalized"], dense["curve"][-1]["hv"])
            valid = valid and len(actual["curve"]) == 100 and [row["budget"] for row in actual["curve"]] == list(range(1, 101))
            valid = valid and all(close(row["hypervolume_normalized"], expected["hv"]) for row, expected in zip(actual["curve"], dense["curve"]))
            if not valid:
                all_secondary_checks = False

    check("legacy_raw_hashes_all_records", all_raw_hash_checks)
    check("reference_hashes_all_records", all_reference_checks)
    check("primary_curves_independent_recompute", all_curve_checks)
    check("secondary_b100_curves_independent_recompute", all_secondary_checks)
    check("duplicates_retained_at_real_budget_positions", duplicate_positions > 0, duplicate_positions)
    check("primary_curve_row_count", sum(len(record["primary"][method]["curve"]) for record in report["records"] for method in protocol["primary_methods"]) == 792)
    check("secondary_curve_row_count", sum(len(record["secondary_b100_descriptive"][method]["curve"]) for record in report["records"] for method in protocol["secondary_methods"]) == 3600)

    for method in protocol["primary_methods"]:
        for metric in protocol["primary_metrics"]:
            values = recomputed[method][metric]
            summary = report["method_summary"][method]
            if metric == "dense_budget_step_auc_v2":
                check(f"summary_{method}_{metric}_mean", close(summary["mean_dense_budget_step_auc_v2"], statistics.mean(values)))
                check(f"summary_{method}_{metric}_median", close(summary["median_dense_budget_step_auc_v2"], statistics.median(values)))
            else:
                check(f"summary_{method}_{metric}_mean", close(summary["mean_endpoint_hypervolume_normalized_b11"], statistics.mean(values)))
                check(f"summary_{method}_{metric}_median", close(summary["median_endpoint_hypervolume_normalized_b11"], statistics.median(values)))

    expected_comparisons = {}
    raw_p = {}
    for comparator_index, comparator in enumerate(protocol["comparators"]):
        for metric_index, metric in enumerate(protocol["primary_metrics"]):
            key = f"{protocol['reference_method']}_minus_{comparator}:{metric}"
            seed = protocol["bootstrap_seed_base"] + 100 * comparator_index + metric_index
            expected = independent_bootstrap(recomputed[protocol["reference_method"]][metric], recomputed[comparator][metric], protocol["bootstrap_resamples"], seed)
            expected_comparisons[key] = expected
            raw_p[key] = expected["bootstrap_p_two_sided"]
    adjusted = independent_holm(raw_p)
    check("holm_family_size", len(expected_comparisons) == 6)
    for key, expected in expected_comparisons.items():
        actual = report["primary_comparisons"][key]
        numeric_fields = ("new_mean", "comparator_mean", "mean_effect", "median_effect", "sd_effect", "bootstrap_p_two_sided")
        check(f"comparison_{key}_numeric", all(close(actual[field], expected[field]) for field in numeric_fields))
        check(f"comparison_{key}_ci", all(close(a, b) for a, b in zip(actual["ci95"], expected["ci95"])))
        check(f"comparison_{key}_record_effects", all(close(a, b) for a, b in zip(actual["per_record_effects"], expected["per_record_effects"])))
        check(f"comparison_{key}_holm", close(actual["holm_p"], adjusted[key]))
        expected_pass = expected["mean_effect"] > 0.0 and expected["ci95"][0] > 0.0 and adjusted[key] < protocol["holm_alpha"]
        check(f"comparison_{key}_pass", actual["pass"] == expected_pass)

    with args.comparisons_csv.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    check("comparison_csv_row_count", len(rows) == 6)
    csv_ok = len(rows) == 6
    for row in rows:
        key = f"{row['comparison']}:{row['metric']}"
        expected = expected_comparisons.get(key)
        if expected is None:
            csv_ok = False
            continue
        for csv_field, json_field in (("new_mean", "new_mean"), ("comparator_mean", "comparator_mean"), ("mean_effect", "mean_effect"), ("bootstrap_p", "bootstrap_p_two_sided")):
            if not close(float(row[csv_field]), expected[json_field]):
                csv_ok = False
        if not close(float(row["ci95_low"]), expected["ci95"][0]) or not close(float(row["ci95_high"]), expected["ci95"][1]) or not close(float(row["holm_p"]), adjusted[key]):
            csv_ok = False
        if (row["pass"] == "True") != report["primary_comparisons"][key]["pass"]:
            csv_ok = False
    check("comparison_csv_numeric_binding", csv_ok)

    for comparator in protocol["comparators"]:
        keys = [f"{protocol['reference_method']}_minus_{comparator}:{metric}" for metric in protocol["primary_metrics"]]
        expected = all(report["primary_comparisons"][key]["pass"] for key in keys)
        check(f"per_comparator_gate_{comparator}", report["per_comparator_two_metric_pass"][comparator] == expected)
    check("overall_dense_gate", report["dense_prefix_superiority_pass"] == all(item["pass"] for item in report["primary_comparisons"].values()))
    check("exclusions_frozen", report["exclusions"] == protocol["exclusions"] and set(report["exclusions"]) == {"gemorna", "lineardesign_scan", "cai_greedy"})
    check("audit_generation_call_counts", audit["primary_real_generation_call_count"] == 792 and audit["secondary_real_generation_call_count"] == 3600)
    check("no_time_matched_claim", not report["time_matched_comparison"] and not audit["time_matched_comparison"])
    check("no_scientific_gate_claim", not report["scientific_gate_passed"] and not audit["scientific_gate_passed"])
    check("no_codonflow_evaluation_claim", not report["codonflow_rk_evaluated"])
    check("no_functional_ood_or_untouched_claim", not report["functional_ood_evaluated"] and not report["functional_untouched_evaluated"])
    check("global_gates_remain_closed", not report["rk_g1_pass"] and not report["expensive_generation_authorized"] and not report["external_sota_authorized"] and not report["sota_claimed"])

    passed = sum(item["pass"] for item in checks)
    payload = {
        "schema": "a8-rk16-independent-verification-v1",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "protocol_sha256": sha256(protocol_path),
        "matrix_report_sha256": sha256(args.matrix_report),
        "audit_sha256": sha256(args.audit),
        "comparisons_csv_sha256": sha256(args.comparisons_csv),
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "time_matched_comparison": False,
        "scientific_gate_passed": False,
        "rk_g1_pass": False,
        "external_sota_authorized": False,
        "sota_claimed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"RK16 independent verification: {passed}/{len(checks)}")
    if passed != len(checks):
        for item in checks:
            if not item["pass"]:
                print(json.dumps(item))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
