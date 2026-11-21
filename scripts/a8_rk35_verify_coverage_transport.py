#!/usr/bin/env python3
"""Independent RK35 verification: rebuild cohort, energies, folds, all 500 fits,
seed metrics/effects, all 24 contrast tests and resampling arrays from raw sources
without importing the production module. Compares against frozen production output.
"""
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
from sklearn.preprocessing import StandardScaler

CONTRASTS = {
    "trunc_vs_simple": ("simple", "trunc_local"),
    "exact_vs_trunc": ("trunc_local", "exact_local"),
    "exact_vs_simple": ("simple", "exact_local"),
    "atg_vs_trunc": ("trunc_local", "cds_start_local"),
    "exact_vs_atg": ("cds_start_local", "exact_local"),
    "trunc_d0_vs_simple": ("simple", "trunc_local_d0"),
}
PRIMARY = ("trunc_vs_simple", "exact_vs_trunc")
GATE = ("exact_vs_simple",)
SECONDARY = ("atg_vs_trunc", "exact_vs_atg", "trunc_d0_vs_simple")
ARM_FEATURES = {
    "simple": ["CAI", "gc_cds", "gc3_cds"],
    "exact_local": ["CAI", "gc_cds", "gc3_cds", "e_exact"],
    "cds_start_local": ["CAI", "gc_cds", "gc3_cds", "e_atg"],
    "trunc_local": ["CAI", "gc_cds", "gc3_cds", "e_trunc"],
    "trunc_local_d0": ["CAI", "gc_cds", "gc3_cds", "e_trunc_d0"],
}


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


def sp(x, y) -> float:
    a = rankdata(np.asarray(x, float))
    b = rankdata(np.asarray(y, float))
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt(np.dot(a, a) * np.dot(b, b)))
    return float(np.dot(a, b) / denom) if denom else float("nan")


def fold_clusters(cluster_labels, seed):
    uniq = sorted(set(int(c) for c in cluster_labels))
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(uniq))
    shuffled = [uniq[i] for i in order]
    size = {c: sum(1 for v in cluster_labels if int(v) == c) for c in uniq}
    shuffled.sort(key=lambda c: -size[c])
    load = [0] * 5
    where = {}
    for c in shuffled:
        best = min(load)
        tied = [i for i in range(5) if load[i] == best]
        f = int(rng.choice(np.array(tied)))
        where[c] = f
        load[f] += size[c]
    return np.array([where[int(c)] for c in cluster_labels], dtype=int), load


def mfe_value(seq: str, dangles: int) -> float:
    md = RNA.md()
    md.dangles = dangles
    md.temperature = 37.0
    val = float(RNA.fold_compound(seq.replace("T", "U"), md).mfe()[1])
    if not np.isfinite(val) or abs(val) >= 100000:
        raise ValueError("bad MFE")
    return val


def predict(model_name, feats, train_df, test_df, rng_seed):
    if model_name == "ridge":
        scaler = StandardScaler().fit(train_df[feats])
        ridge = Ridge(alpha=1.0).fit(scaler.transform(train_df[feats]), train_df["target"])
        return np.asarray(ridge.predict(scaler.transform(test_df[feats])), dtype=float)
    model = HistGradientBoostingRegressor(
        loss="squared_error", learning_rate=0.05, max_iter=200, max_leaf_nodes=7,
        min_samples_leaf=10, l2_regularization=1.0, early_stopping=False, random_state=rng_seed,
    )
    model.fit(train_df[feats], train_df["target"])
    return np.asarray(model.predict(test_df[feats]), dtype=float)


