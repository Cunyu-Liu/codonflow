#!/usr/bin/env python3
"""Frozen synthetic CUDA smoke for the minimal neural CodonFlow-RK contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch

from codonflow.core.codon import AA_OF_INDEX, AA_TO_CODONS_INDEX, CODON_TO_INDEX
from codonflow.models.minimal_neural import (
    FIXED_TERMINAL_STOP,
    MinimalCodonFlowRK,
    MinimalNeuralConfig,
    enumerate_legal_single_edit,
    exact_conditional_kernel,
    multifidelity_loss,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_batch(protocol, seed: int, device: torch.device):
    generator = torch.Generator().manual_seed(seed)
    protein = protocol["synthetic_batch"]["protein"]
    rows = []
    for _ in range(protocol["training"]["batch_size"]):
        row = []
        for aa in protein:
            options = AA_TO_CODONS_INDEX[aa]
            row.append(options[int(torch.randint(len(options), (1,), generator=generator))])
        row.append(FIXED_TERMINAL_STOP)
        rows.append(row)
    codons = torch.tensor(rows, dtype=torch.long, device=device)
    host = torch.arange(len(rows), device=device) % 4
    budget = (torch.arange(len(rows), device=device, dtype=torch.float64) + 1.0) / (len(rows) + 1.0)
    utr = torch.tensor(protocol["synthetic_batch"]["utr_tokens"], device=device).repeat(len(rows), 1)
    z = codons[:, :-1].double() / 60.0
    gc = torch.tensor([sum(b in "GC" for b in c) / 3.0 for c in CODON_TO_INDEX], device=device)[codons].mean(1)
    targets = torch.stack([
        torch.sin(2.0 * math.pi * (z + 0.1)).mean(1),
        torch.cos(2.0 * math.pi * (z + 0.2)).mean(1),
        (z.square() + 0.05 * host.double()[:, None]).mean(1),
        gc + 0.05 * host.double() + 0.1 * budget,
    ], dim=1)
    indices = torch.arange(len(rows), device=device)[:, None]
    channels = torch.arange(4, device=device)[None, :]
    mask = (indices + channels) % 7 != 0
    fidelity = torch.arange(len(rows), device=device) % 3
    return codons, host, budget, utr, targets, mask, fidelity


def evaluate(model, batch):
    codons, host, budget, utr, targets, mask, fidelity = batch
    with torch.no_grad():
        outputs = model(codons, host, budget, utr)
        loss, terms = multifidelity_loss(outputs, targets, mask, fidelity, model.fidelity_weights)
        mse = ((outputs["potentials"] - targets).square()).mean()
    return float(loss), float(mse), {key: float(value) for key, value in terms.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--run-label", default="production")
    args = parser.parse_args()
    started = time.perf_counter()
    protocol_bytes = args.protocol.read_bytes()
    protocol = json.loads(protocol_bytes)
    protocol_sha = hashlib.sha256(protocol_bytes).hexdigest()
    torch.manual_seed(protocol["seed"])
    torch.cuda.manual_seed_all(protocol["seed"])
    torch.use_deterministic_algorithms(True)
    device = torch.device(protocol["device"])
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("this frozen smoke requires real CUDA")
    model = MinimalCodonFlowRK(MinimalNeuralConfig(**protocol["model"])).double().to(device)
    model.train()
    batch = make_batch(protocol, protocol["seed"] + 1, device)
    initial_loss, initial_mse, initial_terms = evaluate(model, batch)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=protocol["training"]["learning_rate"],
        weight_decay=protocol["training"]["weight_decay"],
    )
    history = []
    for step in range(protocol["training"]["steps"]):
        model.zero_grad(set_to_none=True)
        codons, host, budget, utr, targets, mask, fidelity = batch
        outputs = model(codons, host, budget, utr)
        loss, terms = multifidelity_loss(outputs, targets, mask, fidelity, model.fidelity_weights)
        if not torch.isfinite(loss):
            raise FloatingPointError(f"non-finite loss at step {step}")
        loss.backward()
        gradient_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), protocol["training"]["gradient_clip_norm"])
        optimizer.step()
        history.append({
            "step": step + 1,
            "loss_before_step": float(loss.detach()),
            "gradient_norm": float(gradient_norm),
            "learning_rate": protocol["training"]["learning_rate"],
            "elapsed_seconds": time.perf_counter() - started,
        })
    model.eval()
    final_loss, final_mse, final_terms = evaluate(model, batch)
    source = torch.tensor([CODON_TO_INDEX[c] for c in protocol["kernel"]["source_codons"]], device=device)
    kernel = exact_conditional_kernel(
        model, source, protocol["kernel"]["host_id"], protocol["kernel"]["model_budget"],
        torch.tensor(protocol["synthetic_batch"]["utr_tokens"], device=device),
        torch.tensor(protocol["kernel"]["preferences"], dtype=torch.float64, device=device),
        protocol["kernel"]["remaining_budget"], protocol["kernel"]["beta"], protocol["kernel"]["beta_cost"],
    )
    model.zero_grad(set_to_none=True)
    kernel_loss = -kernel["log_probabilities"][0]
    kernel_loss.backward()
    gradients = [p.grad.detach() for p in model.parameters() if p.grad is not None]
    finite_gradient = all(bool(torch.isfinite(g).all()) for g in gradients)
    nonzero_gradient = any(int(torch.count_nonzero(g)) > 0 for g in gradients)
    max_gradient = max(float(g.abs().max()) for g in gradients)
    args.output.mkdir(parents=True, exist_ok=False)
    arrays = {}
    for name in ("candidates", "potentials", "cost", "allowed", "log_probabilities", "delta_phi", "delta_cost"):
        value = kernel[name].detach().cpu().numpy()
        np.save(args.output / f"{name}.npy", value)
        arrays[name] = {"path": f"{name}.npy", "sha256": sha256(args.output / f"{name}.npy"), "shape": list(value.shape)}
    (args.output / "history.json").write_text(json.dumps(history, indent=2) + "\n")
    checkpoint = {
        "schema": "a8-rk11-minimal-neural-checkpoint-v1",
        "protocol_sha256": protocol_sha,
        "config": asdict(model.cfg),
        "state_dict": model.state_dict(),
        "seed": protocol["seed"],
        "final_step": protocol["training"]["steps"],
    }
    checkpoint_path = args.output / "checkpoint.pt"
    torch.save(checkpoint, checkpoint_path)
    candidates = kernel["candidates"].detach().cpu().numpy()
    legal = True
    source_aa = [c for c in protocol["kernel"]["source_codons"][:-1]]
    from codonflow.core.codon import STANDARD_TABLE_1
    source_protein = [STANDARD_TABLE_1[c] for c in source_aa]
    for row in candidates:
        if row[-1] != FIXED_TERMINAL_STOP or any(AA_OF_INDEX[int(v)] == "*" for v in row[:-1]):
            legal = False
        protein = [STANDARD_TABLE_1[next(c for c, i in CODON_TO_INDEX.items() if i == int(v))] for v in row[:-1]]
        if protein != source_protein or sum(a != b for a, b in zip(row.tolist(), source.detach().cpu().tolist())) > 1:
            legal = False
    probability_sum = float(kernel["log_probabilities"].detach().exp().sum())
    masked_probability = float(kernel["log_probabilities"].detach().exp()[~kernel["allowed"]].sum())
    checks = {
        "real_cuda_execution": device.type == "cuda" and torch.cuda.is_available(),
        "history_length_exact": len(history) == protocol["training"]["steps"],
        "all_history_losses_finite": all(math.isfinite(row["loss_before_step"]) for row in history),
        "strict_loss_decrease": final_loss < initial_loss,
        "strict_unmasked_mse_decrease": final_mse < initial_mse,
        "candidate_count_exact": len(candidates) == protocol["kernel"]["expected_candidates_including_noop"],
        "all_candidates_legal_single_edit": legal,
        "probability_sum": abs(probability_sum - 1.0) <= protocol["acceptance"]["probability_sum_abs_tolerance"],
        "budget_masked_probability_zero": masked_probability == 0.0,
        "three_nucleotide_expansion_shape": list(kernel["nucleotide_hidden"].shape) == [len(candidates), 4, 3, protocol["model"]["d_model"]],
        "utr_pair_shape": list(kernel["utr_pair"].shape) == [len(candidates), 4, 5],
        "kernel_gradient_finite": finite_gradient,
        "kernel_gradient_nonzero": nonzero_gradient,
        "synthetic_scope_only": protocol["scientific_scope"].startswith("Synthetic teacher"),
    }
    status = "PASS_MINIMAL_NEURAL_SYNTHETIC_CUDA_CONTRACT" if all(checks.values()) else "FAIL_MINIMAL_NEURAL_CONTRACT"
    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True).strip()
    report = {
        "schema": "a8-rk11-minimal-neural-production-v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha,
        "run_label": args.run_label,
        "status": status,
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "scientific_scope": protocol["scientific_scope"],
        "forbidden_claims": protocol["forbidden_claims"],
        "base_commit": base_commit,
        "code_sha256": {
            "training_script": sha256(Path(__file__)),
            "model_source": sha256(Path(__import__("codonflow.models.minimal_neural", fromlist=["x"]).__file__)),
        },
        "environment": {
            "python": platform.python_version(), "torch": torch.__version__,
            "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
        },
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "initial_eval_loss": initial_loss,
        "final_eval_loss": final_loss,
        "initial_unmasked_mse": initial_mse,
        "final_unmasked_mse": final_mse,
        "initial_terms": initial_terms,
        "final_terms": final_terms,
        "history_sha256": sha256(args.output / "history.json"),
        "checkpoint_sha256": sha256(checkpoint_path),
        "arrays": arrays,
        "candidate_count": len(candidates),
        "budget_allowed": int(kernel["allowed"].sum()),
        "budget_masked": int((~kernel["allowed"]).sum()),
        "probability_sum": probability_sum,
        "masked_probability": masked_probability,
        "kernel_loss_at_noop": float(kernel_loss),
        "kernel_gradient_max_abs": max_gradient,
        "kernel_gradient_finite": finite_gradient,
        "kernel_gradient_nonzero": nonzero_gradient,
        "elapsed_seconds": time.perf_counter() - started,
        "artifact_root": str(args.output),
        "no_functional_untouched_access": True,
        "no_biological_training_data": True,
        "no_full_generator_training": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": status, "checks": f"{report['checks_passed']}/{report['checks_total']}", "initial_loss": initial_loss, "final_loss": final_loss, "candidates": len(candidates), "elapsed_seconds": report["elapsed_seconds"]}, indent=2))
    if status.startswith("FAIL"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
