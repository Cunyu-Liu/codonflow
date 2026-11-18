#!/usr/bin/env python3
"""Bounded, fixed-source RiboMIMO training smoke with retained failures.

This is not a reproduction of the publication's full 10-fold/100-epoch study.
The official algorithm and optimization are unchanged; only modern NumPy ragged
array construction and numeric padding dtype are patched.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
from collections import Counter

SOURCE_COMMIT = "094c693d4df45f4b29f5a3209b31c452a39092a5"
DATASET = "RiboBounded20"
SOURCE_FILES = ("runRiboMIMO.py", "model.py", "utils.py", "getSaliency.py")
RAGGED_REPLACEMENTS = [
    ("model.py", "list_seq = np.array(list_seq)", "list_seq = np.array(list_seq, dtype=object)", "NumPy >=2 rejects ragged codon lists"),
    ("model.py", "list_density = np.array(list_density)", "list_density = np.array(list_density, dtype=object)", "NumPy >=2 rejects ragged density lists"),
    ("model.py", "self.density = np.array(density)", "self.density = np.array(density, dtype=object)", "evaluation/training densities are ragged before padding"),
    ("model.py", "self.x_input = np.array(x_input)", "self.x_input = np.array(x_input, dtype=object)", "model inputs are ragged before padding"),
    ("model.py", "self.density_level = np.array(density_level)", "self.density_level = np.array(density_level, dtype=object)", "classification targets are ragged before padding"),
]
PADDING_REPLACEMENT = (
    "runRiboMIMO.py",
    "data_pad = np.array(data_pad)",
    "data_pad = np.array(data_pad, dtype=float)",
    "ragged compatibility containers require explicit numeric dtype after padding",
)
def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dump_json(path: str | Path, value: object) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def select_records(matrix: str | Path, count: int = 20) -> tuple[list[dict], str]:
    """Deterministically select shortest official-loader-eligible unique genes."""
    lines = Path(matrix).read_text().splitlines()
    if len(lines) % 3:
        raise ValueError("Official matrix must contain complete three-line records")
    parsed = []
    for index in range(len(lines) // 3):
        header, seq_line, count_line = lines[3 * index:3 * index + 3]
        if not header.startswith(">"):
            raise ValueError(f"Invalid header at record {index}")
        name = header[1:].split()[0]
        codons = seq_line.split()
        counts = [float(value) for value in count_line.split()]
        parsed.append((index, name, codons, counts, header, seq_line, count_line))
    names = Counter(row[1] for row in parsed)
    eligible = []
    for row in parsed:
        index, name, codons, counts, header, seq_line, count_line = row
        if names[name] != 1 or len(codons) < 15 or len(codons) != len(counts):
            continue
        if any(len(c) != 3 or set(c) - set("ATCG") for c in codons):
            continue
        if not all(math.isfinite(value) and value >= 0 for value in counts):
            continue
        positive = [value for value in counts if value > 0.5]
        coverage = sum(value > 0.5 for value in counts) / len(counts)
        if not positive or coverage <= 0.6:
            continue
        eligible.append({
            "record_id": name,
            "source_index": index,
            "n_codons": len(codons),
            "coverage": coverage,
            "mean_positive_count": sum(positive) / len(positive),
            "header": header,
            "sequence_line": seq_line,
            "count_line": count_line,
        })
    eligible.sort(key=lambda row: (row["n_codons"], row["record_id"], row["source_index"]))
    selected = eligible[:count]
    if len(selected) != count:
        raise ValueError(f"Only {len(selected)} eligible records; required {count}")
    subset = "\n".join(
        line
        for row in selected
        for line in (row["header"], row["sequence_line"], row["count_line"])
    ) + "\n"
    public_rows = [{k: v for k, v in row.items() if not k.endswith("line") and k != "header"} for row in selected]
    return public_rows, subset


def apply_replacements(source: Path, destination: Path, replacements: list[tuple[str, str, str, str]]) -> list[dict]:
    destination.mkdir(parents=True, exist_ok=False)
    applied = []
    for filename in SOURCE_FILES:
        shutil.copy2(source / filename, destination / filename)
    for filename, old, new, reason in replacements:
        path = destination / filename
        text = path.read_text()
        occurrences = text.count(old)
        if occurrences != 1:
            raise ValueError(f"Expected one occurrence of {old!r} in {filename}, found {occurrences}")
        path.write_text(text.replace(old, new))
        applied.append({"file": filename, "old": old, "new": new, "reason": reason})
    return applied


def unified_diff(source: Path, runtime: Path) -> str:
    chunks = []
    for filename in SOURCE_FILES:
        before = (source / filename).read_text().splitlines(keepends=True)
        after = (runtime / filename).read_text().splitlines(keepends=True)
        chunks.extend(difflib.unified_diff(before, after, fromfile=f"official/{filename}", tofile=f"bounded/{filename}"))
    return "".join(chunks)


def execute(root: Path, python: str, args: list[str], log_name: str, seed: int, seeded_driver: bool) -> dict:
    src = root / "src"
    command = [python, "-u", "runRiboMIMO.py"] + args
    if seeded_driver:
        driver = src / "bounded_seeded_driver.py"
        driver.write_text(
            "import os, runpy, sys, json\n"
            "from pathlib import Path\n"
            "import numpy as np\n"
            "import torch\n"
            "seed = int(os.environ['RIBOMIMO_SEED'])\n"
            "np.random.seed(seed)\n"
            "torch.manual_seed(seed)\n"
            "torch.use_deterministic_algorithms(True)\n"
            "torch.set_num_threads(1)\n"
            "sys.path.insert(0, os.getcwd())\n"
            "runpy.run_path('runRiboMIMO.py', run_name='__main__')\n"
            "Path('runtime_environment.json').write_text(json.dumps({'device': 'cpu', 'torch_num_threads': torch.get_num_threads(), 'deterministic_algorithms_in_driver': torch.are_deterministic_algorithms_enabled(), 'gpu_visible_to_training': torch.cuda.device_count() > 0, 'cuda_visible_devices_after_official_args': os.environ.get('CUDA_VISIBLE_DEVICES')}, indent=2) + '\\n')\n"
        )
        command = [python, "-u", str(driver.name)] + args
    env = os.environ.copy()
    env.update({
        "CUDA_VISIBLE_DEVICES": "",
        "PYTHONHASHSEED": str(seed),
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "RIBOMIMO_SEED": str(seed),
    })
    log_path = root / log_name
    command_path = root / (log_name + ".command.json")
    dump_json(command_path, {"cwd": str(src), "command": command, "environment_overrides": {k: env[k] for k in ("CUDA_VISIBLE_DEVICES", "PYTHONHASHSEED", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "RIBOMIMO_SEED")}})
    start = time.perf_counter()
    with log_path.open("w") as log:
        completed = subprocess.run(command, cwd=src, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
    elapsed = time.perf_counter() - start
    returncode_path = root / (log_name + ".returncode.txt")
    returncode_path.write_text(str(completed.returncode) + "\n")
    return {
        "returncode": completed.returncode,
        "wall_seconds": elapsed,
        "log": str(log_path),
        "log_sha256": sha256(log_path),
        "returncode_path": str(returncode_path),
        "command": str(command_path),
        "command_sha256": sha256(command_path),
    }


def parse_final_metrics(log_path: str | Path) -> dict:
    text = Path(log_path).read_text()
    pattern = re.compile(
        r"RiboMIMO, r2\s+([-+0-9.eE]+)\s+([-+0-9.eE]+),\s*"
        r"mse\s+([-+0-9.eE]+)\s+([-+0-9.eE]+),\s*"
        r"corr\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)"
    )
    matches = pattern.findall(text)
    if not matches:
        raise ValueError("No final cross-validation aggregate found in official log")
    values = [float(value) for value in matches[-1]]
    return {
        "r2_mean": values[0], "r2_std": values[1],
        "mse_mean": values[2], "mse_std": values[3],
        "pearson_mean": values[4], "pearson_std": values[5],
        "aggregation": "mean and population std across two fold-level best-validation checkpoint test scores",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--qc-summary", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--source-archive")
    parser.add_argument("--records", type=int, default=20)
    parser.add_argument("--num-fold", type=int, default=2)
    parser.add_argument("--max-epoch", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261118)
    args = parser.parse_args()
    if args.records != 20 or args.num_fold != 2 or args.max_epoch != 2 or args.batch_size != 4:
        raise ValueError("This frozen smoke contract requires records=20, folds=2, epochs=2, batch=4")
    source = Path(args.source_dir).resolve()
    matrix = Path(args.matrix).resolve()
    output = Path(args.output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output directory must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    qc = json.loads(Path(args.qc_summary).read_text())
    dataset_qc = next(row for row in qc["datasets"] if row["dataset"] == "Mohammad16")
    matrix_sha = sha256(matrix)
    if matrix_sha != dataset_qc["raw_sha256"]:
        raise ValueError("Matrix hash does not match frozen RK03 QC")
    selected, subset = select_records(matrix, args.records)
    subset_path = output / "input_subset.txt"
    subset_path.write_text(subset)
    official_args = [
        "--add_nt", "--add_aa", "--dataset", DATASET, "--gpu", "-1",
        "--seed", str(args.seed), "--num_repeat", "1", "--num_fold", str(args.num_fold),
        "--batch_size", str(args.batch_size), "--max_epoch", str(args.max_epoch),
        "--early_stop", str(args.max_epoch), "--sim", "-1",
    ]
    runs = {}
    for label, replacements, seeded in (
        ("official_unmodified", [], False),
        ("ragged_only", RAGGED_REPLACEMENTS, False),
        ("official_bounded", RAGGED_REPLACEMENTS + [PADDING_REPLACEMENT], True),
    ):
        root = output / label
        (root / "data").mkdir(parents=True)
        shutil.copy2(subset_path, root / "data" / f"{DATASET}.txt")
        applied = apply_replacements(source / "src", root / "src", replacements)
        runs[label] = execute(root, sys.executable, official_args, f"{label}.log", args.seed, seeded)
        runs[label]["applied_replacements"] = applied
    if runs["official_unmodified"]["returncode"] == 0:
        raise RuntimeError("Unmodified source unexpectedly succeeded; retained-failure contract needs review")
    if runs["ragged_only"]["returncode"] == 0:
        raise RuntimeError("Ragged-only source unexpectedly succeeded; padding-patch rationale needs review")
    if runs["official_bounded"]["returncode"] != 0:
        raise RuntimeError("Bounded official training failed; inspect retained log before finalizing")
    runtime = output / "official_bounded" / "src"
    diff_path = output / "official_to_bounded.diff"
    diff_path.write_text(unified_diff(source / "src", runtime))
    replacements_path = output / "compatibility_replacements.json"
    dump_json(replacements_path, runs["official_bounded"]["applied_replacements"])
    results_parent = output / "official_bounded" / "results"
    result_dirs = sorted(path for path in results_parent.iterdir() if path.is_dir())
    if len(result_dirs) != 1:
        raise ValueError(f"Expected one final official result directory, found {len(result_dirs)}")
    result_dir = result_dirs[0]
    official_log = result_dir / "logging.log"
    metrics = parse_final_metrics(official_log)
    checkpoints = {}
    for fold in range(args.num_fold):
        path = result_dir / f"best_model_0_{fold}.pth"
        if not path.is_file():
            raise FileNotFoundError(path)
        checkpoints[str(fold)] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
    import numpy as np
    import scipy
    import sklearn
    import torch
    parameter_count = None
    state = torch.load(checkpoints["0"]["path"], map_location="cpu", weights_only=True)
    parameter_count = sum(value.numel() for value in state.values())
    environment = {
        "python_executable": sys.executable,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "sklearn": sklearn.__version__,
        "device": "cpu",
        "torch_num_threads": torch.get_num_threads(),
        "deterministic_algorithms_in_driver": True,
        "gpu_visible_to_training": False,
    }
    runtime_env_path = output / "official_bounded" / "src" / "runtime_environment.json"
    if not runtime_env_path.is_file():
        raise RuntimeError("Seeded driver did not write its actual runtime environment")
    environment.update(json.loads(runtime_env_path.read_text()))
    environment["runtime_environment_artifact"] = str(runtime_env_path)
    dump_json(output / "environment.json", environment)
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], check=True, capture_output=True, text=True).stdout
    (output / "pip_freeze.txt").write_text(freeze)
    artifacts = {}
    for path in [subset_path, diff_path, replacements_path, output / "environment.json", output / "pip_freeze.txt", official_log, result_dir / "config", runtime_env_path]:
        artifacts[path.name if path != official_log else "final_result_logging.log"] = {"path": str(path), "sha256": sha256(path)}
    for label, run in runs.items():
        for key in ("log", "returncode_path", "command"):
            path = Path(run[key])
            artifacts[f"{label}:{key}"] = {"path": str(path), "sha256": sha256(path)}
    report = {
        "schema_version": "a8-rk05-ribomimo-official-smoke-v2",
        "task": "RK-05",
        "status": "BOUNDED_OFFICIAL_TRAINING_COMPLETE",
        "source": {
            "repository": "https://github.com/tiantz17/RiboMIMO",
            "commit": SOURCE_COMMIT,
            "path": str(source),
            "file_sha256": {name: sha256(source / "src" / name) for name in SOURCE_FILES},
            "archive_path": str(Path(args.source_archive).resolve()) if args.source_archive else None,
            "archive_sha256": sha256(args.source_archive) if args.source_archive else None,
        },
        "matrix": {"path": str(matrix), "sha256": matrix_sha, "dataset": "Mohammad16"},
        "subset": {
            "path": str(subset_path), "sha256": sha256(subset_path), "records": selected,
            "rule": "shortest 20 unique-name records with >=15 codons, aligned lengths, ATCG codons, finite nonnegative counts, positive count >0.5 and strict official coverage >0.6; ties by record ID/source index",
        },
        "protocol": {
            "input_dims": 97, "rnn_hidden_dims": 256, "rnn_depth": 2,
            "num_repeat": 1, "num_fold": 2, "max_epoch": 2, "early_stop": 2,
            "batch_size": 4, "seed": args.seed, "split": "official random gene split, sim=-1",
            "add_nt": True, "add_aa": True, "device": "cpu",
            "selection_metric": "validation R2; reported test values follow the official best-validation checkpoint logic",
        },
        "runs": runs,
        "compatibility": {
            "replacement_count": 6,
            "replacements_path": str(replacements_path),
            "diff_path": str(diff_path),
            "diff_sha256": sha256(diff_path),
            "algorithm_changed": False,
            "bounded_cpu_only": True,
        },
        "official_result": {
            "result_dir": str(result_dir), "config": str(result_dir / "config"),
            "logging_log": str(official_log), "metrics": metrics,
            "checkpoints": checkpoints, "checkpoint_parameter_tensors": len(state),
            "checkpoint_parameter_count": parameter_count,
        },
        "environment": environment,
        "artifacts": artifacts,
        "published_prediction_pickles_used": False,
        "full_official_10fold_100epoch_reproduced": False,
        "homology_aware_split": False,
        "protein_ood": False,
        "study_ood": False,
        "functional_ood": False,
        "main_baseline_comparison": False,
        "publication_metrics_reproduced": False,
        "sota_claim": False,
        "limitations": [
            "Twenty shortest eligible Mohammad16 records and two epochs/two folds are a bounded interface/training diagnostic, not publication performance.",
            "Official random gene splitting is not homology-, protein- or study-OOD; no test/untouched functional claim is authorized.",
            "Five ragged-array replacements plus one numeric-padding dtype patch are compatibility-only; the exploratory LongTensor patch is not required in the fixed torch runtime and is excluded; CUDA execution is not validated.",
            "Author-provided prediction pickles were not used as newly trained model outputs.",
        ],
    }
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        raise FileExistsError(f"Refusing to overwrite report: {report_path}")
    dump_json(report_path, report)
    print(json.dumps({"status": report["status"], "report": str(report_path), "metrics": metrics, "parameter_count": parameter_count}, indent=2))


if __name__ == "__main__":
    main()