def holm_adjust(pvals):
    p = np.asarray(pvals, float)
    idx = np.argsort(p)
    out = np.empty(len(p))
    run = 0.0
    for rank, i in enumerate(idx):
        run = max(run, (len(p) - rank) * p[i])
        out[i] = min(1.0, run)
    return out.tolist()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--production-root", type=Path, required=True)
    ap.add_argument("--production-summary", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    wall = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat()
    protocol = json.loads(args.protocol.read_text())
    production = json.loads(args.production_summary.read_text())
    checks: list[dict] = []

    def check(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    inputs = protocol["inputs"]
    for key, entry in inputs.items():
        check(f"input_sha_{key}", sha256(Path(entry["path"])) == entry["sha256"])
    check("production_script_sha", production["analysis_script_sha256"] == protocol["code"]["production_script_sha256"])
    check("production_protocol_sha", production["protocol_sha256"] == sha256(args.protocol))

    raw = pd.read_csv(inputs["main_csv"]["path"])
    check("raw_rows_154", len(raw) == 154)
    records = []
    for sha, grp in raw.groupby("cds_sha256", sort=False):
        cds = str(grp["cds"].iloc[0]).upper()
        utr = str(grp["utr_5prime"].iloc[0]).upper()
        full = str(grp["sequenceWithUtr"].iloc[0]).upper()
        assert len(cds) == 720 and len(utr) == 144 and full == utr + cds
        assert hashlib.sha256(cds.encode()).hexdigest() == sha
        assert grp["cds"].nunique() == 1 and grp["exact_cds_group"].nunique() == 1
        chars = np.array(list(cds))
        records.append({
            "cds_sha256": sha,
            "exact_cds_group": str(grp["exact_cds_group"].iloc[0]),
            "first_source_row": int(grp["source_row"].min()),
            "CAI": float(grp["CAI"].iloc[0]),
            "gc_cds": float(np.mean(np.isin(chars, ["G", "C"]))),
            "gc3_cds": float(np.mean(np.isin(chars[2::3], ["G", "C"]))),
            "target": float(grp["log10_expression"].mean()),
            "e_exact": mfe_value(utr[-4:] + cds[:38], 2),
            "e_atg": mfe_value(cds[:42], 2),
            "e_trunc": mfe_value(cds[3:45], 2),
            "e_trunc_d0": mfe_value(cds[3:45], 0),
        })
    frame = pd.DataFrame(records).sort_values("first_source_row").reset_index(drop=True)
    frame.insert(0, "group_id", [f"g{i:03d}" for i in range(len(frame))])
    check("groups_150", len(frame) == 150)

    coverage = json.loads(Path(inputs["rk27_coverage_report"]["path"]).read_text())
    facts = pd.read_csv(coverage["facts_csv"])
    check("facts_sha", sha256(Path(coverage["facts_csv"])) == coverage["facts_sha256"])
    frame = frame.merge(facts[["cds_sha256", "sequence_cluster_id"]], on="cds_sha256", how="left", validate="one_to_one")
    frame["sequence_cluster_id"] = frame["sequence_cluster_id"].astype(int)
    check("clusters_37", frame["sequence_cluster_id"].nunique() == 37)

    prod_analysis = pd.read_csv(args.production_root / "analysis_start_aware_150.csv")
    aligned = frame.merge(prod_analysis, on="cds_sha256", suffixes=("_ind", "_prod"), validate="one_to_one")
    check("analysis_rows_align", len(aligned) == 150)
    feature_pairs = [("CAI_ind", "CAI_prod"), ("gc_cds_ind", "gc_cds_prod"), ("gc3_cds_ind", "gc3_cds_prod"), ("target_ind", "target_prod"), ("e_exact", "vienna_exact_local_mfe"), ("e_atg", "vienna_cds_start_mfe"), ("e_trunc", "vienna_trunc_mfe"), ("e_trunc_d0", "vienna_trunc_d0_mfe")]
    feature_delta = max(float(np.max(np.abs(aligned[a].to_numpy(float) - aligned[b].to_numpy(float)))) for a, b in feature_pairs)
    check("raw_feature_recomputation", feature_delta <= 1e-8, feature_delta)
    check("group_id_order", (aligned["group_id_ind"] == aligned["group_id_prod"]).all())
    check("cluster_ids_match", (aligned["sequence_cluster_id_ind"] == aligned["sequence_cluster_id_prod"]).all())

    seeds = protocol["outer_evaluation"]["seeds"]
    primary_seed = protocol["outer_evaluation"]["primary_seed"]
    labels = frame["sequence_cluster_id"].to_numpy(int)
    prod_folds = pd.read_csv(args.production_root / "fold_assignments.csv")
    prod_oof = pd.read_csv(args.production_root / "oof_predictions.csv")
    ind_predictions = []
    fold_match = True
    leakage_free = True
    fit_count = 0
    for seed in seeds:
        folds, loads = fold_clusters(labels, seed)
        if seed == primary_seed:
            check("primary_fold_sizes", loads == coverage["selected_coverage"]["primary_seed_fold_sizes"], loads)
        pf = prod_folds[prod_folds["seed"] == seed].set_index("cds_sha256")["fold"]
        for sha, f in zip(frame["cds_sha256"], folds):
            if int(pf[sha]) != int(f):
                fold_match = False
        po = prod_oof[prod_oof["seed"] == seed].set_index("cds_sha256")
        block = frame.copy()
        block["seed"] = seed
        block["fold"] = folds
        block["null"] = np.nan
        for m in ("ridge", "histgb"):
            for arm in ARM_FEATURES:
                block[f"{m}_{arm}"] = np.nan
        for fold in range(5):
            train = frame[folds != fold]
            test = frame[folds == fold]
            if not set(train["sequence_cluster_id"]).isdisjoint(set(test["sequence_cluster_id"])):
                leakage_free = False
            mean_target = float(train["target"].mean())
            idx = block.index[folds == fold]
            block.loc[idx, "null"] = mean_target
            for m in ("ridge", "histgb"):
                for arm, feats in ARM_FEATURES.items():
                    block.loc[idx, f"{m}_{arm}"] = predict(m, feats, train, test, int(seed + fold))
                    fit_count += 1
            for sha, f in zip(test["cds_sha256"], [fold] * len(test)):
                if int(po.loc[sha, "fold"]) != f:
                    fold_match = False
        ind_predictions.append(block)
    check("folds_match_production", fold_match)
    check("no_cluster_leakage", leakage_free)
    check("independent_500_fits", fit_count == 500, fit_count)
    ind_oof = pd.concat(ind_predictions, ignore_index=True)

    value_cols = [c for c in ind_oof if c == "null" or c.startswith("ridge_") or c.startswith("histgb_")]
    merged_oof = ind_oof.merge(prod_oof, on=["seed", "cds_sha256"], suffixes=("_ind", "_prod"), validate="one_to_one")
    check("oof_rows_1500", len(merged_oof) == 1500)
    prediction_delta = max(float(np.max(np.abs(merged_oof[f"{c}_ind"].to_numpy(float) - merged_oof[f"{c}_prod"].to_numpy(float)))) for c in value_cols)
    check("independent_500_fit_predictions", prediction_delta <= 1e-10, prediction_delta)
    reused_cols = ["ridge_simple", "histgb_simple", "ridge_exact_local", "histgb_exact_local"]
    reused_delta = max(float(np.max(np.abs(merged_oof[f"{c}_ind"].to_numpy(float) - merged_oof[f"{c}_prod"].to_numpy(float)))) for c in reused_cols)
    check("reused_arms_independently_refit", reused_delta <= 1e-10, reused_delta)

    prod_metrics = pd.read_csv(args.production_root / "seed_metrics.csv")
    prod_effects = pd.read_csv(args.production_root / "seed_effects.csv")
    metric_rows, effect_rows = [], []
    for seed in seeds:
        cur = ind_oof[ind_oof["seed"] == seed]
        y = cur["target"].to_numpy(float)
        for c in value_cols:
            p = cur[c].to_numpy(float)
            metric_rows.append({"seed": seed, "arm": c, "spearman": sp(y, p), "mse": float(np.mean((y - p) ** 2))})
        for m in ("ridge", "histgb"):
            for contrast, (a, b) in CONTRASTS.items():
                pa = cur[f"{m}_{a}"].to_numpy(float)
                pb = cur[f"{m}_{b}"].to_numpy(float)
                effect_rows.append({"seed": seed, "test": f"{m}__{contrast}__spearman_effect", "effect": sp(y, pb) - sp(y, pa)})
                effect_rows.append({"seed": seed, "test": f"{m}__{contrast}__mse_improvement", "effect": float(np.mean((y - pa) ** 2 - (y - pb) ** 2))})
    ind_metrics = pd.DataFrame(metric_rows)
    ind_effects = pd.DataFrame(effect_rows)
    mm = ind_metrics.merge(prod_metrics, on=["seed", "arm"], suffixes=("_ind", "_prod"), validate="one_to_one")
    metric_delta = max(float(np.max(np.abs(mm[f"{k}_ind"] - mm[f"{k}_prod"]))) for k in ("spearman", "mse"))
    check("seed_metric_recomputation", len(mm) == len(prod_metrics) and metric_delta <= 1e-12, metric_delta)
    me = ind_effects.merge(prod_effects, on=["seed", "test"], suffixes=("_ind", "_prod"), validate="one_to_one")
    effect_delta = float(np.max(np.abs(me["effect_ind"] - me["effect_prod"])))
    check("seed_effect_recomputation", len(me) == 240 and effect_delta <= 1e-12, {"rows": len(me), "max_abs_delta": effect_delta})

    primary = ind_oof[ind_oof["seed"] == primary_seed].reset_index(drop=True)
    y = primary["target"].to_numpy(float)
    cids = primary["sequence_cluster_id"].to_numpy(int)
    uniq = np.array(sorted(np.unique(cids)), dtype=int)
    cindex = np.searchsorted(uniq, cids)
    crows = [np.flatnonzero(cindex == i) for i in range(len(uniq))]
    inf = protocol["primary_inference"]
    B = int(inf["resamples"])
    boot_c = np.random.default_rng(inf["bootstrap_seed"]).integers(0, len(uniq), size=(B, len(uniq)), dtype=np.int16)
    perm_s = np.random.default_rng(inf["permutation_seed"]).choice(np.array([-1, 1], dtype=np.int8), size=(B, len(uniq)))
    names = [f"{m}__{c}__{metric}" for m in ("ridge", "histgb") for c in CONTRASTS for metric in ("spearman_effect", "mse_improvement")]
    obs = {n: 0.0 for n in names}
    boot = {n: np.empty(B) for n in names}
    null = {n: np.empty(B) for n in names}
    pairs = {}
    for m in ("ridge", "histgb"):
        for c, (a, b) in CONTRASTS.items():
            pa = primary[f"{m}_{a}"].to_numpy(float)
            pb = primary[f"{m}_{b}"].to_numpy(float)
            sn = f"{m}__{c}__spearman_effect"
            mn = f"{m}__{c}__mse_improvement"
            obs[sn] = sp(y, pb) - sp(y, pa)
            diff = (y - pa) ** 2 - (y - pb) ** 2
            obs[mn] = float(diff.mean())
            null[mn] = (perm_s[:, cindex] * diff).mean(axis=1)
            pairs[(m, c)] = (pa, pb, diff)
    for b in range(B):
        sel = boot_c[b]
        ridx = np.concatenate([crows[int(c)] for c in sel])
        w = np.bincount(sel, minlength=len(uniq))[cindex].astype(float)
        swap = perm_s[b, cindex] < 0
        for m in ("ridge", "histgb"):
            for c in CONTRASTS:
                pa, pb, diff = pairs[(m, c)]
                sn = f"{m}__{c}__spearman_effect"
                mn = f"{m}__{c}__mse_improvement"
                boot[sn][b] = sp(y[ridx], pb[ridx]) - sp(y[ridx], pa[ridx])
                boot[mn][b] = float(np.dot(w, diff) / w.sum())
                sa = np.where(swap, pb, pa)
                sb = np.where(swap, pa, pb)
                null[sn][b] = sp(y, sb) - sp(y, sa)

    prod_arrays = np.load(args.production_root / "primary_inference_arrays.npz")
    check("bootstrap_indices_exact", np.array_equal(boot_c, prod_arrays["bootstrap_cluster_indices"]))
    check("permutation_signs_exact", np.array_equal(perm_s, prod_arrays["permutation_cluster_signs"]))
    array_delta = 0.0
    array_count = 0
    for n in names:
        contrast = n.split("__")[1]
        prefix = "primary" if contrast in PRIMARY else ("gate" if contrast in GATE else "secondary")
        for kind, values in (("bootstrap", boot), ("permutation", null)):
            key = f"{prefix}_{kind}__{n}"
            d = float(np.max(np.abs(values[n] - prod_arrays[key])))
            array_delta = max(array_delta, d)
            array_count += 1
    check("independent_inference_arrays", array_count == 48 and array_delta <= 1e-12, {"arrays": array_count, "max_abs_delta": array_delta})

    def build_tests(contrast_subset):
        sub_names = [f"{m}__{c}__{metric}" for m in ("ridge", "histgb") for c in contrast_subset for metric in ("spearman_effect", "mse_improvement")]
        rows = []
        for n in sub_names:
            o = float(obs[n])
            rows.append({
                "test": n, "observed_effect": o,
                "ci95": [float(np.quantile(boot[n], 0.025)), float(np.quantile(boot[n], 0.975))],
                "p_cluster_swap": float((1 + np.sum(np.abs(null[n]) >= abs(o))) / (B + 1)),
            })
        adj = holm_adjust([r["p_cluster_swap"] for r in rows])
        for r, ph in zip(rows, adj):
            eff = ind_effects[ind_effects["test"] == r["test"]].sort_values("seed")["effect"].to_numpy(float)
            r["p_holm"] = ph
            r["positive_seeds"] = int(np.sum(eff > 0))
            r["pass"] = bool(r["observed_effect"] > 0 and r["ci95"][0] > 0 and ph < 0.05 and r["positive_seeds"] >= 8)
        return rows

    ind_primary = build_tests(PRIMARY)
    ind_gate = build_tests(GATE)
    ind_secondary = build_tests(SECONDARY)
    check("primary_family_8", len(ind_primary) == 8)
    check("secondary_family_12", len(ind_secondary) == 12)
    prod_primary = {r["test"]: r for r in production["primary_tests"]}
    summary_delta = 0.0
    pass_mismatch = 0
    for r in ind_primary:
        p = prod_primary[r["test"]]
        for k in ("observed_effect", "p_cluster_swap", "p_holm"):
            summary_delta = max(summary_delta, abs(r[k] - p[k]))
        summary_delta = max(summary_delta, abs(r["ci95"][0] - p["ci95"][0]), abs(r["ci95"][1] - p["ci95"][1]))
        pass_mismatch += int(r["pass"] != p["pass"])
    check("primary_summary_recomputation", summary_delta <= 1e-12 and pass_mismatch == 0, {"max_abs_delta": summary_delta, "pass_mismatches": pass_mismatch})

    rk32_result = json.loads(Path(inputs["rk32_result_v2"]["path"]).read_text())
    rk32_tests = {r["test"]: r for r in rk32_result["primary_tests"]}
    gate_ok = True
    gate_max_delta = 0.0
    for r in ind_gate:
        m, _, metric = r["test"].split("__")
        ref = rk32_tests[f"{m}__vienna_local__{metric}"]
        d = max(abs(r["observed_effect"] - ref["observed_effect"]), abs(r["ci95"][0] - ref["ci95"][0]), abs(r["ci95"][1] - ref["ci95"][1]), abs(r["p_cluster_swap"] - ref["p_cluster_swap"]))
        gate_max_delta = max(gate_max_delta, d)
        gate_ok = gate_ok and d <= 1e-12 and r["pass"]
    check("consistency_gate_independent", gate_ok and gate_max_delta <= 1e-12, gate_max_delta)
    check("production_gate_agrees", bool(production["consistency_gate"]["pass"]) == bool(gate_ok))

    contrast_results = {}
    for c in PRIMARY:
        rows = [r for r in ind_primary if r["test"].split("__")[1] == c]
        contrast_results[c] = all(r["pass"] for r in rows)
    if not gate_ok:
        conclusion = "CONSISTENCY_GATE_FAILED_NOT_EVALUATED"
    elif contrast_results["trunc_vs_simple"]:
        conclusion = "RK33_COVERAGE_RETAINS_INCREMENT_WITHIN_KUDLA_RETROSPECTIVELY"
    elif contrast_results["exact_vs_trunc"]:
        conclusion = "START_AWARE_COVERAGE_NECESSARY_WITHIN_KUDLA_RETROSPECTIVELY"
    else:
        conclusion = "COVERAGE_TRANSPORT_NOT_DISCRIMINATED_RETROSPECTIVELY"
    check("scientific_conclusion_match", conclusion == production["scientific_conclusion"], {"independent": conclusion, "production": production["scientific_conclusion"]})
    check("fit_accounting", production["new_model_fits"] == 300 and production["reused_model_fits"] == 200 and production["evaluated_model_fits"] == 500)
    tl = pd.read_csv(args.production_root / "training_log.csv")
    check("training_log_new_fits_only", int(tl["new_model_fits"].sum()) == 300 and int(tl["reused_model_fits"].sum()) == 200 and len(tl) == 50)

    report = {
        "schema": "a8-rk35-coverage-transport-independent-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "component_wall_seconds": float(time.perf_counter() - wall),
        "independent_model_fits": fit_count,
        "max_feature_abs_delta": feature_delta, "max_prediction_abs_delta": prediction_delta,
        "max_seed_metric_abs_delta": metric_delta, "max_seed_effect_abs_delta": effect_delta,
        "max_inference_abs_delta": array_delta, "max_primary_summary_abs_delta": summary_delta,
        "consistency_gate_max_delta": gate_max_delta,
        "independent_conclusion": conclusion,
        "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "checks": checks,
    }
    atomic_json(args.report, report)
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if report["status"] != "PASS":
        print(json.dumps([c for c in checks if not c["pass"]], indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()