#!/usr/bin/env python3
"""RK32 frozen structure-source and coverage comparison on Kudla cluster OOD."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import RNA
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


def atomic_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx = rankdata(np.asarray(x, dtype=float))
    ry = rankdata(np.asarray(y, dtype=float))
    dx = rx - rx.mean()
    dy = ry - ry.mean()
    denominator = float(np.sqrt(np.dot(dx, dx) * np.dot(dy, dy)))
    return float(np.dot(dx, dy) / denominator) if denominator else float("nan")


def make_cluster_folds(labels: np.ndarray, seed: int) -> tuple[np.ndarray, list[int]]:
    labels = np.asarray(labels, dtype=int)
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
    return np.array([assignment[int(c)] for c in labels], dtype=int), loads.tolist()


def mfe(sequence: str) -> float:
    md = RNA.md()
    md.dangles = 0
    md.temperature = 37.0
    value = float(RNA.fold_compound(sequence.replace("T", "U"), md).mfe()[1])
    if not np.isfinite(value) or abs(value) >= 100000:
        raise ValueError("non-finite MFE")
    return value


def fit_predict(model_name: str, features: list[str], train: pd.DataFrame, test: pd.DataFrame, seed: int) -> np.ndarray:
    if model_name == "ridge":
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    elif model_name == "histgb":
        model = HistGradientBoostingRegressor(
            loss="squared_error", learning_rate=0.05, max_iter=200,
            max_leaf_nodes=7, min_samples_leaf=10, l2_regularization=1.0,
            early_stopping=False, random_state=seed,
        )
    else:
        raise ValueError(model_name)
    model.fit(train[features], train["target"])
    prediction = np.asarray(model.predict(test[features]), dtype=float)
    if not np.isfinite(prediction).all():
        raise ValueError("non-finite prediction")
    return prediction


def holm(p_values: list[float]) -> list[float]:
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty(len(p), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    started_wall = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat()
    protocol = json.loads(args.protocol.read_text())
    if protocol["status"] != "FROZEN_BEFORE_RK32_EXPRESSION_ASSOCIATION_OR_MODEL_FIT":
        raise ValueError("protocol is not frozen")
    if sha256(Path(__file__).resolve()) != protocol["code"]["production_script_sha256"]:
        raise ValueError("production script differs from frozen protocol")

    source_path = Path(protocol["inputs"]["main_csv"]["path"])
    preflight_path = Path(protocol["inputs"]["preflight_csv"]["path"])
    coverage_path = Path(protocol["inputs"]["coverage_report"]["path"])
    for key, path in (("main_csv", source_path), ("preflight_csv", preflight_path), ("coverage_report", coverage_path)):
        if sha256(path) != protocol["inputs"][key]["sha256"]:
            raise ValueError(f"input hash mismatch: {key}")
    coverage = json.loads(coverage_path.read_text())
    if coverage["status"] != "PASS_LABEL_FREE_COVERAGE_AUDIT":
        raise ValueError("invalid frozen cluster coverage")

    usecols = [
        "source_row", "seqId", "cds", "protein_aa", "CAI", "log10_expression",
        "mfe_5prime_kcal_mol", "rna_energy_entire_prot_kcal_mol", "cds_sha256",
    ]
    source = pd.read_csv(source_path, usecols=usecols)
    if len(source) != 154:
        raise ValueError("source row count")
    rows = []
    for cds_sha, group in source.groupby("cds_sha256", sort=False):
        if group["cds"].nunique() != 1 or group["protein_aa"].nunique() != 1:
            raise ValueError("non-unique exact-CDS construct")
        for feature in ("CAI", "mfe_5prime_kcal_mol", "rna_energy_entire_prot_kcal_mol"):
            if not np.isfinite(group[feature]).all() or group[feature].nunique(dropna=False) != 1:
                raise ValueError(f"non-constant {feature}")
        cds = str(group["cds"].iloc[0]).upper()
        if len(cds) != 720 or set(cds) - set("ACGT") or hashlib.sha256(cds.encode()).hexdigest() != cds_sha:
            raise ValueError("CDS identity failure")
        sequence = np.array(list(cds))
        rows.append({
            "cds_sha256": cds_sha,
            "first_source_row": int(group["source_row"].min()),
            "source_rows": ";".join(str(int(x)) for x in sorted(group["source_row"])),
            "seqIds": ";".join(str(x) for x in group["seqId"]),
            "n_measurements": len(group),
            "CAI": float(group["CAI"].iloc[0]),
            "gc_cds": float(np.mean((sequence == "G") | (sequence == "C"))),
            "gc3_cds": float(np.mean((sequence[2::3] == "G") | (sequence[2::3] == "C"))),
            "mfe_5prime_kcal_mol": float(group["mfe_5prime_kcal_mol"].iloc[0]),
            "rna_energy_entire_prot_kcal_mol": float(group["rna_energy_entire_prot_kcal_mol"].iloc[0]),
            "target": float(group["log10_expression"].mean()),
            "cds": cds,
        })
    analysis = pd.DataFrame(rows).sort_values("first_source_row").reset_index(drop=True)
    analysis.insert(0, "group_id", [f"g{i:03d}" for i in range(len(analysis))])
    if len(analysis) != 150 or int((analysis["n_measurements"] > 1).sum()) != 4:
        raise ValueError("exact-CDS aggregation mismatch")

    facts_path = Path(coverage["facts_csv"])
    if sha256(facts_path) != coverage["facts_sha256"]:
        raise ValueError("cluster facts hash")
    facts = pd.read_csv(facts_path)
    analysis = analysis.merge(facts[["cds_sha256", "sequence_cluster_id"]], on="cds_sha256", how="left", validate="one_to_one")
    if analysis["sequence_cluster_id"].nunique() != 37 or analysis["sequence_cluster_id"].isna().any():
        raise ValueError("cluster coverage mismatch")
    analysis["sequence_cluster_id"] = analysis["sequence_cluster_id"].astype(int)

    preflight = pd.read_csv(preflight_path)
    if len(preflight) != 150 or preflight["exact_cds_group"].nunique() != 150:
        raise ValueError("preflight rows")
    selected = protocol["structure_coordinates"]
    preflight_columns = [
        "exact_cds_group", selected["vienna_local_column"],
        selected["vienna_full_cds_column"], selected["vienna_full_mrna_column"],
    ]
    analysis = analysis.merge(
        preflight[preflight_columns], left_on="cds_sha256", right_on="exact_cds_group",
        how="left", validate="one_to_one",
    ).drop(columns="exact_cds_group")
    analysis["vienna_local_mfe"] = analysis[selected["vienna_local_column"]]
    analysis["vienna_full_cds_mfe"] = analysis[selected["vienna_full_cds_column"]]
    analysis["vienna_full_mrna_mfe"] = analysis[selected["vienna_full_mrna_column"]]
    analysis["source_vienna_local_abs_delta"] = np.abs(analysis["vienna_local_mfe"] - analysis["mfe_5prime_kcal_mol"])

    mfe300, mfe48min, mfe48mean = [], [], []
    for cds in analysis["cds"]:
        first300 = cds[:300]
        windows = [mfe(first300[i:i + 48]) for i in range(len(first300) - 48 + 1)]
        mfe300.append(mfe(first300))
        mfe48min.append(float(np.min(windows)))
        mfe48mean.append(float(np.mean(windows)))
    analysis["mfe_cds300"] = mfe300
    analysis["mfe_cds48_min"] = mfe48min
    analysis["mfe_cds48_mean"] = mfe48mean
    structure_features = protocol["structure_features"]
    numeric = analysis[["CAI", "gc_cds", "gc3_cds", "target"] + sum(structure_features.values(), [])]
    if not np.isfinite(numeric.to_numpy(float)).all():
        raise ValueError("non-finite analysis matrix")

    args.output_root.mkdir(parents=True, exist_ok=True)
    analysis_path = args.output_root / "analysis_structure_definitions_150.csv"
    analysis.drop(columns="cds").to_csv(analysis_path, index=False)
    simple = protocol["simple_features"]
    feature_sets = {"simple": simple}
    feature_sets.update({arm: simple + features for arm, features in structure_features.items()})
    seeds = protocol["outer_evaluation"]["seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    all_predictions, all_assignments, training_rows = [], [], []
    for seed in seeds:
        folds, loads = make_cluster_folds(analysis["sequence_cluster_id"].to_numpy(int), seed)
        if seed == primary_seed and loads != coverage["selected_coverage"]["primary_seed_fold_sizes"]:
            raise ValueError("primary fold sizes differ from frozen coverage")
        assignment = analysis[["group_id", "cds_sha256", "sequence_cluster_id"]].copy()
        assignment.insert(0, "seed", seed)
        assignment["fold"] = folds
        all_assignments.append(assignment)
        prediction = analysis[["group_id", "cds_sha256", "sequence_cluster_id", "target"]].copy()
        prediction.insert(0, "seed", seed)
        prediction["fold"] = folds
        prediction["null"] = np.nan
        for model_name in ("ridge", "histgb"):
            for label in feature_sets:
                prediction[f"{model_name}_{label}"] = np.nan
        for fold in range(5):
            train = analysis[folds != fold]
            test = analysis[folds == fold]
            if not set(train["sequence_cluster_id"]).isdisjoint(test["sequence_cluster_id"]):
                raise ValueError("cluster leakage")
            test_indices = prediction.index[folds == fold]
            prediction.loc[test_indices, "null"] = float(train["target"].mean())
            for model_name in ("ridge", "histgb"):
                for label, features in feature_sets.items():
                    prediction.loc[test_indices, f"{model_name}_{label}"] = fit_predict(
                        model_name, features, train, test, int(seed + fold),
                    )
            training_rows.append({
                "seed": seed, "fold": fold, "n_train": len(train), "n_test": len(test),
                "n_train_clusters": train["sequence_cluster_id"].nunique(),
                "n_test_clusters": test["sequence_cluster_id"].nunique(),
                "train_target_mean": float(train["target"].mean()),
                "histgb_random_state": int(seed + fold), "model_fits": 2 * len(feature_sets),
                "cluster_leakage": False,
            })
        value_columns = [column for column in prediction if column == "null" or column.startswith("ridge_") or column.startswith("histgb_")]
        if not np.isfinite(prediction[value_columns].to_numpy(float)).all():
            raise ValueError("incomplete OOF predictions")
        all_predictions.append(prediction)

    predictions = pd.concat(all_predictions, ignore_index=True)
    assignments = pd.concat(all_assignments, ignore_index=True)
    training_log = pd.DataFrame(training_rows)
    predictions_path = args.output_root / "oof_predictions.csv"
    assignments_path = args.output_root / "fold_assignments.csv"
    training_path = args.output_root / "training_log.csv"
    predictions.to_csv(predictions_path, index=False)
    assignments.to_csv(assignments_path, index=False)
    training_log.to_csv(training_path, index=False)

    seed_metric_rows, seed_effect_rows = [], []
    test_names = [f"{model}__{arm}__{metric}" for model in ("ridge", "histgb") for arm in structure_features for metric in ("spearman_effect", "mse_improvement")]
    for seed in seeds:
        current = predictions[predictions["seed"] == seed]
        y = current["target"].to_numpy(float)
        for column in [column for column in current if column == "null" or column.startswith("ridge_") or column.startswith("histgb_")]:
            pred = current[column].to_numpy(float)
            seed_metric_rows.append({"seed": seed, "arm": column, "spearman": spearman(y, pred), "mse": float(np.mean((y - pred) ** 2))})
        for model in ("ridge", "histgb"):
            simple_pred = current[f"{model}_simple"].to_numpy(float)
            for arm in structure_features:
                structure_pred = current[f"{model}_{arm}"].to_numpy(float)
                seed_effect_rows.append({"seed": seed, "test": f"{model}__{arm}__spearman_effect", "effect": spearman(y, structure_pred) - spearman(y, simple_pred)})
                seed_effect_rows.append({"seed": seed, "test": f"{model}__{arm}__mse_improvement", "effect": float(np.mean((y - simple_pred) ** 2 - (y - structure_pred) ** 2))})
    seed_metrics = pd.DataFrame(seed_metric_rows)
    seed_effects = pd.DataFrame(seed_effect_rows)
    seed_metrics_path = args.output_root / "seed_metrics.csv"
    seed_effects_path = args.output_root / "seed_effects.csv"
    seed_metrics.to_csv(seed_metrics_path, index=False)
    seed_effects.to_csv(seed_effects_path, index=False)

    primary = predictions[predictions["seed"] == primary_seed].reset_index(drop=True)
    y = primary["target"].to_numpy(float)
    cluster_ids = primary["sequence_cluster_id"].to_numpy(int)
    unique_clusters = np.array(sorted(np.unique(cluster_ids)), dtype=int)
    cluster_index = np.searchsorted(unique_clusters, cluster_ids)
    cluster_rows = [np.flatnonzero(cluster_index == i) for i in range(len(unique_clusters))]
    inference = protocol["primary_inference"]
    resamples = int(inference["resamples"])
    boot_clusters = np.random.default_rng(inference["bootstrap_seed"]).integers(0, len(unique_clusters), size=(resamples, len(unique_clusters)), dtype=np.int16)
    perm_signs = np.random.default_rng(inference["permutation_seed"]).choice(np.array([-1, 1], dtype=np.int8), size=(resamples, len(unique_clusters)))
    observed = {name: 0.0 for name in test_names}
    boot = {name: np.empty(resamples, dtype=float) for name in test_names}
    null = {name: np.empty(resamples, dtype=float) for name in test_names}
    pair_values = {}
    for model in ("ridge", "histgb"):
        simple_pred = primary[f"{model}_simple"].to_numpy(float)
        for arm in structure_features:
            structure_pred = primary[f"{model}_{arm}"].to_numpy(float)
            sp_name = f"{model}__{arm}__spearman_effect"
            mse_name = f"{model}__{arm}__mse_improvement"
            observed[sp_name] = spearman(y, structure_pred) - spearman(y, simple_pred)
            diff = (y - simple_pred) ** 2 - (y - structure_pred) ** 2
            observed[mse_name] = float(diff.mean())
            null[mse_name] = (perm_signs[:, cluster_index] * diff).mean(axis=1)
            pair_values[(model, arm)] = (simple_pred, structure_pred, diff)

    for b in range(resamples):
        selected_clusters = boot_clusters[b]
        row_index = np.concatenate([cluster_rows[int(c)] for c in selected_clusters])
        weights = np.bincount(selected_clusters, minlength=len(unique_clusters))[cluster_index].astype(float)
        signs = perm_signs[b, cluster_index] < 0
        for model in ("ridge", "histgb"):
            for arm in structure_features:
                simple_pred, structure_pred, diff = pair_values[(model, arm)]
                sp_name = f"{model}__{arm}__spearman_effect"
                mse_name = f"{model}__{arm}__mse_improvement"
                boot[sp_name][b] = spearman(y[row_index], structure_pred[row_index]) - spearman(y[row_index], simple_pred[row_index])
                boot[mse_name][b] = float(np.dot(weights, diff) / weights.sum())
                swapped_simple = np.where(signs, structure_pred, simple_pred)
                swapped_structure = np.where(signs, simple_pred, structure_pred)
                null[sp_name][b] = spearman(y, swapped_structure) - spearman(y, swapped_simple)

    primary_tests = []
    for name in test_names:
        if not np.isfinite(boot[name]).all() or not np.isfinite(null[name]).all():
            raise ValueError(f"non-finite inference: {name}")
        obs = float(observed[name])
        primary_tests.append({
            "test": name,
            "observed_effect": obs,
            "ci95": [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))],
            "p_cluster_swap": float((1 + np.sum(np.abs(null[name]) >= abs(obs))) / (resamples + 1)),
            "bootstrap_median": float(np.median(boot[name])),
        })
    adjusted = holm([row["p_cluster_swap"] for row in primary_tests])
    for row, p_holm in zip(primary_tests, adjusted):
        effects = seed_effects[seed_effects["test"] == row["test"]].sort_values("seed")["effect"].to_numpy(float)
        row.update({
            "p_holm": p_holm,
            "seed_effects": effects.tolist(),
            "positive_seeds": int(np.sum(effects > 0)),
            "mean_seed_effect": float(effects.mean()),
            "median_seed_effect": float(np.median(effects)),
        })
        row["pass"] = bool(row["observed_effect"] > 0 and row["ci95"][0] > 0 and p_holm < 0.05 and row["positive_seeds"] >= 8)
    arm_results = []
    for arm in structure_features:
        rows = [row for row in primary_tests if row["test"].split("__")[1] == arm]
        arm_results.append({"arm": arm, "n_tests": len(rows), "n_pass": sum(row["pass"] for row in rows), "all_four_pass": all(row["pass"] for row in rows)})
    n_supported = sum(row["all_four_pass"] for row in arm_results)
    if n_supported == len(structure_features):
        conclusion = "ALL_STRUCTURE_DEFINITIONS_SUPPORTED_RETROSPECTIVELY"
    elif n_supported:
        conclusion = "STRUCTURE_INCREMENT_DEFINITION_DEPENDENT_RETROSPECTIVELY"
    else:
        conclusion = "NO_STRUCTURE_DEFINITION_SUPPORTED_RETROSPECTIVELY"

    arrays = {f"bootstrap__{name}": values for name, values in boot.items()}
    arrays.update({f"permutation__{name}": values for name, values in null.items()})
    arrays["bootstrap_cluster_indices"] = boot_clusters
    arrays["permutation_cluster_signs"] = perm_signs
    arrays_path = args.output_root / "primary_inference_arrays.npz"
    np.savez_compressed(arrays_path, **arrays)
    primary_metrics = []
    for row in seed_metrics[seed_metrics["seed"] == primary_seed].drop(columns="seed").to_dict("records"):
        primary_metrics.append({
            key: (None if isinstance(value, float) and not np.isfinite(value) else value)
            for key, value in row.items()
        })
    output_files = {}
    for path in (analysis_path, assignments_path, predictions_path, training_path, seed_metrics_path, seed_effects_path, arrays_path):
        output_files[path.name] = {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}
    summary = {
        "schema": "a8-rk32-structure-definition-result-v1",
        "status": "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION",
        "protocol": str(args.protocol), "protocol_sha256": sha256(args.protocol),
        "analysis_script_sha256": sha256(Path(__file__).resolve()),
        "analysis_type": "retrospective_outcome_known_followup_not_independent_confirmation",
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "component_wall_seconds": float(time.perf_counter() - started_wall),
        "n_measurement_rows": 154, "n_exact_cds_groups": 150, "n_sequence_clusters": 37,
        "primary_seed": primary_seed, "seeds": seeds, "folds_per_seed": 5,
        "structure_arms": structure_features,
        "model_fits_per_fold": 2 * len(feature_sets), "total_model_fits": len(seeds) * 5 * 2 * len(feature_sets),
        "primary_absolute_performance": primary_metrics, "primary_tests": primary_tests,
        "arm_results": arm_results, "n_structure_arms_all_four_pass": n_supported,
        "scientific_conclusion": conclusion, "outputs": output_files,
        "scientific_flags": {
            "same_frozen_37_clusters_and_folds": True, "expression_outcome_previously_known": True,
            "independent_untouched_confirmation": False, "functional_untouched_read": False,
            "protein_ood": False, "full_external_sota": False, "RK_G1_complete": False,
        },
    }
    atomic_json(args.summary, summary)
    print(json.dumps({
        "status": summary["status"], "scientific_conclusion": conclusion,
        "arm_results": arm_results, "primary_tests": primary_tests,
        "total_model_fits": summary["total_model_fits"], "summary": str(args.summary),
    }, indent=2))


if __name__ == "__main__":
    main()
