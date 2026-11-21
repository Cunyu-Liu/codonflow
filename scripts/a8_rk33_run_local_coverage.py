#!/usr/bin/env python3
"""RK33 observed-R1 local42 coverage experiment; protocol frozen before fitting."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import platform
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy.stats import rankdata

import a8_rk02_mordstein_structure_increment as rk02
import a8_rk28_run_sequence_cluster_ood as rk28

FAMILIES = ("local42_vs_simple", "local42_vs_full1", "local42_vs_full3")
COMPARATORS = {"local42_vs_simple": "simple", "local42_vs_full1": "full1", "local42_vs_full3": "full3"}
MODELS = ("ridge", "histgb")
TEST_ORDER = [f"{family}__{model}_{metric}" for family in FAMILIES for model in MODELS for metric in ("spearman_effect", "mse_improvement")]
ARMS = [f"{model}_{arm}" for model in MODELS for arm in ("simple", "local42", "full1", "full3")]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def spearman(x, y):
    rx, ry = rankdata(np.asarray(x, float)), rankdata(np.asarray(y, float))
    dx, dy = rx - rx.mean(), ry - ry.mean()
    denominator = math.sqrt(float(np.dot(dx, dx) * np.dot(dy, dy)))
    if denominator == 0:
        raise RuntimeError("undefined Spearman")
    return float(np.dot(dx, dy) / denominator)


def holm(values):
    p = np.asarray(values, float)
    order = np.argsort(p)
    adjusted = np.empty(len(p), float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def local42_mfe(sequence):
    assert len(sequence) == 300 and set(sequence) <= set("ACGT")
    md = rk02.RNA.md()
    md.dangles = 0
    md.temperature = 37.0
    value = float(rk02.RNA.fold_compound(sequence[:42].replace("T", "U"), md).mfe()[1])
    if not math.isfinite(value) or abs(value) >= 100000:
        raise RuntimeError("ViennaRNA failure sentinel")
    return value


def effect_names_for_seed(predictions, seed):
    y = predictions["target"].to_numpy(float)
    metrics = []
    for arm in ARMS:
        pred = predictions[arm].to_numpy(float)
        metrics.append({"seed": seed, "arm": arm, "spearman": spearman(y, pred), "mse": float(np.mean((y - pred) ** 2))})
    effects = {}
    for family, comparator in COMPARATORS.items():
        for model in MODELS:
            local = predictions[f"{model}_local42"].to_numpy(float)
            reference = predictions[f"{model}_{comparator}"].to_numpy(float)
            effects[f"{family}__{model}_spearman_effect"] = spearman(y, local) - spearman(y, reference)
            effects[f"{family}__{model}_mse_improvement"] = float(np.mean((y - reference) ** 2 - (y - local) ** 2))
    assert list(effects) == TEST_ORDER
    return metrics, effects


def primary_inference(primary, resamples, bootstrap_seed, permutation_seed):
    y = primary["target"].to_numpy(float)
    clusters = primary["sequence_cluster_id"].to_numpy(int)
    unique = np.array(sorted(np.unique(clusters)), int)
    assert len(unique) == 74
    positions = np.searchsorted(unique, clusters)
    members = [np.flatnonzero(positions == index) for index in range(len(unique))]
    boot_ids = np.random.default_rng(bootstrap_seed).integers(0, len(unique), size=(resamples, len(unique)), dtype=np.int16)
    signs = np.random.default_rng(permutation_seed).choice(np.array([-1, 1], dtype=np.int8), size=(resamples, len(unique)))
    boot = {name: np.empty(resamples, float) for name in TEST_ORDER}
    null = {name: np.empty(resamples, float) for name in TEST_ORDER}
    observed = {}
    pair_arrays = {}
    for family, comparator in COMPARATORS.items():
        for model in MODELS:
            local = primary[f"{model}_local42"].to_numpy(float)
            reference = primary[f"{model}_{comparator}"].to_numpy(float)
            pair_arrays[(family, model)] = (local, reference)
            sp_name = f"{family}__{model}_spearman_effect"
            mse_name = f"{family}__{model}_mse_improvement"
            observed[sp_name] = spearman(y, local) - spearman(y, reference)
            difference = (y - reference) ** 2 - (y - local) ** 2
            observed[mse_name] = float(difference.mean())
            null[mse_name] = (signs[:, positions] * difference).mean(axis=1)
    for b in range(resamples):
        chosen = boot_ids[b]
        rows = np.concatenate([members[int(cluster)] for cluster in chosen])
        weights = np.bincount(chosen, minlength=len(unique))[positions].astype(float)
        swap = signs[b, positions] < 0
        for (family, model), (local, reference) in pair_arrays.items():
            sp_name = f"{family}__{model}_spearman_effect"
            mse_name = f"{family}__{model}_mse_improvement"
            boot[sp_name][b] = spearman(y[rows], local[rows]) - spearman(y[rows], reference[rows])
            difference = (y - reference) ** 2 - (y - local) ** 2
            boot[mse_name][b] = float(np.dot(weights, difference) / weights.sum())
            swapped_local, swapped_reference = local.copy(), reference.copy()
            swapped_local[swap], swapped_reference[swap] = reference[swap], local[swap]
            null[sp_name][b] = spearman(y, swapped_local) - spearman(y, swapped_reference)
    raw_p = []
    for name in TEST_ORDER:
        assert np.isfinite(boot[name]).all() and np.isfinite(null[name]).all()
        raw_p.append(float((1 + np.count_nonzero(np.abs(null[name]) >= abs(observed[name]))) / (resamples + 1)))
    adjusted = holm(raw_p)
    tests = []
    for index, name in enumerate(TEST_ORDER):
        tests.append({"test": name, "observed_effect": float(observed[name]), "ci95": [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))], "p_cluster_swap": raw_p[index], "p_holm": float(adjusted[index]), "bootstrap_median": float(np.median(boot[name]))})
    arrays = {f"bootstrap__{name}": boot[name] for name in TEST_ORDER}
    arrays.update({f"permutation__{name}": null[name] for name in TEST_ORDER})
    arrays["bootstrap_cluster_indices"] = boot_ids
    arrays["permutation_cluster_signs"] = signs
    return tests, arrays


def conclusion_for(family_pass):
    if all(family_pass.values()):
        return "LOCAL42_INCREMENT_AND_FULL_STRUCTURE_SUPERIORITY_SUPPORTED_RETROSPECTIVELY"
    if family_pass["local42_vs_simple"]:
        return "LOCAL42_INCREMENT_SUPPORTED_BUT_FULL_STRUCTURE_SUPERIORITY_NOT_ESTABLISHED"
    return "LOCAL42_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    wall_start = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat()
    protocol = json.loads(args.protocol.read_text())
    preflight = json.loads(args.preflight_report.read_text())
    assert protocol["schema"] == "a8-rk33-mordstein-local-coverage-protocol-v1"
    assert preflight["status"] == "PASS_RK33_LABEL_FREE_PREFLIGHT"
    assert preflight["protocol_sha256"] == sha256(args.protocol)
    assert preflight["model_fit_authorized"] is True and preflight["local_mfe_computed"] is False
    assert preflight["expression_or_model_fit_performed"] is False
    args.output_root.mkdir(parents=True, exist_ok=True)

    analysis = rk28.build_analysis(protocol)
    sequences = pd.read_csv(protocol["inputs"]["main_csv"]["path"], usecols=["variant_id", "sequence_5prime_300nt"], keep_default_na=False)
    sequence_map = dict(zip(sequences["variant_id"], sequences["sequence_5prime_300nt"]))
    analysis["mfe_observed_cds4_45_local42_kcal_mol"] = [local42_mfe(sequence_map[v].upper()) for v in analysis["variant_id"]]
    assignments = pd.read_csv(protocol["inputs"]["rk28_fold_assignments"]["path"])
    reused = pd.read_csv(protocol["inputs"]["rk28_oof_predictions"]["path"])
    assert sha256(protocol["inputs"]["rk28_fold_assignments"]["path"]) == protocol["inputs"]["rk28_fold_assignments"]["sha256"]
    assert sha256(protocol["inputs"]["rk28_oof_predictions"]["path"]) == protocol["inputs"]["rk28_oof_predictions"]["sha256"]
    assert len(assignments) == len(reused) == 1520
    primary_map = assignments[assignments["seed"] == protocol["outer_evaluation"]["primary_seed"]][["variant_id", "sequence_cluster_id", "fold"]].rename(columns={"fold": "primary_seed_fold"})
    analysis = analysis.merge(primary_map, on="variant_id", validate="one_to_one")
    analysis["cluster_size"] = analysis.groupby("sequence_cluster_id")["variant_id"].transform("size")
    assert len(analysis) == 152 and analysis["sequence_cluster_id"].nunique() == 74

    simple = protocol["models"]["feature_sets"]["simple"]
    feature_sets = {
        "local42": simple + protocol["models"]["feature_sets"]["local42_addition"],
        "full1": simple + protocol["models"]["feature_sets"]["full1_addition"],
    }
    all_predictions, metric_rows, effect_rows, training_rows = [], [], [], []
    for seed in protocol["outer_evaluation"]["sensitivity_seeds"]:
        old = reused[reused["seed"] == seed].copy()
        assert len(old) == 152
        merged = analysis.merge(old[["variant_id", "seed", "sequence_cluster_id", "target", "fold", "ridge_simple", "ridge_structure", "histgb_simple", "histgb_structure"]], on="variant_id", suffixes=("", "_rk28"), validate="one_to_one")
        assert np.array_equal(merged["target"].to_numpy(float), merged["target_rk28"].to_numpy(float))
        assert np.array_equal(merged["sequence_cluster_id"].to_numpy(int), merged["sequence_cluster_id_rk28"].to_numpy(int))
        current = merged[["variant_id", "seed", "sequence_cluster_id", "target", "fold", "ridge_simple", "histgb_simple"]].copy()
        current["ridge_full3"] = merged["ridge_structure"].to_numpy(float)
        current["histgb_full3"] = merged["histgb_structure"].to_numpy(float)
        for arm in ("ridge_local42", "ridge_full1", "histgb_local42", "histgb_full1"):
            current[arm] = np.nan
        folds = merged["fold"].to_numpy(int)
        for fold in range(5):
            train, test = merged.loc[folds != fold], merged.loc[folds == fold]
            test_index = np.flatnonzero(folds == fold)
            assert set(train["sequence_cluster_id"]).isdisjoint(set(test["sequence_cluster_id"]))
            for model in MODELS:
                for label, features in feature_sets.items():
                    prediction = rk28.fit_predict(model, features, train, test, int(seed + fold))
                    current.loc[current.index[test_index], f"{model}_{label}"] = prediction
            training_rows.append({"seed": seed, "fold": fold, "n_train": len(train), "n_test": len(test), "n_train_clusters": train["sequence_cluster_id"].nunique(), "n_test_clusters": test["sequence_cluster_id"].nunique(), "train_target_mean": float(train["target"].mean()), "histgb_random_state": int(seed + fold), "new_model_fits": 4, "reused_rk28_model_fits": 4, "evaluated_model_fits": 8, "cluster_leakage": False})
        assert np.isfinite(current[ARMS].to_numpy(float)).all()
        all_predictions.append(current)
        metrics, effects = effect_names_for_seed(current, seed)
        metric_rows.extend(metrics)
        effect_rows.extend({"seed": seed, "test": name, "effect": value} for name, value in effects.items())
    predictions = pd.concat(all_predictions, ignore_index=True)
    seed_metrics = pd.DataFrame(metric_rows)
    seed_effects = pd.DataFrame(effect_rows)
    training_log = pd.DataFrame(training_rows)

    primary = predictions[predictions["seed"] == protocol["outer_evaluation"]["primary_seed"]].reset_index(drop=True)
    inference = protocol["primary_inference"]
    tests, arrays = primary_inference(primary, inference["cluster_bootstrap"]["resamples"], inference["cluster_bootstrap"]["seed"], inference["cluster_swap_permutation"]["seed"])
    for test in tests:
        values = seed_effects[seed_effects["test"] == test["test"]].sort_values("seed")["effect"].to_numpy(float)
        assert len(values) == 10
        test["seed_effects"] = values.tolist()
        test["positive_seeds"] = int(np.count_nonzero(values > 0))
        test["mean_seed_effect"] = float(values.mean())
        test["median_seed_effect"] = float(np.median(values))
        test["pass"] = bool(test["observed_effect"] > 0 and test["ci95"][0] > 0 and test["p_holm"] < 0.05 and test["positive_seeds"] >= 8)
    family_pass = {family: all(row["pass"] for row in tests if row["test"].startswith(family + "__")) for family in FAMILIES}
    conclusion = conclusion_for(family_pass)

    analysis_path = args.output_root / "analysis_variants_152.csv"
    assignments_path = args.output_root / "fold_assignments.csv"
    predictions_path = args.output_root / "oof_predictions.csv"
    training_path = args.output_root / "training_log.csv"
    metrics_path = args.output_root / "seed_metrics.csv"
    effects_path = args.output_root / "seed_effects.csv"
    arrays_path = args.output_root / "primary_inference_arrays.npz"
    analysis.to_csv(analysis_path, index=False)
    assignments.to_csv(assignments_path, index=False)
    predictions.to_csv(predictions_path, index=False)
    training_log.to_csv(training_path, index=False)
    seed_metrics.to_csv(metrics_path, index=False)
    seed_effects.to_csv(effects_path, index=False)
    np.savez_compressed(arrays_path, **arrays)
    outputs = {path.name: {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size} for path in (analysis_path, assignments_path, predictions_path, training_path, metrics_path, effects_path, arrays_path)}
    summary = {
        "schema": "a8-rk33-mordstein-local-coverage-result-v1",
        "status": "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION",
        "protocol": str(args.protocol), "protocol_sha256": sha256(args.protocol),
        "preflight_report_sha256": sha256(args.preflight_report), "analysis_script_sha256": sha256(Path(__file__).resolve()),
        "source_csv_sha256": protocol["inputs"]["main_csv"]["sha256"],
        "rk28_predictions_sha256": protocol["inputs"]["rk28_oof_predictions"]["sha256"],
        "analysis_type": protocol["analysis_type"], "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": float(time.perf_counter() - wall_start), "n_variants": 152, "n_sequence_clusters": 74,
        "primary_seed": protocol["outer_evaluation"]["primary_seed"], "seeds": protocol["outer_evaluation"]["sensitivity_seeds"], "folds_per_seed": 5,
        "new_model_fits": 200, "reused_rk28_model_fits": 200, "evaluated_model_fits": 400, "device": "CPU_ONLY",
        "primary_absolute_performance": seed_metrics[seed_metrics["seed"] == protocol["outer_evaluation"]["primary_seed"]].drop(columns=["seed"]).to_dict("records"),
        "primary_tests": tests, "family_pass": family_pass, "all_12_pass": all(family_pass.values()),
        "scientific_conclusion": conclusion, "outputs": outputs,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__, "ViennaRNA": rk02.RNA.__version__},
        "scientific_flags": protocol["scientific_boundaries"],
    }
    write_json(args.summary, summary)
    print(json.dumps({"status": summary["status"], "scientific_conclusion": conclusion, "family_pass": family_pass, "passed_endpoints": sum(row["pass"] for row in tests), "total_endpoints": len(tests), "primary_absolute_performance": summary["primary_absolute_performance"], "primary_tests": tests, "new_model_fits": 200, "elapsed_seconds": summary["elapsed_seconds"], "summary": str(args.summary)}, indent=2))


if __name__ == "__main__":
    main()
