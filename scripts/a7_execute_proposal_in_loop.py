"""Execute and independently gate the frozen proposal-in-the-loop diagnostic."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.dataset import read_fasta
from codonflow.models.guided_sampler import synonymous_x0
from codonflow.train.run_pretrain import file_sha256, git_commit
from scripts.a7_proposal_in_loop_gate import DIAGNOSTIC_GENES
from scripts.a7_provenance import resolve_accepted_code_commits
from scripts.a7_run_proposal_in_loop import validate_baseline

import numpy as np


def parse_arm(value):
    name, checkpoint = value.split("=", 1)
    path, sha256 = checkpoint.rsplit(":", 1)
    if name not in ("FULL", "EDIT") or len(sha256) != 64 or not path:
        raise ValueError("arms must be FULL/EDIT=checkpoint_path:checkpoint_sha256")
    return name, path, sha256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", action="append", required=True)
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--baseline-code-commit", action="append", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--calibration-dir", required=True)
    parser.add_argument("--data-split-sha256", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--accept-code-commit", action="append", default=[])
    parser.add_argument("--only-arm", choices=("FULL", "EDIT"))
    parser.add_argument("--skip-gate", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    arms = {name: (name, path, sha256) for name, path, sha256 in map(parse_arm, args.arm)}
    if set(arms) != {"FULL", "EDIT"}:
        raise ValueError("FULL and EDIT checkpoints are required")
    root = Path(args.out_root)
    if not str(root.resolve()).startswith("/teams/"):
        raise ValueError("diagnostic outputs must remain on /teams")
    accepted = resolve_accepted_code_commits([*args.accept_code_commit, *args.baseline_code_commit])
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("diagnostic requires a clean source tree")
    records = {header.split()[0]: sequence for header, sequence in read_fasta(args.benchmark_fasta)}
    benchmark_sha256 = file_sha256(args.benchmark_fasta)
    rscu_sha256 = file_sha256(args.rscu_json)
    for name, checkpoint, expected_sha in arms.values():
        if file_sha256(checkpoint) != expected_sha:
            raise ValueError(f"checkpoint mismatch: {name}")
    for gene in DIAGNOSTIC_GENES:
        source = records[gene]
        calibration_path = Path(args.calibration_dir) / f"{gene}.json"
        for seed in (0, 1, 2):
            initial = synonymous_x0(source, np.random.default_rng(seed * 1009))
            validate_baseline(Path(args.baseline_dir) / f"{gene}_hill_climbing_s{seed}.json", {
                "record_id": gene, "seed": seed, "method": "hill_climbing",
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "initial_sha256": hashlib.sha256(initial.encode()).hexdigest(),
                "benchmark_sha256": benchmark_sha256, "data_split_sha256": args.data_split_sha256,
                "calibration_sha256": file_sha256(str(calibration_path)), "rscu_sha256": rscu_sha256,
                "checkpoint_sha256": None, "code_commit": accepted,
            })
    tasks = []
    for arm, checkpoint, checkpoint_sha256 in arms.values():
        for gene in DIAGNOSTIC_GENES:
            for seed in (0, 1, 2):
                command = [sys.executable, "scripts/a7_run_proposal_in_loop.py",
                           "--checkpoint", checkpoint, "--checkpoint-sha256", checkpoint_sha256,
                           "--benchmark-fasta", args.benchmark_fasta,
                           "--baseline-dir", args.baseline_dir,
                           "--rscu-json", args.rscu_json, "--calibration-dir", args.calibration_dir,
                           "--data-split-sha256", args.data_split_sha256,
                           "--out-dir", str(root / arm), "--record-id", gene, "--seed", str(seed),
                           "--max-attempts", "100000"]
                for commit in sorted(accepted):
                    command.extend(["--baseline-code-commit", commit])
                for commit in sorted(accepted):
                    command.extend(["--accept-code-commit", commit])
                if args.resume:
                    command.append("--resume")
                tasks.append({"arm": arm, "gene": gene, "seed": seed, "command": command})
    if args.only_arm:
        tasks = [task for task in tasks if task["arm"] == args.only_arm]
    if args.dry_run:
        print(json.dumps({"ready": True, "scientific_gate_passed": False,
                          "n_tasks": len(tasks), "out_root": str(root),
                          "code_commit": git_commit(), "accepted_code_commits": sorted(accepted)}))
        return
    status_path = root / (f"execution_status_{args.only_arm}.json" if args.only_arm else "execution_status.json")
    if status_path.exists() and not args.resume:
        raise FileExistsError(f"refusing to overwrite execution status: {status_path}")
    previous = json.loads(status_path.read_text()) if status_path.exists() else None
    root.mkdir(parents=True, exist_ok=True)
    log_dir = root / "logs"
    log_dir.mkdir(exist_ok=True)
    status = {"protocol": "a7_proposal_in_loop_execution_v1", "status": "running",
              "scientific_gate_passed": False, "code_commit": git_commit(),
              "accepted_code_commits": sorted(accepted), "n_tasks": len(tasks),
              "previous_status": previous}
    status_path.write_text(json.dumps(status, indent=2))
    attempt = int(time.time())

    def execute(task):
        label = f"{task['arm']}_{task['gene']}_s{task['seed']}"
        with (log_dir / f"{label}_{attempt}.log").open("w") as log:
            subprocess.run(task["command"], stdout=log, stderr=subprocess.STDOUT, check=True)
        result = root / task["arm"] / f"{task['gene']}_learned_hill_s{task['seed']}.json"
        payload = validate_baseline(result, {"record_id": task["gene"], "seed": task["seed"],
                                             "method": "learned_hill", "code_commit": accepted})
        if payload["device"] != "cuda:0":
            raise ValueError(f"non-CUDA diagnostic result: {result}")
        return label

    try:
        def run_arm(arm):
            for task in tasks:
                if task["arm"] == arm:
                    execute(task)
            return arm
        with ThreadPoolExecutor(max_workers=2) as pool:
            completed = list(pool.map(run_arm, (args.only_arm,) if args.only_arm else ("FULL", "EDIT")))
        if args.skip_gate:
            status["status"] = "shards_complete"
            status["completed_tasks"] = len(tasks)
        else:
            gate = root / "diagnostic_gate.json"
            gate_command = [sys.executable, "scripts/a7_proposal_in_loop_gate.py",
                            "--benchmark-fasta", args.benchmark_fasta,
                            "--calibration-dir", args.calibration_dir, "--out", str(gate)]
            for commit in sorted(accepted):
                gate_command.extend(["--accept-code-commit", commit])
            for arm, _checkpoint, checkpoint_sha256 in arms.values():
                gate_command.extend(["--arm", f"{arm},{checkpoint_sha256},{root / arm / '*_learned_hill_s*.json'},{args.baseline_dir}"])
            with (log_dir / f"diagnostic_gate_{attempt}.log").open("w") as log:
                subprocess.run(gate_command, stdout=log, stderr=subprocess.STDOUT, check=True)
            status["status"] = "diagnostic_complete"
            status["diagnostic_gate"] = str(gate)
            status["diagnostic_gate_sha256"] = file_sha256(str(gate))
            status["completed_tasks"] = len(tasks)
    except Exception as error:
        status["status"] = "failed"
        status["error"] = str(error)
        status_path.write_text(json.dumps(status, indent=2))
        raise
    status_path.write_text(json.dumps(status, indent=2))
    print(json.dumps(status))


if __name__ == "__main__":
    main()
