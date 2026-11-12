"""Launch a frozen A7 training arm only after G0 and CUDA checks pass."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.train.run_pretrain import file_sha256


def training_command(config):
    if config.get("status") != "frozen_pending_g0" or config.get("corruption") != "synonymous":
        raise ValueError("training config is not a frozen synonymous pending-G0 arm")
    if config.get("resume") is not None or config.get("max_epochs") is not None or config.get("max_steps") is not None:
        raise ValueError("old checkpoint resume or step-bounded training is forbidden")
    command = [
        sys.executable, "-m", "codonflow.train.run_pretrain",
        "--train-fasta", config["train_fasta"], "--val-fasta", config["val_fasta"],
        "--out-dir", config["out_dir"], "--corruption", "synonymous",
        "--d-model", str(config["d_model"]), "--n-layers", str(config["n_layers"]),
        "--n-heads", str(config["n_heads"]), "--dropout", str(config["dropout"]),
        "--lr", str(config["lr"]), "--wd", str(config["wd"]),
        "--batch-tokens", str(config["batch_tokens"]), "--max-batch", str(config["max_batch"]),
        "--grad-accum", str(config["grad_accum"]), "--grad-clip", str(config["grad_clip"]),
        "--val-batch-tokens", str(config["val_batch_tokens"]), "--seed", str(config["seed"]),
        "--val-micro-batch-tokens", str(config.get("val_micro_batch_tokens", 4000)),
        "--validation-seed", str(config["validation_seed"]),
        "--gpu-mem-fraction", str(config["gpu_mem_fraction"]),
    ]
    if config["token_only_at_edits"]:
        command.append("--token-only-at-edits")
    return command


def preflight(config_path, g0_gate_path):
    config = json.loads(Path(config_path).read_text())
    gate = json.loads(Path(g0_gate_path).read_text())
    if not gate.get("passed"):
        raise ValueError("G0 has not passed")
    for key in ("train_fasta", "val_fasta"):
        if not Path(config[key]).exists():
            raise FileNotFoundError(config[key])
        hash_key = "train_sha256" if key == "train_fasta" else "val_sha256"
        if file_sha256(config[key]) != config[hash_key]:
            raise ValueError(f"data hash mismatch: {key}")
    return training_command(config)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--g0-gate", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    command = preflight(args.config, args.g0_gate)
    print(json.dumps({"command": command, "dry_run": args.dry_run}))
    if args.dry_run:
        return
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("A7 training requires CUDA; CPU fallback forbidden")
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    subprocess.run(command, env=env, check=True)


if __name__ == "__main__":
    main()
