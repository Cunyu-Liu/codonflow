#!/usr/bin/env python3
"""Independently reproduce RK22 groups, models and randomization inference."""
from __future__ import annotations
import argparse, hashlib, itertools, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rankcorr(x, y):
    xr, yr = stats.rankdata(x), stats.rankdata(y)
    xr, yr = xr - xr.mean(), yr - yr.mean()
    return float(xr @ yr / math.sqrt((xr @ xr) * (yr @ yr)))


def resid(v, z):
    return v - z @ np.linalg.lstsq(z, v, rcond=None)[0]


def beta(x, y, z):
    xr, yr = resid(x, z), resid(y, z)
    return float(xr @ yr / (xr @ xr))


def holm(p):
    order = np.argsort(p)
    out = np.empty(len(p))
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        out[index] = min(1.0, running)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--repo-root", default="/home/codonflow-a8-rk")
    args = ap.parse_args()
    protocol_path = Path(args.protocol).resolve()
    summary_path = Path(args.summary).resolve()
    protocol = json.loads(protocol_path.read_text())
    summary = json.loads(summary_path.read_text())
    root = Path(protocol["output_root"])
    checks = []
    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})
        if not condition:
            raise RuntimeError(f"{name}: {detail}")
    def close(a, b, tol=1e-10):
        return bool(np.allclose(a, b, rtol=tol, atol=tol, equal_nan=False))
    check("protocol_schema", protocol["schema"] == "a8-rk22-fixed-protein-mechanism-protocol-v1")
    check("protocol_frozen", protocol["frozen_before_any_association_or_model_fit"] is True)
    check("summary_pending", summary["status"] == "PASS_ANALYSIS_PENDING_INDEPENDENT_VERIFICATION")
    check("protocol_hash", summary["protocol_sha256"] == sha(protocol_path))
    check("analysis_script_hash", summary["analysis_script_sha256"] == sha(Path(args.repo_root) / "scripts" / "a8_rk22_run_fixed_protein.py"))
    for item in protocol["inputs"].values():
        check("input_hash_" + Path(item["path"]).name, sha(Path(item["path"])) == item["sha256"])
    for name, item in summary["outputs"].items():
        check("output_hash_" + name, sha(root / name) == item["sha256"])
        check("output_bytes_" + name, (root / name).stat().st_size == item["bytes"])

    raw = pd.read_csv(protocol["inputs"]["main_csv"]["path"], dtype={"seqId": str})
    tag = pd.read_csv(protocol["inputs"]["tagged_csv"]["path"], dtype={"seqId": str})
    raw["gc_cds"] = raw.cds.map(lambda s: (s.count("G") + s.count("C")) / len(s))
    raw["gc3_cds"] = raw.cds.map(lambda s: sum(v in "GC" for v in s[2::3]) / (len(s) / 3))
    check("raw_rows", len(raw) == 154 and len(tag) == 72)
    check("within_group_features_constant", all(g[c].nunique(dropna=False) == 1 for _, g in raw.groupby("exact_cds_group") for c in ["CAI", "gc_cds", "gc3_cds", "mfe_5prime_kcal_mol", "cds"]))
    expected_main = raw.groupby("exact_cds_group", sort=False).agg(
        seqIds=("seqId", lambda x: ";".join(x)), n_measurements=("seqId", "size"), CAI=("CAI", "first"),
        gc_cds=("gc_cds", "first"), gc3_cds=("gc3_cds", "first"), mfe_5prime_kcal_mol=("mfe_5prime_kcal_mol", "first"),
        target=("log10_expression", "mean"), first_source_row=("source_row", "min")).reset_index().sort_values("first_source_row").reset_index(drop=True)
    saved_main = pd.read_csv(root / "main_exact_cds_150.csv")
    check("main_group_count", len(expected_main) == len(saved_main) == 150)
    check("main_group_measurements", int(saved_main.n_measurements.sum()) == 154)
    pd.testing.assert_frame_equal(saved_main, expected_main, check_exact=False, rtol=1e-12, atol=1e-12)
    check("main_group_table_exact", True)

    joined = tag.merge(raw[["seqId", "exact_cds_group", "CAI", "gc_cds", "gc3_cds", "mfe_5prime_kcal_mol", "log10_expression"]], on="seqId", validate="one_to_one", suffixes=("_tagged", "_main"))
    joined["delta_mfe5"] = joined["rnaEnergy_-4..37"] - joined.mfe_5prime_kcal_mol
    joined["delta_log10_expression"] = joined.log10_expression_tagged - joined.log10_expression_main
    expected_tag = joined.groupby("main_cds_group", sort=False).agg(
        seqIds=("seqId", lambda x: ";".join(x)), n_measurements=("seqId", "size"), delta_mfe5=("delta_mfe5", "mean"),
        delta_log10_expression=("delta_log10_expression", "mean"), CAI=("CAI", "first"), gc_cds=("gc_cds", "first"), gc3_cds=("gc3_cds", "first")).reset_index()
    saved_tag = pd.read_csv(root / "tagged_exact_cds_71.csv")
    check("tag_group_count", len(expected_tag) == len(saved_tag) == 71)
    check("tag_group_measurements", int(saved_tag.n_measurements.sum()) == 72)
    pd.testing.assert_frame_equal(saved_tag, expected_tag, check_exact=False, rtol=1e-12, atol=1e-12)
    check("tag_group_table_exact", True)

    seeds = protocol["main_analysis"]["seeds"]
    simple = protocol["main_analysis"]["simple_features"]
    structure = protocol["main_analysis"]["structure_features"]
    params = protocol["main_analysis"]["models"]["histgb"]["parameters"]
    Xs, Xt, y = expected_main[simple].to_numpy(float), expected_main[structure].to_numpy(float), expected_main.target.to_numpy(float)
    expected_predictions, expected_folds = [], []
    for seed in seeds:
        kfold = KFold(n_splits=5, shuffle=True, random_state=seed)
        pred = {(m, f): np.empty(150) for m in ["ridge", "histgb"] for f in ["simple", "structure"]}
        pred[("null", "null")] = np.empty(150)
        fold_ids = np.empty(150, dtype=int)
        for fold, (train, test) in enumerate(kfold.split(y), 1):
            fold_ids[test] = fold
            for model in ["ridge", "histgb"]:
                for feature_set, X in (("simple", Xs), ("structure", Xt)):
                    estimator = make_pipeline(StandardScaler(), Ridge(alpha=1.0)) if model == "ridge" else HistGradientBoostingRegressor(random_state=seed, **params)
                    estimator.fit(X[train], y[train])
                    pred[(model, feature_set)][test] = estimator.predict(X[test])
            pred[("null", "null")][test] = y[train].mean()
        for i, group in enumerate(expected_main.exact_cds_group):
            expected_folds.append({"seed": seed, "exact_cds_group": group, "fold": fold_ids[i]})
            for (model, feature_set), values in pred.items():
                expected_predictions.append({"seed": seed, "exact_cds_group": group, "fold": fold_ids[i], "target": y[i], "model": model, "feature_set": feature_set, "prediction": values[i]})
    expected_predictions = pd.DataFrame(expected_predictions)
    expected_folds = pd.DataFrame(expected_folds)
    saved_predictions = pd.read_csv(root / "main_oof_predictions.csv", keep_default_na=False)
    saved_folds = pd.read_csv(root / "main_fold_assignments.csv", keep_default_na=False)
    check("prediction_rows", len(saved_predictions) == len(expected_predictions) == 7500)
    pd.testing.assert_frame_equal(saved_folds, expected_folds, check_exact=True)
    check("fold_assignments_exact", True)
    pd.testing.assert_frame_equal(saved_predictions, expected_predictions, check_exact=False, rtol=1e-10, atol=1e-10)
    check("all_oof_predictions_refit_exact", True)
    check("no_group_crosses_fold", all(len(set(saved_folds[saved_folds.seed == seed].exact_cds_group)) == 150 for seed in seeds))

    metric_rows = []
    for (seed, model, feature_set), frame in expected_predictions.groupby(["seed", "model", "feature_set"], sort=False):
        metric_rows.append({"seed": seed, "model": model, "feature_set": feature_set, "spearman": rankcorr(frame.target, frame.prediction), "mse": float(np.mean((frame.target - frame.prediction) ** 2))})
    expected_metrics = pd.DataFrame(metric_rows)
    saved_metrics = pd.read_csv(root / "main_seed_metrics.csv", keep_default_na=False)
    pd.testing.assert_frame_equal(saved_metrics, expected_metrics, check_exact=False, rtol=1e-10, atol=1e-10)
    check("seed_metrics_recomputed", True)
    effect_rows = []
    for model in ["ridge", "histgb"]:
        for seed in seeds:
            a = expected_metrics[(expected_metrics.seed == seed) & (expected_metrics.model == model) & (expected_metrics.feature_set == "simple")].iloc[0]
            b = expected_metrics[(expected_metrics.seed == seed) & (expected_metrics.model == model) & (expected_metrics.feature_set == "structure")].iloc[0]
            effect_rows.append({"model": model, "seed": seed, "spearman_effect": b.spearman - a.spearman, "mse_improvement": a.mse - b.mse})
    expected_effects = pd.DataFrame(effect_rows)
    saved_effects = pd.read_csv(root / "main_seed_effects.csv")
    pd.testing.assert_frame_equal(saved_effects, expected_effects, check_exact=False, rtol=1e-10, atol=1e-10)
    check("seed_effects_recomputed", True)

    recomputed_primary = []
    for model in ["ridge", "histgb"]:
        for endpoint in ["spearman_effect", "mse_improvement"]:
            values = expected_effects.loc[expected_effects.model == model, endpoint].to_numpy(float)
            patterns = np.asarray(list(itertools.product([-1.0, 1.0], repeat=10)))
            null = patterns @ values / 10
            rng = np.random.default_rng(20261201)
            boot = rng.choice(values, size=(20000, 10), replace=True).mean(axis=1)
            recomputed_primary.append({"test": f"{model}_{endpoint}", "mean": values.mean(), "median": np.median(values), "positive": int((values > 0).sum()), "ci": np.quantile(boot, [.025, .975]), "p": np.mean(np.abs(null) >= abs(values.mean()) - 1e-15)})
    p_adj = holm([x["p"] for x in recomputed_primary])
    for i, (actual, expected) in enumerate(zip(summary["main"]["primary_tests"], recomputed_primary)):
        check("primary_name_" + str(i), actual["test"] == expected["test"])
        check("primary_values_" + expected["test"], close([actual["mean_effect"], actual["median_effect"], actual["positive_seeds"], *actual["ci95"], actual["p_signflip_exact"]], [expected["mean"], expected["median"], expected["positive"], *expected["ci"], expected["p"]]))
        actual_pass = expected["mean"] > 0 and expected["positive"] >= 8 and expected["ci"][0] > 0 and p_adj[i] < .05
        check("primary_decision_" + expected["test"], actual["pass"] == actual_pass and close(actual["p_holm"], p_adj[i]))
    main_pass = all(x["mean"] > 0 and x["positive"] >= 8 and x["ci"][0] > 0 and p_adj[i] < .05 for i, x in enumerate(recomputed_primary))
    check("main_gate_recomputed", summary["main"]["development_structure_increment_pass"] == main_pass)

    x, yt = expected_tag.delta_mfe5.to_numpy(float), expected_tag.delta_log10_expression.to_numpy(float)
    z = np.column_stack([np.ones(71), expected_tag[["CAI", "gc_cds", "gc3_cds"]].to_numpy(float)])
    observed_s, observed_b = rankcorr(x, yt), beta(x, yt, z)
    xr, yr = stats.rankdata(x), stats.rankdata(yt)
    xc, yc = xr - xr.mean(), yr - yr.mean()
    denominator = math.sqrt((xc @ xc) * (yc @ yc))
    rng = np.random.default_rng(20261202)
    null_s_parts = []
    for _ in range(100):
        perm = np.argsort(rng.random((1000, 71)), axis=1)
        xp = xr[perm]
        xp -= xp.mean(axis=1, keepdims=True)
        null_s_parts.append((xp @ yc) / denominator)
    null_s = np.concatenate(null_s_parts)
    rng = np.random.default_rng(20261203)
    perm = np.argsort(rng.random((20000, 71)), axis=1)
    projection = z @ np.linalg.pinv(z)
    xp = x[perm]
    xp = xp - xp @ projection
    null_b = (xp @ resid(yt, z)) / np.sum(xp * xp, axis=1)
    rng = np.random.default_rng(20261204)
    boot_s, boot_b = np.empty(20000), np.empty(20000)
    for i in range(20000):
        take = rng.integers(0, 71, 71)
        boot_s[i] = rankcorr(x[take], yt[take])
        boot_b[i] = beta(x[take], yt[take], z[take])
    arrays = np.load(root / "tagged_randomization_arrays.npz")
    for name, expected in (("null_spearman", null_s), ("null_beta", null_b), ("boot_spearman", boot_s), ("boot_beta", boot_b)):
        check("randomization_array_" + name, np.array_equal(arrays[name], expected))
    p_s = (1 + np.sum(np.abs(null_s) >= abs(observed_s) - 1e-15)) / 100001
    p_b = (1 + np.sum(np.abs(null_b) >= abs(observed_b) - 1e-15)) / 20001
    expected_tag_results = [
        {"test": "paired_spearman", "estimate": observed_s, "ci": np.quantile(boot_s, [.025, .975]), "p": p_s},
        {"test": "adjusted_delta_mfe5_coefficient", "estimate": observed_b, "ci": np.quantile(boot_b, [.025, .975]), "p": p_b},
    ]
    tag_p_adj = holm([p_s, p_b])
    for i, (actual, expected) in enumerate(zip(summary["tagged"]["tests"], expected_tag_results)):
        check("tag_name_" + str(i), actual["test"] == expected["test"])
        check("tag_values_" + expected["test"], close([actual["estimate"], *actual["ci95"], actual["p_permutation"]], [expected["estimate"], *expected["ci"], expected["p"]]))
        expected_pass = expected["estimate"] > 0 and expected["ci"][0] > 0 and tag_p_adj[i] < .05
        check("tag_decision_" + expected["test"], actual["pass"] == expected_pass and close(actual["p_holm"], tag_p_adj[i]))
    tag_pass = all(x["estimate"] > 0 and x["ci"][0] > 0 and tag_p_adj[i] < .05 for i, x in enumerate(expected_tag_results))
    check("tag_gate_recomputed", summary["tagged"]["paired_structure_expression_pass"] == tag_pass)
    check("combined_development_decision", summary["development_structure_support"] == (main_pass and tag_pass))
    flags = summary["scientific_flags"]
    check("scientific_scope_flags", flags["fixed_protein_development_analysis"] is True and all(flags[k] is False for k in flags if k != "fixed_protein_development_analysis"))
    check("no_delta_cai_or_gc", protocol["scientific_scope"]["delta_CAI_or_delta_GC_used"] is False)
    check("no_tagged_sequence_imputation", flags["tagged_sequence_imputed"] is False)

    report = {
        "schema": "a8-rk22-fixed-protein-independent-v1", "status": "PASS_INDEPENDENT_VERIFICATION",
        "checks_passed": len(checks), "checks_total": len(checks), "checks": checks,
        "protocol_sha256": sha(protocol_path), "analysis_summary_sha256": sha(summary_path), "verification_script_sha256": sha(Path(__file__).resolve()),
        "main_development_structure_increment_pass": main_pass, "tagged_paired_structure_expression_pass": tag_pass,
        "development_structure_support": main_pass and tag_pass,
        "protein_ood_evaluated": False, "functional_ood_evaluated": False, "functional_untouched_evaluated": False,
        "rk_g1_pass": False, "expensive_generation_authorized": False, "sota_claimed": False,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "checks_passed": len(checks), "main_pass": main_pass, "tagged_pass": tag_pass}, indent=2))

if __name__ == "__main__":
    main()
