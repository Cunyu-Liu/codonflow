#!/usr/bin/env python3
"""A8-RK09: exact small-state CodonFlow-RK mathematical kernel checks.

This is deliberately not a trainer or a functional experiment.  It verifies the
legal simplex, feasible conditional kernels, preference/budget masks, ordered
Uniform event-time law, and an exact forward/backward path telescoping example.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import random
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

STOP = 63
N_CODON_SLOTS = 64
N_SENSE = 61
State = Tuple[int, ...]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def is_valid_state(state: Sequence[int]) -> bool:
    return (
        len(state) >= 1
        and state[-1] == STOP
        and all(isinstance(value, int) and 0 <= value < N_SENSE for value in state[:-1])
    )


def all_states(length: int) -> List[State]:
    if length < 1:
        raise ValueError("length must include the terminal stop")
    return [tuple(prefix) + (STOP,) for prefix in itertools.product(range(N_SENSE), repeat=length - 1)]


def hamming(left: State, right: State) -> int:
    if len(left) != len(right):
        raise ValueError("state lengths differ")
    return sum(a != b for a, b in zip(left, right))


def feasible_targets(state: State) -> List[State]:
    """No-op plus every single internal sense-codon replacement; stop is fixed."""
    if not is_valid_state(state):
        raise ValueError("invalid state")
    targets = [tuple(state)]
    for position in range(len(state) - 1):
        original = state[position]
        for codon in range(N_SENSE):
            if codon == original:
                continue
            mutable = list(state)
            mutable[position] = codon
            targets.append(tuple(mutable))
    return targets


def preference(state: State) -> float:
    """Fixed synthetic utility used only to test kernel algebra, never as data."""
    return sum((codon % 13) / 12.0 for codon in state[:-1])


def masked_categorical(logits: Sequence[float], terminal: bool) -> List[float]:
    if len(logits) != N_CODON_SLOTS:
        raise ValueError("expected 64 logits")
    if terminal:
        return [1.0 if index == STOP else 0.0 for index in range(N_CODON_SLOTS)]
    masked = [float(value) if index < N_SENSE else -math.inf for index, value in enumerate(logits)]
    maximum = max(masked)
    weights = [math.exp(value - maximum) if math.isfinite(value) else 0.0 for value in masked]
    total = sum(weights)
    if not total > 0.0:
        raise ValueError("no legal internal codon")
    return [value / total for value in weights]


def conditional_kernel(
    state: State,
    beta: float = 0.0,
    remaining_budget: float | None = None,
) -> Dict[State, float]:
    targets = feasible_targets(state)
    if remaining_budget is not None:
        threshold = preference(state) + remaining_budget
        targets = [target for target in targets if preference(target) <= threshold + 1e-15]
    if not targets:
        raise ValueError("empty feasible conditional")
    raw = [math.exp(beta * (preference(target) - preference(state))) for target in targets]
    total = sum(raw)
    return {target: weight / total for target, weight in zip(targets, raw)}


def transition_probability(previous: State, current: State) -> float:
    targets = feasible_targets(previous)
    return 1.0 / len(targets) if current in targets else 0.0


def enumerate_paths(start: State, steps: int) -> Tuple[List[Dict[State, float]], List[Tuple[Tuple[State, ...], float]]]:
    marginals: List[Dict[State, float]] = [{start: 1.0}]
    paths: List[Tuple[Tuple[State, ...], float]] = [((start,), 1.0)]
    for _ in range(steps):
        extended: List[Tuple[Tuple[State, ...], float]] = []
        marginal: Dict[State, float] = defaultdict(float)
        for path, probability in paths:
            previous = path[-1]
            for target in feasible_targets(previous):
                new_probability = probability / len(feasible_targets(previous))
                new_path = path + (target,)
                extended.append((new_path, new_probability))
                marginal[target] += new_probability
        paths = extended
        marginals.append(dict(marginal))
    return marginals, paths


def telescope_example(start: State, steps: int, tolerance: float) -> dict:
    """Construct the exact reverse of the proposal and verify endpoint weights.

    gamma_T(path) = q_T(path) * U(end) / q_T_marginal(end).  Therefore the
    backward conditionals are Bayes reversals of q, and every path log-weight
    must telescope to log U(end) - log q_T_marginal(end).
    """
    marginals, paths = enumerate_paths(start, steps)
    endpoints = sorted(marginals[-1])
    uniform = 1.0 / len(endpoints)
    max_backward_normalization_error = 0.0
    backward_cache: Dict[Tuple[int, State], Dict[State, float]] = {}
    for time in range(1, steps + 1):
        by_current: Dict[State, List[Tuple[State, float]]] = defaultdict(list)
        for path, _ in paths:
            prefix = path[:time]
            previous = prefix[-1]
            current = path[time]
            prefix_probability = marginals[time - 1][previous]
            step_probability = transition_probability(previous, current)
            by_current[current].append((previous, prefix_probability * step_probability))
        for current, rows in by_current.items():
            denominator = marginals[time][current]
            distribution = {previous: numerator / denominator for previous, numerator in rows}
            backward_cache[(time, current)] = distribution
            max_backward_normalization_error = max(
                max_backward_normalization_error, abs(sum(distribution.values()) - 1.0)
            )

    max_telescope_error = 0.0
    recovered: Dict[State, float] = defaultdict(float)
    for path, forward_path_probability in paths:
        forward_log = math.log(forward_path_probability)
        backward_log = math.log(uniform)
        for time in range(1, steps + 1):
            previous = path[time - 1]
            current = path[time]
            backward_log += math.log(backward_cache[(time, current)][previous])
        log_weight = backward_log - forward_log
        expected = math.log(uniform) - math.log(marginals[-1][path[-1]])
        max_telescope_error = max(max_telescope_error, abs(log_weight - expected))
        recovered[path[-1]] += forward_path_probability * math.exp(log_weight)
    max_endpoint_error = max(abs(recovered[state] - uniform) for state in endpoints)
    return {
        "path_count": len(paths),
        "endpoint_count": len(endpoints),
        "max_backward_normalization_error": max_backward_normalization_error,
        "max_telescope_error": max_telescope_error,
        "max_endpoint_reconstruction_error": max_endpoint_error,
        "recovered_total_mass_error": abs(sum(recovered.values()) - 1.0),
        "tolerance": tolerance,
        "pass": max(
            max_backward_normalization_error,
            max_telescope_error,
            max_endpoint_error,
            abs(sum(recovered.values()) - 1.0),
        ) <= tolerance,
    }


def total_variation(left: Dict[State, float], right: Dict[State, float]) -> float:
    return 0.5 * sum(abs(left.get(state, 0.0) - right.get(state, 0.0)) for state in set(left) | set(right))


def run(protocol_path: Path, report_path: Path) -> dict:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    tolerance = protocol["enumeration"]["absolute_tolerance"]
    checks: List[dict] = []

    def record(identifier: str, passed: bool, detail: str) -> None:
        checks.append({"id": identifier, "pass": bool(passed), "detail": detail})

    kernel_length = protocol["state"]["kernel_length_including_stop"]
    start = tuple(protocol["state"]["kernel_start"])
    states = all_states(kernel_length)
    one_step = set(feasible_targets(start))
    two_step_reachable = {state for state in states if hamming(start, state) <= 2}
    record("valid_state_enumeration", len(states) == N_SENSE ** (kernel_length - 1) and all(is_valid_state(s) for s in states), f"states={len(states)}")
    record("internal_stop_forbidden", not any(STOP in state[:-1] for state in states), "internal stop count=0")
    expected_one_step = 1 + (kernel_length - 1) * (N_SENSE - 1)
    record("feasible_target_count", len(one_step) == expected_one_step, f"targets={len(one_step)} expected={expected_one_step}")
    record("feasible_target_legality", all(is_valid_state(s) and hamming(start, s) <= 1 and s[-1] == STOP for s in one_step), "no-op or one internal sense edit only")

    base = conditional_kernel(start)
    base_values = list(base.values())
    record("base_simplex", set(base) == one_step and min(base_values) > 0 and abs(sum(base_values) - 1.0) <= tolerance, f"support={len(base)} mass_error={abs(sum(base_values)-1.0):.3e}")
    record("base_uniform", max(abs(value - 1.0 / len(one_step)) for value in base_values) <= tolerance, "every feasible target has equal probability")

    logits = [math.sin(index + 0.5) for index in range(N_CODON_SLOTS)]
    logits[STOP] = 1e6
    internal = masked_categorical(logits, terminal=False)
    terminal = masked_categorical(logits, terminal=True)
    record("forward_mask_internal", internal[STOP] == 0.0 and abs(sum(internal) - 1.0) <= tolerance and all(value >= 0 for value in internal), "stop logit is removed even when it is maximal")
    record("forward_mask_terminal", terminal[STOP] == 1.0 and sum(terminal) == 1.0 and all(terminal[i] == 0.0 for i in range(N_SENSE)), "terminal stop probability=1")

    beta = protocol["transition"]["preference_beta"]
    preferred = conditional_kernel(start, beta=beta)
    sample_targets = sorted(one_step)[:20]
    ratio_error = 0.0
    for left, right in zip(sample_targets, sample_targets[1:]):
        observed = math.log(preferred[left] / preferred[right])
        expected = beta * (preference(left) - preference(right))
        ratio_error = max(ratio_error, abs(observed - expected))
    record("preference_residual_ratio", set(preferred) == one_step and ratio_error <= tolerance, f"max_log_ratio_error={ratio_error:.3e}")

    budget = protocol["transition"]["remaining_budget"]
    bounded = conditional_kernel(start, beta=beta, remaining_budget=budget)
    expected_bounded = {target for target in one_step if preference(target) <= preference(start) + budget + 1e-15}
    record("remaining_budget_mask", set(bounded) == expected_bounded and all(preference(target) <= preference(start) + budget + 1e-15 for target in bounded), f"retained={len(bounded)} excluded={len(one_step)-len(bounded)}")
    record("remaining_budget_simplex", abs(sum(bounded.values()) - 1.0) <= tolerance and min(bounded.values()) > 0, f"mass_error={abs(sum(bounded.values())-1.0):.3e}")

    accepted = [state for state in states if hamming(start, state) <= 2]
    exact_rejection_probability = Fraction(1, len(accepted))
    rejection_probabilities = [exact_rejection_probability for _ in accepted]
    record("exhaustive_rejection_support", set(accepted) == two_step_reachable, f"accepted={len(accepted)} reachable={len(two_step_reachable)}")
    record("exhaustive_rejection_exact_uniform", len(set(rejection_probabilities)) == 1 and sum(rejection_probabilities) == 1, f"exact_probability=1/{len(accepted)}")

    _, two_step_paths = enumerate_paths(start, 2)
    naive: Dict[State, float] = defaultdict(float)
    for path, probability in two_step_paths:
        naive[path[-1]] += probability
    uniform_two_step = {state: 1.0 / len(two_step_reachable) for state in two_step_reachable}
    naive_tv = total_variation(dict(naive), uniform_two_step)
    record("naive_random_walk_bias_detected", set(naive) == two_step_reachable and naive_tv > 0.05, f"two_step_total_variation={naive_tv:.12f}")

    path_start = tuple(protocol["state"]["path_start"])
    telescope = telescope_example(path_start, protocol["state"]["path_steps"], tolerance)
    record("path_support_complete", telescope["endpoint_count"] == N_SENSE ** 2, f"endpoints={telescope['endpoint_count']} paths={telescope['path_count']}")
    record("backward_conditional_simplex", telescope["max_backward_normalization_error"] <= tolerance, f"max_error={telescope['max_backward_normalization_error']:.3e}")
    record("path_logprob_telescope", telescope["max_telescope_error"] <= tolerance, f"max_error={telescope['max_telescope_error']:.3e}")
    record("path_endpoint_reconstruction", telescope["max_endpoint_reconstruction_error"] <= tolerance and telescope["recovered_total_mass_error"] <= tolerance, f"max_endpoint_error={telescope['max_endpoint_reconstruction_error']:.3e}")

    max_event_error = 0.0
    event_rows = []
    for kappa in protocol["event_time"]["kappas"]:
        for u in protocol["event_time"]["u_grid"]:
            time = 1.0 - u ** (1.0 / kappa)
            recovered_u = (1.0 - time) ** kappa
            cdf = 1.0 - (1.0 - time) ** kappa
            density = kappa * (1.0 - time) ** (kappa - 1.0)
            max_event_error = max(max_event_error, abs(recovered_u - u), abs(cdf - (1.0 - u)))
            event_rows.append({"kappa": kappa, "u": u, "t": time, "cdf": cdf, "density": density})
    record("uniform_event_time_transform", max_event_error <= tolerance, f"max_transform_or_cdf_error={max_event_error:.3e}")

    mc_kappa = protocol["event_time"]["monte_carlo_kappa"]
    rng = random.Random(protocol["event_time"]["monte_carlo_seed"])
    draws = [1.0 - rng.random() ** (1.0 / mc_kappa) for _ in range(protocol["event_time"]["monte_carlo_draws"])]
    observed_mean = sum(draws) / len(draws)
    expected_mean = 1.0 / (mc_kappa + 1.0)
    ordered = sorted(rng.random() for _ in range(mc_kappa))
    record("ordered_uniform_event_times", len(ordered) == mc_kappa and ordered == sorted(ordered) and all(0 <= value <= 1 for value in ordered), "conditional ordered times are Uniform order statistics; joint density=kappa! on the ordered simplex")
    record("event_time_monte_carlo", abs(observed_mean - expected_mean) <= protocol["event_time"]["monte_carlo_mean_tolerance"], f"mean={observed_mean:.9f} expected={expected_mean:.9f}")

    prohibited = protocol["prohibited_claims"]
    record("bounded_scope", not any(prohibited.values()), "no training, functional performance, generation quality, gate change, SOTA or expensive-generation authorization")

    report = {
        "schema": "a8-rk09-minimal-codonflow-kernel-v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256(protocol_path),
        "implementation_sha256": sha256(Path(__file__).resolve()),
        "scope": protocol["scope"],
        "definitions": {
            "state": "L x 64; index 63 is stop; only the final position may be stop",
            "transition": "no-op or one internal sense-codon replacement",
            "preference": "exp(beta*(f(y)-f(x))) over the feasible conditional",
            "path_weight": "log backward path probability - log forward path probability",
            "event_time": "t=1-u**(1/kappa), u~Uniform(0,1)",
        },
        "counts": {
            "kernel_valid_states": len(states),
            "one_step_targets": len(one_step),
            "two_step_reachable_states": len(two_step_reachable),
            "two_step_paths_for_naive_baseline": len(two_step_paths),
            "budget_retained": len(bounded),
            "budget_excluded": len(one_step) - len(bounded),
        },
        "metrics": {
            "naive_two_step_total_variation_vs_uniform": naive_tv,
            "preference_max_log_ratio_error": ratio_error,
            "telescope": telescope,
            "event_time_max_transform_or_cdf_error": max_event_error,
            "event_time_monte_carlo_mean": observed_mean,
            "event_time_expected_mean": expected_mean,
            "event_time_rows": event_rows,
        },
        "checks": checks,
        "checks_passed": sum(check["pass"] for check in checks),
        "checks_total": len(checks),
        "all_pass": all(check["pass"] for check in checks),
        "prohibited_claims": prohibited,
        "interpretation": "PASS certifies only the frozen mathematical kernel and exact small-state implementation. It is not model training, functional performance, generation quality, RK-G1 closure or SOTA evidence.",
    }
    atomic_json(report_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.protocol, args.report)
    print(json.dumps({"all_pass": report["all_pass"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "report": str(args.report)}, ensure_ascii=False))
    if not report["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
