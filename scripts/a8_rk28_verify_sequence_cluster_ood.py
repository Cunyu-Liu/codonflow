#!/usr/bin/env python3
"""Independent RK28 verifier; no production/coverage/RK02 module is imported.

Rebuilds observed-R1 clusters, CAI and ViennaRNA features, all 300 model fits,
and all resampling from raw inputs before loading production outputs.
"""
from pathlib import Path
import argparse
import ast
from collections import Counter
import hashlib
import json
import math

import numpy as np
import pandas as pd
import RNA
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


BASES = "TCAG"
AA_ROWS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODONS = {}
for first_index, first in enumerate(BASES):
    for second_index, second in enumerate(BASES):
        for third_index, third in enumerate(BASES):
            CODONS[first + second + third] = AA_ROWS[first_index * 16 + second_index * 4 + third_index]
STOPS = {codon for codon, aa in CODONS.items() if aa == "*"}
SYNONYMOUS = {codon: sorted(other for other, aa in CODONS.items() if aa == CODONS[codon] and aa != "*") for codon in CODONS if codon not in STOPS}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_fasta_independent(path):
    records, current = {}, None
    for line in Path(path).read_text().splitlines():
        if line.startswith(">"):
            current = line[1:].split()[0]
            records[current] = ""
        else:
            records[current] += line.strip()
    return records


def literal_variable(path, variable):
    for node in ast.parse(Path(path).read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == variable for target in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(variable)


def independent_cai_weights(reference_strings):
    counts = Counter()
    for reference in reference_strings:
        reference = reference.upper()
        assert reference and len(reference) % 3 == 0
        counts.update(reference[index:index + 3] for index in range(0, len(reference), 3))
    for codon in CODONS:
        if codon not in STOPS and counts[codon] == 0:
            counts[codon] = 0.5
    rscu = {}
    for codon in CODONS:
        if codon in STOPS:
            continue
        family = SYNONYMOUS[codon]
        rscu[codon] = counts[codon] / (sum(counts[other] for other in family) / len(family))
    return {codon: rscu[codon] / max(rscu[other] for other in SYNONYMOUS[codon]) for codon in rscu}


def independent_cai(sequence, weights):
    log_values = []
    for index in range(0, len(sequence), 3):
        codon = sequence[index:index + 3]
        if codon in STOPS or codon in {"ATG", "TGG"}:
            continue
        value = float(weights[codon])
        assert math.isfinite(value) and value > 0
        log_values.append(math.log(value))
    assert log_values
    return math.exp(sum(log_values) / len(log_values))


def independent_features(sequence, total, weights):
    assert len(sequence) == 300 and set(sequence) <= set("ACGT")
    rna = sequence.replace("T", "U")
    md = RNA.md()
    md.dangles = 0
    md.temperature = 37.0
    full = float(RNA.fold_compound(rna, md).mfe()[1])
    windows = [float(RNA.fold_compound(rna[start:start + 48], md).mfe()[1]) for start in range(253)]
    assert math.isfinite(full) and abs(full) < 100000
    assert all(math.isfinite(value) and abs(value) < 100000 for value in windows)
    return {
        "log1p_total_assigned_reads": math.log1p(total),
        "gc3_observed_5prime": sum(base in "GC" for base in sequence[2::3]) / 100.0,
        "gc_observed_5prime": sum(base in "GC" for base in sequence) / 300.0,
        "cpg_per_100nt_observed_5prime": 100.0 * sum(sequence[index:index + 2] == "CG" for index in range(299)) / 299.0,
        "cai_human_def_refs_observed_r1": independent_cai(sequence, weights),
        "mfe_observed_r1_full_kcal_mol": full,
        "mfe_observed_r1_window48_min_kcal_mol": min(windows),
        "mfe_observed_r1_window48_mean_kcal_mol": float(np.mean(windows)),
    }


def corr(a, b):
    return float(spearmanr(np.asarray(a, float), np.asarray(b, float)).statistic)


def assign_folds(labels, seed):
    unique = sorted(set(int(value) for value in labels))
    rng = np.random.default_rng(seed)
    shuffled = list(np.array(unique, dtype=int)[rng.permutation(len(unique))])
    ordered = sorted(shuffled, key=lambda cluster: -int(np.count_nonzero(labels == cluster)))
    loads, mapping = [0] * 5, {}
    for cluster in ordered:
        choices = [index for index, load in enumerate(loads) if load == min(loads)]
        fold = int(rng.choice(np.array(choices, dtype=int)))
        mapping[int(cluster)] = fold
        loads[fold] += int(np.count_nonzero(labels == cluster))
    return np.array([mapping[int(value)] for value in labels], dtype=int), loads


def independent_holm(values):
    p = np.asarray(values, float)
    order = np.argsort(p)
    output = np.zeros(len(p), float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        output[index] = min(1.0, running)
    return output


def independent_statistics(primary, clusters, resamples, boot_seed, perm_seed):
    y = primary["target"].to_numpy(float)
    unique = np.array(sorted(set(int(value) for value in clusters)), dtype=int)
    positions = np.searchsorted(unique, clusters)
    members = [np.where(positions == index)[0] for index in range(len(unique))]
    boot_ids = np.random.default_rng(boot_seed).integers(0, len(unique), size=(resamples, len(unique)), dtype=np.int16)
    signs = np.random.default_rng(perm_seed).choice(np.array([-1, 1], dtype=np.int8), size=(resamples, len(unique)))
    names = ["ridge_spearman_effect", "ridge_mse_improvement", "histgb_spearman_effect", "histgb_mse_improvement"]
    boot = {name: np.zeros(resamples, float) for name in names}
    null = {name: np.zeros(resamples, float) for name in names}
    observed = {}
    for model in ["ridge", "histgb"]:
        simple = primary[f"{model}_simple"].to_numpy(float)
        structure = primary[f"{model}_structure"].to_numpy(float)
        observed[f"{model}_spearman_effect"] = corr(y, structure) - corr(y, simple)
        difference = (simple - y) ** 2 - (structure - y) ** 2
        observed[f"{model}_mse_improvement"] = float(np.mean(difference))
        null[f"{model}_mse_improvement"] = np.mean(signs[:, positions] * difference, axis=1)
    for b in range(resamples):
        chosen = boot_ids[b]
        rows = np.concatenate([members[int(cluster)] for cluster in chosen])
        weights = np.bincount(chosen, minlength=len(unique))[positions]
        swap = signs[b, positions] == -1
        for model in ["ridge", "histgb"]:
            simple = primary[f"{model}_simple"].to_numpy(float)
            structure = primary[f"{model}_structure"].to_numpy(float)
            boot[f"{model}_spearman_effect"][b] = corr(y[rows], structure[rows]) - corr(y[rows], simple[rows])
            difference = (simple - y) ** 2 - (structure - y) ** 2
            boot[f"{model}_mse_improvement"][b] = float(np.sum(weights * difference) / np.sum(weights))
            perm_simple, perm_structure = simple.copy(), structure.copy()
            perm_simple[swap], perm_structure[swap] = structure[swap], simple[swap]
            null[f"{model}_spearman_effect"][b] = corr(y, perm_structure) - corr(y, perm_simple)
    raw_p = [float((1 + np.count_nonzero(np.abs(null[name]) >= abs(observed[name]))) / (resamples + 1)) for name in names]
    adjusted = independent_holm(raw_p)
    tests = []
    for index, name in enumerate(names):
        tests.append({
            "test": name, "observed_effect": float(observed[name]),
            "ci95": [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))],
            "p_cluster_swap": raw_p[index], "p_holm": float(adjusted[index]),
            "bootstrap_median": float(np.median(boot[name])),
        })
    arrays = {f"bootstrap__{name}": boot[name] for name in names}
    arrays.update({f"permutation__{name}": null[name] for name in names})
    arrays["bootstrap_cluster_indices"], arrays["permutation_cluster_signs"] = boot_ids, signs
    return tests, arrays


