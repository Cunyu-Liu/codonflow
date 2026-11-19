#!/usr/bin/env python3
"""Development-only nested-CV diagnostic for the frozen MAGE synonymous mechanism gate.

This script never constructs a test feature matrix and never emits test predictions or
metrics. The original v1 DEV_NO_GO result remains immutable.
"""
from __future__ import annotations

import os
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_name] = "1"
os.environ.setdefault("PYTHONHASHSEED", "0")

import argparse
import csv
import hashlib
import json
import math
import platform
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy.stats import spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

BASE = ["intrinsic", "local_mfe", "rcs_only", "full_mechanism"]
REFERENCES = ["intrinsic", "local_mfe"]
CATS = ["position", "wt_codon", "mutant_codon", "amino_acid"]
INTRINSIC_NUM = ["position_scaled", "wt_gc_fraction", "mutant_gc_fraction", "delta_gc_fraction", "wt_gc3", "mutant_gc3", "nt_changes", "is_transition"]
MFE_NUM = ["mfe_ddG_43nt_sliding", "delta_mfe_vs_wt", "abs_delta_mfe_vs_wt", "mfe_x_position_scaled"]
RCS_NUM = ["RCS", "delta_rcs_vs_wt", "abs_delta_rcs_vs_wt", "rcs_x_position_scaled"]
TRANSITIONS = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}


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


def finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def gc(codon: str) -> float:
    return (codon.count("G") + codon.count("C")) / 3.0


def nt_changes(wt: str, mutant: str) -> int:
    return sum(a != b for a, b in zip(wt, mutant))


def is_transition(wt: str, mutant: str) -> float:
    changes = [(a, b) for a, b in zip(wt, mutant) if a != b]
    return float(len(changes) == 1 and tuple(changes[0]) in TRANSITIONS)


def numeric_for(feature_set: str) -> list[str]:
    if feature_set == "intrinsic":
        return list(INTRINSIC_NUM)
    if feature_set == "local_mfe":
        return INTRINSIC_NUM + MFE_NUM
    if feature_set == "rcs_only":
        return INTRINSIC_NUM + RCS_NUM
    if feature_set == "full_mechanism":
        return INTRINSIC_NUM + MFE_NUM + RCS_NUM
    raise KeyError(feature_set)


def construct_features(row: dict, wt_row: dict) -> dict:
    wt = row["wt_codon"]
    mutant = row["mutant_codon"]
    pos = int(row["codon_position"])
    f = json.loads(row["features_json"])
    w = json.loads(wt_row["features_json"])
    rcs = float(f["RCS"])
    mfe = float(f["mfe_ddG_43nt_sliding"])
    wt_rcs = float(w["RCS"])
    wt_mfe = float(w["mfe_ddG_43nt_sliding"])
    delta_rcs = rcs - wt_rcs
    delta_mfe = mfe - wt_mfe
    position_scaled = pos / 71.0
    return {
        "position": str(pos),
        "wt_codon": wt,
        "mutant_codon": mutant,
        "amino_acid": row["amino_acid"],
        "position_scaled": position_scaled,
        "wt_gc_fraction": gc(wt),
        "mutant_gc_fraction": gc(mutant),
        "delta_gc_fraction": gc(mutant) - gc(wt),
        "wt_gc3": float(wt[2] in "GC"),
        "mutant_gc3": float(mutant[2] in "GC"),
        "nt_changes": float(nt_changes(wt, mutant)),
        "is_transition": is_transition(wt, mutant),
        "mfe_ddG_43nt_sliding": mfe,
        "delta_mfe_vs_wt": delta_mfe,
        "abs_delta_mfe_vs_wt": abs(delta_mfe),
        "mfe_x_position_scaled": mfe * position_scaled,
        "RCS": rcs,
        "delta_rcs_vs_wt": delta_rcs,
        "abs_delta_rcs_vs_wt": abs(delta_rcs),
        "rcs_x_position_scaled": rcs * position_scaled,
    }


def make_pipeline(feature_set: str, alpha: float) -> Pipeline:
    nums = numeric_for(feature_set)
    transformer = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=True), CATS),
        ("numeric", StandardScaler(with_mean=False), nums),
    ])
    return Pipeline([
        ("features", transformer),
        ("ridge", Ridge(alpha=alpha, fit_intercept=True, solver="lsqr", tol=1e-12, max_iter=100000)),
    ])


