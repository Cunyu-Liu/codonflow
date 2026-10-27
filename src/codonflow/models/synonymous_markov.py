"""Finite-step synonymous Markov editing with explicit Doob guidance.

For a finite terminal step ``T``, let ``q`` be a full-support discrete-time
kernel and ``G >= 0`` a terminal potential.  With ``h_t(x) = E_q[G(X_T) |
X_t=x]``, backward recursion gives ``h_t(x) = sum_y q(x,y) h_{t+1}(y)`` and
``q_G(x,y) = q(x,y) h_{t+1}(y) / h_t(x)``.  On paths with positive ``G`` this
exact Doob kernel gives ``q_G(x_T | x_t) = q_base(x_T | x_t) G(x_T) /
h_t(x_t)``.  This is a theorem for exact ``h`` on a finite-step kernel, not a
CTMC or EditFlow equivalence claim.

``SynonymousJumpProposal`` supplies the normalized single-codon jump kernel.
``FiniteStepSynonymousMarkovEditor`` uses short Monte-Carlo base rollouts to
estimate ``h``; pruning candidates before estimating their values further
approximates the kernel.  Consequently its sampled terminal distribution is
not asserted to be the exact tilted distribution.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Optional, Sequence

import numpy as np
import torch

from ..core.codon import (
    CODON_TO_INDEX,
    STANDARD_TABLE_1,
    SYNONYMOUS_CODONS,
    is_synonymous,
    is_valid_cds,
    normalize_to_dna,
    split_codons,
)
from ..core.tokenizer import encode_cds


@dataclass(frozen=True)
class SynonymousTransition:
    """One valid single-codon jump (``position=None`` denotes explicit stay)."""

    codons: tuple[str, ...]
    log_probability: float
    position: Optional[int] = None

    @property
    def sequence(self) -> str:
        return "".join(self.codons)

    @property
    def is_stay(self) -> bool:
        return self.position is None


TerminalReward = Callable[[list[str]], Sequence[float]]


def _logsumexp(values: Sequence[float]) -> float:
    """Stable log-sum-exp, including the empty and all--inf conventions."""
    if not values:
        return -math.inf
    largest = max(values)
    if largest == -math.inf:
        return -math.inf
    if largest == math.inf:
        return math.inf
    return largest + math.log(math.fsum(math.exp(v - largest) for v in values))


def _normalized_logs(log_weights: Sequence[float]) -> list[float]:
    normalizer = _logsumexp(log_weights)
    if not math.isfinite(normalizer):
        raise ValueError("A positive finite total transition mass is required")
    return [value - normalizer for value in log_weights]


def _sample_log_probabilities(
    log_probabilities: Sequence[float], rng: np.random.Generator
) -> int:
    probabilities = np.exp(np.asarray(log_probabilities, dtype=np.float64))
    probabilities /= probabilities.sum()
    return int(rng.choice(len(probabilities), p=probabilities))


class SynonymousJumpProposal:
    """Adapt an existing transformer to a normalized synonymous jump kernel.

    For each non-stop position, blank logits parameterize the location mass
    and token logits parameterize alternatives for that position's current
    amino acid.  BOS/EOS are included when calling the model, but neither is
    editable; codon position ``i`` corresponds to model row ``i + 1``.
    Token logits are not globally softmaxed: they are normalized only within
    each amino-acid alternative set, including the current codon.  Writing
    ``a_i = softmax(blank)_i`` and ``b_ic`` for those local probabilities,
    the joint is ``q(i,c) = a_i b_ic`` for each replacement ``c``, while
    ``q(stay) = sum_i a_i b_i,current`` aggregates every no-change event.
    The implementation uses the algebraically identical unnormalized logits
    and performs one joint log normalization, avoiding duplicate self-jumps.

    ``time`` is accepted for finite-step interfaces; the existing transformer
    is called with only its token tensor and may therefore ignore time.
    Invalid source CDS inputs fail fast, and the stop codon is never changed.
    """

    def __init__(self, model, device: Optional[torch.device | str] = None):
        self.model = model
        self.device = torch.device("cpu") if device is None else torch.device(device)
        if hasattr(model, "to"):
            self.model = model.to(self.device)
        if hasattr(model, "eval"):
            self.model.eval()
        self.forward_calls = 0

    @staticmethod
    def validate_source(codons: Sequence[str]) -> tuple[str, ...]:
        normalized = tuple(normalize_to_dna(c) for c in codons)
        sequence = "".join(normalized)
        if not normalized or not is_valid_cds(sequence):
            raise ValueError("Source must be a valid CDS with one terminal stop")
        if any(len(c) != 3 or c not in CODON_TO_INDEX for c in normalized):
            raise ValueError("Every state element must be one standard codon")
        return normalized

    def _transition_tensors(
        self, codons: Sequence[str], time: float | int = 0
    ) -> tuple[list[SynonymousTransition], torch.Tensor]:
        """Build the joint jump distribution without detaching policy gradients."""
        del time  # The interface is time-indexed even if this model ignores it.
        current = self.validate_source(codons)
        ids = encode_cds("".join(current), add_special=True)
        inputs = torch.tensor([ids], dtype=torch.long, device=self.device)
        blank_logits, token_logits = self.model(inputs)
        self.forward_calls += 1
        if blank_logits.ndim != 2 or token_logits.ndim != 3:
            raise ValueError("Model must return [batch, length] and [batch, length, vocab]")
        if (
            blank_logits.shape[0] != 1
            or token_logits.shape[:2] != blank_logits.shape
            or blank_logits.shape[1] != len(ids)
            or token_logits.shape[-1] <= max(ids)
        ):
            raise ValueError("Model output shapes do not match BOS/codons/EOS input")
        blank_logits = blank_logits[0].float()
        token_logits = token_logits[0].float()

        transitions: list[SynonymousTransition] = []
        log_weights: list[torch.Tensor] = []
        locations: list[tuple[int, list[str], torch.Tensor]] = []
        for position, codon in enumerate(current[:-1]):
            aa = STANDARD_TABLE_1[codon]
            alternatives = list(SYNONYMOUS_CODONS[aa])
            indices = [CODON_TO_INDEX[c] for c in alternatives]
            row = position + 1
            local_logs = torch.log_softmax(token_logits[row, indices].double(), dim=-1)
            locations.append((position, alternatives, local_logs))

        for position, alternatives, local_logs in locations:
            row = position + 1
            for alternative, local_log in zip(alternatives, local_logs):
                if alternative == current[position]:
                    continue
                log_weights.append(blank_logits[row] + local_log)
                edited = list(current)
                edited[position] = alternative
                transitions.append(SynonymousTransition(tuple(edited), 0.0, position))

        stay_logit = torch.logsumexp(torch.stack([
            blank_logits[position + 1] + local_logs[alternatives.index(current[position])]
            for position, alternatives, local_logs in locations
        ]), dim=0)
        log_weights.append(stay_logit)
        transitions.append(SynonymousTransition(current, 0.0, None))
        log_weights = torch.stack(log_weights)
        log_probabilities = torch.log_softmax(log_weights.double(), dim=0)
        return transitions, log_probabilities

    @torch.no_grad()
    def enumerate_transitions(
        self, codons: Sequence[str], time: float | int = 0
    ) -> list[SynonymousTransition]:
        """Enumerate every replacement plus stay, with joint logs summing to 1."""
        transitions, log_probabilities = self._transition_tensors(codons, time)
        result = [
            SynonymousTransition(t.codons, float(log_p), t.position)
            for t, log_p in zip(transitions, log_probabilities)
        ]
        if not math.isclose(
            _logsumexp([t.log_probability for t in result]), 0.0,
            abs_tol=1e-10,  # float64 normalization; do not hide actual mass loss.
        ):
            raise RuntimeError("Internal error: jump kernel is not normalized")
        return result

    def sampled_path_log_probability(
        self, initial_cds: str, path: Sequence[str]
    ) -> torch.Tensor:
        """Differentiable normalized log probability of a sampled edit path.

        ``path`` includes the initial CDS, followed by one state per jump.
        The probability includes every transition, including explicit stays.
        """
        if len(path) < 2 or normalize_to_dna(path[0]) != normalize_to_dna(initial_cds):
            raise ValueError("path must start at initial_cds and contain a transition")
        log_probability = None
        for source, target in zip(path, path[1:]):
            codons = self.validate_source(split_codons(source))
            target = normalize_to_dna(target)
            transitions, log_probabilities = self._transition_tensors(codons)
            indices = [i for i, t in enumerate(transitions) if t.sequence == target]
            if len(indices) != 1:
                raise ValueError("path contains an invalid or non-local synonymous jump")
            step_log_probability = log_probabilities[indices[0]]
            log_probability = (
                step_log_probability if log_probability is None
                else log_probability + step_log_probability
            )
        return log_probability / (len(path) - 1)

    def sample_transition(
        self,
        codons: Sequence[str],
        time: float | int = 0,
        rng: Optional[np.random.Generator] = None,
    ) -> SynonymousTransition:
        """Sample the exact enumerated kernel using the supplied NumPy RNG."""
        generator = np.random.default_rng() if rng is None else rng
        transitions = self.enumerate_transitions(codons, time)
        index = _sample_log_probabilities(
            [t.log_probability for t in transitions], generator
        )
        return transitions[index]


class FiniteStepSynonymousMarkovEditor:
    """Finite-step synonymous editor with short-rollout Doob approximations.

    ``terminal_reward`` maps a batch of CDS strings to ``log G`` values;
    infeasible terminal states must receive ``-inf``.  Starting at step ``t``,
    ``R > 0`` independent base-kernel rollouts to fixed ``T`` estimate
    ``log h_t(x) = logsumexp_r(log G(x_T^r)) - log R``.  Candidate scores are
    ``log q(x,y) + log h_{t+1}(y) - log h_t(x)`` and are softmaxed after
    explicit candidate pruning.  This is a Monte-Carlo, candidate-pruned
    approximation, not a proof of exact terminal tilting.

    ``rollout_count=0`` is the separately named ``immediate`` ablation: it uses
    the candidate's own terminal reward instead of base rollout aggregation
    and is never the default.  Only single-codon jumps are supported.  The
    default return is the actual trajectory terminal; ``return_incumbent=True``
    explicitly returns the best feasible terminal observed instead.
    """

    def __init__(
        self,
        proposal: SynonymousJumpProposal,
        terminal_reward: TerminalReward,
        terminal_step: int,
        rollout_count: int = 16,
        candidate_count: Optional[int] = None,
        rng: Optional[np.random.Generator] = None,
    ):
        if terminal_step < 0:
            raise ValueError("terminal_step must be nonnegative")
        if rollout_count < 0:
            raise ValueError("rollout_count must be nonnegative")
        if candidate_count is not None and candidate_count < 1:
            raise ValueError("candidate_count must be positive or None")
        self.proposal = proposal
        self.guided_log_probabilities = False
        self.terminal_reward = terminal_reward
        self.terminal_step = int(terminal_step)
        self.rollout_count = int(rollout_count)
        self.candidate_count = candidate_count
        self.rng = np.random.default_rng(0) if rng is None else rng
        self.mode = "immediate" if rollout_count == 0 else "rollout"
        self.reward_cache: dict[str, float] = {}
        self.unique_terminal_reward_calls = 0
        self.terminal_reward_evaluations = 0
        self.best_terminal: Optional[str] = None
        self.best_terminal_reward = -math.inf

    def reset_counts(self) -> None:
        """Reset reward cache and all accounting before an independent run."""
        self.reward_cache.clear()
        self.unique_terminal_reward_calls = 0
        self.terminal_reward_evaluations = 0
        self.best_terminal = None
        self.best_terminal_reward = -math.inf
        self.proposal.forward_calls = 0

    def _terminal_rewards(self, sequences: Sequence[str]) -> list[float]:
        missing = list(dict.fromkeys(s for s in sequences if s not in self.reward_cache))
        if missing:
            rewards = self.terminal_reward(missing)
            if len(rewards) != len(missing):
                raise ValueError("terminal_reward returned the wrong batch length")
            for sequence, reward in zip(missing, rewards):
                value = float(reward)
                if math.isnan(value):
                    raise ValueError("terminal_reward returned NaN")
                self.reward_cache[sequence] = value
                self.unique_terminal_reward_calls += 1
                self.terminal_reward_evaluations += 1
                if math.isfinite(value) and value > self.best_terminal_reward:
                    self.best_terminal_reward = value
                    self.best_terminal = sequence
        return [self.reward_cache[s] for s in sequences]

    def estimate_log_h(
        self, codons: Sequence[str], step: int, rollout_count: Optional[int] = None
    ) -> float:
        """Estimate finite-horizon value by base rollouts, not immediate reward."""
        current = self.proposal.validate_source(codons)
        if step < 0 or step > self.terminal_step:
            raise ValueError("step must lie in [0, terminal_step]")
        count = self.rollout_count if rollout_count is None else rollout_count
        if count < 0:
            raise ValueError("rollout_count must be nonnegative")
        if step == self.terminal_step:
            return self._terminal_rewards(["".join(current)])[0]
        if count == 0:
            # Deliberate ablation only; unlike the default this does not roll out.
            return self._terminal_rewards(["".join(current)])[0]
        rewards: list[float] = []
        for _ in range(count):
            state = current
            for time in range(step, self.terminal_step):
                state = self.proposal.sample_transition(
                    state, time, self.rng
                ).codons
            rewards.extend(self._terminal_rewards(["".join(state)]))
        return _logsumexp(rewards) - math.log(count)

    def _prune(
        self, transitions: Sequence[SynonymousTransition]
    ) -> list[SynonymousTransition]:
        if self.candidate_count is None or len(transitions) <= self.candidate_count:
            return list(transitions)
        # Pruning is explicit and deterministic for a fixed base kernel.  Stay
        # is always retained; otherwise -inf log h could silently stop a path.
        ranked = sorted(
            range(len(transitions)),
            key=lambda i: (transitions[i].is_stay, transitions[i].log_probability, -i),
            reverse=True,
        )
        return [transitions[i] for i in sorted(ranked[: self.candidate_count])]

    def guided_transitions(
        self, codons: Sequence[str], step: int
    ) -> tuple[list[SynonymousTransition], float, list[float]]:
        """Return pruned guided candidates, current log h, and guided log scores."""
        current = self.proposal.validate_source(codons)
        if step < 0 or step >= self.terminal_step:
            raise ValueError("Guidance requires step in [0, terminal_step)")
        base = self._prune(self.proposal.enumerate_transitions(current, step))
        current_log_h = self.estimate_log_h(current, step)
        candidate_log_h = [
            self.estimate_log_h(t.codons, step + 1) for t in base
        ]
        raw_scores = []
        for transition, next_log_h in zip(base, candidate_log_h):
            if next_log_h == -math.inf:
                raw_scores.append(-math.inf)
            elif current_log_h == -math.inf:
                # Zero estimated current mass has no Doob ratio.  Restrict to
                # estimated positive-mass successors rather than emit NaN or
                # hide the case behind a large finite fallback score.
                raw_scores.append(transition.log_probability + next_log_h)
            else:
                raw_scores.append(
                    transition.log_probability + next_log_h - current_log_h
                )
        guided_logs = _normalized_logs(raw_scores)
        guided = [
            SynonymousTransition(t.codons, log_p, t.position)
            for t, log_p in zip(base, guided_logs)
        ]
        return guided, current_log_h, candidate_log_h

    def sample(
        self,
        source_cds: str,
        start_step: int = 0,
        return_incumbent: bool = False,
    ) -> tuple[str, list[dict]]:
        """Run through fixed ``terminal_step`` with explicit budget accounting."""
        self.reset_counts()
        source = normalize_to_dna(source_cds)
        if not is_valid_cds(source):
            raise ValueError("source_cds must be a valid CDS with one terminal stop")
        if start_step < 0 or start_step > self.terminal_step:
            raise ValueError("start_step must lie in [0, terminal_step]")
        state = self.proposal.validate_source(split_codons(source))
        trace: list[dict] = []
        if start_step == self.terminal_step:
            terminal_reward = self._terminal_rewards([source])[0]
        else:
            terminal_reward = -math.inf
        for step in range(start_step, self.terminal_step):
            guided, current_log_h, candidate_log_h = self.guided_transitions(state, step)
            index = _sample_log_probabilities(
                [t.log_probability for t in guided], self.rng
            )
            chosen = guided[index]
            state = chosen.codons
            terminal_reward = None
            if step + 1 == self.terminal_step:
                terminal_reward = self._terminal_rewards(["".join(state)])[0]
            trace.append(
                {
                    "step": step,
                    "position": chosen.position,
                    "codon": None if chosen.is_stay else state[chosen.position],
                    "sequence": "".join(state),
                    "log_h_current": current_log_h,
                    "log_h_candidate": candidate_log_h[index],
                    "terminal_reward": terminal_reward,
                    "mode": self.mode,
                    "candidate_count": len(guided),
                    "unique_terminal_reward_calls": self.unique_terminal_reward_calls,
                    "terminal_reward_evaluations": self.terminal_reward_evaluations,
                    "forward_calls": self.proposal.forward_calls,
                    "base_log_probability": chosen.log_probability,
                }
            )
        if not trace and start_step < self.terminal_step:
            raise RuntimeError("No transition was sampled before terminal_step")
        if start_step == self.terminal_step:
            terminal = source
        else:
            terminal = "".join(state)
        if not is_synonymous(terminal, source) or not is_valid_cds(terminal):
            raise RuntimeError("Internal error: generated state is not a valid synonym")
        if return_incumbent:
            if self.best_terminal is None:
                raise ValueError("No feasible terminal reward was observed")
            return self.best_terminal, trace
        return terminal, trace


def exact_doob_transitions(
    base_log_probabilities: Sequence[float],
    next_log_h: Sequence[float],
    current_log_h: Optional[float] = None,
) -> list[float]:
    """Exact full-support finite-step Doob reweighting for enumerable tests/use.

    No candidate pruning or Monte-Carlo estimation occurs here.  The caller
    must supply harmonic values satisfying the backward recursion; providing
    ``current_log_h`` makes that consistency check explicit.
    """
    if len(base_log_probabilities) != len(next_log_h) or not next_log_h:
        raise ValueError("Base probabilities and next values must be nonempty and aligned")
    if not math.isclose(_logsumexp(base_log_probabilities), 0.0, abs_tol=1e-10):
        raise ValueError("Base transition probabilities must be normalized")
    harmonic = _logsumexp(
        [q + h for q, h in zip(base_log_probabilities, next_log_h)]
    )
    if current_log_h is not None and not math.isclose(
        harmonic, current_log_h, rel_tol=1e-10, abs_tol=1e-10
    ):
        raise ValueError("current_log_h violates the backward harmonic recursion")
    if not math.isfinite(harmonic):
        raise ValueError("Doob kernel requires positive finite harmonic mass")
    return [q + h - harmonic for q, h in zip(base_log_probabilities, next_log_h)]
