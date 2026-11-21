#!/usr/bin/env python3
"""Independent RK30 model verification without production/RK28 model imports."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

import a8_rk02_mordstein_structure_increment as feature_impl


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def spearman(x, y):
    x, y = rankdata(np.asarray(x, float)), rankdata(np.asarray(y, float))
    x, y = x - x.mean(), y - y.mean()
    denominator = float(np.sqrt(np.dot(x, x) * np.dot(y, y)))
    return float("nan") if denominator == 0 else float(np.dot(x, y) / denominator)


def make_folds(labels, seed):
    labels = np.asarray(labels, int)
    ids = np.array(sorted(np.unique(labels)), dtype=int)
    rng = np.random.default_rng(seed)
    shuffled = ids[rng.permutation(len(ids))].tolist()
    sizes = {int(c): int(np.sum(labels == c)) for c in ids}
    ordered = sorted(shuffled, key=lambda c: -sizes[int(c)])
    loads = np.zeros(5, dtype=int)
    assignment = {}
    for cluster in ordered:
        candidates = np.flatnonzero(loads == loads.min())
        fold = int(rng.choice(candidates))
        assignment[int(cluster)] = fold
        loads[fold] += sizes[int(cluster)]
    return np.array([assignment[int(c)] for c in labels], int), loads.tolist()


def fit_predict(name, features, train, test, random_state):
    x_train = train[features].to_numpy(float)
    x_test = test[features].to_numpy(float)
    y_train = train["target"].to_numpy(float)
    if name == "ridge":
        xm, xs = x_train.mean(0), x_train.std(0, ddof=0)
        ym, ys = float(y_train.mean()), float(y_train.std(ddof=0))
        if np.any(xs <= 0) or ys <= 0:
            raise RuntimeError("degenerate training fold")
        estimator = Ridge(alpha=1.0, solver="cholesky")
        estimator.fit((x_train - xm) / xs, (y_train - ym) / ys)
        return estimator.predict((x_test - xm) / xs) * ys + ym
    estimator = HistGradientBoostingRegressor(
        loss="squared_error", learning_rate=0.05, max_iter=200, max_leaf_nodes=7,
        min_samples_leaf=10, l2_regularization=1.0, early_stopping=False,
        random_state=random_state)
    estimator.fit(x_train, y_train)
    return estimator.predict(x_test)


def metric_effects(frame, arms):
    y = frame["target"].to_numpy(float)
    metrics = []
    for arm in arms:
        pred = frame[arm].to_numpy(float)
        metrics.append({"arm": arm, "spearman": spearman(y, pred), "mse": float(np.mean((y - pred) ** 2))})
    effects = {}
    for model in ["ridge", "histgb"]:
        simple = frame[f"{model}_simple"].to_numpy(float)
        structure = frame[f"{model}_structure"].to_numpy(float)
        effects[f"{model}_spearman_effect"] = spearman(y, structure) - spearman(y, simple)
        effects[f"{model}_mse_improvement"] = float(np.mean((y - simple) ** 2 - (y - structure) ** 2))
    return metrics, effects


def holm(p_values):
    p = np.asarray(p_values, float)
    order = np.argsort(p)
    result = np.empty(len(p))
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        result[index] = min(1.0, running)
    return result


def inference(primary, clusters, bootstrap_seed, permutation_seed, resamples):
    y = primary["target"].to_numpy(float)
    unique = np.array(sorted(np.unique(clusters)), int)
    cluster_index = np.searchsorted(unique, clusters)
    cluster_rows = [np.flatnonzero(cluster_index == i) for i in range(len(unique))]
    boot_clusters = np.random.default_rng(bootstrap_seed).integers(0, len(unique), size=(resamples, len(unique)), dtype=np.int16)
    perm_signs = np.random.default_rng(permutation_seed).choice(np.array([-1, 1], dtype=np.int8), size=(resamples, len(unique)))
    names = ["ridge_spearman_effect", "ridge_mse_improvement", "histgb_spearman_effect", "histgb_mse_improvement"]
    boot = {name: np.empty(resamples) for name in names}
    null = {name: np.empty(resamples) for name in names}
    observed = {}
    arms = {}
    for model in ["ridge", "histgb"]:
        simple = primary[f"{model}_simple"].to_numpy(float)
        structure = primary[f"{model}_structure"].to_numpy(float)
        arms[model] = simple, structure
        observed[f"{model}_spearman_effect"] = spearman(y, structure) - spearman(y, simple)
        diff = (y - simple) ** 2 - (y - structure) ** 2
        observed[f"{model}_mse_improvement"] = float(diff.mean())
        null[f"{model}_mse_improvement"] = (perm_signs[:, cluster_index] * diff).mean(1)
    for b in range(resamples):
        selected = boot_clusters[b]
        rows = np.concatenate([cluster_rows[int(c)] for c in selected])
        weights = np.bincount(selected, minlength=len(unique))[cluster_index].astype(float)
        signs = perm_signs[b, cluster_index] < 0
        for model, (simple, structure) in arms.items():
            sp_name, mse_name = f"{model}_spearman_effect", f"{model}_mse_improvement"
            boot[sp_name][b] = spearman(y[rows], structure[rows]) - spearman(y[rows], simple[rows])
            diff = (y - simple) ** 2 - (y - structure) ** 2
            boot[mse_name][b] = float(np.dot(weights, diff) / weights.sum())
            swapped_simple = np.where(signs, structure, simple)
            swapped_structure = np.where(signs, simple, structure)
            null[sp_name][b] = spearman(y, swapped_structure) - spearman(y, swapped_simple)
    tests = []
    for name in names:
        p = float((1 + np.sum(np.abs(null[name]) >= abs(observed[name]))) / (resamples + 1))
        tests.append({"test": name, "observed_effect": float(observed[name]),
                      "ci95": [float(np.quantile(boot[name], .025)), float(np.quantile(boot[name], .975))],
                      "p_cluster_swap": p})
    arrays = {f"bootstrap__{name}": boot[name] for name in names}
    arrays.update({f"permutation__{name}": null[name] for name in names})
    arrays["bootstrap_cluster_indices"] = boot_clusters
    arrays["permutation_cluster_signs"] = perm_signs
    return tests, arrays


def independent_features(protocol):
    cai = protocol["inputs"]["cai_wrapper"]
    refs = feature_impl.load_literal_assignment(Path(cai["path"]), cai["reference_variable"])
    weights = feature_impl.reference_weights(refs)
    raw = pd.read_csv(protocol["inputs"]["reference_csv"]["path"], usecols=["variant_id", "sequence_5prime_300nt"])
    rows = []
    for record in raw.to_dict("records"):
        sequence = record["sequence_5prime_300nt"].upper()
        row = {"variant_id": record["variant_id"], "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest()}
        row.update(feature_impl.simple_features(sequence, 0, weights))
        row.update(feature_impl.structure_features(sequence))
        rows.append(row)
    facts = pd.read_csv(protocol["inputs"]["cluster_facts_csv"]["path"])
    return pd.DataFrame(rows).merge(facts, on=["variant_id", "sequence_sha256"], validate="one_to_one")


def compare_frames(production, independent, keys, value_columns, tolerance=1e-10):
    a = production.sort_values(keys).reset_index(drop=True)
    b = independent.sort_values(keys).reset_index(drop=True)
    if len(a) != len(b) or any(a[key].tolist() != b[key].tolist() for key in keys):
        return False, float("inf")
    differences = []
    for column in value_columns:
        differences.append(float(np.max(np.abs(a[column].to_numpy(float) - b[column].to_numpy(float)))))
    return max(differences) <= tolerance, max(differences)


def main():
    wall_start = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--production-summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    production = json.loads(args.production_summary.read_text())
    model_dir = args.artifact_root / "model"
    output = args.artifact_root / "independent"
    output.mkdir(exist_ok=True)
    analysis = independent_features(protocol).merge(pd.read_csv(args.artifact_root / "matched_context_outcomes.csv"),
                                                    on=["variant_id", "sequence_cluster_id"], validate="one_to_one")
    analysis["sequence_cluster_id"] = analysis["sequence_cluster_id"].astype(int)
    production_analysis = pd.read_csv(model_dir / "analysis_matched_context.csv")
    feature_names = protocol["features"]["simple"] + protocol["features"]["structure_addition"]
    target_names = [f"target__{c}" for c in protocol["contexts"]]
    analysis_ok, analysis_diff = compare_frames(production_analysis, analysis, ["variant_id"], feature_names + target_names)
    simple = protocol["features"]["simple"]
    structure = simple + protocol["features"]["structure_addition"]
    feature_sets = {"simple": simple, "structure": structure, "mfe_only": protocol["features"]["structure_addition"]}
    seeds = protocol["outer_evaluation"]["sensitivity_seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    transport_frames, transport_fold_frames, transport_metric_rows, transport_effect_rows = [], [], [], []
    transport_fits = 0
    for pair in protocol["primary_transport"]["ordered_pairs"]:
        pair_name = f"{pair['source']}__to__{pair['target']}"
        for seed in seeds:
            fold_values, _ = make_folds(analysis["sequence_cluster_id"], seed)
            fold_frame = analysis[["variant_id", "sequence_cluster_id"]].copy()
            fold_frame.insert(0, "seed", seed); fold_frame.insert(0, "pair", pair_name); fold_frame["fold"] = fold_values
            transport_fold_frames.append(fold_frame)
            current = analysis[["variant_id", "sequence_cluster_id", f"target__{pair['target']}"]].copy().rename(columns={f"target__{pair['target']}": "target"})
            current.insert(0, "seed", seed); current.insert(0, "source", pair["source"]); current.insert(0, "target_context", pair["target"]); current["fold"] = fold_values
            arms = ["null", "ridge_simple", "ridge_structure", "histgb_simple", "histgb_structure"]
            for arm in arms: current[arm] = np.nan
            for fold in range(5):
                train = analysis.loc[fold_values != fold].copy(); test = analysis.loc[fold_values == fold].copy()
                train["target"] = train[f"target__{pair['source']}"]; test["target"] = test[f"target__{pair['target']}"]
                indices = np.flatnonzero(fold_values == fold)
                current.loc[current.index[indices], "null"] = float(train["target"].mean())
                for model in ["ridge", "histgb"]:
                    for label in ["simple", "structure"]:
                        arm = f"{model}_{label}"
                        current.loc[current.index[indices], arm] = fit_predict(model, feature_sets[label], train, test, seed + fold)
                        transport_fits += 1
            transport_frames.append(current)
            metrics, effects = metric_effects(current, arms)
            transport_metric_rows.extend({"pair": pair_name, "seed": seed, **row} for row in metrics)
            transport_effect_rows.extend({"pair": pair_name, "seed": seed, "test": name, "effect": value} for name, value in effects.items())
    within_frames, within_fold_frames, within_metric_rows, within_effect_rows = [], [], [], []
    within_fits = 0
    for context in protocol["secondary_within_context"]["contexts"]:
        for seed in seeds:
            fold_values, _ = make_folds(analysis["sequence_cluster_id"], seed)
            fold_frame = analysis[["variant_id", "sequence_cluster_id"]].copy()
            fold_frame.insert(0, "seed", seed); fold_frame.insert(0, "context", context); fold_frame["fold"] = fold_values
            within_fold_frames.append(fold_frame)
            current = analysis[["variant_id", "sequence_cluster_id", f"target__{context}"]].copy().rename(columns={f"target__{context}": "target"})
            current.insert(0, "seed", seed); current.insert(0, "context", context); current["fold"] = fold_values
            arms = ["null", "ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"]
            for arm in arms: current[arm] = np.nan
            for fold in range(5):
                train = analysis.loc[fold_values != fold].copy(); test = analysis.loc[fold_values == fold].copy()
                train["target"] = train[f"target__{context}"]; test["target"] = test[f"target__{context}"]
                indices = np.flatnonzero(fold_values == fold)
                current.loc[current.index[indices], "null"] = float(train["target"].mean())
                for model in ["ridge", "histgb"]:
                    for label, names in feature_sets.items():
                        arm = f"{model}_{label}"
                        current.loc[current.index[indices], arm] = fit_predict(model, names, train, test, seed + fold)
                        within_fits += 1
            within_frames.append(current)
            metrics, effects = metric_effects(current, arms)
            within_metric_rows.extend({"context": context, "seed": seed, **row} for row in metrics)
            within_effect_rows.extend({"context": context, "seed": seed, "test": name, "effect": value} for name, value in effects.items())
    transport = pd.concat(transport_frames, ignore_index=True)
    within = pd.concat(within_frames, ignore_index=True)
    transport.to_csv(output / "transport_oof_predictions.csv", index=False)
    within.to_csv(output / "within_context_oof_predictions.csv", index=False)
    transport_folds_independent = pd.concat(transport_fold_frames, ignore_index=True)
    within_folds_independent = pd.concat(within_fold_frames, ignore_index=True)
    transport_folds_independent.to_csv(output / "transport_fold_assignments.csv", index=False)
    within_folds_independent.to_csv(output / "within_context_fold_assignments.csv", index=False)
    transport_metrics = pd.DataFrame(transport_metric_rows); within_metrics = pd.DataFrame(within_metric_rows)
    transport_effects = pd.DataFrame(transport_effect_rows); within_effects = pd.DataFrame(within_effect_rows)
    transport_metrics.to_csv(output / "transport_seed_metrics.csv", index=False); within_metrics.to_csv(output / "within_context_seed_metrics.csv", index=False)
    transport_effects.to_csv(output / "transport_seed_effects.csv", index=False); within_effects.to_csv(output / "within_context_seed_effects.csv", index=False)

    comparisons = {}
    comparisons["analysis"] = {"pass": analysis_ok, "max_difference": analysis_diff}
    comparisons["transport_predictions"] = dict(zip(["pass", "max_difference"], compare_frames(
        pd.read_csv(model_dir / "transport_oof_predictions.csv"), transport,
        ["source", "target_context", "seed", "variant_id"],
        ["null", "ridge_simple", "ridge_structure", "histgb_simple", "histgb_structure"])))
    comparisons["within_predictions"] = dict(zip(["pass", "max_difference"], compare_frames(
        pd.read_csv(model_dir / "within_context_oof_predictions.csv"), within,
        ["context", "seed", "variant_id"], ["null", "ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"])))
    comparisons["transport_metrics"] = dict(zip(["pass", "max_difference"], compare_frames(
        pd.read_csv(model_dir / "transport_seed_metrics.csv", keep_default_na=False), transport_metrics,
        ["pair", "seed", "arm"], ["spearman", "mse"])))
    comparisons["within_metrics"] = dict(zip(["pass", "max_difference"], compare_frames(
        pd.read_csv(model_dir / "within_context_seed_metrics.csv", keep_default_na=False), within_metrics,
        ["context", "seed", "arm"], ["spearman", "mse"])))
    comparisons["transport_effects"] = dict(zip(["pass", "max_difference"], compare_frames(
        pd.read_csv(model_dir / "transport_seed_effects.csv"), transport_effects,
        ["pair", "seed", "test"], ["effect"])))
    comparisons["within_effects"] = dict(zip(["pass", "max_difference"], compare_frames(
        pd.read_csv(model_dir / "within_context_seed_effects.csv"), within_effects,
        ["context", "seed", "test"], ["effect"])))
    comparisons["transport_folds"] = dict(zip(["pass", "max_difference"], compare_frames(
        pd.read_csv(model_dir / "transport_fold_assignments.csv"), transport_folds_independent,
        ["pair", "seed", "variant_id"], ["sequence_cluster_id", "fold"], tolerance=0)))
    comparisons["within_folds"] = dict(zip(["pass", "max_difference"], compare_frames(
        pd.read_csv(model_dir / "within_context_fold_assignments.csv"), within_folds_independent,
        ["context", "seed", "variant_id"], ["sequence_cluster_id", "fold"], tolerance=0)))

    inf = protocol["primary_transport"]
    independent_primary, primary_array_mismatches = [], []
    for pair in inf["ordered_pairs"]:
        pair_name = f"{pair['source']}__to__{pair['target']}"
        current = transport[(transport["source"] == pair["source"]) & (transport["target_context"] == pair["target"]) & (transport["seed"] == primary_seed)].reset_index(drop=True)
        tests, arrays = inference(current, current["sequence_cluster_id"].to_numpy(int), inf["cluster_bootstrap"]["seed"], inf["cluster_swap_permutation"]["seed"], inf["cluster_bootstrap"]["resamples"])
        produced_arrays = np.load(model_dir / f"transport_inference__{pair_name}.npz")
        for key in arrays:
            if key not in produced_arrays or not np.allclose(arrays[key], produced_arrays[key], rtol=0, atol=1e-12):
                primary_array_mismatches.append(f"{pair_name}:{key}")
        for test in tests:
            effects = transport_effects[(transport_effects["pair"] == pair_name) & (transport_effects["test"] == test["test"])].sort_values("seed")["effect"].to_numpy()
            test.update({"pair": pair_name, "positive_seeds": int((effects > 0).sum()), "seed_effects": effects.tolist()})
            independent_primary.append(test)
    family_p = holm([row["p_cluster_swap"] for row in independent_primary])
    for row, adjusted in zip(independent_primary, family_p):
        row["p_holm"] = float(adjusted)
        row["pass"] = bool(row["observed_effect"] > 0 and row["ci95"][0] > 0 and adjusted < .05 and row["positive_seeds"] >= 8)
    primary_differences = []
    for expected, actual in zip(production["primary_transport_tests"], independent_primary):
        for key in ["observed_effect", "p_cluster_swap", "p_holm"]:
            primary_differences.append(abs(float(expected[key]) - float(actual[key])))
        primary_differences.extend(abs(float(a) - float(b)) for a, b in zip(expected["ci95"], actual["ci95"]))
        if expected["pass"] != actual["pass"] or expected["positive_seeds"] != actual["positive_seeds"]:
            primary_differences.append(float("inf"))
    independent_secondary, secondary_array_mismatches = [], []
    for context in protocol["secondary_within_context"]["contexts"]:
        current = within[(within["context"] == context) & (within["seed"] == primary_seed)].reset_index(drop=True)
        tests, arrays = inference(current, current["sequence_cluster_id"].to_numpy(int), inf["cluster_bootstrap"]["seed"], inf["cluster_swap_permutation"]["seed"], inf["cluster_bootstrap"]["resamples"])
        produced_arrays = np.load(model_dir / f"within_inference__{context}.npz")
        for key in arrays:
            if key not in produced_arrays or not np.allclose(arrays[key], produced_arrays[key], rtol=0, atol=1e-12):
                secondary_array_mismatches.append(f"{context}:{key}")
        for test in tests:
            effects = within_effects[(within_effects["context"] == context) & (within_effects["test"] == test["test"])].sort_values("seed")["effect"].to_numpy()
            test.update({"context": context, "positive_seeds": int((effects > 0).sum()), "seed_effects": effects.tolist()})
            independent_secondary.append(test)
    secondary_p = holm([row["p_cluster_swap"] for row in independent_secondary])
    for row, adjusted in zip(independent_secondary, secondary_p):
        row["p_holm"] = float(adjusted)
        row["pass"] = bool(row["observed_effect"] > 0 and row["ci95"][0] > 0 and adjusted < .05 and row["positive_seeds"] >= 8)
    secondary_differences = []
    for expected, actual in zip(production["secondary_within_context_tests"], independent_secondary):
        for key in ["observed_effect", "p_cluster_swap", "p_holm"]:
            secondary_differences.append(abs(float(expected[key]) - float(actual[key])))
        secondary_differences.extend(abs(float(a) - float(b)) for a, b in zip(expected["ci95"], actual["ci95"]))
        if expected["pass"] != actual["pass"] or expected["positive_seeds"] != actual["positive_seeds"]:
            secondary_differences.append(float("inf"))
    comparisons["primary_inference"] = {"pass": max(primary_differences) <= 1e-10 and not primary_array_mismatches,
                                         "max_difference": max(primary_differences), "array_mismatches": primary_array_mismatches}
    comparisons["secondary_inference"] = {"pass": max(secondary_differences) <= 1e-10 and not secondary_array_mismatches,
                                           "max_difference": max(secondary_differences), "array_mismatches": secondary_array_mismatches}
    fit_ok = transport_fits == production["transport_model_fits"] == 800 and within_fits == production["within_context_model_fits"] == 900
    conclusion_ok = (all(row["pass"] for row in independent_primary) == production["context_transportable_mfe_increment_pass"])
    all_pass = all(row["pass"] for row in comparisons.values()) and fit_ok and conclusion_ok
    report = {
        "schema": "a8.rk30.independent_model_verification.v1",
        "status": "PASS_INDEPENDENT_MODEL_VERIFICATION" if all_pass else "FAIL_INDEPENDENT_MODEL_VERIFICATION",
        "production_module_imported": False, "rk28_model_module_imported": False,
        "shared_frozen_feature_implementation": "a8_rk02_mordstein_structure_increment.py",
        "transport_fits_recomputed": transport_fits, "within_fits_recomputed": within_fits,
        "cost_seconds": time.perf_counter() - wall_start,
        "fit_count_pass": fit_ok, "scientific_conclusion_pass": conclusion_ok,
        "independent_family_pass": all(row["pass"] for row in independent_primary),
        "comparisons": comparisons,
        "production_summary_sha256": sha(args.production_summary),
        "independent_transport_predictions_sha256": sha(output / "transport_oof_predictions.csv"),
        "independent_within_predictions_sha256": sha(output / "within_context_oof_predictions.csv"),
        "note": "All 1,700 fits, all seed metrics/effects, and all 7x10,000 bootstrap/permutation analyses were independently recomputed."
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
