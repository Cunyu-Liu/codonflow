#!/usr/bin/env python3
"""Independent RK37 raw/feature/model/statistics verification; no production import."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import numpy as np
from scipy import sparse
from scipy.stats import rankdata
from sklearn.linear_model import Ridge

ALPHABET = "ATCG"
CODOON_ORDER = tuple(a + b + c for a in ALPHABET for b in ALPHABET for c in ALPHABET)
INDEX = {codon: i for i, codon in enumerate(CODOON_ORDER)}
WINDOW = (-3, -2, -1, 0, 1, 2, 3)
ARMS = (
    "constant", "ribomimo_raw", "ribomimo_anchored", "position_raw_unanchored",
    "position_raw_anchored", "position_centered_anchored", "local_raw_anchored",
    "local_centered_anchored",
)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def read_records(path, prefix):
    lines = Path(path).read_text().splitlines()
    assert len(lines) % 3 == 0
    records = {}
    for i in range(0, len(lines), 3):
        name = prefix + "|" + lines[i][1:].split()[0]
        codons = tuple(lines[i + 1].split())
        counts = np.array([float(x) for x in lines[i + 2].split()], dtype=np.float64)
        assert len(codons) == len(counts)
        positive = counts > 0.5
        coverage = float(positive.mean())
        if coverage <= 0.6 or "N" in "".join(codons):
            continue
        records[name] = {"codons": codons, "counts": counts, "coverage": coverage, "density": None}
    return records, len(lines) // 3


def normalize(records):
    for name, record in records.items():
        counts = record["counts"]
        use = counts > 0.5
        assert use.any(), name
        record["density"] = use * counts / counts[use].mean()


def masked_labels(records, names):
    offsets = [0]
    pos_out, y_out = [], []
    for name in names:
        density = records[name]["density"]
        assert density is not None
        work = density.copy()
        work[:5] = 0
        work[-4:] = 0
        positions = np.flatnonzero(work > 0).astype(np.int32)
        pos_out.append(positions)
        y_out.append(work[positions].astype(np.float32))
        offsets.append(offsets[-1] + len(positions))
    return {
        "record_ids": np.asarray(names), "offsets": np.asarray(offsets, dtype=np.int64),
        "positions": np.concatenate(pos_out), "target": np.concatenate(y_out),
    }


def centered_target(labels):
    y = labels["target"].astype(np.float64).copy()
    for lo, hi in zip(labels["offsets"][:-1], labels["offsets"][1:]):
        y[lo:hi] -= y[lo:hi].mean(dtype=np.float64)
    return y


def recenter(labels, prediction, anchor):
    prediction = np.asarray(prediction, dtype=np.float64)
    out = prediction.copy()
    for lo, hi in zip(labels["offsets"][:-1], labels["offsets"][1:]):
        out[lo:hi] = prediction[lo:hi] - prediction[lo:hi].mean(dtype=np.float64) + anchor
    return out


def sparse_features(codons, kind):
    """Independent COO construction, deliberately different from production dense->CSR."""
    rows, columns, values = [], [], []
    n = len(codons)
    dimension = 86 if kind == "position" else 477
    base = 64 if kind == "position" else 455
    for pos in range(n):
        if kind == "local":
            for wi, shift in enumerate(WINDOW):
                source = pos + shift
                if 0 <= source < n:
                    rows.extend((pos, pos))
                    columns.extend((wi * 64 + INDEX[codons[source]], 448 + wi))
                    values.extend((1.0, 1.0))
        else:
            rows.append(pos)
            columns.append(INDEX[codons[pos]])
            values.append(1.0)
        rel = pos / max(n - 1, 1)
        rows.extend((pos, pos, pos))
        columns.extend((base + min(19, int(rel * 20)), base + 20, base + 21))
        values.extend((1.0, rel, math.log(n) / 7.0))
    return sparse.coo_matrix((values, (rows, columns)), shape=(n, dimension), dtype=np.float64).tocsr()


def design(records, labels, kind):
    pieces = []
    for i, name in enumerate(labels["record_ids"]):
        lo, hi = labels["offsets"][i:i + 2]
        positions = labels["positions"][lo:hi]
        pieces.append(sparse_features(records[str(name)]["codons"], kind)[positions])
    return sparse.vstack(pieces, format="csr")


def source_split(names, seed):
    ordered = np.array(sorted(names), dtype=object)
    np.random.seed(seed)
    split_seed = int(np.random.randint(0, 1024, 1)[0])
    np.random.seed(split_seed)
    np.random.shuffle(ordered)
    nvalid = len(ordered) // 10
    return ordered[nvalid:].tolist(), ordered[:nvalid].tolist(), split_seed


def transcript_arrays(labels, prediction):
    yall = labels["target"].astype(np.float64)
    pall = np.asarray(prediction, dtype=np.float64)
    mse, pearson, spearman = [], [], []
    for lo, hi in zip(labels["offsets"][:-1], labels["offsets"][1:]):
        y, p = yall[lo:hi], pall[lo:hi]
        mse.append(float(np.mean((y - p) ** 2)))
        if len(y) > 1 and y.std() > 0 and p.std() > 0:
            pearson.append(float(((y - y.mean()) * (p - p.mean())).mean() / (y.std() * p.std())))
            yr, pr = rankdata(y), rankdata(p)
            spearman.append(float(((yr - yr.mean()) * (pr - pr.mean())).mean() / (yr.std() * pr.std())))
        else:
            pearson.append(np.nan)
            spearman.append(np.nan)
    return {"mse": np.array(mse), "pearson": np.array(pearson), "spearman": np.array(spearman)}


def metric_summary(labels, prediction):
    per = transcript_arrays(labels, prediction)
    def agg(key, median=False):
        values = per[key][np.isfinite(per[key])]
        return float(np.median(values) if median else np.mean(values)) if len(values) else None
    y = labels["target"].astype(np.float64)
    p = np.asarray(prediction, dtype=np.float64)
    return {
        "n_transcripts": int(len(labels["record_ids"])), "n_masked_positions": int(len(y)),
        "n_transcripts_with_pearson": int(np.isfinite(per["pearson"]).sum()),
        "n_transcripts_with_spearman": int(np.isfinite(per["spearman"]).sum()),
        "transcript_balanced_mse": agg("mse"), "mean_transcript_pearson": agg("pearson"),
        "median_transcript_pearson": agg("pearson", True), "mean_transcript_spearman": agg("spearman"),
        "global_mse": float(np.mean((y - p) ** 2)),
        "global_r2": float(1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)),
        "global_pearson": float(((y - y.mean()) * (p - p.mean())).mean() / (y.std() * p.std())) if y.std() > 0 and p.std() > 0 else None,
    }, per


def fit_all_sources(protocol, source, seeds):
    normalize(source)
    states, reports = [], []
    total_fits = 0
    for seed in seeds:
        train_names, valid_names, split_seed = source_split(list(source), seed)
        train = masked_labels(source, train_names)
        valid = masked_labels(source, valid_names)
        centered = centered_target(train)
        anchor = float(train["target"].mean(dtype=np.float64))
        candidates_by_family, report_candidates = {}, {}
        for kind in ("position", "local"):
            xtrain = design(source, train, kind)
            xvalid = design(source, valid, kind)
            for mode, yfit in (("raw", train["target"].astype(np.float64)), ("centered", centered)):
                candidates = []
                for alpha in protocol["models"]["alpha_grid"]:
                    model = Ridge(alpha=float(alpha), fit_intercept=True, solver="lsqr", tol=1e-8, max_iter=10000)
                    model.fit(xtrain, yfit)
                    raw_prediction = model.predict(xvalid)
                    anchored_prediction = recenter(valid, raw_prediction, anchor)
                    raw_metrics, _ = metric_summary(valid, raw_prediction)
                    anchored_metrics, _ = metric_summary(valid, anchored_prediction)
                    candidates.append({
                        "alpha": float(alpha), "model": model,
                        "validation_raw": raw_metrics, "validation_anchored": anchored_metrics,
                    })
                    total_fits += 1
                candidates_by_family[(kind, mode)] = candidates
                report_candidates[f"{kind}_{mode}"] = [
                    {"alpha": c["alpha"], "validation_raw": c["validation_raw"], "validation_anchored": c["validation_anchored"]}
                    for c in candidates
                ]
        def choose(kind, mode, deployed):
            values = candidates_by_family[(kind, mode)]
            key = "validation_raw" if deployed == "raw" else "validation_anchored"
            return min(range(len(values)), key=lambda i: (values[i][key]["transcript_balanced_mse"], i))
        selected = {
            "position_raw_unanchored": candidates_by_family[("position", "raw")][choose("position", "raw", "raw")],
            "position_raw_anchored": candidates_by_family[("position", "raw")][choose("position", "raw", "anchored")],
            "position_centered_anchored": candidates_by_family[("position", "centered")][choose("position", "centered", "anchored")],
            "local_raw_anchored": candidates_by_family[("local", "raw")][choose("local", "raw", "anchored")],
            "local_centered_anchored": candidates_by_family[("local", "centered")][choose("local", "centered", "anchored")],
        }
        states.append({"seed": seed, "selected": selected, "anchor": anchor})
        reports.append({
            "seed": seed, "split_seed": split_seed, "train_ids": train_names, "validation_ids": valid_names,
            "source_mean": anchor, "candidates": report_candidates,
            "selected_alpha": {name: c["alpha"] for name, c in selected.items()},
        })
    return states, reports, total_fits


def evaluate_independent(protocol, states, target, output):
    normalize(target)
    labels = masked_labels(target, sorted(target))
    x = {kind: design(target, labels, kind) for kind in ("position", "local")}
    runs, primary_effects = [], []
    for state in states:
        seed = state["seed"]
        selected = state["selected"]
        anchor = state["anchor"]
        predictions = {"constant": np.full(labels["target"].shape, anchor, dtype=np.float64)}
        raw_new = {}
        for name in ARMS[3:]:
            kind = "position" if name.startswith("position") else "local"
            raw = selected[name]["model"].predict(x[kind])
            raw_new[name] = raw
            predictions[name] = raw if name == "position_raw_unanchored" else recenter(labels, raw, anchor)
        old_path = Path(protocol["frozen_external_predictions"]["prediction_template"].format(seed=seed))
        with np.load(old_path, allow_pickle=False) as old:
            assert all(np.array_equal(old[k], labels[k]) for k in ("record_ids", "offsets", "positions", "target"))
            ribo = old["model_prediction"].astype(np.float64)
            old_ridge = old["ridge_prediction"].astype(np.float64)
        assert np.max(np.abs(predictions["position_raw_unanchored"] - old_ridge)) <= 1e-6
        predictions["ribomimo_raw"] = ribo
        predictions["ribomimo_anchored"] = recenter(labels, ribo, anchor)
        metrics, per = {}, {}
        for arm in ARMS:
            metrics[arm], per[arm] = metric_summary(labels, predictions[arm])
        valid_mse = np.isfinite(per["local_centered_anchored"]["mse"]) & np.isfinite(per["constant"]["mse"])
        mse_effect = per["constant"]["mse"][valid_mse] - per["local_centered_anchored"]["mse"][valid_mse]
        valid_r = np.isfinite(per["local_centered_anchored"]["pearson"]) & np.isfinite(per["position_raw_unanchored"]["pearson"])
        r_effect = per["local_centered_anchored"]["pearson"][valid_r] - per["position_raw_unanchored"]["pearson"][valid_r]
        prediction_path = output / "predictions" / f"subtelny14_seed{seed}.npz"
        prediction_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            prediction_path, **labels,
            **{f"prediction_{arm}": predictions[arm] for arm in ARMS},
            **{f"raw_new_{name}": raw for name, raw in raw_new.items()},
            effect_tb_mse_improvement=mse_effect, effect_mean_pearson_improvement=r_effect,
        )
        model_path = output / "predictions" / f"source_models_seed{seed}.npz"
        arrays = {}
        for name, candidate in selected.items():
            arrays[f"coef_{name}"] = np.asarray(candidate["model"].coef_, dtype=np.float64)
            arrays[f"intercept_{name}"] = np.asarray(candidate["model"].intercept_, dtype=np.float64)
            arrays[f"alpha_{name}"] = np.asarray(candidate["alpha"], dtype=np.float64)
        arrays["source_train_raw_masked_mean"] = np.asarray(anchor, dtype=np.float64)
        np.savez_compressed(model_path, **arrays)
        runs.append({
            "seed": seed, "labels": labels, "metrics": metrics, "per": per,
            "mse_effect": mse_effect, "pearson_effect": r_effect,
            "prediction_path": prediction_path, "model_path": model_path,
        })
        primary_effects.append({
            "tb_mse_improvement_over_constant": float(mse_effect.mean()),
            "mean_pearson_improvement_over_position_raw": float(r_effect.mean()),
        })
    return runs, primary_effects


def inference(effect, seed_boot, seed_perm, count):
    n = len(effect)
    brng = np.random.default_rng(seed_boot)
    prng = np.random.default_rng(seed_perm)
    boot = np.array([effect[brng.integers(0, n, n)].mean() for _ in range(count)])
    perm = np.array([(effect * prng.choice(np.array([-1.0, 1.0]), size=n)).mean() for _ in range(count)])
    observed = float(effect.mean())
    return {
        "n_pairs": int(n), "effect": observed,
        "ci95_low": float(np.quantile(boot, 0.025)), "ci95_high": float(np.quantile(boot, 0.975)),
        "sign_flip_pvalue": float((1 + np.count_nonzero(np.abs(perm) >= abs(observed))) / (count + 1)),
        "resamples": int(count),
    }, boot, perm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--production-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text())
    output = Path(args.output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    output.mkdir(parents=True)
    for role in ("source_matrix", "target_matrix"):
        spec = protocol["studies"][role]
        assert file_hash(spec["path"]) == spec["sha256"], role
    source, source_raw = read_records(protocol["studies"]["source_matrix"]["path"], protocol["studies"]["source"])
    target, target_raw = read_records(protocol["studies"]["target_matrix"]["path"], protocol["studies"]["target"])
    source_cds = {"".join(record["codons"]) for record in source.values()}
    target_cds = {"".join(record["codons"]) for record in target.values()}
    overlap = source_cds & target_cds
    assert len(overlap) == protocol["studies"]["exact_cds_overlap_required"]
    seeds = [protocol["split"]["primary_seed"]] + protocol["split"]["sensitivity_seeds"]
    states, source_reports, total_fits = fit_all_sources(protocol, source, seeds)
    assert total_fits == 48
    runs, point_effects = evaluate_independent(protocol, states, target, output)

    cfg = protocol["evaluation"]
    endpoints, independent_inference = [], {}
    for i, name in enumerate(("tb_mse_improvement_over_constant", "mean_pearson_improvement_over_position_raw")):
        effect = runs[0]["mse_effect" if i == 0 else "pearson_effect"]
        endpoint, boot, perm = inference(effect, cfg["bootstrap"]["seed"], cfg["permutation"]["seed"], cfg["bootstrap"]["resamples"])
        endpoint["name"] = name
        endpoint["sensitivity_effects"] = [values[name] for values in point_effects[1:]]
        endpoints.append(endpoint)
        independent_inference[f"{name}_effect"] = effect
        independent_inference[f"{name}_bootstrap"] = boot
        independent_inference[f"{name}_sign_flip"] = perm
    order = sorted(range(2), key=lambda i: endpoints[i]["sign_flip_pvalue"])
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (2 - rank) * endpoints[i]["sign_flip_pvalue"]))
        endpoints[i]["holm_pvalue"] = running
    for endpoint in endpoints:
        endpoint["primary_pass"] = endpoint["effect"] > 0 and endpoint["ci95_low"] > 0 and endpoint["holm_pvalue"] < 0.05
        endpoint["sensitivity_pass"] = all(x > 0 for x in endpoint["sensitivity_effects"])
        endpoint["gate_pass"] = endpoint["primary_pass"] and endpoint["sensitivity_pass"]
    inference_path = output / "inference" / "primary_inference_arrays.npz"
    inference_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(inference_path, **independent_inference)
    decision = "DUAL_DIAGNOSTIC_PASS_REQUIRES_INDEPENDENT_CONFIRMATION" if all(e["gate_pass"] for e in endpoints) else "CROSS_STUDY_TRANSLATION_TASK_UNRESOLVED_COMPONENT_DIAGNOSIS_REQUIRED"

    # Production target results are read only after all independent fitting/selection/evaluation is complete.
    production_path = Path(args.production_report).resolve()
    production = json.loads(production_path.read_text())
    checks = []
    max_differences = {}
    def check(name, condition, evidence=None):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})
    def close(name, left, right, tolerance=1e-7):
        if left is None or right is None:
            check(name, left is right)
            return
        difference = abs(float(left) - float(right))
        max_differences[name] = difference
        check(name, math.isfinite(difference) and difference <= tolerance, {"difference": difference, "tolerance": tolerance})

    check("protocol_sha", file_hash(protocol_path) == production["protocol_sha256"])
    check("production_frozen_commit_present", len(production["frozen_git_commit"]) == 40)
    check("fit_accounting", total_fits == production["fit_accounting"]["actual_unique_fits"] == 48)
    check("source_raw_count", source_raw == production["source_identity"]["raw_records"])
    check("target_raw_count", target_raw == production["target_identity"]["raw_records"])
    check("source_eligible", len(source) == production["source_identity"]["eligible_records"])
    check("target_eligible", len(target) == production["target_identity"]["eligible_records"])
    check("source_matrix_sha_independent", file_hash(protocol["studies"]["source_matrix"]["path"]) == protocol["studies"]["source_matrix"]["sha256"])
    check("target_matrix_sha_independent", file_hash(protocol["studies"]["target_matrix"]["path"]) == protocol["studies"]["target_matrix"]["sha256"])
    check("exact_cds_disjoint_independent", len(overlap) == 0)
    check("target_access_after_fits", production["target_outcomes_accessed_after_all_source_fits"] is True)
    check("decision_match", decision == production["scientific_decision"], {"independent": decision, "production": production["scientific_decision"]})

    for i, seed in enumerate(seeds):
        independent_source = source_reports[i]
        produced_source = production["source_reports"][i]
        check(f"seed_{seed}_split_seed", independent_source["split_seed"] == produced_source["split"]["split_seed"])
        check(f"seed_{seed}_train_ids", independent_source["train_ids"] == produced_source["split"]["train_ids"])
        check(f"seed_{seed}_valid_ids", independent_source["validation_ids"] == produced_source["split"]["validation_ids"])
        close(f"seed_{seed}_source_mean", independent_source["source_mean"], produced_source["split"]["source_train_raw_masked_mean"], 1e-10)
        for family, candidates in independent_source["candidates"].items():
            for j, candidate in enumerate(candidates):
                produced = produced_source["candidates"][family][j]
                check(f"seed_{seed}_{family}_{j}_alpha", candidate["alpha"] == produced["alpha"])
                for deployment in ("validation_raw", "validation_anchored"):
                    for metric in ("transcript_balanced_mse", "mean_transcript_pearson", "global_mse", "global_r2"):
                        close(f"seed_{seed}_{family}_{j}_{deployment}_{metric}", candidate[deployment][metric], produced[deployment][metric], 1e-6)
        for arm, alpha in independent_source["selected_alpha"].items():
            check(f"seed_{seed}_selected_{arm}", alpha == produced_source["selected_alpha"][arm])

        produced_run = produced_source["target_evaluation"]
        independent_run = runs[i]
        for arm in ARMS:
            for metric in ("transcript_balanced_mse", "mean_transcript_pearson", "mean_transcript_spearman", "global_mse", "global_r2", "global_pearson"):
                close(f"seed_{seed}_{arm}_{metric}", independent_run["metrics"][arm][metric], produced_run["target_metrics"][arm][metric], 1e-6)
        for name, effect in point_effects[i].items():
            close(f"seed_{seed}_{name}", effect, produced_run["primary_effects"][name], 1e-6)

        produced_prediction_path = Path(produced_run["artifacts"]["predictions"]["path"])
        with np.load(produced_prediction_path, allow_pickle=False) as expected, np.load(independent_run["prediction_path"], allow_pickle=False) as actual:
            check(f"seed_{seed}_prediction_array_names", set(expected.files) == set(actual.files))
            for key in expected.files:
                if expected[key].dtype.kind in "USbiu":
                    check(f"seed_{seed}_prediction_{key}_exact", np.array_equal(expected[key], actual[key]))
                else:
                    difference = float(np.max(np.abs(expected[key].astype(np.float64) - actual[key].astype(np.float64)))) if expected[key].size else 0.0
                    max_differences[f"seed_{seed}_prediction_{key}"] = difference
                    check(f"seed_{seed}_prediction_{key}", difference <= 1e-6, {"max_abs": difference})
        produced_model_path = Path(produced_run["artifacts"]["source_models"]["path"])
        with np.load(produced_model_path, allow_pickle=False) as expected, np.load(independent_run["model_path"], allow_pickle=False) as actual:
            check(f"seed_{seed}_model_array_names", set(expected.files) == set(actual.files))
            for key in expected.files:
                difference = float(np.max(np.abs(expected[key].astype(np.float64) - actual[key].astype(np.float64)))) if expected[key].size else 0.0
                max_differences[f"seed_{seed}_model_{key}"] = difference
                check(f"seed_{seed}_model_{key}", difference <= 1e-6, {"max_abs": difference})

    for i, endpoint in enumerate(endpoints):
        produced = production["primary_endpoints"][i]
        check(f"primary_{i}_name", endpoint["name"] == produced["name"])
        for field in ("n_pairs", "resamples"):
            check(f"primary_{i}_{field}", endpoint[field] == produced[field])
        for field in ("effect", "ci95_low", "ci95_high", "sign_flip_pvalue", "holm_pvalue"):
            close(f"primary_{i}_{field}", endpoint[field], produced[field], 1e-6)
        check(f"primary_{i}_sensitivity", np.allclose(endpoint["sensitivity_effects"], produced["sensitivity_effects"], rtol=0, atol=1e-6))
        for field in ("primary_pass", "sensitivity_pass", "gate_pass"):
            check(f"primary_{i}_{field}", endpoint[field] == produced[field])
    produced_inference_path = Path(production["artifacts"]["primary_inference_arrays"]["path"])
    with np.load(produced_inference_path, allow_pickle=False) as expected, np.load(inference_path, allow_pickle=False) as actual:
        check("inference_array_names", set(expected.files) == set(actual.files))
        for key in expected.files:
            difference = float(np.max(np.abs(expected[key].astype(np.float64) - actual[key].astype(np.float64))))
            max_differences[f"inference_{key}"] = difference
            check(f"inference_{key}", difference <= 1e-6, {"max_abs": difference})

    scope = production["scientific_scope"]
    for key in ("functional_untouched_read", "generator_training_authorized", "rk_g1_complete", "sota_claim_authorized", "wet_lab_or_prospective_dbtl"):
        check(f"boundary_{key}", scope[key] is False)
    check("retrospective_not_untouched", scope["retrospective_followup_not_untouched"] is True)
    check("production_engineering_status", production["status"] == "PASS_RK37_PRODUCTION_PENDING_INDEPENDENT")
    check("production_report_nonempty", production_path.stat().st_size > 0)

    passed = sum(c["pass"] for c in checks)
    report = {
        "schema": "a8-rk37-translation-pivot-independent-v1",
        "status": "PASS_RK37_INDEPENDENT" if passed == len(checks) else "FAIL",
        "checks_passed": passed, "checks_total": len(checks), "failures": [c for c in checks if not c["pass"]],
        "checks": checks, "independent_fit_count": total_fits,
        "independent_decision": decision, "independent_primary_endpoints": endpoints,
        "max_differences": max_differences,
        "production_report": {"path": str(production_path), "sha256": file_hash(production_path)},
        "protocol": {"path": str(protocol_path), "sha256": file_hash(protocol_path)},
        "artifacts": {
            "predictions": [{"seed": r["seed"], "path": str(r["prediction_path"]), "sha256": file_hash(r["prediction_path"])} for r in runs],
            "models": [{"seed": r["seed"], "path": str(r["model_path"]), "sha256": file_hash(r["model_path"])} for r in runs],
            "inference": {"path": str(inference_path), "sha256": file_hash(inference_path)},
        },
        "wall_seconds": time.perf_counter() - started,
        "scientific_boundaries": "Independent recomputation does not convert this retrospective Subtelny14 follow-up into untouched confirmation, physical velocity, protein/homology OOD or SOTA.",
    }
    save_json(args.output, report)
    save_json(output / "independent_report.copy.json", report)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "decision": decision, "failures": report["failures"][:5]}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
