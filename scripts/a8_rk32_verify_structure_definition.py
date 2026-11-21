#!/usr/bin/env python3
"""Independent raw-data and model recomputation for the frozen RK32 experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rho(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = rankdata(a), rankdata(b)
    da, db = ra - np.mean(ra), rb - np.mean(rb)
    denominator = math.sqrt(float(np.dot(da, da) * np.dot(db, db)))
    return float(np.dot(da, db) / denominator) if denominator else float("nan")


def vienna(sequence: str, dangles: int) -> float:
    md = RNA.md()
    md.dangles = dangles
    md.temperature = 37.0
    return float(RNA.fold_compound(sequence.replace("T", "U"), md).mfe()[1])


def independent_folds(labels: np.ndarray, seed: int) -> tuple[np.ndarray, list[int]]:
    rng = np.random.default_rng(seed)
    identifiers = sorted(set(int(x) for x in labels))
    shuffled = [identifiers[i] for i in rng.permutation(len(identifiers))]
    shuffled.sort(key=lambda c: -int(np.sum(labels == c)))
    loads = [0] * 5
    mapping = {}
    for cluster in shuffled:
        minimum = min(loads)
        choices = [i for i, value in enumerate(loads) if value == minimum]
        chosen = int(rng.choice(choices))
        mapping[cluster] = chosen
        loads[chosen] += int(np.sum(labels == cluster))
    return np.array([mapping[int(x)] for x in labels], dtype=int), loads


def predict(model: str, columns: list[str], train: pd.DataFrame, test: pd.DataFrame, state: int) -> np.ndarray:
    if model == "ridge":
        estimator = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    else:
        estimator = HistGradientBoostingRegressor(
            loss="squared_error", learning_rate=0.05, max_iter=200,
            max_leaf_nodes=7, min_samples_leaf=10, l2_regularization=1.0,
            early_stopping=False, random_state=state,
        )
    estimator.fit(train[columns], train["target"])
    return np.asarray(estimator.predict(test[columns]), dtype=float)


def holm_independent(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    previous = 0.0
    for rank, (index, value) in enumerate(indexed):
        previous = max(previous, (len(values) - rank) * value)
        result[index] = min(1.0, previous)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    started = time.perf_counter()
    checks = []
    def check(name: str, passed: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    protocol = json.loads(args.protocol.read_text())
    result = json.loads(args.result.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    check("protocol_result_hash", result["protocol_sha256"] == digest(args.protocol), result["protocol_sha256"])
    check("production_fit_accounting", result["total_model_fits"] == 700, result["total_model_fits"])
    check("production_test_accounting", len(result["primary_tests"]) == 24, len(result["primary_tests"]))
    check("analysis_type", result["analysis_type"] == "retrospective_outcome_known_followup_not_independent_confirmation", result["analysis_type"])

    source_path = Path(protocol["inputs"]["main_csv"]["path"])
    coverage_path = Path(protocol["inputs"]["coverage_report"]["path"])
    check("source_hash", digest(source_path) == protocol["inputs"]["main_csv"]["sha256"], digest(source_path))
    check("coverage_hash", digest(coverage_path) == protocol["inputs"]["coverage_report"]["sha256"], digest(coverage_path))
    columns = [
        "source_row", "seqId", "sequenceWithUtr", "utr_5prime", "cds", "protein_aa",
        "CAI", "log10_expression", "mfe_5prime_kcal_mol", "rna_energy_entire_prot_kcal_mol", "cds_sha256",
    ]
    raw = pd.read_csv(source_path, usecols=columns)
    records = []
    for cds_hash, group in raw.groupby("cds_sha256", sort=False):
        cds = str(group["cds"].iloc[0]).upper()
        utr = str(group["utr_5prime"].iloc[0]).upper()
        full = str(group["sequenceWithUtr"].iloc[0]).upper()
        assert hashlib.sha256(cds.encode()).hexdigest() == cds_hash
        assert len(utr) == 144 and len(cds) == 720 and len(full) == 864 and full == utr + cds
        assert group["protein_aa"].nunique() == 1
        for name in ("CAI", "mfe_5prime_kcal_mol", "rna_energy_entire_prot_kcal_mol"):
            assert group[name].nunique(dropna=False) == 1
        letters = np.array(list(cds))
        local = vienna(utr[-4:] + cds[:38], 2)
        full_cds = vienna(cds, 2)
        full_mrna = vienna(full, 2)
        windows = np.array([vienna(cds[i:i + 48], 0) for i in range(253)], dtype=float)
        records.append({
            "cds_sha256": cds_hash,
            "first_source_row": int(group["source_row"].min()),
            "CAI": float(group["CAI"].iloc[0]),
            "gc_cds": float(np.mean((letters == "G") | (letters == "C"))),
            "gc3_cds": float(np.mean((letters[2::3] == "G") | (letters[2::3] == "C"))),
            "mfe_5prime_kcal_mol": float(group["mfe_5prime_kcal_mol"].iloc[0]),
            "rna_energy_entire_prot_kcal_mol": float(group["rna_energy_entire_prot_kcal_mol"].iloc[0]),
            "vienna_local_mfe": local,
            "vienna_full_cds_mfe": full_cds,
            "vienna_full_mrna_mfe": full_mrna,
            "mfe_cds300": vienna(cds[:300], 0),
            "mfe_cds48_min": float(windows.min()),
            "mfe_cds48_mean": float(windows.mean()),
            "target": float(group["log10_expression"].mean()),
        })
    independent = pd.DataFrame(records).sort_values("first_source_row").reset_index(drop=True)
    independent.insert(0, "group_id", [f"g{i:03d}" for i in range(len(independent))])
    coverage = json.loads(coverage_path.read_text())
    facts_path = Path(coverage["facts_csv"])
    facts = pd.read_csv(facts_path)
    independent = independent.merge(facts[["cds_sha256", "sequence_cluster_id"]], on="cds_sha256", validate="one_to_one")
    independent["sequence_cluster_id"] = independent["sequence_cluster_id"].astype(int)
    check("raw_cohort", len(independent) == 150 and independent["sequence_cluster_id"].nunique() == 37, {"rows": len(independent), "clusters": independent["sequence_cluster_id"].nunique()})

    produced_analysis = pd.read_csv(args.output_root / "analysis_structure_definitions_150.csv")
    merged = independent.merge(produced_analysis, on=["group_id", "cds_sha256"], suffixes=("_ind", "_prod"), validate="one_to_one")
    feature_columns = ["CAI", "gc_cds", "gc3_cds", "target"] + sum(protocol["structure_features"].values(), [])
    feature_delta = 0.0
    for name in feature_columns:
        feature_delta = max(feature_delta, float(np.max(np.abs(merged[f"{name}_ind"].to_numpy(float) - merged[f"{name}_prod"].to_numpy(float)))))
    check("raw_feature_recomputation", feature_delta <= 1e-8, {"max_abs_delta": feature_delta, "features": feature_columns})

    produced_assignments = pd.read_csv(args.output_root / "fold_assignments.csv")
    produced_predictions = pd.read_csv(args.output_root / "oof_predictions.csv")
    simple = protocol["simple_features"]
    arms = protocol["structure_features"]
    feature_sets = {"simple": simple, **{name: simple + values for name, values in arms.items()}}
    seeds = protocol["outer_evaluation"]["seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    independent_predictions = []
    fold_mismatches = 0
    leakage_failures = 0
    for seed in seeds:
        fold, loads = independent_folds(independent["sequence_cluster_id"].to_numpy(int), seed)
        current_assignments = produced_assignments[produced_assignments["seed"] == seed].sort_values("group_id")
        fold_mismatches += int(np.sum(fold != current_assignments["fold"].to_numpy(int)))
        if seed == primary_seed:
            check("primary_fold_loads", loads == coverage["selected_coverage"]["primary_seed_fold_sizes"], loads)
        current = independent[["group_id", "cds_sha256", "sequence_cluster_id", "target"]].copy()
        current.insert(0, "seed", seed)
        current["fold"] = fold
        current["null"] = np.nan
        for model in ("ridge", "histgb"):
            for label in feature_sets:
                current[f"{model}_{label}"] = np.nan
        for fold_id in range(5):
            train = independent[fold != fold_id]
            test = independent[fold == fold_id]
            leakage_failures += int(not set(train["sequence_cluster_id"]).isdisjoint(test["sequence_cluster_id"]))
            indices = current.index[fold == fold_id]
            current.loc[indices, "null"] = float(train["target"].mean())
            for model in ("ridge", "histgb"):
                for label, features in feature_sets.items():
                    current.loc[indices, f"{model}_{label}"] = predict(model, features, train, test, seed + fold_id)
        independent_predictions.append(current)
    independent_predictions = pd.concat(independent_predictions, ignore_index=True)
    check("fold_recomputation", fold_mismatches == 0, fold_mismatches)
    check("cluster_leakage", leakage_failures == 0, leakage_failures)
    prediction_columns = ["null"] + [f"{model}_{label}" for model in ("ridge", "histgb") for label in feature_sets]
    aligned = independent_predictions.merge(produced_predictions, on=["seed", "group_id"], suffixes=("_ind", "_prod"), validate="one_to_one")
    prediction_delta = 0.0
    for name in prediction_columns:
        prediction_delta = max(prediction_delta, float(np.max(np.abs(aligned[f"{name}_ind"].to_numpy(float) - aligned[f"{name}_prod"].to_numpy(float)))))
    check("independent_700_fit_predictions", len(aligned) == 1500 and prediction_delta <= 1e-10, {"rows": len(aligned), "max_abs_delta": prediction_delta})

    produced_metrics = pd.read_csv(args.output_root / "seed_metrics.csv")
    produced_metrics["arm"] = produced_metrics["arm"].fillna("null")
    produced_effects = pd.read_csv(args.output_root / "seed_effects.csv")
    metric_delta = 0.0
    effect_delta = 0.0
    independent_effects = []
    for seed in seeds:
        current = independent_predictions[independent_predictions["seed"] == seed]
        y = current["target"].to_numpy(float)
        for name in prediction_columns:
            pred = current[name].to_numpy(float)
            expected = produced_metrics[(produced_metrics["seed"] == seed) & (produced_metrics["arm"] == name)].iloc[0]
            sp, mse = rho(y, pred), float(np.mean((y - pred) ** 2))
            if np.isfinite(sp) and np.isfinite(expected["spearman"]):
                metric_delta = max(metric_delta, abs(sp - float(expected["spearman"])))
            else:
                check(f"null_metric_definition_{seed}_{name}", np.isnan(sp) and np.isnan(expected["spearman"]), "both undefined")
            metric_delta = max(metric_delta, abs(mse - float(expected["mse"])))
        for model in ("ridge", "histgb"):
            base = current[f"{model}_simple"].to_numpy(float)
            for arm in arms:
                pred = current[f"{model}_{arm}"].to_numpy(float)
                independent_effects.extend([
                    {"seed": seed, "test": f"{model}__{arm}__spearman_effect", "effect": rho(y, pred) - rho(y, base)},
                    {"seed": seed, "test": f"{model}__{arm}__mse_improvement", "effect": float(np.mean((y - base) ** 2 - (y - pred) ** 2))},
                ])
    independent_effects = pd.DataFrame(independent_effects)
    effect_alignment = independent_effects.merge(produced_effects, on=["seed", "test"], suffixes=("_ind", "_prod"), validate="one_to_one")
    effect_delta = float(np.max(np.abs(effect_alignment["effect_ind"] - effect_alignment["effect_prod"])))
    check("seed_metric_recomputation", metric_delta <= 1e-12, metric_delta)
    check("seed_effect_recomputation", len(effect_alignment) == 240 and effect_delta <= 1e-12, {"rows": len(effect_alignment), "max_abs_delta": effect_delta})

    primary = independent_predictions[independent_predictions["seed"] == primary_seed].reset_index(drop=True)
    y = primary["target"].to_numpy(float)
    labels = primary["sequence_cluster_id"].to_numpy(int)
    clusters = sorted(set(int(x) for x in labels))
    cluster_index = np.array([clusters.index(int(x)) for x in labels], dtype=int)
    members = [np.flatnonzero(cluster_index == i) for i in range(len(clusters))]
    inference = protocol["primary_inference"]
    count = inference["resamples"]
    boot_clusters = np.random.default_rng(inference["bootstrap_seed"]).integers(0, len(clusters), size=(count, len(clusters)), dtype=np.int16)
    perm_signs = np.random.default_rng(inference["permutation_seed"]).choice(np.array([-1, 1], dtype=np.int8), size=(count, len(clusters)))
    test_names = [f"{model}__{arm}__{metric}" for model in ("ridge", "histgb") for arm in arms for metric in ("spearman_effect", "mse_improvement")]
    observed = {name: 0.0 for name in test_names}
    boot = {name: np.zeros(count, dtype=float) for name in test_names}
    null = {name: np.zeros(count, dtype=float) for name in test_names}
    pairs = {}
    for model in ("ridge", "histgb"):
        base = primary[f"{model}_simple"].to_numpy(float)
        for arm in arms:
            pred = primary[f"{model}_{arm}"].to_numpy(float)
            diff = (y - base) ** 2 - (y - pred) ** 2
            sp_name = f"{model}__{arm}__spearman_effect"
            mse_name = f"{model}__{arm}__mse_improvement"
            observed[sp_name] = rho(y, pred) - rho(y, base)
            observed[mse_name] = float(diff.mean())
            null[mse_name] = (perm_signs[:, cluster_index] * diff).mean(axis=1)
            pairs[(model, arm)] = (base, pred, diff)
    for b in range(count):
        selected = boot_clusters[b]
        rows = np.concatenate([members[int(c)] for c in selected])
        weights = np.bincount(selected, minlength=len(clusters))[cluster_index].astype(float)
        signs = perm_signs[b, cluster_index] < 0
        for model in ("ridge", "histgb"):
            for arm in arms:
                base, pred, diff = pairs[(model, arm)]
                sp_name = f"{model}__{arm}__spearman_effect"
                mse_name = f"{model}__{arm}__mse_improvement"
                boot[sp_name][b] = rho(y[rows], pred[rows]) - rho(y[rows], base[rows])
                boot[mse_name][b] = float(np.dot(weights, diff) / weights.sum())
                swapped_base = np.where(signs, pred, base)
                swapped_pred = np.where(signs, base, pred)
                null[sp_name][b] = rho(y, swapped_pred) - rho(y, swapped_base)

    with np.load(args.output_root / "primary_inference_arrays.npz") as saved:
        inference_delta = 0.0
        check("bootstrap_indices", np.array_equal(saved["bootstrap_cluster_indices"], boot_clusters), "exact")
        check("permutation_signs", np.array_equal(saved["permutation_cluster_signs"], perm_signs), "exact")
        for name in test_names:
            inference_delta = max(inference_delta, float(np.max(np.abs(saved[f"bootstrap__{name}"] - boot[name]))))
            inference_delta = max(inference_delta, float(np.max(np.abs(saved[f"permutation__{name}"] - null[name]))))
    check("independent_inference_arrays", inference_delta <= 1e-12, inference_delta)

    p_values = [float((1 + np.sum(np.abs(null[name]) >= abs(observed[name]))) / (count + 1)) for name in test_names]
    adjusted = holm_independent(p_values)
    result_by_name = {row["test"]: row for row in result["primary_tests"]}
    summary_delta = 0.0
    pass_mismatches = 0
    for name, p_raw, p_holm in zip(test_names, p_values, adjusted):
        expected = result_by_name[name]
        ci = [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))]
        values = [observed[name], *ci, p_raw, p_holm, float(np.median(boot[name]))]
        reference = [expected["observed_effect"], *expected["ci95"], expected["p_cluster_swap"], expected["p_holm"], expected["bootstrap_median"]]
        summary_delta = max(summary_delta, max(abs(a - b) for a, b in zip(values, reference)))
        effects = independent_effects[independent_effects["test"] == name].sort_values("seed")["effect"].to_numpy(float)
        passed = observed[name] > 0 and ci[0] > 0 and p_holm < 0.05 and int(np.sum(effects > 0)) >= 8
        pass_mismatches += int(passed != expected["pass"])
        pass_mismatches += int(int(np.sum(effects > 0)) != expected["positive_seeds"])
        pass_mismatches += int(float(np.max(np.abs(effects - np.asarray(expected["seed_effects"], dtype=float)))) > 1e-12)
    check("primary_summary_recomputation", summary_delta <= 1e-12, summary_delta)
    check("pass_seed_and_gate_recomputation", pass_mismatches == 0, pass_mismatches)

    independent_arms = []
    for arm in arms:
        rows = [result_by_name[f"{model}__{arm}__{metric}"] for model in ("ridge", "histgb") for metric in ("spearman_effect", "mse_improvement")]
        independent_arms.append({"arm": arm, "n_tests": 4, "n_pass": sum(row["pass"] for row in rows), "all_four_pass": all(row["pass"] for row in rows)})
    check("arm_conclusion_recomputation", independent_arms == result["arm_results"], independent_arms)
    supported = sum(row["all_four_pass"] for row in independent_arms)
    conclusion = "ALL_STRUCTURE_DEFINITIONS_SUPPORTED_RETROSPECTIVELY" if supported == 6 else ("STRUCTURE_INCREMENT_DEFINITION_DEPENDENT_RETROSPECTIVELY" if supported else "NO_STRUCTURE_DEFINITION_SUPPORTED_RETROSPECTIVELY")
    check("scientific_conclusion", conclusion == result["scientific_conclusion"], conclusion)

    output_hash_failures = []
    for name, item in result["outputs"].items():
        path = args.output_root / name
        if not path.exists() or digest(path) != item["sha256"]:
            output_hash_failures.append(name)
    check("output_hashes", not output_hash_failures, output_hash_failures)
    training = pd.read_csv(args.output_root / "training_log.csv")
    check("training_log", len(training) == 50 and int(training["model_fits"].sum()) == 700 and not training["cluster_leakage"].any(), {"rows": len(training), "fits": int(training["model_fits"].sum())})

    report = {
        "schema": "a8-rk32-structure-definition-independent-v1",
        "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": digest(args.protocol),
        "production_result_sha256": digest(args.result),
        "independent_script_sha256": digest(Path(__file__).resolve()),
        "component_wall_seconds": float(time.perf_counter() - started),
        "checks": checks,
        "max_deltas": {"features": feature_delta, "predictions": prediction_delta, "metrics": metric_delta, "effects": effect_delta, "inference": inference_delta, "summary": summary_delta},
        "scientific_conclusion": conclusion,
        "independent_confirmation": False,
        "functional_untouched_read": False,
        "RK_G1_complete": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.report.with_suffix(args.report.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(args.report)
    print(json.dumps({"status": report["status"], "checks": len(checks), "failed": [row for row in checks if not row["pass"]], "max_deltas": report["max_deltas"], "scientific_conclusion": conclusion}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
