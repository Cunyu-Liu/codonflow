#!/usr/bin/env python3
"""Independent full-CV checkpoint, split, inference and metric verification.

This script never imports the production driver. It restores the pinned official
source independently, applies the seven runtime compatibility edits, reconstructs
all gene folds, and performs two forward passes per released production checkpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import traceback

import numpy as np
import torch
from scipy.stats import pearsonr
from sklearn.metrics import average_precision_score, mean_squared_error, r2_score, roc_auc_score

SOURCE_FILES = ("runRiboMIMO.py", "model.py", "utils.py", "getSaliency.py")
REPLACEMENTS = [
    ("model.py", "list_seq = np.array(list_seq)", "list_seq = np.array(list_seq, dtype=object)"),
    ("model.py", "list_density = np.array(list_density)", "list_density = np.array(list_density, dtype=object)"),
    ("model.py", "self.density = np.array(density)", "self.density = np.array(density, dtype=object)"),
    ("model.py", "self.x_input = np.array(x_input)", "self.x_input = np.array(x_input, dtype=object)"),
    ("model.py", "self.density_level = np.array(density_level)", "self.density_level = np.array(density_level, dtype=object)"),
    ("runRiboMIMO.py", "data_pad = np.array(data_pad)", "data_pad = np.array(data_pad, dtype=float)"),
    ("model.py", "x = pack_padded_sequence(x, length, batch_first=True)", "x = pack_padded_sequence(x, length.cpu(), batch_first=True)"),
]


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def restore_runtime(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    for filename in SOURCE_FILES:
        shutil.copy2(source / filename, destination / filename)
    for filename, old, new in REPLACEMENTS:
        path = destination / filename
        text = path.read_text()
        if text.count(old) != 1:
            raise ValueError(f"Compatibility target count != 1: {filename}: {old}")
        path.write_text(text.replace(old, new))


def regression_metrics(pred: np.ndarray, target: np.ndarray) -> dict:
    return {
        "r2": float(r2_score(target, pred)),
        "mse": float(mean_squared_error(target, pred)),
        "pearson": float(pearsonr(target, pred)[0]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    production_path = Path(args.production_report).resolve()
    output = Path(args.output_dir).resolve()
    report_path = Path(args.report).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output must be absent or empty: {output}")
    if report_path.exists():
        raise FileExistsError(f"Refusing to overwrite: {report_path}")
    output.mkdir(parents=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    checks = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError(f"{name}: {detail}")

    try:
        production = json.loads(production_path.read_text())
        # The frozen production protocol is the authoritative dataset field.
        protocol_path = Path(production["protocol"]["protocol_path"])
        protocol = json.loads(protocol_path.read_text())
        dataset = protocol["dataset"]
        num_fold = int(production["protocol"]["num_fold"])
        check("production_status", production["status"].startswith("PASS_COMPLETE_OFFICIAL_1X10FOLD_MAX100"), production["status"])
        check("dataset", dataset == "Mohammad16", dataset)
        check("protocol_identity", sha256(protocol_path) == production["protocol"]["protocol_sha256"], production["protocol"]["protocol_sha256"])
        check("production_report_identity", production_path.is_file(), str(production_path))

        production_root = Path(production["compatibility"]["diff_path"]).parent
        prepare = json.loads((production_root / "prepare_report.json").read_text())
        check("production_driver", sha256(production_root / "driver.py") == prepare["driver_sha256"], prepare["driver_sha256"])
        for name, info in production["artifacts"].items():
            check(f"artifact_hash:{name}", sha256(info["path"]) == info["sha256"], info["sha256"])
        for fold, info in production["official_result"]["checkpoints"].items():
            check(f"checkpoint_hash:{fold}", sha256(info["path"]) == info["sha256"], info["sha256"])

        source = Path(production["source"]["path"]) / "src"
        for filename, expected in production["source"]["file_sha256"].items():
            check(f"official_source:{filename}", sha256(source / filename) == expected, expected)
        independent_src = output / "src"
        restore_runtime(source, independent_src)
        for filename in SOURCE_FILES:
            actual = sha256(independent_src / filename)
            expected = prepare["runtime_file_sha256"][filename]
            check(f"independent_runtime:{filename}", actual == expected and actual == sha256(production_root / "src" / filename), actual)

        matrix = Path(production["matrix"]["path"])
        check("full_matrix", sha256(matrix) == production["matrix"]["sha256"], production["matrix"]["sha256"])
        (output / "data").mkdir()
        independent_matrix = output / "data" / f"{dataset}.txt"
        shutil.copy2(matrix, independent_matrix)
        check("independent_matrix_copy", sha256(independent_matrix) == production["matrix"]["sha256"], production["matrix"]["sha256"])

        previous = protocol["previous_attempt"]
        previous_report = Path(previous["failure_report"])
        previous_data = json.loads(previous_report.read_text())
        check("failed_v1_retained", previous_data["status"] == "FAIL_OFFICIAL_TRAINING" and sha256(previous_report) == previous["failure_report_sha256"], previous["reason"])
        check("failed_v1_log_retained", sha256(previous_data["log"]) == previous_data["log_sha256"], previous_data["log_sha256"])

        sys.path.insert(0, str(independent_src))
        import model as model_module
        import runRiboMIMO as official_module

        np.random.seed(1234)
        torch.manual_seed(1234)
        torch.cuda.manual_seed_all(1234)
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        loader = model_module.DataLoader(str(output) + "/", dataset)
        eligible = list(loader.list_gene)
        check("eligible_count", len(eligible) == production["matrix"]["official_loader_eligible_records"], len(eligible))
        check("eligible_unique", len(set(eligible)) == len(eligible), len(set(eligible)))
        np.random.seed(1234)
        split_seed = int(np.random.randint(0, 1024, 1)[0])
        check("official_split_seed", split_seed == 815, split_seed)
        loader.split_data(split_seed, num_fold, -1.0)
        fold_gene_ids = [[str(gene) for gene in fold] for fold in loader.list_fold]
        check("ten_folds", len(fold_gene_ids) == 10, len(fold_gene_ids))
        flat_test = [gene for fold in fold_gene_ids for gene in fold]
        check("test_gene_union", set(flat_test) == set(eligible) and len(flat_test) == len(eligible), len(flat_test))
        dump_json(output / "independent_folds.json", {"split_seed": split_seed, "folds": fold_gene_ids})

        official_log = Path(production["official_result"]["logging_log"])
        log_text = official_log.read_text()
        import re
        logged_sizes = []
        for block in re.split(r"\[INFO\] \d+/\d+ repeat \d+/\d+ fold", log_text)[1:]:
            train_match = re.search(r"training data size: (\d+)", block)
            valid_match = re.search(r"validation data size: (\d+)", block)
            test_match = re.search(r"test data size: (\d+)", block)
            if train_match and valid_match and test_match:
                logged_sizes.append((int(train_match.group(1)), int(valid_match.group(1)), int(test_match.group(1))))
        check("logged_fold_size_count", len(logged_sizes) == num_fold, len(logged_sizes))

        fold_results = []
        for fold in range(num_fold):
            index_test = loader.list_fold[fold]
            index_train = np.concatenate(loader.list_fold[:fold] + loader.list_fold[fold + 1:])
            num_valid = len(index_train) // 10
            index_valid = index_train[:num_valid]
            index_train = index_train[num_valid:]
            sizes = (len(index_train), len(index_valid), len(index_test))
            check(f"fold_sizes:{fold}", sizes == logged_sizes[fold], {"independent": sizes, "production": logged_sizes[fold]})
            test_set = set(str(gene) for gene in index_test)
            train_set = set(str(gene) for gene in index_train)
            valid_set = set(str(gene) for gene in index_valid)
            check(f"fold_disjoint:{fold}", not (test_set & train_set) and not (test_set & valid_set) and not (train_set & valid_set), sizes)

            net = official_module.RiboMIMOModel.__new__(official_module.RiboMIMOModel)
            net.data = loader
            net.add_nt = True
            net.add_aa = True
            net.batch_size = 16
            net.use_cuda = True
            net.index_train = index_train
            net.index_test = index_test
            net.threshold = "0,2"
            net.get_thresh()
            train_density_values = []
            for train_gene in index_train:
                train_values = np.asarray(loader.dict_density[train_gene]).copy()
                train_values[:5] = 0
                train_values[-4:] = 0
                train_density_values.append(train_values[train_values > 0])
            train_mean = float(np.mean(np.concatenate(train_density_values)))

            def forward_pass() -> dict:
                loader.get_data_pack(index_test, True, True)
                loader.get_data_pack_cls(index_test, net.threshs)
                per_gene = {}
                for batch in range(int(np.ceil(len(index_test) / 16.0))):
                    index = np.array(range(batch * 16, min((batch + 1) * 16, len(index_test))))
                    x_input, length, density, mask_density, level, batch_index = net.get_data_batch(index)
                    pred_reg, pred_cls, _ = net.model(x_input, length)
                    pred_reg_np = pred_reg.detach().cpu().numpy()
                    pred_cls_np = pred_cls.detach().cpu().numpy()
                    density_np = density.detach().cpu().numpy()
                    mask_np = mask_density.detach().cpu().numpy()
                    level_np = level.detach().cpu().numpy()
                    for row, original_index in enumerate(batch_index):
                        gene = str(index_test[int(original_index)])
                        keep = mask_np[row].astype(bool)
                        per_gene[gene] = {
                            "pred": pred_reg_np[row][keep].copy(),
                            "target": density_np[row][keep].copy(),
                            "pred_cls": pred_cls_np[row][keep].copy(),
                            "level": level_np[row][keep].copy(),
                        }
                ordered = [per_gene[str(gene)] for gene in index_test]
                return {
                    "pred": np.concatenate([row["pred"] for row in ordered]).astype(np.float32),
                    "target": np.concatenate([row["target"] for row in ordered]).astype(np.float32),
                    "pred_cls": np.concatenate([row["pred_cls"] for row in ordered]).astype(np.float32),
                    "level": np.concatenate([row["level"] for row in ordered]).astype(np.int64),
                    "counts": np.array([len(row["pred"]) for row in ordered], dtype=np.int64),
                    "genes": np.array([str(gene) for gene in index_test]),
                }

            loader.get_data_pack(index_test, True, True)
            input_dims = int(loader.x_input[0].shape[1])
            checkpoint = Path(production["official_result"]["checkpoints"][str(fold)]["path"])
            net.model = model_module.RiboMIMO(input_dims, 256, 2, num_class=3)
            state = torch.load(checkpoint, map_location="cpu", weights_only=True)
            net.model.load_state_dict(state, strict=True)
            net.model = net.model.cuda().eval()
            with torch.no_grad():
                first = forward_pass()
                second = forward_pass()
            prediction_delta = float(np.max(np.abs(first["pred"] - second["pred"]))) if len(first["pred"]) else 0.0
            class_delta = float(np.max(np.abs(first["pred_cls"] - second["pred_cls"]))) if len(first["pred_cls"]) else 0.0
            target_delta = float(np.max(np.abs(first["target"] - second["target"]))) if len(first["target"]) else 0.0
            check(f"second_forward:{fold}", prediction_delta == 0.0 and class_delta == 0.0 and target_delta == 0.0, {"pred": prediction_delta, "class": class_delta, "target": target_delta})

            metrics = regression_metrics(first["pred"], first["target"])
            baseline_pred = np.full(len(first["target"]), train_mean, dtype=np.float32)
            baseline_metrics = {
                "train_mean": train_mean,
                "r2": float(r2_score(first["target"], baseline_pred)),
                "mse": float(mean_squared_error(first["target"], baseline_pred)),
            }
            onehot = np.eye(3)[first["level"]]
            metrics["auc"] = float(roc_auc_score(onehot, first["pred_cls"]))
            metrics["aupr"] = float(average_precision_score(onehot, first["pred_cls"]))
            production_fold = production["official_result"]["folds"][fold]
            production_metrics = production_fold["test_at_best_validation"]
            rounded_match = all(round(metrics[key], 6) == round(float(production_metrics[key]), 6) for key in ("r2", "mse", "pearson", "auc", "aupr"))
            deltas = {key: abs(metrics[key] - float(production_metrics[key])) for key in ("r2", "mse", "pearson", "auc", "aupr")}
            check(f"independent_metrics:{fold}", rounded_match, {"metrics": metrics, "production": production_metrics, "deltas": deltas})
            prediction_file = output / f"fold_{fold}_test_predictions.npz"
            np.savez_compressed(
                prediction_file,
                pred=first["pred"], target=first["target"], pred_cls=first["pred_cls"],
                level=first["level"], codon_counts=first["counts"], gene_ids=first["genes"],
                constant_train_mean_pred=baseline_pred,
            )
            fold_results.append({
                "fold": fold, "best_epoch": production_fold["best_epoch"], "epochs_logged": production_fold["epochs_logged"],
                "sizes": {"train": sizes[0], "valid": sizes[1], "test": sizes[2]},
                "train_log_thresholds": net.threshs,
                "valid_masked_codons": int(len(first["pred"])),
                "metrics": metrics, "constant_train_mean_baseline": baseline_metrics,
                "production_logged_metrics": production_metrics,
                "metric_deltas": deltas, "second_forward_max_abs_delta": prediction_delta,
                "second_forward_class_max_abs_delta": class_delta,
                "prediction_file": str(prediction_file), "prediction_file_sha256": sha256(prediction_file),
                "checkpoint_sha256": sha256(checkpoint),
            })
            print(json.dumps({"fold": fold, "metrics": metrics, "second_forward_delta": prediction_delta}), flush=True)
            del net.model
            torch.cuda.empty_cache()

        independent_aggregate = {
            "r2_mean": float(np.mean([row["metrics"]["r2"] for row in fold_results])),
            "r2_std": float(np.std([row["metrics"]["r2"] for row in fold_results])),
            "mse_mean": float(np.mean([row["metrics"]["mse"] for row in fold_results])),
            "mse_std": float(np.std([row["metrics"]["mse"] for row in fold_results])),
            "pearson_mean": float(np.mean([row["metrics"]["pearson"] for row in fold_results])),
            "pearson_std": float(np.std([row["metrics"]["pearson"] for row in fold_results])),
        }
        production_aggregate = production["official_result"]["aggregate"]
        baseline_aggregate = {
            "r2_mean": float(np.mean([row["constant_train_mean_baseline"]["r2"] for row in fold_results])),
            "r2_std": float(np.std([row["constant_train_mean_baseline"]["r2"] for row in fold_results])),
            "mse_mean": float(np.mean([row["constant_train_mean_baseline"]["mse"] for row in fold_results])),
            "mse_std": float(np.std([row["constant_train_mean_baseline"]["mse"] for row in fold_results])),
        }
        aggregate_deltas = {key: abs(independent_aggregate[key] - production_aggregate[key]) for key in independent_aggregate}
        aggregate_match = all(round(independent_aggregate[key], 6) == round(production_aggregate[key], 6) for key in independent_aggregate)
        check("independent_aggregate", aggregate_match, {"independent": independent_aggregate, "production": production_aggregate, "deltas": aggregate_deltas})
        for boundary in ("homology_aware_split", "protein_ood", "study_ood", "functional_ood", "main_baseline_comparison", "publication_metrics_reproduced", "sota_claim"):
            check(f"scope:{boundary}", production[boundary] is False, production[boundary])

        report = {
            "schema_version": "a8-rk05-ribomimo-full-independent-v1",
            "status": "PASS",
            "production_report": str(production_path), "production_report_sha256": sha256(production_path),
            "production_root": str(production_root), "output_dir": str(output),
            "dataset": dataset, "split_seed": split_seed,
            "num_fold": num_fold, "fold_results": fold_results,
            "independent_aggregate": independent_aggregate,
            "constant_train_mean_baseline_aggregate": baseline_aggregate,
            "production_aggregate": production_aggregate,
            "aggregate_deltas": aggregate_deltas,
            "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks),
            "production_driver_imported": False,
            "full_training_rerun": False,
            "two_forward_passes_per_fold": True,
            "homology_aware_split": False, "protein_ood": False, "study_ood": False,
            "functional_ood": False, "main_baseline_comparison": False,
            "publication_metrics_reproduced": False, "sota_claim": False,
        }
        dump_json(report_path, report)
        dump_json(output / "independent_report.copy.json", report)
        print(json.dumps({"status": "PASS", "checks": f"{len(checks)}/{len(checks)}", "report": str(report_path), "report_sha256": sha256(report_path)}, indent=2))
    except Exception:
        failure = {
            "schema_version": "a8-rk05-ribomimo-full-independent-v1",
            "status": "FAIL",
            "production_report": str(production_path),
            "output_dir": str(output),
            "checks": checks,
            "traceback": traceback.format_exc(),
        }
        failure_path = report_path.with_name(report_path.stem + "_failed.json")
        dump_json(failure_path, failure)
        print(traceback.format_exc(), file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
