"""Minimal neural CodonFlow-RK contracts on exact legal single-edit states.

This module is an engineering smoke implementation, not evidence of biological
function, generation quality, or authorization for expensive generator training.
It reuses the unchanged RK-08 supervised backbone and adds explicit codon-to-three-
nucleotide expansion, multi-fidelity potential supervision, and an exact legal
conditional kernel with preference and remaining-budget conditioning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Tuple

import torch
import torch.nn as nn

from ..core.codon import AA_OF_INDEX, CODONS, CODON_TO_INDEX, STOP_INDICES
from .ribokinetic import RiboKineticConfig, RiboKineticModel

SENSE_INDICES = tuple(index for index, aa in enumerate(AA_OF_INDEX) if aa != "*")
FIXED_TERMINAL_STOP = CODON_TO_INDEX["TGA"]


def codon_nucleotide_table(device: Optional[torch.device] = None) -> torch.Tensor:
    """Return [64,3] A/C/G/T indices in the canonical sorted codon vocabulary."""
    lookup = {base: index for index, base in enumerate("ACGT")}
    table = torch.tensor([[lookup[b] for b in codon] for codon in CODONS], dtype=torch.long)
    return table.to(device) if device is not None else table


def codon_gc_table(device: Optional[torch.device] = None) -> torch.Tensor:
    table = torch.tensor([sum(base in "GC" for base in codon) / 3.0 for codon in CODONS])
    return table.to(device) if device is not None else table


def enumerate_legal_single_edit(codon_ids: torch.Tensor) -> torch.Tensor:
    """Enumerate no-op plus every synonymous one-codon edit, with fixed stop.

    The input and output use the core 64-codon vocabulary. Stop codons are never
    emitted internally; the canonical TGA index is fixed at the terminal position.
    """
    if codon_ids.ndim != 1 or codon_ids.numel() < 2:
        raise ValueError("expected one CDS [L] with at least one sense codon and stop")
    source = [int(x) for x in codon_ids.detach().cpu().tolist()]
    if source[-1] != FIXED_TERMINAL_STOP:
        raise ValueError("the terminal codon must be the canonical TGA index")
    if any(index < 0 or index >= len(AA_OF_INDEX) or AA_OF_INDEX[index] == "*" for index in source[:-1]):
        raise ValueError("internal positions must use sense codons")
    candidates = [source]
    for position, current in enumerate(source[:-1]):
        aa = AA_OF_INDEX[current]
        for replacement in SENSE_INDICES:
            if AA_OF_INDEX[replacement] != aa or replacement == current:
                continue
            candidate = source.copy()
            candidate[position] = replacement
            candidates.append(candidate)
    result = torch.tensor(candidates, dtype=torch.long, device=codon_ids.device)
    if result[:, -1].ne(FIXED_TERMINAL_STOP).any():
        raise AssertionError("terminal stop changed during legal enumeration")
    return result


@dataclass
class MinimalNeuralConfig:
    d_model: int = 16
    n_layers: int = 1
    n_heads: int = 4
    max_len: int = 16
    initiation_window: int = 3
    long_range_stride: int = 2
    num_hosts: int = 8
    fidelity_weights: Tuple[float, float, float] = (0.5, 1.0, 2.0)

    def backbone(self) -> RiboKineticConfig:
        if self.d_model <= 0 or self.d_model % self.n_heads:
            raise ValueError("d_model must be positive and divisible by n_heads")
        return RiboKineticConfig(
            d_model=self.d_model,
            n_layers=self.n_layers,
            n_heads=self.n_heads,
            dropout=0.0,
            max_len=self.max_len,
            initiation_window=self.initiation_window,
            long_range_stride=self.long_range_stride,
            num_hosts=self.num_hosts,
        )


class MinimalCodonFlowRK(nn.Module):
    """Small neural potential model with an exact finite-state legal kernel."""

    def __init__(self, cfg: MinimalNeuralConfig):
        super().__init__()
        self.cfg = cfg
        self.backbone = RiboKineticModel(cfg.backbone())
        self.nt_embedding = nn.Embedding(4, cfg.d_model)
        self.nt_projection = nn.Linear(cfg.d_model, cfg.d_model)
        self.nt_head = nn.Linear(cfg.d_model, 4)
        self.register_buffer("nt_table", codon_nucleotide_table(), persistent=True)
        self.register_buffer("gc_table", codon_gc_table(), persistent=True)
        self.register_buffer("fidelity_weights", torch.tensor(cfg.fidelity_weights), persistent=True)
        for module in (self.nt_embedding, self.nt_projection, self.nt_head):
            module.apply(self._init_new)

    @staticmethod
    def _init_new(module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.trunc_normal_(module.weight, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.trunc_normal_(module.weight, std=0.02)

    def expand_nucleotides(self, codon_ids: torch.Tensor) -> torch.Tensor:
        if codon_ids.numel() and (codon_ids.min() < 0 or codon_ids.max() >= 64):
            raise ValueError("minimal neural model requires the 64-codon vocabulary")
        embedded = self.nt_embedding(self.nt_table[codon_ids])
        return self.nt_projection(embedded)

    def forward(
        self,
        codon_ids: torch.Tensor,
        host_ids: torch.Tensor,
        budget: torch.Tensor,
        utr_ids: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        if codon_ids.ndim != 2:
            raise ValueError("codon_ids must have shape [B,L]")
        pad_mask = torch.zeros_like(codon_ids, dtype=torch.bool)
        backbone = self.backbone(
            codon_ids=codon_ids,
            pad_mask=pad_mask,
            host_ids=host_ids,
            budget=budget,
            utr_ids=utr_ids,
        )
        nt_hidden = self.expand_nucleotides(codon_ids)
        nt_potentials = self.nt_head(nt_hidden).mean(dim=2)
        length = codon_ids.size(1)
        positions = torch.arange(length, device=codon_ids.device)
        init_valid = positions < self.cfg.initiation_window

        def mean(values: torch.Tensor, valid: Optional[torch.Tensor] = None) -> torch.Tensor:
            selected = values if valid is None else values[:, valid]
            return selected.mean(dim=1)

        base = torch.stack(
            [
                mean(backbone["initiation"], init_valid),
                mean(backbone["velocity"]),
                mean(backbone["decay"]),
                backbone["function"],
            ],
            dim=1,
        )
        potentials = base + mean(nt_potentials)
        cost = self.gc_table[codon_ids].mean(dim=1, keepdim=True)
        return {
            "potentials": potentials,
            "cost": cost,
            "function_log_scale": backbone["function_log_scale"],
            "nucleotide_hidden": nt_hidden,
            "utr_pair": backbone["utr_pair"],
            "pair_summary": backbone["pair_summary"],
        }


def multifidelity_loss(
    outputs: Mapping[str, torch.Tensor],
    targets: torch.Tensor,
    mask: torch.Tensor,
    fidelity_ids: torch.Tensor,
    fidelity_weights: torch.Tensor,
) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
    """Weighted potential loss; only the function component is heteroscedastic."""
    if targets.shape != outputs["potentials"].shape or mask.shape != targets.shape:
        raise ValueError("targets/mask must match [B,4] potentials")
    if fidelity_ids.ndim != 1 or fidelity_ids.size(0) != targets.size(0):
        raise ValueError("fidelity_ids must have shape [B]")
    if fidelity_ids.numel() and (fidelity_ids.min() < 0 or fidelity_ids.max() >= fidelity_weights.numel()):
        raise ValueError("fidelity id outside frozen weight table")
    weights = fidelity_weights[fidelity_ids].to(targets.dtype).unsqueeze(1)
    error = outputs["potentials"] - targets
    per_value = error.square()
    log_scale = outputs["function_log_scale"]
    per_value[:, 3] = 0.5 * (error[:, 3].square() * (-log_scale).exp() + log_scale)
    weighted = per_value * weights * mask.to(targets.dtype)
    denominator = (weights * mask.to(targets.dtype)).sum().clamp_min(1.0)
    total = weighted.sum() / denominator
    terms = {
        "total": total,
        "masked_values": mask.sum().to(total.dtype),
        "weighted_denominator": denominator,
    }
    for index, name in enumerate(("initiation", "velocity", "decay", "function")):
        component_mask = mask[:, index].to(total.dtype)
        terms[name] = (per_value[:, index] * component_mask).sum() / component_mask.sum().clamp_min(1.0)
    return total, terms


def exact_conditional_kernel(
    model: MinimalCodonFlowRK,
    source: torch.Tensor,
    host_id: int,
    model_budget: float,
    utr_ids: torch.Tensor,
    preferences: torch.Tensor,
    remaining_budget: float,
    beta: float = 0.75,
    beta_cost: float = 0.1,
) -> Dict[str, torch.Tensor]:
    """Exact q over no-op/single-edit states with hard remaining-budget mask."""
    if source.ndim != 1 or preferences.shape != (4,):
        raise ValueError("source must be [L] and preferences [4]")
    candidates = enumerate_legal_single_edit(source)
    count = candidates.size(0)
    host = torch.full((count,), int(host_id), dtype=torch.long, device=source.device)
    budget = torch.full((count,), float(model_budget), dtype=model.gc_table.dtype, device=source.device)
    utr = utr_ids.to(source.device).reshape(1, -1).repeat(count, 1)
    outputs = model(candidates, host, budget, utr)
    potentials = outputs["potentials"]
    cost = outputs["cost"].squeeze(1)
    delta_phi = potentials - potentials[0:1]
    delta_cost = cost - cost[0]
    allowed = cost <= float(remaining_budget)
    if not bool(allowed[0]):
        raise ValueError("remaining budget must at least admit the no-op source")
    base = -torch.log(torch.tensor(float(count), dtype=potentials.dtype, device=potentials.device))
    logits = base - float(beta) * (delta_phi * preferences.to(potentials)).sum(dim=1) - float(beta_cost) * delta_cost
    logits = logits.masked_fill(~allowed, float("-inf"))
    log_probabilities = torch.log_softmax(logits, dim=0)
    return {
        "candidates": candidates,
        "potentials": potentials,
        "cost": cost,
        "delta_phi": delta_phi,
        "delta_cost": delta_cost,
        "allowed": allowed,
        "log_probabilities": log_probabilities,
        "nucleotide_hidden": outputs["nucleotide_hidden"],
        "utr_pair": outputs["utr_pair"],
    }
