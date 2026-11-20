#!/usr/bin/env python3
"""Run the frozen RK22 fixed-protein structure-expression analyses."""
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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False)
    tmp.replace(path)


def holm(pvalues: list[float]) -> list[float]:
    order = np.argsort(pvalues)
    adjusted = np.empty(len(pvalues), dtype=float)
    running = 0.0
    m = len(pvalues)
    for rank, index in enumerate(order):
        running = max(running, (m - rank) * pvalues[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def make_model(name: str, seed: int, parameters: dict):
    if name == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    if name == "histgb":
        return HistGradientBoostingRegressor(random_state=seed, **parameters)
    raise ValueError(name)


def signflip_inference(effects: np.ndarray, bootstrap_seed: int, bootstrap_n: int) -> dict:
    effects = np.asarray(effects, dtype=float)
    n = len(effects)
    patterns = np.asarray(list(itertools.product([-1.0, 1.0], repeat=n)))
    observed = float(effects.mean())
    null = patterns @ effects / n
    p = float(np.mean(np.abs(null) >= abs(observed) - 1e-15))
    rng = np.random.default_rng(bootstrap_seed)
    boot = rng.choice(effects, size=(bootstrap_n, n), replace=True).mean(axis=1)
    return {
        "n_seeds": n,
        "effects": effects.tolist(),
        "mean_effect": observed,
        "median_effect": float(np.median(effects)),
        "positive_seeds": int(np.sum(effects > 0)),
        "ci95": [float(x) for x in np.quantile(boot, [0.025, 0.975])],
        "p_signflip_exact": p,
        "signflip_patterns": int(len(patterns)),
    }


def residualize(values: np.ndarray, covariates: np.ndarray) -> np.ndarray:
    return values - covariates @ np.linalg.lstsq(covariates, values, rcond=None)[0]


def adjusted_coefficient(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> float:
    xr = residualize(np.asarray(x, dtype=float), z)
    yr = residualize(np.asarray(y, dtype=float), z)
    return float(xr @ yr / (xr @ xr))


def rank_correlation(x: np.ndarray, y: np.ndarray) -> float:
    xr = stats.rankdata(x)
    yr = stats.rankdata(y)
    xr = xr - xr.mean()
    yr = yr - yr.mean()
    return float(xr @ yr / math.sqrt((xr @ xr) * (yr @ yr)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--repo-root", default="/home/codonflow-a8-rk")
    args = parser.parse_args()
    repo = Path(args.repo_root)
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol["schema"] != "a8-rk22-fixed-protein-mechanism-protocol-v1" or not protocol["frozen_before_any_association_or_model_fit"]:
        raise ValueError("RK22 protocol is not frozen")
    output = Path(protocol["output_root"])
    output.mkdir(parents=True, exist_ok=True)
    audit = repo / protocol["audit_root"]
    audit.mkdir(parents=True, exist_ok=True)
    for item in protocol["inputs"].values():
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError("Input hash mismatch")

    main_raw = pd.read_csv(protocol["inputs"]["main_csv"]["path"], dtype={"seqId": str})
    tagged_raw = pd.read_csv(protocol["inputs"]["tagged_csv"]["path"], dtype={"seqId": str})
    if len(main_raw) != 154 or len(tagged_raw) != 72:
        raise ValueError("Recovered table row counts changed")
    main_raw["gc_cds"] = main_raw["cds"].map(lambda s: (s.count("G") + s.count("C")) / len(s))
    main_raw["gc3_cds"] = main_raw["cds"].map(lambda s: sum(base in "GC" for base in s[2::3]) / (len(s) / 3))
    feature_columns = ["CAI", "gc_cds", "gc3_cds", "mfe_5prime_kcal_mol"]
    for _, group in main_raw.groupby("exact_cds_group", sort=False):
        if any(group[column].nunique(dropna=False) != 1 for column in feature_columns + ["cds"]):
            raise ValueError("Feature mismatch inside exact-CDS group")
    main_groups = main_raw.groupby("exact_cds_group", sort=False).agg(
        seqIds=("seqId", lambda values: ";".join(values)),
        n_measurements=("seqId", "size"),
        CAI=("CAI", "first"),
        gc_cds=("gc_cds", "first"),
        gc3_cds=("gc3_cds", "first"),
        mfe_5prime_kcal_mol=("mfe_5prime_kcal_mol", "first"),
        target=("log10_expression", "mean"),
        first_source_row=("source_row", "min"),
    ).reset_index().sort_values("first_source_row").reset_index(drop=True)
    if len(main_groups) != 150 or int(main_groups["n_measurements"].sum()) != 154:
        raise ValueError("Main exact-CDS aggregation mismatch")

    join_columns = ["seqId", "exact_cds_group", "CAI", "gc_cds", "gc3_cds", "mfe_5prime_kcal_mol", "log10_expression"]
    tagged = tagged_raw.merge(main_raw[join_columns], on="seqId", how="left", validate="one_to_one", suffixes=("_tagged", "_main"))
    if tagged["exact_cds_group"].isna().any() or not (tagged["main_cds_group"] == tagged["exact_cds_group"]).all():
        raise ValueError("Tagged/main join mismatch")
    tagged["delta_mfe5"] = tagged["rnaEnergy_-4..37"] - tagged["mfe_5prime_kcal_mol"]
    tagged["delta_log10_expression"] = tagged["log10_expression_tagged"] - tagged["log10_expression_main"]
    tagged_groups = tagged.groupby("main_cds_group", sort=False).agg(
        seqIds=("seqId", lambda values: ";".join(values)),
        n_measurements=("seqId", "size"),
        delta_mfe5=("delta_mfe5", "mean"),
        delta_log10_expression=("delta_log10_expression", "mean"),
        CAI=("CAI", "first"),
        gc_cds=("gc_cds", "first"),
        gc3_cds=("gc3_cds", "first"),
    ).reset_index()
    if len(tagged_groups) != 71 or int(tagged_groups["n_measurements"].sum()) != 72:
        raise ValueError("Tagged exact-CDS aggregation mismatch")
    atomic_csv(output / "main_exact_cds_150.csv", main_groups)
    atomic_csv(output / "tagged_exact_cds_71.csv", tagged_groups)

    seeds = protocol["main_analysis"]["seeds"]
    simple = protocol["main_analysis"]["simple_features"]
    structure = protocol["main_analysis"]["structure_features"]
    model_parameters = protocol["main_analysis"]["models"]["histgb"]["parameters"]
    fold_rows, prediction_rows, metric_rows = [], [], []
    X_simple = main_groups[simple].to_numpy(float)
    X_structure = main_groups[structure].to_numpy(float)
    y = main_groups["target"].to_numpy(float)
    groups = main_groups["exact_cds_group"].tolist()
    for seed in seeds:
        splitter = KFold(n_splits=5, shuffle=True, random_state=seed)
        fold_for_row = np.empty(len(y), dtype=int)
        predictions = {(model, feature_set): np.empty(len(y), dtype=float) for model in ["ridge", "histgb"] for feature_set in ["simple", "structure"]}
        predictions[("null", "null")] = np.empty(len(y), dtype=float)
        for fold, (train, test) in enumerate(splitter.split(y), start=1):
            fold_for_row[test] = fold
            for model in ["ridge", "histgb"]:
                for feature_set, X in (("simple", X_simple), ("structure", X_structure)):
                    estimator = make_model(model, seed, model_parameters)
                    estimator.fit(X[train], y[train])
                    predictions[(model, feature_set)][test] = estimator.predict(X[test])
            predictions[("null", "null")][test] = float(y[train].mean())
        for row_index, group in enumerate(groups):
            fold_rows.append({"seed": seed, "exact_cds_group": group, "fold": int(fold_for_row[row_index])})
            for (model, feature_set), values in predictions.items():
                prediction_rows.append({"seed": seed, "exact_cds_group": group, "fold": int(fold_for_row[row_index]), "target": y[row_index], "model": model, "feature_set": feature_set, "prediction": values[row_index]})
        for (model, feature_set), values in predictions.items():
            metric_rows.append({"seed": seed, "model": model, "feature_set": feature_set, "spearman": rank_correlation(y, values), "mse": float(np.mean((y - values) ** 2))})
    folds = pd.DataFrame(fold_rows)
    predictions = pd.DataFrame(prediction_rows)
    metrics = pd.DataFrame(metric_rows)
    atomic_csv(output / "main_fold_assignments.csv", folds)
    atomic_csv(output / "main_oof_predictions.csv", predictions)
    atomic_csv(output / "main_seed_metrics.csv", metrics)

    effect_rows = []
    for model in ["ridge", "histgb"]:
        for seed in seeds:
            simple_row = metrics[(metrics.seed == seed) & (metrics.model == model) & (metrics.feature_set == "simple")].iloc[0]
            structure_row = metrics[(metrics.seed == seed) & (metrics.model == model) & (metrics.feature_set == "structure")].iloc[0]
            effect_rows.append({"model": model, "seed": seed, "spearman_effect": float(structure_row.spearman - simple_row.spearman), "mse_improvement": float(simple_row.mse - structure_row.mse)})
    effects = pd.DataFrame(effect_rows)
    atomic_csv(output / "main_seed_effects.csv", effects)
    primary = []
    for model in ["ridge", "histgb"]:
        for endpoint, column in (("spearman_effect", "spearman_effect"), ("mse_improvement", "mse_improvement")):
            values = effects.loc[effects.model == model, column].to_numpy(float)
            result = signflip_inference(values, 20261201, 20000)
            result.update({"test": f"{model}_{endpoint}", "model": model, "endpoint": endpoint})
            primary.append(result)
    adjusted = holm([item["p_signflip_exact"] for item in primary])
    for item, p_adj in zip(primary, adjusted):
        item["p_holm"] = p_adj
        item["pass"] = bool(item["mean_effect"] > 0 and item["positive_seeds"] >= 8 and item["ci95"][0] > 0 and p_adj < 0.05)
    main_pass = all(item["pass"] for item in primary)

    x = tagged_groups["delta_mfe5"].to_numpy(float)
    y_tag = tagged_groups["delta_log10_expression"].to_numpy(float)
    z = np.column_stack([np.ones(len(x)), tagged_groups[["CAI", "gc_cds", "gc3_cds"]].to_numpy(float)])
    observed_spearman = rank_correlation(x, y_tag)
    observed_beta = adjusted_coefficient(x, y_tag, z)
    xr = stats.rankdata(x)
    yr = stats.rankdata(y_tag)
    xr_centered = xr - xr.mean()
    yr_centered = yr - yr.mean()
    denominator = math.sqrt((xr_centered @ xr_centered) * (yr_centered @ yr_centered))
    rng_s = np.random.default_rng(20261202)
    null_spearman_parts = []
    for _ in range(100):
        permutations = np.argsort(rng_s.random((1000, len(x))), axis=1)
        xp = xr[permutations]
        xp = xp - xp.mean(axis=1, keepdims=True)
        null_spearman_parts.append((xp @ yr_centered) / denominator)
    null_spearman = np.concatenate(null_spearman_parts)
    p_spearman = (1 + int(np.sum(np.abs(null_spearman) >= abs(observed_spearman) - 1e-15))) / (len(null_spearman) + 1)
    projection = z @ np.linalg.pinv(z)
    yr_adjusted = residualize(y_tag, z)
    rng_b = np.random.default_rng(20261203)
    permutations = np.argsort(rng_b.random((20000, len(x))), axis=1)
    xp = x[permutations]
    xp = xp - xp @ projection
    null_beta = (xp @ yr_adjusted) / np.sum(xp * xp, axis=1)
    p_beta = (1 + int(np.sum(np.abs(null_beta) >= abs(observed_beta) - 1e-15))) / (len(null_beta) + 1)
    rng_boot = np.random.default_rng(20261204)
    boot_spearman = np.empty(20000, dtype=float)
    boot_beta = np.empty(20000, dtype=float)
    for index in range(20000):
        take = rng_boot.integers(0, len(x), size=len(x))
        boot_spearman[index] = rank_correlation(x[take], y_tag[take])
        boot_beta[index] = adjusted_coefficient(x[take], y_tag[take], z[take])
    np.savez_compressed(output / "tagged_randomization_arrays.npz", null_spearman=null_spearman, null_beta=null_beta, boot_spearman=boot_spearman, boot_beta=boot_beta)
    tagged_results = [
        {"test": "paired_spearman", "estimate": observed_spearman, "ci95": [float(v) for v in np.quantile(boot_spearman, [0.025, 0.975])], "p_permutation": float(p_spearman), "permutations": len(null_spearman)},
        {"test": "adjusted_delta_mfe5_coefficient", "estimate": observed_beta, "ci95": [float(v) for v in np.quantile(boot_beta, [0.025, 0.975])], "p_permutation": float(p_beta), "permutations": len(null_beta)},
    ]
    tagged_adjusted = holm([item["p_permutation"] for item in tagged_results])
    for item, p_adj in zip(tagged_results, tagged_adjusted):
        item["p_holm"] = p_adj
        item["pass"] = bool(item["estimate"] > 0 and item["ci95"][0] > 0 and p_adj < 0.05)
    tagged_pass = all(item["pass"] for item in tagged_results)

    performance = []
    for model in ["null", "ridge", "histgb"]:
        for feature_set in (["null"] if model == "null" else ["simple", "structure"]):
            subset = metrics[(metrics.model == model) & (metrics.feature_set == feature_set)]
            performance.append({"model": model, "feature_set": feature_set, "mean_spearman": float(subset.spearman.mean()), "mean_mse": float(subset.mse.mean()), "sd_spearman": float(subset.spearman.std(ddof=1)), "sd_mse": float(subset.mse.std(ddof=1))})
    artifact_paths = [
        "main_exact_cds_150.csv", "tagged_exact_cds_71.csv", "main_fold_assignments.csv",
        "main_oof_predictions.csv", "main_seed_metrics.csv", "main_seed_effects.csv", "tagged_randomization_arrays.npz",
    ]
    summary = {
        "schema": "a8-rk22-fixed-protein-mechanism-v1",
        "status": "PASS_ANALYSIS_PENDING_INDEPENDENT_VERIFICATION",
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "analysis_script_sha256": sha256(Path(__file__).resolve()),
        "main": {
            "measurement_rows": 154, "exact_cds_groups": 150, "seeds": seeds, "folds_per_seed": 5,
            "performance": performance, "primary_tests": primary, "development_structure_increment_pass": main_pass,
        },
        "tagged": {
            "measurement_rows": 72, "exact_cds_groups": 71, "tests": tagged_results,
            "paired_structure_expression_pass": tagged_pass,
            "delta_mfe5_median": float(np.median(x)), "delta_log10_expression_median": float(np.median(y_tag)),
        },
        "development_structure_support": bool(main_pass and tagged_pass),
        "outputs": {name: {"sha256": sha256(output / name), "bytes": (output / name).stat().st_size} for name in artifact_paths},
        "scientific_flags": {
            "fixed_protein_development_analysis": True,
            "protein_ood_evaluated": False,
            "functional_ood_evaluated": False,
            "functional_untouched_evaluated": False,
            "rk_g1_pass": False,
            "expensive_generation_authorized": False,
            "external_sota_authorized": False,
            "sota_claimed": False,
            "tagged_sequence_imputed": False,
        },
    }
    atomic_json(output / "rk22_analysis_summary.json", summary)
    atomic_json(audit / "rk22_analysis_summary_v1.json", summary)
    print(json.dumps({
        "status": summary["status"], "main_pass": main_pass, "tagged_pass": tagged_pass,
        "main_tests": [{k: item[k] for k in ["test", "mean_effect", "positive_seeds", "ci95", "p_holm", "pass"]} for item in primary],
        "tagged_tests": tagged_results,
    }, indent=2))


if __name__ == "__main__":
    main()
