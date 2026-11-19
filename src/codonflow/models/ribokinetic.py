"""Minimal ribokinetic prediction backbone for RK-08.

This module is a supervised function/velocity model, not a generator or a
continuous-time flow. Initiation, velocity, decay and pair pathways are always
constructed so ablations have identical parameters and dense attention compute;
ablation flags only gate their information pathways. Pair scores are local
base-pairing biases, not an exact partition function or a structure prediction.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Mapping, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from ..core.codon import CODONS, CODON_TO_INDEX
from ..core.tokenizer import PAD_ID, VOCAB_SIZE
from .edit_flow import SinusoidalPositional

MECHANISMS: Tuple[str, ...] = ("initiation", "velocity", "decay", "pair")
_COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}


@dataclass
class RiboKineticConfig:
    d_model: int = 64
    n_layers: int = 2
    n_heads: int = 4
    vocab_size: int = VOCAB_SIZE
    dropout: float = 0.1
    max_len: int = 2002
    ff_mult: int = 2
    initiation_window: int = 30
    long_range_stride: int = 16
    pair_strength: float = 1.0
    allow_wobble: bool = True
    num_hosts: int = 64

    def validate(self) -> None:
        if self.d_model <= 0 or self.d_model % self.n_heads:
            raise ValueError("d_model must be positive and divisible by n_heads")
        if self.n_layers <= 0 or self.max_len <= 0:
            raise ValueError("n_layers and max_len must be positive")
        if self.initiation_window <= 0 or self.long_range_stride <= 0:
            raise ValueError("initiation_window and long_range_stride must be positive")
        if self.vocab_size != VOCAB_SIZE:
            raise ValueError(f"RK-08 requires the 67-token codon vocabulary, got {self.vocab_size}")


def _paired(a: str, b: str, allow_wobble: bool) -> bool:
    return _COMPLEMENT.get(a) == b or (allow_wobble and {a, b} == {"G", "T"})


def codon_pair_score(codon_a: str, codon_b: str, allow_wobble: bool = True) -> int:
    """Return legal antiparallel base-pair matches between two codons (0..3)."""
    a = codon_a.upper().replace("U", "T")
    b = codon_b.upper().replace("U", "T")
    if len(a) != 3 or len(b) != 3 or any(x not in "ACGT" for x in a + b):
        raise ValueError("pair scores require two valid three-nucleotide codons")
    return sum(_paired(a[i], b[2 - i], allow_wobble) for i in range(3))


@lru_cache(maxsize=2)
def codon_pair_table(allow_wobble: bool = True) -> torch.Tensor:
    """[67, 67] pair table; special tokens have zero pairing score."""
    table = torch.zeros(VOCAB_SIZE, VOCAB_SIZE, dtype=torch.float32)
    for a, ia in CODON_TO_INDEX.items():
        for b, ib in CODON_TO_INDEX.items():
            table[ia, ib] = codon_pair_score(a, b, allow_wobble)
    return table


def build_pair_channel(
    codon_ids: torch.Tensor,
    pad_mask: torch.Tensor,
    initiation_window: int = 30,
    long_range_stride: int = 16,
    pair_strength: float = 1.0,
    allow_wobble: bool = True,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Build dense attention bias and an auditable per-position pair summary.

    High-resolution interactions include every pair touching the initiation
    window. Outside it, only adjacent, diagonal and stride-aligned axial pairs
    are enabled. The dense representation deliberately keeps compute constant
    between pair-on and pair-off ablations; it is not a sparse complexity claim.
    """
    if codon_ids.ndim != 2 or codon_ids.shape != pad_mask.shape:
        raise ValueError("codon_ids and pad_mask must have matching [B, L] shapes")
    if initiation_window <= 0 or long_range_stride <= 0:
        raise ValueError("window and stride must be positive")
    if codon_ids.numel() and (codon_ids.min() < 0 or codon_ids.max() >= VOCAB_SIZE):
        raise ValueError("codon id outside the 67-token vocabulary")
    b, length = codon_ids.shape
    table = codon_pair_table(allow_wobble).to(codon_ids.device)
    scores = table[codon_ids[:, :, None], codon_ids[:, None, :]]
    pos = torch.arange(length, device=codon_ids.device)
    i = pos[:, None]
    j = pos[None, :]
    initiation = (i < initiation_window) | (j < initiation_window)
    axial = ((i % long_range_stride) == 0) & ((j % long_range_stride) == 0)
    local = (i - j).abs() <= 1
    allowed = (initiation | axial | local).unsqueeze(0)
    bias = torch.where(allowed, pair_strength * scores, torch.full_like(scores, -10000.0))
    key_valid = (~pad_mask).to(scores.dtype)
    weighted = scores * allowed.to(scores.dtype) * key_valid[:, None, :]
    count = (allowed.to(scores.dtype) * key_valid[:, None, :]).sum(dim=-1)
    summary = weighted.sum(dim=-1) / count.clamp_min(1.0)
    summary = summary.masked_fill(pad_mask, 0.0)
    return bias, summary


