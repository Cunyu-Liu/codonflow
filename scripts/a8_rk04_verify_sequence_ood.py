#!/usr/bin/env python3
"""Independently recompute the RK04 sequence-OOD and train-only normalization contract."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

SOURCE_ID = "boel_2016_nesg6348"
UNTOUCHED = "functional_untouched"
OOD = "sequence_ood"
CORE = ("train", "dev", "test")
NEW_FIELDS = ["ood_protocol_id", "ood_assignment", "ood_reasons", "length_nt_no_stop", "gc_fraction_no_stop"]
FEATURES = [
    "log_length_nt", "gc_fraction", "cai", "full_cds_mfe_kcal_mol",
    "full_cds_mfe_per_nt", "mfe_5prime_48_kcal_mol", "source_Gave48",
    "source_Gave96", "source_Gave144", "source_Gz48v",
]
REQUIRED_COMPLETE_FEATURES = {
    "gc_fraction", "cai", "full_cds_mfe_kcal_mol", "full_cds_mfe_per_nt",
    "mfe_5prime_48_kcal_mol",
}


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def read_features(path: Path) -> list[dict]:
    numeric = [
        "gc_fraction", "cai", "full_cds_mfe_kcal_mol", "full_cds_mfe_per_nt",
        "mfe_5prime_48_kcal_mol", "source_Gave48", "source_Gave96",
        "source_Gave144", "source_Gz48v",
    ]
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            row = dict(raw)
            row["length_nt"] = int(raw["length_nt"])
            for key in numeric:
                if raw[key] == "":
                    if key in REQUIRED_COMPLETE_FEATURES:
                        raise ValueError(f"required feature {key} is missing")
                    row[key] = None
                    continue
                row[key] = float(raw[key])
                if not math.isfinite(row[key]):
                    raise ValueError(f"non-finite {key}")
            row["log_length_nt"] = math.log(row["length_nt"])
            rows.append(row)
    return rows


def close_nested(left, right, tolerance=0.0) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(close_nested(left[key], right[key], tolerance) for key in left)
    if isinstance(left, (float, int)) and isinstance(right, (float, int)):
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    return left == right


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--production-script", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    checks = []

    def check(name: str, condition: bool, detail=None) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    input_sha = sha256_file(args.input)
    feature_sha = sha256_file(args.features)
    production_sha = sha256_file(args.production_script)
    check("original_split_sha256_matches_summary", input_sha == summary["inputs"]["original_split"]["sha256"])
    check("feature_sha256_matches_summary", feature_sha == summary["inputs"]["proxy_features"]["sha256"])
    check("production_script_sha256_matches_summary", production_sha == summary["production_code_sha256"])
    check("summary_initial_status_pending_independent", summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("label_access_declared_false", summary["label_access"] is False)

    original_fields, original = read_csv(args.input)
    csv_path = Path(summary["artifacts"]["sequence_ood_csv"]["path"])
    norm_path = Path(summary["artifacts"]["train_only_normalization"]["path"])
    output_fields, output = read_csv(csv_path)
    normalization = json.loads(norm_path.read_text())
    features = read_features(args.features)
    check("original_row_count_25420", len(original) == 25420, len(original))
    check("output_row_count_25420", len(output) == 25420, len(output))
    check("feature_row_count_6348", len(features) == 6348, len(features))
    check("output_schema_appends_exact_contract", output_fields == original_fields + NEW_FIELDS)
    check("all_original_columns_and_row_order_unchanged", all(
        all(row[key] == out[key] for key in original_fields)
        for row, out in zip(original, output)
    ))

    train = [row for row in features if row["split_assignment"] == "train"]
    thresholds = {}
    for variable in ("length_nt", "gc_fraction"):
        values = np.asarray([row[variable] for row in train], dtype=np.float64)
        lower, upper = np.quantile(values, [0.05, 0.95])
        thresholds[variable] = {
            "lower": float(lower), "upper": float(upper),
            "train_min": float(values.min()), "train_max": float(values.max()),
            "train_rows": len(train),
        }
    check("thresholds_recomputed_from_original_train_only", close_nested(thresholds, summary["thresholds"]))
    check("threshold_train_rows_5079", all(value["train_rows"] == 5079 for value in thresholds.values()))

    grouped = defaultdict(list)
    for row in features:
        grouped[row["operational_protein_cluster"]].append(row)
    expected_reasons = {}
    for cluster, members in grouped.items():
        reasons = set()
        for variable, short in (("length_nt", "length"), ("gc_fraction", "gc")):
            values = [row[variable] for row in members]
            if min(values) < thresholds[variable]["lower"]:
                reasons.add(short + "_low")
            if max(values) > thresholds[variable]["upper"]:
                reasons.add(short + "_high")
        expected_reasons[cluster] = sorted(reasons)

    expected_by_identity = {}
    for row in features:
        reasons = expected_reasons[row["operational_protein_cluster"]]
        expected_by_identity[(row["source_row"], row["construct_id"])] = {
            "assignment": OOD if reasons else row["split_assignment"],
            "reasons": "|".join(reasons), "length": str(row["length_nt"]),
            "gc": format(row["gc_fraction"], ".17g"),
        }
    boel_output = [row for row in output if row["source_id"] == SOURCE_ID]
    untouched_output = [row for row in output if row["source_id"] != SOURCE_ID]
    check("untouched_row_count_19072", len(untouched_output) == 19072, len(untouched_output))
    check("untouched_copied_without_features_or_ood_reasons", all(
        row["split_assignment"] == UNTOUCHED and row["ood_assignment"] == UNTOUCHED
        and row["ood_reasons"] == "" and row["length_nt_no_stop"] == "" and row["gc_fraction_no_stop"] == ""
        for row in untouched_output
    ))
    check("boel_assignments_recomputed_exactly", all(
        row["ood_assignment"] == expected_by_identity[(row["source_row"], row["construct_id"])]["assignment"]
        for row in boel_output
    ))
    check("boel_reasons_recomputed_exactly", all(
        row["ood_reasons"] == expected_by_identity[(row["source_row"], row["construct_id"])]["reasons"]
        for row in boel_output
    ))
    check("boel_length_gc_values_recomputed_exactly", all(
        row["length_nt_no_stop"] == expected_by_identity[(row["source_row"], row["construct_id"])]["length"]
        and row["gc_fraction_no_stop"] == expected_by_identity[(row["source_row"], row["construct_id"])]["gc"]
        for row in boel_output
    ))

    cluster_assignments = defaultdict(set)
    for row in boel_output:
        cluster_assignments[row["operational_protein_cluster"]].add(row["ood_assignment"])
    check("every_boel_cluster_has_exactly_one_ood_assignment", all(len(value) == 1 for value in cluster_assignments.values()))
    check("sequence_ood_nonempty", any(row["ood_assignment"] == OOD for row in boel_output))
    check("retained_core_has_no_extreme_row", all(
        thresholds[variable]["lower"] <= float(row[key]) <= thresholds[variable]["upper"]
        for row in boel_output if row["ood_assignment"] in CORE
        for variable, key in (("length_nt", "length_nt_no_stop"), ("gc_fraction", "gc_fraction_no_stop"))
    ))
    check("every_sequence_ood_row_has_at_least_one_reason", all(
        row["ood_reasons"] for row in boel_output if row["ood_assignment"] == OOD
    ))
    check("core_rows_have_no_ood_reason", all(
        not row["ood_reasons"] for row in boel_output if row["ood_assignment"] in CORE
    ))

    assignment_counts = Counter(row["ood_assignment"] for row in boel_output)
    cluster_counts = defaultdict(set)
    for row in boel_output:
        cluster_counts[row["ood_assignment"]].add(row["operational_protein_cluster"])
    moved = Counter(row["split_assignment"] for row in boel_output if row["ood_assignment"] == OOD)
    reason_counts = Counter()
    for reasons in expected_reasons.values():
        reason_counts.update(reasons)
    check("assignment_row_counts_match", dict(sorted(assignment_counts.items())) == summary["counts"]["boel_rows_by_ood_assignment"])
    check("assignment_cluster_counts_match", {key: len(value) for key, value in sorted(cluster_counts.items())} == summary["counts"]["boel_clusters_by_ood_assignment"])
    check("moved_original_split_counts_match", dict(sorted(moved.items())) == summary["counts"]["sequence_ood_rows_from_original_split"])
    check("reason_counts_match", dict(sorted(reason_counts.items())) == summary["counts"]["sequence_ood_cluster_reason_counts"])

    retained_train_identities = {
        (row["source_row"], row["construct_id"]) for row in boel_output if row["ood_assignment"] == "train"
    }
    recomputed_norm = {}
    for feature in FEATURES:
        observed = [
            row[feature] for row in features
            if (row["source_row"], row["construct_id"]) in retained_train_identities
            and row[feature] is not None
        ]
        values = np.asarray(observed, dtype=np.float64)
        recomputed_norm[feature] = {
            "mean": float(values.mean()), "scale_ddof0": float(values.std(ddof=0)),
            "n_observed": len(values), "n_missing": len(retained_train_identities) - len(values),
            "imputation": "train_observed_mean", "missing_indicator": True,
            "min": float(values.min()), "max": float(values.max()),
        }
    check("normalization_recomputed_from_retained_train_observed_values", close_nested(recomputed_norm, normalization["features"]))
    check("normalization_observed_plus_missing_equals_retained_train_rows", all(
        value["n_observed"] + value["n_missing"] == assignment_counts["train"]
        for value in normalization["features"].values()
    ))
    check("source_gave144_total_missing_62_recomputed", sum(
        row["source_Gave144"] is None for row in features
    ) == 62)
    check("source_gave144_missing_examples_remain_for_nontrain_imputation", any(
        row["source_Gave144"] is None
        and expected_by_identity[(row["source_row"], row["construct_id"])]["assignment"] != "train"
        for row in features
    ))
    check("normalization_scales_positive_finite", all(
        math.isfinite(value["scale_ddof0"]) and value["scale_ddof0"] > 0
        for value in normalization["features"].values()
    ))
    check("normalization_forbids_nontrain_fit", normalization["dev_test_sequence_ood_functional_untouched_used_for_fit"] is False)
    check("output_csv_sha256_matches_summary", sha256_file(csv_path) == summary["artifacts"]["sequence_ood_csv"]["sha256"])
    check("normalization_sha256_matches_summary", sha256_file(norm_path) == summary["artifacts"]["train_only_normalization"]["sha256"])
    check("sequence_ood_not_yet_evaluated", summary["sequence_ood_evaluated"] is False)
    check("functional_untouched_not_evaluated", summary["functional_untouched_evaluated"] is False)
    check("generator_training_not_authorized", summary["generator_training_authorized"] is False)

    passed = sum(item["pass"] for item in checks)
    report = {
        "schema_version": "a8-rk04-sequence-ood-independent-verification-v1",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks_passed": passed, "checks_total": len(checks), "checks": checks,
        "independent_scope": "recomputed from frozen original split and feature table without importing production code",
        "input_sha256": input_sha, "feature_sha256": feature_sha, "production_script_sha256": production_sha,
        "sequence_ood_csv_sha256": sha256_file(csv_path), "normalization_sha256": sha256_file(norm_path),
        "performance_evaluated": False, "sequence_ood_evaluated": False, "functional_untouched_evaluated": False,
        "scientific_boundaries": summary["scientific_scope"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + f".part.{os.getpid()}")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "failed": [c["name"] for c in checks if not c["pass"]]}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
