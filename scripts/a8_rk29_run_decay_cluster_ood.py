#!/usr/bin/env python3
"""A8-RK29 frozen iCodon protein-cluster OOD production analysis.

The protocol, coverage report, and this implementation are committed before
--authorize-outcome-read is used. No functional-untouched data are accessed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy.stats import rankdata
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

import a8_rk29_label_free_coverage as cov


def sha256(path):
    return cov.sha256(path)


def write_json(path, value):
    cov.write_json(Path(path), value)


def spearman(x, y):
    rx, ry = rankdata(np.asarray(x, float)), rankdata(np.asarray(y, float))
    dx, dy = rx - rx.mean(), ry - ry.mean()
    denominator = float(np.sqrt(np.dot(dx, dx) * np.dot(dy, dy)))
    return float("nan") if denominator == 0 else float(np.dot(dx, dy) / denominator)


def pearson(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    dx, dy = x - x.mean(), y - y.mean()
    denominator = float(np.sqrt(np.dot(dx, dx) * np.dot(dy, dy)))
    return float("nan") if denominator == 0 else float(np.dot(dx, dy) / denominator)


def holm_adjust(p_values):
    p = np.asarray(p_values, dtype=float)
    assert p.shape == (4,) and np.isfinite(p).all()
    order = np.argsort(p)
    adjusted = np.empty(4, dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (4 - rank) * p[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def make_cluster_folds(cluster_labels, seed, n_folds=5):
    return cov.make_cluster_folds(cluster_labels, seed, n_folds)


def assign_outcome_names(outcome, geo, timepoint_map):
    """Match S6 rows to unique GEO names using canonical metadata and 9 vectors."""
    outcome = outcome.copy().reset_index(drop=True)
    geo = geo.copy().reset_index(drop=True)
    canonical = [cov.canonical_metadata(str(name)) for name in geo["Name"]]
    geo["canonical_protein"] = [x[0] for x in canonical]
    geo["canonical_group"] = [x[1] for x in canonical]
    assigned_names, matched_rows, max_differences = [], [], []
    for row in outcome.to_dict("records"):
        candidates = geo[(geo["canonical_protein"] == row["Protein_id"]) & (geo["canonical_group"] == row["Group"])]
        if candidates.empty:
            raise RuntimeError(f"no canonical GEO candidates for {row['Protein_id']} {row['Group']}")
        mask = np.ones(len(candidates), dtype=bool)
        for geo_column, outcome_column in timepoint_map.items():
            left = candidates[geo_column].to_numpy(float)
            right = float(row[outcome_column])
            mask &= np.isclose(left, right, atol=1e-12, rtol=0.0)
        matched = candidates[mask]
        names = sorted(set(matched["Name"].astype(str)))
        if len(names) != 1:
            raise RuntimeError(f"ambiguous or missing measurement join for {row['Protein_id']} {row['Group']}: {names}")
        assigned_names.append(names[0])
        matched_rows.append(matched.iloc[0])
        matched_difference = max(float(np.max(np.abs(matched[geo_column].to_numpy(float) - float(row[outcome_column])))) for geo_column, outcome_column in timepoint_map.items())
        max_differences.append(matched_difference)
    if len(set(assigned_names)) != len(assigned_names):
        raise RuntimeError("S6-to-GEO assignment is not one-to-one")
    matched_geo = pd.DataFrame(matched_rows).reset_index(drop=True)
    result = outcome.copy()
    result["Name"] = assigned_names
    for geo_column in timepoint_map:
        result[geo_column] = matched_geo[geo_column].to_numpy(float)
    diagnostics = {
        "n_s6_rows": len(outcome), "n_geo_source_rows": len(geo),
        "n_unique_assigned_names": len(set(assigned_names)),
        "n_geo_rows_used": len(matched_geo), "n_geo_redundant_rows_not_used": len(geo) - len(matched_geo),
        "max_abs_timepoint_difference": float(max(max_differences, default=0.0)),
        "geo_auxiliary_protein_group_columns_used": False,
        "join_rule": "canonical FASTA-derived metadata plus all nine numeric vectors; unique Name and one-to-one assignment",
    }
    return result, diagnostics


def load_authorized_analysis(protocol, coverage):
    outcome_columns = ["Protein_id", "Group"] + list(protocol["outcome_access"]["geo_to_outcome_timepoint_map"].values()) + ["Decay_rate", "Predicted_mRNA_stability"]
    _, _, outcome_records = cov.read_xlsx_selected(protocol["inputs"]["outcome_xlsx"]["path"], outcome_columns)
    outcome = pd.DataFrame(outcome_records)
    geo = pd.read_csv(protocol["inputs"]["geo_perfect_csv_gz"]["path"])
    assert len(outcome) == 955 and len(geo) == 10227
    mapped, alignment = assign_outcome_names(outcome, geo, protocol["outcome_access"]["geo_to_outcome_timepoint_map"])
    facts_path = Path(coverage["facts_tsv"])
    assert sha256(facts_path) == coverage["facts_sha256"]
    facts = pd.read_csv(facts_path, sep="\t")
    assert len(facts) == 950 and facts["Name"].is_unique
    analysis = facts.merge(mapped, on="Name", how="left", validate="one_to_one", suffixes=("_canonical", "_s6"))
    assert len(analysis) == 950 and analysis["Decay_rate"].notna().all()
    assert (analysis["Protein_id_canonical"] == analysis["Protein_id_s6"]).all()
    assert (analysis["Group_canonical"] == analysis["Group_s6"]).all()
    analysis = analysis.rename(columns={"Protein_id_canonical": "Protein_id", "Group_canonical": "Group", "Decay_rate": "target", "Predicted_mRNA_stability": "icodon_score"})
    fasta = cov.read_fasta_gz(protocol["inputs"]["reference_fasta_gz"]["path"])
    structure_path = Path(coverage["structure_features_tsv"])
    assert sha256(structure_path) == coverage["structure_features_sha256"]
    structure = pd.read_csv(structure_path, sep="\t")
    assert len(structure) == 950 and structure["Name"].is_unique
    analysis = analysis.merge(structure, on="Name", how="left", validate="one_to_one")
    constant5 = protocol["sequence_definition"]["constant_5prime"]
    variable_length = protocol["sequence_definition"]["variable_length_nt"]
    feature_rows = []
    for row in analysis.to_dict("records"):
        full = fasta[row["Name"]]
        assert hashlib.sha256(full.encode()).hexdigest() == row["full_cds_sha256"]
        variable = full[len(constant5):len(constant5) + variable_length]
        feature_rows.append(simple_features(variable, row["Group"]))
    analysis = pd.concat([analysis.reset_index(drop=True), pd.DataFrame(feature_rows)], axis=1)
    analysis["target"] = analysis["target"].astype(float)
    analysis["icodon_score"] = analysis["icodon_score"].astype(float)
    analysis["evaluation_group_id"] = analysis["evaluation_group_id"].astype(int)
    analysis["primary_seed_fold"] = analysis["primary_seed_fold"].astype(int)
    assert np.isfinite(analysis[["target", "icodon_score"] + protocol["features"]["structure_addition"]].to_numpy(float)).all()
    return analysis, alignment


def simple_features(variable, design_group):
    codons = [variable[i:i + 3] for i in range(0, len(variable), 3)]
    assert len(codons) == 99
    translation = cov.translate(variable)
    assert "*" not in translation
    result = {}
    for codon in sorted(c for c, aa in cov.CODON_TABLE.items() if aa != "*"):
        result[f"codon__{codon}"] = codons.count(codon) / len(codons)
    for amino_acid in "ACDEFGHIKLMNPQRSTVWY":
        result[f"aa__{amino_acid}"] = translation.count(amino_acid) / len(translation)
    result["gc"] = (variable.count("G") + variable.count("C")) / len(variable)
    result["gc3"] = sum(c[2] in "GC" for c in codons) / len(codons)
    result["cpg_per_nt"] = variable.count("CG") / len(variable)
    result["upa_per_nt"] = variable.count("TA") / len(variable)
    for group in ["iCodon_1", "iCodon_2", "iCodon_3", "iCodon_4", "iCodon_5", "IDT", "Genewiz"]:
        result[f"design__{group}"] = float(design_group == group)
    return result


def feature_sets(protocol, analysis):
    icodon = ["icodon_score"]
    simple = icodon + sorted(c for c in analysis.columns if c.startswith("codon__") or c.startswith("aa__") or c.startswith("design__")) + ["gc", "gc3", "cpg_per_nt", "upa_per_nt"]
    assert len(simple) == 93, len(simple)
    structure_addition = list(protocol["features"]["structure_addition"])
    return {"icodon": icodon, "simple": simple, "structure": simple + structure_addition, "mfe_only": structure_addition}


def slope(time_values, abundance_values):
    x, y = np.asarray(time_values, float), np.asarray(abundance_values, float)
    dx = x - x.mean()
    return float(np.dot(dx, y - y.mean()) / np.dot(dx, dx))


def first_order_diagnostics(mapped, protocol):
    time_map = protocol["outcome_access"]["geo_to_outcome_timepoint_map"]
    geo_columns = list(time_map)
    abundance = mapped[geo_columns].to_numpy(float)
    assert abundance.ndim == 2 and abundance.shape[0] >= 2 and abundance.shape[1] == 9 and np.isfinite(abundance).all() and (abundance > 0).all()
    times = np.array(protocol["outcome_access"]["decay_recompute_diagnostic"]["time_hpi"], float)
    target = mapped["Decay_rate"].to_numpy(float)
    estimators = {name: [] for name in protocol["outcome_access"]["decay_recompute_diagnostic"]["candidate_estimators"]}
    for row in abundance:
        matrix = row.reshape(3, 3)
        for base_name, log in [("ln", np.log), ("log2", np.log2)]:
            estimators[f"all_nine_points_{base_name}"].append(slope(np.repeat(times, 3), log(row)))
            estimators[f"timepoint_mean_abundance_{base_name}"].append(slope(times, log(matrix.mean(axis=1))))
            estimators[f"timepoint_mean_log_abundance_{base_name}"].append(slope(times, log(matrix).mean(axis=1)))
    correlations = {name: pearson(target, values) for name, values in estimators.items()}
    best = max(correlations, key=lambda name: abs(correlations[name]))
    assert abs(correlations[best]) >= protocol["outcome_access"]["decay_recompute_diagnostic"]["minimum_absolute_pearson_with_published_decay"]
    return {"candidate_pearson_with_published_decay": correlations, "best_diagnostic": best, "best_absolute_pearson": abs(correlations[best]), "published_target_unchanged": True}


def fit_predict(model_name, feature_names, train, test, random_state):
    x_train = train[feature_names].to_numpy(float)
    x_test = test[feature_names].to_numpy(float)
    y_train = train["target"].to_numpy(float)
    if model_name == "ridge":
        xm, xs = x_train.mean(axis=0), x_train.std(axis=0, ddof=0)
        xs = np.where(xs <= 0, 1.0, xs)
        ym, ys = float(y_train.mean()), float(y_train.std(ddof=0))
        assert ys > 0
        model = Ridge(alpha=1.0, solver="cholesky")
        model.fit((x_train - xm) / xs, (y_train - ym) / ys)
        prediction = model.predict((x_test - xm) / xs) * ys + ym
    elif model_name == "histgb":
        model = HistGradientBoostingRegressor(loss="squared_error", learning_rate=0.05, max_iter=200, max_leaf_nodes=7, min_samples_leaf=10, l2_regularization=1.0, early_stopping=False, random_state=random_state)
        model.fit(x_train, y_train)
        prediction = model.predict(x_test)
    else:
        raise ValueError(model_name)
    prediction = np.asarray(prediction, dtype=float)
    assert np.isfinite(prediction).all()
    return prediction


def metric_rows_for_seed(predictions, seed, arms):
    y = predictions["target"].to_numpy(float)
    rows = [{"seed": seed, "arm": arm, "spearman": spearman(y, predictions[arm]), "mse": float(np.mean((y - predictions[arm].to_numpy(float)) ** 2))} for arm in arms]
    effects = {}
    for model in ["ridge", "histgb"]:
        simple = predictions[f"{model}_simple"].to_numpy(float)
        structure = predictions[f"{model}_structure"].to_numpy(float)
        effects[f"{model}_spearman_effect"] = spearman(y, structure) - spearman(y, simple)
        effects[f"{model}_mse_improvement"] = float(np.mean((y - simple) ** 2) - np.mean((y - structure) ** 2))
    return rows, effects


def swap_arms(simple, structure, swap_mask):
    simple, structure, mask = np.asarray(simple, float), np.asarray(structure, float), np.asarray(swap_mask, bool)
    return np.where(mask, structure, simple), np.where(mask, simple, structure)


def primary_inference(primary, cluster_ids, bootstrap_seed, permutation_seed, resamples):
    y = primary["target"].to_numpy(float)
    unique_clusters = np.array(sorted(np.unique(cluster_ids).tolist()), dtype=int)
    assert len(unique_clusters) >= 10
    cluster_index = np.searchsorted(unique_clusters, cluster_ids)
    cluster_rows = [np.flatnonzero(cluster_index == i) for i in range(len(unique_clusters))]
    boot_clusters = np.random.default_rng(bootstrap_seed).integers(0, len(unique_clusters), size=(resamples, len(unique_clusters)), dtype=np.int16)
    perm_signs = np.random.default_rng(permutation_seed).choice(np.array([-1, 1], dtype=np.int8), size=(resamples, len(unique_clusters)))
    tests = ["ridge_spearman_effect", "ridge_mse_improvement", "histgb_spearman_effect", "histgb_mse_improvement"]
    observed, boot, null, arms = {}, {}, {}, {}
    for name in tests:
        boot[name], null[name] = np.empty(resamples, float), np.empty(resamples, float)
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
        signs = perm_signs[b, cluster_index] < 0
        for model, (simple, structure) in arms.items():
            sp_name, mse_name = f"{model}_spearman_effect", f"{model}_mse_improvement"
            boot[sp_name][b] = spearman(y[row_index], structure[row_index]) - spearman(y[row_index], simple[row_index])
            diff = (y - simple) ** 2 - (y - structure) ** 2
            boot[mse_name][b] = float(np.dot(weights, diff) / weights.sum())
            swapped_simple, swapped_structure = swap_arms(simple, structure, signs)
            null[sp_name][b] = spearman(y, swapped_structure) - spearman(y, swapped_simple)
    p_values, results = [], []
    for name in tests:
        assert np.isfinite(boot[name]).all() and np.isfinite(null[name]).all()
        observed_value = float(observed[name])
        p = float((1 + np.sum(np.abs(null[name]) >= abs(observed_value))) / (resamples + 1))
        p_values.append(p)
        results.append({"test": name, "observed_effect": observed_value, "ci95": [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))], "p_cluster_swap": p, "bootstrap_median": float(np.median(boot[name]))})
    for row, adjusted in zip(results, holm_adjust(p_values)):
        row["p_holm"] = adjusted
    arrays = {f"bootstrap__{name}": boot[name] for name in tests}
    arrays.update({f"permutation__{name}": null[name] for name in tests})
    arrays["bootstrap_cluster_indices"] = boot_clusters
    arrays["permutation_cluster_signs"] = perm_signs
    return results, arrays


def secondary_descriptive(primary):
    arms = [c for c in primary.columns if c.startswith("ridge_") or c.startswith("histgb_")]
    within, top1 = [], []
    for arm in arms:
        correlations = []
        regrets = []
        for _, group in primary.groupby("Protein_id", sort=True):
            y = group["target"].to_numpy(float)
            pred = group[arm].to_numpy(float)
            correlation = spearman(y, pred)
            if np.isfinite(correlation):
                correlations.append(correlation)
            regrets.append(float(y.max() - y[np.argmax(pred)]))
        within.append({"arm": arm, "n_proteins": len(correlations), "mean_within_protein_spearman": float(np.mean(correlations)), "median_within_protein_spearman": float(np.median(correlations))})
        top1.append({"arm": arm, "n_proteins": len(regrets), "mean_top1_regret": float(np.mean(regrets)), "median_top1_regret": float(np.median(regrets)), "max_top1_regret": float(np.max(regrets))})
    return {"within_protein_spearman": within, "top1_design_regret": top1, "confirmatory": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--coverage-report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--authorize-outcome-read", action="store_true")
    args = parser.parse_args()
    assert args.authorize_outcome_read, "explicit outcome authorization is required"
    wall_start = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat()
    protocol = json.loads(args.protocol.read_text())
    coverage = json.loads(args.coverage_report.read_text())
    assert protocol["schema"] == "a8-rk29-icodon-decay-cluster-ood-protocol-v1"
    assert coverage["status"] == "PASS_LABEL_FREE_COVERAGE_AUDIT_FEASIBLE"
    assert coverage["protocol_sha256"] == sha256(args.protocol)
    assert coverage["outcome_values_accessed"] is False and coverage["expression_or_model_fit_performed"] is False
    for spec in protocol["inputs"].values():
        assert sha256(spec["path"]) == spec["sha256"]
    args.output_root.mkdir(parents=True, exist_ok=True)

    mapped, alignment = load_authorized_analysis(protocol, coverage)
    # Reconstruct the complete mapped table for the prespecified decay diagnostic.
    outcome_columns = ["Protein_id", "Group"] + list(protocol["outcome_access"]["geo_to_outcome_timepoint_map"].values()) + ["Decay_rate", "Predicted_mRNA_stability"]
    _, _, all_outcome_records = cov.read_xlsx_selected(protocol["inputs"]["outcome_xlsx"]["path"], outcome_columns)
    all_geo = pd.read_csv(protocol["inputs"]["geo_perfect_csv_gz"]["path"])
    all_mapped, second_alignment = assign_outcome_names(pd.DataFrame(all_outcome_records), all_geo, protocol["outcome_access"]["geo_to_outcome_timepoint_map"])
    assert alignment == second_alignment
    decay_diagnostic = first_order_diagnostics(all_mapped, protocol)
    analysis = mapped
    assert analysis["target"].nunique() >= protocol["outcome_access"]["dynamic_range_gate"]["min_unique_values"]
    target_iqr = float(analysis["target"].quantile(0.75) - analysis["target"].quantile(0.25))
    assert target_iqr > 0
    analysis_path = args.output_root / "analysis_variants_950.csv"
    analysis.to_csv(analysis_path, index=False)

    sets = feature_sets(protocol, analysis)
    arms = protocol["models"]["arms"]
    seeds = protocol["outer_evaluation"]["sensitivity_seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    all_predictions, fold_rows, seed_metric_rows, seed_effect_rows, training_rows = [], [], [], [], []
    for seed in seeds:
        folds, loads = make_cluster_folds(analysis["evaluation_group_id"].to_numpy(int), seed)
        if seed == primary_seed:
            assert loads == coverage["selected_coverage"]["primary_seed_fold_sizes"]
            assert np.array_equal(folds, analysis["primary_seed_fold"].to_numpy(int))
        assignment = analysis[["Name", "Protein_id", "evaluation_group_id"]].copy()
        assignment.insert(0, "seed", seed)
        assignment["fold"] = folds
        fold_rows.append(assignment)
        seed_predictions = analysis[["Name", "Protein_id", "Group_s6", "evaluation_group_id", "target"]].copy()
        seed_predictions.insert(0, "seed", seed)
        seed_predictions["fold"] = folds
        for arm in arms:
            seed_predictions[arm] = np.nan
        for fold in range(5):
            train = analysis[folds != fold].copy()
            test = analysis[folds == fold].copy()
            assert set(train["evaluation_group_id"]).isdisjoint(set(test["evaluation_group_id"]))
            assert train["target"].std(ddof=0) > 0
            test_index = np.flatnonzero(folds == fold)
            seed_predictions.loc[seed_predictions.index[test_index], "null"] = float(train["target"].mean())
            for model_name in ["ridge", "histgb"]:
                for label, names in sets.items():
                    arm = f"{model_name}_{label}"
                    seed_predictions.loc[seed_predictions.index[test_index], arm] = fit_predict(model_name, names, train, test, seed + fold)
            training_rows.append({"seed": seed, "fold": fold, "n_train": len(train), "n_test": len(test), "n_train_groups": train["evaluation_group_id"].nunique(), "n_test_groups": test["evaluation_group_id"].nunique(), "train_target_mean": float(train["target"].mean()), "train_target_sd": float(train["target"].std(ddof=0)), "histgb_random_state": seed + fold, "model_fits": 8, "cluster_leakage": False})
        assert np.isfinite(seed_predictions[arms].to_numpy(float)).all()
        all_predictions.append(seed_predictions)
        metrics, effects = metric_rows_for_seed(seed_predictions, seed, arms)
        seed_metric_rows.extend(metrics)
        for name, effect in effects.items():
            seed_effect_rows.append({"seed": seed, "test": name, "effect": effect})

    predictions = pd.concat(all_predictions, ignore_index=True)
    assignments = pd.concat(fold_rows, ignore_index=True)
    training_log = pd.DataFrame(training_rows)
    seed_metrics = pd.DataFrame(seed_metric_rows)
    seed_effects = pd.DataFrame(seed_effect_rows)
    paths = {
        "assignments": args.output_root / "fold_assignments.csv", "predictions": args.output_root / "oof_predictions.csv",
        "training": args.output_root / "training_log.csv", "metrics": args.output_root / "seed_metrics.csv", "effects": args.output_root / "seed_effects.csv",
    }
    assignments.to_csv(paths["assignments"], index=False)
    predictions.to_csv(paths["predictions"], index=False)
    training_log.to_csv(paths["training"], index=False)
    seed_metrics.to_csv(paths["metrics"], index=False)
    seed_effects.to_csv(paths["effects"], index=False)

    primary = predictions[predictions["seed"] == primary_seed].reset_index(drop=True)
    assert len(primary) == 950
    inf = protocol["primary_inference"]
    primary_tests, arrays = primary_inference(primary, primary["evaluation_group_id"].to_numpy(int), inf["cluster_bootstrap"]["seed"], inf["cluster_swap_permutation"]["seed"], inf["cluster_bootstrap"]["resamples"])
    arrays_path = args.output_root / "primary_inference_arrays.npz"
    np.savez_compressed(arrays_path, **arrays)
    all_pass = True
    for test in primary_tests:
        effects = seed_effects[seed_effects["test"] == test["test"]].sort_values("seed")["effect"].to_numpy(float)
        test.update({"seed_effects": effects.tolist(), "positive_seeds": int(np.sum(effects > 0)), "mean_seed_effect": float(effects.mean()), "median_seed_effect": float(np.median(effects))})
        test["pass"] = bool(test["observed_effect"] > 0 and test["ci95"][0] > 0 and test["p_holm"] < inf["alpha"] and test["positive_seeds"] >= 8)
        all_pass = all_pass and test["pass"]
    secondary = secondary_descriptive(primary)
    primary_group_metrics = []
    for group, frame in primary.groupby("Group_s6", sort=True):
        for arm in arms:
            primary_group_metrics.append({"Group": group, "n": len(frame), "arm": arm, "spearman": spearman(frame["target"], frame[arm]), "mse": float(np.mean((frame["target"] - frame[arm]) ** 2))})
    design_metrics_path = args.output_root / "primary_design_group_metrics.csv"
    pd.DataFrame(primary_group_metrics).to_csv(design_metrics_path, index=False)
    output_files = {}
    for path in [analysis_path, *paths.values(), arrays_path, design_metrics_path]:
        output_files[path.name] = {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}
    summary = {
        "schema": "a8-rk29-icodon-decay-cluster-ood-result-v1", "status": "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION",
        "protocol": str(args.protocol), "protocol_sha256": sha256(args.protocol), "coverage_report_sha256": sha256(args.coverage_report),
        "analysis_script_sha256": sha256(Path(__file__).resolve()), "coverage_script_sha256": sha256(Path(cov.__file__).resolve()),
        "inputs": {key: {"path": spec["path"], "sha256": spec["sha256"]} for key, spec in protocol["inputs"].items()},
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": float(time.perf_counter() - wall_start),
        "source_alignment": alignment, "decay_recompute_diagnostic": decay_diagnostic,
        "n_source_variants": 955, "n_variants": len(analysis), "n_excluded_low_coverage_variants": 5,
        "n_proteins": analysis["Protein_id"].nunique(), "n_evaluation_groups": analysis["evaluation_group_id"].nunique(),
        "target_qc": {"unique_values": int(analysis["target"].nunique()), "iqr": target_iqr, "min": float(analysis["target"].min()), "max": float(analysis["target"].max())},
        "primary_seed": primary_seed, "seeds": seeds, "folds_per_seed": 5, "model_fits_per_seed": 40, "total_model_fits": 400, "device": "CPU_ONLY",
        "primary_absolute_performance": seed_metrics[seed_metrics["seed"] == primary_seed].drop(columns=["seed"]).to_dict("records"),
        "primary_tests": primary_tests, "secondary_descriptive": secondary,
        "sequence_cluster_ood_structure_increment_pass": bool(all_pass),
        "scientific_conclusion": protocol["result_interpretation"]["pass"] if all_pass else protocol["result_interpretation"]["fail"],
        "outputs": output_files,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__, "ViennaRNA": cov.RNA.__version__},
        "scientific_flags": protocol["scientific_boundaries"], "functional_untouched_read": False, "expensive_generative_training_performed": False,
    }
    write_json(args.summary, summary)
    print(json.dumps({"status": summary["status"], "scientific_conclusion": summary["scientific_conclusion"], "n_variants": len(analysis), "n_proteins": analysis["Protein_id"].nunique(), "source_alignment": alignment, "decay_recompute_diagnostic": decay_diagnostic, "primary_absolute_performance": summary["primary_absolute_performance"], "primary_tests": primary_tests, "total_model_fits": 400, "elapsed_seconds": summary["elapsed_seconds"], "summary": str(args.summary)}, indent=2))


if __name__ == "__main__":
    main()
