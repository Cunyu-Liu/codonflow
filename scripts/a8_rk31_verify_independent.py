#!/usr/bin/env python3
"""Independent RK31 recomputation; never imports the production or RK28 helpers."""
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
from scipy.stats import rankdata


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def spearman(x, y) -> float:
    rx, ry = rankdata(np.asarray(x, float)), rankdata(np.asarray(y, float))
    dx, dy = rx - rx.mean(), ry - ry.mean()
    denominator = float(np.sqrt(np.dot(dx, dx) * np.dot(dy, dy)))
    return float("nan") if denominator == 0 else float(np.dot(dx, dy) / denominator)


def make_folds(labels, seed: int, n_folds: int = 5):
    labels = np.asarray(labels, dtype=int)
    identifiers = np.array(sorted(set(labels.tolist())), dtype=int)
    rng = np.random.default_rng(seed)
    shuffled = identifiers[rng.permutation(len(identifiers))].tolist()
    sizes = {int(c): int(np.sum(labels == c)) for c in identifiers}
    ordered = sorted(shuffled, key=lambda c: -sizes[int(c)])
    loads = np.zeros(n_folds, dtype=int)
    assignment = {}
    for cluster in ordered:
        candidates = np.flatnonzero(loads == loads.min())
        fold = int(rng.choice(candidates))
        assignment[int(cluster)] = fold
        loads[fold] += sizes[int(cluster)]
    return np.array([assignment[int(c)] for c in labels], dtype=int), loads.tolist()


def make_long(frame: pd.DataFrame, contexts: list[str], nonreference: list[str]) -> pd.DataFrame:
    rows = []
    for context in contexts:
        part = frame.copy()
        part["context"] = context
        part["target"] = part[f"target__{context}"].astype(float)
        for other in nonreference:
            part[f"context__{other}"] = float(context == other)
        rows.append(part)
    return pd.concat(rows, ignore_index=True)


def add_gating(frame: pd.DataFrame, protocol: dict) -> pd.DataFrame:
    result = frame.copy()
    for indicator in protocol["features"]["nonreference_context_indicators"]:
        for mfe in protocol["features"]["structure_addition"]:
            result[f"{indicator}__x__{mfe}"] = result[indicator].to_numpy(float) * result[mfe].to_numpy(float)
    return result


def feature_list(protocol: dict, arm: str) -> list[str]:
    simple = list(protocol["features"]["simple"])
    mfe = list(protocol["features"]["structure_addition"])
    indicators = list(protocol["features"]["nonreference_context_indicators"])
    if arm == "shared_simple":
        return simple + indicators
    if arm == "shared_full":
        return simple + mfe + indicators
    if arm == "context_gated_full":
        return simple + mfe + indicators + [f"{indicator}__x__{name}" for indicator in indicators for name in mfe]
    if arm == "no_transport_simple":
        return simple
    if arm == "no_transport_full":
        return simple + mfe
    raise ValueError(arm)


def ridge_predict(train: pd.DataFrame, test: pd.DataFrame, names: list[str]) -> np.ndarray:
    x = train[names].to_numpy(float)
    z = test[names].to_numpy(float)
    y = train["target"].to_numpy(float)
    xm, xs = x.mean(axis=0), x.std(axis=0, ddof=0)
    ym, ys = float(y.mean()), float(y.std(ddof=0))
    if np.any(xs <= 0) or ys <= 0:
        raise RuntimeError("Degenerate scaling")
    x = (x - xm) / xs
    z = (z - xm) / xs
    y = (y - ym) / ys
    # Independently solve the centered L2 system rather than calling production's sklearn helper.
    coefficients = np.linalg.solve(x.T @ x + np.eye(x.shape[1], dtype=float), x.T @ y)
    prediction = (z @ coefficients) * ys + ym
    if not np.isfinite(prediction).all():
        raise RuntimeError("Nonfinite independent prediction")
    return prediction


