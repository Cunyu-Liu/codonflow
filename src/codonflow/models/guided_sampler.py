"""Doob-h guided edit flow sampling (pCoMole eq (11)-(15), appendix B).

At each reverse step:
  1. propose C candidate edits (synonymous replacements per position)
  2. estimate log h_t(y) for each candidate with R short rollouts scored by
     the terminal reward log G(x_1) (log-domain logsumexp, stable softmax)
  3. select candidate with s_c = log u_t(y_c | x_t) + log h_t(y_c)

log h_t(x) = log( (1/R) sum_r exp(log G(x_T^r)) ) computed via logsumexp.
"""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np
import torch

from ..core.codon import (
    CODON_TO_INDEX,
    CODONS,
    STANDARD_TABLE_1,
    normalize_to_dna,
    split_codons,
)
from ..core.tokenizer import VOCAB_SIZE


def logsumexp(values: Sequence[float]) -> float:
    if not values:
        return float("-inf")
    m = max(values)
    if m == float("-inf"):
        return float("-inf")
    return m + math.log(sum(math.exp(v - m) for v in values))


class GuidedSampler:
    """Guided edit-flow sampler for the fixed-length synonymous regime."""

    def __init__(
        self,
        model,
        device: torch.device,
        reward_fn: Callable[[str], float],
        n_steps: int = 20,
        n_candidates: int = 10,
        n_rollouts: int = 5,
        temperature: float = 1.0,
        rng: Optional[np.random.Generator] = None,
    ):
        self.model = model
        self.device = device
        self.reward_fn = reward_fn
        self.n_steps = n_steps
        self.n_candidates = n_candidates
        self.n_rollouts = n_rollouts
        self.temperature = temperature
        self.rng = rng or np.random.default_rng(0)

    def _edit_candidates(
        self, seq_codons: List[str], n_candidates: int
    ) -> List[Tuple[int, str]]:
        """Synonymous-replacement candidate edits: (position, new codon)."""
        cands: List[Tuple[int, str]] = []
        n = len(seq_codons)
        if n == 0:
            return cands
        for _ in range(n_candidates):
            pos = int(self.rng.integers(0, n))
            aa = STANDARD_TABLE_1[seq_codons[pos]]
            if aa == "*":
                continue
            opts = [c for c in __import__(
                "codonflow.core.codon", fromlist=["SYNONYMOUS_CODONS"]
            ).SYNONYMOUS_CODONS[aa] if c != seq_codons[pos]]
            if not opts:
                continue
            new = opts[int(self.rng.integers(0, len(opts)))]
            cands.append((pos, new))
        return cands

    @torch.no_grad()
    def _edit_log_rate(self, ids: torch.Tensor, position: int, new_codon: str) -> float:
        """log u_t(y|x_t): model token log-prob of the replacement codon at
        the edited position (fixed-length regime: single-token edit)."""
        blank_logits, token_logits = self.model(ids.unsqueeze(0).to(self.device))
        idx = CODON_TO_INDEX[new_codon]
        lp = torch.log_softmax(token_logits[0, position].float(), dim=-1)[idx]
        return float(lp.item())

    def _apply_edit(self, seq_codons: List[str], pos: int, new_codon: str) -> List[str]:
        out = list(seq_codons)
        out[pos] = new_codon
        return out

    def _rollout_value(self, seq_codons: List[str], target_len: int) -> float:
        """log h estimate: run the base policy to completion (random edits)
        and average exp(log G) over rollouts in log domain."""
        log_ws: List[float] = []
        for _ in range(self.n_rollouts):
            cur = list(seq_codons)
            for _step in range(self.n_steps):
                cands = self._edit_candidates(cur, 1)
                if cands:
                    pos, new = cands[0]
                    cur = self._apply_edit(cur, pos, new)
            seq = "".join(cur)
            log_ws.append(self.reward_fn(seq))
        return logsumexp(log_ws) - math.log(self.n_rollouts)

    @torch.no_grad()
    def sample(
        self,
        x_0_seq: str,
        n_steps: Optional[int] = None,
        n_candidates: Optional[int] = None,
        n_rollouts: Optional[int] = None,
    ) -> Tuple[str, List[dict]]:
        """Run guided editing from x_0; returns final sequence and trace."""
        steps = n_steps or self.n_steps
        C = n_candidates or self.n_candidates
        R = n_rollouts or self.n_rollouts
        seq_codons = split_codons(normalize_to_dna(x_0_seq))
        trace: List[dict] = []
        for step in range(steps):
            cands = self._edit_candidates(seq_codons, C)
            if not cands:
                break
            scored = []
            for pos, new in cands:
                edited = self._apply_edit(seq_codons, pos, new)
                ids = torch.tensor(
                    [CODON_TO_INDEX[c] for c in edited], dtype=torch.long
                )
                log_u = self._edit_log_rate(ids, pos, new)
                log_h = self._rollout_value(edited, len(edited))
                s = log_u + log_h
                if s > float("-inf"):
                    scored.append((s, pos, new))
            if not scored:
                break
            scores = np.array([s for s, _, _ in scored], dtype=float)
            scores = scores / max(self.temperature, 1e-6)
            probs = np.exp(scores - scores.max())
            probs = probs / probs.sum()
            pick = int(self.rng.choice(len(scored), p=probs))
            _s, pos, new = scored[pick]
            seq_codons = self._apply_edit(seq_codons, pos, new)
            trace.append(
                {"step": step, "pos": pos, "codon": new,
                 "log_u": float(_s)}
            )
        return "".join(seq_codons), trace
