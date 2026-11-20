#!/usr/bin/env python3
"""Post-hoc development-only closure of frozen MAGE OOF comparator arms.

No model is fit, no new sequence/label source is opened, and no test prediction or
metric is created. The original DEV_NO_GO_TEST_UNTOUCHED decision is immutable.
"""
from __future__ import annotations

import os
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_name] = "1"
os.environ.setdefault("PYTHONHASHSEED", "0")

import argparse
import hashlib
import json
import math
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy.stats import rankdata

ARMS = ["intrinsic", "local_mfe", "rcs_only", "full_mechanism"]


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def dump(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    y = np.asarray(y, dtype=np.float64)
    pred = np.asarray(pred, dtype=np.float64)
    constant = bool(np.all(pred == pred[0]))
    rho = None if constant else float(np.corrcoef(rankdata(y, method="average"), rankdata(pred, method="average"))[0, 1])
    return {
        "n": int(len(y)),
        "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
        "mae": float(np.mean(np.abs(y - pred))),
        "spearman": rho,
        "spearman_null_reason": "undefined_for_constant_prediction_not_zero" if constant else None,
        "mean_y": float(np.mean(y)),
        "mean_prediction": float(np.mean(pred)),
    }


def effect(y: np.ndarray, candidate: np.ndarray, reference: np.ndarray, names: list[str]) -> dict:
    a = metrics(y, candidate)
    b = metrics(y, reference)
    out = {}
    for name in names:
        metric = name[6:]
        out[name] = float(a[metric] - b[metric])
    return out


def holm(p_values: list[float]) -> list[float]:
    p = np.asarray(p_values, dtype=np.float64)
    order = np.argsort(p)
    adjusted = np.empty(len(p), dtype=np.float64)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        adjusted[index] = min(1.0, running)
    return [float(x) for x in adjusted]


def paired_analysis(y: np.ndarray, candidate: np.ndarray, reference: np.ndarray,
                    names: list[str], bootstrap_seed: int, permutation_seed: int,
                    replicates: int) -> dict:
    y = np.asarray(y, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    observed = effect(y, candidate, reference, names)
    n = len(y)
    boot = np.empty((replicates, len(names)), dtype=np.float64)
    rng = np.random.default_rng(bootstrap_seed)
    for b in range(replicates):
        idx = rng.integers(0, n, n)
        values = effect(y[idx], candidate[idx], reference[idx], names)
        boot[b] = [values[name] for name in names]
    rng = np.random.default_rng(permutation_seed)
    perm = np.empty((replicates, len(names)), dtype=np.float64)
    for b in range(replicates):
        swap = rng.random(n) < 0.5
        c = np.where(swap, reference, candidate)
        r = np.where(swap, candidate, reference)
        values = effect(y, c, r, names)
        perm[b] = [values[name] for name in names]
    obs = np.asarray([observed[name] for name in names], dtype=np.float64)
    p = (1 + np.sum(np.abs(perm) >= np.abs(obs)[None, :], axis=0)) / (replicates + 1.0)
    out = dict(observed)
    for j, name in enumerate(names):
        out[f"{name}_ci95"] = [float(x) for x in np.percentile(boot[:, j], [2.5, 97.5])]
        out[f"permutation_p_{name[6:]}"] = float(p[j])
    out["bootstrap_replicates"] = int(replicates)
    out["permutation_replicates"] = int(replicates)
    return out


def outer_train_mean(y: np.ndarray, folds: np.ndarray) -> np.ndarray:
    y = np.asarray(y, dtype=np.float64)
    folds = np.asarray(folds, dtype=int)
    if set(folds.tolist()) != {0, 1, 2, 3, 4}:
        raise AssertionError("outer folds must be exactly 0..4")
    pred = np.empty(len(y), dtype=np.float64)
    for fold in range(5):
        evaluation = folds == fold
        training = ~evaluation
        if not np.any(evaluation) or not np.any(training):
            raise AssertionError("empty outer train/eval partition")
        pred[evaluation] = float(np.mean(y[training]))
    return pred


def predictions_for(df: pd.DataFrame, seed: str, arm: str) -> np.ndarray:
    return df[f"pred_{seed}_{arm}"].to_numpy(dtype=np.float64)


def load_frame(cfg: dict) -> pd.DataFrame:
    src = cfg["source"]
    for key in ["oof_csv", "nested_report", "nested_protocol", "nested_production_script"]:
        if sha256(src[key]) != src[f"{key}_sha256"]:
            raise AssertionError(f"source hash mismatch: {key}")
    nested = json.loads(Path(src["nested_report"]).read_text())
    if nested.get("status") != "DEV_NO_GO_TEST_UNTOUCHED":
        raise AssertionError("nested development no-go boundary changed")
    df = pd.read_csv(src["oof_csv"])
    expected = {"construct_id", "original_split", "position", "observed_rich"}
    seeds = [cfg["inference"]["primary_outer_seed"], *cfg["inference"]["sensitivity_outer_seeds"]]
    for seed in seeds:
        expected.add(f"outer_fold_{seed}")
        expected.update(f"pred_{seed}_{arm}" for arm in ARMS)
    if set(df.columns) != expected:
        raise AssertionError(f"OOF schema mismatch: {set(df.columns) ^ expected}")
    if len(df) != cfg["development_data"]["expected_n_constructs"] or df["construct_id"].nunique() != len(df):
        raise AssertionError("OOF construct count or uniqueness mismatch")
    if set(df["original_split"]) - set(cfg["development_data"]["allowed_original_splits"]):
        raise AssertionError("out-of-development row reached comparator audit")
    numeric = df.drop(columns=["construct_id", "original_split"])
    if not np.isfinite(numeric.to_numpy(dtype=np.float64)).all():
        raise AssertionError("non-finite OOF value")
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    started = time.perf_counter()
    cfg = json.loads(Path(a.protocol).read_text())
    df = load_frame(cfg)
    y = df["observed_rich"].to_numpy(dtype=np.float64)
    primary = cfg["inference"]["primary_outer_seed"]
    seeds = [primary, *cfg["inference"]["sensitivity_outer_seeds"]]
    reps = int(cfg["inference"]["bootstrap_replicates"])
    if reps != int(cfg["inference"]["permutation_replicates"]):
        raise AssertionError("this frozen implementation requires equal bootstrap/permutation replicates")

    primary_predictions = {arm: predictions_for(df, primary, arm) for arm in ARMS}
    mean_prediction = outer_train_mean(y, df[f"outer_fold_{primary}"].to_numpy(dtype=int))
    model_metrics = {arm: metrics(y, primary_predictions[arm]) for arm in ARMS}
    model_metrics["outer_train_mean"] = metrics(y, mean_prediction)

    comparisons = {}
    p_entries = []
    for spec in cfg["exploratory_comparisons"]:
        cid = spec["comparison_id"]
        names = list(spec["metrics"])
        result = paired_analysis(y, primary_predictions[spec["candidate"]], primary_predictions[spec["reference"]],
                                 names, spec["bootstrap_seed"], spec["permutation_seed"], reps)
        result.update({"candidate": spec["candidate"], "reference": spec["reference"],
                       "interpretation": spec["interpretation"], "analysis_role": "post_hoc_exploratory"})
        comparisons[cid] = result
        for name in names:
            p_entries.append((cid, name, result[f"permutation_p_{name[6:]}"]))
    base = cfg["outer_training_mean_baseline"]
    cid = base["comparison_id"]
    names = list(base["metrics"])
    result = paired_analysis(y, primary_predictions[base["candidate"]], mean_prediction,
                             names, base["bootstrap_seed"], base["permutation_seed"], reps)
    result.update({"candidate": base["candidate"], "reference": base["reference"],
                   "reference_metrics": model_metrics["outer_train_mean"],
                   "analysis_role": "post_hoc_exploratory"})
    comparisons[cid] = result
    for name in names:
        p_entries.append((cid, name, result[f"permutation_p_{name[6:]}"]))
    adjusted = holm([entry[2] for entry in p_entries])
    for (entry_cid, name, _), value in zip(p_entries, adjusted):
        comparisons[entry_cid][f"holm_p_{name[6:]}"] = value

    sensitivity = {}
    for seed in seeds:
        predictions = {arm: predictions_for(df, seed, arm) for arm in ARMS}
        folds = df[f"outer_fold_{seed}"].to_numpy(dtype=int)
        mean_pred = outer_train_mean(y, folds)
        seed_comparisons = {}
        for spec in cfg["exploratory_comparisons"]:
            seed_comparisons[spec["comparison_id"]] = effect(
                y, predictions[spec["candidate"]], predictions[spec["reference"]], list(spec["metrics"]))
        seed_comparisons[base["comparison_id"]] = effect(
            y, predictions[base["candidate"]], mean_pred, list(base["metrics"]))
        sensitivity[seed] = {
            "models": {**{arm: metrics(y, predictions[arm]) for arm in ARMS},
                       "outer_train_mean": metrics(y, mean_pred)},
            "comparisons": seed_comparisons,
            "outer_train_mean_fold_values": [float(np.mean(y[folds != fold])) for fold in range(5)],
        }

    checks = [
        {"name": "development_rows_only", "pass": set(df["original_split"]) <= {"train", "dev"}},
        {"name": "n_131_unique_constructs", "pass": len(df) == 131 and df["construct_id"].nunique() == 131},
        {"name": "no_new_model_fit", "pass": cfg["development_data"]["new_model_fits"] == 0},
        {"name": "five_exploratory_holm_tests", "pass": len(p_entries) == 5},
        {"name": "fold_varying_mean_spearman_descriptive_only", "pass": math.isfinite(model_metrics["outer_train_mean"]["spearman"]) and base["metrics"] == ["delta_rmse"]},
        {"name": "all_technical_values_finite", "pass": all(math.isfinite(float(v)) for c in comparisons.values() for k, v in c.items() if k.startswith(("delta_", "permutation_", "holm_")) and not k.endswith("ci95"))},
    ]
    if not all(c["pass"] for c in checks):
        raise AssertionError(f"technical contract failed: {checks}")
    report = {
        "schema": "a8-rk03-mage-oof-comparator-closure-v2",
        "protocol": str(Path(a.protocol).resolve()),
        "protocol_sha256": sha256(a.protocol),
        "production_script_sha256": sha256(__file__),
        "source": cfg["source"],
        "status": "DEVELOPMENT_ONLY_EXPLORATORY_TEST_UNTOUCHED",
        "scientific_gate": "UNCHANGED_DEV_NO_GO_TEST_UNTOUCHED",
        "scientific_gate_pass": False,
        "test_authorized": False,
        "new_model_fits": 0,
        "primary_outer_seed": primary,
        "primary_models": model_metrics,
        "exploratory_comparisons": comparisons,
        "holm_family": [{"comparison_id": c, "effect": n, "raw_p": p, "holm_p": h}
                        for (c, n, p), h in zip(p_entries, adjusted)],
        "sensitivity": sensitivity,
        "feature_arm_interpretation": cfg["feature_arm_interpretation"],
        "limitations": [
            "Post-hoc exploratory comparison on already-used development predictions; not independent confirmation.",
            "The frozen rcs_only arm includes intrinsic features and is not a pure external-pretrained-model baseline.",
            "No separate constant-speed-field arm, mature-model replacement, test metric, transport analysis, or generator authorization is produced.",
            "Outer-training means vary across folds; their OOF Spearman is descriptive only and is excluded from paired inference, which uses RMSE only.",
        ],
        "cost": {"wall_seconds": None, "resample_replicates_primary": int(3 * 2 * reps),
                 "new_training_compute": 0, "new_scorer_calls": 0},
        "technical_checks": checks,
        "overall_pass": True,
        "overall_pass_scope": "technical_artifact_contract_only_not_scientific_go",
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__},
    }
    report["cost"]["wall_seconds"] = float(time.perf_counter() - started)
    dump(a.output, report)
    print(json.dumps({"status": report["status"], "overall_pass": True, "output": a.output,
                      "wall_seconds": report["cost"]["wall_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
