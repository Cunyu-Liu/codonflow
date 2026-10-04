import numpy as np
import torch

from codonflow.gating.atc import (
    ATCUtility,
    DEFAULT_NORM_STATS,
    feasibility_and_log_utility,
    gated_log_weight,
)
from codonflow.eval.metrics import cai, cai_weights_from_rscu
from tests.test_metrics import RSCU_EQUAL


def _toy_atc():
    return ATCUtility(
        norm_stats={k: dict(v) for k, v in DEFAULT_NORM_STATS.items()},
        omega=(1.0, 1.0, 1.0, 0.5),
        rho=0.01,
    )


def test_utility_monotone_in_cai():
    atc = _toy_atc()
    u_low = atc.utility(0.6, -100.0, -0.05, 0.0)
    u_high = atc.utility(0.9, -100.0, -0.05, 0.0)
    assert u_high > u_low


def test_utility_bounds():
    atc = _toy_atc()
    u = atc.utility(0.5, -1000.0, -0.5, -10.0)
    assert 0.0 <= u <= 1.0 + 1e-9


def test_gated_log_weight():
    assert gated_log_weight(0.7, feasible=True) == 0.7
    assert gated_log_weight(0.7, feasible=False) == float("-inf")


def test_tchebycheff_min_semantics():
    atc = _toy_atc()
    f = [0.9, 0.1, 0.9, 0.9]
    u = atc.utility_from_normalized(f)
    assert u <= min(1.0, 0.5) + 0.01 * (0.9 + 0.1 + 0.9 + 0.5)


def test_feasibility_gate():
    atc = _toy_atc()
    x = "ATGGCTTAA"
    y = "ATGGCCTAA"
    w = cai_weights_from_rscu(RSCU_EQUAL)
    feasible, log_g = feasibility_and_log_utility(
        y, x, atc, lambda s: cai(s, w), mfe_value=-10.0
    )
    assert feasible
    assert log_g > 0

    bad = "ATGAATTAA"
    feasible2, log_g2 = feasibility_and_log_utility(
        bad, x, atc, lambda s: cai(s, w), mfe_value=-10.0
    )
    assert not feasible2
    assert log_g2 == float("-inf")
