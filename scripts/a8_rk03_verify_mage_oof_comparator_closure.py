#!/usr/bin/env python3
"""Independent recomputation of the frozen MAGE OOF comparator-closure report."""
from __future__ import annotations

import os
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

ARMS = ["intrinsic", "local_mfe", "rcs_only", "full_mechanism"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metric(y, p):
    y = np.asarray(y, dtype=np.float64)
    p = np.asarray(p, dtype=np.float64)
    if np.ptp(p) == 0:
        rho = None
    else:
        rho = float(np.corrcoef(rankdata(y, method="average"), rankdata(p, method="average"))[0, 1])
    return {
        "n": len(y),
        "rmse": float(np.sqrt(np.mean(np.square(y - p)))),
        "mae": float(np.mean(np.absolute(y - p))),
        "spearman": rho,
        "spearman_null_reason": "undefined_for_constant_prediction_not_zero" if rho is None else None,
        "mean_y": float(np.mean(y)),
        "mean_prediction": float(np.mean(p)),
    }


def contrast(y, c, r, names):
    cm, rm = metric(y, c), metric(y, r)
    return {name: float(cm[name[6:]] - rm[name[6:]]) for name in names}


def mean_oof(y, folds):
    result = np.zeros(len(y), dtype=np.float64)
    for f in (0, 1, 2, 3, 4):
        eval_idx = np.flatnonzero(folds == f)
        train_idx = np.flatnonzero(folds != f)
        result[eval_idx] = np.sum(y[train_idx]) / len(train_idx)
    return result


def resample(y, c, r, names, bs, ps, reps):
    observed = contrast(y, c, r, names)
    n = len(y)
    bvals = np.zeros((reps, len(names)), dtype=np.float64)
    rng = np.random.default_rng(bs)
    for b in range(reps):
        idx = rng.integers(0, n, size=n)
        e = contrast(y[idx], c[idx], r[idx], names)
        bvals[b, :] = [e[name] for name in names]
    pvals = np.zeros((reps, len(names)), dtype=np.float64)
    rng = np.random.default_rng(ps)
    for b in range(reps):
        choose = rng.random(n) < 0.5
        cc = c.copy()
        rr = r.copy()
        cc[choose] = r[choose]
        rr[choose] = c[choose]
        e = contrast(y, cc, rr, names)
        pvals[b, :] = [e[name] for name in names]
    obs = np.array([observed[name] for name in names])
    significance = (1.0 + np.count_nonzero(np.abs(pvals) >= np.abs(obs), axis=0)) / (reps + 1.0)
    result = dict(observed)
    for j, name in enumerate(names):
        result[f"{name}_ci95"] = [float(v) for v in np.percentile(bvals[:, j], (2.5, 97.5))]
        result[f"permutation_p_{name[6:]}"] = float(significance[j])
    result["bootstrap_replicates"] = reps
    result["permutation_replicates"] = reps
    return result


def holm(values):
    values = np.asarray(values, dtype=np.float64)
    order = np.argsort(values)
    out = np.zeros(len(values), dtype=np.float64)
    previous = 0.0
    for rank, idx in enumerate(order):
        previous = max(previous, (len(values) - rank) * values[idx])
        out[idx] = min(1.0, previous)
    return out.tolist()


def differences(expected, actual, path="", tol=1e-12):
    out = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            return [{"path": path, "error": "keys", "expected": sorted(expected) if isinstance(expected, dict) else expected,
                     "actual": sorted(actual) if isinstance(actual, dict) else actual}]
        for key in sorted(expected):
            out.extend(differences(expected[key], actual[key], f"{path}.{key}" if path else key, tol))
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return [{"path": path, "error": "list_length"}]
        for i, (a, b) in enumerate(zip(expected, actual)):
            out.extend(differences(a, b, f"{path}[{i}]", tol))
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        if not isinstance(actual, (float, int)) or not math.isfinite(float(actual)) or abs(float(expected) - float(actual)) > tol:
            out.append({"path": path, "expected": expected, "actual": actual})
    elif expected != actual:
        out.append({"path": path, "expected": expected, "actual": actual})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--production", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    cfg = json.loads(Path(a.protocol).read_text())
    prod = json.loads(Path(a.production).read_text())
    checks = []

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    for key in ["oof_csv", "nested_report", "nested_protocol", "nested_production_script"]:
        check(f"source_hash_{key}", sha256(cfg["source"][key]) == cfg["source"][f"{key}_sha256"])
    check("protocol_hash_bound", prod.get("protocol_sha256") == sha256(a.protocol))
    check("production_script_hash_bound", prod.get("production_script_sha256") == sha256(cfg["source"]["nested_production_script"].replace("a8_rk03_mage_development_nested_cv.py", "a8_rk03_mage_oof_comparator_closure.py")))
    check("production_technical_pass", prod.get("overall_pass") is True and all(c.get("pass") for c in prod.get("technical_checks", [])))
    check("scientific_no_go_unchanged", prod.get("scientific_gate") == "UNCHANGED_DEV_NO_GO_TEST_UNTOUCHED" and prod.get("test_authorized") is False and prod.get("scientific_gate_pass") is False)

    df = pd.read_csv(cfg["source"]["oof_csv"])
    check("development_only", set(df["original_split"].unique()).issubset({"train", "dev"}))
    check("131_unique_constructs", len(df) == 131 and len(set(df["construct_id"])) == 131)
    y = df["observed_rich"].to_numpy(dtype=np.float64)
    primary = cfg["inference"]["primary_outer_seed"]
    seeds = [primary, *cfg["inference"]["sensitivity_outer_seeds"]]
    reps = cfg["inference"]["bootstrap_replicates"]

    expected_models = {}
    pred = {}
    for arm in ARMS:
        pred[arm] = df[f"pred_{primary}_{arm}"].to_numpy(dtype=np.float64)
        expected_models[arm] = metric(y, pred[arm])
    folds = df[f"outer_fold_{primary}"].to_numpy(dtype=int)
    check("primary_folds_exact", set(folds.tolist()) == {0, 1, 2, 3, 4})
    mean_pred = mean_oof(y, folds)
    expected_models["outer_train_mean"] = metric(y, mean_pred)
    model_diff = differences(prod["primary_models"], expected_models, "primary_models")
    check("primary_models_recomputed", not model_diff, model_diff[:10])

    expected_comparisons = {}
    p_entries = []
    for spec in cfg["exploratory_comparisons"]:
        cid = spec["comparison_id"]
        names = spec["metrics"]
        value = resample(y, pred[spec["candidate"]], pred[spec["reference"]], names,
                         spec["bootstrap_seed"], spec["permutation_seed"], reps)
        value.update({"candidate": spec["candidate"], "reference": spec["reference"],
                      "interpretation": spec["interpretation"], "analysis_role": "post_hoc_exploratory"})
        expected_comparisons[cid] = value
        for name in names:
            p_entries.append((cid, name, value[f"permutation_p_{name[6:]}"]))
    base = cfg["outer_training_mean_baseline"]
    value = resample(y, pred[base["candidate"]], mean_pred, base["metrics"],
                     base["bootstrap_seed"], base["permutation_seed"], reps)
    value.update({"candidate": base["candidate"], "reference": base["reference"],
                  "reference_metrics": expected_models["outer_train_mean"], "analysis_role": "post_hoc_exploratory"})
    expected_comparisons[base["comparison_id"]] = value
    for name in base["metrics"]:
        p_entries.append((base["comparison_id"], name, value[f"permutation_p_{name[6:]}"]))
    adjusted = holm([x[2] for x in p_entries])
    for (cid, name, _), h in zip(p_entries, adjusted):
        expected_comparisons[cid][f"holm_p_{name[6:]}"] = h
    comparison_diff = differences(prod["exploratory_comparisons"], expected_comparisons, "exploratory_comparisons")
    check("effects_intervals_permutation_and_holm_recomputed", not comparison_diff, comparison_diff[:20])
    expected_family = [{"comparison_id": c, "effect": n, "raw_p": p, "holm_p": h}
                       for (c, n, p), h in zip(p_entries, adjusted)]
    family_diff = differences(prod["holm_family"], expected_family, "holm_family")
    check("holm_family_recomputed", not family_diff, family_diff[:10])

    expected_sensitivity = {}
    for seed in seeds:
        sp = {arm: df[f"pred_{seed}_{arm}"].to_numpy(dtype=np.float64) for arm in ARMS}
        sf = df[f"outer_fold_{seed}"].to_numpy(dtype=int)
        check(f"folds_exact_{seed}", set(sf.tolist()) == {0, 1, 2, 3, 4})
        sm = mean_oof(y, sf)
        sc = {}
        for spec in cfg["exploratory_comparisons"]:
            sc[spec["comparison_id"]] = contrast(y, sp[spec["candidate"]], sp[spec["reference"]], spec["metrics"])
        sc[base["comparison_id"]] = contrast(y, sp[base["candidate"]], sm, base["metrics"])
        expected_sensitivity[seed] = {
            "models": {**{arm: metric(y, sp[arm]) for arm in ARMS}, "outer_train_mean": metric(y, sm)},
            "comparisons": sc,
            "outer_train_mean_fold_values": [float(np.mean(y[sf != f])) for f in range(5)],
        }
    sensitivity_diff = differences(prod["sensitivity"], expected_sensitivity, "sensitivity")
    check("all_three_seed_metrics_and_effects_recomputed", not sensitivity_diff, sensitivity_diff[:20])

    # Explicitly prove that every evaluation-fold label was excluded from its mean.
    leakage_failures = []
    for seed in seeds:
        sf = df[f"outer_fold_{seed}"].to_numpy(dtype=int)
        sm = mean_oof(y, sf)
        for i in range(len(y)):
            expected = float(np.mean(y[sf != sf[i]]))
            if sm[i] != expected:
                leakage_failures.append({"seed": seed, "row": i})
    check("outer_train_mean_has_no_evaluation_label", not leakage_failures, leakage_failures[:10])
    check("fold_varying_mean_spearman_descriptive_only", math.isfinite(expected_models["outer_train_mean"]["spearman"]) and base["metrics"] == ["delta_rmse"])
    check("five_test_family", len(p_entries) == 5)
    check("no_new_training_or_scorer", prod.get("new_model_fits") == 0 and prod["cost"]["new_training_compute"] == 0 and prod["cost"]["new_scorer_calls"] == 0)
    check("arm_name_limitation_retained", "not a pure external" in prod["feature_arm_interpretation"]["rcs_only"])
    check("no_test_or_generator_claim", prod.get("status") == "DEVELOPMENT_ONLY_EXPLORATORY_TEST_UNTOUCHED")

    report = {
        "schema": "a8-rk03-mage-oof-comparator-closure-independent-v2",
        "protocol_sha256": sha256(a.protocol),
        "production_report": str(Path(a.production).resolve()),
        "production_report_sha256": sha256(a.production),
        "independent_script_sha256": sha256(__file__),
        "overall_pass": all(c["pass"] for c in checks),
        "overall_pass_scope": "independent_technical_recomputation_only_not_scientific_go",
        "scientific_gate": "UNCHANGED_DEV_NO_GO_TEST_UNTOUCHED",
        "check_counts": {"passed": sum(c["pass"] for c in checks), "total": len(checks)},
        "checks": checks,
        "tolerance": 1e-12,
    }
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"overall_pass": report["overall_pass"], "checks": report["check_counts"], "output": a.output}, indent=2))
    if not report["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
