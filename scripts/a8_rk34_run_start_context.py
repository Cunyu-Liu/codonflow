#!/usr/bin/env python3
"""RK34 frozen matched 42-nt start/upstream factorial ablation."""
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

CONTEXTS = ["exact_real", "start_only", "upstream_only", "neither"]
ARMS = [f"{context}_d{dangles}" for dangles in (2, 0) for context in CONTEXTS]
FAMILIES = [
    "exact_vs_simple", "upstream_given_start", "start_given_upstream",
    "start_without_upstream", "upstream_without_start",
]
MODELS = ["ridge", "histgb"]
METRICS = ["spearman_effect", "mse_improvement"]


def comparison_specs() -> list[dict[str, str]]:
    specs = []
    for analysis, dangles in (("primary", 2), ("sensitivity_d0", 0)):
        exact = f"exact_real_d{dangles}"
        start = f"start_only_d{dangles}"
        upstream = f"upstream_only_d{dangles}"
        neither = f"neither_d{dangles}"
        for family, arm_a, arm_b in (
            ("exact_vs_simple", exact, "simple"),
            ("upstream_given_start", exact, start),
            ("start_given_upstream", exact, upstream),
            ("start_without_upstream", start, neither),
            ("upstream_without_start", upstream, neither),
        ):
            specs.append({"analysis": analysis, "dangles": str(dangles), "family": family, "arm_a": arm_a, "arm_b": arm_b})
    return specs


COMPARISONS = comparison_specs()
TEST_ORDER = [
    f"{spec['analysis']}__{model}__{spec['family']}__{metric}"
    for spec in COMPARISONS for model in MODELS for metric in METRICS
]


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


def context_sequences(utr: str, cds: str) -> dict[str, str]:
    utr = utr.upper()
    cds = cds.upper()
    if len(utr) < 4 or len(cds) < 38:
        raise ValueError("insufficient UTR/CDS coverage")
    upstream, start, body = utr[-4:], cds[:3], cds[3:38]
    result = {
        "exact_real": upstream + start + body,
        "start_only": "NNNN" + start + body,
        "upstream_only": upstream + "NNN" + body,
        "neither": "NNNN" + "NNN" + body,
    }
    if set(result) != set(CONTEXTS) or any(len(value) != 42 for value in result.values()):
        raise AssertionError("matched context construction failure")
    return result


def cds_gc_features(cds: str) -> tuple[float, float]:
    sequence = np.array(list(cds.upper()))
    gc_mask = (sequence == "G") | (sequence == "C")
    return float(np.mean(gc_mask)), float(np.mean(gc_mask[2::3]))


def mfe(sequence: str, dangles: int) -> float:
    if dangles not in (0, 2):
        raise ValueError("unsupported dangles")
    md = RNA.md()
    md.dangles = dangles
    md.temperature = 37.0
    value = float(RNA.fold_compound(sequence.replace("T", "U"), md).mfe()[1])
    if not np.isfinite(value) or abs(value) >= 100000:
        raise ValueError("non-finite MFE")
    return value


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx = rankdata(np.asarray(x, dtype=float))
    ry = rankdata(np.asarray(y, dtype=float))
    dx, dy = rx - rx.mean(), ry - ry.mean()
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


def effect_names_for_seed(frame: pd.DataFrame, seed: int) -> tuple[list[dict[str, object]], dict[str, float]]:
    current = frame[frame["seed"] == seed]
    if len(current) == 0:
        raise ValueError("seed absent")
    y = current["target"].to_numpy(float)
    metrics = []
    value_columns = ["null"] + [f"{model}_{arm}" for model in MODELS for arm in ["simple"] + ARMS]
    for column in value_columns:
        pred = current[column].to_numpy(float)
        metrics.append({"seed": seed, "arm": column, "spearman": spearman(y, pred), "mse": float(np.mean((y - pred) ** 2))})
    effects: dict[str, float] = {}
    for spec in COMPARISONS:
        for model in MODELS:
            pred_a = current[f"{model}_{spec['arm_a']}"].to_numpy(float)
            pred_b = current[f"{model}_{spec['arm_b']}"].to_numpy(float)
            base = f"{spec['analysis']}__{model}__{spec['family']}"
            effects[f"{base}__spearman_effect"] = spearman(y, pred_a) - spearman(y, pred_b)
            effects[f"{base}__mse_improvement"] = float(np.mean((y - pred_b) ** 2 - (y - pred_a) ** 2))
    if list(effects) != TEST_ORDER:
        raise AssertionError("effect order mismatch")
    return metrics, effects


