#!/usr/bin/env python3
"""Independent raw-source verifier for MAGE development nested-CV v2.

No production module is imported. All records, folds, ridge fits, predictions,
metrics, intervals, permutations and gates are independently reconstructed.
"""
from __future__ import annotations

import os
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import csv
import hashlib
import json
import math
import subprocess
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

MODELS = ["intrinsic", "local_mfe", "rcs_only", "full_mechanism"]
REFERENCES = ["intrinsic", "local_mfe"]
CATS = ["position", "wt_codon", "mutant_codon", "amino_acid"]
I_NUM = ["position_scaled", "wt_gc_fraction", "mutant_gc_fraction", "delta_gc_fraction", "wt_gc3", "mutant_gc3", "nt_changes", "is_transition"]
M_NUM = ["mfe_ddG_43nt_sliding", "delta_mfe_vs_wt", "abs_delta_mfe_vs_wt", "mfe_x_position_scaled"]
R_NUM = ["RCS", "delta_rcs_vs_wt", "abs_delta_rcs_vs_wt", "rcs_x_position_scaled"]
AA = {}
for codons, aa in [
    (["TTT", "TTC"], "F"), (["TTA", "TTG", "CTT", "CTC", "CTA", "CTG"], "L"),
    (["ATT", "ATC", "ATA"], "I"), (["ATG"], "M"), (["GTT", "GTC", "GTA", "GTG"], "V"),
    (["TCT", "TCC", "TCA", "TCG", "AGT", "AGC"], "S"), (["CCT", "CCC", "CCA", "CCG"], "P"),
    (["ACT", "ACC", "ACA", "ACG"], "T"), (["GCT", "GCC", "GCA", "GCG"], "A"),
    (["TAT", "TAC"], "Y"), (["TAA", "TAG", "TGA"], "*"), (["CAT", "CAC"], "H"),
    (["CAA", "CAG"], "Q"), (["AAT", "AAC"], "N"), (["AAA", "AAG"], "K"),
    (["GAT", "GAC"], "D"), (["GAA", "GAG"], "E"), (["TGT", "TGC"], "C"),
    (["TGG"], "W"), (["CGT", "CGC", "CGA", "CGG", "AGA", "AGG"], "R"),
    (["GGT", "GGC", "GGA", "GGG"], "G")]:
    for codon in codons:
        AA[codon] = aa


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def finite(x):
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def nums(model):
    return {"intrinsic": I_NUM, "local_mfe": I_NUM + M_NUM, "rcs_only": I_NUM + R_NUM, "full_mechanism": I_NUM + M_NUM + R_NUM}[model]


def gc(c):
    return (c.count("G") + c.count("C")) / 3.0


def features(row, wt_row):
    wt, mut, pos = row["wt_codon"], row["mutant_codon"], int(row["codon_position"])
    f, w = json.loads(row["features_json"]), json.loads(wt_row["features_json"])
    rcs, mfe = float(f["RCS"]), float(f["mfe_ddG_43nt_sliding"])
    dr = rcs - float(w["RCS"])
    dm = mfe - float(w["mfe_ddG_43nt_sliding"])
    ps = pos / 71.0
    transitions = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}
    changes = [(a, b) for a, b in zip(wt, mut) if a != b]
    return {
        "position": str(pos), "wt_codon": wt, "mutant_codon": mut, "amino_acid": row["amino_acid"],
        "position_scaled": ps, "wt_gc_fraction": gc(wt), "mutant_gc_fraction": gc(mut),
        "delta_gc_fraction": gc(mut) - gc(wt), "wt_gc3": float(wt[2] in "GC"),
        "mutant_gc3": float(mut[2] in "GC"), "nt_changes": float(sum(a != b for a, b in zip(wt, mut))),
        "is_transition": float(len(changes) == 1 and tuple(changes[0]) in transitions),
        "mfe_ddG_43nt_sliding": mfe, "delta_mfe_vs_wt": dm, "abs_delta_mfe_vs_wt": abs(dm),
        "mfe_x_position_scaled": mfe * ps, "RCS": rcs, "delta_rcs_vs_wt": dr,
        "abs_delta_rcs_vs_wt": abs(dr), "rcs_x_position_scaled": rcs * ps,
    }


