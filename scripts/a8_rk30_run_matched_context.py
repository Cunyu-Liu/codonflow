#!/usr/bin/env python3
"""RK30 matched-context whole-cluster transport and within-context analysis."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn

import a8_rk02_mordstein_structure_increment as rk02
import a8_rk28_run_sequence_cluster_ood as rk28


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def holm_adjust(p_values) -> list[float]:
    p = np.asarray(p_values, dtype=float)
    if p.ndim != 1 or not np.isfinite(p).all():
        raise ValueError("Holm input must be a finite vector")
    order = np.argsort(p)
    adjusted = np.empty(len(p), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def transport_train_test(analysis: pd.DataFrame, pair: dict, folds: np.ndarray, fold: int):
    train = analysis.loc[folds != fold, ["variant_id", "sequence_cluster_id"] +
                         [c for c in analysis.columns if c.startswith(("gc", "cpg", "cai", "mfe"))] +
                         [f"target__{pair['source']}"]].copy()
    test = analysis.loc[folds == fold].copy()
    train = train.rename(columns={f"target__{pair['source']}": "target"})
    test["target"] = test[f"target__{pair['target']}"]
    if set(train["sequence_cluster_id"]) & set(test["sequence_cluster_id"]):
        raise RuntimeError("Transport cluster leakage")
    if f"target__{pair['target']}" in train.columns:
        raise RuntimeError("Target outcome leaked into source training frame")
    return train, test


def transport_metrics(predictions: pd.DataFrame) -> tuple[list[dict], dict]:
    y = predictions["target"].to_numpy(float)
    rows = []
    for arm in ["null", "ridge_simple", "ridge_structure", "histgb_simple", "histgb_structure"]:
        pred = predictions[arm].to_numpy(float)
        rows.append({"arm": arm, "spearman": rk28.spearman(y, pred),
                     "mse": float(np.mean((y - pred) ** 2))})
    effects = {}
    for model in ["ridge", "histgb"]:
        simple = predictions[f"{model}_simple"].to_numpy(float)
        structure = predictions[f"{model}_structure"].to_numpy(float)
        effects[f"{model}_spearman_effect"] = rk28.spearman(y, structure) - rk28.spearman(y, simple)
        effects[f"{model}_mse_improvement"] = float(np.mean((y - simple) ** 2 - (y - structure) ** 2))
    return rows, effects


def build_feature_table(protocol: dict) -> pd.DataFrame:
    for key in ["reference_csv", "cluster_facts_csv", "feature_implementation", "cai_wrapper"]:
        item = protocol["inputs"][key]
        if sha256(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"Input hash mismatch: {key}")
    cai = protocol["inputs"]["cai_wrapper"]
    references = rk02.load_literal_assignment(Path(cai["path"]), cai["reference_variable"])
    if len(references) != cai["reference_count"]:
        raise ValueError("CAI reference count mismatch")
    weights = rk02.reference_weights(references)
    raw = pd.read_csv(protocol["inputs"]["reference_csv"]["path"],
                      usecols=["variant_id", "sequence_5prime_300nt"])
    facts = pd.read_csv(protocol["inputs"]["cluster_facts_csv"]["path"])
    rows = []
    proteins = set()
    for record in raw.to_dict("records"):
        sequence = str(record["sequence_5prime_300nt"]).upper()
        proteins.add(rk02.translate(sequence))
        row = {"variant_id": str(record["variant_id"]),
               "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest()}
        row.update(rk02.simple_features(sequence, 0, weights))
        row.update(rk02.structure_features(sequence))
        rows.append(row)
    if len(proteins) != 1:
        raise ValueError("The observed-R1 cohort no longer maps to one protein segment")
    features = pd.DataFrame(rows).merge(facts, on=["variant_id", "sequence_sha256"],
                                        how="inner", validate="one_to_one")
    if len(features) != 152 or features["sequence_cluster_id"].nunique() != 74:
        raise ValueError("Frozen reference/cluster cohort mismatch")
    return features


def check_primary_folds(analysis: pd.DataFrame, protocol: dict) -> list[int]:
    folds, loads = rk28.make_cluster_folds(analysis["sequence_cluster_id"].to_numpy(int),
                                           protocol["outer_evaluation"]["primary_seed"])
    cluster_counts = [analysis.loc[folds == fold, "sequence_cluster_id"].nunique() for fold in range(5)]
    if min(loads) < 5 or min(cluster_counts) < 2:
        raise RuntimeError(f"Primary fold coverage infeasible: sizes={loads}, clusters={cluster_counts}")
    return loads


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--freeze-report", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    wall_start = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat()
    protocol = json.loads(args.protocol.read_text())
    freeze = json.loads(args.freeze_report.read_text())
    if freeze.get("status") != "PASS_RK30_LABEL_FREE_FREEZE" or freeze.get("protocol_sha256") != sha256(args.protocol):
        raise RuntimeError("Post-commit protocol freeze verification failed")
    counting_path = args.artifact_root / "RK30_COUNTING.json"
    counting = json.loads(counting_path.read_text())
    if counting.get("status") != "PASS_COUNTING_COVERAGE_FEASIBLE" or not counting.get("coverage_feasible"):
        raise RuntimeError("Matched-context counting did not pass the frozen coverage gate")
    if counting.get("protocol_sha256") != sha256(args.protocol):
        raise RuntimeError("Counting and model protocols differ")
    outcomes_path = args.artifact_root / "matched_context_outcomes.csv"
    if sha256(outcomes_path) != counting["outcomes_sha256"]:
        raise RuntimeError("Outcome file hash mismatch")
    features = build_feature_table(protocol)
    outcomes = pd.read_csv(outcomes_path)
    analysis = features.merge(outcomes, on=["variant_id", "sequence_cluster_id"],
                              how="inner", validate="one_to_one")
    if len(analysis) != counting["common_variants"]:
        raise RuntimeError("Feature/outcome common-cohort mismatch")
    analysis["sequence_cluster_id"] = analysis["sequence_cluster_id"].astype(int)
    primary_loads = check_primary_folds(analysis, protocol)
    output = args.artifact_root / "model"
    output.mkdir(exist_ok=True)
    analysis_path = output / "analysis_matched_context.csv"
    analysis.to_csv(analysis_path, index=False)

    simple = protocol["features"]["simple"]
    structure = simple + protocol["features"]["structure_addition"]
    mfe_only = protocol["features"]["structure_addition"]
    feature_sets = {"simple": simple, "structure": structure, "mfe_only": mfe_only}
    seeds = protocol["outer_evaluation"]["sensitivity_seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]

    transport_predictions, transport_folds, transport_metrics_rows = [], [], []
    transport_seed_effects, transport_logs = [], []
    transport_fit_count = 0
    for pair in protocol["primary_transport"]["ordered_pairs"]:
        pair_name = f"{pair['source']}__to__{pair['target']}"
        for seed in seeds:
            folds, loads = rk28.make_cluster_folds(analysis["sequence_cluster_id"].to_numpy(int), seed)
            fold_frame = analysis[["variant_id", "sequence_cluster_id"]].copy()
            fold_frame.insert(0, "seed", seed)
            fold_frame.insert(0, "pair", pair_name)
            fold_frame["fold"] = folds
            transport_folds.append(fold_frame)
            current = analysis[["variant_id", "sequence_cluster_id", f"target__{pair['target']}"]].copy()
            current = current.rename(columns={f"target__{pair['target']}": "target"})
            current.insert(0, "seed", seed)
            current.insert(0, "source", pair["source"])
            current.insert(0, "target_context", pair["target"])
            current["fold"] = folds
            for arm in ["null", "ridge_simple", "ridge_structure", "histgb_simple", "histgb_structure"]:
                current[arm] = np.nan
            for fold in range(5):
                train, test = transport_train_test(analysis, pair, folds, fold)
                test_index = np.flatnonzero(folds == fold)
                current.loc[current.index[test_index], "null"] = float(train["target"].mean())
                for model_name in ["ridge", "histgb"]:
                    for label in ["simple", "structure"]:
                        arm = f"{model_name}_{label}"
                        pred = rk28.fit_predict(model_name, feature_sets[label], train, test, int(seed + fold))
                        current.loc[current.index[test_index], arm] = pred
                        transport_fit_count += 1
                transport_logs.append({"pair": pair_name, "seed": seed, "fold": fold,
                                       "n_source_train": len(train), "n_target_test": len(test),
                                       "n_train_clusters": train["sequence_cluster_id"].nunique(),
                                       "n_test_clusters": test["sequence_cluster_id"].nunique(),
                                       "source_target_mean": float(train["target"].mean()),
                                       "model_fits": 4, "cluster_leakage": False,
                                       "target_outcome_used_for_fit": False})
            arms = ["null", "ridge_simple", "ridge_structure", "histgb_simple", "histgb_structure"]
            if not np.isfinite(current[arms].to_numpy(float)).all():
                raise RuntimeError("Nonfinite transport prediction")
            transport_predictions.append(current)
            metric_rows, effects = transport_metrics(current)
            for row in metric_rows:
                transport_metrics_rows.append({"pair": pair_name, "seed": seed, **row})
            for test_name, effect in effects.items():
                transport_seed_effects.append({"pair": pair_name, "seed": seed,
                                               "test": test_name, "effect": effect})

    within_predictions, within_folds, within_metrics_rows = [], [], []
    within_seed_effects, within_logs = [], []
    within_fit_count = 0
    for context in protocol["secondary_within_context"]["contexts"]:
        for seed in seeds:
            folds, loads = rk28.make_cluster_folds(analysis["sequence_cluster_id"].to_numpy(int), seed)
            fold_frame = analysis[["variant_id", "sequence_cluster_id"]].copy()
            fold_frame.insert(0, "seed", seed)
            fold_frame.insert(0, "context", context)
            fold_frame["fold"] = folds
            within_folds.append(fold_frame)
            current = analysis[["variant_id", "sequence_cluster_id", f"target__{context}"]].copy()
            current = current.rename(columns={f"target__{context}": "target"})
            current.insert(0, "seed", seed)
            current.insert(0, "context", context)
            current["fold"] = folds
            arms = ["null", "ridge_simple", "ridge_structure", "ridge_mfe_only",
                    "histgb_simple", "histgb_structure", "histgb_mfe_only"]
            for arm in arms:
                current[arm] = np.nan
            for fold in range(5):
                train, test = transport_train_test(analysis, {"source": context, "target": context}, folds, fold)
                test_index = np.flatnonzero(folds == fold)
                current.loc[current.index[test_index], "null"] = float(train["target"].mean())
                for model_name in ["ridge", "histgb"]:
                    for label, names in feature_sets.items():
                        arm = f"{model_name}_{label}"
                        pred = rk28.fit_predict(model_name, names, train, test, int(seed + fold))
                        current.loc[current.index[test_index], arm] = pred
                        within_fit_count += 1
                within_logs.append({"context": context, "seed": seed, "fold": fold,
                                    "n_train": len(train), "n_test": len(test),
                                    "n_train_clusters": train["sequence_cluster_id"].nunique(),
                                    "n_test_clusters": test["sequence_cluster_id"].nunique(),
                                    "train_target_mean": float(train["target"].mean()),
                                    "model_fits": 6, "cluster_leakage": False})
            if not np.isfinite(current[arms].to_numpy(float)).all():
                raise RuntimeError("Nonfinite within-context prediction")
            within_predictions.append(current)
            metric_rows, effects = rk28.metric_rows_for_seed(current, seed)
            for row in metric_rows:
                row["context"] = context
                within_metrics_rows.append(row)
            for test_name, effect in effects.items():
                within_seed_effects.append({"context": context, "seed": seed,
                                            "test": test_name, "effect": effect})

    if transport_fit_count != 800 or within_fit_count != 900:
        raise RuntimeError(f"Fit count mismatch: {transport_fit_count}, {within_fit_count}")
    transport_pred = pd.concat(transport_predictions, ignore_index=True)
    within_pred = pd.concat(within_predictions, ignore_index=True)
    transport_pred.to_csv(output / "transport_oof_predictions.csv", index=False)
    within_pred.to_csv(output / "within_context_oof_predictions.csv", index=False)
    pd.concat(transport_folds, ignore_index=True).to_csv(output / "transport_fold_assignments.csv", index=False)
    pd.concat(within_folds, ignore_index=True).to_csv(output / "within_context_fold_assignments.csv", index=False)
    pd.DataFrame(transport_logs).to_csv(output / "transport_training_log.csv", index=False)
    pd.DataFrame(within_logs).to_csv(output / "within_context_training_log.csv", index=False)
    transport_metrics_df = pd.DataFrame(transport_metrics_rows)
    within_metrics_df = pd.DataFrame(within_metrics_rows)
    transport_metrics_df.to_csv(output / "transport_seed_metrics.csv", index=False)
    within_metrics_df.to_csv(output / "within_context_seed_metrics.csv", index=False)
    transport_effects_df = pd.DataFrame(transport_seed_effects)
    within_effects_df = pd.DataFrame(within_seed_effects)
    transport_effects_df.to_csv(output / "transport_seed_effects.csv", index=False)
    within_effects_df.to_csv(output / "within_context_seed_effects.csv", index=False)

    inf = protocol["primary_transport"]
    primary_rows = []
    for pair in inf["ordered_pairs"]:
        pair_name = f"{pair['source']}__to__{pair['target']}"
        primary = transport_pred[(transport_pred["source"] == pair["source"]) &
                                 (transport_pred["target_context"] == pair["target"]) &
                                 (transport_pred["seed"] == primary_seed)].reset_index(drop=True)
        tests, arrays = rk28.primary_inference(primary, primary["sequence_cluster_id"].to_numpy(int),
                                               inf["cluster_bootstrap"]["seed"],
                                               inf["cluster_swap_permutation"]["seed"],
                                               inf["cluster_bootstrap"]["resamples"])
        np.savez_compressed(output / f"transport_inference__{pair_name}.npz", **arrays)
        for test in tests:
            effects = transport_effects_df[(transport_effects_df["pair"] == pair_name) &
                                           (transport_effects_df["test"] == test["test"])].sort_values("seed")["effect"].to_numpy(float)
            test.update({"pair": pair_name, "source": pair["source"], "target": pair["target"],
                         "mechanism": pair["mechanism"], "p_holm_within_pair": test["p_holm"],
                         "seed_effects": effects.tolist(), "positive_seeds": int((effects > 0).sum()),
                         "mean_seed_effect": float(effects.mean()), "median_seed_effect": float(np.median(effects))})
            primary_rows.append(test)
    family_adjusted = holm_adjust([row["p_cluster_swap"] for row in primary_rows])
    for row, adjusted in zip(primary_rows, family_adjusted):
        row["p_holm"] = adjusted
        row["pass"] = bool(row["observed_effect"] > 0 and row["ci95"][0] > 0 and
                           adjusted < 0.05 and row["positive_seeds"] >= 8)
    pair_status = {}
    for pair in inf["ordered_pairs"]:
        pair_name = f"{pair['source']}__to__{pair['target']}"
        pair_status[pair_name] = all(row["pass"] for row in primary_rows if row["pair"] == pair_name)
    family_pass = all(row["pass"] for row in primary_rows)

    secondary_rows = []
    for context in protocol["secondary_within_context"]["contexts"]:
        primary = within_pred[(within_pred["context"] == context) &
                              (within_pred["seed"] == primary_seed)].reset_index(drop=True)
        tests, arrays = rk28.primary_inference(primary, primary["sequence_cluster_id"].to_numpy(int),
                                               inf["cluster_bootstrap"]["seed"],
                                               inf["cluster_swap_permutation"]["seed"],
                                               inf["cluster_bootstrap"]["resamples"])
        np.savez_compressed(output / f"within_inference__{context}.npz", **arrays)
        for test in tests:
            effects = within_effects_df[(within_effects_df["context"] == context) &
                                        (within_effects_df["test"] == test["test"])].sort_values("seed")["effect"].to_numpy(float)
            test.update({"context": context, "p_holm_within_context": test["p_holm"],
                         "seed_effects": effects.tolist(), "positive_seeds": int((effects > 0).sum()),
                         "mean_seed_effect": float(effects.mean()), "median_seed_effect": float(np.median(effects))})
            secondary_rows.append(test)
    secondary_adjusted = holm_adjust([row["p_cluster_swap"] for row in secondary_rows])
    for row, adjusted in zip(secondary_rows, secondary_adjusted):
        row["p_holm"] = adjusted
        row["pass"] = bool(row["observed_effect"] > 0 and row["ci95"][0] > 0 and
                           adjusted < 0.05 and row["positive_seeds"] >= 8)

    primary_absolute = transport_metrics_df[transport_metrics_df["seed"] == primary_seed].drop(columns="seed").to_dict("records")
    within_absolute = within_metrics_df[within_metrics_df["seed"] == primary_seed].drop(columns="seed").to_dict("records")
    output_files = {}
    for path in sorted(output.iterdir()):
        if path.is_file():
            output_files[path.name] = {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}
    summary = {
        "schema": "a8-rk30-mordstein-matched-context-result-v1",
        "status": "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION",
        "scientific_conclusion": "MATCHED_CONTEXT_MFE_TRANSPORT_SUPPORTED_RETROSPECTIVELY" if family_pass else "MATCHED_CONTEXT_MFE_TRANSPORT_NOT_SUPPORTED",
        "context_transportable_mfe_increment_pass": bool(family_pass),
        "host_transport_bidirectional_pass": bool(pair_status["hela_no_intron__to__hek293_no_intron"] and pair_status["hek293_no_intron__to__hela_no_intron"]),
        "intron_transport_bidirectional_pass": bool(pair_status["hela_no_intron__to__hela_with_intron"] and pair_status["hela_with_intron__to__hela_no_intron"]),
        "pair_status": pair_status,
        "protocol_sha256": sha256(args.protocol), "counting_report_sha256": sha256(counting_path),
        "analysis_script_sha256": sha256(Path(__file__).resolve()),
        "n_common_variants": len(analysis), "n_common_clusters": int(analysis["sequence_cluster_id"].nunique()),
        "primary_seed_fold_sizes": primary_loads, "primary_seed": primary_seed,
        "transport_model_fits": transport_fit_count, "within_context_model_fits": within_fit_count,
        "total_model_fits": transport_fit_count + within_fit_count, "device": "CPU_ONLY",
        "primary_transport_absolute_performance": primary_absolute,
        "primary_transport_tests": primary_rows,
        "secondary_within_context_absolute_performance": within_absolute,
        "secondary_within_context_tests": secondary_rows,
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - wall_start,
        "outputs": output_files,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                        "scipy": scipy.__version__, "sklearn": sklearn.__version__, "ViennaRNA": rk02.RNA.__version__},
        "scientific_flags": protocol["scientific_boundaries"],
        "interpretation_boundary": "A failed transport family rejects broad transportability in this design; it does not establish a universal negative structure mechanism. Secondary within-context results cannot rescue primary transport failure."
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": summary["status"], "scientific_conclusion": summary["scientific_conclusion"],
                      "n_common_variants": len(analysis), "n_common_clusters": summary["n_common_clusters"],
                      "total_model_fits": summary["total_model_fits"], "pair_status": pair_status,
                      "elapsed_seconds": summary["elapsed_seconds"], "summary": str(args.summary)}, indent=2))


if __name__ == "__main__":
    main()
