"""ATC utility (Amendment A1): four min-max normalized objectives into an
augmented Tchebycheff scalar, plus the gated terminal weight G(x).

Objectives (all to MAXIMIZE after transform):
  f1 = CAI                       in [0, 1]
  f2 = -MFE                      (kcal/mol, positive = more stable)
  f3 = -|GC - target|            deviation from target GC
  f4 = -motif_penalty            soft motif exclusions

Each axis is min-max normalized to [0,1] with calibration stats frozen in
configs/atc_norm.yaml (from Task 1.2 baseline solutions, 5/95 quantiles).

G(x) = exp(beta * U(x)) * 1[x in F],  U(x) = min_k omega_k f_k + rho * sum_k omega_k f_k
"""
from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence

from ..core.codon import gc_fraction, feasible_edit
from ..eval.metrics import mfe

DEFAULT_NORM_STATS = {
    "cai": {"q5": 0.65, "q95": 0.95},
    "neg_mfe": {"q5": 50.0, "q95": 250.0},
    "neg_gc_dev": {"q5": 0.0, "q95": 0.15},
    "neg_motif": {"q5": 0.0, "q95": 5.0},
}

DEFAULT_OMEGA = (1.0, 1.0, 1.0, 0.5)
DEFAULT_RHO = 0.01
DEFAULT_BETA = 1.0
DEFAULT_GC_TARGET = 0.55


def load_norm_stats(path: Optional[str] = None) -> Dict[str, Dict[str, float]]:
    if path is None:
        return {k: dict(v) for k, v in DEFAULT_NORM_STATS.items()}
    import json

    with open(path) as f:
        return json.load(f)


def motif_penalty(seq: str, motifs: Optional[Mapping[str, int]] = None) -> float:
    """Soft penalty = sum over motifs of count * weight (weights default 1)."""
    from ..core.motifs import count_motifs

    counts = count_motifs(seq)
    if motifs:
        return float(sum(c * float(motifs.get(name, 1.0)) for name, c in counts.items()))
    return float(sum(counts.values()))


class ATCUtility:
    """Augmented Tchebycheff utility on normalized objectives."""

    def __init__(
        self,
        norm_stats: Optional[Dict[str, Dict[str, float]]] = None,
        omega: Sequence[float] = DEFAULT_OMEGA,
        rho: float = DEFAULT_RHO,
        gc_target: float = DEFAULT_GC_TARGET,
        motif_weights: Optional[Mapping[str, float]] = None,
    ) -> None:
        self.norm = norm_stats or {k: dict(v) for k, v in DEFAULT_NORM_STATS.items()}
        self.omega = tuple(float(w) for w in omega)
        self.rho = float(rho)
        self.gc_target = float(gc_target)
        self.motif_weights = motif_weights

    def raw_objectives(self, cds: str, mfe_value: Optional[float] = None) -> Dict[str, float]:
        if mfe_value is None:
            mfe_value = mfe(cds)
        return {
            "cai": None,  # filled by caller (needs CAI weights)
            "neg_mfe": -float(mfe_value),
            "neg_gc_dev": -abs(gc_fraction(cds) - self.gc_target),
            "neg_motif": -motif_penalty(cds, self.motif_weights),
        }

    def normalize(self, axis: str, value: float) -> float:
        q5 = self.norm[axis]["q5"]
        q95 = self.norm[axis]["q95"]
        if q95 <= q5:
            return 0.0
        v = (value - q5) / (q95 - q5)
        return min(max(v, 0.0), 1.0)

    def utility_from_normalized(self, f: Sequence[float]) -> float:
        """U = min_k omega_k f_k + rho * sum_k omega_k f_k (to maximize)."""
        w = self.omega
        tcheb = min(w[k] * f[k] for k in range(len(w)))
        aug = self.rho * sum(w[k] * f[k] for k in range(len(w)))
        return tcheb + aug

    def utility(self, cai: float, neg_mfe: float, neg_gc_dev: float, neg_motif: float) -> float:
        f = [
            self.normalize("cai", cai),
            self.normalize("neg_mfe", neg_mfe),
            self.normalize("neg_gc_dev", neg_gc_dev),
            self.normalize("neg_motif", neg_motif),
        ]
        return self.utility_from_normalized(f)


def gated_log_weight(
    log_u: float,
    feasible: bool,
    beta: float = DEFAULT_BETA,
) -> float:
    """log G(x) = beta * U(x) + log 1[x in F]; infeasible -> -inf."""
    if not feasible:
        return float("-inf")
    return beta * log_u


def feasibility_and_log_utility(
    y: str,
    x: str,
    atc: ATCUtility,
    cai_fn,
    beta: float = DEFAULT_BETA,
    mfe_value: Optional[float] = None,
) -> tuple:
    """Returns (feasible, log G(x)) with the hard predicate from codon.feasible_edit."""
    feasible = feasible_edit(y, x)
    if not feasible:
        return False, float("-inf")
    cai_val = cai_fn(y)
    if mfe_value is None:
        mfe_value = mfe(y)
    u = atc.utility(cai_val, -mfe_value, -abs(gc_fraction(y) - atc.gc_target),
                    -motif_penalty(y, atc.motif_weights))
    return True, beta * u
