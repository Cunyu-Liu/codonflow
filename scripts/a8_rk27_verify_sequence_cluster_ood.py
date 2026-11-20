#!/usr/bin/env python3
"""Independent RK27 verifier.

It rebuilds clusters, folds, aggregation, every model prediction and all resampling
from the frozen protocol and raw source before loading production predictions.
It never imports the production or coverage implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def corr_spearman(a: np.ndarray, b: np.ndarray) -> float:
    return float(spearmanr(np.asarray(a, float), np.asarray(b, float)).statistic)


def independent_holm(p_values: list[float]) -> np.ndarray:
    p = np.array(p_values, dtype=float)
    m = len(p)
    order = np.argsort(p)
    out = np.zeros(m, dtype=float)
    # Enforce step-down monotonicity without using the production implementation.
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p[idx])
        out[idx] = min(1.0, running)
    return out


def assign_independent(labels: np.ndarray, seed: int) -> tuple[np.ndarray, list[int]]:
    unique = sorted(set(int(x) for x in labels))
    rng = np.random.default_rng(seed)
    random_order = list(np.array(unique, dtype=int)[rng.permutation(len(unique))])
    random_order = sorted(random_order, key=lambda c: -int(np.count_nonzero(labels == c)))
    loads = [0] * 5
    mapping = {}
    for cluster in random_order:
        minimum = min(loads)
        choices = [i for i, value in enumerate(loads) if value == minimum]
        chosen = int(rng.choice(np.array(choices, dtype=int)))
        mapping[int(cluster)] = chosen
        loads[chosen] += int(np.count_nonzero(labels == cluster))
    return np.array([mapping[int(c)] for c in labels], dtype=int), loads


def independent_statistics(primary: pd.DataFrame, clusters: np.ndarray, n_resamples: int, boot_seed: int, perm_seed: int) -> tuple[list[dict], dict[str, np.ndarray]]:
    y = primary["target"].to_numpy(float)
    unique = np.array(sorted(set(int(x) for x in clusters)), dtype=int)
    positions = np.searchsorted(unique, clusters)
    members = [np.where(positions == i)[0] for i in range(len(unique))]
    boot_rng = np.random.default_rng(boot_seed)
    boot_ids = boot_rng.integers(0, len(unique), size=(n_resamples, len(unique)), dtype=np.int16)
    perm_rng = np.random.default_rng(perm_seed)
    signs = perm_rng.choice(np.array([-1, 1], dtype=np.int8), size=(n_resamples, len(unique)))
    names = ["ridge_spearman_effect", "ridge_mse_improvement", "histgb_spearman_effect", "histgb_mse_improvement"]
    boot = {name: np.zeros(n_resamples, dtype=float) for name in names}
    null = {name: np.zeros(n_resamples, dtype=float) for name in names}
    observed = {}
    for model in ["ridge", "histgb"]:
        simple = primary[f"{model}_simple"].to_numpy(float)
        structure = primary[f"{model}_structure"].to_numpy(float)
        observed[f"{model}_spearman_effect"] = corr_spearman(y, structure) - corr_spearman(y, simple)
        difference = (simple - y) ** 2 - (structure - y) ** 2
        observed[f"{model}_mse_improvement"] = float(np.mean(difference))
        null[f"{model}_mse_improvement"] = np.mean(signs[:, positions] * difference, axis=1)
    for b in range(n_resamples):
        chosen = boot_ids[b]
        rows = np.concatenate([members[int(c)] for c in chosen])
        counts = np.bincount(chosen, minlength=len(unique))
        weights = counts[positions]
        swap = signs[b, positions] == -1
        for model in ["ridge", "histgb"]:
            simple = primary[f"{model}_simple"].to_numpy(float)
            structure = primary[f"{model}_structure"].to_numpy(float)
            boot[f"{model}_spearman_effect"][b] = corr_spearman(y[rows], structure[rows]) - corr_spearman(y[rows], simple[rows])
            difference = (simple - y) ** 2 - (structure - y) ** 2
            boot[f"{model}_mse_improvement"][b] = float(np.sum(weights * difference) / np.sum(weights))
            perm_simple = simple.copy()
            perm_structure = structure.copy()
            perm_simple[swap] = structure[swap]
            perm_structure[swap] = simple[swap]
            null[f"{model}_spearman_effect"][b] = corr_spearman(y, perm_structure) - corr_spearman(y, perm_simple)
    p_values = [float((1 + np.count_nonzero(np.abs(null[name]) >= abs(observed[name]))) / (n_resamples + 1)) for name in names]
    adjusted = independent_holm(p_values)
    tests = []
    for i, name in enumerate(names):
        tests.append({
            "test": name,
            "observed_effect": float(observed[name]),
            "ci95": [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))],
            "p_cluster_swap": p_values[i],
            "p_holm": float(adjusted[i]),
            "bootstrap_median": float(np.median(boot[name])),
        })
    arrays = {f"bootstrap__{name}": boot[name] for name in names}
    arrays.update({f"permutation__{name}": null[name] for name in names})
    arrays["bootstrap_cluster_indices"] = boot_ids
    arrays["permutation_cluster_signs"] = signs
    return tests, arrays


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--coverage-report", type=Path, required=True)
    parser.add_argument("--production-summary", type=Path, required=True)
    parser.add_argument("--independent-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.independent_root.mkdir(parents=True, exist_ok=True)
    protocol = json.loads(args.protocol.read_text())
    coverage = json.loads(args.coverage_report.read_text())

    source_path = Path(protocol["inputs"]["main_csv"]["path"])
    source = pd.read_csv(source_path, usecols=["source_row", "seqId", "cds", "protein_aa", "CAI", "log10_expression", "mfe_5prime_kcal_mol"])
    source["cds"] = source["cds"].astype(str).str.upper()
    records = []
    for cds, group in source.groupby("cds", sort=False):
        assert group["CAI"].nunique() == 1 and group["mfe_5prime_kcal_mol"].nunique() == 1
        assert group["protein_aa"].nunique() == 1 and np.isfinite(group["log10_expression"]).all()
        gc = sum(c in "GC" for c in cds) / len(cds)
        gc3 = sum(c in "GC" for c in cds[2::3]) / len(cds[2::3])
        records.append({
            "cds": cds,
            "cds_sha256": hashlib.sha256(cds.encode()).hexdigest(),
            "first_source_row": int(group["source_row"].min()),
            "n_measurements": len(group),
            "CAI": float(group["CAI"].iloc[0]),
            "gc_cds": gc,
            "gc3_cds": gc3,
            "mfe_5prime_kcal_mol": float(group["mfe_5prime_kcal_mol"].iloc[0]),
            "target": float(np.mean(group["log10_expression"].to_numpy(float))),
        })
    units = pd.DataFrame(records).sort_values("first_source_row").reset_index(drop=True)
    units.insert(0, "unit_id", [f"u{i:03d}" for i in range(len(units))])
    assert len(source) == 154 and len(units) == 150 and int((units["n_measurements"] > 1).sum()) == 4
    assert units["cds"].str.len().eq(720).all() and units["cds"].nunique() == 150

    # Independently rebuild the frozen complete-linkage clusters from raw CDS strings.
    encoded = np.array([[ord(c) for c in cds] for cds in units["cds"]], dtype=np.uint8)
    identities = np.mean(encoded[:, None, :] == encoded[None, :, :], axis=2)
    tree = linkage(squareform(1.0 - identities, checks=False), method="complete")
    cluster = fcluster(tree, t=0.10, criterion="distance").astype(int)
    units["sequence_cluster_id"] = cluster
    assert len(set(cluster)) == 37 and max(np.bincount(cluster)[1:]) == 61
    facts = pd.read_csv(coverage["facts_csv"])
    cluster_comparison = units[["cds_sha256", "sequence_cluster_id"]].merge(facts[["cds_sha256", "sequence_cluster_id"]], on="cds_sha256", suffixes=("_independent", "_coverage"), validate="one_to_one")
    cluster_mismatches = int((cluster_comparison["sequence_cluster_id_independent"] != cluster_comparison["sequence_cluster_id_coverage"]).sum())
    assert cluster_mismatches == 0

    seeds = protocol["outer_evaluation"]["sensitivity_seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    feature_sets = {
        "simple": ["CAI", "gc_cds", "gc3_cds"],
        "structure": ["CAI", "gc_cds", "gc3_cds", "mfe_5prime_kcal_mol"],
        "mfe_only": ["mfe_5prime_kcal_mol"],
    }
    independent_predictions = []
    independent_assignments = []
    independent_metrics = []
    independent_effects = []
    independent_training = []
    for seed in seeds:
        folds, loads = assign_independent(cluster, seed)
        if seed == primary_seed:
            assert loads == coverage["selected_coverage"]["primary_seed_fold_sizes"]
        assignment = units[["unit_id", "cds_sha256", "sequence_cluster_id"]].copy()
        assignment.insert(0, "seed", seed)
        assignment["fold"] = folds
        independent_assignments.append(assignment)
        current = units[["unit_id", "cds_sha256", "sequence_cluster_id", "target"]].copy()
        current.insert(0, "seed", seed)
        current["fold"] = folds
        for arm in ["null", "ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"]:
            current[arm] = np.nan
        for fold in range(5):
            train = units.loc[folds != fold]
            test = units.loc[folds == fold]
            assert set(train["sequence_cluster_id"]).isdisjoint(set(test["sequence_cluster_id"]))
            current.loc[current.index[folds == fold], "null"] = float(train["target"].mean())
            for model_name in ["ridge", "histgb"]:
                for label, features in feature_sets.items():
                    if model_name == "ridge":
                        estimator = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
                    else:
                        estimator = HistGradientBoostingRegressor(
                            loss="squared_error", learning_rate=0.05, max_iter=200,
                            max_leaf_nodes=7, min_samples_leaf=10,
                            l2_regularization=1.0, early_stopping=False,
                            random_state=int(seed + fold),
                        )
                    estimator.fit(train[features], train["target"])
                    current.loc[current.index[folds == fold], f"{model_name}_{label}"] = estimator.predict(test[features])
            independent_training.append({
                "seed": seed, "fold": fold, "n_train": len(train), "n_test": len(test),
                "n_train_clusters": train["sequence_cluster_id"].nunique(),
                "n_test_clusters": test["sequence_cluster_id"].nunique(),
                "train_target_mean": float(train["target"].mean()),
                "histgb_random_state": int(seed + fold), "model_fits": 6,
                "cluster_leakage": False,
            })
        independent_predictions.append(current)
        y = current["target"].to_numpy(float)
        for arm in ["null", "ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"]:
            pred = current[arm].to_numpy(float)
            independent_metrics.append({"seed": seed, "arm": arm, "spearman": corr_spearman(y, pred), "mse": float(np.mean((pred - y) ** 2))})
        for model in ["ridge", "histgb"]:
            simple = current[f"{model}_simple"].to_numpy(float)
            structure = current[f"{model}_structure"].to_numpy(float)
            independent_effects.append({"seed": seed, "test": f"{model}_spearman_effect", "effect": corr_spearman(y, structure) - corr_spearman(y, simple)})
            independent_effects.append({"seed": seed, "test": f"{model}_mse_improvement", "effect": float(np.mean((simple - y) ** 2 - (structure - y) ** 2))})

    independent_predictions = pd.concat(independent_predictions, ignore_index=True)
    independent_assignments = pd.concat(independent_assignments, ignore_index=True)
    independent_metrics = pd.DataFrame(independent_metrics)
    independent_effects = pd.DataFrame(independent_effects)
    independent_training = pd.DataFrame(independent_training)
    independent_predictions.to_csv(args.independent_root / "oof_predictions.csv", index=False)
    independent_assignments.to_csv(args.independent_root / "fold_assignments.csv", index=False)
    independent_metrics.to_csv(args.independent_root / "seed_metrics.csv", index=False)
    independent_effects.to_csv(args.independent_root / "seed_effects.csv", index=False)
    independent_training.to_csv(args.independent_root / "training_log.csv", index=False)

    primary = independent_predictions[independent_predictions["seed"] == primary_seed].reset_index(drop=True)
    inf = protocol["primary_inference"]
    independent_tests, independent_arrays = independent_statistics(
        primary, primary["sequence_cluster_id"].to_numpy(int),
        inf["cluster_bootstrap"]["resamples"], inf["cluster_bootstrap"]["seed"],
        inf["cluster_swap_permutation"]["seed"],
    )
    np.savez_compressed(args.independent_root / "primary_inference_arrays.npz", **independent_arrays)
    independent_pass = True
    for test in independent_tests:
        values = independent_effects[independent_effects["test"] == test["test"]].sort_values("seed")["effect"].to_numpy(float)
        test["seed_effects"] = values.tolist()
        test["positive_seeds"] = int(np.count_nonzero(values > 0))
        test["mean_seed_effect"] = float(np.mean(values))
        test["median_seed_effect"] = float(np.median(values))
        test["pass"] = bool(test["observed_effect"] > 0 and test["ci95"][0] > 0 and test["p_holm"] < 0.05 and test["positive_seeds"] >= 8)
        independent_pass = independent_pass and test["pass"]
    independent_conclusion = "FIXED_PROTEIN_SEQUENCE_CLUSTER_OOD_MFE_INCREMENT_SUPPORTED_RETROSPECTIVELY" if independent_pass else "FIXED_PROTEIN_SEQUENCE_CLUSTER_OOD_MFE_INCREMENT_NOT_SUPPORTED"

    # Only now load production outputs for comparison.
    production_summary = json.loads(args.production_summary.read_text())
    production_root = Path(protocol["output_root"])
    production_predictions = pd.read_csv(production_root / "oof_predictions.csv")
    production_assignments = pd.read_csv(production_root / "fold_assignments.csv")
    production_metrics = pd.read_csv(production_root / "seed_metrics.csv", keep_default_na=False)
    production_effects = pd.read_csv(production_root / "seed_effects.csv")
    production_training = pd.read_csv(production_root / "training_log.csv")
    production_analysis = pd.read_csv(production_root / "analysis_exact_cds_150.csv")
    production_arrays = np.load(production_root / "primary_inference_arrays.npz")

    checks = []
    def check(name: str, ok: bool, details: object) -> None:
        checks.append({"name": name, "pass": bool(ok), "details": details})

    check("source_sha256", digest(source_path) == protocol["inputs"]["main_csv"]["sha256"], digest(source_path))
    check("protocol_sha256", digest(args.protocol) == production_summary["protocol_sha256"], digest(args.protocol))
    check("coverage_sha256", digest(args.coverage_report) == production_summary["coverage_report_sha256"], digest(args.coverage_report))
    check("sample_chain", len(source) == 154 and len(units) == 150 and len(set(cluster)) == 37, {"measurements": len(source), "units": len(units), "clusters": len(set(cluster))})
    check("cluster_assignment_exact", cluster_mismatches == 0, {"mismatches": cluster_mismatches})

    analysis_compare = production_analysis.merge(units, on="cds_sha256", suffixes=("_production", "_independent"), validate="one_to_one")
    check("analysis_row_coverage", len(analysis_compare) == 150, len(analysis_compare))
    for feature in ["CAI", "gc_cds", "gc3_cds", "mfe_5prime_kcal_mol", "target"]:
        delta = float(np.max(np.abs(analysis_compare[f"{feature}_production"] - analysis_compare[f"{feature}_independent"])))
        check(f"analysis_{feature}", delta < 1e-12, {"max_abs_diff": delta})

    assignment_compare = production_assignments.merge(independent_assignments, on=["seed", "cds_sha256"], suffixes=("_production", "_independent"), validate="one_to_one")
    assignment_mismatches = int((assignment_compare["fold_production"] != assignment_compare["fold_independent"]).sum())
    check("all_1500_fold_assignments_exact", len(assignment_compare) == 1500 and assignment_mismatches == 0, {"rows": len(assignment_compare), "mismatches": assignment_mismatches})

    prediction_compare = production_predictions.merge(independent_predictions, on=["seed", "cds_sha256"], suffixes=("_production", "_independent"), validate="one_to_one")
    check("prediction_row_coverage", len(prediction_compare) == 1500, len(prediction_compare))
    for arm in ["null", "ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"]:
        delta = float(np.max(np.abs(prediction_compare[f"{arm}_production"] - prediction_compare[f"{arm}_independent"])))
        check(f"predictions_{arm}", delta < 1e-9, {"max_abs_diff": delta, "n": 1500})

    metric_compare = production_metrics.merge(independent_metrics, on=["seed", "arm"], suffixes=("_production", "_independent"), validate="one_to_one")
    check("metric_row_coverage", len(metric_compare) == 70, len(metric_compare))
    for metric in ["spearman", "mse"]:
        delta = float(np.max(np.abs(metric_compare[f"{metric}_production"] - metric_compare[f"{metric}_independent"])))
        check(f"seed_metrics_{metric}", delta < 1e-9, {"max_abs_diff": delta})
    effect_compare = production_effects.merge(independent_effects, on=["seed", "test"], suffixes=("_production", "_independent"), validate="one_to_one")
    effect_delta = float(np.max(np.abs(effect_compare["effect_production"] - effect_compare["effect_independent"])))
    check("all_40_seed_effects", len(effect_compare) == 40 and effect_delta < 1e-9, {"rows": len(effect_compare), "max_abs_diff": effect_delta})

    training_compare = production_training.merge(independent_training, on=["seed", "fold"], suffixes=("_production", "_independent"), validate="one_to_one")
    training_delta = 0.0
    for column in ["n_train", "n_test", "n_train_clusters", "n_test_clusters", "train_target_mean", "histgb_random_state", "model_fits"]:
        training_delta = max(training_delta, float(np.max(np.abs(training_compare[f"{column}_production"] - training_compare[f"{column}_independent"]))))
    check("all_50_training_log_rows", len(training_compare) == 50 and training_delta < 1e-12, {"rows": len(training_compare), "max_abs_diff": training_delta})
    check("training_log_no_cluster_leakage", not production_training["cluster_leakage"].any(), {"rows": len(production_training)})

    for key in ["bootstrap_cluster_indices", "permutation_cluster_signs"]:
        equal = bool(np.array_equal(production_arrays[key], independent_arrays[key]))
        check(f"resampling_indices_{key}", equal, {"shape": list(independent_arrays[key].shape), "exact": equal})
    for name in ["ridge_spearman_effect", "ridge_mse_improvement", "histgb_spearman_effect", "histgb_mse_improvement"]:
        for prefix in ["bootstrap", "permutation"]:
            key = f"{prefix}__{name}"
            delta = float(np.max(np.abs(production_arrays[key] - independent_arrays[key])))
            check(f"resampling_values_{key}", delta < 1e-8, {"max_abs_diff": delta, "n": len(independent_arrays[key])})

    production_tests = {row["test"]: row for row in production_summary["primary_tests"]}
    for test in independent_tests:
        reference = production_tests[test["test"]]
        deltas = {
            "observed_effect": abs(test["observed_effect"] - reference["observed_effect"]),
            "ci95_low": abs(test["ci95"][0] - reference["ci95"][0]),
            "ci95_high": abs(test["ci95"][1] - reference["ci95"][1]),
            "p_cluster_swap": abs(test["p_cluster_swap"] - reference["p_cluster_swap"]),
            "p_holm": abs(test["p_holm"] - reference["p_holm"]),
        }
        same = max(deltas.values()) < 1e-8 and test["positive_seeds"] == reference["positive_seeds"] and test["pass"] == reference["pass"]
        check(f"primary_test_{test['test']}", same, {"deltas": deltas, "independent_pass": test["pass"], "production_pass": reference["pass"]})

    check("scientific_conclusion_agreement", independent_conclusion == production_summary["scientific_conclusion"], {"independent": independent_conclusion, "production": production_summary["scientific_conclusion"]})
    check("scientific_pass_agreement", independent_pass == production_summary["sequence_cluster_ood_mfe_increment_pass"], independent_pass)
    flags = production_summary["scientific_flags"]
    check("retrospective_boundary", flags["labels_previously_used_in_RK22_development"] and not flags["independent_untouched_confirmation"], flags)
    check("no_functional_untouched_or_generator_authorization", not flags["functional_untouched_read"] and not flags["generator_training_authorized"] and not flags["RK_G1_complete"], flags)
    check("no_overclaim_velocity_decay_or_protein_ood", not flags["velocity_or_decay_measured"] and not flags["full_spatial_coupling_established"] and not flags["protein_ood"], flags)
    check("production_pending_status_before_this_verifier", production_summary["status"] == "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION", production_summary["status"])
    check("total_model_fits_recorded", production_summary["total_model_fits"] == 300 and production_summary["device"] == "CPU_ONLY", {"fits": production_summary["total_model_fits"], "device": production_summary["device"]})

    passed = all(row["pass"] for row in checks)
    report = {
        "schema": "a8-rk27-independent-verification-v1",
        "status": "PASS" if passed else "FAIL",
        "independent_verification_pass": passed,
        "n_checks": len(checks),
        "n_passed": int(sum(row["pass"] for row in checks)),
        "checks": checks,
        "independent_script_sha256": digest(Path(__file__).resolve()),
        "production_summary": str(args.production_summary),
        "production_summary_sha256": digest(args.production_summary),
        "independent_conclusion": independent_conclusion,
        "independent_sequence_cluster_ood_pass": independent_pass,
        "independent_primary_tests": independent_tests,
        "independent_outputs": {
            path.name: {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size}
            for path in sorted(args.independent_root.iterdir()) if path.is_file()
        },
        "implementation": {
            "production_module_imported": False,
            "coverage_module_imported": False,
            "clusters_rebuilt_from_raw_cds": True,
            "all_models_refit": True,
            "all_resamples_recomputed": True,
            "functional_untouched_read": False,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": report["status"], "n_checks": len(checks), "n_passed": report["n_passed"],
        "independent_conclusion": independent_conclusion,
        "failed_checks": [row for row in checks if not row["pass"]],
        "independent_primary_tests": independent_tests,
    }, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
