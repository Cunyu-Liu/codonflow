"""Execute actual-budget external recomputation with bounded CPU workers."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.dataset import read_fasta


def expected_inputs(records, input_dir, seeds=(0, 1, 2)):
    paths = [Path(input_dir) / f"{record}_s{seed}.json"
             for record in records for seed in seeds]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise ValueError(f"missing external inputs: {missing}")
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--calibration-dir", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        raise ValueError("workers must be between 1 and 16")
    if not str(Path(args.out_root).resolve()).startswith("/teams/"):
        raise ValueError("external outputs must remain on /teams")
    records = [header.split()[0] for header, _ in read_fasta(args.benchmark_fasta)]
    inputs = expected_inputs(records, args.input_dir)
    root = Path(args.out_root)
    root.mkdir(parents=True, exist_ok=True)
    status_path = root / "execution_status.json"
    if status_path.exists() and not args.resume:
        raise FileExistsError(f"refusing to overwrite execution status: {status_path}")
    previous = json.loads(status_path.read_text()) if status_path.exists() else None
    tasks = []
    for path in inputs:
        record = path.name.rsplit("_s", 1)[0]
        seed = int(path.stem.rsplit("_s", 1)[1])
        out = root / record / f"{path.stem}.json"
        if out.exists():
            if not args.resume:
                raise FileExistsError(f"refusing to overwrite external audit: {out}")
            existing = json.loads(out.read_text())
            if (existing.get("protocol") != "a7_external_actual_budget_v1"
                    or existing.get("input_sha256") != hashlib.sha256(path.read_bytes()).hexdigest()):
                raise ValueError(f"external resume mismatch: {out}")
            continue
        tasks.append((path, out, seed))
    status = {"protocol": "a7_external_actual_budget_execution_v1", "status": "ready" if args.dry_run else "running",
              "scientific_gate_passed": False, "not_a_method_ranking": True,
              "n_inputs": len(inputs), "n_new_tasks": len(tasks), "workers": args.workers,
              "benchmark_fasta": args.benchmark_fasta, "out_root": str(root),
              "previous_status": previous}
    if args.dry_run:
        print(json.dumps(status))
        return
    status_path.write_text(json.dumps(status, indent=2))

    def execute(task):
        path, out, _seed = task
        out.parent.mkdir(parents=True, exist_ok=True)
        with (root / "logs" / f"{path.stem}.log").open("w") as log:
            subprocess.run([sys.executable, "scripts/a7_recompute_external.py", "--input", str(path),
                            "--benchmark-fasta", args.benchmark_fasta,
                            "--calibration-dir", args.calibration_dir,
                            "--rscu-json", args.rscu_json, "--out", str(out)],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        return {"path": str(out), "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}

    (root / "logs").mkdir(exist_ok=True)
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            outputs = list(pool.map(execute, tasks))
        status.update({"status": "external_reference_complete", "outputs": outputs})
    except Exception as error:
        status.update({"status": "failed", "error": str(error)})
        status_path.write_text(json.dumps(status, indent=2))
        raise
    status_path.write_text(json.dumps(status, indent=2))
    print(json.dumps(status))


if __name__ == "__main__":
    main()