def xy(records: list[dict], feature_set: str) -> tuple[pd.DataFrame, np.ndarray | None]:
    if any(r["split"] not in {"train", "dev"} for r in records):
        raise AssertionError("Frozen test/out-of-development record reached a development feature matrix")
    nums = numeric_for(feature_set)
    columns = CATS + nums
    X = pd.DataFrame([{c: row[c] for c in columns} for row in records], columns=columns)
    for column in nums:
        X[column] = X[column].astype(np.float64)
    for column in CATS:
        X[column] = X[column].astype(str)
    y = np.asarray([float(row["expression_value"]) for row in records], dtype=np.float64)
    return X, y


def metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    y = np.asarray(y, dtype=np.float64)
    pred = np.asarray(pred, dtype=np.float64)
    return {
        "n": int(len(y)),
        "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
        "mae": float(np.mean(np.abs(y - pred))),
        "spearman": float(spearmanr(y, pred).statistic),
        "mean_y": float(np.mean(y)),
        "mean_prediction": float(np.mean(pred)),
    }


def effect(y: np.ndarray, candidate: np.ndarray, reference: np.ndarray) -> dict:
    a = metrics(y, candidate)
    b = metrics(y, reference)
    return {"delta_spearman": a["spearman"] - b["spearman"], "delta_rmse": a["rmse"] - b["rmse"]}


def holm(p_values: list[float]) -> list[float]:
    p = np.asarray(p_values, dtype=np.float64)
    order = np.argsort(p)
    adjusted = np.empty(len(p), dtype=np.float64)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        adjusted[index] = min(1.0, running)
    return [float(x) for x in adjusted]


def assign_folds(construct_ids: list[str], n_folds: int, salt: str) -> dict[str, int]:
    if len(set(construct_ids)) != len(construct_ids):
        raise ValueError("construct IDs must be unique")
    if n_folds < 2 or len(construct_ids) < n_folds:
        raise ValueError("not enough constructs for requested folds")
    ordered = sorted(construct_ids, key=lambda c: (hashlib.sha256(f"{salt}:{c}".encode()).hexdigest(), c))
    return {c: i % n_folds for i, c in enumerate(ordered)}


def fit_ridge(train: list[dict], evaluation: list[dict], feature_set: str, alpha: float) -> np.ndarray:
    model = make_pipeline(feature_set, alpha)
    X, y = xy(train, feature_set)
    model.fit(X, y)
    Xe, _ = xy(evaluation, feature_set)
    return np.asarray(model.predict(Xe), dtype=np.float64)


def nested_cv(records: list[dict], feature_set: str, alphas: list[float], seed: str, outer_folds: int, inner_folds: int) -> dict:
    ids = [r["construct_id"] for r in records]
    by_id = {r["construct_id"]: r for r in records}
    outer = assign_folds(ids, outer_folds, seed)
    predictions: dict[str, float] = {}
    selections = []
    for fold in range(outer_folds):
        outer_train_ids = [c for c in ids if outer[c] != fold]
        outer_eval_ids = [c for c in ids if outer[c] == fold]
        inner = assign_folds(outer_train_ids, inner_folds, f"{seed}:inner")
        inner_predictions = {alpha: {} for alpha in alphas}
        for inner_fold in range(inner_folds):
            inner_train = [by_id[c] for c in outer_train_ids if inner[c] != inner_fold]
            inner_eval = [by_id[c] for c in outer_train_ids if inner[c] == inner_fold]
            for alpha in alphas:
                pred = fit_ridge(inner_train, inner_eval, feature_set, alpha)
                inner_predictions[alpha].update({r["construct_id"]: float(p) for r, p in zip(inner_eval, pred)})
        trials = []
        for alpha in alphas:
            pred = np.asarray([inner_predictions[alpha][c] for c in outer_train_ids], dtype=np.float64)
            y = np.asarray([float(by_id[c]["expression_value"]) for c in outer_train_ids], dtype=np.float64)
            trials.append({"alpha": alpha, "inner_oof_rmse": float(np.sqrt(np.mean((y - pred) ** 2)))})
        best = sorted(trials, key=lambda t: (t["inner_oof_rmse"], -t["alpha"], str(t["alpha"])))[0]
        pred = fit_ridge([by_id[c] for c in outer_train_ids], [by_id[c] for c in outer_eval_ids], feature_set, best["alpha"])
        predictions.update({c: float(p) for c, p in zip(outer_eval_ids, pred)})
        selections.append({"outer_fold": fold, "n_outer_train": len(outer_train_ids), "n_outer_eval": len(outer_eval_ids), "selected_alpha": best["alpha"], "inner_alpha_grid": trials})
    if set(predictions) != set(ids) or len(predictions) != len(ids):
        raise AssertionError("outer OOF predictions are incomplete or duplicated")
    return {"predictions": predictions, "outer_folds": outer, "selections": selections}


