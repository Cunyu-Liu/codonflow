"""Resume an interrupted A7 run from a verified complete-epoch state in a new directory."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.train.run_pretrain import file_sha256, git_commit
from scripts.a7_convergence_audit import validate_run_config
from scripts.a7_run_training import preflight


def prepare_resume(config_path, g0_gate_path):
    config = json.loads(Path(config_path).read_text())
    command = preflight(config_path, g0_gate_path, allow_resume=True)
    source = Path(config["resume"])
    source_dir = source.parent
    out_dir = Path(config["out_dir"])
    if source.name != "training_state.pt" or source_dir == out_dir:
        raise ValueError("resume source must be training_state.pt in a different run directory")
    if out_dir.exists():
        raise FileExistsError(f"refusing to overwrite resume output: {out_dir}")
    history = [json.loads(line) for line in (source_dir / "log.jsonl").read_text().splitlines() if line.strip()]
    if not history or [row["epoch"] for row in history] != list(range(1, len(history) + 1)):
        raise ValueError("resume history must contain complete consecutive epochs")
    import torch
    state = torch.load(source, map_location="cpu", weights_only=True)
    best_epoch = min(range(len(history)), key=lambda index: history[index]["val_loss"]) + 1
    best_value = history[best_epoch - 1]["val_loss"]
    if state["epoch"] != len(history) or state["best_epoch"] != best_epoch:
        raise ValueError("resume state does not match complete epoch history")
    if state["best_val_loss"] != best_value or not state.get("optimizer") or not state["rng"].get("cuda"):
        raise ValueError("resume requires best validation state, optimizer and CUDA RNG")
    validate_run_config(config, state["config"])
    best = torch.load(source_dir / "best.pt", map_location="cpu", weights_only=True)
    if best_epoch == len(history):
        if best.keys() != state["model"].keys() or not all(
                torch.equal(best[key], state["model"][key]) for key in best):
            raise ValueError("best checkpoint does not match the latest best training state")
    source_hashes = {name: file_sha256(str(source_dir / name))
                     for name in ("training_state.pt", "best.pt", "log.jsonl")}
    out_dir.mkdir(parents=True, exist_ok=False)
    frozen_state = out_dir / "resume_input.pt"
    destinations = {"training_state.pt": frozen_state, "best.pt": out_dir / "best.pt",
                    "log.jsonl": out_dir / "log.jsonl"}
    for name, destination in destinations.items():
        shutil.copyfile(source_dir / name, destination)
        if file_sha256(str(destination)) != source_hashes[name]:
            raise IOError(f"resume copy hash mismatch: {name}")
    command[command.index("--resume") + 1] = str(frozen_state)
    provenance = {"protocol": "a7_exact_epoch_resume_v1", "passed": True,
                  "run_id": config["run_id"], "config_path": str(config_path),
                  "config_sha256": file_sha256(str(config_path)), "code_commit": git_commit(),
                  "source_run_dir": str(source_dir), "resume_epoch": len(history),
                  "best_epoch": best_epoch, "best_val_loss": best_value,
                  "source_sha256": source_hashes,
                  "frozen_resume_path": str(frozen_state),
                  "frozen_resume_sha256": source_hashes["training_state.pt"]}
    manifest = out_dir / "resume_provenance.json"
    temporary = manifest.with_suffix(".tmp")
    temporary.write_text(json.dumps(provenance, indent=2))
    temporary.replace(manifest)
    return command, provenance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--g0-gate", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    if not str(Path(config["out_dir"]).resolve()).startswith("/teams/"):
        raise ValueError("resume checkpoints must remain on /teams")
    if args.dry_run:
        command = preflight(args.config, args.g0_gate, allow_resume=True)
        print(json.dumps({"command": command, "dry_run": True}))
        return
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("exact resume requires CUDA; CPU fallback forbidden")
    command, provenance = prepare_resume(args.config, args.g0_gate)
    print(json.dumps({"resume_epoch": provenance["resume_epoch"],
                      "frozen_resume_sha256": provenance["frozen_resume_sha256"]}), flush=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    subprocess.run(command, env=env, check=True)


if __name__ == "__main__":
    main()
