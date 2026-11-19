#!/usr/bin/env python3
"""Frozen fixed-infA synonymous mechanism-increment experiment."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

BASE = ["intrinsic", "local_mfe", "rcs_only", "full_mechanism"]
CATS = ["position", "wt_codon", "mutant_codon", "amino_acid"]
INTRINSIC_NUM = ["position_scaled", "wt_gc_fraction", "mutant_gc_fraction", "delta_gc_fraction", "wt_gc3", "mutant_gc3", "nt_changes", "is_transition"]
MFE_NUM = ["mfe_ddG_43nt_sliding", "delta_mfe_vs_wt", "abs_delta_mfe_vs_wt", "mfe_x_position_scaled"]
RCS_NUM = ["RCS", "delta_rcs_vs_wt", "abs_delta_rcs_vs_wt", "rcs_x_position_scaled"]
TRANSITIONS = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def dump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def gc(codon):
    return (codon.count("G") + codon.count("C")) / 3.0


def nt_changes(wt, mutant):
    return sum(a != b for a, b in zip(wt, mutant))


def is_transition(wt, mutant):
    changes = [(a, b) for a, b in zip(wt, mutant) if a != b]
    return float(len(changes) == 1 and tuple(changes[0]) in TRANSITIONS)


def construct_features(row, wt_row):
    wt = row["wt_codon"]
    mutant = row["mutant_codon"]
    pos = int(row["codon_position"])
    f = json.loads(row["features_json"])
    w = json.loads(wt_row["features_json"])
    rcs = float(f["RCS"])
    mfe = float(f["mfe_ddG_43nt_sliding"])
    wt_rcs = float(w["RCS"])
    wt_mfe = float(w["mfe_ddG_43nt_sliding"])
    delta_rcs = rcs - wt_rcs
    delta_mfe = mfe - wt_mfe
    position_scaled = pos / 71.0
    return {
        "position": str(pos),
        "wt_codon": wt,
        "mutant_codon": mutant,
        "amino_acid": row["amino_acid"],
        "position_scaled": position_scaled,
        "wt_gc_fraction": gc(wt),
        "mutant_gc_fraction": gc(mutant),
        "delta_gc_fraction": gc(mutant) - gc(wt),
        "wt_gc3": float(wt[2] in "GC"),
        "mutant_gc3": float(mutant[2] in "GC"),
        "nt_changes": float(nt_changes(wt, mutant)),
        "is_transition": is_transition(wt, mutant),
        "mfe_ddG_43nt_sliding": mfe,
        "delta_mfe_vs_wt": delta_mfe,
        "abs_delta_mfe_vs_wt": abs(delta_mfe),
        "mfe_x_position_scaled": mfe * position_scaled,
        "RCS": rcs,
        "delta_rcs_vs_wt": delta_rcs,
        "abs_delta_rcs_vs_wt": abs(delta_rcs),
        "rcs_x_position_scaled": rcs * position_scaled,
    }


def numeric_for(feature_set):
    if feature_set == "intrinsic":
        return INTRINSIC_NUM
    if feature_set == "local_mfe":
        return INTRINSIC_NUM + MFE_NUM
    if feature_set == "rcs_only":
        return INTRINSIC_NUM + RCS_NUM
    if feature_set == "full_mechanism":
        return INTRINSIC_NUM + MFE_NUM + RCS_NUM
    raise KeyError(feature_set)


def make_pipeline(feature_set, alpha):
    nums = numeric_for(feature_set)
    transformer = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=True), CATS),
        ("numeric", StandardScaler(with_mean=False), nums),
    ])
    return Pipeline([
        ("features", transformer),
        ("ridge", Ridge(alpha=alpha, fit_intercept=True, solver="lsqr", tol=1e-12, max_iter=100000)),
    ])


def xy(records, feature_set):
    nums = numeric_for(feature_set)
    columns = CATS + nums
    X = pd.DataFrame([{c: row[c] for c in columns} for row in records], columns=columns)
    for c in nums:
        X[c] = X[c].astype(np.float64)
    for c in CATS:
        X[c] = X[c].astype(str)
    y = np.asarray([float(row["expression_value"]) for row in records], dtype=np.float64)
    return X, y


def metrics(y, pred):
    y = np.asarray(y, dtype=np.float64)
    pred = np.asarray(pred, dtype=np.float64)
    return {
        "n": int(len(y)),
        "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
        "mae": float(np.mean(np.abs(y - pred))),
        "spearman": float(spearmanr(y, pred).statistic),
        "mean_y": float(np.mean(y)),
        "mean_prediction": float(np.mean(pred)),
    }


def effect(y, candidate, reference):
    a = metrics(y, candidate)
    b = metrics(y, reference)
    return {"delta_spearman": a["spearman"] - b["spearman"], "delta_rmse": a["rmse"] - b["rmse"]}


def paired_analysis(y, candidate, reference, bootstrap_seed, permutation_seed, replicates, with_permutation=True):
    y = np.asarray(y, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    observed = effect(y, candidate, reference)
    n = len(y)
    boot = np.empty((replicates, 2), dtype=np.float64)
    rng = np.random.default_rng(bootstrap_seed)
    for b in range(replicates):
        idx = rng.integers(0, n, n)
        boot[b, 0] = effect(y[idx], candidate[idx], reference[idx])["delta_spearman"]
        boot[b, 1] = effect(y[idx], candidate[idx], reference[idx])["delta_rmse"]
    result = {
        **observed,
        "delta_spearman_ci95": [float(x) for x in np.percentile(boot[:, 0], [2.5, 97.5])],
        "delta_rmse_ci95": [float(x) for x in np.percentile(boot[:, 1], [2.5, 97.5])],
        "bootstrap_replicates": int(replicates),
    }
    if with_permutation:
        rng = np.random.default_rng(permutation_seed)
        perm = np.empty((replicates, 2), dtype=np.float64)
        for b in range(replicates):
            swap = rng.random(n) < 0.5
            c = np.where(swap, reference, candidate)
            r = np.where(swap, candidate, reference)
            perm[b, 0] = effect(y, c, r)["delta_spearman"]
            perm[b, 1] = effect(y, c, r)["delta_rmse"]
        obs = np.asarray([observed["delta_spearman"], observed["delta_rmse"]])
        p = (1 + np.sum(np.abs(perm) >= np.abs(obs)[None, :], axis=0)) / (replicates + 1.0)
        result.update({"permutation_p_spearman": float(p[0]), "permutation_p_rmse": float(p[1]), "permutation_replicates": int(replicates)})
    return result


def holm_two(p_values):
    p = np.asarray(p_values, dtype=np.float64)
    order = np.argsort(p)
    adjusted = np.empty(2, dtype=np.float64)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (2 - rank) * p[idx])
        adjusted[idx] = min(1.0, running)
    return [float(x) for x in adjusted]


def fit_select(records, medium, alphas):
    train = [r for r in records if r["split"] == "train" and r["expression_type"] == medium]
    dev = [r for r in records if r["split"] == "dev" and r["expression_type"] == medium]
    output = {}
    dev_predictions = {}
    for feature_set in BASE:
        trials = []
        for alpha in alphas:
            model = make_pipeline(feature_set, alpha)
            X, y = xy(train, feature_set)
            model.fit(X, y)
            Xd, yd = xy(dev, feature_set)
            pred = model.predict(Xd)
            m = metrics(yd, pred)
            trials.append({"alpha": alpha, "dev": m, "model": model, "pred": pred})
        best = sorted(trials, key=lambda t: (t["dev"]["rmse"], -t["alpha"], str(t["alpha"])))[0]
        output[feature_set] = {"selected_alpha": best["alpha"], "dev": best["dev"], "alpha_grid": [{"alpha": t["alpha"], "dev_rmse": t["dev"]["rmse"], "dev_spearman": t["dev"]["spearman"]} for t in trials]}
        dev_predictions[feature_set] = best["pred"].tolist()
    reference = min(["intrinsic", "local_mfe"], key=lambda k: (output[k]["dev"]["rmse"], k))
    authorized = output["full_mechanism"]["dev"]["rmse"] < min(output["intrinsic"]["dev"]["rmse"], output["local_mfe"]["dev"]["rmse"])
    return {"models": output, "reference_baseline": reference, "test_authorized": bool(authorized), "dev_predictions": dev_predictions, "dev_construct_ids": [r["construct_id"] for r in dev]}


def refit_predict(records, medium, selection, evaluation_records):
    fit = [r for r in records if r["split"] in {"train", "dev"} and r["expression_type"] == medium]
    predictions = {}
    for feature_set in BASE:
        model = make_pipeline(feature_set, selection["models"][feature_set]["selected_alpha"])
        X, y = xy(fit, feature_set)
        model.fit(X, y)
        Xe, _ = xy(evaluation_records, feature_set)
        predictions[feature_set] = model.predict(Xe)
    return predictions


def evaluate_feature_sets(y, predictions, bootstrap_seed, replicates):
    result = {name: metrics(y, pred) for name, pred in predictions.items()}
    comparisons = {}
    for i, reference in enumerate(BASE[:-1]):
        comparisons[f"full_mechanism_minus_{reference}"] = paired_analysis(
            y, predictions["full_mechanism"], predictions[reference], bootstrap_seed + i, bootstrap_seed + 100 + i, replicates, with_permutation=False
        )
    return {"models": result, "comparisons": comparisons}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    config_path = Path(args.config).resolve()
    cfg = json.loads(config_path.read_text())
    os.environ.setdefault("PYTHONHASHSEED", "0")
    csv_path = Path(cfg["source"]["csv"])
    assert sha256(csv_path) == cfg["source"]["csv_sha256"]
    assert sha256(cfg["source"]["codon_module"]) == cfg["source"]["codon_module_sha256"]
    from codonflow.core.codon import AA_OF_INDEX, CODON_TO_INDEX, STOP_CODONS

    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    wt_by_position = {}
    media_rows = {"relative_fitness_rich": {}, "relative_fitness_minimal": {}}
    for row in rows:
        if row["record_class"] == "wild_type_control" and row["expression_type"] == "relative_fitness_rich":
            wt_by_position[int(row["codon_position"])] = row
        if row["record_class"] == "single_codon_variant" and row["expression_type"] in media_rows:
            media_rows[row["expression_type"]][row["construct_id"]] = row

    def aa(codon):
        return AA_OF_INDEX[CODON_TO_INDEX[codon]]

    def eligible(row):
        pos = int(row["codon_position"])
        wt = wt_by_position.get(pos)
        if wt is None or row["wt_codon"] in STOP_CODONS or row["mutant_codon"] in STOP_CODONS:
            return False
        if row["wt_codon"] == row["mutant_codon"] or row["amino_acid"] == "*":
            return False
        if aa(row["wt_codon"]) != aa(row["mutant_codon"]) or aa(row["mutant_codon"]) != row["amino_acid"]:
            return False
        if not finite(row["expression_value"]) or not finite(row["expression_stdev"]):
            return False
        f = json.loads(row["features_json"])
        w = json.loads(wt["features_json"])
        return all(finite(f.get(k)) and finite(w.get(k)) for k in ("RCS", "mfe_ddG_43nt_sliding"))

    common = set(media_rows["relative_fitness_rich"]) & set(media_rows["relative_fitness_minimal"])
    eligible_constructs = sorted(c for c in common if eligible(media_rows["relative_fitness_rich"][c]) and eligible(media_rows["relative_fitness_minimal"][c]))
    for c in eligible_constructs:
        a = json.loads(media_rows["relative_fitness_rich"][c]["features_json"])
        b = json.loads(media_rows["relative_fitness_minimal"][c]["features_json"])
        assert all(float(a[k]) == float(b[k]) for k in ("RCS", "mfe_ddG_43nt_sliding"))
    for pos, rich_wt in wt_by_position.items():
        minimal_wt = [r for r in rows if r["record_class"] == "wild_type_control" and r["expression_type"] == "relative_fitness_minimal" and int(r["codon_position"]) == pos]
        if minimal_wt:
            a = json.loads(rich_wt["features_json"])
            b = json.loads(minimal_wt[0]["features_json"])
            assert all(not finite(a.get(k)) or not finite(b.get(k)) or float(a[k]) == float(b[k]) for k in ("RCS", "mfe_ddG_43nt_sliding"))

    seed = cfg["split"]["seed"]
    primary_constructs = [c for c in eligible_constructs if 10 <= int(media_rows["relative_fitness_rich"][c]["codon_position"]) <= 71]
    ordered = sorted(primary_constructs, key=lambda c: hashlib.sha256((seed + ":" + c).encode()).hexdigest())
    n = len(ordered)
    n_dev = round(n * 0.2)
    n_test = round(n * 0.2)
    split_by_construct = {}
    for i, c in enumerate(ordered):
        split_by_construct[c] = "dev" if i < n_dev else ("test" if i < n_dev + n_test else "train")
    # Assignment order is hash-based; returned records are canonicalized by construct ID.
    primary = []
    for c in primary_constructs:
        rich = media_rows["relative_fitness_rich"][c]
        pos = int(rich["codon_position"])
        for medium in ("relative_fitness_rich", "relative_fitness_minimal"):
            row = dict(media_rows[medium][c])
            row.update(construct_features(row, wt_by_position[pos]))
            row["split"] = split_by_construct[c]
            primary.append(row)
    split_counts = Counter(r["split"] for r in primary if r["expression_type"] == "relative_fitness_rich")
    assert dict(split_counts) == {"train": 98, "dev": 33, "test": 33}, split_counts

    rich_records = [r for r in primary if r["expression_type"] == "relative_fitness_rich"]
    selection = fit_select(primary, "relative_fitness_rich", cfg["model"]["alpha_grid"])
    authorized = selection["test_authorized"]
    summary = {
        "schema": "a8-rk03-mage-synonymous-mechanism-v1",
        "status": "DEV_NO_GO_TEST_UNTOUCHED" if not authorized else "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "protocol_id": cfg["protocol_id"],
        "protocol_sha256": sha256(config_path),
        "source_csv_sha256": sha256(csv_path),
        "codon_module_sha256": sha256(cfg["source"]["codon_module"]),
        "eligibility": {
            "source_rows": len(rows),
            "common_constructs_across_media": len(common),
            "eligible_constructs_all_positions": len(eligible_constructs),
            "primary_constructs_positions_10_71": len(rich_records),
            "primary_positions": len({r["codon_position"] for r in rich_records}),
            "split_counts": dict(split_counts),
            "split_assignments_sha256": hashlib.sha256("\n".join(f"{c},{split_by_construct[c]}" for c in sorted(split_by_construct)).encode()).hexdigest(),
        },
        "rich_dev_selection": {"models": selection["models"], "reference_baseline": selection["reference_baseline"], "test_authorized": authorized},
        "primary_test": None,
        "secondary": None,
        "mechanism_increment_pass": False,
        "limitations": cfg["interpretation"],
    }

    artifact_root = Path(cfg["artifacts"]["large_artifact_root"])
    artifact_root.mkdir(parents=True, exist_ok=True)
    with (artifact_root / "split_assignments.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["construct_id", "position", "split"])
        for c in sorted(split_by_construct):
            writer.writerow([c, media_rows["relative_fitness_rich"][c]["codon_position"], split_by_construct[c]])
    with (artifact_root / "dev_predictions.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["construct_id", "observed_rich"] + BASE)
        dev_rich = sorted([r for r in primary if r["expression_type"] == "relative_fitness_rich" and r["split"] == "dev"], key=lambda r: r["construct_id"])
        assert [r["construct_id"] for r in dev_rich] == selection["dev_construct_ids"]
        for i, row in enumerate(dev_rich):
            writer.writerow([row["construct_id"], row["expression_value"]] + [selection["dev_predictions"][m][i] for m in BASE])

    if authorized:
        test = sorted([r for r in primary if r["split"] == "test"], key=lambda r: r["construct_id"])
        rich_test = [r for r in test if r["expression_type"] == "relative_fitness_rich"]
        rich_predictions = refit_predict(primary, "relative_fitness_rich", selection, rich_test)
        y_rich = np.asarray([float(r["expression_value"]) for r in rich_test])
        reference = selection["reference_baseline"]
        primary_result = paired_analysis(y_rich, rich_predictions["full_mechanism"], rich_predictions[reference], 30261219, 30261220, 20000, True)
        p_adj = holm_two([primary_result["permutation_p_spearman"], primary_result["permutation_p_rmse"]])
        primary_result.update({"reference_baseline": reference, "holm_p_spearman": p_adj[0], "holm_p_rmse": p_adj[1]})
        primary_result["models"] = {name: metrics(y_rich, pred) for name, pred in rich_predictions.items()}
        primary_result["all_comparisons"] = evaluate_feature_sets(y_rich, rich_predictions, 30261300, 20000)["comparisons"]
        mechanism_pass = (
            primary_result["delta_spearman_ci95"][0] > 0
            and primary_result["delta_rmse_ci95"][1] < 0
            and max(p_adj) < 0.05
        )
        summary["primary_test"] = primary_result
        summary["mechanism_increment_pass"] = bool(mechanism_pass)

        minimal_selection = fit_select(primary, "relative_fitness_minimal", cfg["model"]["alpha_grid"])
        minimal_test = [r for r in test if r["expression_type"] == "relative_fitness_minimal"]
        minimal_predictions = refit_predict(primary, "relative_fitness_minimal", minimal_selection, minimal_test)
        y_minimal = np.asarray([float(r["expression_value"]) for r in minimal_test])
        minimal_eval = evaluate_feature_sets(y_minimal, minimal_predictions, 30261400, 20000)
        minimal_eval["selection"] = {"models": minimal_selection["models"], "reference_baseline": minimal_selection["reference_baseline"]}
        transport_eval = evaluate_feature_sets(y_minimal, rich_predictions, 30261500, 20000)

        n_terminal = []
        for c in eligible_constructs:
            rich = media_rows["relative_fitness_rich"][c]
            pos = int(rich["codon_position"])
            if 2 <= pos <= 9:
                row = dict(rich)
                row.update(construct_features(rich, wt_by_position[pos]))
                n_terminal.append(row)
        n_terminal = sorted(n_terminal, key=lambda r: r["construct_id"])
        nterm_predictions = refit_predict(primary, "relative_fitness_rich", selection, n_terminal)
        y_nterm = np.asarray([float(r["expression_value"]) for r in n_terminal])
        nterm_eval = evaluate_feature_sets(y_nterm, nterm_predictions, 30261600, 20000)
        nterm_eval["note"] = "Transport only; positions 2-3 can overlap the source pair-library region and are not independent of RCS supervision."
        summary["secondary"] = {"minimal_within_condition": minimal_eval, "rich_to_minimal_transport": transport_eval, "n_terminal_transport": nterm_eval}

        with (artifact_root / "test_predictions.csv").open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["construct_id", "position", "observed_rich", "observed_minimal"] + [f"rich_{m}" for m in BASE] + [f"minimal_{m}" for m in BASE] + [f"transport_{m}" for m in BASE])
            for i in range(len(test) // 2):
                writer.writerow([rich_test[i]["construct_id"], rich_test[i]["codon_position"], y_rich[i], y_minimal[i]] + [rich_predictions[m][i] for m in BASE] + [minimal_predictions[m][i] for m in BASE] + [rich_predictions[m][i] for m in BASE])
        with (artifact_root / "n_terminal_transport_predictions.csv").open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["construct_id", "position", "observed_rich"] + BASE)
            for i, row in enumerate(n_terminal):
                writer.writerow([row["construct_id"], row["codon_position"], y_nterm[i]] + [nterm_predictions[m][i] for m in BASE])

    summary["artifact_files"] = {}
    for path in sorted(artifact_root.glob("*.csv")):
        summary["artifact_files"][path.name] = {"sha256": sha256(path), "bytes": path.stat().st_size}
    summary["elapsed_s"] = time.perf_counter() - started
    dump(args.output, summary)
    print(json.dumps({"status": summary["status"], "primary_n": len(rich_records), "test_authorized": authorized, "mechanism_increment_pass": summary["mechanism_increment_pass"], "elapsed_s": summary["elapsed_s"]}, indent=2))


if __name__ == "__main__":
    main()