def main():
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
    cai_path = Path(protocol["inputs"]["cai_wrapper"]["path"])
    fasta_path = Path(protocol["inputs"]["references_r1_fasta"]["path"])
    assert digest(source_path) == protocol["inputs"]["main_csv"]["sha256"]
    assert digest(cai_path) == protocol["inputs"]["cai_wrapper"]["sha256"]
    assert digest(fasta_path) == protocol["inputs"]["references_r1_fasta"]["sha256"]
    references = literal_variable(cai_path, protocol["inputs"]["cai_wrapper"]["reference_variable"])
    weights = independent_cai_weights(references)
    fasta = read_fasta_independent(fasta_path)
    source = pd.read_csv(source_path, keep_default_na=False)
    assert len(source) == 152 and source["variant_id"].is_unique
    rows, proteins = [], set()
    for record in source.to_dict("records"):
        variant = str(record["variant_id"])
        sequence = str(record["sequence_5prime_300nt"]).upper()
        assert fasta[variant] == sequence
        counts = [int(record[f"counts_bin{index}"]) for index in range(1, 9)]
        total = int(np.sum(counts))
        assert total == int(record["r1_assigned_reads"]) and total >= 1000
        target = float(np.dot(np.arange(1, 9), counts) / total)
        assert abs(target - float(record["flowseq_score_r1_only"])) <= 1e-12
        proteins.add("".join(CODONS[sequence[index:index + 3]] for index in range(0, 300, 3)))
        row = {"variant_id": variant, "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(), "total_assigned_reads": total, "target": target}
        row.update(independent_features(sequence, total, weights))
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
    facts = pd.read_csv(coverage["facts_csv"])
    cluster_comparison = units[["variant_id", "sequence_cluster_id"]].merge(facts[["variant_id", "sequence_cluster_id"]], on="variant_id", suffixes=("_independent", "_coverage"), validate="one_to_one")
    cluster_mismatches = int((cluster_comparison["sequence_cluster_id_independent"] != cluster_comparison["sequence_cluster_id_coverage"]).sum())
    assert cluster_mismatches == 0
    units.to_csv(args.independent_root / "analysis_variants_152.csv", index=False)

    simple_features = protocol["models"]["feature_sets"]["simple"]
    structure_features = simple_features + protocol["models"]["feature_sets"]["structure_addition"]
    mfe_features = protocol["models"]["feature_sets"]["mfe_only_descriptive"]
    feature_sets = {"simple": simple_features, "structure": structure_features, "mfe_only": mfe_features}
    seeds = protocol["outer_evaluation"]["sensitivity_seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    independent_predictions, independent_assignments = [], []
    independent_metrics, independent_effects, independent_training = [], [], []
    arms = ["null", "ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"]
    for seed in seeds:
        folds, loads = assign_folds(cluster, seed)
        if seed == primary_seed:
            assert loads == coverage["selected_coverage"]["primary_seed_fold_sizes"]
        assignment = units[["variant_id", "sequence_cluster_id"]].copy()
        assignment.insert(0, "seed", seed)
        assignment["fold"] = folds
        independent_assignments.append(assignment)
        current = units[["variant_id", "sequence_cluster_id", "target"]].copy()
        current.insert(0, "seed", seed)
        current["fold"] = folds
        for arm in arms:
            current[arm] = np.nan
        for fold in range(5):
            train, test = units.loc[folds != fold], units.loc[folds == fold]
            assert set(train["sequence_cluster_id"]).isdisjoint(set(test["sequence_cluster_id"]))
            current.loc[current.index[folds == fold], "null"] = float(train["target"].mean())
            for model_name in ["ridge", "histgb"]:
                for label, features in feature_sets.items():
                    if model_name == "ridge":
                        x_scaler = StandardScaler().fit(train[features])
                        y_scaler = StandardScaler().fit(train[["target"]])
                        estimator = Ridge(alpha=1.0, solver="cholesky")
                        estimator.fit(x_scaler.transform(train[features]), y_scaler.transform(train[["target"]]).ravel())
                        prediction = y_scaler.inverse_transform(estimator.predict(x_scaler.transform(test[features])).reshape(-1, 1)).ravel()
                    else:
                        estimator = HistGradientBoostingRegressor(
                            loss="squared_error", learning_rate=0.05, max_iter=200,
                            max_leaf_nodes=7, min_samples_leaf=10, l2_regularization=1.0,
                            early_stopping=False, random_state=int(seed + fold),
                        )
                        estimator.fit(train[features], train["target"])
                        prediction = estimator.predict(test[features])
                    current.loc[current.index[folds == fold], f"{model_name}_{label}"] = prediction
            independent_training.append({
                "seed": seed, "fold": fold, "n_train": len(train), "n_test": len(test),
                "n_train_clusters": train["sequence_cluster_id"].nunique(), "n_test_clusters": test["sequence_cluster_id"].nunique(),
                "train_target_mean": float(train["target"].mean()), "histgb_random_state": int(seed + fold),
                "model_fits": 6, "cluster_leakage": False,
            })
        independent_predictions.append(current)
        y = current["target"].to_numpy(float)
        for arm in arms:
            prediction = current[arm].to_numpy(float)
            independent_metrics.append({"seed": seed, "arm": arm, "spearman": corr(y, prediction), "mse": float(np.mean((prediction - y) ** 2))})
        for model in ["ridge", "histgb"]:
            simple = current[f"{model}_simple"].to_numpy(float)
            structure = current[f"{model}_structure"].to_numpy(float)
            independent_effects.append({"seed": seed, "test": f"{model}_spearman_effect", "effect": corr(y, structure) - corr(y, simple)})
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
        primary, primary["sequence_cluster_id"].to_numpy(int), inf["cluster_bootstrap"]["resamples"],
        inf["cluster_bootstrap"]["seed"], inf["cluster_swap_permutation"]["seed"],
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
    independent_conclusion = protocol["result_interpretation"]["pass"] if independent_pass else protocol["result_interpretation"]["fail"]

    # Production results are loaded only after every independent computation finishes.
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

    check("source_sha256", digest(source_path) == production_summary["source_csv_sha256"], digest(source_path))
    check("protocol_sha256", digest(args.protocol) == production_summary["protocol_sha256"], digest(args.protocol))
    check("coverage_sha256", digest(args.coverage_report) == production_summary["coverage_report_sha256"], digest(args.coverage_report))
    check("feature_implementation_hash_bound", digest(Path(protocol["inputs"]["rk02_feature_implementation"]["path"])) == production_summary["feature_implementation_sha256"], production_summary["feature_implementation_sha256"])
    check("sample_chain", len(source) == 152 and len(units) == 152 and len(set(cluster)) == 74 and len(proteins) == 1, {"variants": len(units), "clusters": len(set(cluster)), "observed_protein_groups": len(proteins)})
    check("cluster_assignment_exact", cluster_mismatches == 0, {"mismatches": cluster_mismatches})
    analysis_compare = production_analysis.merge(units, on="variant_id", suffixes=("_production", "_independent"), validate="one_to_one")
    check("analysis_row_coverage", len(analysis_compare) == 152, len(analysis_compare))
    analysis_features = ["total_assigned_reads", "target"] + simple_features + protocol["models"]["feature_sets"]["structure_addition"]
    for feature in analysis_features:
        delta = float(np.max(np.abs(analysis_compare[f"{feature}_production"] - analysis_compare[f"{feature}_independent"])))
        check(f"analysis_{feature}", delta < 1e-10, {"max_abs_diff": delta})
    assignment_compare = production_assignments.merge(independent_assignments, on=["seed", "variant_id"], suffixes=("_production", "_independent"), validate="one_to_one")
    assignment_mismatches = int((assignment_compare["fold_production"] != assignment_compare["fold_independent"]).sum())
    check("all_1520_fold_assignments_exact", len(assignment_compare) == 1520 and assignment_mismatches == 0, {"rows": len(assignment_compare), "mismatches": assignment_mismatches})
    prediction_compare = production_predictions.merge(independent_predictions, on=["seed", "variant_id"], suffixes=("_production", "_independent"), validate="one_to_one")
    check("prediction_row_coverage", len(prediction_compare) == 1520, len(prediction_compare))
    for arm in arms:
        delta = float(np.max(np.abs(prediction_compare[f"{arm}_production"] - prediction_compare[f"{arm}_independent"])))
        check(f"predictions_{arm}", delta < 1e-9, {"max_abs_diff": delta, "n": 1520})
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
    check("scientific_pass_agreement", independent_pass == production_summary["sequence_cluster_ood_structure_increment_pass"], independent_pass)
    flags = production_summary["scientific_flags"]
    check("retrospective_boundary", flags["labels_previously_used_in_RK02_development"] and not flags["independent_untouched_confirmation"], flags)
    check("fragment_and_predicted_structure_boundary", not flags["complete_cds_observed"] and not flags["measured_structure"] and not flags["author_gfp_identity_mapping"], flags)
    check("no_functional_untouched_or_generator_authorization", not flags["functional_untouched_read"] and not flags["generator_training_authorized"] and not flags["rk_g1_complete"], flags)
    check("no_overclaim_velocity_decay_or_protein_ood", not flags["velocity_or_decay_measured"] and not flags["full_spatial_coupling_established"] and not flags["protein_ood"], flags)
    check("production_pending_status_before_this_verifier", production_summary["status"] == "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION", production_summary["status"])
    check("total_model_fits_recorded", production_summary["total_model_fits"] == 300 and production_summary["device"] == "CPU_ONLY", {"fits": production_summary["total_model_fits"], "device": production_summary["device"]})

    passed = all(row["pass"] for row in checks)
    report = {
        "schema": "a8-rk28-independent-verification-v1", "status": "PASS" if passed else "FAIL",
        "independent_verification_pass": passed, "n_checks": len(checks), "n_passed": int(sum(row["pass"] for row in checks)),
        "checks": checks, "independent_script_sha256": digest(Path(__file__).resolve()),
        "production_summary": str(args.production_summary), "production_summary_sha256": digest(args.production_summary),
        "independent_conclusion": independent_conclusion, "independent_sequence_cluster_ood_pass": independent_pass,
        "independent_primary_tests": independent_tests,
        "independent_outputs": {path.name: {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size} for path in sorted(args.independent_root.iterdir()) if path.is_file()},
        "implementation": {
            "production_module_imported": False, "coverage_module_imported": False, "rk02_module_imported": False,
            "clusters_rebuilt_from_raw_observed_r1": True, "features_rebuilt_from_raw_observed_r1": True,
            "all_models_refit": True, "all_resamples_recomputed": True, "functional_untouched_read": False,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "n_checks": len(checks), "n_passed": report["n_passed"], "independent_conclusion": independent_conclusion, "failed_checks": [row for row in checks if not row["pass"]], "independent_primary_tests": independent_tests}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
