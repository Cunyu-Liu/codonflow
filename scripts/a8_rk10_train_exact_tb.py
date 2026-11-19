#!/usr/bin/env python3
"""Exact small-state conditional trajectory-balance optimization.

This is a mathematical optimization smoke on a frozen synthetic potential. It is
not biological generator training and does not evaluate functional performance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch

SENSE = 61
N_STATES = SENSE * SENSE
N_ACTIONS = 1 + 2 * (SENSE - 1)
START = 0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sense_codons() -> list[str]:
    stops = {"TAA", "TAG", "TGA"}
    return [a + b + c for a in "ACGT" for b in "ACGT" for c in "ACGT" if a + b + c not in stops]


def build_geometry() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return destinations, parents, and reverse-action indices for all states."""
    transitions = np.zeros((N_STATES, N_ACTIONS), dtype=np.int64)
    for state in range(N_STATES):
        c0, c1 = divmod(state, SENSE)
        destinations = [state]
        destinations.extend(c * SENSE + c1 for c in range(SENSE) if c != c0)
        destinations.extend(c0 * SENSE + c for c in range(SENSE) if c != c1)
        transitions[state] = destinations
    # Every legal edit is reversible, so the same construction gives legal parents.
    parents = transitions.copy()
    reverse = np.zeros((N_STATES, N_ACTIONS), dtype=np.int64)
    for state in range(N_STATES):
        for action in range(N_ACTIONS):
            parent_state = state
            child_state = transitions[state, action]
            matches = np.flatnonzero(parents[child_state] == parent_state)
            if len(matches) != 1:
                raise AssertionError((state, action, child_state, matches))
            reverse[state, action] = matches[0]
    return transitions, parents, reverse


def build_features() -> tuple[np.ndarray, list[str]]:
    codons = sense_codons()
    if len(codons) != SENSE:
        raise AssertionError(len(codons))
    scalar = np.array([
        math.sin((index + 1) * 0.37) + 0.25 * math.cos((index + 1) * 0.11)
        for index in range(SENSE)
    ], dtype=np.float64)
    gc = np.array([sum(base in "GC" for base in codon) / 3.0 for codon in codons])
    features = np.zeros((N_STATES, 4), dtype=np.float64)
    for state in range(N_STATES):
        c0, c1 = divmod(state, SENSE)
        features[state] = [
            0.5 * (scalar[c0] + scalar[c1]),
            abs(scalar[c0] - scalar[c1]),
            0.5 * (gc[c0] + gc[c1]),
            float(c0 == c1),
        ]
    return features, codons


def build_paths(transitions: np.ndarray, reverse: np.ndarray) -> dict[str, np.ndarray]:
    actions = np.arange(N_ACTIONS, dtype=np.int64)
    a0 = np.repeat(actions, N_ACTIONS)
    a1 = np.tile(actions, N_ACTIONS)
    start = np.zeros(N_ACTIONS * N_ACTIONS, dtype=np.int64)
    mid = transitions[START, a0]
    end = transitions[mid, a1]
    rev0 = reverse[start, a0]
    rev1 = reverse[mid, a1]
    if not np.array_equal(parents_for_check(transitions)[mid, rev0], start):
        raise AssertionError("First reversed edges do not return to start")
    if not np.array_equal(parents_for_check(transitions)[end, rev1], mid):
        raise AssertionError("Second reversed edges do not return to midpoint")
    return {"start": start, "mid": mid, "end": end, "a0": a0, "a1": a1, "rev0": rev0, "rev1": rev1}


def parents_for_check(transitions: np.ndarray) -> np.ndarray:
    return transitions


def target_logprob(features: np.ndarray, transitions: np.ndarray, paths: dict[str, np.ndarray], protocol: dict) -> np.ndarray:
    """Exact oracle-induced endpoint law, including every per-step normalizer."""
    weights = np.asarray(protocol["features"]["target_weights"], dtype=np.float64)
    beta = float(protocol["conditional_kernel"]["beta"])
    energy = features @ weights
    logits = beta * (energy[transitions] - energy[:, None])
    logits = logits - logits.max(axis=1, keepdims=True)
    log_forward = logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))
    forward_path = log_forward[paths["start"], paths["a0"]] + log_forward[paths["mid"], paths["a1"]]
    endpoint = np.bincount(paths["end"], weights=np.exp(forward_path), minlength=N_STATES)
    if np.any(endpoint <= 0) or abs(endpoint.sum() - 1.0) > 1e-12:
        raise AssertionError("Oracle endpoint must have full support and unit mass")
    return np.log(endpoint)


