#!/usr/bin/env python3
"""Independent numerical and bitwise verification of RK-11 synthetic contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch

from codonflow.core.codon import AA_OF_INDEX, AA_TO_CODONS_INDEX, CODON_TO_INDEX
from codonflow.models.minimal_neural import MinimalCodonFlowRK, MinimalNeuralConfig


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def independent_candidates(source):
    rows = [source.copy()]
    for position, current in enumerate(source[:-1]):
        for replacement in range(64):
            if AA_OF_INDEX[replacement] == "*" or replacement == current:
                continue
            if AA_OF_INDEX[replacement] == AA_OF_INDEX[current]:
                row = source.copy(); row[position] = replacement; rows.append(row)
    return np.asarray(rows, dtype=np.int64)


def independent_batch(protocol, seed, device):
    generator = torch.Generator().manual_seed(seed)
    rows = []
    for _ in range(protocol["training"]["batch_size"]):
        row = []
        for aa in protocol["synthetic_batch"]["protein"]:
            options = AA_TO_CODONS_INDEX[aa]
            row.append(options[int(torch.randint(len(options), (1,), generator=generator))])
        row.append(CODON_TO_INDEX[protocol["synthetic_batch"]["terminal_codon"]])
        rows.append(row)
    codons = torch.tensor(rows, dtype=torch.long, device=device)
    host = torch.arange(len(rows), device=device) % 4
    budget = (torch.arange(len(rows), device=device, dtype=torch.float64) + 1.0) / (len(rows) + 1.0)
    utr = torch.tensor(protocol["synthetic_batch"]["utr_tokens"], device=device).repeat(len(rows), 1)
    z = codons[:, :-1].double() / 60.0
    # Production constructs this constant table with the default float32 dtype;
    # model inference and all remaining teacher arithmetic are float64.
    gc_values = torch.zeros(64, dtype=torch.float32, device=device)
    for codon, index in CODON_TO_INDEX.items():
        gc_values[index] = sum(base in "GC" for base in codon) / 3.0
    gc = gc_values[codons].mean(1)
    target = torch.stack([
        torch.sin(2.0 * math.pi * (z + 0.1)).mean(1),
        torch.cos(2.0 * math.pi * (z + 0.2)).mean(1),
        (z.square() + 0.05 * host.double()[:, None]).mean(1),
        gc + 0.05 * host.double() + 0.1 * budget,
    ], dim=1)
    mask = (torch.arange(len(rows), device=device)[:, None] + torch.arange(4, device=device)[None, :]) % 7 != 0
    fidelity = torch.arange(len(rows), device=device) % 3
    return codons, host, budget, utr, target, mask, fidelity


def max_error(actual, expected):
    return float(np.max(np.abs(np.asarray(actual, dtype=np.float64) - np.asarray(expected, dtype=np.float64))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--production-artifacts", required=True, type=Path)
    parser.add_argument("--production-report", required=True, type=Path)
    parser.add_argument("--retrain-artifacts", required=True, type=Path)
    parser.add_argument("--retrain-report", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    protocol_bytes = args.protocol.read_bytes(); protocol = json.loads(protocol_bytes)
    protocol_sha = hashlib.sha256(protocol_bytes).hexdigest()
    production = json.loads(args.production_report.read_text())
    retrain = json.loads(args.retrain_report.read_text())
    torch.use_deterministic_algorithms(True)
    device = torch.device("cuda")
    checkpoint_path = args.production_artifacts / "checkpoint.pt"
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    retrain_checkpoint = torch.load(args.retrain_artifacts / "checkpoint.pt", map_location="cpu", weights_only=False)
    model = MinimalCodonFlowRK(MinimalNeuralConfig(**checkpoint["config"])).double().to(device)
    model.load_state_dict(checkpoint["state_dict"], strict=True); model.eval()
    # Match the production operation order: teacher evaluation precedes the
    # nine-state conditional forward, avoiding CUDA kernel-path reorder effects.
    batch = independent_batch(protocol, protocol["seed"] + 1, device)
    with torch.no_grad():
        out = model(*batch[:4])
    target, mask, fidelity = batch[4], batch[5], batch[6]
    error = out["potentials"] - target
    per_value = error.square()
    log_scale = out["function_log_scale"]
    per_value[:, 3] = 0.5 * (error[:, 3].square() * (-log_scale).exp() + log_scale)
    weights = torch.tensor(protocol["model"]["fidelity_weights"], dtype=torch.float64, device=device)[fidelity].unsqueeze(1)
    denominator = (weights * mask).sum()
    final_loss = float((per_value * weights * mask).sum() / denominator)
    final_mse = float(error.square().mean())
    source_list = [CODON_TO_INDEX[c] for c in protocol["kernel"]["source_codons"]]
    expected_candidates = independent_candidates(source_list)
    candidates = torch.tensor(expected_candidates, dtype=torch.long, device=device)
    count = len(candidates)
    with torch.no_grad():
        outputs = model(
            candidates,
            torch.full((count,), protocol["kernel"]["host_id"], dtype=torch.long, device=device),
            torch.full((count,), protocol["kernel"]["model_budget"], dtype=torch.float64, device=device),
            torch.tensor(protocol["synthetic_batch"]["utr_tokens"], device=device).repeat(count, 1),
        )
    potentials = outputs["potentials"].cpu().numpy(); cost = outputs["cost"].squeeze(1).cpu().numpy()
    delta_phi = potentials - potentials[0:1]; delta_cost = cost - cost[0]
    preferences = np.asarray(protocol["kernel"]["preferences"], dtype=np.float64)
    allowed = cost <= protocol["kernel"]["remaining_budget"]
    logits = -math.log(count) - protocol["kernel"]["beta"] * (delta_phi * preferences).sum(1) - protocol["kernel"]["beta_cost"] * delta_cost
    logits[~allowed] = -np.inf
    finite = np.isfinite(logits)
    normalizer = float(np.log(np.exp(logits[finite] - np.max(logits[finite])).sum()) + np.max(logits[finite]))
    logq = logits - normalizer
    array_errors = {}
    for name, expected in (("potentials", potentials), ("cost", cost), ("delta_phi", delta_phi), ("delta_cost", delta_cost)):
        array_errors[name] = max_error(np.load(args.production_artifacts / f"{name}.npy"), expected)
    produced_logq = np.load(args.production_artifacts / "log_probabilities.npy")
    array_errors["log_probabilities"] = max_error(produced_logq[finite], logq[finite])
    candidate_exact = np.array_equal(np.load(args.production_artifacts / "candidates.npy"), expected_candidates)
    allowed_exact = np.array_equal(np.load(args.production_artifacts / "allowed.npy"), allowed)
    masked_neg_inf = bool(np.isneginf(produced_logq[~allowed]).all())
    history_production = (args.production_artifacts / "history.json").read_bytes()
    history = json.loads(history_production)
    retrain_history = json.loads((args.retrain_artifacts / "history.json").read_text())
    deterministic_keys = ("step", "loss_before_step", "gradient_norm", "learning_rate")
    history_numeric_equal = len(history) == len(retrain_history) and all(
        all(left[key] == right[key] for key in deterministic_keys)
        and math.isfinite(left["elapsed_seconds"]) and left["elapsed_seconds"] >= 0.0
        and math.isfinite(right["elapsed_seconds"]) and right["elapsed_seconds"] >= 0.0
        for left, right in zip(history, retrain_history)
    )
    tensor_bitwise = set(checkpoint["state_dict"]) == set(retrain_checkpoint["state_dict"]) and all(
        torch.equal(checkpoint["state_dict"][key], retrain_checkpoint["state_dict"][key]) for key in checkpoint["state_dict"]
    )
    array_names = ("candidates", "potentials", "cost", "allowed", "log_probabilities", "delta_phi", "delta_cost")
    retrain_array_bitwise = all((args.production_artifacts / f"{name}.npy").read_bytes() == (args.retrain_artifacts / f"{name}.npy").read_bytes() for name in array_names)
    tolerance = protocol["acceptance"]["independent_numeric_abs_tolerance"]
    checks = {
        "both_production_reports_pass": production["status"].startswith("PASS") and retrain["status"].startswith("PASS"),
        "protocol_hash_matches_both": production["protocol_sha256"] == protocol_sha and retrain["protocol_sha256"] == protocol_sha,
        "checkpoint_protocol_hash": checkpoint["protocol_sha256"] == protocol_sha,
        "production_checkpoint_sha": production["checkpoint_sha256"] == sha256(checkpoint_path),
        "retrain_checkpoint_sha": retrain["checkpoint_sha256"] == sha256(args.retrain_artifacts / "checkpoint.pt"),
        "checkpoint_bytes_bitwise_equal": checkpoint_path.read_bytes() == (args.retrain_artifacts / "checkpoint.pt").read_bytes(),
        "all_state_tensors_bitwise_equal": tensor_bitwise,
        "history_numeric_values_equal": history_numeric_equal,
        "history_hash_matches_report": production["history_sha256"] == hashlib.sha256(history_production).hexdigest(),
        "all_kernel_arrays_bitwise_equal": retrain_array_bitwise,
        "independent_candidates_exact": candidate_exact,
        "candidate_count_exact": count == protocol["kernel"]["expected_candidates_including_noop"],
        "terminal_tga_fixed": bool((expected_candidates[:, -1] == CODON_TO_INDEX["TGA"]).all()),
        "internal_stops_absent": all(AA_OF_INDEX[int(v)] != "*" for v in expected_candidates[:, :-1].ravel()),
        "potentials_recomputed": array_errors["potentials"] <= tolerance,
        "cost_recomputed": array_errors["cost"] <= tolerance,
        "delta_phi_recomputed": array_errors["delta_phi"] <= tolerance,
        "delta_cost_recomputed": array_errors["delta_cost"] <= tolerance,
        "budget_mask_recomputed": allowed_exact,
        "log_probabilities_recomputed": array_errors["log_probabilities"] <= tolerance,
        "masked_states_negative_infinity": masked_neg_inf,
        "probability_sum_exact": abs(float(np.exp(logq).sum()) - 1.0) <= protocol["acceptance"]["probability_sum_abs_tolerance"],
        "final_loss_recomputed": abs(final_loss - production["final_eval_loss"]) <= tolerance,
        "final_mse_recomputed": abs(final_mse - production["final_unmasked_mse"]) <= tolerance,
        "history_length_and_finite_loss": len(history) == protocol["training"]["steps"] and all(math.isfinite(row["loss_before_step"]) for row in history),
        "strict_training_decrease": production["final_eval_loss"] < production["initial_eval_loss"],
        "synthetic_scope_preserved": production["no_biological_training_data"] and production["no_full_generator_training"],
    }
    status = "PASS_INDEPENDENT_MINIMAL_NEURAL" if all(checks.values()) else "FAIL_INDEPENDENT_MINIMAL_NEURAL"
    report = {
        "schema": "a8-rk11-minimal-neural-independent-v1",
        "protocol_id": protocol["protocol_id"], "protocol_sha256": protocol_sha,
        "status": status, "checks": checks, "checks_passed": sum(checks.values()), "checks_total": len(checks),
        "array_abs_errors": array_errors, "final_loss_recomputed": final_loss, "final_mse_recomputed": final_mse,
        "candidate_count": count, "allowed_count": int(allowed.sum()), "masked_count": int((~allowed).sum()),
        "tensor_bitwise_equal": tensor_bitwise, "array_bitwise_equal": retrain_array_bitwise,
        "history_numeric_equal": history_numeric_equal,
        "history_elapsed_seconds_compared_for_equality": False,
        "teacher_gc_constant_dtype": "float32",
        "model_and_remaining_teacher_dtype": "float64",
        "scientific_scope": protocol["scientific_scope"], "forbidden_claims": protocol["forbidden_claims"],
        "production_report": str(args.production_report), "retrain_report": str(args.retrain_report),
        "production_artifacts": str(args.production_artifacts), "retrain_artifacts": str(args.retrain_artifacts),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": status, "checks": f"{report['checks_passed']}/{report['checks_total']}", "array_abs_errors": array_errors, "final_loss": final_loss}, indent=2))
    if status.startswith("FAIL"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