def run_inference(primary: pd.DataFrame, resamples: int, bootstrap_seed: int, permutation_seed: int) -> tuple[list[dict[str, object]], dict[str, np.ndarray]]:
    primary = primary.reset_index(drop=True)
    y = primary["target"].to_numpy(float)
    cluster_ids = primary["sequence_cluster_id"].to_numpy(int)
    unique_clusters = np.array(sorted(np.unique(cluster_ids)), dtype=int)
    cluster_index = np.searchsorted(unique_clusters, cluster_ids)
    cluster_rows = [np.flatnonzero(cluster_index == i) for i in range(len(unique_clusters))]
    boot_clusters = np.random.default_rng(bootstrap_seed).integers(0, len(unique_clusters), size=(resamples, len(unique_clusters)), dtype=np.int16)
    perm_signs = np.random.default_rng(permutation_seed).choice(np.array([-1, 1], dtype=np.int8), size=(resamples, len(unique_clusters)))
    observed = {name: 0.0 for name in TEST_ORDER}
    boot = {name: np.empty(resamples, dtype=float) for name in TEST_ORDER}
    null = {name: np.empty(resamples, dtype=float) for name in TEST_ORDER}
    pair_values = {}
    metadata = {}
    for spec in COMPARISONS:
        for model in MODELS:
            pred_a = primary[f"{model}_{spec['arm_a']}"].to_numpy(float)
            pred_b = primary[f"{model}_{spec['arm_b']}"].to_numpy(float)
            diff = (y - pred_b) ** 2 - (y - pred_a) ** 2
            base = f"{spec['analysis']}__{model}__{spec['family']}"
            sp_name, mse_name = f"{base}__spearman_effect", f"{base}__mse_improvement"
            observed[sp_name] = spearman(y, pred_a) - spearman(y, pred_b)
            observed[mse_name] = float(diff.mean())
            null[mse_name] = (perm_signs[:, cluster_index] * diff).mean(axis=1)
            pair_values[(spec["analysis"], model, spec["family"])] = (pred_a, pred_b, diff)
            for metric, name in (("spearman_effect", sp_name), ("mse_improvement", mse_name)):
                metadata[name] = {**spec, "model": model, "metric": metric}

    for b in range(resamples):
        selected_clusters = boot_clusters[b]
        row_index = np.concatenate([cluster_rows[int(c)] for c in selected_clusters])
        weights = np.bincount(selected_clusters, minlength=len(unique_clusters))[cluster_index].astype(float)
        signs = perm_signs[b, cluster_index] < 0
        for spec in COMPARISONS:
            for model in MODELS:
                pred_a, pred_b, diff = pair_values[(spec["analysis"], model, spec["family"])]
                base = f"{spec['analysis']}__{model}__{spec['family']}"
                sp_name, mse_name = f"{base}__spearman_effect", f"{base}__mse_improvement"
                boot[sp_name][b] = spearman(y[row_index], pred_a[row_index]) - spearman(y[row_index], pred_b[row_index])
                boot[mse_name][b] = float(np.dot(weights, diff) / weights.sum())
                swapped_a = np.where(signs, pred_b, pred_a)
                swapped_b = np.where(signs, pred_a, pred_b)
                null[sp_name][b] = spearman(y, swapped_a) - spearman(y, swapped_b)

    rows = []
    for name in TEST_ORDER:
        if not np.isfinite(boot[name]).all() or not np.isfinite(null[name]).all():
            raise ValueError(f"non-finite inference: {name}")
        obs = float(observed[name])
        rows.append({
            "test": name, **metadata[name], "observed_effect": obs,
            "ci95": [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))],
            "p_cluster_swap": float((1 + np.sum(np.abs(null[name]) >= abs(obs))) / (resamples + 1)),
            "bootstrap_median": float(np.median(boot[name])),
            "confirmatory": metadata[name]["analysis"] == "primary",
        })
    for analysis in ("primary", "sensitivity_d0"):
        indices = [i for i, row in enumerate(rows) if row["analysis"] == analysis]
        adjusted = holm([rows[i]["p_cluster_swap"] for i in indices])
        for i, p_holm in zip(indices, adjusted):
            rows[i]["p_holm"] = p_holm
    arrays = {f"bootstrap__{name}": values for name, values in boot.items()}
    arrays.update({f"permutation__{name}": values for name, values in null.items()})
    arrays["bootstrap_cluster_indices"] = boot_clusters
    arrays["permutation_cluster_signs"] = perm_signs
    return rows, arrays