def raw_development(cfg):
    with open(cfg["source"]["csv"], newline="") as handle:
        rows = list(csv.DictReader(handle))
    wt = {}
    media = {"relative_fitness_rich": {}, "relative_fitness_minimal": {}}
    for row in rows:
        if row["record_class"] == "wild_type_control" and row["expression_type"] == "relative_fitness_rich":
            wt[int(row["codon_position"])] = row
        elif row["record_class"] == "single_codon_variant" and row["expression_type"] in media:
            media[row["expression_type"]][row["construct_id"]] = row

    def eligible(row):
        p = int(row["codon_position"])
        w = wt.get(p)
        if w is None or row["wt_codon"] in {"TAA", "TAG", "TGA"} or row["mutant_codon"] in {"TAA", "TAG", "TGA"}:
            return False
        if row["wt_codon"] == row["mutant_codon"] or row["amino_acid"] == "*":
            return False
        if AA[row["wt_codon"]] != AA[row["mutant_codon"]] or AA[row["mutant_codon"]] != row["amino_acid"]:
            return False
        if not finite(row["expression_value"]) or not finite(row["expression_stdev"]):
            return False
        f, wf = json.loads(row["features_json"]), json.loads(w["features_json"])
        return all(finite(f.get(k)) and finite(wf.get(k)) for k in ("RCS", "mfe_ddG_43nt_sliding"))

    common = set(media["relative_fitness_rich"]) & set(media["relative_fitness_minimal"])
    eligible_ids = sorted(c for c in common if eligible(media["relative_fitness_rich"][c]) and eligible(media["relative_fitness_minimal"][c]))
    primary = [c for c in eligible_ids if 10 <= int(media["relative_fitness_rich"][c]["codon_position"]) <= 71]
    ordered = sorted(primary, key=lambda c: hashlib.sha256(("20261119:" + c).encode()).hexdigest())
    nd = round(len(ordered) * 0.2)
    nt = round(len(ordered) * 0.2)
    split = {c: "dev" if i < nd else "test" if i < nd + nt else "train" for i, c in enumerate(ordered)}
    records = []
    for c in primary:
        if split[c] == "test":
            continue
        row = dict(media["relative_fitness_rich"][c])
        row.update(features(row, wt[int(row["codon_position"])]))
        row["split"] = split[c]
        records.append(row)
    records.sort(key=lambda r: r["construct_id"])
    return records, split, {"source_rows": len(rows), "common": len(common), "eligible": len(eligible_ids), "primary": len(primary)}


def fold_map(ids, k, salt):
    ordered = sorted(ids, key=lambda c: (hashlib.sha256(f"{salt}:{c}".encode()).hexdigest(), c))
    return {c: i % k for i, c in enumerate(ordered)}


def design(records, model):
    columns = CATS + nums(model)
    X = pd.DataFrame([{c: r[c] for c in columns} for r in records], columns=columns)
    for c in nums(model):
        X[c] = X[c].astype(np.float64)
    for c in CATS:
        X[c] = X[c].astype(str)
    y = np.array([float(r["expression_value"]) for r in records], dtype=np.float64)
    return X, y


def predict(train, evaluation, model, alpha):
    transformer = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=True), CATS),
        ("numeric", StandardScaler(with_mean=False), nums(model)),
    ])
    pipeline = Pipeline([("features", transformer), ("ridge", Ridge(alpha=alpha, fit_intercept=True, solver="lsqr", tol=1e-12, max_iter=100000))])
    X, y = design(train, model)
    pipeline.fit(X, y)
    Xe, _ = design(evaluation, model)
    return np.array(pipeline.predict(Xe), dtype=np.float64)


def nested(records, model, alphas, seed):
    ids = [r["construct_id"] for r in records]
    by_id = {r["construct_id"]: r for r in records}
    outer = fold_map(ids, 5, seed)
    oof = {}
    selected = []
    for fold in range(5):
        train_ids = [c for c in ids if outer[c] != fold]
        eval_ids = [c for c in ids if outer[c] == fold]
        inner = fold_map(train_ids, 4, f"{seed}:inner")
        inner_oof = {a: {} for a in alphas}
        for f in range(4):
            tr = [by_id[c] for c in train_ids if inner[c] != f]
            ev = [by_id[c] for c in train_ids if inner[c] == f]
            for a in alphas:
                p = predict(tr, ev, model, a)
                inner_oof[a].update({r["construct_id"]: float(v) for r, v in zip(ev, p)})
        trials = []
        y = np.array([float(by_id[c]["expression_value"]) for c in train_ids])
        for a in alphas:
            p = np.array([inner_oof[a][c] for c in train_ids])
            trials.append({"alpha": a, "inner_oof_rmse": float(np.sqrt(np.mean((y - p) ** 2)))})
        best = sorted(trials, key=lambda t: (t["inner_oof_rmse"], -t["alpha"], str(t["alpha"])))[0]
        p = predict([by_id[c] for c in train_ids], [by_id[c] for c in eval_ids], model, best["alpha"])
        oof.update({c: float(v) for c, v in zip(eval_ids, p)})
        selected.append({"outer_fold": fold, "n_outer_train": len(train_ids), "n_outer_eval": len(eval_ids), "selected_alpha": best["alpha"], "inner_alpha_grid": trials})
    return oof, outer, selected


