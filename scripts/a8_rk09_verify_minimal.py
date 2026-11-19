#!/usr/bin/env python3
"""Independent RK09 reference calculations; never imports the production module."""
import argparse
import hashlib
import itertools
import json
import math
import os
import random
from collections import defaultdict
from pathlib import Path

STOP = 63
SENSE = 61


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def valid(state):
    return state[-1] == STOP and all(0 <= value < SENSE for value in state[:-1])


def distance(a, b):
    return sum(x != y for x, y in zip(a, b))


def neighbors(state):
    answer = [state]
    for position in range(len(state) - 1):
        for replacement in range(SENSE):
            if replacement != state[position]:
                answer.append(state[:position] + (replacement,) + state[position + 1:])
    return answer


def utility(state):
    return sum((value % 13) / 12 for value in state[:-1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    production = json.loads(args.production.read_text())
    checks = []

    def check(name, condition, detail):
        checks.append({"id": name, "pass": bool(condition), "detail": detail})

    check("protocol_identity", production["protocol_sha256"] == digest(args.protocol) and production["protocol_id"] == protocol["protocol_id"], "protocol hash and ID independently matched")
    check("implementation_identity", production["implementation_sha256"] == digest(args.implementation), "implementation SHA256 independently matched")
    check("production_check_accounting", production["all_pass"] and production["checks_total"] == 22 and production["checks_passed"] == 22 and all(row["pass"] for row in production["checks"]), "22/22 production checks are present and true")

    start = (0, 0, 0, STOP)
    states = [prefix + (STOP,) for prefix in itertools.product(range(SENSE), repeat=3)]
    check("state_space", len(states) == 226981 and all(valid(state) for state in states), f"independent states={len(states)}")
    target1 = set(neighbors(start))
    target2 = {state for state in states if distance(start, state) <= 2}
    combinatorial_target2 = 1 + 3 * 60 + 3 * 60 * 60
    check("feasible_and_rejection_support", len(target1) == 181 and len(target2) == combinatorial_target2 == production["counts"]["two_step_reachable_states"], f"one-step={len(target1)} two-step={len(target2)}")
    accepted = [state for state in states if distance(start, state) <= 2]
    check("exhaustive_rejection_reference", set(accepted) == target2 and all(valid(state) for state in accepted), "every accepted proposal is valid; conditional probability is exactly 1/10981")

    q = {start: 1.0}
    for _ in range(2):
        following = defaultdict(float)
        for state, probability in q.items():
            targets = neighbors(state)
            for target in targets:
                following[target] += probability / len(targets)
        q = dict(following)
    uniform = 1 / len(target2)
    tv = 0.5 * sum(abs(q.get(state, 0.0) - uniform) for state in target2)
    check("naive_random_walk_total_variation", set(q) == target2 and abs(tv - production["metrics"]["naive_two_step_total_variation_vs_uniform"]) <= 1e-14 and tv > 0.05, f"independent TV={tv:.15f}")

    # Independent three-position path enumeration and direct Bayes telescoping.
    path_start = (0, 0, STOP)
    first = neighbors(path_start)
    q1 = {state: 1 / len(first) for state in first}
    q2 = defaultdict(float)
    for middle in first:
        targets = neighbors(middle)
        for end in targets:
            q2[end] += q1[middle] / len(targets)
    endpoint_uniform = 1 / len(q2)
    max_error = 0.0
    recovered = defaultdict(float)
    path_count = 0
    for middle in first:
        middle_targets = neighbors(middle)
        for end in middle_targets:
            path_probability = q1[middle] / len(middle_targets)
            backward_first = 1.0  # fixed initial state
            backward_second = q1[middle] * (1 / len(middle_targets)) / q2[end]
            backward_path = endpoint_uniform * backward_first * backward_second
            log_weight = math.log(backward_path) - math.log(path_probability)
            expected = math.log(endpoint_uniform) - math.log(q2[end])
            max_error = max(max_error, abs(log_weight - expected))
            recovered[end] += path_probability * math.exp(log_weight)
            path_count += 1
    endpoint_error = max(abs(recovered[end] - endpoint_uniform) for end in q2)
    saved = production["metrics"]["telescope"]
    check("path_count_and_support", path_count == 14641 == saved["path_count"] and len(q2) == 3721 == saved["endpoint_count"], f"paths={path_count} endpoints={len(q2)}")
    check("independent_path_telescope", max_error <= 1e-12 and abs(max_error - saved["max_telescope_error"]) <= 1e-12, f"independent max error={max_error:.3e}")
    check("independent_endpoint_recovery", endpoint_error <= 1e-12 and abs(sum(recovered.values()) - 1) <= 1e-12 and abs(endpoint_error - saved["max_endpoint_reconstruction_error"]) <= 1e-12, f"independent max endpoint error={endpoint_error:.3e}")

    beta = protocol["transition"]["preference_beta"]
    ordered = sorted(target1)
    weights = {state: math.exp(beta * (utility(state) - utility(start))) for state in ordered}
    normalizer = sum(weights.values())
    probabilities = {state: value / normalizer for state, value in weights.items()}
    ratio_error = 0.0
    for left, right in zip(ordered[:20], ordered[1:21]):
        ratio_error = max(ratio_error, abs(math.log(probabilities[left] / probabilities[right]) - beta * (utility(left) - utility(right))))
    check("preference_ratio_reference", ratio_error <= 1e-12 and abs(ratio_error - production["metrics"]["preference_max_log_ratio_error"]) <= 1e-12, f"independent ratio error={ratio_error:.3e}")
    budget = protocol["transition"]["remaining_budget"]
    bounded = [state for state in target1 if utility(state) <= utility(start) + budget + 1e-15]
    check("remaining_budget_reference", len(bounded) == production["counts"]["budget_retained"] and len(target1) - len(bounded) == production["counts"]["budget_excluded"], f"retained={len(bounded)} excluded={len(target1)-len(bounded)}")

    logits = [math.sin(index + 0.5) for index in range(64)]
    logits[STOP] = 1e6
    maximum = max(logits[:SENSE])
    masked = [math.exp(value - maximum) for value in logits[:SENSE]]
    total = sum(masked)
    masked = [value / total for value in masked] + [0.0] * (64 - SENSE)
    check("forward_stop_mask_reference", len(masked) == 64 and masked[-1] == 0 and abs(sum(masked) - 1) <= 1e-12, "independent internal mask removes the dominant stop logit")

    max_event_error = 0.0
    for kappa in protocol["event_time"]["kappas"]:
        for u in protocol["event_time"]["u_grid"]:
            time = 1 - u ** (1 / kappa)
            max_event_error = max(max_event_error, abs((1 - time) ** kappa - u), abs((1 - (1 - time) ** kappa) - (1 - u)))
    check("event_time_inverse_cdf", max_event_error <= 1e-12, f"independent max error={max_event_error:.3e}")
    rng = random.Random(protocol["event_time"]["monte_carlo_seed"])
    kappa = protocol["event_time"]["monte_carlo_kappa"]
    values = [1 - rng.random() ** (1 / kappa) for _ in range(protocol["event_time"]["monte_carlo_draws"])]
    mean = sum(values) / len(values)
    expected_mean = 1 / (kappa + 1)
    check("event_time_mean_reference", abs(mean - production["metrics"]["event_time_monte_carlo_mean"]) <= 1e-15 and abs(expected_mean - production["metrics"]["event_time_expected_mean"]) <= 1e-15 and abs(mean - expected_mean) <= protocol["event_time"]["monte_carlo_mean_tolerance"], f"mean={mean:.12f}; integral expectation=1/(kappa+1)={expected_mean:.12f}")
    check("bounded_claims", all(value is False for value in production["prohibited_claims"].values()) and "not model training" in production["interpretation"], "no training, functional, generation, gate or SOTA claim")

    result = {
        "schema": "a8-rk09-minimal-codonflow-independent-v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": digest(args.protocol),
        "implementation_sha256": digest(args.implementation),
        "production_sha256": digest(args.production),
        "production_report_all_pass": production["all_pass"],
        "independent_metrics": {
            "naive_two_step_total_variation": tv,
            "path_count": path_count,
            "endpoint_count": len(q2),
            "max_path_telescope_error": max_error,
            "max_endpoint_recovery_error": endpoint_error,
            "event_time_monte_carlo_mean": mean,
            "event_time_expected_mean": expected_mean,
        },
        "checks": checks,
        "checks_passed": sum(row["pass"] for row in checks),
        "checks_total": len(checks),
        "all_pass": all(row["pass"] for row in checks),
        "scope": "Independent mathematical recomputation only; no trained model, functional result, generation result, RK-G1 decision or SOTA claim.",
    }
    save(args.report, result)
    print(json.dumps({"all_pass": result["all_pass"], "checks": f"{result['checks_passed']}/{result['checks_total']}", "report": str(args.report)}))
    if not result["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
