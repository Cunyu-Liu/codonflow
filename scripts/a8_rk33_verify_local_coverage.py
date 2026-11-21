#!/usr/bin/env python3
"""Independent RK33 raw-source, model and inference verification.

No RK33 production module is imported. Prior RK28 independent predictions are
reused only after their byte identity and 54/54 verification chain are checked.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import RNA
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

import a8_rk28_verify_sequence_cluster_ood as previous

FAMILIES = ("local42_vs_simple", "local42_vs_full1", "local42_vs_full3")
COMPARATORS = {"local42_vs_simple": "simple", "local42_vs_full1": "full1", "local42_vs_full3": "full3"}
MODELS = ("ridge", "histgb")
TEST_ORDER = [f"{family}__{model}_{metric}" for family in FAMILIES for model in MODELS for metric in ("spearman_effect", "mse_improvement")]
ARMS = [f"{model}_{arm}" for model in MODELS for arm in ("simple", "local42", "full1", "full3")]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def independent_local42(sequence):
    rna = sequence[:42].replace("T", "U")
    md = RNA.md(); md.dangles = 0; md.temperature = 37.0
    value = float(RNA.fold_compound(rna, md).mfe()[1])
    assert math.isfinite(value) and abs(value) < 100000
    return value


def independent_metrics_effects(current, seed):
    y = current["target"].to_numpy(float)
    metrics = [{"seed": seed, "arm": arm, "spearman": previous.corr(y, current[arm]), "mse": float(np.mean((current[arm].to_numpy(float) - y) ** 2))} for arm in ARMS]
    effects = {}
    for family, comparator in COMPARATORS.items():
        for model in MODELS:
            local = current[f"{model}_local42"].to_numpy(float)
            reference = current[f"{model}_{comparator}"].to_numpy(float)
            effects[f"{family}__{model}_spearman_effect"] = previous.corr(y, local) - previous.corr(y, reference)
            effects[f"{family}__{model}_mse_improvement"] = float(np.mean((reference - y) ** 2 - (local - y) ** 2))
    assert list(effects) == TEST_ORDER
    return metrics, effects


def independent_statistics(primary, resamples, boot_seed, perm_seed):
    y = primary["target"].to_numpy(float)
    clusters = primary["sequence_cluster_id"].to_numpy(int)
    unique = np.array(sorted(set(int(value) for value in clusters)), int)
    assert len(unique) == 74
    positions = np.searchsorted(unique, clusters)
    members = [np.where(positions == index)[0] for index in range(len(unique))]
    boot_ids = np.random.default_rng(boot_seed).integers(0, len(unique), size=(resamples, len(unique)), dtype=np.int16)
    signs = np.random.default_rng(perm_seed).choice(np.array([-1, 1], dtype=np.int8), size=(resamples, len(unique)))
    boot = {name: np.zeros(resamples, float) for name in TEST_ORDER}
    null = {name: np.zeros(resamples, float) for name in TEST_ORDER}
    observed, pairs = {}, {}
    for family, comparator in COMPARATORS.items():
        for model in MODELS:
            local = primary[f"{model}_local42"].to_numpy(float)
            reference = primary[f"{model}_{comparator}"].to_numpy(float)
            pairs[(family, model)] = (local, reference)
            sp_name = f"{family}__{model}_spearman_effect"
            mse_name = f"{family}__{model}_mse_improvement"
            observed[sp_name] = previous.corr(y, local) - previous.corr(y, reference)
            difference = (reference - y) ** 2 - (local - y) ** 2
            observed[mse_name] = float(np.mean(difference))
            null[mse_name] = np.mean(signs[:, positions] * difference, axis=1)
    for b in range(resamples):
        chosen = boot_ids[b]
        rows = np.concatenate([members[int(cluster)] for cluster in chosen])
        weights = np.bincount(chosen, minlength=len(unique))[positions]
        swap = signs[b, positions] == -1
        for (family, model), (local, reference) in pairs.items():
            sp_name = f"{family}__{model}_spearman_effect"
            mse_name = f"{family}__{model}_mse_improvement"
            boot[sp_name][b] = previous.corr(y[rows], local[rows]) - previous.corr(y[rows], reference[rows])
            difference = (reference - y) ** 2 - (local - y) ** 2
            boot[mse_name][b] = float(np.sum(weights * difference) / np.sum(weights))
            perm_local, perm_reference = local.copy(), reference.copy()
            perm_local[swap], perm_reference[swap] = reference[swap], local[swap]
            null[sp_name][b] = previous.corr(y, perm_local) - previous.corr(y, perm_reference)
    raw_p = [float((1 + np.count_nonzero(np.abs(null[name]) >= abs(observed[name]))) / (resamples + 1)) for name in TEST_ORDER]
    adjusted = previous.independent_holm(raw_p)
    tests = [{"test": name, "observed_effect": float(observed[name]), "ci95": [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))], "p_cluster_swap": raw_p[index], "p_holm": float(adjusted[index]), "bootstrap_median": float(np.median(boot[name]))} for index, name in enumerate(TEST_ORDER)]
    arrays = {f"bootstrap__{name}": boot[name] for name in TEST_ORDER}
    arrays.update({f"permutation__{name}": null[name] for name in TEST_ORDER})
    arrays["bootstrap_cluster_indices"], arrays["permutation_cluster_signs"] = boot_ids, signs
    return tests, arrays


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--production-summary", type=Path, required=True)
    parser.add_argument("--independent-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    wall_start = time.perf_counter(); started = datetime.now(timezone.utc).isoformat()
    args.independent_root.mkdir(parents=True, exist_ok=True)
    protocol = json.loads(args.protocol.read_text())
    preflight = json.loads(args.preflight_report.read_text())
    assert preflight["status"] == "PASS_RK33_LABEL_FREE_PREFLIGHT" and preflight["protocol_sha256"] == digest(args.protocol)

    old_report_path = Path("/home/codonflow-a8-rk/audits/20261121/RK28/rk28_sequence_cluster_ood_independent_v1.json")
    assert digest(old_report_path) == protocol["prior_evidence"]["rk28_independent_report_sha256"]
    old_report = json.loads(old_report_path.read_text())
    old_checks = old_report["checks"]
    assert old_report["status"] == "PASS" and len(old_checks) == 54 and all(row["pass"] for row in old_checks)
    old_independent_predictions_path = Path(old_report["independent_outputs"]["oof_predictions.csv"]["path"])
    old_independent_assignments_path = Path(old_report["independent_outputs"]["fold_assignments.csv"]["path"])
    assert digest(old_independent_predictions_path) == protocol["inputs"]["rk28_oof_predictions"]["sha256"]
    assert digest(old_independent_assignments_path) == protocol["inputs"]["rk28_fold_assignments"]["sha256"]
    assert digest(protocol["inputs"]["rk28_oof_predictions"]["path"]) == protocol["inputs"]["rk28_oof_predictions"]["sha256"]

    source_path = Path(protocol["inputs"]["main_csv"]["path"])
    cai_path = Path(protocol["inputs"]["cai_wrapper"]["path"])
    fasta_path = Path(protocol["inputs"]["references_r1_fasta"]["path"])
    assert digest(source_path) == protocol["inputs"]["main_csv"]["sha256"]
    assert digest(cai_path) == protocol["inputs"]["cai_wrapper"]["sha256"]
    assert digest(fasta_path) == protocol["inputs"]["references_r1_fasta"]["sha256"]
    references = previous.literal_variable(cai_path, protocol["inputs"]["cai_wrapper"]["reference_variable"])
    weights = previous.independent_cai_weights(references)
    fasta = previous.read_fasta_independent(fasta_path)
    source = pd.read_csv(source_path, keep_default_na=False)
    assert len(source) == 152 and source["variant_id"].is_unique
    rows, proteins = [], set()
    for record in source.to_dict("records"):
        variant = str(record["variant_id"]); sequence = str(record["sequence_5prime_300nt"]).upper()
        assert fasta[variant] == sequence
        counts = [int(record[f"counts_bin{index}"]) for index in range(1, 9)]
        total = int(np.sum(counts)); assert total == int(record["r1_assigned_reads"]) and total >= 1000
        target = float(np.dot(np.arange(1, 9), counts) / total)
        assert abs(target - float(record["flowseq_score_r1_only"])) <= 1e-12
        proteins.add("".join(previous.CODONS[sequence[index:index + 3]] for index in range(0, 300, 3)))
        row = {"variant_id": variant, "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(), "total_assigned_reads": total, "target": target}
        row.update(previous.independent_features(sequence, total, weights))
        row["mfe_observed_cds4_45_local42_kcal_mol"] = independent_local42(sequence)
        rows.append(row)
    assert len(proteins) == 1
    units = pd.DataFrame(rows)
    sequences = [str(value).upper() for value in source["sequence_5prime_300nt"]]
    encoded = np.array([[ord(base) for base in sequence] for sequence in sequences], dtype=np.uint8)
    identities = np.mean(encoded[:, None, :] == encoded[None, :, :], axis=2)
    tree = linkage(squareform(1.0 - identities, checks=False), method="complete")
    cluster = fcluster(tree, t=0.10, criterion="distance").astype(int)
    units["sequence_cluster_id"] = cluster
    assert len(set(cluster)) == 74 and max(np.bincount(cluster)[1:]) == 12

    reused = pd.read_csv(old_independent_predictions_path)
    old_assignments = pd.read_csv(old_independent_assignments_path)
    cluster_comparison = units[["variant_id", "sequence_cluster_id"]].merge(old_assignments[["variant_id", "sequence_cluster_id"]].drop_duplicates(), on="variant_id", suffixes=("_independent", "_rk28"), validate="one_to_one")
    cluster_mismatches = int((cluster_comparison["sequence_cluster_id_independent"] != cluster_comparison["sequence_cluster_id_rk28"]).sum())
    assert cluster_mismatches == 0

    simple = protocol["models"]["feature_sets"]["simple"]
    feature_sets = {"local42": simple + protocol["models"]["feature_sets"]["local42_addition"], "full1": simple + protocol["models"]["feature_sets"]["full1_addition"]}
    seeds = protocol["outer_evaluation"]["sensitivity_seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    independent_predictions, independent_assignments, independent_metrics, independent_effects, independent_training = [], [], [], [], []
    for seed in seeds:
        folds, loads = previous.assign_folds(cluster, seed)
        expected = old_assignments[old_assignments["seed"] == seed].set_index("variant_id").loc[units["variant_id"], "fold"].to_numpy(int)
        assert np.array_equal(folds, expected)
        assignment = units[["variant_id", "sequence_cluster_id"]].copy(); assignment.insert(0, "seed", seed); assignment["fold"] = folds
        independent_assignments.append(assignment)
        old = reused[reused["seed"] == seed].set_index("variant_id").loc[units["variant_id"]].reset_index()
        assert np.array_equal(old["fold"].to_numpy(int), folds)
        assert np.allclose(old["target"].to_numpy(float), units["target"].to_numpy(float), rtol=0, atol=1e-12)
        current = units[["variant_id", "sequence_cluster_id", "target"]].copy(); current.insert(0, "seed", seed); current["fold"] = folds
        current["ridge_simple"] = old["ridge_simple"].to_numpy(float); current["histgb_simple"] = old["histgb_simple"].to_numpy(float)
        current["ridge_full3"] = old["ridge_structure"].to_numpy(float); current["histgb_full3"] = old["histgb_structure"].to_numpy(float)
        for arm in ("ridge_local42", "ridge_full1", "histgb_local42", "histgb_full1"):
            current[arm] = np.nan
        for fold in range(5):
            train, test = units.loc[folds != fold], units.loc[folds == fold]
            assert set(train["sequence_cluster_id"]).isdisjoint(set(test["sequence_cluster_id"]))
            for model in MODELS:
                for label, features in feature_sets.items():
                    if model == "ridge":
                        x_scaler = StandardScaler().fit(train[features]); y_scaler = StandardScaler().fit(train[["target"]])
                        estimator = Ridge(alpha=1.0, solver="cholesky")
                        estimator.fit(x_scaler.transform(train[features]), y_scaler.transform(train[["target"]]).ravel())
                        prediction = y_scaler.inverse_transform(estimator.predict(x_scaler.transform(test[features])).reshape(-1, 1)).ravel()
                    else:
                        estimator = HistGradientBoostingRegressor(loss="squared_error", learning_rate=0.05, max_iter=200, max_leaf_nodes=7, min_samples_leaf=10, l2_regularization=1.0, early_stopping=False, random_state=int(seed + fold))
                        estimator.fit(train[features], train["target"])
                        prediction = estimator.predict(test[features])
                    current.loc[current.index[folds == fold], f"{model}_{label}"] = prediction
            independent_training.append({"seed": seed, "fold": fold, "n_train": len(train), "n_test": len(test), "n_train_clusters": train["sequence_cluster_id"].nunique(), "n_test_clusters": test["sequence_cluster_id"].nunique(), "train_target_mean": float(train["target"].mean()), "histgb_random_state": int(seed + fold), "new_model_fits": 4, "reused_rk28_model_fits": 4, "evaluated_model_fits": 8, "cluster_leakage": False})
        assert np.isfinite(current[ARMS].to_numpy(float)).all()
        independent_predictions.append(current)
        metrics, effects = independent_metrics_effects(current, seed)
        independent_metrics.extend(metrics)
        independent_effects.extend({"seed": seed, "test": name, "effect": value} for name, value in effects.items())

    independent_predictions = pd.concat(independent_predictions, ignore_index=True)
    independent_assignments = pd.concat(independent_assignments, ignore_index=True)
    independent_metrics = pd.DataFrame(independent_metrics); independent_effects = pd.DataFrame(independent_effects); independent_training = pd.DataFrame(independent_training)
    primary = independent_predictions[independent_predictions["seed"] == primary_seed].reset_index(drop=True)
    inf = protocol["primary_inference"]
    independent_tests, independent_arrays = independent_statistics(primary, inf["cluster_bootstrap"]["resamples"], inf["cluster_bootstrap"]["seed"], inf["cluster_swap_permutation"]["seed"])
    for test in independent_tests:
        values = independent_effects[independent_effects["test"] == test["test"]].sort_values("seed")["effect"].to_numpy(float)
        test["seed_effects"] = values.tolist(); test["positive_seeds"] = int(np.count_nonzero(values > 0)); test["mean_seed_effect"] = float(values.mean()); test["median_seed_effect"] = float(np.median(values))
        test["pass"] = bool(test["observed_effect"] > 0 and test["ci95"][0] > 0 and test["p_holm"] < 0.05 and test["positive_seeds"] >= 8)
    family_pass = {family: all(row["pass"] for row in independent_tests if row["test"].startswith(family + "__")) for family in FAMILIES}
    if all(family_pass.values()):
        independent_conclusion = "LOCAL42_INCREMENT_AND_FULL_STRUCTURE_SUPERIORITY_SUPPORTED_RETROSPECTIVELY"
    elif family_pass["local42_vs_simple"]:
        independent_conclusion = "LOCAL42_INCREMENT_SUPPORTED_BUT_FULL_STRUCTURE_SUPERIORITY_NOT_ESTABLISHED"
    else:
        independent_conclusion = "LOCAL42_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED"

    primary_folds = independent_assignments[independent_assignments["seed"] == primary_seed][["variant_id", "fold"]].rename(columns={"fold": "primary_seed_fold"})
    units = units.merge(primary_folds, on="variant_id", validate="one_to_one")
    units["cluster_size"] = units.groupby("sequence_cluster_id")["variant_id"].transform("size")
    output_paths = {name: args.independent_root / name for name in ["analysis_variants_152.csv", "fold_assignments.csv", "oof_predictions.csv", "training_log.csv", "seed_metrics.csv", "seed_effects.csv", "primary_inference_arrays.npz"]}
    units.to_csv(output_paths["analysis_variants_152.csv"], index=False)
    independent_assignments.to_csv(output_paths["fold_assignments.csv"], index=False)
    independent_predictions.to_csv(output_paths["oof_predictions.csv"], index=False)
    independent_training.to_csv(output_paths["training_log.csv"], index=False)
    independent_metrics.to_csv(output_paths["seed_metrics.csv"], index=False)
    independent_effects.to_csv(output_paths["seed_effects.csv"], index=False)
    np.savez_compressed(output_paths["primary_inference_arrays.npz"], **independent_arrays)

    # Production results are loaded only after all independent computations finish.
    production_summary = json.loads(args.production_summary.read_text())
    production_root = Path(production_summary["outputs"]["oof_predictions.csv"]["path"]).parent
    production_predictions = pd.read_csv(production_root / "oof_predictions.csv")
    production_assignments = pd.read_csv(production_root / "fold_assignments.csv")
    production_metrics = pd.read_csv(production_root / "seed_metrics.csv", keep_default_na=False)
    production_effects = pd.read_csv(production_root / "seed_effects.csv")
    production_training = pd.read_csv(production_root / "training_log.csv")
    production_analysis = pd.read_csv(production_root / "analysis_variants_152.csv")
    production_arrays = np.load(production_root / "primary_inference_arrays.npz")
    checks = []
    def check(name, ok, details):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    check("rk28_independent_chain_54_of_54", old_report["status"] == "PASS" and len(old_checks) == 54 and all(row["pass"] for row in old_checks), {"checks": 54, "predictions_sha256": digest(old_independent_predictions_path)})
    check("source_sha256", digest(source_path) == production_summary["source_csv_sha256"], digest(source_path))
    check("protocol_sha256", digest(args.protocol) == production_summary["protocol_sha256"], digest(args.protocol))
    check("preflight_sha256", digest(args.preflight_report) == production_summary["preflight_report_sha256"], digest(args.preflight_report))
    check("sample_chain", len(source) == len(units) == 152 and len(set(cluster)) == 74 and len(proteins) == 1, {"variants": len(units), "clusters": len(set(cluster)), "observed_protein_groups": len(proteins)})
    check("cluster_assignment_exact", cluster_mismatches == 0, {"mismatches": cluster_mismatches})
    analysis_compare = production_analysis.merge(units, on="variant_id", suffixes=("_production", "_independent"), validate="one_to_one")
    check("analysis_row_coverage", len(analysis_compare) == 152, len(analysis_compare))
    analysis_features = ["total_assigned_reads", "target"] + simple + protocol["models"]["feature_sets"]["full3_addition"] + protocol["models"]["feature_sets"]["local42_addition"]
    analysis_deltas = {}
    for feature in analysis_features:
        delta = float(np.max(np.abs(analysis_compare[f"{feature}_production"] - analysis_compare[f"{feature}_independent"])))
        analysis_deltas[feature] = delta
        check(f"analysis_{feature}", delta < 1e-10, {"max_abs_diff": delta})
    assignment_compare = production_assignments.merge(independent_assignments, on=["seed", "variant_id"], suffixes=("_production", "_independent"), validate="one_to_one")
    assignment_mismatches = int((assignment_compare["fold_production"] != assignment_compare["fold_independent"]).sum())
    check("all_1520_fold_assignments_exact", len(assignment_compare) == 1520 and assignment_mismatches == 0, {"rows": len(assignment_compare), "mismatches": assignment_mismatches})
    prediction_compare = production_predictions.merge(independent_predictions, on=["seed", "variant_id"], suffixes=("_production", "_independent"), validate="one_to_one")
    check("prediction_row_coverage", len(prediction_compare) == 1520, len(prediction_compare))
    prediction_deltas = {}
    for arm in ARMS:
        delta = float(np.max(np.abs(prediction_compare[f"{arm}_production"] - prediction_compare[f"{arm}_independent"])))
        prediction_deltas[arm] = delta
        check(f"predictions_{arm}", delta < 1e-9, {"max_abs_diff": delta, "n": 1520})
    metric_compare = production_metrics.merge(independent_metrics, on=["seed", "arm"], suffixes=("_production", "_independent"), validate="one_to_one")
    check("metric_row_coverage", len(metric_compare) == 80, len(metric_compare))
    for metric in ["spearman", "mse"]:
        delta = float(np.max(np.abs(metric_compare[f"{metric}_production"] - metric_compare[f"{metric}_independent"])))
        check(f"seed_metrics_{metric}", delta < 1e-9, {"max_abs_diff": delta})
    effect_compare = production_effects.merge(independent_effects, on=["seed", "test"], suffixes=("_production", "_independent"), validate="one_to_one")
    effect_delta = float(np.max(np.abs(effect_compare["effect_production"] - effect_compare["effect_independent"])))
    check("all_120_seed_effects", len(effect_compare) == 120 and effect_delta < 1e-9, {"rows": len(effect_compare), "max_abs_diff": effect_delta})
    training_compare = production_training.merge(independent_training, on=["seed", "fold"], suffixes=("_production", "_independent"), validate="one_to_one")
    training_delta = 0.0
    for column in ["n_train", "n_test", "n_train_clusters", "n_test_clusters", "train_target_mean", "histgb_random_state", "new_model_fits", "reused_rk28_model_fits", "evaluated_model_fits"]:
        training_delta = max(training_delta, float(np.max(np.abs(training_compare[f"{column}_production"] - training_compare[f"{column}_independent"]))))
    check("all_50_training_log_rows", len(training_compare) == 50 and training_delta < 1e-12, {"rows": len(training_compare), "max_abs_diff": training_delta})
    check("training_log_no_cluster_leakage", not production_training["cluster_leakage"].any(), {"rows": len(production_training)})
    check("fit_accounting", production_summary["new_model_fits"] == 200 and production_summary["reused_rk28_model_fits"] == 200 and production_summary["evaluated_model_fits"] == 400, {"new": 200, "reused": 200, "evaluated": 400})
    for key in ["bootstrap_cluster_indices", "permutation_cluster_signs"]:
        equal = bool(np.array_equal(production_arrays[key], independent_arrays[key]))
        check(f"resampling_indices_{key}", equal, {"shape": list(independent_arrays[key].shape), "exact": equal})
    array_delta = 0.0
    for name in TEST_ORDER:
        for prefix in ["bootstrap", "permutation"]:
            key = f"{prefix}__{name}"
            delta = float(np.max(np.abs(production_arrays[key] - independent_arrays[key])))
            array_delta = max(array_delta, delta)
            check(f"resampling_values_{key}", delta < 1e-8, {"max_abs_diff": delta, "n": len(independent_arrays[key])})
    production_tests = {row["test"]: row for row in production_summary["primary_tests"]}
    test_delta = 0.0
    for test in independent_tests:
        reference = production_tests[test["test"]]
        deltas = {"observed_effect": abs(test["observed_effect"] - reference["observed_effect"]), "ci95_low": abs(test["ci95"][0] - reference["ci95"][0]), "ci95_high": abs(test["ci95"][1] - reference["ci95"][1]), "p_cluster_swap": abs(test["p_cluster_swap"] - reference["p_cluster_swap"]), "p_holm": abs(test["p_holm"] - reference["p_holm"])}
        test_delta = max(test_delta, max(deltas.values()))
        same = max(deltas.values()) < 1e-8 and test["positive_seeds"] == reference["positive_seeds"] and test["pass"] == reference["pass"]
        check(f"primary_test_{test['test']}", same, {"deltas": deltas, "independent_pass": test["pass"], "production_pass": reference["pass"]})
    check("family_gate_agreement", family_pass == production_summary["family_pass"], {"independent": family_pass, "production": production_summary["family_pass"]})
    check("scientific_conclusion_agreement", independent_conclusion == production_summary["scientific_conclusion"], {"independent": independent_conclusion, "production": production_summary["scientific_conclusion"]})
    check("scientific_boundaries", production_summary["scientific_flags"] == protocol["scientific_boundaries"] and not production_summary["scientific_flags"]["exact_kudla_start_aware_transport"] and not production_summary["scientific_flags"]["rk_g1_complete"], production_summary["scientific_flags"])

    outputs = {path.name: {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size} for path in output_paths.values()}
    report = {
        "schema": "a8-rk33-local-coverage-independent-v1", "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": float(time.perf_counter() - wall_start),
        "production_summary_sha256": digest(args.production_summary), "protocol_sha256": digest(args.protocol), "preflight_report_sha256": digest(args.preflight_report),
        "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks),
        "failed_checks": [row["name"] for row in checks if not row["pass"]], "independent_conclusion": independent_conclusion, "family_pass": family_pass,
        "independent_tests": independent_tests, "independent_outputs": outputs,
        "max_abs_deltas": {"analysis": max(analysis_deltas.values()), "predictions": max(prediction_deltas.values()), "seed_effects": effect_delta, "inference_arrays": array_delta, "primary_tests": test_delta},
        "new_model_fits": 200, "reused_rk28_model_fits": 200, "evaluated_model_fits": 400,
        "independent_implementation": "Raw-source clustering and outcomes; StandardScaler/Ridge and separately constructed HistGB; SciPy Spearman and independent generalized resampling; no RK33 production import.",
        "scientific_flags": protocol["scientific_boundaries"],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f'{report["checks_passed"]}/{report["checks_total"]}', "failed_checks": report["failed_checks"], "independent_conclusion": independent_conclusion, "family_pass": family_pass, "max_abs_deltas": report["max_abs_deltas"], "elapsed_seconds": report["elapsed_seconds"], "report": str(args.report)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