def paired_analysis(y: np.ndarray, candidate: np.ndarray, reference: np.ndarray, bootstrap_seed: int, permutation_seed: int, replicates: int) -> dict:
    y = np.asarray(y, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    observed = effect(y, candidate, reference)
    n = len(y)
    boot = np.empty((replicates, 2), dtype=np.float64)
    rng = np.random.default_rng(bootstrap_seed)
    for b in range(replicates):
        idx = rng.integers(0, n, n)
        values = effect(y[idx], candidate[idx], reference[idx])
        boot[b] = [values["delta_spearman"], values["delta_rmse"]]
    rng = np.random.default_rng(permutation_seed)
    perm = np.empty((replicates, 2), dtype=np.float64)
    for b in range(replicates):
        swap = rng.random(n) < 0.5
        c = np.where(swap, reference, candidate)
        r = np.where(swap, candidate, reference)
        values = effect(y, c, r)
        perm[b] = [values["delta_spearman"], values["delta_rmse"]]
    obs = np.asarray([observed["delta_spearman"], observed["delta_rmse"]])
    p = (1 + np.sum(np.abs(perm) >= np.abs(obs)[None, :], axis=0)) / (replicates + 1.0)
    return {
        **observed,
        "delta_spearman_ci95": [float(x) for x in np.percentile(boot[:, 0], [2.5, 97.5])],
        "delta_rmse_ci95": [float(x) for x in np.percentile(boot[:, 1], [2.5, 97.5])],
        "permutation_p_spearman": float(p[0]),
        "permutation_p_rmse": float(p[1]),
        "bootstrap_replicates": int(replicates),
        "permutation_replicates": int(replicates),
    }


def load_development_records(cfg: dict) -> tuple[list[dict], dict]:
    csv_path = Path(cfg["source"]["csv"])
    if sha256(csv_path) != cfg["source"]["csv_sha256"]:
        raise AssertionError("source CSV hash mismatch")
    if sha256(cfg["source"]["codon_module"]) != cfg["source"]["codon_module_sha256"]:
        raise AssertionError("codon module hash mismatch")
    if sha256(cfg["source"]["v1_protocol"]) != cfg["source"]["v1_protocol_sha256"]:
        raise AssertionError("v1 protocol hash mismatch")
    if sha256(cfg["source"]["v1_report"]) != cfg["source"]["v1_report_sha256"]:
        raise AssertionError("v1 report hash mismatch")
    if sha256(cfg["source"]["v1_split_assignments"]) != cfg["source"]["v1_split_assignments_sha256"]:
        raise AssertionError("v1 split artifact hash mismatch")
    v1 = json.loads(Path(cfg["source"]["v1_report"]).read_text())
    if v1["status"] != "DEV_NO_GO_TEST_UNTOUCHED" or v1["primary_test"] is not None or v1["mechanism_increment_pass"]:
        raise AssertionError("v1 immutable no-go boundary mismatch")
    from codonflow.core.codon import AA_OF_INDEX, CODON_TO_INDEX, STOP_CODONS

    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    wt_by_position = {}
    media_rows = {"relative_fitness_rich": {}, "relative_fitness_minimal": {}}
    for row in rows:
        if row["record_class"] == "wild_type_control" and row["expression_type"] == "relative_fitness_rich":
            wt_by_position[int(row["codon_position"])] = row
        if row["record_class"] == "single_codon_variant" and row["expression_type"] in media_rows:
            media_rows[row["expression_type"]][row["construct_id"]] = row

    def aa(codon: str) -> str:
        return AA_OF_INDEX[CODON_TO_INDEX[codon]]

    def eligible(row: dict) -> bool:
        pos = int(row["codon_position"])
        wt = wt_by_position.get(pos)
        if wt is None or row["wt_codon"] in STOP_CODONS or row["mutant_codon"] in STOP_CODONS:
            return False
        if row["wt_codon"] == row["mutant_codon"] or row["amino_acid"] == "*":
            return False
        if aa(row["wt_codon"]) != aa(row["mutant_codon"]) or aa(row["mutant_codon"]) != row["amino_acid"]:
            return False
        if not finite(row["expression_value"]) or not finite(row["expression_stdev"]):
            return False
        f = json.loads(row["features_json"])
        w = json.loads(wt["features_json"])
        return all(finite(f.get(k)) and finite(w.get(k)) for k in ("RCS", "mfe_ddG_43nt_sliding"))

    common = set(media_rows["relative_fitness_rich"]) & set(media_rows["relative_fitness_minimal"])
    eligible_constructs = sorted(c for c in common if eligible(media_rows["relative_fitness_rich"][c]) and eligible(media_rows["relative_fitness_minimal"][c]))
    for c in eligible_constructs:
        a = json.loads(media_rows["relative_fitness_rich"][c]["features_json"])
        b = json.loads(media_rows["relative_fitness_minimal"][c]["features_json"])
        if not all(float(a[k]) == float(b[k]) for k in ("RCS", "mfe_ddG_43nt_sliding")):
            raise AssertionError("rich/minimal feature mismatch")
    primary_constructs = [c for c in eligible_constructs if 10 <= int(media_rows["relative_fitness_rich"][c]["codon_position"]) <= 71]
    ordered = sorted(primary_constructs, key=lambda c: hashlib.sha256(("20261119:" + c).encode()).hexdigest())
    n_dev = round(len(ordered) * 0.2)
    n_test = round(len(ordered) * 0.2)
    split_by_construct = {c: ("dev" if i < n_dev else ("test" if i < n_dev + n_test else "train")) for i, c in enumerate(ordered)}
    if dict(Counter(split_by_construct.values())) != {"dev": 33, "test": 33, "train": 98}:
        raise AssertionError("original split reconstruction mismatch")
    with Path(cfg["source"]["v1_split_assignments"]).open(newline="") as handle:
        saved_split = {r["construct_id"]: r["split"] for r in csv.DictReader(handle)}
    if saved_split != split_by_construct:
        raise AssertionError("saved v1 split differs from raw reconstruction")

    development = []
    for c in primary_constructs:
        split = split_by_construct[c]
        if split not in {"train", "dev"}:
            continue
        rich = media_rows["relative_fitness_rich"][c]
        pos = int(rich["codon_position"])
        row = dict(rich)
        row.update(construct_features(rich, wt_by_position[pos]))
        row["split"] = split
        development.append(row)
    development.sort(key=lambda r: r["construct_id"])
    if len(development) != 131 or any(r["split"] == "test" for r in development):
        raise AssertionError("development table contract failed")
    audit = {
        "source_rows": len(rows),
        "common_constructs_across_media": len(common),
        "eligible_constructs_all_positions": len(eligible_constructs),
        "primary_constructs_positions_10_71": len(primary_constructs),
        "development_n": len(development),
        "development_original_split_counts": dict(Counter(r["split"] for r in development)),
        "frozen_test_n_excluded": sum(s == "test" for s in split_by_construct.values()),
        "test_construct_ids_emitted": False,
        "v1_status_retained": v1["status"],
        "v1_primary_test": v1["primary_test"],
    }
    return development, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    config_path = Path(args.config).resolve()
    cfg = json.loads(config_path.read_text())
    records, data_audit = load_development_records(cfg)
    ids = [r["construct_id"] for r in records]
    y = np.asarray([float(r["expression_value"]) for r in records], dtype=np.float64)
    seeds = [cfg["nested_cv"]["primary_outer_seed"]] + cfg["nested_cv"]["sensitivity_outer_seeds"]
    alphas = cfg["features_and_models"]["alpha_grid"]
    runs = {}
    for seed in seeds:
        runs[seed] = {}
        for feature_set in BASE:
            runs[seed][feature_set] = nested_cv(records, feature_set, alphas, seed, cfg["nested_cv"]["outer_folds"], cfg["nested_cv"]["inner_folds"])

    primary_seed = seeds[0]
    primary_predictions = {name: np.asarray([runs[primary_seed][name]["predictions"][c] for c in ids]) for name in BASE}
    primary_models = {name: metrics(y, pred) for name, pred in primary_predictions.items()}
    comparisons = {}
    p_values = []
    for i, reference in enumerate(REFERENCES):
        result = paired_analysis(y, primary_predictions["full_mechanism"], primary_predictions[reference], cfg["primary_comparisons"]["bootstrap"]["seed"] + i, cfg["primary_comparisons"]["paired_permutation"]["seed"] + i, cfg["primary_comparisons"]["bootstrap"]["replicates"])
        comparisons[f"full_mechanism_minus_{reference}"] = result
        p_values.extend([result["permutation_p_spearman"], result["permutation_p_rmse"]])
    adjusted = holm(p_values)
    for i, reference in enumerate(REFERENCES):
        result = comparisons[f"full_mechanism_minus_{reference}"]
        result["holm_p_spearman"] = adjusted[2 * i]
        result["holm_p_rmse"] = adjusted[2 * i + 1]

    sensitivity = {}
    sensitivity_signs_ok = True
    for seed in seeds[1:]:
        predictions = {name: np.asarray([runs[seed][name]["predictions"][c] for c in ids]) for name in BASE}
        seed_result = {"models": {name: metrics(y, pred) for name, pred in predictions.items()}, "comparisons": {}}
        for reference in REFERENCES:
            values = effect(y, predictions["full_mechanism"], predictions[reference])
            seed_result["comparisons"][f"full_mechanism_minus_{reference}"] = values
            sensitivity_signs_ok &= values["delta_spearman"] > 0 and values["delta_rmse"] < 0
        sensitivity[seed] = seed_result
    primary_ok = all(
        result["delta_spearman_ci95"][0] > 0
        and result["delta_rmse_ci95"][1] < 0
        and result["holm_p_spearman"] < 0.05
        and result["holm_p_rmse"] < 0.05
        for result in comparisons.values()
    )
    development_go = bool(primary_ok and sensitivity_signs_ok)
    artifact_root = Path(cfg["artifacts"]["large_artifact_root"])
    artifact_root.mkdir(parents=True, exist_ok=True)
    prediction_path = artifact_root / "development_oof_predictions.csv"
    with prediction_path.open("w", newline="") as handle:
        fields = ["construct_id", "original_split", "position", "observed_rich"]
        for seed in seeds:
            fields.append(f"outer_fold_{seed}")
            fields.extend(f"pred_{seed}_{name}" for name in BASE)
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in records:
            out = {
                "construct_id": row["construct_id"], "original_split": row["split"], "position": row["position"], "observed_rich": row["expression_value"]
            }
            for seed in seeds:
                out[f"outer_fold_{seed}"] = runs[seed]["intrinsic"]["outer_folds"][row["construct_id"]]
                for name in BASE:
                    out[f"pred_{seed}_{name}"] = runs[seed][name]["predictions"][row["construct_id"]]
            writer.writerow(out)
    fold_path = artifact_root / "development_fold_assignments.csv"
    with fold_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["construct_id", "original_split", "seed", "outer_fold"])
        for row in records:
            for seed in seeds:
                writer.writerow([row["construct_id"], row["split"], seed, runs[seed]["intrinsic"]["outer_folds"][row["construct_id"]]])
    artifact_files = {}
    for path in (prediction_path, fold_path):
        artifact_files[path.name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    summary = {
        "schema": "a8-rk03-mage-development-nested-cv-v2",
        "protocol_id": cfg["protocol_id"],
        "protocol_sha256": sha256(config_path),
        "status": "DEV_GO_PENDING_INDEPENDENT_VERIFICATION_TEST_STILL_UNTOUCHED" if development_go else "DEV_NO_GO_TEST_UNTOUCHED",
        "development_go": development_go,
        "primary_development_ok": bool(primary_ok),
        "sensitivity_signs_ok": bool(sensitivity_signs_ok),
        "test_predictions_generated": False,
        "test_metrics_generated": False,
        "test_authorized_by_v1": False,
        "original_v1_gate_modified": False,
        "mechanism_increment_pass": False,
        "generator_training_authorized": False,
        "data_audit": data_audit,
        "primary_seed": primary_seed,
        "primary_models": primary_models,
        "primary_comparisons": comparisons,
        "sensitivity": sensitivity,
        "nested_cv_selection": {seed: {name: runs[seed][name]["selections"] for name in BASE} for seed in seeds},
        "artifact_files": artifact_files,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__, "numeric_threads": 1},
        "elapsed_s": time.perf_counter() - started,
        "limitations": cfg["interpretation"],
    }
    dump(args.output, summary)
    print(json.dumps({"status": summary["status"], "development_go": development_go, "primary_development_ok": primary_ok, "sensitivity_signs_ok": sensitivity_signs_ok, "n": len(records), "elapsed_s": summary["elapsed_s"]}, indent=2))


if __name__ == "__main__":
    main()