def utr_cds_pair_scores(
    codon_ids: torch.Tensor,
    utr_ids: torch.Tensor,
    allow_wobble: bool = True,
    utr_pad_id: int = 4,
) -> torch.Tensor:
    """Return [B, L_codon, L_utr] legal single-base pairing potentials.

    UTR tokens use A/C/G/T=0/1/2/3 and ``utr_pad_id`` for padding. Scores count
    complementary bases available in each codon; they are features only and do
    not imply that a pair is present in a folded structure.
    """
    if codon_ids.ndim != 2 or utr_ids.ndim != 2 or codon_ids.size(0) != utr_ids.size(0):
        raise ValueError("expected codon_ids [B,L] and utr_ids [B,U] with equal B")
    if utr_ids.numel() and (utr_ids.min() < 0 or utr_ids.max() > utr_pad_id):
        raise ValueError("UTR token outside A/C/G/T/pad")
    table = torch.zeros(VOCAB_SIZE, 5, dtype=torch.float32, device=codon_ids.device)
    for codon, index in CODON_TO_INDEX.items():
        for utr_index, nucleotide in enumerate("ACGT"):
            table[index, utr_index] = sum(
                _paired(base, nucleotide, allow_wobble) for base in codon
            )
    scores = table[codon_ids[:, :, None], utr_ids[:, None, :]]
    return scores.masked_fill((utr_ids == utr_pad_id)[:, None, :], 0.0)


class PairTransformerBlock(nn.Module):
    """Pre-norm transformer block accepting sample-specific pair attention bias."""

    def __init__(self, cfg: RiboKineticConfig):
        super().__init__()
        self.n_heads = cfg.n_heads
        self.norm1 = nn.LayerNorm(cfg.d_model)
        self.attn = nn.MultiheadAttention(
            cfg.d_model, cfg.n_heads, dropout=cfg.dropout, batch_first=True
        )
        self.norm2 = nn.LayerNorm(cfg.d_model)
        self.ff = nn.Sequential(
            nn.Linear(cfg.d_model, cfg.d_model * cfg.ff_mult),
            nn.GELU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.d_model * cfg.ff_mult, cfg.d_model),
        )
        self.drop = nn.Dropout(cfg.dropout)

    def forward(
        self,
        x: torch.Tensor,
        pad_mask: torch.Tensor,
        pair_bias: torch.Tensor,
    ) -> torch.Tensor:
        h = self.norm1(x)
        attn_mask = pair_bias.repeat_interleave(self.n_heads, dim=0)
        key_padding = torch.zeros_like(pad_mask, dtype=pair_bias.dtype).masked_fill(
            pad_mask, float("-inf")
        )
        attended, _ = self.attn(
            h, h, h,
            key_padding_mask=key_padding,
            attn_mask=attn_mask,
            need_weights=False,
        )
        x = x + self.drop(attended)
        return x + self.drop(self.ff(self.norm2(x)))


