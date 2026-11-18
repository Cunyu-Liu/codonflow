"""Generate fixed-500 protein-only external candidates with strict resume."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.dataset import read_fasta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("generation500 allows 1-4 concurrent workers")
    if not str(Path(args.out_root).resolve()).startswith("/teams/"):
        raise ValueError("generation outputs must remain on /teams")
    records = [(header.split()[0], seed) for header, _ in read_fasta(args.benchmark_fasta)
               for seed in (0, 1, 2)]
    root = Path(args.out_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    status_path = root / "execution_status.json"
    if status_path.exists() and not args.resume:
        raise FileExistsError(f"refusing to overwrite execution status: {status_path}")
    previous = json.loads(status_path.read_text()) if status_path.exists() else None
    tasks = []
    for record, seed in records:
        path = root / f"{record}_s{seed}.json"
        if path.exists():
            if not args.resume:
                raise FileExistsError(f"refusing to overwrite generation: {path}")
            payload = json.loads(path.read_text())
            if (payload.get("status") != "done" or payload.get("record_id") != record
                    or payload.get("seed") != seed or payload.get("protocol") != "a6_baselines_v1"):
                raise ValueError(f"generation resume mismatch: {path}")
            for method in ("codongpt", "gemorna"):
                result = payload["methods"][method]
                if result["status"] not in ("done", "architectural_exclusion") or result.get("n_requested") != 500:
                    raise ValueError(f"generation500 resume mismatch: {path} {method}")
            continue
        tasks.append((record, seed))
    status = {"protocol": "a7_external_generation500_v1", "status": "ready" if args.dry_run else "running",
              "scientific_gate_passed": False, "n_tasks": len(records), "n_new_tasks": len(tasks),
              "request_n": 500, "workers": args.workers, "out_root": str(root),
              "previous_status": previous}
    if args.dry_run:
        print(json.dumps(status))
        return
    status_path.write_text(json.dumps(status, indent=2))

    def execute(task):
        record, seed = task
        with (root / "logs" / f"{record}_s{seed}.log").open("w") as log:
            subprocess.run([sys.executable, "scripts/run_a6_baselines.py", "--benchmark-fasta", args.benchmark_fasta,
                            "--rscu-json", args.rscu_json, "--out-dir", args.out_root,
                            "--methods", "codongpt", "gemorna", "--n-solutions", "500",
                            "--record-id", record, "--seed", str(seed)],
                           stdout=log, stderr=subprocess.STDOUT, check=True,
                           env={**os.environ, "CODONFLOW_GEMORNA_PERSISTENT": "0"})
        out = root / f"{record}_s{seed}.json"
        payload = json.loads(out.read_text())
        if payload["status"] != "done":
            raise ValueError(f"incomplete generation: {out}")
        return {"path": str(out), "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            outputs = list(pool.map(execute, tasks))
        status.update({"status": "generation_complete", "outputs": outputs})
    except Exception as error:
        status.update({"status": "failed", "error": str(error)})
        status_path.write_text(json.dumps(status, indent=2))
        raise
    status_path.write_text(json.dumps(status, indent=2))
    print(json.dumps(status))


if __name__ == "__main__":
    main()
