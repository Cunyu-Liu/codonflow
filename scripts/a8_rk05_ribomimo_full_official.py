#!/usr/bin/env python3
"""Execute one frozen full-matrix official RiboMIMO CV protocol.

The official algorithm is unchanged. Six modern NumPy compatibility replacements
are applied verbatim; a wrapper fixes random seeds/determinism and records the
runtime. The report never upgrades random gene CV into OOD or SOTA evidence.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time

SOURCE_FILES = ("runRiboMIMO.py", "model.py", "utils.py", "getSaliency.py")
REPLACEMENTS = [
    ("model.py", "list_seq = np.array(list_seq)", "list_seq = np.array(list_seq, dtype=object)", "NumPy >=2 rejects ragged codon lists"),
    ("model.py", "list_density = np.array(list_density)", "list_density = np.array(list_density, dtype=object)", "NumPy >=2 rejects ragged density lists"),
    ("model.py", "self.density = np.array(density)", "self.density = np.array(density, dtype=object)", "evaluation/training densities are ragged before padding"),
    ("model.py", "self.x_input = np.array(x_input)", "self.x_input = np.array(x_input, dtype=object)", "model inputs are ragged before padding"),
    ("model.py", "self.density_level = np.array(density_level)", "self.density_level = np.array(density_level, dtype=object)", "classification targets are ragged before padding"),
    ("runRiboMIMO.py", "data_pad = np.array(data_pad)", "data_pad = np.array(data_pad, dtype=float)", "ragged compatibility containers require explicit numeric dtype after padding"),
    ("model.py", "x = pack_padded_sequence(x, length, batch_first=True)", "x = pack_padded_sequence(x, length.cpu(), batch_first=True)", "modern PyTorch requires a CPU int64 lengths tensor; sequence values and model logic are unchanged"),
]


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_json(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def apply_replacements(source: Path, destination: Path) -> list[dict]:
    destination.mkdir(parents=True, exist_ok=False)
    applied = []
    for filename in SOURCE_FILES:
        shutil.copy2(source / filename, destination / filename)
    for filename, old, new, reason in REPLACEMENTS:
        path = destination / filename
        text = path.read_text()
        if text.count(old) != 1:
            raise ValueError(f"Expected exactly one compatibility target in {filename}: {old!r}")
        path.write_text(text.replace(old, new))
        applied.append({"file": filename, "old": old, "new": new, "reason": reason})
    return applied


def unified_diff(source: Path, runtime: Path) -> str:
    chunks = []
    for filename in SOURCE_FILES:
        before = (source / filename).read_text().splitlines(keepends=True)
        after = (runtime / filename).read_text().splitlines(keepends=True)
        chunks.extend(difflib.unified_diff(before, after, fromfile=f"official/{filename}", tofile=f"full/{filename}"))
    return "".join(chunks)


def parse_official_log(path: Path, num_fold: int) -> dict:
    text = path.read_text()
    aggregate_pattern = re.compile(
        r"RiboMIMO, r2\s+([-+0-9.eE]+|nan|inf|-inf)\s+([-+0-9.eE]+|nan|inf|-inf),\s*"
        r"mse\s+([-+0-9.eE]+|nan|inf|-inf)\s+([-+0-9.eE]+|nan|inf|-inf),\s*"
        r"corr\s+([-+0-9.eE]+|nan|inf|-inf)\s+([-+0-9.eE]+|nan|inf|-inf)"
    )
    matches = aggregate_pattern.findall(text)
    if not matches:
        raise ValueError("No final official cross-validation aggregate found")
    values = [float(value) for value in matches[-1]]
    aggregate = {
        "r2_mean": values[0], "r2_std": values[1],
        "mse_mean": values[2], "mse_std": values[3],
        "pearson_mean": values[4], "pearson_std": values[5],
        "aggregation": "mean and population std across fold-level best-validation-checkpoint test scores",
    }
    epoch_pattern = re.compile(
        r"Fold (\d+)x(\d+)/(\d+)x(\d+), (Valid|Test), "
        r"r2 ([-+0-9.eE]+|nan|inf|-inf), mse ([-+0-9.eE]+|nan|inf|-inf), corr ([-+0-9.eE]+|nan|inf|-inf), "
        r"auc ([-+0-9.eE]+|nan|inf|-inf), aupr ([-+0-9.eE]+|nan|inf|-inf), loss ([-+0-9.eE]+|nan|inf|-inf)"
    )
    folds = {fold: {"fold": fold, "best_valid_r2": float("-inf"), "epochs_logged": 0} for fold in range(num_fold)}
    pending = {}
    for match in epoch_pattern.finditer(text):
        _repeat, fold_text, _nr, _nf, split = match.group(1, 2, 3, 4, 5)
        fold = int(fold_text) - 1
        metrics = {
            "r2": float(match.group(6)), "mse": float(match.group(7)),
            "pearson": float(match.group(8)), "auc": float(match.group(9)),
            "aupr": float(match.group(10)), "classification_loss": float(match.group(11)),
        }
        if split == "Valid":
            folds[fold]["epochs_logged"] += 1
            improved = metrics["r2"] > folds[fold]["best_valid_r2"]
            if improved:
                folds[fold]["best_valid_r2"] = metrics["r2"]
                folds[fold]["best_epoch"] = folds[fold]["epochs_logged"]
            pending[fold] = improved
        else:
            if pending.get(fold, False):
                folds[fold]["test_at_best_validation"] = metrics
    fold_rows = list(folds.values())
    if any("test_at_best_validation" not in row for row in fold_rows):
        raise ValueError("Missing best-validation test metrics for at least one fold")
    import math
    import statistics
    numeric_aggregate = [aggregate[key] for key in ("r2_mean", "r2_std", "mse_mean", "mse_std", "pearson_mean", "pearson_std")]
    if not all(math.isfinite(value) for value in numeric_aggregate):
        raise ValueError(f"Official aggregate contains non-finite regression metrics: {aggregate}")
    test = [row["test_at_best_validation"] for row in fold_rows]
    recomputed = {
        "r2_mean": statistics.fmean(row["r2"] for row in test),
        "r2_std": statistics.pstdev(row["r2"] for row in test),
        "mse_mean": statistics.fmean(row["mse"] for row in test),
        "mse_std": statistics.pstdev(row["mse"] for row in test),
        "pearson_mean": statistics.fmean(row["pearson"] for row in test),
        "pearson_std": statistics.pstdev(row["pearson"] for row in test),
    }
    deltas = {key: abs(recomputed[key] - aggregate[key]) for key in recomputed}
    if max(deltas.values()) > 0.0000011:
        raise ValueError(f"Official aggregate does not match per-fold log reconstruction: {deltas}")
    return {"aggregate": aggregate, "folds": fold_rows, "recomputed_from_fold_logs": recomputed, "rounding_deltas": deltas}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text())
    if protocol["status"] != "FROZEN_BEFORE_TRAINING":
        raise ValueError("Protocol was not frozen before training")
    output = Path(args.output_dir).resolve()
    report_path = Path(args.report).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output directory must be absent or empty: {output}")
    if report_path.exists():
        raise FileExistsError(f"Refusing to overwrite report: {report_path}")
    output.mkdir(parents=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    driver_snapshot = output / "driver.py"
    shutil.copy2(Path(__file__).resolve(), driver_snapshot)

    source = Path(protocol["source"]["path"]).resolve()
    for filename, expected in protocol["source"]["file_sha256"].items():
        if sha256(source / "src" / filename) != expected:
            raise ValueError(f"Official source hash mismatch: {filename}")
    matrix = Path(protocol["matrix"]["path"]).resolve()
    if sha256(matrix) != protocol["matrix"]["sha256"]:
        raise ValueError("Full matrix hash mismatch")
    preflight_path = Path(protocol["loader_preflight"]["report"])
    if sha256(preflight_path) != protocol["loader_preflight"]["sha256"]:
        raise ValueError("Loader preflight identity mismatch")

    runtime = output / "src"
    applied = apply_replacements(source / "src", runtime)
    (output / "data").mkdir()
    runtime_matrix = output / "data" / f"{protocol['dataset']}.txt"
    shutil.copy2(matrix, runtime_matrix)
    shutil.copy2(protocol_path, output / "protocol.copy.json")
    diff_path = output / "official_to_full.diff"
    diff_path.write_text(unified_diff(source / "src", runtime))
    replacements_path = output / "compatibility_replacements.json"
    dump_json(replacements_path, applied)

    official = protocol["official_arguments"]
    official_args = [
        "--add_nt", "--add_aa", "--dataset", protocol["dataset"],
        "--gpu", official["gpu"], "--seed", str(official["seed"]),
        "--num_repeat", str(official["num_repeat"]), "--num_fold", str(official["num_fold"]),
        "--batch_size", str(official["batch_size"]), "--max_epoch", str(official["max_epoch"]),
        "--early_stop", str(official["early_stop"]), "--learning_rate", str(official["learning_rate"]),
        "--weight_decay", str(official["weight_decay"]), "--sim", str(official["sim"]),
    ]
    seeded_driver = runtime / "full_seeded_driver.py"
    seeded_driver.write_text(
        "import json, os, runpy, sys\n"
        "from pathlib import Path\n"
        "import numpy as np\n"
        "import torch\n"
        "seed = int(os.environ['RIBOMIMO_SEED'])\n"
        "np.random.seed(seed)\n"
        "torch.manual_seed(seed)\n"
        "torch.cuda.manual_seed_all(seed)\n"
        "torch.use_deterministic_algorithms(True)\n"
        "torch.set_num_threads(1)\n"
        "torch.backends.cudnn.deterministic = True\n"
        "torch.backends.cudnn.benchmark = False\n"
        "sys.path.insert(0, os.getcwd())\n"
        "runpy.run_path('runRiboMIMO.py', run_name='__main__')\n"
        "env = {'torch': torch.__version__, 'numpy': np.__version__, 'cuda_available': torch.cuda.is_available(), 'cuda_device_count_after_official_args': torch.cuda.device_count(), 'cuda_visible_devices_after_official_args': os.environ.get('CUDA_VISIBLE_DEVICES'), 'torch_num_threads': torch.get_num_threads(), 'deterministic_algorithms': torch.are_deterministic_algorithms_enabled(), 'cudnn_deterministic': torch.backends.cudnn.deterministic, 'cudnn_benchmark': torch.backends.cudnn.benchmark, 'gpu_names': [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}\n"
        "Path('runtime_environment.json').write_text(json.dumps(env, indent=2) + '\\n')\n"
    )
    command = [protocol["execution"]["python"], "-u", seeded_driver.name] + official_args
    env = os.environ.copy()
    env.update({
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "CUDA_VISIBLE_DEVICES": official["gpu"],
        "PYTHONHASHSEED": str(official["seed"]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "RIBOMIMO_SEED": str(official["seed"]),
        "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
    })
    command_path = output / "training.command.json"
    dump_json(command_path, {"cwd": str(runtime), "command": command, "environment_overrides": {key: env[key] for key in ("CUDA_DEVICE_ORDER", "CUDA_VISIBLE_DEVICES", "PYTHONHASHSEED", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "RIBOMIMO_SEED", "CUBLAS_WORKSPACE_CONFIG")}})
    prepare = {
        "schema_version": "a8-rk05-ribomimo-full-prepare-v1",
        "status": "PREPARED_NOT_TRAINED",
        "protocol": str(protocol_path), "protocol_sha256": sha256(protocol_path),
        "output_dir": str(output), "command": str(command_path),
        "driver_snapshot": str(driver_snapshot), "driver_sha256": sha256(driver_snapshot),
        "runtime_file_sha256": {name: sha256(runtime / name) for name in SOURCE_FILES},
        "matrix_copy_sha256": sha256(runtime_matrix),
        "diff_sha256": sha256(diff_path),
        "replacement_count": len(applied),
    }
    dump_json(output / "prepare_report.json", prepare)
    print(json.dumps(prepare, indent=2), flush=True)
    if args.prepare_only:
        return

    log_path = output / "training.console.log"
    returncode_path = output / "training.returncode.txt"
    start = time.perf_counter()
    with log_path.open("w") as log:
        completed = subprocess.run(command, cwd=runtime, env=env, stdout=log, stderr=subprocess.STDOUT)
    elapsed = time.perf_counter() - start
    returncode_path.write_text(str(completed.returncode) + "\n")
    if completed.returncode != 0:
        failure = {
            "schema_version": "a8-rk05-ribomimo-full-execution-failure-v1",
            "status": "FAIL_OFFICIAL_TRAINING",
            "returncode": completed.returncode,
            "wall_seconds": elapsed,
            "log": str(log_path), "log_sha256": sha256(log_path),
            "command": str(command_path), "output_dir": str(output),
        }
        failure_path = report_path.with_name(report_path.stem + "_failed.json")
        dump_json(failure_path, failure)
        raise RuntimeError(f"Official full training failed; retained report: {failure_path}")

    results_parent = output / "results"
    result_dirs = sorted(path for path in results_parent.iterdir() if path.is_dir())
    if len(result_dirs) != 1:
        raise ValueError(f"Expected one official result directory, found {result_dirs}")
    result_dir = result_dirs[0]
    official_log = result_dir / "logging.log"
    parsed = parse_official_log(official_log, official["num_fold"])
    checkpoints = {}
    for fold in range(official["num_fold"]):
        path = result_dir / f"best_model_0_{fold}.pth"
        if not path.is_file():
            raise FileNotFoundError(path)
        checkpoints[str(fold)] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}

    import numpy as np
    import scipy
    import sklearn
    import torch
    state = torch.load(checkpoints["0"]["path"], map_location="cpu", weights_only=True)
    parameter_count = sum(value.numel() for value in state.values())
    runtime_environment_path = runtime / "runtime_environment.json"
    environment = {
        "python_executable": protocol["execution"]["python"],
        "python": platform.python_version(),
        "torch": torch.__version__, "numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__,
        "runtime_environment_artifact": str(runtime_environment_path),
    }
    environment.update(json.loads(runtime_environment_path.read_text()))
    dump_json(output / "environment.json", environment)
    freeze = subprocess.run([protocol["execution"]["python"], "-m", "pip", "freeze"], check=True, capture_output=True, text=True).stdout
    (output / "pip_freeze.txt").write_text(freeze)

    artifacts = {}
    for path in (protocol_path, driver_snapshot, runtime_matrix, diff_path, replacements_path, command_path, log_path, returncode_path, official_log, result_dir / "config", runtime_environment_path, output / "environment.json", output / "pip_freeze.txt"):
        artifacts[path.name if path != official_log else "official_result_logging.log"] = {"path": str(path), "sha256": sha256(path)}
    report = {
        "schema_version": "a8-rk05-ribomimo-full-official-v1",
        "task": "RK-05",
        "status": f"PASS_COMPLETE_OFFICIAL_1X{official['num_fold']}FOLD_MAX{official['max_epoch']}_{protocol['dataset'].upper()}",
        "source": protocol["source"],
        "matrix": {**protocol["matrix"], "runtime_copy": str(runtime_matrix), "runtime_copy_sha256": sha256(runtime_matrix)},
        "loader_preflight": protocol["loader_preflight"],
        "protocol": {**official, "protocol_path": str(protocol_path), "protocol_sha256": sha256(protocol_path)},
        "execution": {**protocol["execution"], "wall_seconds": elapsed, "returncode": completed.returncode},
        "compatibility": {**protocol["compatibility"], "replacements_path": str(replacements_path), "diff_path": str(diff_path), "diff_sha256": sha256(diff_path)},
        "official_result": {
            "result_dir": str(result_dir), "config": str(result_dir / "config"), "logging_log": str(official_log),
            **parsed, "checkpoints": checkpoints,
            "checkpoint_parameter_tensors": len(state), "checkpoint_parameter_count": parameter_count,
        },
        "environment": environment,
        "artifacts": artifacts,
        "published_prediction_pickles_used": False,
        "official_default_1x10fold_max100_protocol_executed": True,
        "all_four_datasets_reproduced": False,
        "homology_aware_split": False,
        "protein_ood": False,
        "study_ood": False,
        "functional_ood": False,
        "main_baseline_comparison": False,
        "publication_metrics_reproduced": False,
        "sota_claim": False,
        "limitations": [
            "This is one complete author-processed matrix under the official random-gene 1x10-fold/max-100-epoch/early-stop-5 protocol; folds may stop before epoch 100.",
            "Modern NumPy compatibility patches and deterministic CUDA execution do not reproduce the original Python/CUDA environment or prove publication-number identity.",
            "Official random gene CV is not homology-, protein-, study- or functional-OOD and is not a unified-cost main baseline comparison.",
            "Author-provided prediction pickles were not used as newly trained outputs; publication metric identity remains separately unverified.",
        ],
    }
    dump_json(report_path, report)
    dump_json(output / "production_report.copy.json", report)
    print(json.dumps({"status": report["status"], "report": str(report_path), "metrics": parsed["aggregate"], "wall_seconds": elapsed}, indent=2), flush=True)


if __name__ == "__main__":
    main()
