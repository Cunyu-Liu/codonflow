"""Audit a completed A7 training run and freeze its CUDA-verified checkpoint manifest."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.train.run_pretrain import file_sha256, git_commit


def validate_history(history, reported, log_rows, tolerance=1e-3, patience=3):
    if len(history) < patience + 1 or not all(math.isfinite(value) and value > 0 for value in history):
        raise ValueError("finite positive validation history is required")
    if [row["epoch"] for row in log_rows] != list(range(1, len(history) + 1)):
        raise ValueError("validation epochs must be complete and consecutive")
    if [row["val_loss"] for row in log_rows] != history:
        raise ValueError("convergence history does not match log.jsonl")
    relative_improvements = [(previous - current) / abs(previous)
                             for previous, current in zip(history, history[1:])]
    if len(relative_improvements) < patience or not all(
            improvement < tolerance for improvement in relative_improvements[-patience:]):
        raise ValueError("registered validation plateau has not been reached")
    best_epoch = min(range(len(history)), key=history.__getitem__) + 1
    best_value = history[best_epoch - 1]
    if reported["epoch"] != len(history) or reported["best_epoch"] != best_epoch:
        raise ValueError("reported epoch does not match validation history")
    if reported["best_val_loss"] != best_value or reported["last_val_loss"] != history[-1]:
        raise ValueError("reported validation loss does not match history")
    return {"n_epochs": len(history), "best_epoch": best_epoch,
            "best_val_loss": best_value, "last_val_loss": history[-1],
            "last_three_relative_improvements": relative_improvements[-patience:],
            "relative_tolerance": tolerance, "patience_epochs": patience}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--g0-gate", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("convergence audit requires CUDA; CPU fallback forbidden")
    config = json.loads(Path(args.config).read_text())
    if not str(Path(config["out_dir"]).resolve()).startswith("/teams/"):
        raise ValueError("checkpoints and audit artifacts must remain on /teams")
    if json.loads(Path(args.g0_gate).read_text()).get("passed") is not True:
        raise ValueError("G0 evidence is not accepted")
    out_dir = Path(config["out_dir"])
    names = ("best.pt", "last.pt", "training_state.pt", "converged.pt", "converged.json", "log.jsonl")
    missing = [name for name in names if not (out_dir / name).is_file()]
    if missing:
        raise ValueError(f"training is not complete; missing {missing}")
    history_check = validate_history(
        json.loads((out_dir / "converged.json").read_text())["history"],
        json.loads((out_dir / "converged.json").read_text()),
        [json.loads(line) for line in (out_dir / "log.jsonl").read_text().splitlines() if line.strip()],
        config["convergence"]["relative_tolerance"], config["convergence"]["patience_epochs"],
    )
    run_config = json.loads((out_dir / "run_config.json").read_text())
    for key in ("train_fasta", "val_fasta", "d_model", "n_layers", "n_heads", "dropout",
                "seed", "validation_seed", "token_only_at_edits", "corruption"):
        if run_config[key] != config[key]:
            raise ValueError(f"run configuration mismatch: {key}")
    for key, hash_key in (("train_fasta", "train_sha256"), ("val_fasta", "val_sha256")):
        if file_sha256(config[key]) != config[hash_key] or run_config[hash_key] != config[hash_key]:
            raise ValueError(f"data hash mismatch: {key}")
    current_commit = git_commit()
    run_commit = run_config["code_commit"]
    subprocess.run(["git", "merge-base", "--is-ancestor", run_commit, current_commit], check=True)
    status = subprocess.check_output(["git", "status", "--porcelain"], text=True)
    if status.strip():
        raise ValueError("convergence audit requires a clean code worktree")
    device = torch.device("cuda:0")
    states = {name: torch.load(out_dir / name, map_location="cpu", weights_only=True)
              for name in ("best.pt", "last.pt", "training_state.pt", "converged.pt")}
    training = states["training_state.pt"]
    if training["best_epoch"] != history_check["best_epoch"] or training["epoch"] != history_check["n_epochs"]:
        raise ValueError("training_state epoch mismatch")
    if not training.get("optimizer") or not training["rng"].get("cuda"):
        raise ValueError("optimizer and CUDA RNG state must be preserved")
    from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer
    model = EditFlowTransformer(EditFlowConfig(d_model=config["d_model"], n_layers=config["n_layers"],
                                               n_heads=config["n_heads"], dropout=config["dropout"])).to(device)
    for name, state in states.items():
        weights = state["model"] if name == "training_state.pt" else state
        model.load_state_dict(weights)
    if not next(model.parameters()).is_cuda:
        raise RuntimeError("checkpoint validation did not use CUDA")
    ids = torch.zeros((1, 8), dtype=torch.long, device=device)
    model.eval()
    with torch.no_grad():
        blank, token = model(ids)
        if not torch.isfinite(blank).all() or not torch.isfinite(token).all():
            raise RuntimeError("nonfinite CUDA checkpoint forward")
    torch.cuda.synchronize()
    if any(torch.equal(states["best.pt"][key], states["converged.pt"][key]) is False
           for key in states["best.pt"]):
        raise ValueError("converged.pt is not the best validation checkpoint")
    hashes = {name: file_sha256(str(out_dir / name)) for name in names}
    result = {"protocol": "a7_convergence_audit_v1", "passed": True,
              "run_id": config["run_id"], "config_path": args.config,
              "config_sha256": file_sha256(args.config), "g0_gate_sha256": file_sha256(args.g0_gate),
              "run_code_commit": run_commit, "audit_code_commit": current_commit,
              "code_dirty": False, "device": str(device), "cuda_forward_finite": True,
              "history": history_check, "checkpoint_sha256": hashes,
              "checkpoint_paths": {name: str(out_dir / name) for name in names}}
    out = Path(args.out)
    if not str(out.resolve()).startswith("/teams/"):
        raise ValueError("audit output must remain on /teams")
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(out.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(out)
    print(json.dumps({"out": str(out), "passed": True, "converged_sha256": hashes["converged.pt"]}))


if __name__ == "__main__":
    main()