def conclusion_for(family_pass: dict[str, bool]) -> str:
    exact = family_pass["exact_vs_simple"]
    upstream = family_pass["upstream_given_start"] and family_pass["upstream_without_start"]
    start = family_pass["start_given_upstream"] and family_pass["start_without_upstream"]
    if not exact:
        return "NO_EXACT_CONTEXT_INCREMENT_SUPPORTED_RETROSPECTIVELY"
    if upstream and start:
        return "START_AND_UPSTREAM_CONTRIBUTIONS_SUPPORTED_RETROSPECTIVELY"
    if upstream:
        return "UPSTREAM_BUT_NOT_START_CONTRIBUTION_SUPPORTED_RETROSPECTIVELY"
    if start:
        return "START_BUT_NOT_UPSTREAM_CONTRIBUTION_SUPPORTED_RETROSPECTIVELY"
    return "JOINT_EXACT_CONTEXT_WITHOUT_SEPARABLE_CONTRIBUTIONS_RETROSPECTIVELY"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    started_wall = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat()
    protocol = json.loads(args.protocol.read_text())
    if protocol["status"] != "FROZEN_BEFORE_RK34_EXPRESSION_ASSOCIATION_OR_MODEL_FIT":
        raise ValueError("protocol is not frozen")
    if sha256(Path(__file__).resolve()) != protocol["code"]["production_script_sha256"]:
        raise ValueError("production script differs from frozen protocol")
    if args.output_root.exists() and any(args.output_root.iterdir()):
        raise FileExistsError("output root is not empty")

    paths = {key: Path(value["path"]) for key, value in protocol["inputs"].items()}
    for key, path in paths.items():
        if sha256(path) != protocol["inputs"][key]["sha256"]:
            raise ValueError(f"input hash mismatch: {key}")
    preflight = json.loads(paths["preflight_report"].read_text())
    if preflight["status"] != "PASS_LABEL_FREE_START_CONTEXT_PREFLIGHT" or preflight["expression_columns_read"] or preflight["model_fit_performed"]:
        raise ValueError("invalid label-free preflight")
    if preflight["candidate_csv_sha256"] != protocol["inputs"]["candidate_csv"]["sha256"]:
        raise ValueError("preflight candidate identity mismatch")
    coverage = json.loads(paths["coverage_report"].read_text())
    if coverage["status"] != "PASS_LABEL_FREE_COVERAGE_AUDIT":
        raise ValueError("invalid frozen cluster coverage")

    usecols = [
        "source_row", "seqId", "cds", "utr_5prime", "sequenceWithUtr", "protein_aa", "CAI", "log10_expression",
        "cds_sha256", "exact_cds_group",
    ]
    source = pd.read_csv(paths["main_csv"], usecols=usecols)
    if len(source) != 154:
        raise ValueError("source row count")
    rows = []
    for cds_sha, group in source.groupby("cds_sha256", sort=False):
        for column in ("cds", "utr_5prime", "sequenceWithUtr", "protein_aa", "exact_cds_group"):
            if group[column].nunique() != 1:
                raise ValueError(f"non-unique {column}")
        if not np.isfinite(group["CAI"]).all() or group["CAI"].nunique(dropna=False) != 1:
            raise ValueError("non-constant CAI")
        cds = str(group["cds"].iloc[0]).upper()
        utr = str(group["utr_5prime"].iloc[0]).upper()
        full = str(group["sequenceWithUtr"].iloc[0]).upper()
        if len(utr) != 144 or len(cds) != 720 or len(full) != 864 or full != utr + cds or cds[:3] != "ATG":
            raise ValueError("full-mRNA coverage failure")
        if set(full) - set("ACGT") or hashlib.sha256(cds.encode()).hexdigest() != cds_sha:
            raise ValueError("CDS identity failure")
        gc_cds, gc3_cds = cds_gc_features(cds)
        rows.append({
            "cds_sha256": cds_sha, "exact_cds_group": str(group["exact_cds_group"].iloc[0]),
            "first_source_row": int(group["source_row"].min()),
            "source_rows": ";".join(str(int(x)) for x in sorted(group["source_row"])),
            "seqIds": ";".join(str(x) for x in group["seqId"]), "n_measurements": len(group),
            "CAI": float(group["CAI"].iloc[0]),
            "gc_cds": gc_cds,
            "gc3_cds": gc3_cds,
            "target": float(group["log10_expression"].mean()), "cds": cds, "utr": utr,
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

    candidate = pd.read_csv(paths["candidate_csv"])
    candidate_columns = ["exact_cds_group"] + [f"sequence__{context}" for context in CONTEXTS] + ARMS
    analysis = analysis.merge(candidate[candidate_columns], on="exact_cds_group", how="left", validate="one_to_one")
    max_energy_delta = 0.0
    for row in analysis.itertuples(index=False):
        contexts = context_sequences(row.utr, row.cds)
        for context in CONTEXTS:
            if getattr(row, f"sequence__{context}") != contexts[context]:
                raise ValueError("candidate sequence identity")
        for dangles in (2, 0):
            for context in CONTEXTS:
                arm = f"{context}_d{dangles}"
                recomputed = mfe(contexts[context], dangles)
                max_energy_delta = max(max_energy_delta, abs(recomputed - float(getattr(row, arm))))
    if max_energy_delta > 1e-12:
        raise ValueError(f"candidate energy mismatch: {max_energy_delta}")

    numeric = analysis[["CAI", "gc_cds", "gc3_cds", "target"] + ARMS]
    if not np.isfinite(numeric.to_numpy(float)).all() or not (analysis[ARMS].nunique() > 1).all():
        raise ValueError("invalid analysis feature matrix")
    args.output_root.mkdir(parents=True, exist_ok=True)
    analysis_path = args.output_root / "analysis_start_context_150.csv"
    analysis.drop(columns=["cds", "utr"]).to_csv(analysis_path, index=False)

    assignments = pd.read_csv(paths["rk32_fold_assignments"])
    predictions = pd.read_csv(paths["rk32_oof_predictions"])
    if len(assignments) != 1500 or len(predictions) != 1500:
        raise ValueError("reused fold/prediction row count")
    target_map = analysis.set_index("group_id")["target"]
    cds_map = analysis.set_index("group_id")["cds_sha256"]
    if not np.allclose(predictions["group_id"].map(target_map), predictions["target"], rtol=0, atol=1e-12):
        raise ValueError("reused target identity")
    if not predictions["group_id"].map(cds_map).equals(predictions["cds_sha256"]):
        raise ValueError("reused CDS identity")

    seeds = protocol["outer_evaluation"]["seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    expected_folds = {}
    for seed in seeds:
        folds, loads = make_cluster_folds(analysis["sequence_cluster_id"].to_numpy(int), seed)
        expected_folds[seed] = folds
        if seed == primary_seed and loads != coverage["selected_coverage"]["primary_seed_fold_sizes"]:
            raise ValueError("primary fold sizes differ from frozen coverage")
        expected_by_group = pd.Series(folds, index=analysis["group_id"])
        actual_assignment = assignments[assignments["seed"] == seed].set_index("group_id")["fold"]
        actual_prediction = predictions[predictions["seed"] == seed].set_index("group_id")["fold"]
        if not expected_by_group.equals(actual_assignment.loc[expected_by_group.index]) or not expected_by_group.equals(actual_prediction.loc[expected_by_group.index]):
            raise ValueError(f"fold identity mismatch at seed {seed}")
        for fold in range(5):
            train_clusters = set(analysis.loc[folds != fold, "sequence_cluster_id"])
            test_clusters = set(analysis.loc[folds == fold, "sequence_cluster_id"])
            if not train_clusters.isdisjoint(test_clusters):
                raise ValueError("cluster leakage")

    reused_columns = ["seed", "group_id", "cds_sha256", "sequence_cluster_id", "target", "fold", "null"] + [
        f"{model}_{arm}" for model in MODELS for arm in ("simple", "vienna_local")
    ]
    predictions = predictions[reused_columns].rename(columns={
        "ridge_vienna_local": "ridge_exact_real_d2", "histgb_vienna_local": "histgb_exact_real_d2",
    }).reset_index(drop=True)
    simple = protocol["simple_features"]
    new_arms = [arm for arm in ARMS if arm != "exact_real_d2"]
    if len(new_arms) != 7:
        raise AssertionError("new arm accounting")
    for model in MODELS:
        for arm in new_arms:
            predictions[f"{model}_{arm}"] = np.nan
    training_rows = []
    for seed in seeds:
        folds = expected_folds[seed]
        seed_positions = np.flatnonzero(predictions["seed"].to_numpy(int) == seed)
        if len(seed_positions) != 150:
            raise ValueError("seed prediction rows")
        for fold in range(5):
            train = analysis[folds != fold]
            test = analysis[folds == fold]
            test_positions = seed_positions[folds == fold]
            for model in MODELS:
                for arm in new_arms:
                    predictions.loc[test_positions, f"{model}_{arm}"] = fit_predict(
                        model, simple + [arm], train, test, int(seed + fold),
                    )
            training_rows.append({
                "seed": seed, "fold": fold, "n_train": len(train), "n_test": len(test),
                "n_train_clusters": train["sequence_cluster_id"].nunique(),
                "n_test_clusters": test["sequence_cluster_id"].nunique(),
                "train_target_mean": float(train["target"].mean()), "histgb_random_state": int(seed + fold),
                "new_model_fits": 2 * len(new_arms), "reused_model_fits": 4,
                "evaluated_model_fits": 2 * (1 + len(ARMS)), "cluster_leakage": False,
            })
    value_columns = ["null"] + [f"{model}_{arm}" for model in MODELS for arm in ["simple"] + ARMS]
    if not np.isfinite(predictions[value_columns].to_numpy(float)).all():
        raise ValueError("incomplete OOF predictions")

    predictions_path = args.output_root / "oof_predictions.csv"
    assignments_path = args.output_root / "fold_assignments.csv"
    training_path = args.output_root / "training_log.csv"
    predictions.to_csv(predictions_path, index=False)
    assignments.to_csv(assignments_path, index=False)
    training_log = pd.DataFrame(training_rows)
    training_log.to_csv(training_path, index=False)

    seed_metric_rows, seed_effect_rows = [], []
    effects_by_seed = {}
    for seed in seeds:
        metrics, effects = effect_names_for_seed(predictions, seed)
        seed_metric_rows.extend(metrics)
        effects_by_seed[seed] = effects
        seed_effect_rows.extend({"seed": seed, "test": name, "effect": effect} for name, effect in effects.items())
    seed_metrics = pd.DataFrame(seed_metric_rows)
    seed_effects = pd.DataFrame(seed_effect_rows)
    seed_metrics_path = args.output_root / "seed_metrics.csv"
    seed_effects_path = args.output_root / "seed_effects.csv"
    seed_metrics.to_csv(seed_metrics_path, index=False)
    seed_effects.to_csv(seed_effects_path, index=False)

    inference = protocol["primary_inference"]
    primary_tests, arrays = run_inference(
        predictions[predictions["seed"] == primary_seed], int(inference["resamples"]),
        int(inference["bootstrap_seed"]), int(inference["permutation_seed"]),
    )
    for row in primary_tests:
        effects = np.array([effects_by_seed[seed][row["test"]] for seed in seeds], dtype=float)
        row.update({
            "seed_effects": effects.tolist(), "positive_seeds": int(np.sum(effects > 0)),
            "mean_seed_effect": float(effects.mean()), "median_seed_effect": float(np.median(effects)),
        })
        row["pass"] = bool(row["observed_effect"] > 0 and row["ci95"][0] > 0 and row["p_holm"] < 0.05 and row["positive_seeds"] >= 8)

    family_results = []
    for analysis_name in ("primary", "sensitivity_d0"):
        for family in FAMILIES:
            selected = [row for row in primary_tests if row["analysis"] == analysis_name and row["family"] == family]
            family_results.append({
                "analysis": analysis_name, "family": family, "n_tests": len(selected),
                "n_pass": sum(row["pass"] for row in selected), "all_four_pass": all(row["pass"] for row in selected),
                "confirmatory": analysis_name == "primary",
            })
    primary_family_pass = {row["family"]: row["all_four_pass"] for row in family_results if row["analysis"] == "primary"}
    conclusion = conclusion_for(primary_family_pass)

    arrays_path = args.output_root / "primary_inference_arrays.npz"
    np.savez_compressed(arrays_path, **arrays)
    primary_metrics = []
    for row in seed_metrics[seed_metrics["seed"] == primary_seed].drop(columns="seed").to_dict("records"):
        primary_metrics.append({key: (None if isinstance(value, float) and not np.isfinite(value) else value) for key, value in row.items()})
    output_files = {}
    for path in (analysis_path, assignments_path, predictions_path, training_path, seed_metrics_path, seed_effects_path, arrays_path):
        output_files[path.name] = {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}
    summary = {
        "schema": "a8-rk34-start-context-result-v1", "status": "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION",
        "protocol": str(args.protocol), "protocol_sha256": sha256(args.protocol),
        "analysis_script_sha256": sha256(Path(__file__).resolve()),
        "analysis_type": "retrospective_outcome_known_coverage_followup_not_independent_confirmation",
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "component_wall_seconds": float(time.perf_counter() - started_wall),
        "n_measurement_rows": 154, "n_exact_cds_groups": 150, "n_sequence_clusters": 37,
        "primary_seed": primary_seed, "seeds": seeds, "folds_per_seed": 5,
        "contexts": CONTEXTS, "structure_arms": ARMS, "comparisons": COMPARISONS,
        "new_model_fits": 700, "reused_rk32_model_fits": 200, "evaluated_model_fits": 900,
        "max_recomputed_energy_abs_delta": max_energy_delta,
        "primary_absolute_performance": primary_metrics, "primary_tests": primary_tests,
        "family_results": family_results, "primary_family_pass": primary_family_pass,
        "n_confirmatory_tests": sum(row["analysis"] == "primary" for row in primary_tests),
        "n_confirmatory_pass": sum(row["analysis"] == "primary" and row["pass"] for row in primary_tests),
        "n_sensitivity_tests": sum(row["analysis"] == "sensitivity_d0" for row in primary_tests),
        "scientific_conclusion": conclusion, "outputs": output_files,
        "scientific_flags": {
            "same_frozen_37_clusters_and_folds": True, "expression_outcome_previously_known": True,
            "independent_untouched_confirmation": False, "functional_untouched_read": False,
            "host_or_assay_identified": False, "protein_ood": False, "full_external_sota": False,
            "sensitivity_can_upgrade_failed_primary": False, "RK_G1_complete": False,
        },
    }
    atomic_json(args.summary, summary)
    print(json.dumps({
        "status": summary["status"], "scientific_conclusion": conclusion,
        "primary_family_results": [row for row in family_results if row["analysis"] == "primary"],
        "n_confirmatory_pass": summary["n_confirmatory_pass"], "n_confirmatory_tests": summary["n_confirmatory_tests"],
        "new_model_fits": 700, "reused_rk32_model_fits": 200, "evaluated_model_fits": 900,
        "summary": str(args.summary),
    }, indent=2))


if __name__ == "__main__":
    main()
