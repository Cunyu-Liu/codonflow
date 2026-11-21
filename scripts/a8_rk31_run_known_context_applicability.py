#!/usr/bin/env python3
"""RK31 retrospective known-context, whole-cluster variant-OOD applicability model."""
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

import a8_rk28_run_sequence_cluster_ood as rk28


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def holm_adjust(p_values) -> list[float]:
    values = np.asarray(p_values, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("Holm requires a finite vector")
    order = np.argsort(values)
    adjusted = np.empty(len(values), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(values) - rank) * values[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def make_long(frame: pd.DataFrame, contexts: list[str], nonreference: list[str]) -> pd.DataFrame:
    parts = []
    for context in contexts:
        part = frame.copy()
        part["context"] = context
        part["target"] = part[f"target__{context}"].astype(float)
        for other in nonreference:
            part[f"context__{other}"] = float(context == other)
        parts.append(part)
    result = pd.concat(parts, ignore_index=True)
    return result


def feature_names(protocol: dict, arm: str) -> list[str]:
    simple = protocol["features"]["simple"]
    structure = protocol["features"]["structure_addition"]
    indicators = protocol["features"]["nonreference_context_indicators"]
    if arm == "shared_simple":
        return simple + indicators
    if arm == "shared_full":
        return simple + structure + indicators
    if arm == "context_gated_full":
        interactions = [f"{indicator}__x__{mfe}" for indicator in indicators for mfe in structure]
        return simple + structure + indicators + interactions
    if arm == "no_transport_simple":
        return simple
    if arm == "no_transport_full":
        return simple + structure
    raise ValueError(arm)


def add_interactions(frame: pd.DataFrame, protocol: dict) -> pd.DataFrame:
    result = frame.copy()
    for indicator in protocol["features"]["nonreference_context_indicators"]:
        for mfe in protocol["features"]["structure_addition"]:
            result[f"{indicator}__x__{mfe}"] = result[indicator].to_numpy(float) * result[mfe].to_numpy(float)
    return result


def metric_rows(predictions: pd.DataFrame, arms: list[str]) -> list[dict]:
    target = predictions["target"].to_numpy(float)
    rows = []
    for arm in arms:
        pred = predictions[arm].to_numpy(float)
        rows.append({"arm": arm, "spearman": rk28.spearman(target, pred),
                     "mse": float(np.mean((target - pred) ** 2))})
    return rows


def effect_value(predictions: pd.DataFrame, baseline: str, metric: str) -> float:
    target = predictions["target"].to_numpy(float)
    base = predictions[baseline].to_numpy(float)
    candidate = predictions["context_gated_full"].to_numpy(float)
    if metric == "spearman_effect":
        return rk28.spearman(target, candidate) - rk28.spearman(target, base)
    if metric == "mse_improvement":
        return float(np.mean((target - base) ** 2 - (target - candidate) ** 2))
    raise ValueError(metric)


def contrast_inference(predictions: pd.DataFrame, baseline: str, metric: str,
                       cluster_rows: list[np.ndarray], cluster_index: np.ndarray,
                       boot_clusters: np.ndarray, perm_signs: np.ndarray) -> tuple[dict, np.ndarray, np.ndarray]:
    target = predictions["target"].to_numpy(float)
    base = predictions[baseline].to_numpy(float)
    candidate = predictions["context_gated_full"].to_numpy(float)
    observed = effect_value(predictions, baseline, metric)
    resamples = len(boot_clusters)
    bootstrap = np.empty(resamples, dtype=float)
    permutation = np.empty(resamples, dtype=float)
    if metric == "mse_improvement":
        difference = (target - base) ** 2 - (target - candidate) ** 2
        permutation = (perm_signs[:, cluster_index] * difference).mean(axis=1)
    for index in range(resamples):
        selected = boot_clusters[index]
        row_index = np.concatenate([cluster_rows[int(c)] for c in selected])
        if metric == "spearman_effect":
            bootstrap[index] = (rk28.spearman(target[row_index], candidate[row_index]) -
                                rk28.spearman(target[row_index], base[row_index]))
            signs = perm_signs[index, cluster_index] < 0
            swapped_base = np.where(signs, candidate, base)
            swapped_candidate = np.where(signs, base, candidate)
            permutation[index] = (rk28.spearman(target, swapped_candidate) -
                                  rk28.spearman(target, swapped_base))
        else:
            weights = np.bincount(selected, minlength=len(cluster_rows))[cluster_index].astype(float)
            bootstrap[index] = float(np.dot(weights, difference) / weights.sum())
    if not np.isfinite(bootstrap).all() or not np.isfinite(permutation).all():
        raise RuntimeError("Nonfinite inference array")
    p_value = float((1 + np.sum(np.abs(permutation) >= abs(observed))) / (resamples + 1))
    return ({"observed_effect": float(observed),
             "ci95": [float(np.quantile(bootstrap, 0.025)), float(np.quantile(bootstrap, 0.975))],
             "p_cluster_swap": p_value, "bootstrap_median": float(np.median(bootstrap))},
            bootstrap, permutation)


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
    if protocol.get("schema") != "a8-rk31-known-context-applicability-protocol-v1":
        raise ValueError("Unexpected protocol")
    freeze = json.loads(args.freeze_report.read_text())
    if freeze.get("status") != "PASS_RK31_PREEXPERIMENT_FREEZE" or freeze.get("protocol_sha256") != sha256(args.protocol):
        raise RuntimeError("Preexperiment freeze is missing or does not bind this protocol")
    for key, item in protocol["inputs"].items():
        if sha256(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"Input hash mismatch: {key}")
    independent = json.loads(Path(protocol["inputs"]["rk30_independent_report"]["path"]).read_text())
    if independent.get("status") != "PASS_INDEPENDENT_VERIFICATION":
        raise RuntimeError("RK30 independent model evidence is not accepted")
    analysis = pd.read_csv(protocol["inputs"]["analysis_csv"]["path"])
    expected = protocol["inputs"]["analysis_csv"]
    if len(analysis) != expected["expected_variants"] or analysis["sequence_cluster_id"].nunique() != expected["expected_clusters"]:
        raise RuntimeError("Frozen common-cohort dimensions differ")
    if analysis["variant_id"].nunique() != len(analysis):
        raise RuntimeError("Duplicate variant IDs")
    analysis["sequence_cluster_id"] = analysis["sequence_cluster_id"].astype(int)
    contexts = protocol["contexts"]
    nonreference = [context for context in contexts if context != protocol["reference_context"]]
    expected_indicators = [f"context__{context}" for context in nonreference]
    if protocol["features"]["nonreference_context_indicators"] != expected_indicators:
        raise RuntimeError("Context indicator order differs from protocol")
    arms = ["null", "shared_simple", "shared_full", "no_transport_simple", "no_transport_full", "context_gated_full"]
    pooled_arms = ["shared_simple", "shared_full", "context_gated_full"]
    separate_arms = ["no_transport_simple", "no_transport_full"]
    seeds = protocol["outer_evaluation"]["sensitivity_seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    output = args.artifact_root / "model"
    output.mkdir(parents=True, exist_ok=False)

    prediction_parts, fold_parts, metric_rows_all, effect_rows_all, training_logs = [], [], [], [], []
    fit_count = 0
    for seed in seeds:
        folds, loads = rk28.make_cluster_folds(analysis["sequence_cluster_id"].to_numpy(int), int(seed))
        if min(loads) < 5:
            raise RuntimeError("Fold coverage infeasible")
        fold_frame = analysis[["variant_id", "sequence_cluster_id"]].copy()
        fold_frame.insert(0, "seed", seed)
        fold_frame["fold"] = folds
        fold_parts.append(fold_frame)
        seed_prediction = make_long(analysis[["variant_id", "sequence_cluster_id"] +
                                            [f"target__{context}" for context in contexts]], contexts, nonreference)
        seed_prediction.insert(0, "seed", seed)
        seed_prediction["fold"] = np.tile(folds, len(contexts))
        for arm in arms:
            seed_prediction[arm] = np.nan
        position = {(row.context, row.variant_id): index for index, row in
                    enumerate(seed_prediction[["context", "variant_id"]].itertuples(index=False))}
        for fold in range(protocol["outer_evaluation"]["folds"]):
            train_base = analysis.loc[folds != fold].copy()
            test_base = analysis.loc[folds == fold].copy()
            train_long = add_interactions(make_long(train_base, contexts, nonreference), protocol)
            test_long = add_interactions(make_long(test_base, contexts, nonreference), protocol)
            if set(train_base["sequence_cluster_id"]) & set(test_base["sequence_cluster_id"]):
                raise RuntimeError("Whole-cluster leakage")
            test_positions = [position[(row.context, row.variant_id)] for row in
                              test_long[["context", "variant_id"]].itertuples(index=False)]
            for arm in pooled_arms:
                prediction = rk28.fit_predict("ridge", feature_names(protocol, arm), train_long, test_long, int(seed + fold))
                seed_prediction.iloc[test_positions, seed_prediction.columns.get_loc(arm)] = prediction
                fit_count += 1
                training_logs.append({"seed": seed, "fold": fold, "arm": arm, "context": "POOLED",
                                      "n_train": len(train_long), "n_test": len(test_long),
                                      "n_train_clusters": train_base["sequence_cluster_id"].nunique(),
                                      "n_test_clusters": test_base["sequence_cluster_id"].nunique(),
                                      "model_fits": 1, "cluster_leakage": False,
                                      "held_out_outcomes_used_as_features": False})
            for context in contexts:
                train_context = train_base.copy()
                test_context = test_base.copy()
                train_context["target"] = train_context[f"target__{context}"]
                context_positions = [position[(context, variant)] for variant in test_context["variant_id"]]
                null_positions = [position[(context, variant)] for variant in test_context["variant_id"]]
                seed_prediction.iloc[null_positions, seed_prediction.columns.get_loc("null")] = float(train_context["target"].mean())
                for arm in separate_arms:
                    prediction = rk28.fit_predict("ridge", feature_names(protocol, arm), train_context, test_context, int(seed + fold))
                    seed_prediction.iloc[context_positions, seed_prediction.columns.get_loc(arm)] = prediction
                    fit_count += 1
                    training_logs.append({"seed": seed, "fold": fold, "arm": arm, "context": context,
                                          "n_train": len(train_context), "n_test": len(test_context),
                                          "n_train_clusters": train_context["sequence_cluster_id"].nunique(),
                                          "n_test_clusters": test_context["sequence_cluster_id"].nunique(),
                                          "model_fits": 1, "cluster_leakage": False,
                                          "held_out_outcomes_used_as_features": False})
        if not np.isfinite(seed_prediction[arms].to_numpy(float)).all():
            raise RuntimeError("Nonfinite OOF prediction")
        prediction_parts.append(seed_prediction)
        for context in contexts:
            group = seed_prediction.loc[seed_prediction["context"] == context].reset_index(drop=True)
            for row in metric_rows(group, arms):
                metric_rows_all.append({"seed": seed, "context": context, **row})
            for baseline in protocol["primary_comparisons"]["baselines"]:
                for metric in protocol["primary_comparisons"]["metrics"]:
                    effect_rows_all.append({"seed": seed, "context": context, "baseline": baseline, "metric": metric,
                                            "effect": effect_value(group, baseline, metric)})
    if fit_count != protocol["outer_evaluation"]["expected_ridge_fits"]:
        raise RuntimeError(f"Fit count mismatch: {fit_count}")

    predictions = pd.concat(prediction_parts, ignore_index=True)
    fold_assignments = pd.concat(fold_parts, ignore_index=True)
    metrics = pd.DataFrame(metric_rows_all)
    effects = pd.DataFrame(effect_rows_all)
    predictions.to_csv(output / "known_context_oof_predictions.csv", index=False)
    fold_assignments.to_csv(output / "whole_cluster_fold_assignments.csv", index=False)
    metrics.to_csv(output / "seed_metrics.csv", index=False)
    effects.to_csv(output / "seed_effects.csv", index=False)
    pd.DataFrame(training_logs).to_csv(output / "training_log.csv", index=False)

    inference = protocol["inference"]
    primary_rows = []
    for context in contexts:
        primary = predictions.loc[(predictions["context"] == context) &
                                  (predictions["seed"] == primary_seed)].reset_index(drop=True)
        cluster_ids = primary["sequence_cluster_id"].to_numpy(int)
        unique_clusters = np.array(sorted(np.unique(cluster_ids).tolist()), dtype=int)
        cluster_index = np.searchsorted(unique_clusters, cluster_ids)
        cluster_rows = [np.flatnonzero(cluster_index == index) for index in range(len(unique_clusters))]
        rng_boot = np.random.default_rng(inference["cluster_bootstrap"]["seed"])
        boot_clusters = rng_boot.integers(0, len(unique_clusters),
                                         size=(inference["cluster_bootstrap"]["resamples"], len(unique_clusters)), dtype=np.int16)
        rng_perm = np.random.default_rng(inference["cluster_sign_swap_permutation"]["seed"])
        perm_signs = rng_perm.choice(np.array([-1, 1], dtype=np.int8),
                                    size=(inference["cluster_sign_swap_permutation"]["permutations"], len(unique_clusters)))
        arrays = {"bootstrap_cluster_indices": boot_clusters, "permutation_cluster_signs": perm_signs}
        for baseline in protocol["primary_comparisons"]["baselines"]:
            for metric in protocol["primary_comparisons"]["metrics"]:
                result, bootstrap, permutation = contrast_inference(
                    primary, baseline, metric, cluster_rows, cluster_index, boot_clusters, perm_signs)
                test_name = f"{baseline}__{metric}"
                arrays[f"bootstrap__{test_name}"] = bootstrap
                arrays[f"permutation__{test_name}"] = permutation
                seed_effects = effects.loc[(effects["context"] == context) & (effects["baseline"] == baseline) &
                                           (effects["metric"] == metric)].sort_values("seed")["effect"].to_numpy(float)
                result.update({"context": context, "baseline": baseline, "candidate": "context_gated_full",
                               "metric": metric, "test": test_name,
                               "seed_effects": seed_effects.tolist(),
                               "positive_seeds": int((seed_effects > 0).sum()),
                               "mean_seed_effect": float(seed_effects.mean()),
                               "median_seed_effect": float(np.median(seed_effects))})
                primary_rows.append(result)
        np.savez_compressed(output / f"primary_inference__{context}.npz", **arrays)
    adjusted = holm_adjust([row["p_cluster_swap"] for row in primary_rows])
    if len(primary_rows) != protocol["primary_comparisons"]["expected_endpoints"]:
        raise RuntimeError("Primary endpoint count mismatch")
    for row, p_holm in zip(primary_rows, adjusted):
        row["p_holm"] = float(p_holm)
        row["pass"] = bool(row["observed_effect"] > 0 and row["ci95"][0] > 0 and
                           p_holm < 0.05 and row["positive_seeds"] >= 8)
    family_pass = all(row["pass"] for row in primary_rows)
    gating_rows = [row for row in primary_rows if row["baseline"] == "shared_full"]
    context_status = {context: all(row["pass"] for row in primary_rows if row["context"] == context)
                      for context in contexts}
    output_files = {path.name: {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}
                    for path in sorted(output.iterdir()) if path.is_file()}
    summary = {
        "schema": "a8-rk31-known-context-applicability-result-v1",
        "status": "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION",
        "scientific_conclusion": ("KNOWN_CONTEXT_GATED_MFE_APPLICABILITY_SUPPORTED_RETROSPECTIVELY" if family_pass
                                  else "KNOWN_CONTEXT_GATED_MFE_APPLICABILITY_NOT_SUPPORTED"),
        "known_context_applicability_pass": bool(family_pass),
        "gating_over_shared_full_pass": bool(all(row["pass"] for row in gating_rows)),
        "context_status": context_status,
        "evidence_status": protocol["evidence_status"],
        "protocol_sha256": sha256(args.protocol),
        "analysis_script_sha256": sha256(Path(__file__).resolve()),
        "input_analysis_sha256": sha256(Path(protocol["inputs"]["analysis_csv"]["path"])),
        "n_variants": len(analysis), "n_clusters": int(analysis["sequence_cluster_id"].nunique()),
        "primary_seed": primary_seed, "ridge_fit_count": fit_count,
        "device": "CPU_ONLY", "primary_endpoints": primary_rows,
        "primary_absolute_performance": metrics.loc[metrics["seed"] == primary_seed].drop(columns="seed").to_dict("records"),
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - wall_start,
        "outputs": output_files,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                        "scipy": scipy.__version__, "sklearn": sklearn.__version__},
        "scientific_boundaries": protocol["scientific_boundaries"],
        "interpretation_boundary": "Retrospective known-context variant-OOD only. Failure rejects this broad gated-applicability claim, not every possible context-dependent mechanism. No unseen-context transport, causal, protein-OOD, functional-untouched or SOTA claim."
    }
    write_json(args.summary, summary)
    write_json(args.artifact_root / "RK31_MODEL_SUMMARY.json", summary)
    print(json.dumps({"status": summary["status"], "scientific_conclusion": summary["scientific_conclusion"],
                      "family_pass": family_pass, "gating_over_shared_full_pass": summary["gating_over_shared_full_pass"],
                      "context_status": context_status, "fits": fit_count, "elapsed_seconds": summary["elapsed_seconds"],
                      "summary": str(args.summary)}, indent=2))


if __name__ == "__main__":
    main()
