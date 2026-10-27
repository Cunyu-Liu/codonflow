"""RLOO fine-tuning with label-free bi-reward (GrammarRL Eq (4)-(8)).

direct   = (1/|y|) sum log pi_ref(y_t | x, y_<t)   (unconstrained probs)
reverse  = 1[Trans(y) == Trans(x)]                 (hard translation cycle)
r        = (1-lambda) R_direct / sigma_direct + lambda R_reverse / sigma_reverse
Group    = N policy samples + 1 LinearDesign solution, all equally weighted
           in the LOO baseline (not an imitation target).
Loss     = RLOO advantage + squared log-ratio trust penalty.
           The linear GrammarRL penalty is not a KL surrogate for arbitrary
           sampled sequences; CodonFlow uses the squared log ratio instead.
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
    """RLOO advantage with squared log-ratio trust penalty.

    The squared log ratio penalizes departure in either direction. It is not
    labelled KL because sampled-sequence log-ratio differences are not a full
    path-distribution KL estimator. The advantage is a constant per rollout.
    """
    adv = loo_advantage(rewards)
    delta = log_pi_theta - log_pi_ref
    per_seq = -adv.detach() * log_pi_theta + beta * delta.square()
    return per_seq.mean()


def rloo_accumulate_path_gradients(
    log_pi_fn: Callable[[int], torch.Tensor],
    log_pi_ref: torch.Tensor,
    rewards: torch.Tensor,
    beta: float,
) -> list[torch.Tensor]:
    """Backpropagate identical RLOO loss one path at a time to bound memory."""
    if len(log_pi_ref) != len(rewards) or len(rewards) < 2:
        raise ValueError("RLOO requires aligned log-reference and reward groups of size >= 2")
    advantage = loo_advantage(rewards).detach()
    detached_log_pi = []
    for index in range(len(rewards)):
        log_pi = log_pi_fn(index)
        detached_log_pi.append(log_pi.detach())
        loss = -advantage[index] * log_pi + beta * (log_pi - log_pi_ref[index]).square()
        (loss / len(rewards)).backward()
    return detached_log_pi


class RewardTracker:
    """Moving-average plateau detector for the RLOO reward curve."""

    def __init__(self, patience: int = 50, rel_tol: float = 0.005, smoothing: int = 20):
        self.patience = patience
        self.rel_tol = rel_tol
        self.smoothing = smoothing
        self.history: List[float] = []
        self.smoothed_history: List[float] = []
        self.best: Optional[float] = None
        self._plateau_steps = 0

    def update(self, value: float) -> bool:
        """Compare trailing mean rewards; do not stop on noisy single batches."""
        self.history.append(value)
        smooth = sum(self.history[-self.smoothing:]) / len(self.history[-self.smoothing:])
        self.smoothed_history.append(smooth)
        if len(self.smoothed_history) < self.smoothing:
            return False
        if self.best is None or smooth > self.best * (1 + self.rel_tol):
            self.best = max(smooth, self.best or smooth)
            self._plateau_steps = 0
        else:
            self._plateau_steps += 1
        return self._plateau_steps >= self.patience

    @property
    def converged(self) -> bool:
        return self._plateau_steps >= self.patience