def _masked_mean(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    weights = mask.to(values.dtype).unsqueeze(-1)
    return (values * weights).sum(dim=1) / weights.sum(dim=1).clamp_min(1.0)


def _weighted_summary(
    hidden: torch.Tensor,
    weights: torch.Tensor,
    valid: torch.Tensor,
) -> torch.Tensor:
    w = weights * valid.to(weights.dtype)
    denom = w.abs().sum(dim=1, keepdim=True).clamp_min(1e-6)
    return (hidden * w.unsqueeze(-1)).sum(dim=1) / denom


class RiboKineticModel(nn.Module):
    """Shared-backbone multi-task model with constant-cost mechanism ablations."""

    def __init__(self, cfg: RiboKineticConfig):
        super().__init__()
        cfg.validate()
        self.cfg = cfg
        self.codon_embed = nn.Embedding(cfg.vocab_size, cfg.d_model)
        self.host_embed = nn.Embedding(cfg.num_hosts, cfg.d_model)
        self.budget_projection = nn.Linear(1, cfg.d_model)
        self.position = SinusoidalPositional(cfg.d_model, cfg.max_len)
        self.blocks = nn.ModuleList([PairTransformerBlock(cfg) for _ in range(cfg.n_layers)])
        self.norm = nn.LayerNorm(cfg.d_model)
        self.initiation_head = nn.Linear(cfg.d_model, 1)
        self.velocity_head = nn.Linear(cfg.d_model, 1)
        self.decay_head = nn.Linear(cfg.d_model, 1)
        self.function_head = nn.Sequential(
            nn.Linear(cfg.d_model * 5, cfg.d_model),
            nn.GELU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.d_model, 2),
        )
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.trunc_normal_(module.weight, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.trunc_normal_(module.weight, std=0.02)

    def forward(
        self,
        codon_ids: torch.Tensor,
        pad_mask: torch.Tensor,
        host_ids: Optional[torch.Tensor] = None,
        budget: Optional[torch.Tensor] = None,
        utr_ids: Optional[torch.Tensor] = None,
        active_mechanisms: Optional[Mapping[str, bool]] = None,
    ) -> Dict[str, Optional[torch.Tensor]]:
        if codon_ids.ndim != 2 or codon_ids.shape != pad_mask.shape:
            raise ValueError("codon_ids and pad_mask must have matching [B,L] shapes")
        if codon_ids.size(1) > self.cfg.max_len:
            raise ValueError("sequence length exceeds configured max_len")
        active = {name: True for name in MECHANISMS}
        if active_mechanisms is not None:
            unknown = set(active_mechanisms) - set(MECHANISMS)
            if unknown:
                raise ValueError(f"unknown mechanisms: {sorted(unknown)}")
            active.update({k: bool(v) for k, v in active_mechanisms.items()})
        h = self.position(self.codon_embed(codon_ids))
        if host_ids is not None:
            if host_ids.shape != codon_ids.shape[:1]:
                raise ValueError("host_ids must have shape [B]")
            h = h + self.host_embed(host_ids).unsqueeze(1)
        if budget is not None:
            if budget.ndim != 1 or budget.size(0) != codon_ids.size(0):
                raise ValueError("budget must have shape [B]")
            h = h + self.budget_projection(budget[:, None]).unsqueeze(1)
        pair_bias, pair_summary = build_pair_channel(
            codon_ids,
            pad_mask,
            self.cfg.initiation_window,
            self.cfg.long_range_stride,
            self.cfg.pair_strength,
            self.cfg.allow_wobble,
        )
        # Pair-off retains identical dense attention operations and parameters.
        encoder_bias = pair_bias if active["pair"] else torch.zeros_like(pair_bias)
        for block in self.blocks:
            h = block(h, pad_mask, encoder_bias)
        h = self.norm(h)
        h = h.masked_fill(pad_mask.unsqueeze(-1), 0.0)
        initiation = self.initiation_head(h).squeeze(-1)
        velocity = self.velocity_head(h).squeeze(-1)
        decay = self.decay_head(h).squeeze(-1)
        valid = ~pad_mask
        initiation_valid = valid & (
            torch.arange(codon_ids.size(1), device=codon_ids.device)[None, :]
            < self.cfg.initiation_window
        )
        utr_pair = None
        if utr_ids is not None:
            utr_pair = utr_cds_pair_scores(codon_ids, utr_ids, self.cfg.allow_wobble)
            utr_valid = (utr_ids != 4).to(utr_pair.dtype)
            utr_summary = (utr_pair * utr_valid[:, None, :]).sum(-1) / utr_valid.sum(
                dim=1, keepdim=True
            ).clamp_min(1.0)
            pair_summary = 0.5 * (pair_summary + utr_summary)
        pooled = _masked_mean(h, valid)
        init_summary = _weighted_summary(h, initiation, initiation_valid)
        velocity_summary = _weighted_summary(h, velocity, valid)
        decay_summary = _weighted_summary(h, decay, valid)
        pair_summary_h = _weighted_summary(h, pair_summary, valid)
        features = torch.cat(
            [
                pooled,
                init_summary if active["initiation"] else torch.zeros_like(init_summary),
                velocity_summary if active["velocity"] else torch.zeros_like(velocity_summary),
                decay_summary if active["decay"] else torch.zeros_like(decay_summary),
                pair_summary_h if active["pair"] else torch.zeros_like(pair_summary_h),
            ],
            dim=-1,
        )
        function_out = self.function_head(features)
        function = function_out[:, 0]
        function_log_scale = function_out[:, 1].clamp(-6.0, 4.0)
        for tensor in (initiation, velocity, decay):
            tensor.masked_fill_(pad_mask, 0.0)
        return {
            "function": function,
            "function_log_scale": function_log_scale,
            "initiation": initiation,
            "velocity": velocity,
            "decay": decay,
            "pair_summary": pair_summary,
            "utr_pair": utr_pair,
        }


def ribokinetic_loss(
    outputs: Mapping[str, Optional[torch.Tensor]],
    batch: Mapping[str, torch.Tensor],
    weights: Optional[Mapping[str, float]] = None,
) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
    """Heteroscedastic function NLL plus masked supervised mechanism losses."""
    loss_weights = {name: 1.0 for name in MECHANISMS}
    loss_weights["function"] = 1.0
    if weights:
        loss_weights.update(weights)
    terms: Dict[str, torch.Tensor] = {}
    total: Optional[torch.Tensor] = None

    def add(name: str, value: torch.Tensor) -> None:
        nonlocal total
        weighted = loss_weights[name] * value
        terms[name] = value
        total = weighted if total is None else total + weighted

    function_mask = batch.get("function_mask")
    if function_mask is not None and function_mask.any():
        error = outputs["function"] - batch["function_target"]
        log_scale = outputs["function_log_scale"]
        nll = 0.5 * (error.square() * (-log_scale).exp() + log_scale)
        add("function", nll[function_mask].mean())
    for name in MECHANISMS[:3]:
        target = batch.get(f"{name}_target")
        mask = batch.get(f"{name}_mask")
        if target is not None and mask is not None and mask.any():
            add(name, (outputs[name] - target).square()[mask].mean())
    if total is None:
        raise ValueError("no supervised function or mechanism target is present")
    terms["total"] = total
    return total, terms
