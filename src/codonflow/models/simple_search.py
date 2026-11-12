"""Budget-matched non-learned and learned-agnostic synonymous searches."""
from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import numpy as np

from ..core.codon import (
    STANDARD_TABLE_1,
    SYNONYMOUS_CODONS,
    is_valid_cds,
    normalize_to_dna,
    split_codons,
)

ObjectiveFunction = Callable[[str], Sequence[float]]


def weighted_sum(objectives: Sequence[float], weights: Sequence[float]) -> float:
    values = np.asarray(objectives, dtype=float)
    coefficients = np.asarray(weights, dtype=float)
    if values.ndim != 1 or coefficients.shape != values.shape:
        raise ValueError("objective and weight dimensions differ")
    return float(np.dot(values, coefficients))


def augmented_tchebycheff(
    objectives: Sequence[float], weights: Sequence[float], rho: float = 0.01
) -> float:
    values = np.asarray(objectives, dtype=float)
    coefficients = np.asarray(weights, dtype=float)
    if values.ndim != 1 or coefficients.shape != values.shape:
        raise ValueError("objective and weight dimensions differ")
    active = np.flatnonzero(coefficients > 0)
    if not len(active):
        return 0.0
    return float(np.min(coefficients[active] * values[active])
                 + rho * np.dot(coefficients, values))


def random_synonymous(source: str, rng: np.random.Generator) -> str:
    codons = split_codons(source)
    result = []
    for codon in codons[:-1]:
        alternatives = SYNONYMOUS_CODONS[STANDARD_TABLE_1[codon]]
        result.append(alternatives[int(rng.integers(len(alternatives)))])
    result.append(codons[-1])
    return "".join(result)


def single_codon_proposal(source: str, rng: np.random.Generator) -> str:
    codons = split_codons(source)
    positions = []
    for index, codon in enumerate(codons[:-1]):
        alternatives = SYNONYMOUS_CODONS[STANDARD_TABLE_1[codon]]
        if len(alternatives) > 1:
            positions.append(index)
    if not positions:
        return source
    position = positions[int(rng.integers(len(positions)))]
    current = codons[position]
    alternatives = [c for c in SYNONYMOUS_CODONS[STANDARD_TABLE_1[current]] if c != current]
    codons[position] = alternatives[int(rng.integers(len(alternatives)))]
    return "".join(codons)


class UniqueObjectiveScorer:
    def __init__(self, objective_fn: ObjectiveFunction):
        self.objective_fn = objective_fn
        self.cache: dict[str, tuple[float, ...]] = {}
        self.terminal_evaluations = 0

    @property
    def unique_calls(self) -> int:
        return len(self.cache)

    def __call__(self, sequence: str) -> tuple[float, ...]:
        self.terminal_evaluations += 1
        if sequence not in self.cache:
            values = tuple(float(value) for value in self.objective_fn(sequence))
            if not values or not np.isfinite(values).all():
                raise ValueError("objective function returned invalid values")
            self.cache[sequence] = values
        return self.cache[sequence]


@dataclass
class SearchResult:
    method: str
    source: str
    status: str
    points: list[dict]
    attempts: int
    terminal_evaluations: int
    elapsed_s: float

    def to_dict(self) -> dict:
        return {
            "protocol": "a7_simple_search_v1",
            "method": self.method,
            "status": self.status,
            "source_sha256": hashlib.sha256(self.source.encode()).hexdigest(),
            "points": self.points,
            "n_unique": len(self.points),
            "costs": {
                "forward_calls": 0,
                "generator_calls": self.attempts,
                "terminal_reward_evaluations": self.terminal_evaluations,
                "unique_terminal_reward_calls": len(self.points),
                "elapsed_s": self.elapsed_s,
            },
        }


