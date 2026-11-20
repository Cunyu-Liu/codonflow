#!/usr/bin/env python3
"""RK27 fixed-GFP sequence-cluster OOD production analysis.

Frozen protocol: audits/20261121/RK27/a8_rk27_kudla_sequence_cluster_ood_protocol_v1.json
No functional-untouched data are accessed. All model fitting is CPU-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx = rankdata(np.asarray(x, dtype=float))
    ry = rankdata(np.asarray(y, dtype=float))
    dx = rx - rx.mean()
    dy = ry - ry.mean()
    denom = float(np.sqrt(np.dot(dx, dx) * np.dot(dy, dy)))
    if denom == 0:
        return float("nan")
    return float(np.dot(dx, dy) / denom)


def holm_adjust(p_values: list[float]) -> list[float]:
    p = np.asarray(p_values, dtype=float)
    assert p.shape == (4,) and np.isfinite(p).all()
    order = np.argsort(p)
    adjusted = np.empty(4, dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        candidate = (4 - rank) * p[index]
        running = max(running, candidate)
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def make_cluster_folds(cluster_labels: np.ndarray, seed: int, n_folds: int = 5) -> tuple[np.ndarray, list[int]]:
    labels = np.asarray(cluster_labels, dtype=int)
    ids = np.array(sorted(np.unique(labels).tolist()), dtype=int)
    rng = np.random.default_rng(seed)
    shuffled = ids[rng.permutation(len(ids))].tolist()
    sizes = {int(c): int(np.sum(labels == c)) for c in ids}
    ordered = sorted(shuffled, key=lambda c: -sizes[int(c)])
    loads = np.zeros(n_folds, dtype=int)
    assignment: dict[int, int] = {}
    for cluster in ordered:
        candidates = np.flatnonzero(loads == loads.min())
        fold = int(rng.choice(candidates))
        assignment[int(cluster)] = fold
        loads[fold] += sizes[int(cluster)]
    folds = np.array([assignment[int(c)] for c in labels], dtype=int)
    return folds, loads.tolist()


def aggregate_source(source: pd.DataFrame) -> pd.DataFrame:
    required = {
        "source_row", "seqId", "cds", "protein_aa", "CAI", "log10_expression",
        "mfe_5prime_kcal_mol", "cds_sha256"
    }
    assert required.issubset(source.columns)
    rows = []
    for cds_sha, group in source.groupby("cds_sha256", sort=False):
        assert group["cds"].nunique() == 1
        assert group["protein_aa"].nunique() == 1
        for feature in ["CAI", "mfe_5prime_kcal_mol"]:
            assert np.isfinite(group[feature]).all()
            assert group[feature].nunique(dropna=False) == 1
        assert np.isfinite(group["log10_expression"]).all()
        cds = str(group["cds"].iloc[0]).upper()
        assert len(cds) == 720 and set(cds) <= set("ACGT")
        assert hashlib.sha256(cds.encode()).hexdigest() == cds_sha
        seq = np.array(list(cds))
        rows.append({
            "cds_sha256": cds_sha,
            "first_source_row": int(group["source_row"].min()),
            "source_rows": ";".join(str(int(x)) for x in sorted(group["source_row"])),
            "seqIds": ";".join(str(x) for x in group["seqId"]),
            "n_measurements": int(len(group)),
            "CAI": float(group["CAI"].iloc[0]),
            "gc_cds": float(np.mean((seq == "G") | (seq == "C"))),
            "gc3_cds": float(np.mean((seq[2::3] == "G") | (seq[2::3] == "C"))),
            "mfe_5prime_kcal_mol": float(group["mfe_5prime_kcal_mol"].iloc[0]),
            "target": float(group["log10_expression"].mean()),
        })
    result = pd.DataFrame(rows).sort_values("first_source_row").reset_index(drop=True)
    result.insert(0, "group_id", [f"g{i:03d}" for i in range(len(result))])
    return result


def swap_arms(simple: np.ndarray, structure: np.ndarray, swap_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    simple = np.asarray(simple, dtype=float)
    structure = np.asarray(structure, dtype=float)
    mask = np.asarray(swap_mask, dtype=bool)
    return np.where(mask, structure, simple), np.where(mask, simple, structure)


def fit_predict(model_name: str, feature_names: list[str], train: pd.DataFrame, test: pd.DataFrame, random_state: int) -> np.ndarray:
    if model_name == "ridge":
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    elif model_name == "histgb":
        model = HistGradientBoostingRegressor(
            loss="squared_error", learning_rate=0.05, max_iter=200,
            max_leaf_nodes=7, min_samples_leaf=10, l2_regularization=1.0,
            early_stopping=False, random_state=random_state,
        )
    else:
        raise ValueError(model_name)
    model.fit(train[feature_names], train["target"])
    prediction = np.asarray(model.predict(test[feature_names]), dtype=float)
    assert np.isfinite(prediction).all()
    return prediction


def metric_rows_for_seed(predictions: pd.DataFrame, seed: int) -> tuple[list[dict], dict[str, float]]:
    y = predictions["target"].to_numpy(float)
    metric_rows = []
    arms = ["null", "ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"]
    for arm in arms:
        pred = predictions[arm].to_numpy(float)
        metric_rows.append({
            "seed": seed, "arm": arm,
            "spearman": spearman(y, pred),
            "mse": float(np.mean((y - pred) ** 2)),
        })
    effects = {}
    for model in ["ridge", "histgb"]:
        simple = predictions[f"{model}_simple"].to_numpy(float)
        structure = predictions[f"{model}_structure"].to_numpy(float)
        effects[f"{model}_spearman_effect"] = spearman(y, structure) - spearman(y, simple)
        effects[f"{model}_mse_improvement"] = float(np.mean((y - simple) ** 2) - np.mean((y - structure) ** 2))
    return metric_rows, effects


def primary_inference(primary: pd.DataFrame, cluster_ids: np.ndarray, bootstrap_seed: int, permutation_seed: int, resamples: int) -> tuple[list[dict], dict[str, np.ndarray]]:
    y = primary["target"].to_numpy(float)
    unique_clusters = np.array(sorted(np.unique(cluster_ids).tolist()), dtype=int)
    assert len(unique_clusters) == 37
    cluster_index = np.searchsorted(unique_clusters, cluster_ids)
    cluster_rows = [np.flatnonzero(cluster_index == i) for i in range(len(unique_clusters))]
    rng_boot = np.random.default_rng(bootstrap_seed)
    boot_clusters = rng_boot.integers(0, len(unique_clusters), size=(resamples, len(unique_clusters)), dtype=np.int16)
    rng_perm = np.random.default_rng(permutation_seed)
    perm_signs = rng_perm.choice(np.array([-1, 1], dtype=np.int8), size=(resamples, len(unique_clusters)))

    tests = ["ridge_spearman_effect", "ridge_mse_improvement", "histgb_spearman_effect", "histgb_mse_improvement"]
    observed: dict[str, float] = {}
    boot = {name: np.empty(resamples, dtype=float) for name in tests}
    null = {name: np.empty(resamples, dtype=float) for name in tests}
    arms = {}
    for model in ["ridge", "histgb"]:
        simple = primary[f"{model}_simple"].to_numpy(float)
        structure = primary[f"{model}_structure"].to_numpy(float)
        arms[model] = (simple, structure)
        observed[f"{model}_spearman_effect"] = spearman(y, structure) - spearman(y, simple)
        diff = (y - simple) ** 2 - (y - structure) ** 2
        observed[f"{model}_mse_improvement"] = float(diff.mean())
        null[f"{model}_mse_improvement"] = (perm_signs[:, cluster_index] * diff).mean(axis=1)

    for b in range(resamples):
        selected = boot_clusters[b]
        row_index = np.concatenate([cluster_rows[int(c)] for c in selected])
        weights = np.bincount(selected, minlength=len(unique_clusters))[cluster_index].astype(float)
        assert weights.sum() > 0
        signs = perm_signs[b, cluster_index] < 0
        for model, (simple, structure) in arms.items():
            sp_name = f"{model}_spearman_effect"
            mse_name = f"{model}_mse_improvement"
            boot[sp_name][b] = spearman(y[row_index], structure[row_index]) - spearman(y[row_index], simple[row_index])
            diff = (y - simple) ** 2 - (y - structure) ** 2
            boot[mse_name][b] = float(np.dot(weights, diff) / weights.sum())
            swapped_simple, swapped_structure = swap_arms(simple, structure, signs)
            null[sp_name][b] = spearman(y, swapped_structure) - spearman(y, swapped_simple)

    p_values = []
    results = []
    for name in tests:
        assert np.isfinite(boot[name]).all() and np.isfinite(null[name]).all()
        obs = float(observed[name])
        p = float((1 + np.sum(np.abs(null[name]) >= abs(obs))) / (resamples + 1))
        p_values.append(p)
        results.append({
            "test": name,
            "observed_effect": obs,
            "ci95": [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))],
            "p_cluster_swap": p,
            "bootstrap_median": float(np.median(boot[name])),
        })
    adjusted = holm_adjust(p_values)
    for row, p_holm in zip(results, adjusted):
        row["p_holm"] = p_holm
    arrays = {f"bootstrap__{name}": boot[name] for name in tests}
    arrays.update({f"permutation__{name}": null[name] for name in tests})
    arrays["bootstrap_cluster_indices"] = boot_clusters
    arrays["permutation_cluster_signs"] = perm_signs
    return results, arrays


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--coverage-report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    protocol = json.loads(args.protocol.read_text())
    coverage = json.loads(args.coverage_report.read_text())
    assert protocol["status"] == "FROZEN_BEFORE_ANY_RK27_MODEL_FIT_OR_NEW_EXPRESSION_ASSOCIATION"
    assert coverage["status"] == "PASS_LABEL_FREE_COVERAGE_AUDIT"
    assert coverage["protocol_sha256"] == sha256(args.protocol)
    assert coverage["expression_or_model_fit_performed"] is False
    args.output_root.mkdir(parents=True, exist_ok=True)

    source_path = Path(protocol["inputs"]["main_csv"]["path"])
    assert sha256(source_path) == protocol["inputs"]["main_csv"]["sha256"]
    usecols = ["source_row", "seqId", "cds", "protein_aa", "CAI", "log10_expression", "mfe_5prime_kcal_mol", "cds_sha256"]
    source = pd.read_csv(source_path, usecols=usecols)
    assert len(source) == 154
    analysis = aggregate_source(source)
    assert len(analysis) == 150 and (analysis["n_measurements"] > 1).sum() == 4
    facts_path = Path(coverage["facts_csv"])
    assert sha256(facts_path) == coverage["facts_sha256"]
    facts = pd.read_csv(facts_path)
    analysis = analysis.merge(facts, on="cds_sha256", how="left", validate="one_to_one", suffixes=("", "_facts"))
    assert analysis["sequence_cluster_id"].notna().all()
    assert analysis["first_source_row"].equals(analysis["first_source_row_facts"])
    analysis = analysis.drop(columns=["first_source_row_facts", "cluster_size"])
    analysis["sequence_cluster_id"] = analysis["sequence_cluster_id"].astype(int)
    assert analysis["sequence_cluster_id"].nunique() == 37
    analysis_path = args.output_root / "analysis_exact_cds_150.csv"
    analysis.to_csv(analysis_path, index=False)

    feature_sets = {
        "simple": ["CAI", "gc_cds", "gc3_cds"],
        "structure": ["CAI", "gc_cds", "gc3_cds", "mfe_5prime_kcal_mol"],
        "mfe_only": ["mfe_5prime_kcal_mol"],
    }
    seeds = protocol["outer_evaluation"]["sensitivity_seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    all_predictions = []
    fold_rows = []
    seed_metric_rows = []
    seed_effect_rows = []
    for seed in seeds:
        folds, loads = make_cluster_folds(analysis["sequence_cluster_id"].to_numpy(int), seed)
        if seed == primary_seed:
            assert loads == coverage["selected_coverage"]["primary_seed_fold_sizes"]
        fold_assignment = analysis[["group_id", "cds_sha256", "sequence_cluster_id"]].copy()
        fold_assignment.insert(0, "seed", seed)
        fold_assignment["fold"] = folds
        fold_rows.append(fold_assignment)
        seed_predictions = analysis[["group_id", "cds_sha256", "sequence_cluster_id", "target"]].copy()
        seed_predictions.insert(0, "seed", seed)
        seed_predictions["fold"] = folds
        for arm in ["null", "ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"]:
            seed_predictions[arm] = np.nan
        for fold in range(5):
            train = analysis[folds != fold].copy()
            test = analysis[folds == fold].copy()
            test_index = np.flatnonzero(folds == fold)
            assert set(train["sequence_cluster_id"]).isdisjoint(set(test["sequence_cluster_id"]))
            histgb_seed = int(seed + fold)
            seed_predictions.loc[seed_predictions.index[test_index], "null"] = float(train["target"].mean())
            for model_name in ["ridge", "histgb"]:
                for feature_label, feature_names in feature_sets.items():
                    arm = f"{model_name}_{feature_label}"
                    pred = fit_predict(model_name, feature_names, train, test, histgb_seed)
                    seed_predictions.loc[seed_predictions.index[test_index], arm] = pred
            # The training log is built separately below; no result-dependent decisions occur here.
        assert np.isfinite(seed_predictions[["null", "ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"]].to_numpy(float)).all()
        all_predictions.append(seed_predictions)
        metrics, effects = metric_rows_for_seed(seed_predictions, seed)
        seed_metric_rows.extend(metrics)
        for test_name, effect in effects.items():
            seed_effect_rows.append({"seed": seed, "test": test_name, "effect": effect})

    predictions = pd.concat(all_predictions, ignore_index=True)
    assignments = pd.concat(fold_rows, ignore_index=True)
    predictions_path = args.output_root / "oof_predictions.csv"
    assignments_path = args.output_root / "fold_assignments.csv"
    predictions.to_csv(predictions_path, index=False)
    assignments.to_csv(assignments_path, index=False)

    # Fold-level training log is derived only from assignments and training targets.
    training_log_rows = []
    for seed in seeds:
        current = assignments[assignments["seed"] == seed]
        for fold in range(5):
            test_groups = set(current.loc[current["fold"] == fold, "group_id"])
            train_mask = ~analysis["group_id"].isin(test_groups)
            test_mask = ~train_mask
            train_clusters = set(analysis.loc[train_mask, "sequence_cluster_id"])
            test_clusters = set(analysis.loc[test_mask, "sequence_cluster_id"])
            assert train_clusters.isdisjoint(test_clusters)
            training_log_rows.append({
                "seed": seed, "fold": fold,
                "n_train": int(train_mask.sum()), "n_test": int(test_mask.sum()),
                "n_train_clusters": len(train_clusters), "n_test_clusters": len(test_clusters),
                "train_target_mean": float(analysis.loc[train_mask, "target"].mean()),
                "histgb_random_state": int(seed + fold), "model_fits": 6,
                "cluster_leakage": False,
            })
    training_log = pd.DataFrame(training_log_rows)
    training_log_path = args.output_root / "training_log.csv"
    training_log.to_csv(training_log_path, index=False)

    seed_metrics = pd.DataFrame(seed_metric_rows)
    seed_effects = pd.DataFrame(seed_effect_rows)
    seed_metrics_path = args.output_root / "seed_metrics.csv"
    seed_effects_path = args.output_root / "seed_effects.csv"
    seed_metrics.to_csv(seed_metrics_path, index=False)
    seed_effects.to_csv(seed_effects_path, index=False)

    primary = predictions[predictions["seed"] == primary_seed].reset_index(drop=True)
    assert len(primary) == 150
    inf = protocol["primary_inference"]
    primary_tests, arrays = primary_inference(
        primary, primary["sequence_cluster_id"].to_numpy(int),
        inf["cluster_bootstrap"]["seed"], inf["cluster_swap_permutation"]["seed"],
        inf["cluster_bootstrap"]["resamples"],
    )
    assert inf["cluster_swap_permutation"]["permutations"] == inf["cluster_bootstrap"]["resamples"]
    arrays_path = args.output_root / "primary_inference_arrays.npz"
    np.savez_compressed(arrays_path, **arrays)

    all_pass = True
    for test in primary_tests:
        effects = seed_effects[seed_effects["test"] == test["test"]].sort_values("seed")["effect"].to_numpy(float)
        test["seed_effects"] = effects.tolist()
        test["positive_seeds"] = int(np.sum(effects > 0))
        test["mean_seed_effect"] = float(effects.mean())
        test["median_seed_effect"] = float(np.median(effects))
        test["pass"] = bool(
            test["observed_effect"] > 0
            and test["ci95"][0] > 0
            and test["p_holm"] < 0.05
            and test["positive_seeds"] >= 8
        )
        all_pass = all_pass and test["pass"]

    primary_metrics = seed_metrics[seed_metrics["seed"] == primary_seed].drop(columns=["seed"]).to_dict("records")
    output_files = {}
    for path in [analysis_path, assignments_path, predictions_path, training_log_path, seed_metrics_path, seed_effects_path, arrays_path]:
        output_files[path.name] = {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}
    summary = {
        "schema": "a8-rk27-kudla-sequence-cluster-ood-result-v1",
        "status": "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION",
        "protocol": str(args.protocol),
        "protocol_sha256": sha256(args.protocol),
        "coverage_report_sha256": sha256(args.coverage_report),
        "analysis_script_sha256": sha256(Path(__file__).resolve()),
        "analysis_type": "retrospective_fixed_protein_sequence_cluster_transport_validation",
        "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "n_measurement_rows": 154,
        "n_exact_cds_groups": 150,
        "n_sequence_clusters": 37,
        "selected_min_identity": 0.90,
        "primary_seed": primary_seed,
        "seeds": seeds,
        "folds_per_seed": 5,
        "model_fits_per_seed": 30,
        "total_model_fits": 300,
        "device": "CPU_ONLY",
        "primary_absolute_performance": primary_metrics,
        "primary_tests": primary_tests,
        "sequence_cluster_ood_mfe_increment_pass": bool(all_pass),
        "scientific_conclusion": "FIXED_PROTEIN_SEQUENCE_CLUSTER_OOD_MFE_INCREMENT_SUPPORTED_RETROSPECTIVELY" if all_pass else "FIXED_PROTEIN_SEQUENCE_CLUSTER_OOD_MFE_INCREMENT_NOT_SUPPORTED",
        "outputs": output_files,
        "scientific_flags": {
            "fixed_protein": True,
            "sequence_cluster_ood": True,
            "protein_ood": False,
            "independent_untouched_confirmation": False,
            "labels_previously_used_in_RK22_development": True,
            "functional_untouched_read": False,
            "velocity_or_decay_measured": False,
            "full_spatial_coupling_established": False,
            "generator_training_authorized": False,
            "RK_G1_complete": False,
        },
    }
    write_json(args.summary, summary)
    print(json.dumps({
        "status": summary["status"],
        "scientific_conclusion": summary["scientific_conclusion"],
        "primary_absolute_performance": primary_metrics,
        "primary_tests": primary_tests,
        "total_model_fits": 300,
        "summary": str(args.summary),
    }, indent=2))


if __name__ == "__main__":
    main()
