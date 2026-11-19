#!/usr/bin/env python3
"""Independent raw-data and model-matrix verification for the frozen MAGE experiment."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.stats import rankdata
from sklearn.linear_model import Ridge

FEATURE_SETS = ["intrinsic", "local_mfe", "rcs_only", "full_mechanism"]
CAT = ["position", "wt_codon", "mutant_codon", "amino_acid"]
N0 = ["position_scaled", "wt_gc_fraction", "mutant_gc_fraction", "delta_gc_fraction", "wt_gc3", "mutant_gc3", "nt_changes", "is_transition"]
NM = ["mfe_ddG_43nt_sliding", "delta_mfe_vs_wt", "abs_delta_mfe_vs_wt", "mfe_x_position_scaled"]
NR = ["RCS", "delta_rcs_vs_wt", "abs_delta_rcs_vs_wt", "rcs_x_position_scaled"]
SWAP = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def nums(kind):
    return N0 if kind == "intrinsic" else N0 + NM if kind == "local_mfe" else N0 + NR if kind == "rcs_only" else N0 + NM + NR


def features(row, wtrow):
    wt, mut = row["wt_codon"], row["mutant_codon"]
    pos = int(row["codon_position"])
    f, w = json.loads(row["features_json"]), json.loads(wtrow["features_json"])
    rc, mf, wr, wm = float(f["RCS"]), float(f["mfe_ddG_43nt_sliding"]), float(w["RCS"]), float(w["mfe_ddG_43nt_sliding"])
    g = lambda c: (c.count("G") + c.count("C")) / 3.0
    differences = [(a, b) for a, b in zip(wt, mut) if a != b]
    ps = pos / 71.0
    return {
        "position": str(pos), "wt_codon": wt, "mutant_codon": mut, "amino_acid": row["amino_acid"],
        "position_scaled": ps, "wt_gc_fraction": g(wt), "mutant_gc_fraction": g(mut), "delta_gc_fraction": g(mut) - g(wt),
        "wt_gc3": float(wt[2] in "GC"), "mutant_gc3": float(mut[2] in "GC"), "nt_changes": float(len(differences)),
        "is_transition": float(len(differences) == 1 and tuple(differences[0]) in SWAP),
        "mfe_ddG_43nt_sliding": mf, "delta_mfe_vs_wt": mf - wm, "abs_delta_mfe_vs_wt": abs(mf - wm), "mfe_x_position_scaled": mf * ps,
        "RCS": rc, "delta_rcs_vs_wt": rc - wr, "abs_delta_rcs_vs_wt": abs(rc - wr), "rcs_x_position_scaled": rc * ps,
    }


class ManualDesign:
    def __init__(self, kind):
        self.kind = kind
        self.numeric = nums(kind)

    def fit(self, records):
        self.categories = {c: sorted({str(r[c]) for r in records}) for c in CAT}
        self.offsets = {}
        offset = 0
        for c in CAT:
            self.offsets[c] = (offset, {v: i for i, v in enumerate(self.categories[c])})
            offset += len(self.categories[c])
        self.n_categorical = offset
        values = np.asarray([[float(r[c]) for c in self.numeric] for r in records], dtype=np.float64)
        scale = np.sqrt(np.mean(values ** 2, axis=0) - np.mean(values, axis=0) ** 2)
        scale[scale <= 0] = 1.0
        self.scale = scale
        return self

    def transform(self, records):
        rows, cols = [], []
        for i, r in enumerate(records):
            for c in CAT:
                offset, mapping = self.offsets[c]
                value = str(r[c])
                if value in mapping:
                    rows.append(i)
                    cols.append(offset + mapping[value])
        categorical = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(records), self.n_categorical), dtype=np.float64)
        numeric = np.asarray([[float(r[c]) for c in self.numeric] for r in records], dtype=np.float64) / self.scale
        return sparse.hstack([categorical, sparse.csr_matrix(numeric)], format="csr")


def fit_model(train, kind, alpha):
    design = ManualDesign(kind).fit(train)
    X = design.transform(train)
    y = np.asarray([float(r["expression_value"]) for r in train], dtype=np.float64)
    model = Ridge(alpha=alpha, fit_intercept=True, solver="lsqr", tol=1e-12, max_iter=100000)
    model.fit(X, y)
    return design, model


def predict(fitted, records):
    design, model = fitted
    return model.predict(design.transform(records))


def corr(y, p):
    a, b = rankdata(y), rankdata(p)
    return float(np.corrcoef(a, b)[0, 1])


def met(y, p):
    y, p = np.asarray(y), np.asarray(p)
    return {"n": int(len(y)), "rmse": float(np.sqrt(np.mean((y - p) ** 2))), "mae": float(np.mean(np.abs(y - p))), "spearman": corr(y, p), "mean_y": float(np.mean(y)), "mean_prediction": float(np.mean(p))}


def delta(y, c, r):
    return np.asarray([corr(y, c) - corr(y, r), met(y, c)["rmse"] - met(y, r)["rmse"]])


def paired(y, c, r, bs, ps, B, permutation):
    y, c, r = np.asarray(y), np.asarray(c), np.asarray(r)
    n = len(y)
    observed = delta(y, c, r)
    rng = np.random.default_rng(bs)
    boot = np.empty((B, 2))
    for b in range(B):
        idx = rng.integers(0, n, n)
        boot[b] = delta(y[idx], c[idx], r[idx])
    out = {
        "delta_spearman": float(observed[0]), "delta_rmse": float(observed[1]),
        "delta_spearman_ci95": [float(x) for x in np.percentile(boot[:, 0], [2.5, 97.5])],
        "delta_rmse_ci95": [float(x) for x in np.percentile(boot[:, 1], [2.5, 97.5])],
        "bootstrap_replicates": B,
    }
    if permutation:
        rng = np.random.default_rng(ps)
        null = np.empty((B, 2))
        for b in range(B):
            swap = rng.random(n) < 0.5
            null[b] = delta(y, np.where(swap, r, c), np.where(swap, c, r))
        p = (1 + np.sum(np.abs(null) >= np.abs(observed)[None, :], axis=0)) / (B + 1.0)
        out.update({"permutation_p_spearman": float(p[0]), "permutation_p_rmse": float(p[1]), "permutation_replicates": B})
    return out


def select(records, medium, alphas):
    train = [r for r in records if r["split"] == "train" and r["expression_type"] == medium]
    dev = [r for r in records if r["split"] == "dev" and r["expression_type"] == medium]
    models, dev_predictions = {}, {}
    for kind in FEATURE_SETS:
        trials = []
        for alpha in alphas:
            fitted = fit_model(train, kind, alpha)
            pred = predict(fitted, dev)
            trials.append((alpha, met([float(r["expression_value"]) for r in dev], pred), pred))
        best = sorted(trials, key=lambda t: (t[1]["rmse"], -t[0], str(t[0])))[0]
        models[kind] = {"selected_alpha": best[0], "dev": best[1], "trials": trials}
        dev_predictions[kind] = best[2]
    reference = min(["intrinsic", "local_mfe"], key=lambda k: (models[k]["dev"]["rmse"], k))
    authorized = models["full_mechanism"]["dev"]["rmse"] < min(models["intrinsic"]["dev"]["rmse"], models["local_mfe"]["dev"]["rmse"])
    return {"models": models, "reference": reference, "authorized": authorized, "dev_predictions": dev_predictions, "dev": dev}


def final_predictions(records, medium, chosen, evaluation):
    fit = [r for r in records if r["split"] in {"train", "dev"} and r["expression_type"] == medium]
    return {kind: predict(fit_model(fit, kind, chosen["models"][kind]["selected_alpha"]), evaluation) for kind in FEATURE_SETS}


def comparisons(y, preds, seed, B=20000):
    return {f"full_mechanism_minus_{ref}": paired(y, preds["full_mechanism"], preds[ref], seed + i, seed + 100 + i, B, False) for i, ref in enumerate(FEATURE_SETS[:-1])}


def flatten_numbers(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten_numbers(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten_numbers(v, f"{prefix}[{i}]"))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out[prefix] = float(obj)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--production", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    prod = json.loads(Path(args.production).read_text())
    checks = []
    max_delta = 0.0

    def check(name, ok, detail=""):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    def close(name, actual, expected, tol=2e-11):
        nonlocal max_delta
        a, b = flatten_numbers(actual), flatten_numbers(expected)
        check(name + ".keys", set(a) == set(b), {"only_independent": sorted(set(a) - set(b)), "only_production": sorted(set(b) - set(a))})
        if set(a) == set(b):
            d = max((abs(a[k] - b[k]) for k in a), default=0.0)
            max_delta = max(max_delta, d)
            check(name + ".values", d <= tol, {"max_abs_delta": d, "tolerance": tol})

    check("source_csv_sha256", digest(cfg["source"]["csv"]) == prod["source_csv_sha256"] == cfg["source"]["csv_sha256"])
    check("protocol_sha256", digest(args.config) == prod["protocol_sha256"])
    check("codon_module_sha256", digest(cfg["source"]["codon_module"]) == prod["codon_module_sha256"])
    from codonflow.core.codon import AA_OF_INDEX, CODON_TO_INDEX, STOP_CODONS
    with open(cfg["source"]["csv"], newline="") as f:
        source = list(csv.DictReader(f))
    wt = {int(r["codon_position"]): r for r in source if r["record_class"] == "wild_type_control" and r["expression_type"] == "relative_fitness_rich"}
    media = {m: {r["construct_id"]: r for r in source if r["record_class"] == "single_codon_variant" and r["expression_type"] == m} for m in ("relative_fitness_rich", "relative_fitness_minimal")}

    def valid(r):
        p = int(r["codon_position"])
        if p not in wt or r["wt_codon"] in STOP_CODONS or r["mutant_codon"] in STOP_CODONS or r["wt_codon"] == r["mutant_codon"] or r["amino_acid"] == "*":
            return False
        if AA_OF_INDEX[CODON_TO_INDEX[r["wt_codon"]]] != AA_OF_INDEX[CODON_TO_INDEX[r["mutant_codon"]]] or r["amino_acid"] != AA_OF_INDEX[CODON_TO_INDEX[r["mutant_codon"]]]:
            return False
        try:
            if not math.isfinite(float(r["expression_value"])) or not math.isfinite(float(r["expression_stdev"])):
                return False
            f, w = json.loads(r["features_json"]), json.loads(wt[p]["features_json"])
            return all(math.isfinite(float(f[k])) and math.isfinite(float(w[k])) for k in ("RCS", "mfe_ddG_43nt_sliding"))
        except (KeyError, TypeError, ValueError):
            return False

    common = set(media["relative_fitness_rich"]) & set(media["relative_fitness_minimal"])
    eligible = sorted(c for c in common if valid(media["relative_fitness_rich"][c]) and valid(media["relative_fitness_minimal"][c]))
    primary_ids = [c for c in eligible if 10 <= int(media["relative_fitness_rich"][c]["codon_position"]) <= 71]
    ordered = sorted(primary_ids, key=lambda c: hashlib.sha256(("20261119:" + c).encode()).hexdigest())
    nd, nt = round(len(ordered) * 0.2), round(len(ordered) * 0.2)
    assignment = {c: "dev" if i < nd else "test" if i < nd + nt else "train" for i, c in enumerate(ordered)}
    records = []
    for c in primary_ids:
        for medium in media:
            row = dict(media[medium][c])
            row.update(features(row, wt[int(row["codon_position"])]))
            row["split"] = assignment[c]
            records.append(row)
    rich = [r for r in records if r["expression_type"] == "relative_fitness_rich"]
    counts = dict(Counter(r["split"] for r in rich))
    check("eligible_all_positions", len(eligible) == prod["eligibility"]["eligible_constructs_all_positions"], len(eligible))
    check("eligible_primary", len(primary_ids) == prod["eligibility"]["primary_constructs_positions_10_71"], len(primary_ids))
    check("split_counts", counts == prod["eligibility"]["split_counts"], counts)
    assignment_hash = hashlib.sha256("\n".join(f"{c},{assignment[c]}" for c in sorted(assignment)).encode()).hexdigest()
    check("split_assignment_hash", assignment_hash == prod["eligibility"]["split_assignments_sha256"])

    chosen = select(records, "relative_fitness_rich", cfg["model"]["alpha_grid"])
    for kind in FEATURE_SETS:
        expected = prod["rich_dev_selection"]["models"][kind]
        check("alpha." + kind, chosen["models"][kind]["selected_alpha"] == expected["selected_alpha"], chosen["models"][kind]["selected_alpha"])
        close("dev_metrics." + kind, chosen["models"][kind]["dev"], expected["dev"])
        independent_grid = [{"alpha": a, "dev_rmse": m["rmse"], "dev_spearman": m["spearman"]} for a, m, _ in chosen["models"][kind]["trials"]]
        close("dev_grid." + kind, independent_grid, expected["alpha_grid"])
    check("reference_baseline", chosen["reference"] == prod["rich_dev_selection"]["reference_baseline"], chosen["reference"])
    check("dev_authorization", chosen["authorized"] == prod["rich_dev_selection"]["test_authorized"] == prod["rich_dev_selection"]["test_authorized"], chosen["authorized"])
    artifact_root = Path(cfg["artifacts"]["large_artifact_root"])
    with (artifact_root / "dev_predictions.csv").open(newline="") as f:
        dev_file = list(csv.DictReader(f))
    check("dev_prediction_order", [r["construct_id"] for r in dev_file] == [r["construct_id"] for r in chosen["dev"]])
    for kind in FEATURE_SETS:
        actual = chosen["dev_predictions"][kind]
        expected = np.asarray([float(r[kind]) for r in dev_file])
        d = float(np.max(np.abs(actual - expected)))
        max_delta = max(max_delta, d)
        check("dev_prediction_values." + kind, d <= 2e-11, d)

    if not chosen["authorized"]:
        check("no_go_status", prod["status"] == "DEV_NO_GO_TEST_UNTOUCHED")
        check("no_test_metrics", prod["primary_test"] is None and prod["secondary"] is None)
        check("no_test_artifacts", not (artifact_root / "test_predictions.csv").exists() and not (artifact_root / "n_terminal_transport_predictions.csv").exists())
    else:
        test = sorted([r for r in records if r["split"] == "test"], key=lambda r: r["construct_id"])
        rich_test = [r for r in test if r["expression_type"] == "relative_fitness_rich"]
        minimal_test = [r for r in test if r["expression_type"] == "relative_fitness_minimal"]
        rich_pred = final_predictions(records, "relative_fitness_rich", chosen, rich_test)
        y_rich = np.asarray([float(r["expression_value"]) for r in rich_test])
        y_min = np.asarray([float(r["expression_value"]) for r in minimal_test])
        primary = paired(y_rich, rich_pred["full_mechanism"], rich_pred[chosen["reference"]], 30261219, 30261220, 20000, True)
        p = [primary["permutation_p_spearman"], primary["permutation_p_rmse"]]
        order = np.argsort(p)
        adjusted = np.empty(2)
        running = 0.0
        for rank, idx in enumerate(order):
            running = max(running, (2 - rank) * p[idx])
            adjusted[idx] = min(1.0, running)
        primary.update({"reference_baseline": chosen["reference"], "holm_p_spearman": float(adjusted[0]), "holm_p_rmse": float(adjusted[1])})
        close("primary_effect", primary, {k: v for k, v in prod["primary_test"].items() if k not in {"models", "all_comparisons"}})
        close("primary_model_metrics", {k: met(y_rich, v) for k, v in rich_pred.items()}, prod["primary_test"]["models"])
        close("primary_all_comparisons", comparisons(y_rich, rich_pred, 30261300), prod["primary_test"]["all_comparisons"])
        mechanism_pass = primary["delta_spearman_ci95"][0] > 0 and primary["delta_rmse_ci95"][1] < 0 and max(adjusted) < 0.05
        check("mechanism_gate", mechanism_pass == prod["mechanism_increment_pass"], mechanism_pass)

        with (artifact_root / "test_predictions.csv").open(newline="") as f:
            test_file = list(csv.DictReader(f))
        check("test_prediction_order", [r["construct_id"] for r in test_file] == [r["construct_id"] for r in rich_test])
        minimal_chosen = select(records, "relative_fitness_minimal", cfg["model"]["alpha_grid"])
        minimal_pred = final_predictions(records, "relative_fitness_minimal", minimal_chosen, minimal_test)
        for kind in FEATURE_SETS:
            for prefix, array in (("rich_", rich_pred[kind]), ("minimal_", minimal_pred[kind]), ("transport_", rich_pred[kind])):
                expected = np.asarray([float(r[prefix + kind]) for r in test_file])
                d = float(np.max(np.abs(array - expected)))
                max_delta = max(max_delta, d)
                check("test_predictions." + prefix + kind, d <= 2e-11, d)
        close("minimal_metrics", {k: met(y_min, v) for k, v in minimal_pred.items()}, prod["secondary"]["minimal_within_condition"]["models"])
        close("minimal_comparisons", comparisons(y_min, minimal_pred, 30261400), prod["secondary"]["minimal_within_condition"]["comparisons"])
        close("transport_metrics", {k: met(y_min, v) for k, v in rich_pred.items()}, prod["secondary"]["rich_to_minimal_transport"]["models"])
        close("transport_comparisons", comparisons(y_min, rich_pred, 30261500), prod["secondary"]["rich_to_minimal_transport"]["comparisons"])
        for kind in FEATURE_SETS:
            close("minimal_dev." + kind, minimal_chosen["models"][kind]["dev"], prod["secondary"]["minimal_within_condition"]["selection"]["models"][kind]["dev"])
            check("minimal_alpha." + kind, minimal_chosen["models"][kind]["selected_alpha"] == prod["secondary"]["minimal_within_condition"]["selection"]["models"][kind]["selected_alpha"])

        nterm = []
        for c in eligible:
            row = media["relative_fitness_rich"][c]
            if 2 <= int(row["codon_position"]) <= 9:
                item = dict(row)
                item.update(features(row, wt[int(row["codon_position"])]))
                nterm.append(item)
        nterm = sorted(nterm, key=lambda r: r["construct_id"])
        nterm_pred = final_predictions(records, "relative_fitness_rich", chosen, nterm)
        y_nterm = np.asarray([float(r["expression_value"]) for r in nterm])
        close("nterm_metrics", {k: met(y_nterm, v) for k, v in nterm_pred.items()}, prod["secondary"]["n_terminal_transport"]["models"])
        close("nterm_comparisons", comparisons(y_nterm, nterm_pred, 30261600), prod["secondary"]["n_terminal_transport"]["comparisons"])

    for name, metadata in prod["artifact_files"].items():
        check("artifact_hash." + name, digest(artifact_root / name) == metadata["sha256"])
    passed = sum(c["pass"] for c in checks)
    report = {"schema": "a8-rk03-mage-synonymous-independent-v1", "status": "PASS" if passed == len(checks) else "FAIL", "checks_passed": passed, "checks_total": len(checks), "max_numeric_delta": max_delta, "tolerance": 2e-11, "checks": checks, "production_sha256": digest(args.production)}
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "checks_passed", "checks_total", "max_numeric_delta")}, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
