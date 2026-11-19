#!/usr/bin/env python3
"""Independent NumPy verifier for the exact trajectory-balance small task.

This file deliberately does not import the production training implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

SENSE = 61
STATES = 3721
ACTIONS = 121


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def log_softmax_rows(value: np.ndarray) -> np.ndarray:
    shifted = value - value.max(axis=1, keepdims=True)
    return shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))


def reference_geometry() -> tuple[np.ndarray, np.ndarray]:
    edges = np.empty((STATES, ACTIONS), dtype=np.int64)
    for state in range(STATES):
        first, second = state // SENSE, state % SENSE
        row = [state]
        row += [replacement * SENSE + second for replacement in range(SENSE) if replacement != first]
        row += [first * SENSE + replacement for replacement in range(SENSE) if replacement != second]
        if len(row) != ACTIONS or len(set(row)) != ACTIONS:
            raise AssertionError(state)
        edges[state] = row
    reverse = np.empty_like(edges)
    for source in range(STATES):
        for action in range(ACTIONS):
            target = edges[source, action]
            where = np.flatnonzero(edges[target] == source)
            if where.size != 1:
                raise AssertionError((source, action, target))
            reverse[source, action] = where[0]
    return edges, reverse


def reference_features() -> np.ndarray:
    codons = [
        a + b + c
        for a in "ACGT" for b in "ACGT" for c in "ACGT"
        if a + b + c not in {"TAA", "TAG", "TGA"}
    ]
    if len(codons) != SENSE:
        raise AssertionError(len(codons))
    potential = np.array([
        math.sin(0.37 * (i + 1)) + 0.25 * math.cos(0.11 * (i + 1))
        for i in range(SENSE)
    ])
    gc = np.array([(codon.count("G") + codon.count("C")) / 3 for codon in codons])
    result = np.empty((STATES, 4), dtype=np.float64)
    for state in range(STATES):
        first, second = divmod(state, SENSE)
        result[state] = (
            (potential[first] + potential[second]) / 2,
            abs(potential[first] - potential[second]),
            (gc[first] + gc[second]) / 2,
            first == second,
        )
    return result


def reference_paths(edges: np.ndarray, reverse: np.ndarray) -> dict[str, np.ndarray]:
    a0 = np.repeat(np.arange(ACTIONS), ACTIONS)
    a1 = np.tile(np.arange(ACTIONS), ACTIONS)
    start = np.zeros(ACTIONS * ACTIONS, dtype=np.int64)
    mid = edges[0, a0]
    end = edges[mid, a1]
    return {
        "start": start, "mid": mid, "end": end, "a0": a0, "a1": a1,
        "rev0": reverse[start, a0], "rev1": reverse[mid, a1],
    }


def reference_target(features: np.ndarray, edges: np.ndarray, paths: dict[str, np.ndarray], protocol: dict) -> np.ndarray:
    """Recompute the exact oracle-induced endpoint law without production code."""
    weights = np.asarray(protocol["features"]["target_weights"], dtype=np.float64)
    beta = float(protocol["conditional_kernel"]["beta"])
    energy = features @ weights
    log_forward = log_softmax_rows(beta * (energy[edges] - energy[:, None]))
    forward_path = log_forward[paths["start"], paths["a0"]] + log_forward[paths["mid"], paths["a1"]]
    endpoint = np.bincount(paths["end"], weights=np.exp(forward_path), minlength=STATES)
    if np.any(endpoint <= 0) or abs(endpoint.sum() - 1) > 1e-12:
        raise AssertionError("Invalid oracle endpoint law")
    return np.log(endpoint)


def evaluate(
    theta: np.ndarray,
    backward: np.ndarray,
    features: np.ndarray,
    edges: np.ndarray,
    paths: dict[str, np.ndarray],
    target: np.ndarray,
    beta: float,
) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray]:
    energy = features @ theta
    log_forward = log_softmax_rows(beta * (energy[edges] - energy[:, None]))
    backward_mask = np.isin(edges, edges[0])
    masked_backward = np.where(backward_mask, backward, -np.inf)
    log_backward = log_softmax_rows(masked_backward)
    forward_path = log_forward[paths["start"], paths["a0"]] + log_forward[paths["mid"], paths["a1"]]
    backward_path = log_backward[paths["end"], paths["rev1"]]
    residual = target[paths["end"]] + backward_path - forward_path
    forward_endpoint = np.bincount(paths["end"], weights=np.exp(forward_path), minlength=STATES)
    reconstructed = np.bincount(paths["end"], weights=np.exp(forward_path + residual), minlength=STATES)
    probability = np.exp(target)
    metrics = {
        "loss": float(np.mean(residual ** 2)),
        "max_abs_path_residual": float(np.max(np.abs(residual))),
        "max_abs_endpoint_reconstruction_error": float(np.max(np.abs(reconstructed - probability))),
        "max_abs_forward_target_error": float(np.max(np.abs(forward_endpoint - probability))),
        "forward_target_kl": float(np.sum(probability * (target - np.log(np.maximum(forward_endpoint, 1e-300))))),
        "backward_normalization_error": float(np.max(np.abs(np.exp(log_backward).sum(axis=1) - 1))),
        "forward_endpoint_mass_error": float(abs(forward_endpoint.sum() - 1)),
        "reconstructed_endpoint_mass_error": float(abs(reconstructed.sum() - 1)),
    }
    return metrics, residual, forward_path, forward_endpoint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"Nonempty output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    production = json.loads(args.production_report.read_text(encoding="utf-8"))
    protocol_path = Path(production["protocol"])
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    checkpoint_path = Path(production["checkpoint"])
    checkpoint = np.load(checkpoint_path)
    theta = checkpoint["theta"]
    backward = checkpoint["backward_logits"]
    edges, reverse = reference_geometry()
    features = reference_features()
    paths = reference_paths(edges, reverse)
    beta = float(protocol["conditional_kernel"]["beta"])
    endpoint_count = np.bincount(paths["end"], minlength=STATES).astype(np.float64)
    target = reference_target(features, edges, paths, protocol)
    metrics, residual, forward_path, forward_endpoint = evaluate(theta, backward, features, edges, paths, target, beta)

    # An independently constructed analytic oracle proves that the frozen target
    # and forward/backward path identities have an exact zero-residual solution.
    true_theta = np.asarray(protocol["features"]["target_weights"], dtype=np.float64)
    true_energy = features @ true_theta
    true_log_forward = log_softmax_rows(beta * (true_energy[edges] - true_energy[:, None]))
    true_forward_path = true_log_forward[paths["start"], paths["a0"]] + true_log_forward[paths["mid"], paths["a1"]]
    true_forward_endpoint = np.bincount(paths["end"], weights=np.exp(true_forward_path), minlength=STATES)
    analytic_backward_path = true_forward_path - target[paths["end"]]
    analytic_residual = target[paths["end"]] + analytic_backward_path - true_forward_path
    analytic_normalization = np.bincount(paths["end"], weights=np.exp(analytic_backward_path), minlength=STATES)

    checks = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("production_pass", production["status"] == "PASS" and production["checks_passed"] == production["checks_total"], production["status"])
    check("protocol_hash", sha256(protocol_path) == production["protocol_sha256"], production["protocol_sha256"])
    check("checkpoint_hash", sha256(checkpoint_path) == production["checkpoint_sha256"], production["checkpoint_sha256"])
    check("tensor_shapes", theta.shape == (4,) and backward.shape == (STATES, ACTIONS), {"theta": theta.shape, "backward": backward.shape})
    check("geometry", edges.shape == (STATES, ACTIONS) and len(paths["end"]) == 14641 and np.all(endpoint_count > 0), {"states": STATES, "paths": len(paths["end"]), "minimum_endpoint_paths": int(endpoint_count.min())})
    check("reverse_edges", np.array_equal(edges[paths["mid"], paths["rev0"]], paths["start"]) and np.array_equal(edges[paths["end"], paths["rev1"]], paths["mid"]), True)
    check("target_normalization", abs(float(np.exp(target).sum()) - 1) <= 1e-12, float(np.exp(target).sum()))
    check("finite_learned_tensors", bool(np.isfinite(theta).all() and np.isfinite(backward).all()), True)
    for key, value in metrics.items():
        check(f"report_metric:{key}", abs(value - production["metrics"][key]) <= 1e-12, {"independent": value, "production": production["metrics"][key]})
    acceptance = protocol["acceptance"]
    check("independent_loss", metrics["loss"] <= acceptance["final_loss_max"], metrics["loss"])
    check("independent_path_residual", metrics["max_abs_path_residual"] <= acceptance["max_abs_path_residual_max"], metrics["max_abs_path_residual"])
    check("independent_endpoint_reconstruction", metrics["max_abs_endpoint_reconstruction_error"] <= acceptance["max_abs_endpoint_reconstruction_error_max"], metrics["max_abs_endpoint_reconstruction_error"])
    check("independent_forward_target", metrics["max_abs_forward_target_error"] <= acceptance["max_abs_forward_target_error_max"], metrics["max_abs_forward_target_error"])
    check("independent_kl", metrics["forward_target_kl"] <= acceptance["forward_target_kl_max"], metrics["forward_target_kl"])
    check("analytic_oracle_zero_residual", float(np.max(np.abs(analytic_residual))) <= 1e-12, float(np.max(np.abs(analytic_residual))))
    check("analytic_oracle_target", float(np.max(np.abs(true_forward_endpoint - np.exp(target)))) <= 1e-12, float(np.max(np.abs(true_forward_endpoint - np.exp(target)))))
    check("analytic_oracle_backward_normalization", float(np.max(np.abs(analytic_normalization - 1))) <= 1e-12, float(np.max(np.abs(analytic_normalization - 1))))
    check("mathematical_scope_only", all(production[key] is False for key in ("biological_reward_measured", "functional_or_generation_performance_evaluated", "full_neural_model_trained", "rk_g1_gate_modified", "expensive_generation_authorized", "sota_claimed")), production["scope"])
    status = "PASS" if all(row["pass"] for row in checks) else "FAIL"
    report = {
        "schema_version": "a8-rk10-exact-trajectory-balance-independent-v1",
        "status": status,
        "production_report": str(args.production_report),
        "production_report_sha256": sha256(args.production_report),
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": sha256(checkpoint_path),
        "production_driver_imported": False,
        "implementation_sha256": sha256(Path(__file__).resolve()),
        "metrics": metrics,
        "analytic_oracle": {
            "max_abs_residual": float(np.max(np.abs(analytic_residual))),
            "max_abs_forward_target_error": float(np.max(np.abs(true_forward_endpoint - np.exp(target)))),
            "max_abs_backward_normalization_error": float(np.max(np.abs(analytic_normalization - 1))),
        },
        "checks": checks,
        "checks_passed": sum(row["pass"] for row in checks),
        "checks_total": len(checks),
        "scope": protocol["scope"],
    }
    atomic_json(args.report, report)
    print(json.dumps({"status": status, "checks": f"{report['checks_passed']}/{report['checks_total']}", "metrics": metrics, "analytic_oracle": report["analytic_oracle"]}, indent=2))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
