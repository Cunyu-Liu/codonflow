#!/usr/bin/env python3
"""Run the frozen RK23 Boel Delta G_UH protein-OOD increment protocol."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.metadata
import io
import json
import math
import os
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr, rankdata, spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

from scripts.a8_rk07_proxy_evaluate import fit_multinomial_logistic, logistic_expected_score


INPUT_HASH_KEYS = {
    "split_file": "split_sha256",
    "feature_file": "feature_file_sha256",
    "feature_summary": "feature_summary_sha256",
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def gc3_fraction(cds: str) -> float:
    seq = "".join(cds.upper().split())
    if len(seq) < 6 or len(seq) % 3:
        raise ValueError("invalid CDS for GC3")
    codons = [seq[i:i + 3] for i in range(0, len(seq), 3)]
    if codons[-1] not in {"TAA", "TAG", "TGA"}:
        raise ValueError("terminal stop required")
    positions = [c[2] for c in codons[:-1]]
    return float(np.mean([b in "GC" for b in positions]))


def feature_matrix(rows: list[dict], names: list[str]) -> np.ndarray:
    columns = []
    for name in names:
        if name == "log_length_nt":
            columns.append(np.log(np.asarray([r["length_nt"] for r in rows], dtype=float)))
        else:
            columns.append(np.asarray([r[name] for r in rows], dtype=float))
    matrix = np.column_stack(columns)
    if not np.isfinite(matrix).all():
        raise ValueError(f"non-finite features: {names}")
    return matrix


def load_data(protocol: dict, splits: list[str]) -> dict[str, list[dict]]:
    feature_path = protocol["feature_file"]
    wanted = {}
    numeric = {"length_nt", "gc_fraction", "cai", "full_cds_mfe_per_nt", "mfe_5prime_48_kcal_mol", "source_Gz48v"}
    with gzip.open(feature_path, "rt", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            split = raw["split_assignment"]
            if split not in splits:
                continue
            key = (raw["source_row"], raw["construct_id"])
            if key in wanted:
                raise ValueError(f"duplicate feature identity: {key}")
            row = dict(raw)
            for name in numeric:
                row[name] = float(row[name])
            wanted[key] = row
    found = set()
    output = {s: [] for s in splits}
    with open(protocol["split_file"], newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            if raw["source_id"] != protocol["source_id"]:
                continue
            split = raw["split_assignment"]
            if split == protocol["forbidden_split"]:
                raise ValueError("forbidden functional_untouched row encountered")
            if split not in splits:
                continue
            key = (raw["source_row"], raw["construct_id"])
            if key not in wanted:
                raise ValueError(f"unexpected split identity: {key}")
            row = wanted[key]
            cds = "".join(raw["cds"].upper().split())
            if hashlib.sha256(cds.encode()).hexdigest() != row["cds_sha256"]:
                raise ValueError(f"CDS hash mismatch: {key}")
            if row["operational_protein_cluster"] != raw["operational_protein_cluster"]:
                raise ValueError(f"cluster mismatch: {key}")
            source = json.loads(raw["features_json"])
            if float(source["Gz48v"]) != row["source_Gz48v"]:
                raise ValueError(f"Gz48v mismatch: {key}")
            label = float(raw[protocol["label_field"]])
            if label not in protocol["label_classes"]:
                raise ValueError(f"unexpected label: {label}")
            row["label"] = label
            row["gc3_fraction"] = gc3_fraction(cds)
            output[split].append(row)
            found.add(key)
    if found != set(wanted):
        raise ValueError("feature/split identities do not match")
    for split, rows in output.items():
        rows.sort(key=lambda r: int(r["source_row"]))
        if len(rows) != int(protocol["expected_rows"][split]):
            raise ValueError(f"{split} row count mismatch")
    return output


def regression_metrics(y: np.ndarray, prediction: np.ndarray, source_rows: np.ndarray, top_fraction: float, positive_label: int) -> dict:
    mse = float(np.mean((y - prediction) ** 2))
    k = max(1, int(math.ceil(top_fraction * len(y))))
    order = np.lexsort((source_rows.astype(int), -prediction))[:k]
    positive = y == positive_label
    base_rate = float(np.mean(positive))
    if base_rate <= 0:
        raise ValueError("no positive labels")
    values = {
        "spearman": float(spearmanr(y, prediction).statistic),
        "pearson": float(pearsonr(y, prediction).statistic),
        "mse": mse,
        "rmse": float(math.sqrt(mse)),
        "mae": float(np.mean(np.abs(y - prediction))),
        "top10_e5_enrichment": float(np.mean(positive[order]) / base_rate),
        "n": int(len(y)),
    }
    if not all(math.isfinite(float(v)) for v in values.values()):
        raise ValueError("non-finite metrics")
    return values


def fast_spearman(y: np.ndarray, prediction: np.ndarray) -> float:
    yr = rankdata(y)
    pr = rankdata(prediction)
    yc = yr - yr.mean()
    pc = pr - pr.mean()
    denominator = math.sqrt(float(np.dot(yc, yc) * np.dot(pc, pc)))
    if denominator == 0:
        raise ValueError("undefined bootstrap Spearman")
    return float(np.dot(yc, pc) / denominator)


def fit_models(train_rows: list[dict], protocol: dict) -> dict:
    models = {}
    y = np.asarray([r["label"] for r in train_rows], dtype=float)
    classes = np.asarray(protocol["label_classes"], dtype=int)
    for contrast_name in ("primary_contrast", "secondary_descriptive_contrast"):
        cfg = protocol[contrast_name]
        role_models = {}
        for role in ("base", "augmented"):
            names = cfg[f"{role}_features"]
            x = feature_matrix(train_rows, names)
            logistic = fit_multinomial_logistic(x, y, classes, protocol["models"]["logistic"]["l2"], protocol["models"]["logistic"]["max_iter"])
            logistic["feature_names"] = names
            hcfg = protocol["models"]["histgb"]
            hist = HistGradientBoostingRegressor(
                learning_rate=hcfg["learning_rate"], max_iter=hcfg["max_iter"],
                max_leaf_nodes=hcfg["max_leaf_nodes"], min_samples_leaf=hcfg["min_samples_leaf"],
                l2_regularization=hcfg["l2_regularization"], early_stopping=hcfg["early_stopping"],
                random_state=hcfg["random_state"],
            )
            hist.fit(x, y)
            role_models[role] = {"feature_names": names, "logistic": logistic, "histgb": hist}
        models[contrast_name] = role_models
    return models


def predict_contrast(models: dict, rows: list[dict], contrast_name: str) -> dict:
    output = {}
    for role in ("base", "augmented"):
        entry = models[contrast_name][role]
        x = feature_matrix(rows, entry["feature_names"])
        for model_name in ("logistic", "histgb"):
            model = entry[model_name]
            prediction = logistic_expected_score(model, x) if model_name == "logistic" else model.predict(x)
            output[f"{contrast_name}_{role}_{model_name}"] = np.asarray(prediction, dtype=float)
    return output


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=p_values.get)
    running = 0.0
    result = {}
    for rank, key in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * p_values[key]))
        result[key] = running
    return result


def resample_primary(y: np.ndarray, predictions: dict, clusters: np.ndarray, protocol: dict, split_index: int, output_npz: str | Path) -> dict:
    contrast = protocol["primary_contrast"]["name"]
    b = int(protocol["bootstrap"]["replicates"])
    if b != int(protocol["permutation"]["replicates"]):
        raise ValueError("paired arrays require equal replicate counts")
    group_names = sorted(set(clusters))
    group_indices = [np.flatnonzero(clusters == g) for g in group_names]
    models = ("logistic", "histgb")
    metric_names = ("delta_spearman", "mse_improvement")
    boot_effects = np.zeros((b, 2, 2), dtype=float)
    perm_effects = np.zeros((b, 2, 2), dtype=float)
    boot_rng = np.random.default_rng(int(protocol["bootstrap"]["seed"]) + split_index)
    perm_rng = np.random.default_rng(int(protocol["permutation"]["seed"]) + split_index)
    for replicate in range(b):
        sampled = boot_rng.integers(0, len(group_indices), size=len(group_indices))
        idx = np.concatenate([group_indices[i] for i in sampled])
        swap = perm_rng.random(len(group_indices)) < 0.5
        for mi, model_name in enumerate(models):
            base = predictions[f"{contrast}_base_{model_name}"]
            augmented = predictions[f"{contrast}_augmented_{model_name}"]
            b0 = base[idx]
            a0 = augmented[idx]
            boot_effects[replicate, mi, 0] = fast_spearman(y[idx], a0) - fast_spearman(y[idx], b0)
            boot_effects[replicate, mi, 1] = np.mean((y[idx] - b0) ** 2) - np.mean((y[idx] - a0) ** 2)
            pb = base.copy()
            pa = augmented.copy()
            for selected, indices in zip(swap, group_indices):
                if selected:
                    pb[indices], pa[indices] = augmented[indices], base[indices]
            perm_effects[replicate, mi, 0] = fast_spearman(y, pa) - fast_spearman(y, pb)
            perm_effects[replicate, mi, 1] = np.mean((y - pb) ** 2) - np.mean((y - pa) ** 2)
    point = {}
    raw_p = {}
    report = {}
    for mi, model_name in enumerate(models):
        base = predictions[f"{contrast}_base_{model_name}"]
        augmented = predictions[f"{contrast}_augmented_{model_name}"]
        point_values = [
            float(spearmanr(y, augmented).statistic - spearmanr(y, base).statistic),
            float(np.mean((y - base) ** 2) - np.mean((y - augmented) ** 2)),
        ]
        for qi, metric_name in enumerate(metric_names):
            key = f"{model_name}_{metric_name}"
            effect = float(point_values[qi])
            point[key] = effect
            ci = np.percentile(boot_effects[:, mi, qi], [2.5, 97.5])
            p = float((1 + np.sum(np.abs(perm_effects[:, mi, qi]) >= abs(effect))) / (b + 1))
            raw_p[key] = p
            report[key] = {
                "effect": effect,
                "ci95": [float(ci[0]), float(ci[1])],
                "p_raw": p,
                "passes_direction": bool(effect > 0 and ci[0] > 0),
            }
    adjusted = holm_adjust(raw_p)
    for key in report:
        report[key]["p_holm"] = adjusted[key]
        report[key]["passes_all"] = bool(report[key]["passes_direction"] and adjusted[key] < 0.05)
    output_npz = Path(output_npz)
    output_npz.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_npz.with_name(output_npz.name + f".tmp.{os.getpid()}.npz")
    np.savez_compressed(tmp, bootstrap_effects=boot_effects, permutation_effects=perm_effects, models=np.asarray(models), metrics=np.asarray(metric_names))
    os.replace(tmp, output_npz)
    return {
        "comparisons": report,
        "all_four_pass": bool(all(v["passes_all"] for v in report.values())),
        "bootstrap_replicates": b,
        "permutation_replicates": b,
        "clusters": len(group_names),
        "resampling_file": str(output_npz.resolve()),
        "resampling_sha256": sha256_file(output_npz),
    }


def evaluate_split(models: dict, rows: list[dict], protocol: dict, split: str, split_index: int, resampling_path: str | Path | None, run_inference: bool = True) -> tuple[dict, dict]:
    y = np.asarray([r["label"] for r in rows], dtype=float)
    source_rows = np.asarray([r["source_row"] for r in rows], dtype=int)
    clusters = np.asarray([r["operational_protein_cluster"] for r in rows])
    predictions = {}
    for contrast_name in ("primary_contrast", "secondary_descriptive_contrast"):
        predictions.update(predict_contrast(models, rows, contrast_name))
    metrics = {}
    for name, prediction in predictions.items():
        metrics[name] = regression_metrics(y, prediction, source_rows, protocol["top_k_fraction"], protocol["top_k_positive_label"])
    paired = {}
    for contrast_name in ("primary_contrast", "secondary_descriptive_contrast"):
        for model_name in ("logistic", "histgb"):
            base = metrics[f"{contrast_name}_base_{model_name}"]
            augmented = metrics[f"{contrast_name}_augmented_{model_name}"]
            paired[f"{contrast_name}_{model_name}"] = {
                "delta_spearman": augmented["spearman"] - base["spearman"],
                "mse_improvement": base["mse"] - augmented["mse"],
                "delta_pearson": augmented["pearson"] - base["pearson"],
                "delta_top10_e5_enrichment": augmented["top10_e5_enrichment"] - base["top10_e5_enrichment"],
            }
    inference = None
    if split != "train" and run_inference:
        inference = resample_primary(y, predictions, clusters, protocol, split_index, resampling_path)
    return {"n": len(rows), "metrics": metrics, "paired_effects": paired, "primary_inference": inference}, predictions


def atomic_predictions(path: str | Path, datasets: dict[str, list[dict]], predictions: dict[str, dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["split_assignment", "source_row", "construct_id", "operational_protein_cluster", "label"] + sorted(next(iter(predictions.values())).keys())
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                for split, rows in datasets.items():
                    for i, row in enumerate(rows):
                        out = {k: row[k] for k in fields[:5]}
                        out.update({name: float(values[i]) for name, values in predictions[split].items()})
                        writer.writerow(out)
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--evaluation-splits", nargs="+", default=["train", "dev"])
    parser.add_argument("--frozen-test-confirmation", action="store_true")
    parser.add_argument("--dev-result", default=None)
    parser.add_argument("--model-artifact", required=True)
    parser.add_argument("--output-result", required=True)
    parser.add_argument("--output-predictions", required=True)
    parser.add_argument("--resampling-prefix", required=True)
    args = parser.parse_args()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text())
    if args.evaluation_splits[0] != "train" or args.evaluation_splits not in (["train", "dev"], ["train", "dev", "test"]):
        raise ValueError("evaluation splits must be train/dev or train/dev/test")
    test_requested = "test" in args.evaluation_splits
    if test_requested != args.frozen_test_confirmation:
        raise ValueError("test and --frozen-test-confirmation must agree")
    for key, digest_key in INPUT_HASH_KEYS.items():
        if sha256_file(protocol[key]) != protocol[digest_key]:
            raise ValueError(f"input hash mismatch: {key}")
    for key in ("source_data_fig5_file", "optimized_genes_file"):
        if sha256_file(protocol["optimized_construct_boundary"][key]) != protocol["optimized_construct_boundary"][key.replace("_file", "_sha256")]:
            raise ValueError(f"raw workbook hash mismatch: {key}")
    datasets = load_data(protocol, args.evaluation_splits)
    model_path = Path(args.model_artifact).resolve()
    if not test_requested:
        models = fit_models(datasets["train"], protocol)
        payload = {"protocol_sha256": sha256_file(protocol_path), "feature_file_sha256": sha256_file(protocol["feature_file"]), "models": models}
        model_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = model_path.with_name(model_path.name + f".tmp.{os.getpid()}")
        with open(tmp, "wb") as handle:
            pickle.dump(payload, handle, protocol=4)
        os.replace(tmp, model_path)
        dev_result = None
    else:
        if not args.dev_result:
            raise ValueError("test requires --dev-result")
        dev_result_path = Path(args.dev_result).resolve()
        dev_result = json.loads(dev_result_path.read_text())
        if dev_result["protocol_sha256"] != sha256_file(protocol_path):
            raise ValueError("dev protocol hash mismatch")
        if dev_result["model_artifact_sha256"] != sha256_file(model_path):
            raise ValueError("model artifact hash mismatch")
        with open(model_path, "rb") as handle:
            payload = pickle.load(handle)
        if payload["protocol_sha256"] != sha256_file(protocol_path):
            raise ValueError("model protocol mismatch")
        models = payload["models"]
    results = {}
    predictions = {}
    for split_index, split in enumerate(args.evaluation_splits):
        frozen_dev_replay = bool(test_requested and split == "dev")
        resampling = None if split == "train" or frozen_dev_replay else Path(f"{args.resampling_prefix}_{split}.npz")
        results[split], predictions[split] = evaluate_split(models, datasets[split], protocol, split, split_index, resampling, run_inference=not frozen_dev_replay)
        if frozen_dev_replay:
            frozen_dev = dev_result["split_results"]["dev"]
            for key in ("n", "metrics", "paired_effects"):
                if results["dev"][key] != frozen_dev[key]:
                    raise RuntimeError(f"frozen dev results do not reproduce exactly: {key}; test aborted")
            results["dev"] = frozen_dev
            for name, values in predictions["dev"].items():
                old = dev_result["dev_prediction_sha256_by_name"][name]
                current = hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()
                if old != current:
                    raise RuntimeError(f"frozen dev prediction mismatch: {name}")
    atomic_predictions(args.output_predictions, datasets, predictions)
    status = "FROZEN_TEST_EVALUATED_PENDING_INDEPENDENT_VERIFICATION" if test_requested else "DEV_ONLY_NO_TEST_ACCESS"
    result = {
        "status": status,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256_file(protocol_path),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "rk07_evaluate_dependency_sha256": sha256_file(Path(sys.modules["scripts.a8_rk07_proxy_evaluate"].__file__).resolve()),
        "command": [sys.executable, "-m", "scripts.a8_rk23_run_boel_uh", *sys.argv[1:]],
        "evaluation_splits": args.evaluation_splits,
        "test_metrics_computed": test_requested,
        "test_reused_not_globally_untouched": True,
        "functional_untouched_accessed": False,
        "train_fit_only": True,
        "model_artifact": str(model_path),
        "model_artifact_sha256": sha256_file(model_path),
        "dev_result": str(Path(args.dev_result).resolve()) if args.dev_result else None,
        "dev_result_sha256": sha256_file(args.dev_result) if args.dev_result else None,
        "split_results": results,
        "dev_prediction_sha256_by_name": {name: hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest() for name, values in predictions.get("dev", {}).items()},
        "prediction_file": str(Path(args.output_predictions).resolve()),
        "prediction_file_sha256": sha256_file(args.output_predictions),
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "scipy": importlib.metadata.version("scipy"), "sklearn": importlib.metadata.version("scikit-learn")},
        "scientific_scope": protocol["scientific_scope"],
        "gate": protocol["gate"],
        "rk_g1": False,
        "generator_training_authorized": False,
        "functional_untouched_confirmed": False,
        "prohibited_claims": protocol["prohibited_claims"],
    }
    atomic_json(args.output_result, result)
    compact = {"status": status, "model_artifact_sha256": result["model_artifact_sha256"], "splits": {}}
    for split, value in results.items():
        compact["splits"][split] = {"paired_effects": value["paired_effects"], "primary_inference": value["primary_inference"]}
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
