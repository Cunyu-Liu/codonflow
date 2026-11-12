"""Run independent unique18 gene shards with bounded GPU concurrency."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.dataset import read_fasta


def pending_records(benchmark_fasta, output_dir, seed):
    output_dir = Path(output_dir)
    pending = []
    for header, _sequence in read_fasta(benchmark_fasta):
        record_id = header.split()[0]
        path = output_dir / f"{record_id}_s{seed}.json"
        if path.exists() and json.loads(path.read_text()).get("status") == "done":
            continue
        pending.append(record_id)
    return pending


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--n-solutions", type=int, default=100)
    args = parser.parse_args()
    records = pending_records(args.benchmark_fasta, args.output_dir, args.seed)
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()

    def run(record_id):
        log_path = log_dir / f"{record_id}_s{args.seed}.log"
        command = [
            sys.executable, "scripts/run_a6_baselines.py",
            "--benchmark-fasta", args.benchmark_fasta, "--record-id", record_id,
            "--rscu-json", args.rscu_json, "--out-dir", args.output_dir,
            "--n-solutions", str(args.n_solutions), "--seed", str(args.seed), "--resume",
        ]
        with log_path.open("w") as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        return record_id

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        completed = list(pool.map(run, records))
    print(json.dumps({"seed": args.seed, "n_completed_this_run": len(completed),
                      "completed": completed}))


if __name__ == "__main__":
    main()