def met(y, p):
    return {"n": len(y), "rmse": float(np.sqrt(np.mean((y - p) ** 2))), "mae": float(np.mean(np.abs(y - p))), "spearman": float(spearmanr(y, p).statistic), "mean_y": float(np.mean(y)), "mean_prediction": float(np.mean(p))}


def eff(y, c, r):
    a, b = met(y, c), met(y, r)
    return {"delta_spearman": a["spearman"] - b["spearman"], "delta_rmse": a["rmse"] - b["rmse"]}


def inference(y, c, r, bs, ps, reps):
    obs = eff(y, c, r)
    n = len(y)
    boot = np.empty((reps, 2))
    rng = np.random.default_rng(bs)
    for b in range(reps):
        idx = rng.integers(0, n, n)
        v = eff(y[idx], c[idx], r[idx])
        boot[b] = [v["delta_spearman"], v["delta_rmse"]]
    rng = np.random.default_rng(ps)
    perm = np.empty((reps, 2))
    for b in range(reps):
        swap = rng.random(n) < 0.5
        v = eff(y, np.where(swap, r, c), np.where(swap, c, r))
        perm[b] = [v["delta_spearman"], v["delta_rmse"]]
    point = np.array([obs["delta_spearman"], obs["delta_rmse"]])
    p = (1 + np.sum(np.abs(perm) >= np.abs(point)[None, :], axis=0)) / (reps + 1.0)
    return {**obs, "delta_spearman_ci95": [float(x) for x in np.percentile(boot[:, 0], [2.5, 97.5])], "delta_rmse_ci95": [float(x) for x in np.percentile(boot[:, 1], [2.5, 97.5])], "permutation_p_spearman": float(p[0]), "permutation_p_rmse": float(p[1]), "bootstrap_replicates": reps, "permutation_replicates": reps}


