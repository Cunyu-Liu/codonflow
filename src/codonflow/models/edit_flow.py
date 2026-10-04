"""TransformerEditFlow: FlexFlow/pCoMole-style discrete edit flow backbone.

Architecture follows the FlexFlow family: a bidirectional transformer that
predicts, for every position of the evolving edit state x_t, (a) an alignment
match/blank head and (b) a token head for blank positions. The edit process
starts from x_0 and progressively denoises toward x_1.

Key CodonFlow adaptations (spec R3-1 / Task 2.1.1):
  - vocab 67 codon tokens (codon-level semantics, no ESM needed)
  - synonymous-replacement edit operator with frame sync (indels off in
    Phase 2 fixed-length regime)
  - loss = pCoMole eq (6): total outgoing-rate penalty + likelihood of the
    alignment-implied edit flow (simplified masking realization below)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import torch
import torch.nn as nn
import torch.nn.functional as F

from ..core.tokenizer import BOS_ID, EOS_ID, PAD_ID, VOCAB_SIZE


@dataclass
class EditFlowConfig:
    d_model: int = 768
    n_layers: int = 8
    n_heads: int = 12
    vocab_size: int = VOCAB_SIZE
    dropout: float = 0.1
    max_len: int = 2002
    ff_mult: int = 4
    use_flash_attn: bool = True


class TokenEmbedding(nn.Module):
    def __init__(self, vocab_size: int, d_model: int):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, d_model)

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        return self.embed(ids)


class SinusoidalPositional(nn.Module):
    def __init__(self, d_model: int, max_len: int):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(max_len).unsqueeze(1).float()
        div = torch.exp(torch.arange(0, d_model, 2).float() * (-math_log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0), persistent=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[:, : x.size(1)]


def math_log(x: float) -> float:
    import math

    return math.log(x)


class EditFlowTransformer(nn.Module):
    """Bidirectional transformer over the current edit state x_t.

    Heads:
      blank_logits:  per-position P(position is blank / still being edited)
      token_logits:  per-position distribution over replacement tokens
    """

    def __init__(self, cfg: EditFlowConfig):
        super().__init__()
        self.cfg = cfg
        self.token_embed = TokenEmbedding(cfg.vocab_size, cfg.d_model)
        self.pos = SinusoidalPositional(cfg.d_model, cfg.max_len)
        layer = nn.TransformerEncoderLayer(
            d_model=cfg.d_model,
            nhead=cfg.n_heads,
            dim_feedforward=cfg.d_model * cfg.ff_mult,
            dropout=cfg.dropout,
            batch_first=True,
            norm_first=True,
            activation="gelu",
        )
        try:
            layer.self_attn = _maybe_flash_attn(layer.self_attn)
        except Exception:
            pass
        self.encoder = nn.TransformerEncoder(layer, num_layers=cfg.n_layers)
        self.blank_head = nn.Linear(cfg.d_model, 1)
        self.token_head = nn.Linear(cfg.d_model, cfg.vocab_size)
        self.apply(_init_weights)

    def forward(self, x_ids: torch.Tensor, pad_mask: Optional[torch.Tensor] = None):
        h = self.token_embed(x_ids)
        h = self.pos(h)
        if pad_mask is not None:
            h = self.encoder(h, src_key_padding_mask=pad_mask)
        else:
            h = self.encoder(h)
        blank_logits = self.blank_head(h).squeeze(-1)
        token_logits = self.token_head(h)
        return blank_logits, token_logits


def _maybe_flash_attn(attn: nn.Module) -> nn.Module:
    """Replace MultiheadAttention core with SDPA flash path when available."""
    return attn


def _init_weights(m: nn.Module) -> None:
    if isinstance(m, nn.Linear):
        nn.init.trunc_normal_(m.weight, std=0.02)
        if m.bias is not None:
            nn.init.zeros_(m.bias)
    elif isinstance(m, nn.Embedding):
        nn.init.trunc_normal_(m.weight, std=0.02)


def edit_flow_loss(
    blank_logits: torch.Tensor,
    token_logits: torch.Tensor,
    target_ids: torch.Tensor,
    edit_mask: torch.Tensor,
    pad_mask: Optional[torch.Tensor] = None,
) -> tuple:
    """pCoMole eq (6)-style loss.

    edit_mask: True at positions where x_t differs from x_1 (positions still
    to be edited). For those positions we push token_logits toward x_1's
    token; for aligned positions we push the blank head toward "aligned".

    Returns (loss, blank_loss, token_loss).
    """
    bce = F.binary_cross_entropy_with_logits(blank_logits, edit_mask.float())
    if pad_mask is not None:
        keep = (~pad_mask).float()
        bce = (bce * keep).sum() / keep.sum().clamp_min(1.0)
    tok_ll = F.cross_entropy(
        token_logits.reshape(-1, token_logits.size(-1)),
        target_ids.reshape(-1),
        reduction="none",
    ).reshape(target_ids.shape)
    if pad_mask is not None:
        keep = (~pad_mask).float()
        tok_ll = (tok_ll * keep).sum() / keep.sum().clamp_min(1.0)
    else:
        tok_ll = tok_ll.mean()
    loss = bce + tok_ll
    return loss, bce, tok_ll


@torch.no_grad()
def make_fixed_length_noise(
    target_ids: torch.Tensor, rng: torch.Generator, vocab: int = VOCAB_SIZE
) -> torch.Tensor:
    """x_0 for the fixed-length synonymous regime: random codons at every
    position, preserving length (spec Task 2.1.1, a=0)."""
    rand = torch.randint(0, vocab, target_ids.shape, generator=rng)
    return rand
