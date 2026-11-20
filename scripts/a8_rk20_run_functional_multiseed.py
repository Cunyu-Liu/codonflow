#!/usr/bin/env python3
"""Execute the six frozen RK20 training runs sequentially, without selection."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--repo-root", default="/home/codonflow-a8-rk")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["status"] != "PASS_PREPARATION_NEW_RESULTS_NOT_READ":
        raise ValueError("preparation manifest is not in the frozen pre-result state")
    protocol = json.loads(Path(manifest["protocol"]).read_text(encoding="utf-8"))
    train_script = repo / protocol["training_contract"]["script"]
    if sha256(train_script) != protocol["training_contract"]["script_sha256"]:
        raise ValueError("training script changed after protocol freeze")
    output_root = Path(manifest["output_root"])
    execution = {
        "schema": "a8-rk20-functional-multiseed-execution-v1",
        "status": "RUNNING",
        "protocol_sha256": manifest["protocol_sha256"],
        "manifest_sha256": sha256(manifest_path),
        "python": sys.executable,
        "started_unix": time.time(),
        "runs": [],
        "test_or_ood_selection": False,
        "functional_untouched_evaluated": False,
    }
    execution_path = output_root / "execution_status.json"
    atomic_json(execution_path, execution)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo / "src")

    for entry in manifest["entries"]:
        if entry["status"] == "reuse_frozen":
            execution["runs"].append({**entry, "execution": "reused_frozen_output"})
            atomic_json(execution_path, execution)
            continue
        output = Path(entry["output_dir"])
        log_path = Path(entry["log"])
        run_record = {**entry, "execution": "pending"}
        if output.exists():
            summary_path = output / "run_summary.json"
            if not summary_path.is_file():
                raise FileExistsError(f"partial or unexpected output directory requires manual review: {output}")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if summary["training"]["seed"] != entry["seed"] or summary["ablation"] != entry["arm"]:
                raise ValueError(f"existing run does not match manifest: {output}")
            if summary["hashes"]["config_sha256"] != entry["config_sha256"]:
                raise ValueError(f"existing run config hash mismatch: {output}")
            run_record["execution"] = "reused_verified_completed_run"
            execution["runs"].append(run_record)
            atomic_json(execution_path, execution)
            continue
        command = [
            sys.executable,
            str(train_script),
            "--data", protocol["data"]["functional_csv"],
            "--config", entry["config"],
            "--output-dir", str(output),
            "--device", "cuda",
        ]
        run_record["command"] = command
        run_record["started_unix"] = time.time()
        run_record["execution"] = "running"
        execution["runs"].append(run_record)
        atomic_json(execution_path, execution)
        with log_path.open("x", encoding="utf-8") as log:
            completed = subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        run_record["returncode"] = completed.returncode
        run_record["elapsed_seconds"] = time.time() - run_record["started_unix"]
        if completed.returncode != 0:
            run_record["execution"] = "failed"
            execution["status"] = "FAILED"
            atomic_json(execution_path, execution)
            raise RuntimeError(f"training failed for {entry['model']} seed {entry['seed']}; see {log_path}")
        summary = json.loads((output / "run_summary.json").read_text(encoding="utf-8"))
        if summary["training"]["seed"] != entry["seed"] or summary["ablation"] != entry["arm"]:
            raise ValueError("completed run identity mismatch")
        if summary["hashes"]["data_sha256"] != manifest["data_sha256"]:
            raise ValueError("completed run data hash mismatch")
        if summary["hashes"]["config_sha256"] != entry["config_sha256"]:
            raise ValueError("completed run config hash mismatch")
        if summary["hashes"]["script_sha256"] != manifest["training_script_sha256"]:
            raise ValueError("completed run training script hash mismatch")
        run_record["execution"] = "completed"
        run_record["predictions_sha256"] = sha256(output / "predictions.csv")
        run_record["checkpoint_sha256"] = summary["hashes"]["checkpoint_sha256"]
        run_record["selected_epoch_by_dev_only"] = summary["selected_epoch"]
        run_record["training_seconds"] = summary["training"]["elapsed_seconds"]
        run_record["forward_passes"] = summary["training"]["forward_passes"]
        atomic_json(execution_path, execution)

    execution["status"] = "PASS_ALL_FROZEN_RUNS_COMPLETE_PENDING_COMPARISON"
    execution["finished_unix"] = time.time()
    execution["elapsed_seconds"] = execution["finished_unix"] - execution["started_unix"]
    atomic_json(execution_path, execution)
    audit_copy = repo / protocol["audit_root"] / "rk20_functional_multiseed_execution_v1.json"
    atomic_json(audit_copy, execution)
    print(json.dumps({"status": execution["status"], "elapsed_seconds": execution["elapsed_seconds"], "runs": len(execution["runs"])}, indent=2))


if __name__ == "__main__":
    main()