def torch_residual(
    theta: torch.Tensor,
    backward_logits: torch.Tensor,
    features: torch.Tensor,
    transitions: torch.Tensor,
    paths: dict[str, torch.Tensor],
    target: torch.Tensor,
    beta: float,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    energy = features @ theta
    forward_logits = beta * (energy[transitions] - energy[:, None])
    log_forward = torch.log_softmax(forward_logits, dim=1)
    reachable_mid = transitions[START]
    backward_mask = torch.isin(transitions, reachable_mid)
    log_backward = torch.log_softmax(backward_logits.masked_fill(~backward_mask, -torch.inf), dim=1)
    forward_path = (
        log_forward[paths["start"], paths["a0"]]
        + log_forward[paths["mid"], paths["a1"]]
    )
    # With one fixed start, the first reverse step is deterministic and has log p=0.
    backward_path = log_backward[paths["end"], paths["rev1"]]
    residual = target[paths["end"]] + backward_path - forward_path
    return residual, forward_path, log_forward, log_backward


def numpy_metrics(
    theta: np.ndarray,
    backward_logits: np.ndarray,
    features: np.ndarray,
    transitions: np.ndarray,
    paths: dict[str, np.ndarray],
    target: np.ndarray,
    beta: float,
) -> dict:
    """Numpy evaluation used for saved-report metrics; independent verifier reimplements it."""
    energy = features @ theta
    logits = beta * (energy[transitions] - energy[:, None])
    logits = logits - logits.max(axis=1, keepdims=True)
    log_forward = logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))
    backward_mask = np.isin(transitions, transitions[START])
    masked_backward = np.where(backward_mask, backward_logits, -np.inf)
    shifted = masked_backward - masked_backward.max(axis=1, keepdims=True)
    log_backward = shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))
    forward_path = log_forward[paths["start"], paths["a0"]] + log_forward[paths["mid"], paths["a1"]]
    backward_path = log_backward[paths["end"], paths["rev1"]]
    residual = target[paths["end"]] + backward_path - forward_path
    forward_endpoint = np.bincount(paths["end"], weights=np.exp(forward_path), minlength=N_STATES)
    reconstructed = np.bincount(paths["end"], weights=np.exp(forward_path + residual), minlength=N_STATES)
    target_probability = np.exp(target)
    kl = float(np.sum(target_probability * (target - np.log(np.maximum(forward_endpoint, 1e-300)))))
    return {
        "loss": float(np.mean(residual ** 2)),
        "max_abs_path_residual": float(np.max(np.abs(residual))),
        "max_abs_endpoint_reconstruction_error": float(np.max(np.abs(reconstructed - target_probability))),
        "max_abs_forward_target_error": float(np.max(np.abs(forward_endpoint - target_probability))),
        "forward_target_kl": kl,
        "backward_normalization_error": float(np.max(np.abs(np.exp(log_backward).sum(axis=1) - 1.0))),
        "forward_endpoint_mass_error": float(abs(forward_endpoint.sum() - 1.0)),
        "reconstructed_endpoint_mass_error": float(abs(reconstructed.sum() - 1.0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    started = time.time()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if protocol["schema_version"] != "a8-rk10-exact-trajectory-balance-protocol-v1":
        raise ValueError("Unexpected protocol")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"Nonempty output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(int(protocol["optimization"]["seed"]))
    np.random.seed(int(protocol["optimization"]["seed"]))
    torch.use_deterministic_algorithms(True)
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is required by the frozen protocol but is unavailable")

    transitions_np, parents_np, reverse_np = build_geometry()
    features_np, codons = build_features()
    paths_np = build_paths(transitions_np, reverse_np)
    target_np = target_logprob(features_np, transitions_np, paths_np, protocol)
    beta = float(protocol["conditional_kernel"]["beta"])
    steps = int(protocol["optimization"]["fixed_steps"])
    if (N_STATES, N_ACTIONS, len(paths_np["end"])) != (3721, 121, 14641):
        raise AssertionError("Frozen small-state dimensions changed")

    transitions = torch.as_tensor(transitions_np, dtype=torch.long, device=device)
    features = torch.as_tensor(features_np, dtype=torch.float64, device=device)
    target = torch.as_tensor(target_np, dtype=torch.float64, device=device)
    paths = {key: torch.as_tensor(value, dtype=torch.long, device=device) for key, value in paths_np.items()}
    theta = torch.nn.Parameter(torch.zeros(4, dtype=torch.float64, device=device))
    backward_logits = torch.nn.Parameter(torch.zeros((N_STATES, N_ACTIONS), dtype=torch.float64, device=device))
    opt = protocol["optimization"]
    optimizer = torch.optim.Adam([theta, backward_logits], lr=float(opt["learning_rate_initial"]))

    with torch.no_grad():
        initial_residual, _, _, _ = torch_residual(theta, backward_logits, features, transitions, paths, target, beta)
        initial_loss = float(initial_residual.pow(2).mean().cpu())
        initial_max = float(initial_residual.abs().max().cpu())
    history = [{"step": 0, "loss": initial_loss, "max_abs_residual": initial_max, "lr": float(opt["learning_rate_initial"])}]
    for step in range(1, steps + 1):
        fraction = (step - 1) / max(steps - 1, 1)
        lr = float(opt["learning_rate_initial"]) + fraction * (float(opt["learning_rate_final"]) - float(opt["learning_rate_initial"]))
        for group in optimizer.param_groups:
            group["lr"] = lr
        optimizer.zero_grad(set_to_none=True)
        residual, _, _, _ = torch_residual(theta, backward_logits, features, transitions, paths, target, beta)
        loss = residual.pow(2).mean()
        if not torch.isfinite(loss):
            raise FloatingPointError(f"Nonfinite loss at step {step}")
        loss.backward()
        optimizer.step()
        if step == 1 or step % int(opt["history_every"]) == 0 or step == steps:
            history.append({
                "step": step,
                "loss": float(loss.detach().cpu()),
                "max_abs_residual": float(residual.detach().abs().max().cpu()),
                "lr": lr,
            })

    theta_np = theta.detach().cpu().numpy()
    backward_np = backward_logits.detach().cpu().numpy()
    checkpoint = args.output_dir / "final_checkpoint.npz"
    np.savez(checkpoint, theta=theta_np, backward_logits=backward_np)
    metrics = numpy_metrics(theta_np, backward_np, features_np, transitions_np, paths_np, target_np, beta)
    acceptance = protocol["acceptance"]
    checks = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("frozen_dimensions", len(paths_np["end"]) == 14641 and N_STATES == 3721 and N_ACTIONS == 121, {"states": N_STATES, "actions": N_ACTIONS, "paths": len(paths_np["end"])})
    check("fixed_step_optimization", len(history) == 42 and history[-1]["step"] == steps, {"history_rows": len(history), "steps": steps})
    check("loss_decreased", metrics["loss"] < initial_loss, {"initial": initial_loss, "final": metrics["loss"]})
    check("final_loss", metrics["loss"] <= float(acceptance["final_loss_max"]), metrics["loss"])
    check("path_residual", metrics["max_abs_path_residual"] <= float(acceptance["max_abs_path_residual_max"]), metrics["max_abs_path_residual"])
    check("endpoint_reconstruction", metrics["max_abs_endpoint_reconstruction_error"] <= float(acceptance["max_abs_endpoint_reconstruction_error_max"]), metrics["max_abs_endpoint_reconstruction_error"])
    check("forward_target", metrics["max_abs_forward_target_error"] <= float(acceptance["max_abs_forward_target_error_max"]), metrics["max_abs_forward_target_error"])
    check("forward_target_kl", metrics["forward_target_kl"] <= float(acceptance["forward_target_kl_max"]), metrics["forward_target_kl"])
    check("backward_normalization", metrics["backward_normalization_error"] <= float(acceptance["backward_normalization_error_max"]), metrics["backward_normalization_error"])
    check("finite_tensors", bool(np.isfinite(theta_np).all() and np.isfinite(backward_np).all()), True)
    check("mathematical_scope_only", all(value is False for value in protocol["boundaries"].values()), protocol["boundaries"])
    status = "PASS" if all(row["pass"] for row in checks) else "FAIL"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True).strip()
    report = {
        "schema_version": "a8-rk10-exact-trajectory-balance-training-v1",
        "status": status,
        "protocol": str(args.protocol),
        "protocol_sha256": sha256(args.protocol),
        "source_commit_at_start": commit,
        "implementation_sha256": sha256(Path(__file__).resolve()),
        "device": str(device),
        "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else "CPU",
        "dtype": "float64",
        "deterministic_algorithms": True,
        "geometry": {"states": N_STATES, "actions_per_state": N_ACTIONS, "paths": len(paths_np["end"]), "codons": len(codons)},
        "theta": theta_np.tolist(),
        "target_weights": protocol["features"]["target_weights"],
        "initial_loss": initial_loss,
        "initial_max_abs_residual": initial_max,
        "metrics": metrics,
        "history": history,
        "checks": checks,
        "checks_passed": sum(row["pass"] for row in checks),
        "checks_total": len(checks),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256(checkpoint),
        "wall_time_seconds": time.time() - started,
        "biological_reward_measured": False,
        "functional_or_generation_performance_evaluated": False,
        "full_neural_model_trained": False,
        "rk_g1_gate_modified": False,
        "expensive_generation_authorized": False,
        "sota_claimed": False,
        "scope": protocol["scope"],
    }
    atomic_json(args.report, report)
    print(json.dumps({"status": status, "checks": f"{report['checks_passed']}/{report['checks_total']}", "metrics": metrics, "checkpoint_sha256": report["checkpoint_sha256"], "wall_time_seconds": report["wall_time_seconds"]}, indent=2))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
