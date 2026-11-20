#!/usr/bin/env python3
"""RK28 fixed-GFP HEK293 observed-R1 sequence-cluster OOD production analysis.

The protocol and label-free coverage are frozen in commit 52d270e6 before this
script reads outcomes. All model fits are CPU-only; no untouched data are read.
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

import a8_rk02_mordstein_structure_increment as rk02


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def spearman(x, y):
    rx = rankdata(np.asarray(x, dtype=float))
    ry = rankdata(np.asarray(y, dtype=float))
    dx, dy = rx - rx.mean(), ry - ry.mean()
    denom = float(np.sqrt(np.dot(dx, dx) * np.dot(dy, dy)))
    return float("nan") if denom == 0 else float(np.dot(dx, dy) / denom)


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
    labels = np.asarray(cluster_labels, dtype=int)
    ids = np.array(sorted(np.unique(labels).tolist()), dtype=int)
    rng = np.random.default_rng(seed)
    shuffled = ids[rng.permutation(len(ids))].tolist()
    sizes = {int(c): int(np.sum(labels == c)) for c in ids}
    ordered = sorted(shuffled, key=lambda c: -sizes[int(c)])
    loads = np.zeros(n_folds, dtype=int)
    assignment = {}
    for cluster in ordered:
        candidates = np.flatnonzero(loads == loads.min())
        fold = int(rng.choice(candidates))
        assignment[int(cluster)] = fold
        loads[fold] += sizes[int(cluster)]
    folds = np.array([assignment[int(c)] for c in labels], dtype=int)
    return folds, loads.tolist()


def fit_predict(model_name, feature_names, train, test, random_state):
    x_train = train[feature_names].to_numpy(float)
    x_test = test[feature_names].to_numpy(float)
    y_train = train["target"].to_numpy(float)
    if model_name == "ridge":
        xm, xs = x_train.mean(axis=0), x_train.std(axis=0, ddof=0)
        ym, ys = float(y_train.mean()), float(y_train.std(ddof=0))
        if np.any(xs <= 0) or ys <= 0:
            raise RuntimeError("degenerate training-fold scaling")
        model = Ridge(alpha=1.0, solver="cholesky")
        model.fit((x_train - xm) / xs, (y_train - ym) / ys)
        prediction = model.predict((x_test - xm) / xs) * ys + ym
    elif model_name == "histgb":
        model = HistGradientBoostingRegressor(
            loss="squared_error", learning_rate=0.05, max_iter=200,
            max_leaf_nodes=7, min_samples_leaf=10, l2_regularization=1.0,
            early_stopping=False, random_state=random_state,
        )
        model.fit(x_train, y_train)
        prediction = model.predict(x_test)
    else:
        raise ValueError(model_name)
    prediction = np.asarray(prediction, dtype=float)
    assert np.isfinite(prediction).all()
    return prediction


def metric_rows_for_seed(predictions, seed):
    y = predictions["target"].to_numpy(float)
    metric_rows = []
    arms = ["null", "ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"]
    for arm in arms:
        pred = predictions[arm].to_numpy(float)
        metric_rows.append({"seed": seed, "arm": arm, "spearman": spearman(y, pred), "mse": float(np.mean((y - pred) ** 2))})
    effects = {}
    for model in ["ridge", "histgb"]:
        simple = predictions[f"{model}_simple"].to_numpy(float)
        structure = predictions[f"{model}_structure"].to_numpy(float)
        effects[f"{model}_spearman_effect"] = spearman(y, structure) - spearman(y, simple)
        effects[f"{model}_mse_improvement"] = float(np.mean((y - simple) ** 2) - np.mean((y - structure) ** 2))
    return metric_rows, effects


def swap_arms(simple, structure, swap_mask):
    simple, structure, mask = np.asarray(simple, float), np.asarray(structure, float), np.asarray(swap_mask, bool)
    return np.where(mask, structure, simple), np.where(mask, simple, structure)


def primary_inference(primary, cluster_ids, bootstrap_seed, permutation_seed, resamples):
    y = primary["target"].to_numpy(float)
    unique_clusters = np.array(sorted(np.unique(cluster_ids).tolist()), dtype=int)
    assert len(unique_clusters) >= 10
    cluster_index = np.searchsorted(unique_clusters, cluster_ids)
    cluster_rows = [np.flatnonzero(cluster_index == i) for i in range(len(unique_clusters))]
    rng_boot = np.random.default_rng(bootstrap_seed)
    boot_clusters = rng_boot.integers(0, len(unique_clusters), size=(resamples, len(unique_clusters)), dtype=np.int16)
    rng_perm = np.random.default_rng(permutation_seed)
    perm_signs = rng_perm.choice(np.array([-1, 1], dtype=np.int8), size=(resamples, len(unique_clusters)))
    tests = ["ridge_spearman_effect", "ridge_mse_improvement", "histgb_spearman_effect", "histgb_mse_improvement"]
    observed, boot, null, arms = {}, {}, {}, {}
    for name in tests:
        boot[name] = np.empty(resamples, dtype=float)
        null[name] = np.empty(resamples, dtype=float)
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
        obs = float(observed[name])
        p = float((1 + np.sum(np.abs(null[name]) >= abs(obs))) / (resamples + 1))
        p_values.append(p)
        results.append({
            "test": name, "observed_effect": obs,
            "ci95": [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))],
            "p_cluster_swap": p, "bootstrap_median": float(np.median(boot[name])),
        })
    for row, p_holm in zip(results, holm_adjust(p_values)):
        row["p_holm"] = p_holm
    arrays = {f"bootstrap__{name}": boot[name] for name in tests}
    arrays.update({f"permutation__{name}": null[name] for name in tests})
    arrays["bootstrap_cluster_indices"] = boot_clusters
    arrays["permutation_cluster_signs"] = perm_signs
    return results, arrays


def build_analysis(protocol):
    source_path = Path(protocol["inputs"]["main_csv"]["path"])
    assert sha256(source_path) == protocol["inputs"]["main_csv"]["sha256"]
    feature_path = Path(protocol["inputs"]["rk02_feature_implementation"]["path"])
    assert sha256(feature_path) == protocol["inputs"]["rk02_feature_implementation"]["sha256"]
    cai_path = Path(protocol["inputs"]["cai_wrapper"]["path"])
    assert sha256(cai_path) == protocol["inputs"]["cai_wrapper"]["sha256"]
    fasta_path = Path(protocol["inputs"]["references_r1_fasta"]["path"])
    assert sha256(fasta_path) == protocol["inputs"]["references_r1_fasta"]["sha256"]
    references = rk02.load_literal_assignment(cai_path, protocol["inputs"]["cai_wrapper"]["reference_variable"])
    assert len(references) == protocol["inputs"]["cai_wrapper"]["reference_count"]
    weights = rk02.reference_weights(references)
    fasta = rk02.read_fasta(fasta_path)
    raw = pd.read_csv(source_path, keep_default_na=False)
    assert len(raw) == 152 and raw["variant_id"].is_unique
    rows = []
    proteins = set()
    for record in raw.to_dict("records"):
        variant = str(record["variant_id"])
        sequence = str(record["sequence_5prime_300nt"]).upper()
        assert fasta.get(variant) == sequence
        counts = [int(record[f"counts_bin{i}"]) for i in range(1, 9)]
        total = sum(counts)
        assert total == int(record["r1_assigned_reads"]) and total >= 1000
        score = rk02.flowseq_score(counts)
        assert abs(score - float(record["flowseq_score_r1_only"])) <= 1e-12
        proteins.add(rk02.translate(sequence))
        row = {
            "variant_id": variant, "total_assigned_reads": total,
            "target": score, "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
        }
        row.update(rk02.simple_features(sequence, total, weights))
        row.update(rk02.structure_features(sequence))
        rows.append(row)
    assert len(proteins) == 1
    analysis = pd.DataFrame(rows)
    analysis.attrs["observed_r1_protein"] = next(iter(proteins))
    return analysis


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--coverage-report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    wall_start = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat()
    protocol = json.loads(args.protocol.read_text())
    coverage = json.loads(args.coverage_report.read_text())
    assert protocol["schema"] == "a8-rk28-mordstein-sequence-cluster-ood-protocol-v1"
    assert coverage["status"] == "PASS_LABEL_FREE_COVERAGE_AUDIT_FEASIBLE"
    assert coverage["protocol_sha256"] == sha256(args.protocol)
    assert coverage["coverage_feasible"] is True and coverage["model_fit_authorized"] is True
    assert coverage["expression_or_model_fit_performed"] is False
    args.output_root.mkdir(parents=True, exist_ok=True)

    analysis = build_analysis(protocol)
    facts_path = Path(coverage["facts_csv"])
    assert sha256(facts_path) == coverage["facts_sha256"]
    facts = pd.read_csv(facts_path)
    analysis = analysis.merge(facts, on=["variant_id", "sequence_sha256"], how="left", validate="one_to_one")
    assert len(analysis) == 152 and analysis["sequence_cluster_id"].notna().all()
    analysis["sequence_cluster_id"] = analysis["sequence_cluster_id"].astype(int)
    assert analysis["sequence_cluster_id"].nunique() == 74
    analysis_path = args.output_root / "analysis_variants_152.csv"
    analysis.to_csv(analysis_path, index=False)

    simple = protocol["models"]["feature_sets"]["simple"]
    structure = simple + protocol["models"]["feature_sets"]["structure_addition"]
    mfe_only = protocol["models"]["feature_sets"]["mfe_only_descriptive"]
    feature_sets = {"simple": simple, "structure": structure, "mfe_only": mfe_only}
    seeds = protocol["outer_evaluation"]["sensitivity_seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    all_predictions, fold_rows, seed_metric_rows, seed_effect_rows = [], [], [], []
    for seed in seeds:
        folds, loads = make_cluster_folds(analysis["sequence_cluster_id"].to_numpy(int), seed)
        if seed == primary_seed:
            assert loads == coverage["selected_coverage"]["primary_seed_fold_sizes"]
        fold_assignment = analysis[["variant_id", "sequence_cluster_id"]].copy()
        fold_assignment.insert(0, "seed", seed)
        fold_assignment["fold"] = folds
        fold_rows.append(fold_assignment)
        seed_predictions = analysis[["variant_id", "sequence_cluster_id", "target"]].copy()
        seed_predictions.insert(0, "seed", seed)
        seed_predictions["fold"] = folds
        arms = ["null", "ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"]
        for arm in arms:
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
        assert np.isfinite(seed_predictions[arms].to_numpy(float)).all()
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

    training_log_rows = []
    for seed in seeds:
        current = assignments[assignments["seed"] == seed]
        for fold in range(5):
            test_variants = set(current.loc[current["fold"] == fold, "variant_id"])
            test_mask = analysis["variant_id"].isin(test_variants)
            train_mask = ~test_mask
            train_clusters = set(analysis.loc[train_mask, "sequence_cluster_id"])
            test_clusters = set(analysis.loc[test_mask, "sequence_cluster_id"])
            assert train_clusters.isdisjoint(test_clusters)
            training_log_rows.append({
                "seed": seed, "fold": fold, "n_train": int(train_mask.sum()), "n_test": int(test_mask.sum()),
                "n_train_clusters": len(train_clusters), "n_test_clusters": len(test_clusters),
                "train_target_mean": float(analysis.loc[train_mask, "target"].mean()),
                "histgb_random_state": int(seed + fold), "model_fits": 6, "cluster_leakage": False,
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
    assert len(primary) == 152
    inf = protocol["primary_inference"]
    primary_tests, arrays = primary_inference(
        primary, primary["sequence_cluster_id"].to_numpy(int),
        inf["cluster_bootstrap"]["seed"], inf["cluster_swap_permutation"]["seed"], inf["cluster_bootstrap"]["resamples"],
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
        test["pass"] = bool(test["observed_effect"] > 0 and test["ci95"][0] > 0 and test["p_holm"] < 0.05 and test["positive_seeds"] >= 8)
        all_pass = all_pass and test["pass"]
    primary_metrics = seed_metrics[seed_metrics["seed"] == primary_seed].drop(columns=["seed"]).to_dict("records")
    output_files = {}
    for path in [analysis_path, assignments_path, predictions_path, training_log_path, seed_metrics_path, seed_effects_path, arrays_path]:
        output_files[path.name] = {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}
    summary = {
        "schema": "a8-rk28-mordstein-sequence-cluster-ood-result-v1",
        "status": "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION",
        "protocol": str(args.protocol), "protocol_sha256": sha256(args.protocol),
        "coverage_report_sha256": sha256(args.coverage_report), "analysis_script_sha256": sha256(Path(__file__).resolve()),
        "source_csv_sha256": protocol["inputs"]["main_csv"]["sha256"],
        "feature_implementation_sha256": protocol["inputs"]["rk02_feature_implementation"]["sha256"],
        "cai_wrapper_sha256": protocol["inputs"]["cai_wrapper"]["sha256"],
        "analysis_type": protocol["analysis_type"], "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": float(time.perf_counter() - wall_start),
        "n_variants": 152, "n_sequence_clusters": 74, "selected_min_identity": 0.90,
        "primary_seed": primary_seed, "seeds": seeds, "folds_per_seed": 5,
        "model_fits_per_seed": 30, "total_model_fits": 300, "device": "CPU_ONLY",
        "primary_absolute_performance": primary_metrics, "primary_tests": primary_tests,
        "sequence_cluster_ood_structure_increment_pass": bool(all_pass),
        "scientific_conclusion": protocol["result_interpretation"]["pass"] if all_pass else protocol["result_interpretation"]["fail"],
        "outputs": output_files,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__, "ViennaRNA": rk02.RNA.__version__},
        "scientific_flags": protocol["scientific_boundaries"],
    }
    write_json(args.summary, summary)
    print(json.dumps({
        "status": summary["status"], "scientific_conclusion": summary["scientific_conclusion"],
        "primary_absolute_performance": primary_metrics, "primary_tests": primary_tests,
        "total_model_fits": 300, "elapsed_seconds": summary["elapsed_seconds"], "summary": str(args.summary),
    }, indent=2))


if __name__ == "__main__":
    main()
