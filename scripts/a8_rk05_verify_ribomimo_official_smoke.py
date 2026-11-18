#!/usr/bin/env python3
"""Independent RiboMIMO bounded-smoke re-execution and checkpoint evaluation.

The production module is never imported. Selection, compatibility edits,
training, fold reconstruction and metric computation are implemented separately.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import numpy as np
from scipy.stats import pearsonr
from sklearn.metrics import mean_squared_error, r2_score
import torch

COMMIT = "094c693d4df45f4b29f5a3209b31c452a39092a5"
DATASET = "RiboBounded20"
FILES = ("runRiboMIMO.py", "model.py", "utils.py", "getSaliency.py")
EDITS = [
    ("model.py", "list_seq = np.array(list_seq)", "list_seq = np.array(list_seq, dtype=object)"),
    ("model.py", "list_density = np.array(list_density)", "list_density = np.array(list_density, dtype=object)"),
    ("model.py", "self.density = np.array(density)", "self.density = np.array(density, dtype=object)"),
    ("model.py", "self.x_input = np.array(x_input)", "self.x_input = np.array(x_input, dtype=object)"),
    ("model.py", "self.density_level = np.array(density_level)", "self.density_level = np.array(density_level, dtype=object)"),
    ("runRiboMIMO.py", "data_pad = np.array(data_pad)", "data_pad = np.array(data_pad, dtype=float)"),
]


def sha(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_json(path: str | Path, value: object) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def independent_subset(matrix: Path, expected_count: int = 20) -> tuple[list[dict], bytes]:
    lines = matrix.read_text().splitlines()
    assert len(lines) % 3 == 0
    records = []
    for source_index in range(len(lines) // 3):
        h, s, c = lines[3 * source_index:3 * source_index + 3]
        name = h[1:].split()[0]
        codons = s.split()
        counts = [float(x) for x in c.split()]
        records.append((source_index, name, codons, counts, h, s, c))
    name_counts = Counter(row[1] for row in records)
    candidates = []
    for source_index, name, codons, counts, h, s, c in records:
        if name_counts[name] != 1 or len(codons) < 15 or len(codons) != len(counts):
            continue
        if any(len(codon) != 3 or set(codon) - set("ATCG") for codon in codons):
            continue
        if not all(math.isfinite(x) and x >= 0 for x in counts):
            continue
        positives = [x for x in counts if x > 0.5]
        coverage = sum(x > 0.5 for x in counts) / len(counts)
        if not positives or coverage <= 0.6:
            continue
        candidates.append({
            "record_id": name, "source_index": source_index, "n_codons": len(codons),
            "coverage": coverage, "mean_positive_count": sum(positives) / len(positives),
            "_lines": (h, s, c),
        })
    candidates.sort(key=lambda row: (row["n_codons"], row["record_id"], row["source_index"]))
    chosen = candidates[:expected_count]
    assert len(chosen) == expected_count
    payload = ("\n".join(line for row in chosen for line in row["_lines"]) + "\n").encode()
    for row in chosen:
        del row["_lines"]
    return chosen, payload


def build_runtime(source: Path, runtime: Path) -> None:
    runtime.mkdir(parents=True)
    for name in FILES:
        shutil.copy2(source / name, runtime / name)
    for name, old, new in EDITS:
        path = runtime / name
        text = path.read_text()
        assert text.count(old) == 1, (name, old, text.count(old))
        path.write_text(text.replace(old, new))


def aggregate(log: Path) -> list[float]:
    match = re.findall(
        r"RiboMIMO, r2\s+([-+0-9.eE]+)\s+([-+0-9.eE]+),\s*"
        r"mse\s+([-+0-9.eE]+)\s+([-+0-9.eE]+),\s*"
        r"corr\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", log.read_text())
    assert match
    return [float(x) for x in match[-1]]


def fold_best_from_log(log: Path, folds: int = 2) -> list[dict]:
    """Reconstruct official best-validation checkpoint test rows from log events."""
    pattern = re.compile(
        r"Fold 1x(\d+)/1x2, (Valid|Test), r2\s+([-+0-9.eE]+),\s*"
        r"mse\s+([-+0-9.eE]+),\s*corr\s+([-+0-9.eE]+)")
    best = {fold: -np.inf for fold in range(folds)}
    improved = {fold: False for fold in range(folds)}
    selected = {fold: None for fold in range(folds)}
    for line in log.read_text().splitlines():
        match = pattern.search(line)
        if not match:
            continue
        fold = int(match.group(1)) - 1
        kind = match.group(2)
        values = [float(match.group(i)) for i in (3, 4, 5)]
        if kind == "Valid":
            improved[fold] = values[0] > best[fold]
            if improved[fold]:
                best[fold] = values[0]
        elif improved[fold]:
            selected[fold] = {"r2": values[0], "mse": values[1], "pearson": values[2]}
            improved[fold] = False
    assert all(selected[fold] is not None for fold in range(folds)), selected
    return [selected[fold] for fold in range(folds)]


def evaluate_checkpoints(runtime_src: Path, runtime_root: Path, checkpoints: dict, seed: int) -> tuple[list[dict], int]:
    """Load fixed official modules and recompute each held-out fold from checkpoints."""
    sys.path.insert(0, str(runtime_src))
    for name in ("runRiboMIMO", "model", "utils"):
        if name in sys.modules:
            del sys.modules[name]
    official = importlib.import_module("runRiboMIMO")
    loader = official.DataLoader(str(runtime_root) + "/", DATASET)
    np.random.seed(seed)
    repeat_seeds = np.random.randint(0, 1024, 1)
    loader.split_data(repeat_seeds[0], 2, -1)
    rows = []
    parameter_count = None
    for fold in range(2):
        index_test = loader.list_fold[fold]
        index_train = np.concatenate(loader.list_fold[:fold] + loader.list_fold[fold + 1:])
        num_valid = len(index_train) // 10
        index_valid = index_train[:num_valid]
        index_train = index_train[num_valid:]
        assert len(index_valid) == 1 and len(index_train) == 9 and len(index_test) == 10
        helper = object.__new__(official.RiboMIMOModel)
        helper.data = loader
        helper.use_cuda = False
        helper.threshold = "0,2"
        helper.index_train = index_train
        helper.get_thresh()
        loader.get_data_pack(index_test, True, True)
        loader.get_data_pack_cls(index_test, helper.threshs)
        model = official.RiboMIMO(97, 256, 2, num_class=3)
        state = torch.load(checkpoints[str(fold)]["path"], map_location="cpu", weights_only=True)
        model.load_state_dict(state)
        model.eval()
        if parameter_count is None:
            parameter_count = sum(x.numel() for x in state.values())
        labels, predictions = [], []
        with torch.no_grad():
            for start in range(0, len(index_test), 4):
                indices = np.arange(start, min(start + 4, len(index_test)))
                x, length, density, mask, _, _ = helper.get_data_batch(indices)
                pred, _, _ = model(x, length)
                labels.extend(density.masked_select(mask).cpu().numpy())
                predictions.extend(pred.masked_select(mask).cpu().numpy())
        rows.append({
            "fold": fold,
            "repeat_seed": int(repeat_seeds[0]),
            "test_genes": list(index_test),
            "valid_genes": list(index_valid),
            "train_genes": list(index_train),
            "positive_masked_positions": len(labels),
            "r2": float(r2_score(labels, predictions)),
            "mse": float(mean_squared_error(labels, predictions)),
            "pearson": float(pearsonr(labels, predictions)[0]),
        })
    return rows, parameter_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--production-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    prod = json.loads(Path(args.production_report).read_text())
    prod_root = Path(prod["subset"]["path"]).parent
    source = Path(args.source_dir).resolve() / "src"
    matrix = Path(args.matrix).resolve()
    checks = []
    numeric_deltas = [0.0]

    def check(name: str, passed: bool, detail: object = "") -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    check("fixed_source_identity", prod["source"]["commit"] == COMMIT and all(sha(source / n) == h for n, h in prod["source"]["file_sha256"].items()))
    check("matrix_identity", sha(matrix) == prod["matrix"]["sha256"])
    selected, subset_bytes = independent_subset(matrix)
    subset_path = output / "input_subset.txt"
    subset_path.write_bytes(subset_bytes)
    check("independent_selection_and_subset_hash", selected == prod["subset"]["records"] and sha(subset_path) == prod["subset"]["sha256"], {"records": len(selected)})
    for label, error_token in (("official_unmodified", "inhomogeneous"), ("ragged_only", "numpy.object_")):
        run = prod["runs"][label]
        text = Path(run["log"]).read_text()
        check(label + "_failure_retained", run["returncode"] != 0 and error_token.lower() in text.lower(), text[-500:])
    runtime = output / "official_bounded" / "src"
    build_runtime(source, runtime)
    runtime_matches = all(sha(runtime / name) == sha(prod_root / "official_bounded" / "src" / name) for name in FILES)
    check("six_compatibility_edits_reproduced", len(prod["compatibility"]["replacements_path"]) > 0 and len(json.loads(Path(prod["compatibility"]["replacements_path"]).read_text())) == 6 and runtime_matches)
    data_dir = output / "official_bounded" / "data"
    data_dir.mkdir(parents=True)
    shutil.copy2(subset_path, data_dir / f"{DATASET}.txt")
    driver = runtime / "bounded_seeded_driver.py"
    driver.write_text(
        "import os, runpy, sys, json\nfrom pathlib import Path\nimport numpy as np\nimport torch\n"
        "seed=int(os.environ['RIBOMIMO_SEED'])\nnp.random.seed(seed)\ntorch.manual_seed(seed)\n"
        "torch.use_deterministic_algorithms(True)\ntorch.set_num_threads(1)\n"
        "sys.path.insert(0,os.getcwd())\nrunpy.run_path('runRiboMIMO.py',run_name='__main__')\n"
        "Path('runtime_environment.json').write_text(json.dumps({'device':'cpu','torch_num_threads':torch.get_num_threads(),'deterministic_algorithms_in_driver':torch.are_deterministic_algorithms_enabled(),'gpu_visible_to_training':torch.cuda.device_count()>0,'cuda_visible_devices_after_official_args':os.environ.get('CUDA_VISIBLE_DEVICES')},indent=2)+'\\n')\n"
    )
    seed = int(prod["protocol"]["seed"])
    command = [sys.executable, "-u", driver.name, "--add_nt", "--add_aa", "--dataset", DATASET,
               "--gpu", "-1", "--seed", str(seed), "--num_repeat", "1", "--num_fold", "2",
               "--batch_size", "4", "--max_epoch", "2", "--early_stop", "2", "--sim", "-1"]
    env = os.environ.copy()
    env.update({"CUDA_VISIBLE_DEVICES": "", "PYTHONHASHSEED": str(seed), "PYTHONDONTWRITEBYTECODE": "1",
                "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "RIBOMIMO_SEED": str(seed)})
    save_json(output / "independent_training.command.json", {"cwd": str(runtime), "command": command})
    started = time.perf_counter()
    with (output / "independent_training.log").open("w") as log:
        completed = subprocess.run(command, cwd=runtime, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
    elapsed = time.perf_counter() - started
    (output / "independent_training.returncode.txt").write_text(str(completed.returncode) + "\n")
    result_dirs = sorted((output / "official_bounded" / "results").glob("*/"))
    independent_env_path = runtime / "runtime_environment.json"
    independent_env = json.loads(independent_env_path.read_text()) if independent_env_path.is_file() else {}
    runtime_ok = independent_env.get("torch_num_threads") == 1 and independent_env.get("deterministic_algorithms_in_driver") is True and independent_env.get("gpu_visible_to_training") is False
    check("independent_training_completed", completed.returncode == 0 and len(result_dirs) == 1 and runtime_ok, {"returncode": completed.returncode, "wall_seconds": elapsed, "runtime_environment": independent_env})
    if completed.returncode != 0 or len(result_dirs) != 1:
        raise RuntimeError("Independent training failed; inspect raw log")
    result_dir = result_dirs[0]
    independent_log = result_dir / "logging.log"
    independent_checkpoints = {}
    for fold in range(2):
        path = result_dir / f"best_model_0_{fold}.pth"
        independent_checkpoints[str(fold)] = {"path": str(path), "sha256": sha(path)}
    check("independent_checkpoints_present", all(Path(row["path"]).is_file() for row in independent_checkpoints.values()))
    production_aggregate = aggregate(Path(prod["official_result"]["logging_log"]))
    independent_aggregate = aggregate(independent_log)
    retrain_delta = max(abs(a - b) for a, b in zip(production_aggregate, independent_aggregate))
    numeric_deltas.append(retrain_delta)
    check("independent_retraining_aggregate_match", retrain_delta <= 1e-6, {"production": production_aggregate, "independent": independent_aggregate, "delta": retrain_delta})
    max_state_delta = 0.0
    for fold in range(2):
        left = torch.load(prod["official_result"]["checkpoints"][str(fold)]["path"], map_location="cpu", weights_only=True)
        right = torch.load(independent_checkpoints[str(fold)]["path"], map_location="cpu", weights_only=True)
        assert left.keys() == right.keys()
        for key in left:
            max_state_delta = max(max_state_delta, float((left[key] - right[key]).abs().max()))
    numeric_deltas.append(max_state_delta)
    check("retrained_checkpoint_tensors_match", max_state_delta == 0.0, {"max_abs_delta": max_state_delta})
    rows, parameter_count = evaluate_checkpoints(runtime, output / "official_bounded", prod["official_result"]["checkpoints"], seed)
    save_json(output / "independent_checkpoint_test_metrics.json", rows)
    expected_rows = fold_best_from_log(Path(prod["official_result"]["logging_log"]))
    for fold in range(2):
        delta = max(abs(rows[fold][key] - expected_rows[fold][key]) for key in ("r2", "mse", "pearson"))
        numeric_deltas.append(delta)
        check(f"fold_{fold}_checkpoint_metrics_match", delta <= 2e-5, {"independent": rows[fold], "official_log_rounded": expected_rows[fold], "delta": delta})
    recomputed_aggregate = []
    for key in ("r2", "mse", "pearson"):
        values = [row[key] for row in rows]
        recomputed_aggregate.extend([float(np.mean(values)), float(np.std(values))])
    aggregate_delta = max(abs(a - b) for a, b in zip(recomputed_aggregate, production_aggregate))
    numeric_deltas.append(aggregate_delta)
    check("checkpoint_aggregate_recomputed", aggregate_delta <= 2e-5, {"checkpoint_recompute": recomputed_aggregate, "official_log_rounded": production_aggregate, "delta": aggregate_delta})
    check("model_contract_and_parameter_count", parameter_count == prod["official_result"]["checkpoint_parameter_count"], parameter_count)
    artifact_failures = []
    for name, row in prod["artifacts"].items():
        if not Path(row["path"]).is_file() or sha(row["path"]) != row["sha256"]:
            artifact_failures.append(name)
    check("production_artifact_hashes", not artifact_failures, artifact_failures)
    check("environment_protocol", prod["environment"]["device"] == "cpu" and prod["environment"]["torch_num_threads"] == 1 and prod["protocol"]["num_fold"] == 2 and prod["protocol"]["max_epoch"] == 2 and prod["protocol"]["input_dims"] == 97)
    forbidden = ("full_official_10fold_100epoch_reproduced", "homology_aware_split", "protein_ood", "study_ood", "functional_ood", "main_baseline_comparison", "publication_metrics_reproduced", "sota_claim")
    check("bounded_scope_and_no_overclaim", all(prod[key] is False for key in forbidden) and prod["published_prediction_pickles_used"] is False)
    passed = sum(row["pass"] for row in checks)
    report = {
        "schema_version": "a8-rk05-ribomimo-independent-verification-v1",
        "task": "RK-05",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "production_module_imported": False,
        "source_commit": COMMIT,
        "check_count": len(checks),
        "passed_checks": passed,
        "checks": checks,
        "max_numeric_delta": max(numeric_deltas),
        "independent_training": {
            "returncode": completed.returncode, "wall_seconds": elapsed,
            "log": str(output / "independent_training.log"),
            "log_sha256": sha(output / "independent_training.log"),
            "result_dir": str(result_dir),
            "runtime_environment_path": str(independent_env_path),
            "runtime_environment": independent_env,
            "checkpoints": independent_checkpoints,
        },
        "checkpoint_metrics_path": str(output / "independent_checkpoint_test_metrics.json"),
        "scope": "Bounded 20-record, two-fold, two-epoch CPU official training verification only; no publication, OOD, functional, main-matrix or SOTA claim.",
    }
    destination = Path(args.output).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    save_json(destination, report)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "max_numeric_delta": report["max_numeric_delta"], "output": str(destination)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