def holm(values):
    p = np.array(values)
    order = np.argsort(p)
    out = np.empty(len(p))
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (len(p) - rank) * p[idx])
        out[idx] = min(1.0, running)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--production-script", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    cfg = json.loads(Path(args.config).read_text())
    report = json.loads(Path(args.report).read_text())
    checks = []
    deltas = {"prediction": 0.0, "metric": 0.0, "inference": 0.0, "inner_rmse": 0.0}

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    def near(a, b, tol=1e-9):
        return abs(float(a) - float(b)) <= tol

    for key, path_key in [("csv_sha256", "csv"), ("codon_module_sha256", "codon_module"), ("v1_protocol_sha256", "v1_protocol"), ("v1_report_sha256", "v1_report"), ("v1_split_assignments_sha256", "v1_split_assignments")]:
        check(f"source_hash_{path_key}", digest(cfg["source"][path_key]) == cfg["source"][key])
    check("protocol_hash", digest(args.config) == report["protocol_sha256"])
    production_sha = digest(args.production_script)
    check("production_script_nonempty", len(production_sha) == 64)
    v1 = json.loads(Path(cfg["source"]["v1_report"]).read_text())
    check("v1_no_go_retained", v1["status"] == "DEV_NO_GO_TEST_UNTOUCHED" and v1["primary_test"] is None and not v1["mechanism_increment_pass"])
    records, split, counts = raw_development(cfg)
    ids = [r["construct_id"] for r in records]
    check("raw_counts", counts == {"source_rows": 9344, "common": 4599, "eligible": 179, "primary": 164}, counts)
    check("development_counts", len(records) == 131 and Counter(r["split"] for r in records) == Counter({"train": 98, "dev": 33}))
    check("test_excluded_from_records", not any(split[c] == "test" for c in ids) and sum(v == "test" for v in split.values()) == 33)
    with open(cfg["source"]["v1_split_assignments"], newline="") as handle:
        saved_split = {r["construct_id"]: r["split"] for r in csv.DictReader(handle)}
    check("v1_split_exact", saved_split == split)
    artifact_root = Path(cfg["artifacts"]["large_artifact_root"])
    pred_path = artifact_root / "development_oof_predictions.csv"
    fold_path = artifact_root / "development_fold_assignments.csv"
    check("prediction_artifact_hash", digest(pred_path) == report["artifact_files"][pred_path.name]["sha256"])
    check("fold_artifact_hash", digest(fold_path) == report["artifact_files"][fold_path.name]["sha256"])
    with open(pred_path, newline="") as handle:
        prediction_rows = list(csv.DictReader(handle))
    check("prediction_ids_exact", [r["construct_id"] for r in prediction_rows] == ids and len(prediction_rows) == 131)
    check("prediction_has_no_test", all(r["construct_id"] in ids for r in prediction_rows))
    with open(fold_path, newline="") as handle:
        fold_rows = list(csv.DictReader(handle))
    check("fold_rows_complete", len(fold_rows) == 131 * 3 and all(r["construct_id"] in ids for r in fold_rows))
    check("prediction_split_position_outcome", all(r["original_split"] == rec["split"] and r["position"] == rec["position"] and near(r["observed_rich"], rec["expression_value"], 0) for r, rec in zip(prediction_rows, records)))

    seeds = [cfg["nested_cv"]["primary_outer_seed"]] + cfg["nested_cv"]["sensitivity_outer_seeds"]
    alphas = cfg["features_and_models"]["alpha_grid"]
    runs = {}
    for seed in seeds:
        runs[seed] = {}
        for model in MODELS:
            oof, outer, selected = nested(records, model, alphas, seed)
            runs[seed][model] = {"oof": oof, "outer": outer, "selected": selected}
            check(f"outer_folds_{seed}_{model}", outer == runs[seed]["intrinsic"]["outer"] if model != "intrinsic" else len(outer) == 131)
            expected_selected = report["nested_cv_selection"][seed][model]
            check(f"alpha_selection_{seed}_{model}", [s["selected_alpha"] for s in selected] == [s["selected_alpha"] for s in expected_selected])
            inner_delta = max(abs(a["inner_oof_rmse"] - b["inner_oof_rmse"]) for sa, sb in zip(selected, expected_selected) for a, b in zip(sa["inner_alpha_grid"], sb["inner_alpha_grid"]))
            deltas["inner_rmse"] = max(deltas["inner_rmse"], inner_delta)
            check(f"inner_rmse_{seed}_{model}", inner_delta <= 1e-9, inner_delta)
            pdelta = max(abs(oof[r["construct_id"]] - float(r[f"pred_{seed}_{model}"])) for r in prediction_rows)
            deltas["prediction"] = max(deltas["prediction"], pdelta)
            check(f"predictions_{seed}_{model}", pdelta <= 1e-9, pdelta)
    check("fold_artifact_exact", all(int(fr["outer_fold"]) == runs[fr["seed"]]["intrinsic"]["outer"][fr["construct_id"]] for fr in fold_rows))

    y = np.array([float(r["expression_value"]) for r in records])
    primary = seeds[0]
    primary_preds = {model: np.array([runs[primary][model]["oof"][c] for c in ids]) for model in MODELS}
    for model in MODELS:
        recomputed = met(y, primary_preds[model])
        expected = report["primary_models"][model]
        delta = max(abs(recomputed[k] - expected[k]) for k in ("rmse", "mae", "spearman", "mean_y", "mean_prediction"))
        deltas["metric"] = max(deltas["metric"], delta)
        check(f"primary_metrics_{model}", delta <= 1e-10, delta)
    raw_p = []
    recomputed_comparisons = {}
    for i, reference in enumerate(REFERENCES):
        name = f"full_mechanism_minus_{reference}"
        result = inference(y, primary_preds["full_mechanism"], primary_preds[reference], cfg["primary_comparisons"]["bootstrap"]["seed"] + i, cfg["primary_comparisons"]["paired_permutation"]["seed"] + i, 20000)
        recomputed_comparisons[name] = result
        expected = report["primary_comparisons"][name]
        keys = ["delta_spearman", "delta_rmse", "permutation_p_spearman", "permutation_p_rmse"]
        delta = max(abs(result[k] - expected[k]) for k in keys)
        delta = max(delta, max(abs(a - b) for k in ("delta_spearman_ci95", "delta_rmse_ci95") for a, b in zip(result[k], expected[k])))
        deltas["inference"] = max(deltas["inference"], delta)
        check(f"primary_inference_{reference}", delta <= 1e-10, delta)
        raw_p.extend([result["permutation_p_spearman"], result["permutation_p_rmse"]])
    adjusted = holm(raw_p)
    for i, reference in enumerate(REFERENCES):
        expected = report["primary_comparisons"][f"full_mechanism_minus_{reference}"]
        check(f"holm_{reference}", near(adjusted[2 * i], expected["holm_p_spearman"], 1e-12) and near(adjusted[2 * i + 1], expected["holm_p_rmse"], 1e-12))

    sensitivity_ok = True
    for seed in seeds[1:]:
        predictions = {model: np.array([runs[seed][model]["oof"][c] for c in ids]) for model in MODELS}
        for model in MODELS:
            recomputed = met(y, predictions[model])
            expected = report["sensitivity"][seed]["models"][model]
            delta = max(abs(recomputed[k] - expected[k]) for k in ("rmse", "mae", "spearman", "mean_y", "mean_prediction"))
            deltas["metric"] = max(deltas["metric"], delta)
            check(f"sensitivity_metrics_{seed}_{model}", delta <= 1e-10, delta)
        for reference in REFERENCES:
            name = f"full_mechanism_minus_{reference}"
            values = eff(y, predictions["full_mechanism"], predictions[reference])
            expected = report["sensitivity"][seed]["comparisons"][name]
            delta = max(abs(values[k] - expected[k]) for k in values)
            deltas["metric"] = max(deltas["metric"], delta)
            check(f"sensitivity_effect_{seed}_{reference}", delta <= 1e-10, delta)
            sensitivity_ok &= values["delta_spearman"] > 0 and values["delta_rmse"] < 0
    primary_ok = all(r["delta_spearman_ci95"][0] > 0 and r["delta_rmse_ci95"][1] < 0 and r["holm_p_spearman"] < 0.05 and r["holm_p_rmse"] < 0.05 for r in report["primary_comparisons"].values())
    go = bool(primary_ok and sensitivity_ok)
    check("primary_gate_recomputed", primary_ok == report["primary_development_ok"])
    check("sensitivity_gate_recomputed", bool(sensitivity_ok) == report["sensitivity_signs_ok"])
    check("development_gate_recomputed", go == report["development_go"])
    expected_status = "DEV_GO_PENDING_INDEPENDENT_VERIFICATION_TEST_STILL_UNTOUCHED" if go else "DEV_NO_GO_TEST_UNTOUCHED"
    check("status_recomputed", report["status"] == expected_status)
    check("test_readout_absent", not report["test_predictions_generated"] and not report["test_metrics_generated"] and not report["mechanism_increment_pass"] and not report["generator_training_authorized"])
    check("original_gate_not_modified", not report["test_authorized_by_v1"] and not report["original_v1_gate_modified"])
    check("all_numeric_deltas_within_tolerance", max(deltas.values()) <= 1e-9, deltas)
    test_log = Path(args.report).with_name("mage_development_nested_cv_unit_tests.console.log")
    initial_log = Path(args.report).with_name("mage_development_nested_cv_unit_tests_initial_failure.console.log")
    check("unit_tests_12_pass", test_log.exists() and "Ran 12 tests" in test_log.read_text() and "OK" in test_log.read_text())
    check("initial_failure_preserved", initial_log.exists() and "FileNotFoundError" in initial_log.read_text())
    git_head = subprocess.check_output(["git", "-C", "/home/codonflow-a8-rk", "rev-parse", "HEAD"], text=True).strip()
    result = {
        "schema": "a8-rk03-mage-development-nested-cv-independent-v2",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "checks_passed": sum(c["pass"] for c in checks),
        "checks_total": len(checks),
        "checks": checks,
        "protocol_sha256": digest(args.config),
        "production_report_sha256": digest(args.report),
        "production_script_sha256": production_sha,
        "git_head_at_verification": git_head,
        "development_go_recomputed": go,
        "primary_development_ok_recomputed": bool(primary_ok),
        "sensitivity_signs_ok_recomputed": bool(sensitivity_ok),
        "test_untouched": True,
        "max_numeric_deltas": deltas,
        "recomputed_primary_comparisons": recomputed_comparisons,
        "elapsed_s": time.perf_counter() - started,
    }
    save(args.output, result)
    print(json.dumps({"status": result["status"], "checks": f"{result['checks_passed']}/{result['checks_total']}", "development_go": go, "max_numeric_deltas": deltas, "elapsed_s": result["elapsed_s"]}, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
