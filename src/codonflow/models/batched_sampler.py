"""Batched guided sampler: one forward pass for ALL candidates at each step.

The unbatched sampler costs ~1.6s/step on a MIG (one forward per candidate
edit plus per-candidate MFE). This version:
  - proposes C candidates, evaluates log u_t for all of them with a SINGLE
    forward on the current state (token logits cover every position);
  - scores lookahead reward with batched MFE through a shared cache;
  - ~C-fold reduction in forward calls and vectorized RNA folding.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import torch

from ..core.codon import (
    CODON_TO_INDEX,
    STANDARD_TABLE_1,
    SYNONYMOUS_CODONS,
    normalize_to_dna,
    split_codons,
)
from ..core.tokenizer import BOS_ID, EOS_ID


class BatchedGuidedSampler:
    """Doob-h guided sampling with batched candidate evaluation."""

    def __init__(
        self,
        model,
        device: torch.device,
        reward_fn: Callable[[List[str]], List[float]],
        n_steps: int = 20,
        n_candidates: int = 10,
        temperature: float = 1.0,
        rng: Optional[np.random.Generator] = None,
    ):
        self.model = model.to(device).eval()
        self.device = device
        self.reward_fn = reward_fn
        self.n_steps = n_steps
        self.n_candidates = n_candidates
        self.temperature = temperature
        self.rng = rng or np.random.default_rng(0)

    def _candidates(self, seq_codons: List[str], n: int) -> List[Tuple[int, str]]:
        cands: List[Tuple[int, str]] = []
        seen = set()
        L = len(seq_codons)
        for _ in range(n * 4):
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

    @torch.no_grad()
    def sample(self, x_0_seq: str) -> Tuple[str, List[Dict]]:
        seq_codons = split_codons(normalize_to_dna(x_0_seq))
        trace: List[Dict] = []
        for step in range(self.n_steps):
            cands = self._candidates(seq_codons, self.n_candidates)
            if not cands:
                break
            log_probs = self._token_log_probs(seq_codons)
            edited_seqs = []
            log_u_list = []
            for pos, new in cands:
                edited = list(seq_codons)
                edited[pos] = new
                edited_seqs.append("".join(edited))
                idx = CODON_TO_INDEX[new]
                log_u_list.append(float(log_probs[pos + 1, idx].item()))
            log_h_list = self.reward_fn(edited_seqs)
            scores = []
            for log_u, log_h in zip(log_u_list, log_h_list):
                s = log_u + log_h
                scores.append(s if s != float("-inf") else -1e18)
            arr = np.array(scores, dtype=np.float64)
            arr = arr / max(self.temperature, 1e-9)
            w = np.exp(arr - arr.max())
            w = w / w.sum()
            pick = int(self.rng.choice(len(cands), p=w))
            pos, new = cands[pick]
            seq_codons[pos] = new
            trace.append(
                {"step": step, "pos": pos, "codon": new, "log_u": round(log_u_list[pick], 4)}
            )
        return "".join(seq_codons), trace


class BatchedReward:
    """Reward with a process-wide MFE cache and batched folding."""

    def __init__(self, weights, atc, mfe_cache: Optional[Dict[str, float]] = None,
                 fold_batch: int = 64):
        from ..eval.metrics import cai, mfe_batch
        from ..core.codon import gc_fraction
        from ..core.motifs import motif_penalty_score

        self._cai = cai
        self._mfe_batch = mfe_batch
        self._gc = gc_fraction
        self._motif = motif_penalty_score
        self.weights = weights
        self.atc = atc
        self.mfe_cache = mfe_cache if mfe_cache is not None else {}
        self.fold_batch = fold_batch

    def __call__(self, seqs: List[str]) -> List[float]:
        missing = [s for s in seqs if s not in self.mfe_cache]
        for i in range(0, len(missing), self.fold_batch):
            chunk = missing[i : i + self.fold_batch]
            mfes = self._mfe_batch(chunk)
            for s, m in zip(chunk, mfes):
                self.mfe_cache[s] = m
        out = []
        for s in seqs:
            m = self.mfe_cache[s]
            out.append(
                self.atc.utility(
                    self._cai(s, self.weights), -m,
                    -abs(self._gc(s) - 0.55), -self._motif(s),
                )
            )
        return out
