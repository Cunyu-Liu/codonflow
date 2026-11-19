#!/usr/bin/env python3
"""Build a label-blind length/GC sequence-OOD contract from the frozen RK04 split.

The original protein-cluster split is preserved.  Thresholds are row-weighted
quantiles of the original training partition only.  A complete operational
protein cluster is moved to sequence_ood when any member is outside either
training range.  Expression labels are never accessed.  MAGE functional
untouched rows are copied without feature calculation or evaluation.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SOURCE_ID = "boel_2016_nesg6348"
UNTOUCHED = "functional_untouched"
OOD = "sequence_ood"
CORE = ("train", "dev", "test")
PROTOCOL_ID = "a8_rk04_sequence_ood_v1_train_q005_q095_cluster"
NEW_FIELDS = [
    "ood_protocol_id", "ood_assignment", "ood_reasons",
    "length_nt_no_stop", "gc_fraction_no_stop",
]
NORMALIZATION_FEATURES = [
    "log_length_nt", "gc_fraction", "cai", "full_cds_mfe_kcal_mol",
    "full_cds_mfe_per_nt", "mfe_5prime_48_kcal_mol", "source_Gave48",
    "source_Gave96", "source_Gave144", "source_Gz48v",
]
REQUIRED_COMPLETE_FEATURES = {
    "gc_fraction", "cai", "full_cds_mfe_kcal_mol", "full_cds_mfe_per_nt",
    "mfe_5prime_48_kcal_mol",
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, path)


def artifact(path: Path) -> dict:
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def finite(value: str, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite {name}")
    return result


def read_features(path: Path) -> list[dict]:
    numeric = [
        "gc_fraction", "cai", "full_cds_mfe_kcal_mol", "full_cds_mfe_per_nt",
        "mfe_5prime_48_kcal_mol", "source_Gave48", "source_Gave96",
        "source_Gave144", "source_Gz48v",
    ]
    rows = []
    identities = set()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            if raw["source_id"] != SOURCE_ID:
                raise ValueError("unexpected source in frozen feature table")
            split = raw["split_assignment"]
            if split == UNTOUCHED:
                raise ValueError("functional untouched appears in feature table")
            if split not in CORE:
                raise ValueError(f"unexpected original split: {split}")
            identity = (raw["source_row"], raw["construct_id"])
            if identity in identities:
                raise ValueError(f"duplicate feature identity: {identity}")
            identities.add(identity)
            row = dict(raw)
            row["length_nt"] = int(raw["length_nt"])
            for key in numeric:
                if raw[key] == "":
                    if key in REQUIRED_COMPLETE_FEATURES:
                        raise ValueError(f"required feature {key} is missing")
                    row[key] = None
                else:
                    row[key] = finite(raw[key], key)
            row["log_length_nt"] = math.log(row["length_nt"])
            rows.append(row)
    if len(rows) != 6348:
        raise ValueError(f"expected 6348 Boel feature rows, found {len(rows)}")
    return rows


def quantile_thresholds(rows: list[dict], lower_q: float, upper_q: float) -> dict:
    train = [row for row in rows if row["split_assignment"] == "train"]
    if not train:
        raise ValueError("original train is empty")
    result = {}
    for variable in ("length_nt", "gc_fraction"):
        values = np.asarray([row[variable] for row in train], dtype=np.float64)
        lower, upper = np.quantile(values, [lower_q, upper_q])
        result[variable] = {
            "lower": float(lower), "upper": float(upper),
            "train_min": float(values.min()), "train_max": float(values.max()),
            "train_rows": len(train),
        }
    return result


def cluster_extremes(rows: list[dict], thresholds: dict) -> dict:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["operational_protein_cluster"]].append(row)
    result = {}
    for cluster, members in grouped.items():
        reasons = set()
        for variable, short in (("length_nt", "length"), ("gc_fraction", "gc")):
            values = [row[variable] for row in members]
            if min(values) < thresholds[variable]["lower"]:
                reasons.add(short + "_low")
            if max(values) > thresholds[variable]["upper"]:
                reasons.add(short + "_high")
        result[cluster] = sorted(reasons)
    return result


def fit_normalization(rows: list[dict]) -> dict:
    train = [row for row in rows if row["ood_assignment"] == "train"]
    if not train:
        raise ValueError("retained train is empty")
    output = {}
    for feature in NORMALIZATION_FEATURES:
        observed = [row[feature] for row in train if row[feature] is not None]
        values = np.asarray(observed, dtype=np.float64)
        if len(values) < 2:
            raise ValueError(f"insufficient observed train values for {feature}")
        mean = float(values.mean())
        scale = float(values.std(ddof=0))
        if not math.isfinite(mean) or not math.isfinite(scale) or scale <= 1e-12:
            raise ValueError(f"invalid train-only normalization for {feature}")
        output[feature] = {
            "mean": mean, "scale_ddof0": scale, "n_observed": len(values),
            "n_missing": len(train) - len(values), "imputation": "train_observed_mean",
            "missing_indicator": True,
            "min": float(values.min()), "max": float(values.max()),
        }
    return output


def read_original(path: Path) -> tuple[list[str], list[dict]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    if not fields or len(rows) != 25420:
        raise ValueError("frozen RK04 input schema or row count is invalid")
    return fields, rows


def build(args: argparse.Namespace) -> dict:
    if not (0 < args.lower_quantile < args.upper_quantile < 1):
        raise ValueError("quantiles must satisfy 0 < lower < upper < 1")
    for key, expected in (("input", args.input_sha256), ("features", args.features_sha256)):
        path = getattr(args, key)
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"SHA256 mismatch for {key}: {actual}")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    args.audit_dir.mkdir(parents=True, exist_ok=True)
    original_fields, original_rows = read_original(args.input)
    features = read_features(args.features)
    by_identity = {(row["source_row"], row["construct_id"]): row for row in features}
    thresholds = quantile_thresholds(features, args.lower_quantile, args.upper_quantile)
    extreme_by_cluster = cluster_extremes(features, thresholds)
    for row in features:
        reasons = extreme_by_cluster[row["operational_protein_cluster"]]
        row["ood_assignment"] = OOD if reasons else row["split_assignment"]
        row["ood_reasons"] = reasons
    normalization = fit_normalization(features)

    output_rows = []
    matched = set()
    for original in original_rows:
        row = dict(original)
        if original["source_id"] == SOURCE_ID:
            identity = (original["source_row"], original["construct_id"])
            feature = by_identity.get(identity)
            if feature is None:
                raise ValueError(f"missing Boel feature identity: {identity}")
            if feature["operational_protein_cluster"] != original["operational_protein_cluster"]:
                raise ValueError(f"cluster mismatch: {identity}")
            if hashlib.sha256(original["cds"].encode()).hexdigest() != feature["cds_sha256"]:
                raise ValueError(f"CDS SHA mismatch: {identity}")
            row.update({
                "ood_protocol_id": PROTOCOL_ID,
                "ood_assignment": feature["ood_assignment"],
                "ood_reasons": "|".join(feature["ood_reasons"]),
                "length_nt_no_stop": str(feature["length_nt"]),
                "gc_fraction_no_stop": format(feature["gc_fraction"], ".17g"),
            })
            matched.add(identity)
        else:
            if original["split_assignment"] != UNTOUCHED:
                raise ValueError("non-Boel row escaped functional untouched")
            row.update({
                "ood_protocol_id": PROTOCOL_ID, "ood_assignment": UNTOUCHED,
                "ood_reasons": "", "length_nt_no_stop": "", "gc_fraction_no_stop": "",
            })
        output_rows.append(row)
    if matched != set(by_identity):
        raise ValueError("not every feature row was matched to the original split")

    output_csv = args.output_dir / "functional_long_sequence_ood.csv"
    temporary = output_csv.with_name(output_csv.name + f".part.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=original_fields + NEW_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)
    os.replace(temporary, output_csv)

    normalization_payload = {
        "schema_version": "a8-rk04-train-only-normalization-v1",
        "fit_partition": "retained train after cluster-complete sequence-OOD removal; observed values only per feature",
        "features": normalization,
        "transform": "missing values are mean-imputed using the retained-train observed mean; z=(x_imputed-mean)/scale_ddof0; add one missing indicator per feature; log_length_nt uses natural logarithm",
        "missing_value_contract": "no zero filling; required sequence/proxy features must be complete, optional source features may be missing and are explicitly counted",
        "label_access": False,
        "dev_test_sequence_ood_functional_untouched_used_for_fit": False,
    }
    normalization_path = args.output_dir / "train_only_normalization.json"
    atomic_json(normalization_path, normalization_payload)

    boel = [row for row in output_rows if row["source_id"] == SOURCE_ID]
    assignment_counts = Counter(row["ood_assignment"] for row in boel)
    cluster_counts = defaultdict(set)
    for row in boel:
        cluster_counts[row["ood_assignment"]].add(row["operational_protein_cluster"])
    reason_counts = Counter()
    for reasons in extreme_by_cluster.values():
        reason_counts.update(reasons)
    moved_by_original = Counter(
        row["split_assignment"] for row in boel if row["ood_assignment"] == OOD
    )
    core = [row for row in boel if row["ood_assignment"] in CORE]
    for row in core:
        for variable, output_key in (("length_nt", "length_nt_no_stop"), ("gc_fraction", "gc_fraction_no_stop")):
            value = float(row[output_key])
            if not (thresholds[variable]["lower"] <= value <= thresholds[variable]["upper"]):
                raise ValueError("extreme sequence remained in a core partition")
    cluster_assignments = defaultdict(set)
    for row in boel:
        cluster_assignments[row["operational_protein_cluster"]].add(row["ood_assignment"])
    if any(len(assignments) != 1 for assignments in cluster_assignments.values()):
        raise ValueError("an operational cluster spans multiple OOD assignments")

    summary = {
        "schema_version": "a8-rk04-sequence-ood-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "protocol_id": PROTOCOL_ID,
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "production_code_sha256": sha256_file(Path(__file__).resolve()),
        "inputs": {"original_split": artifact(args.input), "proxy_features": artifact(args.features)},
        "label_access": False,
        "threshold_protocol": {
            "fit_partition": "original train only",
            "variables": ["length_nt", "gc_fraction"],
            "length_definition": "feature-table CDS coding length excluding terminal stop",
            "gc_definition": "feature-table GC fraction excluding terminal stop",
            "quantiles": [args.lower_quantile, args.upper_quantile],
            "quantile_method": "numpy.quantile linear interpolation on row-weighted original-train values",
            "cluster_rule": "move the entire operational cluster if any member is below lower or above upper for either variable",
            "core_interval": "closed [lower, upper]",
        },
        "thresholds": thresholds,
        "counts": {
            "boel_rows_by_ood_assignment": dict(sorted(assignment_counts.items())),
            "boel_clusters_by_ood_assignment": {key: len(value) for key, value in sorted(cluster_counts.items())},
            "sequence_ood_rows_from_original_split": dict(sorted(moved_by_original.items())),
            "sequence_ood_cluster_reason_counts": dict(sorted(reason_counts.items())),
            "functional_untouched_rows_copied_without_feature_calculation": sum(
                row["ood_assignment"] == UNTOUCHED for row in output_rows
            ),
        },
        "artifacts": {"sequence_ood_csv": artifact(output_csv), "train_only_normalization": artifact(normalization_path)},
        "predictor_development_ready": True,
        "generator_training_authorized": False,
        "sequence_ood_evaluated": False,
        "functional_untouched_evaluated": False,
        "scientific_scope": [
            "This creates a genuine train-range-excluded length/GC OOD partition, not merely post-hoc strata.",
            "Boel remains cross-protein nonsynonymous expression data, not a fixed-protein synonymous library.",
            "Sequence OOD is frozen for one-shot evaluation after model selection; it is not functional untouched MAGE evidence.",
            "No generator training, SOTA, wet-lab, UTR-CDS, velocity or decay claim is authorized.",
        ],
    }
    atomic_json(args.audit_dir / "sequence_ood_summary.json", summary)
    print(json.dumps({
        "status": summary["status"], "thresholds": thresholds,
        "counts": summary["counts"], "sequence_ood_csv_sha256": summary["artifacts"]["sequence_ood_csv"]["sha256"],
        "normalization_sha256": summary["artifacts"]["train_only_normalization"]["sha256"],
    }, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--features-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--lower-quantile", type=float, default=0.05)
    parser.add_argument("--upper-quantile", type=float, default=0.95)
    args = parser.parse_args()
    build(args)


if __name__ == "__main__":
    main()
