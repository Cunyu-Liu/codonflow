#!/usr/bin/env python3
"""Descriptively compare RK24 author multiclass predictions with frozen RK23 HistGB+UH."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def read_predictions(path, split, columns):
    output = {}
    with gzip.open(path, "rt", newline="") as f:
        for row in csv.DictReader(f):
            if row["split_assignment"] != split:
                continue
            key = (int(row["source_row"]), row["construct_id"])
            assert key not in output
            output[key] = {
                "cluster": row["operational_protein_cluster"], "label": float(row["label"]),
                **{name: float(row[name]) for name in columns},
            }
    return output


def metrics(y, p):
    return {"spearman": float(spearmanr(y, p).statistic), "mse": float(np.mean((y - p) ** 2))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--addendum", required=True)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--rk24-result", required=True)
    parser.add_argument("--rk24-predictions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    addendum_path = Path(args.addendum).resolve()
    addendum = json.loads(addendum_path.read_text())
    assert addendum["registered_after_rk24_dev_and_before_rk24_test"]
    assert not addendum["primary_endpoints_or_gate_changed"]
    reference = addendum["rk23"][args.split]
    assert sha(reference["result"]) == reference["result_sha256"]
    assert sha(reference["predictions"]) == reference["predictions_sha256"]
    reference_result = json.loads(Path(reference["result"]).read_text())
    assert reference_result["prediction_file_sha256"] == reference["predictions_sha256"]
    current_result_path = Path(args.rk24_result).resolve()
    current_result = json.loads(current_result_path.read_text())
    assert current_result["prediction_file_sha256"] == sha(args.rk24_predictions)
    assert args.split in current_result["evaluation_splits"]

    old = read_predictions(reference["predictions"], args.split, [addendum["rk23_prediction_column"], addendum["rk23_logistic_crosscheck_column"]])
    new = read_predictions(args.rk24_predictions, args.split, [addendum["rk24_author_column"], addendum["rk24_base_column"]])
    assert set(old) == set(new) and len(old) == current_result["split_results"][args.split]["n"]
    keys = sorted(old)
    for key in keys:
        assert old[key]["label"] == new[key]["label"] and old[key]["cluster"] == new[key]["cluster"]
    y = np.array([new[k]["label"] for k in keys])
    histgb = np.array([old[k][addendum["rk23_prediction_column"]] for k in keys])
    old_logistic = np.array([old[k][addendum["rk23_logistic_crosscheck_column"]] for k in keys])
    base = np.array([new[k][addendum["rk24_base_column"]] for k in keys])
    author = np.array([new[k][addendum["rk24_author_column"]] for k in keys])
    base_crosscheck = float(np.max(np.abs(base - old_logistic)))
    assert base_crosscheck <= addendum["base_logistic_crosscheck_max_abs_tolerance"]
    result = {
        "status": "PASS_DESCRIPTIVE_HISTGB_COMPARATOR",
        "addendum_id": addendum["addendum_id"],
        "addendum_sha256": sha(addendum_path),
        "split": args.split,
        "n": len(keys),
        "rk24_result": str(current_result_path),
        "rk24_result_sha256": sha(current_result_path),
        "rk24_predictions_sha256": sha(args.rk24_predictions),
        "rk23_result_sha256": reference["result_sha256"],
        "rk23_predictions_sha256": reference["predictions_sha256"],
        "base_logistic_crosscheck_max_abs_difference": base_crosscheck,
        "metrics": {
            "rk23_histgb_plus_uh": metrics(y, histgb),
            "rk24_base_plus_uh_logistic": metrics(y, base),
            "rk24_author_multiclass": metrics(y, author),
        },
        "descriptive_effects": {
            "author_minus_histgb_spearman": float(spearmanr(y, author).statistic - spearmanr(y, histgb).statistic),
            "histgb_minus_author_mse": float(np.mean((y - histgb) ** 2) - np.mean((y - author) ** 2)),
        },
        "inference_status": addendum["inference_status"],
        "primary_protocol_changed": False,
        "primary_gate_changed": False,
        "functional_untouched_accessed": False,
        "rk_g1": False,
        "generator_training_authorized": False,
        "prohibited_claims": addendum["prohibited_claims"],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
