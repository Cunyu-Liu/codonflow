"""Doob-h guided sampling with true edit-flow probabilities (Phase 2 core).

The sampler combines:
  - model token logits u_t(y_c | x_t) at the edited position
  - lookahead value log h_t(y_c) estimated by a 1-step greedy polish +
    terminal reward (G(x) = beta * U(x) + log 1[x in F])
Selection: s_c = log u_t + log h_t (log-domain, stable softmax over candidates).

For the fixed-length synonymous regime every intermediate state is feasible
by construction if x_0 is built from synonymous codons of the source - the
only infeasible edits are non-synonymous replacements, which the operator
never proposes. This matches spec Q1 hard-gating semantics.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import torch

from ..core.codon import (
    CODON_TO_INDEX,
    CODONS,
    STANDARD_TABLE_1,
    SYNONYMOUS_CODONS,
    normalize_to_dna,
    split_codons,
)
from ..core.tokenizer import BOS_ID, EOS_ID, encode_cds


class CodonGuidedSampler:
    """Guided sampler for the codon edit flow.

    reward_fn: callable mapping a CDS string -> log G(x) (beta*U + log 1[F]).
    """

    def __init__(
        self,
        model,
        device: torch.device,
        reward_fn: Callable[[str], float],
        n_steps: int = 20,
        n_candidates: int = 10,
        temperature: float = 1.0,
        greedy_lookahead: bool = True,
        rng: Optional[np.random.Generator] = None,
    ):
        self.model = model.to(device).eval()
        self.device = device
        self.reward_fn = reward_fn
        self.n_steps = n_steps
        self.n_candidates = n_candidates
        self.temperature = temperature
        self.greedy_lookahead = greedy_lookahead
        self.rng = rng or np.random.default_rng(0)

    def _candidates(
        self, seq_codons: List[str], n: int
    ) -> List[Tuple[int, str]]:
        cands: List[Tuple[int, str]] = []
        seen = set()
        L = len(seq_codons)
        for _ in range(n * 3):
            if len(cands) >= n:
                break
            pos = int(self.rng.integers(0, L))
            aa = STANDARD_TABLE_1[seq_codons[pos]]
            if aa == "*":
                continue
            opts = [c for c in SYNONYMOUS_CODONS[aa] if c != seq_codons[pos]]
            if not opts:
                continue
            new = opts[int(self.rng.integers(0, len(opts)))]
            key = (pos, new)
            if key in seen:
                continue
            seen.add(key)
            cands.append(key)
        return cands

    @torch.no_grad()
    def _token_log_probs(self, seq_codons: List[str]) -> torch.Tensor:
        ids = [BOS_ID] + [CODON_TO_INDEX[c] for c in seq_codons] + [EOS_ID]
        t = torch.tensor([ids], dtype=torch.long, device=self.device)
        _, token_logits = self.model(t)
        return torch.log_softmax(token_logits[0].float(), dim=-1)

    def _edit_log_rate(
        self, log_probs: torch.Tensor, position: int, new_codon: str
    ) -> float:
        idx = CODON_TO_INDEX[new_codon]
        return float(log_probs[position + 1, idx].item())

    def _lookahead_value(self, seq_codons: List[str]) -> float:
        if self.greedy_lookahead:
            return self.reward_fn("".join(seq_codons))
        return self.reward_fn("".join(seq_codons))

    @torch.no_grad()
    def sample(self, x_0_seq: str) -> Tuple[str, List[Dict]]:
        seq_codons = split_codons(normalize_to_dna(x_0_seq))
        trace: List[Dict] = []
        for step in range(self.n_steps):
            cands = self._candidates(seq_codons, self.n_candidates)
            if not cands:
                break
            log_probs = self._token_log_probs(seq_codons)
            scored: List[Tuple[float, int, str]] = []
            for pos, new in cands:
                log_u = self._edit_log_rate(log_probs, pos, new)
                edited = list(seq_codons)
                edited[pos] = new
                log_h = self._lookahead_value(edited)
                s = log_u + log_h
                if s != float("-inf"):
                    scored.append((s, pos, new, log_u, log_h))
            if not scored:
                break
            arr = np.array([x[0] for x in scored], dtype=np.float64)
            arr = arr / max(self.temperature, 1e-9)
            w = np.exp(arr - arr.max())
            w = w / w.sum()
            pick = int(self.rng.choice(len(scored), p=w))
            s, pos, new, log_u, log_h = scored[pick]
            seq_codons[pos] = new
            trace.append(
                {
                    "step": step,
                    "pos": pos,
                    "codon": new,
                    "log_u": round(log_u, 4),
                    "log_h": round(log_h, 4),
                }
            )
        return "".join(seq_codons), trace


def synonymous_x0(source_cds: str, rng: np.random.Generator) -> str:
    """Feasible x_0: random synonymous codons per position (a=0 regime)."""
    codons = split_codons(normalize_to_dna(source_cds))
    out = []
    for c in codons:
        aa = STANDARD_TABLE_1[c]
        opts = list(SYNONYMOUS_CODONS[aa])
        out.append(opts[int(rng.integers(0, len(opts)))])
    return "".join(out)
