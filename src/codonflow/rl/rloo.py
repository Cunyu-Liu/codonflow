"""RLOO fine-tuning with label-free bi-reward (GrammarRL Eq (4)-(8)).

direct   = (1/|y|) sum log pi_ref(y_t | x, y_<t)   (unconstrained probs)
reverse  = 1[Trans(y) == Trans(x)]                 (hard translation cycle)
r        = (1-lambda) R_direct / sigma_direct + lambda R_reverse / sigma_reverse
Group    = N policy samples + 1 LinearDesign solution, all equally weighted
           in the LOO baseline (not an imitation target).
Loss     = mean over group of [ -A^(i) log pi_theta + beta * Delta^(i) ],
           A^(i) = r^(i) - (1/N) sum_{j != i} r^(j),
           Delta^(i) = log pi_theta - log pi_ref (per-sequence, not KL).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import torch
import torch.nn.functional as F


@dataclass
class RLOOConfig:
    lmbda: float = 0.5
    beta: float = 0.02
    group_n: int = 3
    lr: float = 3.3e-7
    seed: int = 0
    sigma_direct: float = 1.0
    sigma_reverse: float = 1.0
    max_steps: Optional[int] = None
    plateau_patience: int = 50
    plateau_rel_tol: float = 0.005
    reward_smoothing: int = 20


def loo_advantage(rewards: torch.Tensor) -> torch.Tensor:
    """A^(i) = r^(i) - mean_{j != i} r^(j) (GrammarRL Sec 3.2)."""
    n = rewards.shape[0]
    if n < 2:
        return rewards - rewards.mean()
    total = rewards.sum()
    mean_others = (total - rewards) / (n - 1)
    return rewards - mean_others


def combined_reward(
    direct: torch.Tensor,
    reverse: torch.Tensor,
    sigma_direct: float,
    sigma_reverse: float,
    lmbda: float,
) -> torch.Tensor:
    return (1 - lmbda) * direct / sigma_direct + lmbda * reverse / sigma_reverse


def sequence_log_prob(
    logits: torch.Tensor,
    targets: torch.Tensor,
    mask: torch.Tensor,
) -> torch.Tensor:
    """Length-normalized log p(y) for the edit-flow token head.

    logits: (B, L, V), targets: (B, L), mask: (B, L) with 1 at real codon
    positions.
    """
    lp = F.cross_entropy(
        logits.reshape(-1, logits.size(-1)),
        targets.reshape(-1),
        reduction="none",
    ).reshape(targets.shape)
    lp = (lp * mask).sum(dim=1)
    lens = mask.sum(dim=1).clamp_min(1)
    return -lp / lens


def rloo_loss(
    log_pi_theta: torch.Tensor,
    log_pi_ref: torch.Tensor,
    rewards: torch.Tensor,
    beta: float,
) -> torch.Tensor:
    """L = mean_i [ -A^(i) log pi_theta + beta * (log pi_theta - log pi_ref) ].

    All log-probs are per-sequence length-normalized values; the policy
    gradient uses unconstrained probabilities (GrammarRL Sec 3.2).
    """
    adv = loo_advantage(rewards)
    delta = log_pi_theta - log_pi_ref
    per_seq = -adv * log_pi_theta + beta * delta
    return per_seq.mean()


class RewardTracker:
    """Moving-average plateau detector for the RLOO reward curve."""

    def __init__(self, patience: int = 50, rel_tol: float = 0.005):
        self.patience = patience
        self.rel_tol = rel_tol
        self.history: List[float] = []
        self.best: Optional[float] = None
        self._plateau_steps = 0

    def update(self, value: float) -> bool:
        """Returns True when the plateau criterion triggers (converged)."""
        self.history.append(value)
        if self.best is None or value > self.best * (1 + self.rel_tol):
            self.best = max(value, self.best or value)
            self._plateau_steps = 0
        else:
            self._plateau_steps += 1
        return self._plateau_steps >= self.patience

    @property
    def converged(self) -> bool:
        return self._plateau_steps >= self.patience
