#!/usr/bin/env python3
"""RK35 production: RK33-window coverage transport within the frozen Kudla cohort.

Complements RK34 (matched N-mask factorial context decomposition, parallel session).
RK35 tests NATURAL windows: does the actual RK33 slice CDS[3:45] (1-based CDS4-45)
retain the RK32 local-structure increment within Kudla, and does exact start-aware
coverage beat it? Primary confirmatory contrasts: trunc_vs_simple, exact_vs_trunc
(8 tests, Holm(8)). Gate: exact_vs_simple must reproduce RK32 vienna_local within
1e-12. Secondary descriptive (no gate): atg_vs_trunc, exact_vs_atg, trunc_d0_vs_simple
(12 tests, Holm(12) descriptive only; body-shift confounded, decomposition deferred to RK34).

Refuses to run unless the frozen protocol SHA matches and the production script SHA
matches the protocol gate. Atomic outputs; no overwrite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

MODELS = ("ridge", "histgb")
METRICS = ("spearman_effect", "mse_improvement")
# (arm_a, arm_b); effect = metric(arm_b) - metric(arm_a); positive favors arm_b.
PRIMARY_CONTRASTS = {
    "trunc_vs_simple": ("simple", "trunc_local"),
    "exact_vs_trunc": ("trunc_local", "exact_local"),
}
GATE_CONTRAST = {"exact_vs_simple": ("simple", "exact_local")}
SECONDARY_CONTRASTS = {
    "atg_vs_trunc": ("trunc_local", "cds_start_local"),
    "exact_vs_atg": ("cds_start_local", "exact_local"),
    "trunc_d0_vs_simple": ("simple", "trunc_local_d0"),
}
NEW_ARMS = ("cds_start_local", "trunc_local", "trunc_local_d0")
REUSED_ARMS = {"simple": "simple", "exact_local": "vienna_local"}
ARM_STRUCTURE = {
    "exact_local": "vienna_exact_local_mfe",
    "cds_start_local": "vienna_cds_start_mfe",
    "trunc_local": "vienna_trunc_mfe",
    "trunc_local_d0": "vienna_trunc_d0_mfe",
}
SIMPLE_FEATURES = ["CAI", "gc_cds", "gc3_cds"]


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


def spearman(x, y) -> float:
    a = rankdata(np.asarray(x, dtype=float))
    b = rankdata(np.asarray(y, dtype=float))
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt(np.dot(a, a) * np.dot(b, b)))
    return float(np.dot(a, b) / denom) if denom else float("nan")


def make_cluster_folds(cluster_labels, seed: int):
    unique = sorted(set(int(c) for c in cluster_labels))
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(unique))
    shuffled = [unique[i] for i in order]
    sizes = {c: int(np.sum(cluster_labels == c)) for c in unique}
    shuffled.sort(key=lambda c: -sizes[c])
    loads = [0] * 5
    assignment = {}
    for c in shuffled:
        best = min(loads)
        candidates = [i for i in range(5) if loads[i] == best]
        fold = int(rng.choice(np.array(candidates)))
        assignment[c] = fold
        loads[fold] += sizes[c]
    folds = np.array([assignment[int(c)] for c in cluster_labels], dtype=int)
    return folds, loads


def fit_predict(model_name: str, features, train: pd.DataFrame, test: pd.DataFrame, rng_seed: int):
    if model_name == "ridge":
        pipe = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        pipe.fit(train[features], train["target"])
        return np.asarray(pipe.predict(test[features]), dtype=float)
    model = HistGradientBoostingRegressor(
        loss="squared_error", learning_rate=0.05, max_iter=200, max_leaf_nodes=7,
        min_samples_leaf=10, l2_regularization=1.0, early_stopping=False, random_state=rng_seed,
    )
    model.fit(train[features], train["target"])
    return np.asarray(model.predict(test[features]), dtype=float)


def holm(pvalues) -> list[float]:
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty(len(p), dtype=float)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (len(p) - rank) * p[idx])
        adjusted[idx] = min(1.0, running)
    return adjusted.tolist()


def contrast_test_name(model_name: str, contrast: str, metric: str) -> str:
    return f"{model_name}__{contrast}__{metric}"


def pass_rule(row: dict) -> bool:
    return bool(row["observed_effect"] > 0 and row["ci95"][0] > 0 and row["p_holm"] < 0.05 and row["positive_seeds"] >= 8)


def decide(gate_pass: bool, contrast_results: dict):
    if not gate_pass:
        return "CONSISTENCY_GATE_FAILED_NOT_EVALUATED", "gate_failed"
    if contrast_results["trunc_vs_simple"]["all_four_pass"]:
        return "RK33_COVERAGE_RETAINS_INCREMENT_WITHIN_KUDLA_RETROSPECTIVELY", "D1"
    if contrast_results["exact_vs_trunc"]["all_four_pass"]:
        return "START_AWARE_COVERAGE_NECESSARY_WITHIN_KUDLA_RETROSPECTIVELY", "D2"
    return "COVERAGE_TRANSPORT_NOT_DISCRIMINATED_RETROSPECTIVELY", "D3"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--output-root", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()
    wall_start = time.perf_counter()
    started_utc = datetime.now(timezone.utc).isoformat()
    protocol = json.loads(args.protocol.read_text())
    if protocol["status"] != "FROZEN_BEFORE_RK35_EXPRESSION_ASSOCIATION_OR_MODEL_FIT":
        raise ValueError("protocol not frozen")
    script_sha = sha256(Path(__file__).resolve())
    if script_sha != protocol["code"]["production_script_sha256"]:
        raise ValueError("production script SHA does not match frozen protocol")
    paths = {key: Path(entry["path"]) for key, entry in protocol["inputs"].items()}
    for key, entry in protocol["inputs"].items():
        if sha256(paths[key]) != entry["sha256"]:
            raise ValueError(f"input SHA mismatch: {key}")
    args.output_root.mkdir(parents=True, exist_ok=True)

    # ---- cohort ----
    raw = pd.read_csv(paths["main_csv"])
    if len(raw) != 154:
        raise ValueError("expected 154 measurement rows")
    groups = []
    for cds_sha, grp in raw.groupby("cds_sha256", sort=False):
        cds = str(grp["cds"].iloc[0]).upper()
        if hashlib.sha256(cds.encode()).hexdigest() != cds_sha:
            raise ValueError("cds hash mismatch")
        if grp["cds"].nunique() != 1 or grp["exact_cds_group"].nunique() != 1:
            raise ValueError("inconsistent group")
        chars = np.array(list(cds))
        groups.append({
            "cds_sha256": cds_sha,
            "exact_cds_group": str(grp["exact_cds_group"].iloc[0]),
            "first_source_row": int(grp["source_row"].min()),
            "source_rows": ";".join(str(int(v)) for v in sorted(grp["source_row"])),
            "seqIds": ";".join(str(v) for v in grp["seqId"]),
            "n_measurements": int(len(grp)),
            "CAI": float(grp["CAI"].iloc[0]),
            "gc_cds": float(np.mean(np.isin(chars, ["G", "C"]))),
            "gc3_cds": float(np.mean(np.isin(chars[2::3], ["G", "C"]))),
            "target": float(grp["log10_expression"].mean()),
        })
    frame = pd.DataFrame(groups).sort_values("first_source_row").reset_index(drop=True)
    frame.insert(0, "group_id", [f"g{i:03d}" for i in range(len(frame))])
    if len(frame) != 150:
        raise ValueError("expected 150 groups")

    coverage = json.loads(paths["rk27_coverage_report"].read_text())
    if coverage["status"] != "PASS_LABEL_FREE_COVERAGE_AUDIT":
        raise ValueError("RK27 coverage not passed")
    facts = pd.read_csv(coverage["facts_csv"])
    if sha256(Path(coverage["facts_csv"])) != coverage["facts_sha256"]:
        raise ValueError("facts SHA mismatch")
    frame = frame.merge(facts[["cds_sha256", "sequence_cluster_id"]], on="cds_sha256", how="left", validate="one_to_one")
    if frame["sequence_cluster_id"].isna().any():
        raise ValueError("missing cluster id")
    frame["sequence_cluster_id"] = frame["sequence_cluster_id"].astype(int)
    if frame["sequence_cluster_id"].nunique() != 37:
        raise ValueError("expected 37 clusters")

    # ---- structure features ----
    rk32_preflight = pd.read_csv(paths["rk32_preflight_csv"])
    rk34_preflight = pd.read_csv(paths["rk35_preflight_csv"])
    frame = frame.merge(
        rk32_preflight[["exact_cds_group", "local_utr_minus4_cds38__dangles2", "local_cds42__dangles2"]],
        on="exact_cds_group", how="left", validate="one_to_one",
    )
    frame = frame.merge(
        rk34_preflight[["exact_cds_group", "trunc_cds4_45__dangles2", "trunc_cds4_45__dangles0"]],
        on="exact_cds_group", how="left", validate="one_to_one",
    )
    frame = frame.rename(columns={
        "local_utr_minus4_cds38__dangles2": "vienna_exact_local_mfe",
        "local_cds42__dangles2": "vienna_cds_start_mfe",
        "trunc_cds4_45__dangles2": "vienna_trunc_mfe",
        "trunc_cds4_45__dangles0": "vienna_trunc_d0_mfe",
    })
    for column in ARM_STRUCTURE.values():
        if not np.isfinite(frame[column].to_numpy(float)).all():
            raise ValueError(f"non-finite structure feature: {column}")
    analysis_path = args.output_root / "analysis_start_aware_150.csv"
    frame.to_csv(analysis_path, index=False)

    # ---- reuse RK32 OOF with hard gates ----
    rk32_oof = pd.read_csv(paths["rk32_oof_predictions"])
    rk32_folds = pd.read_csv(paths["rk32_fold_assignments"])
    rk32_result = json.loads(paths["rk32_result_v2"].read_text())
    for key, filename in (("rk32_oof_predictions", "oof_predictions.csv"), ("rk32_fold_assignments", "fold_assignments.csv"), ("rk32_seed_effects", "seed_effects.csv")):
        if sha256(paths[key]) != rk32_result["outputs"][filename]["sha256"]:
            raise ValueError(f"reuse SHA differs from RK32 result: {key}")
    reuse_columns = ["seed", "group_id", "cds_sha256", "sequence_cluster_id", "fold", "null"]
    for model_name in MODELS:
        for rk32_arm in REUSED_ARMS.values():
            reuse_columns.append(f"{model_name}_{rk32_arm}")
    rk32_oof = rk32_oof[reuse_columns]

    seeds = protocol["outer_evaluation"]["seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    cluster_labels = frame["sequence_cluster_id"].to_numpy(int)
    prediction_blocks, fold_rows, training_rows = [], [], []
    new_fit_count = 0
    reused_fit_count = 0
    for seed in seeds:
        folds, loads = make_cluster_folds(cluster_labels, seed)
        if seed == primary_seed and loads != coverage["selected_coverage"]["primary_seed_fold_sizes"]:
            raise ValueError("primary fold sizes differ from RK27 coverage")
        rk32_seed_folds = rk32_folds[rk32_folds["seed"] == seed].set_index("cds_sha256")
        rk32_seed_oof = rk32_oof[rk32_oof["seed"] == seed].set_index("cds_sha256")
        block = frame.copy()
        block["seed"] = seed
        block["fold"] = folds
        block["null"] = np.nan
        for model_name in MODELS:
            for arm in ("simple", "exact_local", *NEW_ARMS):
                block[f"{model_name}_{arm}"] = np.nan
        for fold in range(5):
            train_mask = folds != fold
            test_mask = folds == fold
            train = frame[train_mask]
            test = frame[test_mask]
            if not set(train["sequence_cluster_id"]).isdisjoint(set(test["sequence_cluster_id"])):
                raise ValueError("cluster leakage")
            train_mean = float(train["target"].mean())
            test_index = block.index[test_mask]
            block.loc[test_index, "null"] = train_mean
            for sha, group_id, cluster_id in zip(test["cds_sha256"], test["group_id"], test["sequence_cluster_id"]):
                rf = rk32_seed_folds.loc[sha]
                if int(rf["fold"]) != fold or int(rf["sequence_cluster_id"]) != int(cluster_id) or str(rf["group_id"]) != str(group_id):
                    raise ValueError("RK32 fold assignment mismatch")
                fold_rows.append({"seed": seed, "group_id": group_id, "cds_sha256": sha, "sequence_cluster_id": int(cluster_id), "fold": fold})
            for _, row in test.iterrows():
                sha = row["cds_sha256"]
                rk32_row = rk32_seed_oof.loc[sha]
                if int(rk32_row["fold"]) != fold:
                    raise ValueError("RK32 OOF fold mismatch")
                if abs(float(rk32_row["null"]) - train_mean) > 1e-12:
                    raise ValueError("RK32 null differs from recomputed train mean")
                index = block.index[block["cds_sha256"] == sha][0]
                for model_name in MODELS:
                    for new_arm, rk32_arm in REUSED_ARMS.items():
                        block.loc[index, f"{model_name}_{new_arm}"] = float(rk32_row[f"{model_name}_{rk32_arm}"])
            reused_fit_count += 2 * len(REUSED_ARMS)
            for model_name in MODELS:
                for arm in NEW_ARMS:
                    features = SIMPLE_FEATURES + [ARM_STRUCTURE[arm]]
                    pred = fit_predict(model_name, features, train, test, int(seed + fold))
                    block.loc[test_index, f"{model_name}_{arm}"] = pred
                    new_fit_count += 1
                    training_rows.append({"seed": seed, "fold": fold, "model": model_name, "arm": arm, "n_train": int(len(train)), "n_test": int(len(test)), "train_target_mean": train_mean, "new_model_fits": 1, "reused_model_fits": 0})
        prediction_blocks.append(block)
    predictions = pd.concat(prediction_blocks, ignore_index=True)
    if new_fit_count != 300 or reused_fit_count != 200:
        raise ValueError(f"fit accounting mismatch: new={new_fit_count} reused={reused_fit_count}")
    value_columns = [c for c in predictions if c == "null" or c.startswith("ridge_") or c.startswith("histgb_")]
    if not np.isfinite(predictions[value_columns].to_numpy(float)).all():
        raise ValueError("non-finite predictions")
    predictions.to_csv(args.output_root / "oof_predictions.csv", index=False)
    pd.DataFrame(fold_rows).to_csv(args.output_root / "fold_assignments.csv", index=False)
    training_log = pd.DataFrame(training_rows)
    training_log.to_csv(args.output_root / "training_log.csv", index=False)

    # ---- seed metrics / effects ----
    all_contrasts = {**PRIMARY_CONTRASTS, **GATE_CONTRAST, **SECONDARY_CONTRASTS}
    seed_metric_rows, seed_effect_rows = [], []
    for seed in seeds:
        current = predictions[predictions["seed"] == seed]
        y = current["target"].to_numpy(float)
        for column in value_columns:
            pred = current[column].to_numpy(float)
            seed_metric_rows.append({"seed": seed, "arm": column, "spearman": spearman(y, pred), "mse": float(np.mean((y - pred) ** 2))})
        for model_name in MODELS:
            for contrast, (arm_a, arm_b) in all_contrasts.items():
                pred_a = current[f"{model_name}_{arm_a}"].to_numpy(float)
                pred_b = current[f"{model_name}_{arm_b}"].to_numpy(float)
                seed_effect_rows.append({"seed": seed, "test": contrast_test_name(model_name, contrast, "spearman_effect"), "effect": spearman(y, pred_b) - spearman(y, pred_a)})
                seed_effect_rows.append({"seed": seed, "test": contrast_test_name(model_name, contrast, "mse_improvement"), "effect": float(np.mean((y - pred_a) ** 2 - (y - pred_b) ** 2))})
    seed_metrics = pd.DataFrame(seed_metric_rows)
    seed_effects = pd.DataFrame(seed_effect_rows)
    seed_metrics.to_csv(args.output_root / "seed_metrics.csv", index=False)
    seed_effects.to_csv(args.output_root / "seed_effects.csv", index=False)

    # ---- primary-seed inference ----
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

    def run_inference(contrasts: dict):
        names = [contrast_test_name(m, c, metric) for m in MODELS for c in contrasts for metric in METRICS]
        observed = {name: 0.0 for name in names}
        boot = {name: np.empty(resamples, dtype=float) for name in names}
        null = {name: np.empty(resamples, dtype=float) for name in names}
        pair_values = {}
        for model_name in MODELS:
            for contrast, (arm_a, arm_b) in contrasts.items():
                pred_a = primary[f"{model_name}_{arm_a}"].to_numpy(float)
                pred_b = primary[f"{model_name}_{arm_b}"].to_numpy(float)
                sname = contrast_test_name(model_name, contrast, "spearman_effect")
                mname = contrast_test_name(model_name, contrast, "mse_improvement")
                observed[sname] = spearman(y, pred_b) - spearman(y, pred_a)
                diff = (y - pred_a) ** 2 - (y - pred_b) ** 2
                observed[mname] = float(diff.mean())
                null[mname] = (perm_signs[:, cluster_index] * diff).mean(axis=1)
                pair_values[(model_name, contrast)] = (pred_a, pred_b, diff)
        for b in range(resamples):
            selected = boot_clusters[b]
            row_idx = np.concatenate([cluster_rows[int(c)] for c in selected])
            weights = np.bincount(selected, minlength=len(unique_clusters))[cluster_index].astype(float)
            y_boot = y[row_idx]
            swap = perm_signs[b, cluster_index] < 0
            for model_name in MODELS:
                for contrast in contrasts:
                    pred_a, pred_b, diff = pair_values[(model_name, contrast)]
                    sname = contrast_test_name(model_name, contrast, "spearman_effect")
                    mname = contrast_test_name(model_name, contrast, "mse_improvement")
                    boot[sname][b] = spearman(y_boot, pred_b[row_idx]) - spearman(y_boot, pred_a[row_idx])
                    boot[mname][b] = float(np.dot(weights, diff) / weights.sum())
                    sa = np.where(swap, pred_b, pred_a)
                    sb = np.where(swap, pred_a, pred_b)
                    null[sname][b] = spearman(y, sb) - spearman(y, sa)
        return names, observed, boot, null

    primary_names, primary_obs, primary_boot, primary_null = run_inference(PRIMARY_CONTRASTS)
    gate_names, gate_obs, gate_boot, gate_null = run_inference(GATE_CONTRAST)
    secondary_names, secondary_obs, secondary_boot, secondary_null = run_inference(SECONDARY_CONTRASTS)

    def summarize_tests(names, observed, boot, null):
        rows = []
        for name in names:
            if not np.isfinite(boot[name]).all() or not np.isfinite(null[name]).all():
                raise ValueError(f"non-finite inference: {name}")
            obs = float(observed[name])
            rows.append({
                "test": name, "observed_effect": obs,
                "ci95": [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))],
                "p_cluster_swap": float((1 + np.sum(np.abs(null[name]) >= abs(obs))) / (resamples + 1)),
                "bootstrap_median": float(np.median(boot[name])),
            })
        adjusted = holm([r["p_cluster_swap"] for r in rows])
        for row, p_holm in zip(rows, adjusted):
            effects = seed_effects[seed_effects["test"] == row["test"]].sort_values("seed")["effect"].to_numpy(float)
            row.update({
                "p_holm": p_holm, "seed_effects": effects.tolist(),
                "positive_seeds": int(np.sum(effects > 0)),
                "mean_seed_effect": float(effects.mean()), "median_seed_effect": float(np.median(effects)),
            })
            row["pass"] = pass_rule(row)
        return rows

    primary_tests = summarize_tests(primary_names, primary_obs, primary_boot, primary_null)
    gate_tests = summarize_tests(gate_names, gate_obs, gate_boot, gate_null)
    secondary_tests = summarize_tests(secondary_names, secondary_obs, secondary_boot, secondary_null)
    for row in secondary_tests:
        row["role"] = "secondary_descriptive_no_gate"

    # ---- consistency gate vs RK32 ----
    rk32_tests = {row["test"]: row for row in rk32_result["primary_tests"]}
    rk32_seed_effects = pd.read_csv(paths["rk32_seed_effects"])
    gate_details = []
    gate_pass = True
    for row in gate_tests:
        model_name, contrast, metric = row["test"].split("__")
        rk32_name = f"{model_name}__vienna_local__{metric}"
        reference = rk32_tests[rk32_name]
        deltas = {
            "observed_effect": abs(row["observed_effect"] - reference["observed_effect"]),
            "ci95_lower": abs(row["ci95"][0] - reference["ci95"][0]),
            "ci95_upper": abs(row["ci95"][1] - reference["ci95"][1]),
            "p_cluster_swap": abs(row["p_cluster_swap"] - reference["p_cluster_swap"]),
        }
        ref_effects = rk32_seed_effects[rk32_seed_effects["test"] == rk32_name].sort_values("seed")["effect"].to_numpy(float)
        deltas["seed_effects_max"] = float(np.max(np.abs(np.asarray(row["seed_effects"]) - ref_effects)))
        equal = all(v <= 1e-12 for v in deltas.values())
        gate_pass = gate_pass and equal and row["pass"]
        gate_details.append({"test": row["test"], "rk32_reference": rk32_name, "deltas": deltas, "bitwise_equal_within_1e-12": equal, "rk35_gate_pass": row["pass"]})

    contrast_results = {}
    for contrast in PRIMARY_CONTRASTS:
        rows = [r for r in primary_tests if r["test"].split("__")[1] == contrast]
        contrast_results[contrast] = {"n_tests": len(rows), "n_pass": sum(r["pass"] for r in rows), "all_four_pass": all(r["pass"] for r in rows)}
    conclusion, decision_code = decide(gate_pass, contrast_results)

    arrays = {}
    for prefix, boot, null in (("primary", primary_boot, primary_null), ("gate", gate_boot, gate_null), ("secondary", secondary_boot, secondary_null)):
        arrays.update({f"{prefix}_bootstrap__{name}": values for name, values in boot.items()})
        arrays.update({f"{prefix}_permutation__{name}": values for name, values in null.items()})
    arrays["bootstrap_cluster_indices"] = boot_clusters
    arrays["permutation_cluster_signs"] = perm_signs
    np.savez(args.output_root / "primary_inference_arrays.npz", **arrays)

    outputs = {}
    for name in ("analysis_start_aware_150.csv", "oof_predictions.csv", "fold_assignments.csv", "training_log.csv", "seed_metrics.csv", "seed_effects.csv", "primary_inference_arrays.npz"):
        p = args.output_root / name
        outputs[name] = {"path": str(p), "sha256": sha256(p), "bytes": p.stat().st_size}
    summary = {
        "schema": "a8-rk35-coverage-transport-result-v1",
        "status": "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION",
        "analysis_type": protocol["analysis_type"],
        "started_utc": started_utc, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "component_wall_seconds": float(time.perf_counter() - wall_start),
        "protocol_sha256": sha256(args.protocol), "analysis_script_sha256": script_sha,
        "n_measurement_rows": 154, "n_exact_cds_groups": 150, "n_sequence_clusters": 37,
        "primary_seed": primary_seed, "seeds": seeds, "folds_per_seed": 5,
        "arms": ["simple", "exact_local", *NEW_ARMS],
        "primary_contrasts": PRIMARY_CONTRASTS, "gate_contrast": GATE_CONTRAST, "secondary_contrasts": SECONDARY_CONTRASTS,
        "new_model_fits": new_fit_count, "reused_model_fits": reused_fit_count, "evaluated_model_fits": new_fit_count + reused_fit_count,
        "consistency_gate": {"pass": bool(gate_pass), "details": gate_details},
        "primary_absolute_performance": {
            model_name: {
                arm: {
                    "spearman": float(seed_metrics[(seed_metrics["seed"] == primary_seed) & (seed_metrics["arm"] == f"{model_name}_{arm}")]["spearman"].iloc[0]),
                    "mse": float(seed_metrics[(seed_metrics["seed"] == primary_seed) & (seed_metrics["arm"] == f"{model_name}_{arm}")]["mse"].iloc[0]),
                } for arm in ("simple", "exact_local", *NEW_ARMS)
            } for model_name in MODELS
        },
        "primary_tests": primary_tests, "gate_tests": gate_tests, "secondary_tests": secondary_tests,
        "contrast_results": contrast_results,
        "scientific_conclusion": conclusion, "decision_code": decision_code,
        "scientific_flags": {
            "functional_untouched_read": False, "generator_training_authorized": False,
            "RK_G1_complete": False, "independent_confirmation": False,
            "host_assay_identified": False, "protein_ood_claimed": False,
            "matched_body_decomposition_deferred_to_RK34": True,
        },
        "outputs": outputs,
    }
    atomic_json(args.summary, summary)
    print(json.dumps({k: summary[k] for k in ("status", "scientific_conclusion", "decision_code", "new_model_fits", "reused_model_fits", "consistency_gate", "contrast_results", "component_wall_seconds")}, indent=2))


if __name__ == "__main__":
    main()