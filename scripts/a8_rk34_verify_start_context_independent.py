#!/usr/bin/env python3
"""Independent RK34 raw-source reconstruction; does not import production code."""
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
FAMILIES = ["exact_vs_simple", "upstream_given_start", "start_given_upstream", "start_without_upstream", "upstream_without_start"]
MODELS = ["ridge", "histgb"]
METRICS = ["spearman_effect", "mse_improvement"]


def comparisons():
    result = []
    for analysis, dangles in (("primary", 2), ("sensitivity_d0", 0)):
        exact, start = f"exact_real_d{dangles}", f"start_only_d{dangles}"
        upstream, neither = f"upstream_only_d{dangles}", f"neither_d{dangles}"
        for family, a, b in (
            ("exact_vs_simple", exact, "simple"), ("upstream_given_start", exact, start),
            ("start_given_upstream", exact, upstream), ("start_without_upstream", start, neither),
            ("upstream_without_start", upstream, neither),
        ):
            result.append({"analysis": analysis, "family": family, "arm_a": a, "arm_b": b})
    return result


COMPARISONS = comparisons()
TEST_ORDER = [f"{c['analysis']}__{m}__{c['family']}__{metric}" for c in COMPARISONS for m in MODELS for metric in METRICS]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_seed_metrics(path):
    """Read the production metric schema, canonicalizing the CSV null-arm label."""
    frame = pd.read_csv(path)
    if list(frame.columns) != ["seed", "arm", "spearman", "mse"]:
        raise ValueError("unexpected seed-metric schema")
    frame["arm"] = frame["arm"].fillna("null")
    return frame


def vienna(sequence, dangles):
    md = RNA.md(); md.dangles = dangles; md.temperature = 37.0
    value = float(RNA.fold_compound(sequence.replace("T", "U"), md).mfe()[1])
    if not np.isfinite(value):
        raise ValueError("non-finite MFE")
    return value


def contexts(utr, cds):
    u, a, b = utr[-4:], cds[:3], cds[3:38]
    return {"exact_real": u + a + b, "start_only": "NNNN" + a + b,
            "upstream_only": u + "NNN" + b, "neither": "NNNNNNN" + b}


def rho(x, y):
    x, y = rankdata(x), rankdata(y)
    x, y = x - np.mean(x), y - np.mean(y)
    d = float(np.sqrt(np.dot(x, x) * np.dot(y, y)))
    return float(np.dot(x, y) / d) if d else float("nan")


def cluster_folds(labels, seed):
    labels = np.asarray(labels, dtype=int)
    ids = np.array(sorted(np.unique(labels)), dtype=int)
    rng = np.random.default_rng(seed)
    shuffled = ids[rng.permutation(len(ids))].tolist()
    sizes = {int(c): int(np.sum(labels == c)) for c in ids}
    ordered = sorted(shuffled, key=lambda c: -sizes[int(c)])
    loads = np.zeros(5, dtype=int)
    mapping = {}
    for cluster in ordered:
        choices = np.flatnonzero(loads == loads.min())
        fold = int(rng.choice(choices))
        mapping[int(cluster)] = fold
        loads[fold] += sizes[int(cluster)]
    return np.array([mapping[int(c)] for c in labels], dtype=int), loads.tolist()


def predict(model_name, features, train, test, random_state):
    if model_name == "ridge":
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    else:
        model = HistGradientBoostingRegressor(
            loss="squared_error", learning_rate=0.05, max_iter=200, max_leaf_nodes=7,
            min_samples_leaf=10, l2_regularization=1.0, early_stopping=False, random_state=random_state,
        )
    model.fit(train[features], train["target"])
    return np.asarray(model.predict(test[features]), dtype=float)