def holm(values) -> np.ndarray:
    p = np.asarray(values, float)
    order = np.argsort(p)
    result = np.empty(len(p), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        result[index] = min(1.0, running)
    return result


def effect(frame: pd.DataFrame, baseline: str, metric: str) -> float:
    y = frame["target"].to_numpy(float)
    b = frame[baseline].to_numpy(float)
    c = frame["context_gated_full"].to_numpy(float)
    if metric == "spearman_effect":
        return spearman(y, c) - spearman(y, b)
    return float(np.mean((y - b) ** 2 - (y - c) ** 2))


def inference(frame: pd.DataFrame, baseline: str, metric: str, cluster_rows, cluster_index,
              boot_clusters, perm_signs):
    y = frame["target"].to_numpy(float)
    b = frame[baseline].to_numpy(float)
    c = frame["context_gated_full"].to_numpy(float)
    observed = effect(frame, baseline, metric)
    boot = np.empty(len(boot_clusters), dtype=float)
    perm = np.empty(len(boot_clusters), dtype=float)
    difference = (y - b) ** 2 - (y - c) ** 2
    if metric == "mse_improvement":
        perm = (perm_signs[:, cluster_index] * difference).mean(axis=1)
    for i in range(len(boot_clusters)):
        selected = boot_clusters[i]
        rows = np.concatenate([cluster_rows[int(v)] for v in selected])
        if metric == "spearman_effect":
            boot[i] = spearman(y[rows], c[rows]) - spearman(y[rows], b[rows])
            swap = perm_signs[i, cluster_index] < 0
            bs = np.where(swap, c, b)
            cs = np.where(swap, b, c)
            perm[i] = spearman(y, cs) - spearman(y, bs)
        else:
            weights = np.bincount(selected, minlength=len(cluster_rows))[cluster_index].astype(float)
            boot[i] = float(np.dot(weights, difference) / weights.sum())
    p = float((1 + np.sum(np.abs(perm) >= abs(observed))) / (len(boot) + 1))
    return {"observed_effect": float(observed),
            "ci95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
            "p_cluster_swap": p, "bootstrap_median": float(np.median(boot))}, boot, perm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--freeze-report", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    protocol = json.loads(args.protocol.read_text())
    result = json.loads(args.result.read_text())
    checks = []
    maxima = {"prediction": 0.0, "fold": 0.0, "metric": 0.0, "effect": 0.0,
              "inference": 0.0, "primary_effect": 0.0, "primary_ci": 0.0}

    def check(name: str, condition: bool, evidence=None) -> None:
        checks.append({"check": name, "pass": bool(condition), "evidence": evidence})

    try:
        check("result_pending_independent", result["status"] == "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION")
        check("protocol_binding", result["protocol_sha256"] == sha256(args.protocol))
        freeze = json.loads(args.freeze_report.read_text())
        check("freeze_binding", freeze.get("status") == "PASS_RK31_PREEXPERIMENT_FREEZE" and
              freeze.get("protocol_sha256") == sha256(args.protocol) and
              freeze.get("production_script_sha256") == result.get("analysis_script_sha256"))
        for key, item in protocol["inputs"].items():
            check(f"input_hash_{key}", sha256(Path(item["path"])) == item["sha256"])
        for name, item in result["outputs"].items():
            path = args.artifact_root / "model" / name
            check(f"output_hash_{name}", path.exists() and sha256(path) == item["sha256"])
        analysis = pd.read_csv(protocol["inputs"]["analysis_csv"]["path"])
        analysis["sequence_cluster_id"] = analysis["sequence_cluster_id"].astype(int)
        check("cohort_dimensions", len(analysis) == 126 and analysis["sequence_cluster_id"].nunique() == 69)
        contexts = protocol["contexts"]
        nonreference = [c for c in contexts if c != protocol["reference_context"]]
        arms = ["null", "shared_simple", "shared_full", "no_transport_simple", "no_transport_full", "context_gated_full"]
        pooled = ["shared_simple", "shared_full", "context_gated_full"]
        separate = ["no_transport_simple", "no_transport_full"]
        seeds = protocol["outer_evaluation"]["sensitivity_seeds"]
        own_predictions, own_folds, own_metrics, own_effects = [], [], [], []
        own_fit_count = 0
        for seed in seeds:
            folds, loads = make_folds(analysis["sequence_cluster_id"].to_numpy(int), int(seed))
            fold_frame = analysis[["variant_id", "sequence_cluster_id"]].copy()
            fold_frame.insert(0, "seed", seed)
            fold_frame["fold"] = folds
            own_folds.append(fold_frame)
            current = make_long(analysis[["variant_id", "sequence_cluster_id"] +
                                         [f"target__{context}" for context in contexts]], contexts, nonreference)
            current.insert(0, "seed", seed)
            current["fold"] = np.tile(folds, len(contexts))
            for arm in arms:
                current[arm] = np.nan
            positions = {(row.context, row.variant_id): i for i, row in
                         enumerate(current[["context", "variant_id"]].itertuples(index=False))}
            for fold in range(5):
                train = analysis.loc[folds != fold].copy()
                test = analysis.loc[folds == fold].copy()
                check(f"cluster_disjoint_{seed}_{fold}", not bool(set(train["sequence_cluster_id"]) & set(test["sequence_cluster_id"])))
                train_long = add_gating(make_long(train, contexts, nonreference), protocol)
                test_long = add_gating(make_long(test, contexts, nonreference), protocol)
                test_positions = [positions[(row.context, row.variant_id)] for row in
                                  test_long[["context", "variant_id"]].itertuples(index=False)]
                for arm in pooled:
                    pred = ridge_predict(train_long, test_long, feature_list(protocol, arm))
                    current.iloc[test_positions, current.columns.get_loc(arm)] = pred
                    own_fit_count += 1
                for context in contexts:
                    train_context = train.copy()
                    test_context = test.copy()
                    train_context["target"] = train_context[f"target__{context}"]
                    pos = [positions[(context, variant)] for variant in test_context["variant_id"]]
                    current.iloc[pos, current.columns.get_loc("null")] = float(train_context["target"].mean())
                    for arm in separate:
                        pred = ridge_predict(train_context, test_context, feature_list(protocol, arm))
                        current.iloc[pos, current.columns.get_loc(arm)] = pred
                        own_fit_count += 1
            check(f"finite_predictions_{seed}", np.isfinite(current[arms].to_numpy(float)).all())
            own_predictions.append(current)
            for context in contexts:
                group = current.loc[current["context"] == context].reset_index(drop=True)
                y = group["target"].to_numpy(float)
                for arm in arms:
                    pred = group[arm].to_numpy(float)
                    own_metrics.append({"seed": seed, "context": context, "arm": arm,
                                        "spearman": spearman(y, pred), "mse": float(np.mean((y - pred) ** 2))})
                for baseline in protocol["primary_comparisons"]["baselines"]:
                    for metric in protocol["primary_comparisons"]["metrics"]:
                        own_effects.append({"seed": seed, "context": context, "baseline": baseline, "metric": metric,
                                            "effect": effect(group, baseline, metric)})
        check("independent_fit_count", own_fit_count == 450 and result["ridge_fit_count"] == 450, own_fit_count)
        own_pred = pd.concat(own_predictions, ignore_index=True)
        own_fold = pd.concat(own_folds, ignore_index=True)
        own_metric = pd.DataFrame(own_metrics)
        own_effect = pd.DataFrame(own_effects)
        production_pred = pd.read_csv(args.artifact_root / "model/known_context_oof_predictions.csv")
        production_fold = pd.read_csv(args.artifact_root / "model/whole_cluster_fold_assignments.csv")
        production_metric = pd.read_csv(args.artifact_root / "model/seed_metrics.csv")
        production_effect = pd.read_csv(args.artifact_root / "model/seed_effects.csv")
        training_log = pd.read_csv(args.artifact_root / "model/training_log.csv")
        check("prediction_schema", len(production_pred) == 3780 and len(own_pred) == 3780)
        check("fold_schema", len(production_fold) == 1260 and len(own_fold) == 1260)
        keys = ["seed", "context", "variant_id"]
        own_pred = own_pred.sort_values(keys).reset_index(drop=True)
        production_pred = production_pred.sort_values(keys).reset_index(drop=True)
        check("prediction_keys_exact", own_pred[keys + ["sequence_cluster_id", "fold"]].equals(
            production_pred[keys + ["sequence_cluster_id", "fold"]]))
        check("targets_exact", np.array_equal(own_pred["target"].to_numpy(float), production_pred["target"].to_numpy(float)))
        for arm in arms:
            delta = float(np.max(np.abs(own_pred[arm].to_numpy(float) - production_pred[arm].to_numpy(float))))
            maxima["prediction"] = max(maxima["prediction"], delta)
            check(f"prediction_{arm}", delta < 1e-9, delta)
        fold_keys = ["seed", "variant_id"]
        own_fold = own_fold.sort_values(fold_keys).reset_index(drop=True)
        production_fold = production_fold.sort_values(fold_keys).reset_index(drop=True)
        fold_delta = int(np.sum(own_fold["fold"].to_numpy(int) != production_fold["fold"].to_numpy(int)))
        maxima["fold"] = fold_delta
        check("folds_exact", fold_delta == 0 and own_fold[fold_keys + ["sequence_cluster_id"]].equals(
            production_fold[fold_keys + ["sequence_cluster_id"]]), fold_delta)
        metric_keys = ["seed", "context", "arm"]
        own_metric = own_metric.sort_values(metric_keys).reset_index(drop=True)
        production_metric = production_metric.sort_values(metric_keys).reset_index(drop=True)
        check("metric_keys", own_metric[metric_keys].equals(production_metric[metric_keys]))
        for metric in ["spearman", "mse"]:
            delta = float(np.max(np.abs(own_metric[metric].to_numpy(float) - production_metric[metric].to_numpy(float))))
            maxima["metric"] = max(maxima["metric"], delta)
            check(f"metric_{metric}", delta < 1e-9, delta)
        effect_keys = ["seed", "context", "baseline", "metric"]
        own_effect = own_effect.sort_values(effect_keys).reset_index(drop=True)
        production_effect = production_effect.sort_values(effect_keys).reset_index(drop=True)
        check("effect_keys", own_effect[effect_keys].equals(production_effect[effect_keys]))
        effect_delta = float(np.max(np.abs(own_effect["effect"].to_numpy(float) - production_effect["effect"].to_numpy(float))))
        maxima["effect"] = effect_delta
        check("seed_effects", effect_delta < 1e-9, effect_delta)
        absolute_map = {(int(row["seed"]), row["context"], row["arm"]): row for row in own_metric.to_dict("records")}
        absolute_ok = True
        for row in result["primary_absolute_performance"]:
            reference = absolute_map[(protocol["outer_evaluation"]["primary_seed"], row["context"], row["arm"])]
            absolute_ok &= abs(float(row["spearman"]) - reference["spearman"]) < 1e-9 and abs(float(row["mse"]) - reference["mse"]) < 1e-9
        check("primary_absolute_summary", absolute_ok and len(result["primary_absolute_performance"]) == 18)
        check("training_log_count", len(training_log) == 450 and int(training_log["model_fits"].sum()) == 450)
        check("training_log_no_leakage_flags", not training_log["cluster_leakage"].astype(bool).any() and
              not training_log["held_out_outcomes_used_as_features"].astype(bool).any())

        primary_seed = protocol["outer_evaluation"]["primary_seed"]
        own_primary_rows = []
        for context in contexts:
            frame = own_pred.loc[(own_pred["context"] == context) & (own_pred["seed"] == primary_seed)].reset_index(drop=True)
            cluster_ids = frame["sequence_cluster_id"].to_numpy(int)
            unique = np.array(sorted(set(cluster_ids.tolist())), dtype=int)
            cluster_index = np.searchsorted(unique, cluster_ids)
            cluster_rows = [np.flatnonzero(cluster_index == i) for i in range(len(unique))]
            rng_boot = np.random.default_rng(protocol["inference"]["cluster_bootstrap"]["seed"])
            boot_clusters = rng_boot.integers(0, len(unique), size=(10000, len(unique)), dtype=np.int16)
            rng_perm = np.random.default_rng(protocol["inference"]["cluster_sign_swap_permutation"]["seed"])
            signs = rng_perm.choice(np.array([-1, 1], dtype=np.int8), size=(10000, len(unique)))
            npz = np.load(args.artifact_root / f"model/primary_inference__{context}.npz")
            check(f"inference_indices_{context}", np.array_equal(npz["bootstrap_cluster_indices"], boot_clusters) and
                  np.array_equal(npz["permutation_cluster_signs"], signs))
            for baseline in protocol["primary_comparisons"]["baselines"]:
                for metric in protocol["primary_comparisons"]["metrics"]:
                    row, boot, perm = inference(frame, baseline, metric, cluster_rows, cluster_index, boot_clusters, signs)
                    name = f"{baseline}__{metric}"
                    for label, own_array in [("bootstrap", boot), ("permutation", perm)]:
                        production_array = npz[f"{label}__{name}"]
                        delta = float(np.max(np.abs(own_array - production_array)))
                        maxima["inference"] = max(maxima["inference"], delta)
                        check(f"{label}_{context}_{name}", own_array.shape == production_array.shape and
                              own_array.dtype == production_array.dtype and delta < 1e-8, delta)
                    seed_values = own_effect.loc[(own_effect["context"] == context) & (own_effect["baseline"] == baseline) &
                                                 (own_effect["metric"] == metric) & (own_effect["seed"] == primary_seed)]
                    # Seed sensitivity is taken from all independently recomputed seed effects below.
                    all_seed_effects = own_effect.loc[(own_effect["context"] == context) & (own_effect["baseline"] == baseline) &
                                                      (own_effect["metric"] == metric)].sort_values("seed")["effect"].to_numpy(float)
                    row.update({"context": context, "baseline": baseline, "metric": metric,
                                "test": name, "seed_effects": all_seed_effects.tolist(),
                                "positive_seeds": int((all_seed_effects > 0).sum())})
                    own_primary_rows.append(row)
        check("primary_endpoint_count", len(own_primary_rows) == 24 and len(result["primary_endpoints"]) == 24)
        adjusted = holm([row["p_cluster_swap"] for row in own_primary_rows])
        production_primary = {(r["context"], r["baseline"], r["metric"]): r for r in result["primary_endpoints"]}
        for row, p_holm in zip(own_primary_rows, adjusted):
            row["p_holm"] = float(p_holm)
            row["pass"] = bool(row["observed_effect"] > 0 and row["ci95"][0] > 0 and p_holm < 0.05 and row["positive_seeds"] >= 8)
            other = production_primary[(row["context"], row["baseline"], row["metric"])]
            effect_delta = abs(row["observed_effect"] - other["observed_effect"])
            ci_delta = max(abs(row["ci95"][0] - other["ci95"][0]), abs(row["ci95"][1] - other["ci95"][1]))
            maxima["primary_effect"] = max(maxima["primary_effect"], effect_delta)
            maxima["primary_ci"] = max(maxima["primary_ci"], ci_delta)
            check(f"primary_{row['context']}_{row['test']}", effect_delta < 1e-9 and ci_delta < 1e-8 and
                  row["p_cluster_swap"] == other["p_cluster_swap"] and row["p_holm"] == other["p_holm"] and
                  row["pass"] == other["pass"] and row["positive_seeds"] == other["positive_seeds"],
                  {"effect_delta": effect_delta, "ci_delta": ci_delta})
        family_pass = all(row["pass"] for row in own_primary_rows)
        gating_pass = all(row["pass"] for row in own_primary_rows if row["baseline"] == "shared_full")
        context_status = {context: all(row["pass"] for row in own_primary_rows if row["context"] == context)
                          for context in contexts}
        expected_conclusion = ("KNOWN_CONTEXT_GATED_MFE_APPLICABILITY_SUPPORTED_RETROSPECTIVELY" if family_pass
                               else "KNOWN_CONTEXT_GATED_MFE_APPLICABILITY_NOT_SUPPORTED")
        check("context_status", context_status == result["context_status"], context_status)
        check("family_conclusion", family_pass == result["known_context_applicability_pass"] and
              gating_pass == result["gating_over_shared_full_pass"] and expected_conclusion == result["scientific_conclusion"],
              {"family_pass": family_pass, "gating_pass": gating_pass, "conclusion": expected_conclusion})
        check("functional_untouched_closed", protocol["scientific_boundaries"]["functional_untouched_read"] is False)
        check("generator_closed", protocol["scientific_boundaries"]["generator_training_authorized"] is False)
        failed = [c for c in checks if not c["pass"]]
        status = "PASS_INDEPENDENT_VERIFICATION" if not failed else "FAIL_INDEPENDENT_VERIFICATION"
        report = {"schema": "a8-rk31-independent-verification-v1", "status": status,
                  "created_utc": datetime.now(timezone.utc).isoformat(),
                  "protocol_sha256": sha256(args.protocol), "result_sha256": sha256(args.result),
                  "independent_script_sha256": sha256(Path(__file__).resolve()),
                  "checks_total": len(checks), "checks_passed": len(checks) - len(failed), "failed_checks": failed,
                  "checks": checks, "max_abs_differences": maxima,
                  "independent_fit_count": own_fit_count, "production_module_imported": False,
                  "rk28_production_helper_imported": False,
                  "known_context_applicability_pass": family_pass, "gating_over_shared_full_pass": gating_pass,
                  "scientific_conclusion": expected_conclusion,
                  "functional_untouched_read": False, "generator_training_authorized": False,
                  "elapsed_seconds": time.perf_counter() - started,
                  "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                                  "scipy": scipy.__version__, "sklearn": sklearn.__version__}}
    except Exception as exc:
        report = {"schema": "a8-rk31-independent-verification-v1", "status": "FAIL_INDEPENDENT_VERIFICATION",
                  "created_utc": datetime.now(timezone.utc).isoformat(), "error": repr(exc),
                  "checks_total": len(checks), "checks_passed": sum(c["pass"] for c in checks), "checks": checks,
                  "max_abs_differences": maxima, "production_module_imported": False,
                  "elapsed_seconds": time.perf_counter() - started}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}",
                      "max_abs_differences": maxima, "elapsed_seconds": report["elapsed_seconds"],
                      "output": str(args.output)}, indent=2))
    if report["status"] != "PASS_INDEPENDENT_VERIFICATION":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