class SimpleSearch:
    METHODS = ("uniform", "hill_climbing", "mh_annealing", "areuredi_style")

    def __init__(
        self,
        source: str,
        objective_fn: ObjectiveFunction,
        weights: Sequence[float],
        seed: int = 0,
        rho: float = 0.01,
        initial_temperature: float = 1.0,
        final_temperature: float = 0.01,
        normalization: Optional[tuple[Sequence[float], Sequence[float]]] = None,
        uniform_operator: str = "single_codon",
    ):
        self.source = normalize_to_dna(source)
        if not is_valid_cds(self.source):
            raise ValueError("source must be a valid CDS with one terminal stop")
        self.objective_fn = objective_fn
        self.weights = tuple(float(value) for value in weights)
        self.seed = seed
        self.rho = rho
        self.initial_temperature = initial_temperature
        self.final_temperature = final_temperature
        self.normalization = normalization
        if uniform_operator not in ("single_codon", "global_synonymous"):
            raise ValueError("unknown uniform operator")
        self.uniform_operator = uniform_operator
        if initial_temperature <= 0 or final_temperature <= 0:
            raise ValueError("temperatures must be positive")
        if normalization is not None:
            reference, scale = (np.asarray(values, dtype=float) for values in normalization)
            if (reference.shape != scale.shape or scale.ndim != 1
                    or not np.isfinite(reference).all() or not np.isfinite(scale).all()
                    or np.any(scale <= 0)):
                raise ValueError("invalid utility normalization")
            self.normalization = (reference, scale)

    def _utility(self, method: str, objectives: Sequence[float]) -> float:
        values = np.asarray(objectives, dtype=float)
        if self.normalization is not None:
            reference, scale = self.normalization
            if values.shape != reference.shape:
                raise ValueError("objective and calibration dimensions differ")
            values = (values - reference) / scale
        if method == "areuredi_style":
            return augmented_tchebycheff(values, self.weights, self.rho)
        return weighted_sum(values, self.weights)

    def run(self, method: str, max_unique_scorer: int = 500,
            max_attempts: Optional[int] = None) -> SearchResult:
        if method not in self.METHODS:
            raise ValueError(f"unknown search method: {method}")
        if max_unique_scorer < 1:
            raise ValueError("max_unique_scorer must be positive")
        max_attempts = max_attempts or max(1000, 50 * max_unique_scorer)
        rng = np.random.default_rng(self.seed)
        scorer = UniqueObjectiveScorer(self.objective_fn)
        started = time.perf_counter()
        current = self.source
        current_objectives = scorer(current)
        points = [{"budget": 1, "sequence": current, "objectives": list(current_objectives)}]
        attempts = 0
        while scorer.unique_calls < max_unique_scorer and attempts < max_attempts:
            attempts += 1
            if method == "uniform" and self.uniform_operator == "global_synonymous":
                candidate = random_synonymous(self.source, rng)
            elif method == "uniform":
                candidate = single_codon_proposal(self.source, rng)
            else:
                candidate = single_codon_proposal(current, rng)
            candidate_objectives = scorer(candidate)
            if len(scorer.cache) > len(points):
                points.append({"budget": len(points) + 1, "sequence": candidate,
                               "objectives": list(candidate_objectives)})
            if method == "uniform":
                current, current_objectives = candidate, candidate_objectives
                continue
            delta = self._utility(method, candidate_objectives) - self._utility(method, current_objectives)
            if method == "hill_climbing":
                accept = delta >= 0
            else:
                progress = scorer.unique_calls / max_unique_scorer
                temperature = self.initial_temperature * (
                    self.final_temperature / self.initial_temperature
                ) ** progress
                accept = math.log(rng.random()) < delta / temperature
            if accept:
                current, current_objectives = candidate, candidate_objectives
        status = "done" if scorer.unique_calls == max_unique_scorer else "max_attempts_exhausted"
        return SearchResult(
            method=method,
            source=self.source,
            status=status,
            points=points,
            attempts=attempts,
            terminal_evaluations=scorer.terminal_evaluations,
            elapsed_s=time.perf_counter() - started,
        )