def holm(values):
    p = np.asarray(values, dtype=float)
    order = np.argsort(p)
    answer = np.empty(len(p), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        answer[index] = min(1.0, running)
    return answer.tolist()


def seed_statistics(frame, seed):
    current = frame[frame["seed"] == seed]
    y = current["target"].to_numpy(float)
    metrics = []
    for column in ["null"] + [f"{m}_{a}" for m in MODELS for a in ["simple"] + ARMS]:
        pred = current[column].to_numpy(float)
        metrics.append({"seed": seed, "arm": column, "spearman": rho(y, pred), "mse": float(np.mean((y - pred) ** 2))})
    effects = {}
    for spec in COMPARISONS:
        for model in MODELS:
            a = current[f"{model}_{spec['arm_a']}"].to_numpy(float)
            b = current[f"{model}_{spec['arm_b']}"].to_numpy(float)
            base = f"{spec['analysis']}__{model}__{spec['family']}"
            effects[f"{base}__spearman_effect"] = rho(y, a) - rho(y, b)
            effects[f"{base}__mse_improvement"] = float(np.mean((y - b) ** 2 - (y - a) ** 2))
    return metrics, effects


def inference(primary, resamples, bootstrap_seed, permutation_seed):
    primary = primary.reset_index(drop=True)
    y = primary["target"].to_numpy(float)
    labels = primary["sequence_cluster_id"].to_numpy(int)
    clusters = np.array(sorted(np.unique(labels)), dtype=int)
    cluster_index = np.searchsorted(clusters, labels)
    members = [np.flatnonzero(cluster_index == i) for i in range(len(clusters))]
    boot_ids = np.random.default_rng(bootstrap_seed).integers(0, len(clusters), size=(resamples, len(clusters)), dtype=np.int16)
    signs = np.random.default_rng(permutation_seed).choice(np.array([-1, 1], dtype=np.int8), size=(resamples, len(clusters)))
    observed = {name: 0.0 for name in TEST_ORDER}
    boot = {name: np.empty(resamples) for name in TEST_ORDER}
    null = {name: np.empty(resamples) for name in TEST_ORDER}
    pairs, metadata = {}, {}
    for spec in COMPARISONS:
        for model in MODELS:
            a = primary[f"{model}_{spec['arm_a']}"].to_numpy(float)
            b = primary[f"{model}_{spec['arm_b']}"].to_numpy(float)
            diff = (y - b) ** 2 - (y - a) ** 2
            base = f"{spec['analysis']}__{model}__{spec['family']}"
            sp, mse = f"{base}__spearman_effect", f"{base}__mse_improvement"
            observed[sp] = rho(y, a) - rho(y, b)
            observed[mse] = float(np.mean(diff))
            null[mse] = (signs[:, cluster_index] * diff).mean(axis=1)
            pairs[(spec["analysis"], model, spec["family"])] = (a, b, diff)
            metadata[sp] = {**spec, "model": model, "metric": "spearman_effect"}
            metadata[mse] = {**spec, "model": model, "metric": "mse_improvement"}
    for draw in range(resamples):
        selected = boot_ids[draw]
        rows = np.concatenate([members[int(c)] for c in selected])
        weights = np.bincount(selected, minlength=len(clusters))[cluster_index].astype(float)
        swap = signs[draw, cluster_index] < 0
        for spec in COMPARISONS:
            for model in MODELS:
                a, b, diff = pairs[(spec["analysis"], model, spec["family"])]
                base = f"{spec['analysis']}__{model}__{spec['family']}"
                sp, mse = f"{base}__spearman_effect", f"{base}__mse_improvement"
                boot[sp][draw] = rho(y[rows], a[rows]) - rho(y[rows], b[rows])
                boot[mse][draw] = float(np.dot(weights, diff) / weights.sum())
                new_a = np.where(swap, b, a)
                new_b = np.where(swap, a, b)
                null[sp][draw] = rho(y, new_a) - rho(y, new_b)
    rows = []
    for name in TEST_ORDER:
        obs = float(observed[name])
        rows.append({
            "test": name, **metadata[name], "observed_effect": obs,
            "ci95": [float(np.quantile(boot[name], 0.025)), float(np.quantile(boot[name], 0.975))],
            "p_cluster_swap": float((1 + np.sum(np.abs(null[name]) >= abs(obs))) / (resamples + 1)),
            "bootstrap_median": float(np.median(boot[name])), "confirmatory": metadata[name]["analysis"] == "primary",
        })
    for analysis in ("primary", "sensitivity_d0"):
        indices = [i for i, row in enumerate(rows) if row["analysis"] == analysis]
        adjusted = holm([rows[i]["p_cluster_swap"] for i in indices])
        for i, value in zip(indices, adjusted):
            rows[i]["p_holm"] = value
    arrays = {f"bootstrap__{name}": values for name, values in boot.items()}
    arrays.update({f"permutation__{name}": values for name, values in null.items()})
    arrays["bootstrap_cluster_indices"] = boot_ids
    arrays["permutation_cluster_signs"] = signs
    return rows, arrays


def conclusion(family_pass):
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--production-summary", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists() or (args.output_root.exists() and any(args.output_root.iterdir())):
        raise FileExistsError("independent output exists")
    started_time = time.perf_counter()
    protocol = json.loads(args.protocol.read_text())
    production = json.loads(args.production_summary.read_text())
    checks = []

    def check(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    for key, record in protocol["inputs"].items():
        path = Path(record["path"])
        check(f"input_{key}", sha(path) == record["sha256"])
    check("protocol_identity", production["protocol_sha256"] == sha(args.protocol))
    check("production_code_identity", production["analysis_script_sha256"] == protocol["code"]["production_script_sha256"])
    check("production_pending_independent", production["status"] == "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION")
    check("fit_accounting", production["new_model_fits"] == 700 and production["reused_rk32_model_fits"] == 200 and production["evaluated_model_fits"] == 900)

    source_path = Path(protocol["inputs"]["main_csv"]["path"])
    source = pd.read_csv(source_path, usecols=["source_row", "seqId", "cds", "utr_5prime", "sequenceWithUtr", "protein_aa", "CAI", "log10_expression", "cds_sha256", "exact_cds_group"])
    records = []
    energy_delta = 0.0
    for cds_sha, group in source.groupby("cds_sha256", sort=False):
        cds = str(group["cds"].iloc[0]).upper(); utr = str(group["utr_5prime"].iloc[0]).upper()
        full = str(group["sequenceWithUtr"].iloc[0]).upper()
        assert len(cds) == 720 and len(utr) == 144 and full == utr + cds and cds[:3] == "ATG"
        assert hashlib.sha256(cds.encode()).hexdigest() == cds_sha
        seq = np.array(list(cds)); gc = (seq == "G") | (seq == "C")
        row = {
            "cds_sha256": cds_sha, "exact_cds_group": str(group["exact_cds_group"].iloc[0]),
            "first_source_row": int(group["source_row"].min()), "n_measurements": len(group),
            "CAI": float(group["CAI"].iloc[0]), "gc_cds": float(gc.mean()), "gc3_cds": float(gc[2::3].mean()),
            "target": float(group["log10_expression"].mean()),
        }
        context_map = contexts(utr, cds)
        for context in CONTEXTS:
            assert len(context_map[context]) == 42
            row[f"sequence__{context}"] = context_map[context]
        for dangles in (2, 0):
            for context in CONTEXTS:
                row[f"{context}_d{dangles}"] = vienna(context_map[context], dangles)
        records.append(row)
    analysis = pd.DataFrame(records).sort_values("first_source_row").reset_index(drop=True)
    analysis.insert(0, "group_id", [f"g{i:03d}" for i in range(len(analysis))])
    check("raw_cohort", len(source) == 154 and len(analysis) == 150 and int((analysis["n_measurements"] > 1).sum()) == 4)

    coverage = json.loads(Path(protocol["inputs"]["coverage_report"]["path"]).read_text())
    facts = pd.read_csv(coverage["facts_csv"])
    check("cluster_facts_hash", sha(coverage["facts_csv"]) == coverage["facts_sha256"])
    analysis = analysis.merge(facts[["cds_sha256", "sequence_cluster_id"]], on="cds_sha256", how="left", validate="one_to_one")
    analysis["sequence_cluster_id"] = analysis["sequence_cluster_id"].astype(int)
    check("frozen_cluster_count", analysis["sequence_cluster_id"].nunique() == 37)

    production_analysis = pd.read_csv(args.production_root / "analysis_start_context_150.csv")
    aligned = analysis.merge(production_analysis, on=["group_id", "cds_sha256"], suffixes=("_ind", "_prod"), validate="one_to_one")
    check("analysis_row_identity", len(aligned) == 150)
    for column in ["CAI", "gc_cds", "gc3_cds", "target"] + ARMS:
        delta = float(np.max(np.abs(aligned[f"{column}_ind"].to_numpy(float) - aligned[f"{column}_prod"].to_numpy(float))))
        energy_delta = max(energy_delta, delta)
        check(f"analysis_{column}", delta <= 1e-12, delta)
    check("context_sequence_identity", all((aligned[f"sequence__{context}_ind"] == aligned[f"sequence__{context}_prod"]).all() for context in CONTEXTS))

    seeds = protocol["outer_evaluation"]["seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    all_predictions, all_assignments, training = [], [], []
    for seed in seeds:
        folds, loads = cluster_folds(analysis["sequence_cluster_id"].to_numpy(int), seed)
        if seed == primary_seed:
            check("primary_fold_loads", loads == coverage["selected_coverage"]["primary_seed_fold_sizes"], loads)
        assignment = analysis[["group_id", "cds_sha256", "sequence_cluster_id"]].copy()
        assignment.insert(0, "seed", seed); assignment["fold"] = folds
        all_assignments.append(assignment)
        prediction = analysis[["group_id", "cds_sha256", "sequence_cluster_id", "target"]].copy()
        prediction.insert(0, "seed", seed); prediction["fold"] = folds; prediction["null"] = np.nan
        for model in MODELS:
            for arm in ["simple"] + ARMS:
                prediction[f"{model}_{arm}"] = np.nan
        for fold in range(5):
            train = analysis[folds != fold]; test = analysis[folds == fold]
            check(f"leakage_{seed}_{fold}", set(train["sequence_cluster_id"]).isdisjoint(test["sequence_cluster_id"]))
            positions = prediction.index[folds == fold]
            prediction.loc[positions, "null"] = float(train["target"].mean())
            for model in MODELS:
                for arm in ["simple"] + ARMS:
                    prediction.loc[positions, f"{model}_{arm}"] = predict(model, protocol["simple_features"] + ([] if arm == "simple" else [arm]), train, test, int(seed + fold))
            training.append({"seed": seed, "fold": fold, "n_train": len(train), "n_test": len(test), "model_fits": 18})
        all_predictions.append(prediction)
    independent_predictions = pd.concat(all_predictions, ignore_index=True)
    independent_assignments = pd.concat(all_assignments, ignore_index=True)
    check("independent_fit_count", sum(row["model_fits"] for row in training) == 900)

    production_predictions = pd.read_csv(args.production_root / "oof_predictions.csv")
    production_folds = pd.read_csv(args.production_root / "fold_assignments.csv")
    check("prediction_row_identity", len(production_predictions) == len(independent_predictions) == 1500 and production_predictions[["seed", "group_id", "cds_sha256"]].equals(independent_predictions[["seed", "group_id", "cds_sha256"]]))
    check("fold_byte_content_identity", production_folds.equals(independent_assignments))
    prediction_deltas = {}
    for model in MODELS:
        for arm in ["simple"] + ARMS:
            column = f"{model}_{arm}"
            delta = float(np.max(np.abs(production_predictions[column].to_numpy(float) - independent_predictions[column].to_numpy(float))))
            prediction_deltas[column] = delta
            check(f"prediction_{column}", delta <= 1e-10, delta)
    reused = pd.read_csv(protocol["inputs"]["rk32_oof_predictions"]["path"])
    for model in MODELS:
        for production_column, reused_column in ((f"{model}_simple", f"{model}_simple"), (f"{model}_exact_real_d2", f"{model}_vienna_local")):
            delta = float(np.max(np.abs(production_predictions[production_column].to_numpy(float) - reused[reused_column].to_numpy(float))))
            check(f"accepted_reuse_{production_column}", delta <= 1e-12, delta)

    metric_rows, effect_rows, effects_by_seed = [], [], {}
    for seed in seeds:
        metrics, effects = seed_statistics(independent_predictions, seed)
        metric_rows.extend(metrics); effects_by_seed[seed] = effects
        effect_rows.extend({"seed": seed, "test": name, "effect": value} for name, value in effects.items())
    independent_metrics = pd.DataFrame(metric_rows); independent_effects = pd.DataFrame(effect_rows)
    production_metrics = read_seed_metrics(args.production_root / "seed_metrics.csv")
    production_effects = pd.read_csv(args.production_root / "seed_effects.csv")
    metric_delta = float(np.max(np.abs(independent_metrics[["spearman", "mse"]].to_numpy(float) - production_metrics[["spearman", "mse"]].to_numpy(float))))
    effect_delta = float(np.max(np.abs(independent_effects["effect"].to_numpy(float) - production_effects["effect"].to_numpy(float))))
    check("seed_metric_identity", independent_metrics[["seed", "arm"]].equals(production_metrics[["seed", "arm"]]) and metric_delta <= 1e-9, metric_delta)
    check("seed_effect_identity", independent_effects[["seed", "test"]].equals(production_effects[["seed", "test"]]) and effect_delta <= 1e-9, effect_delta)

    settings = protocol["primary_inference"]
    independent_tests, independent_arrays = inference(independent_predictions[independent_predictions["seed"] == primary_seed], int(settings["resamples"]), int(settings["bootstrap_seed"]), int(settings["permutation_seed"]))
    production_arrays = np.load(args.production_root / "primary_inference_arrays.npz")
    check("bootstrap_draw_identity", np.array_equal(independent_arrays["bootstrap_cluster_indices"], production_arrays["bootstrap_cluster_indices"]))
    check("permutation_draw_identity", np.array_equal(independent_arrays["permutation_cluster_signs"], production_arrays["permutation_cluster_signs"]))
    array_delta = 0.0
    for name in TEST_ORDER:
        for prefix in ("bootstrap", "permutation"):
            key = f"{prefix}__{name}"
            array_delta = max(array_delta, float(np.max(np.abs(independent_arrays[key] - production_arrays[key]))))
    check("inference_array_identity", array_delta <= 1e-8, array_delta)

    production_test_map = {row["test"]: row for row in production["primary_tests"]}
    check("test_order", [row["test"] for row in independent_tests] == list(production_test_map) == TEST_ORDER)
    observed_delta = ci_delta = 0.0
    for row in independent_tests:
        seed_values = np.array([effects_by_seed[seed][row["test"]] for seed in seeds])
        row.update({"seed_effects": seed_values.tolist(), "positive_seeds": int(np.sum(seed_values > 0)),
                    "mean_seed_effect": float(seed_values.mean()), "median_seed_effect": float(np.median(seed_values))})
        row["pass"] = bool(row["observed_effect"] > 0 and row["ci95"][0] > 0 and row["p_holm"] < 0.05 and row["positive_seeds"] >= 8)
        other = production_test_map[row["test"]]
        observed_delta = max(observed_delta, abs(row["observed_effect"] - other["observed_effect"]))
        ci_delta = max(ci_delta, float(np.max(np.abs(np.array(row["ci95"]) - np.array(other["ci95"])))))
        same = (
            abs(row["observed_effect"] - other["observed_effect"]) <= 1e-9
            and np.allclose(row["ci95"], other["ci95"], rtol=0, atol=1e-9)
            and row["p_cluster_swap"] == other["p_cluster_swap"] and row["p_holm"] == other["p_holm"]
            and row["positive_seeds"] == other["positive_seeds"] and row["pass"] == other["pass"]
            and np.allclose(row["seed_effects"], other["seed_effects"], rtol=0, atol=1e-9)
        )
        check(f"endpoint_{row['test']}", same, {"observed_delta": abs(row["observed_effect"] - other["observed_effect"]),
              "p_independent": row["p_cluster_swap"], "p_production": other["p_cluster_swap"],
              "pass_independent": row["pass"], "pass_production": other["pass"]})
    check("aggregate_observed_delta", observed_delta <= 1e-9, observed_delta)
    check("aggregate_ci_delta", ci_delta <= 1e-9, ci_delta)

    families = []
    for analysis_name in ("primary", "sensitivity_d0"):
        for family in FAMILIES:
            selected = [row for row in independent_tests if row["analysis"] == analysis_name and row["family"] == family]
            families.append({"analysis": analysis_name, "family": family, "n_tests": len(selected),
                             "n_pass": sum(row["pass"] for row in selected), "all_four_pass": all(row["pass"] for row in selected),
                             "confirmatory": analysis_name == "primary"})
    check("family_gate_identity", families == production["family_results"], {"independent": families, "production": production["family_results"]})
    primary_pass = {row["family"]: row["all_four_pass"] for row in families if row["analysis"] == "primary"}
    independent_conclusion = conclusion(primary_pass)
    check("scientific_conclusion_identity", independent_conclusion == production["scientific_conclusion"], independent_conclusion)
    check("confirmatory_counts", production["n_confirmatory_tests"] == 20 and production["n_confirmatory_pass"] == sum(row["analysis"] == "primary" and row["pass"] for row in independent_tests))
    check("scientific_boundaries", production["scientific_flags"]["functional_untouched_read"] is False and production["scientific_flags"]["independent_untouched_confirmation"] is False and production["scientific_flags"]["RK_G1_complete"] is False)

    args.output_root.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "oof_predictions.csv": independent_predictions, "fold_assignments.csv": independent_assignments,
        "training_log.csv": pd.DataFrame(training), "seed_metrics.csv": independent_metrics, "seed_effects.csv": independent_effects,
    }
    output_records = {}
    for name, frame in output_paths.items():
        path = args.output_root / name; frame.to_csv(path, index=False)
        output_records[name] = {"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size}
    arrays_path = args.output_root / "primary_inference_arrays.npz"
    np.savez_compressed(arrays_path, **independent_arrays)
    output_records[arrays_path.name] = {"path": str(arrays_path), "sha256": sha(arrays_path), "bytes": arrays_path.stat().st_size}
    tests_path = args.output_root / "independent_primary_tests.json"
    tests_path.write_text(json.dumps(independent_tests, indent=2, sort_keys=True) + "\n")
    output_records[tests_path.name] = {"path": str(tests_path), "sha256": sha(tests_path), "bytes": tests_path.stat().st_size}
    payload = {
        "schema": "a8-rk34-independent-verification-v2", "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
        "verification_revision": "v2_canonicalize_null_baseline_arm_after_csv_roundtrip",
        "seed_metric_numeric_tolerance": 1e-9,
        "seed_metric_identifier_normalization": "Empty CSV arm is the null baseline; scientific tolerances and endpoints are unchanged.",
        "started_utc": datetime.fromtimestamp(time.time() - (time.perf_counter() - started_time), timezone.utc).isoformat(),
        "completed_utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": float(time.perf_counter() - started_time),
        "protocol_sha256": sha(args.protocol), "production_summary_sha256": sha(args.production_summary),
        "independent_model_fits": 900, "scientific_conclusion": independent_conclusion,
        "max_deltas": {"analysis": energy_delta, "prediction": max(prediction_deltas.values()),
                       "seed_metric": metric_delta, "seed_effect": effect_delta, "inference_arrays": array_delta,
                       "observed_effect": observed_delta, "ci": ci_delta},
        "prediction_deltas": prediction_deltas, "checks": checks,
        "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks),
        "outputs": output_records, "functional_untouched_read": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": payload["status"], "checks_passed": payload["checks_passed"], "checks_total": len(checks),
                      "scientific_conclusion": independent_conclusion, "max_deltas": payload["max_deltas"],
                      "elapsed_seconds": payload["elapsed_seconds"], "failed_checks": [row for row in checks if not row["pass"]]}, indent=2))
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
