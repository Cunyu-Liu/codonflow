"""Validation for A7 frozen run artifacts."""
from __future__ import annotations

from typing import Mapping

REQUIRED_METADATA = (
    "protocol_version", "run_id", "status", "seed", "record_id",
    "source_sha256", "benchmark_sha256", "data_split_sha256",
    "code_commit", "code_dirty", "checkpoint_path", "checkpoint_sha256",
    "points", "anytime", "costs", "missing_methods", "exclusions",
)
REQUIRED_COSTS = (
    "forward_calls", "base_state_evaluations", "rollout_batch_forwards",
    "rollout_state_transitions", "terminal_reward_evaluations",
    "unique_terminal_reward_calls", "elapsed_s",
)


def validate_result_payload(payload: Mapping) -> None:
    missing = [key for key in REQUIRED_METADATA if key not in payload]
    if missing:
        raise ValueError(f"missing result metadata: {missing}")
    if payload["protocol_version"] != "a7_evaluation_v1":
        raise ValueError("unsupported protocol_version")
    if payload["status"] not in ("done", "failed", "partial", "architectural_exclusion"):
        raise ValueError("invalid run status")
    if not isinstance(payload["seed"], int) or payload["seed"] < 0:
        raise ValueError("seed must be a nonnegative integer")
    for key in ("source_sha256", "benchmark_sha256", "data_split_sha256"):
        value = payload[key]
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"{key} must be a SHA256 hex digest")
    if not isinstance(payload["points"], list) or not payload["points"]:
        raise ValueError("points must be a nonempty list")
    budgets = []
    for point in payload["points"]:
        budget = point.get("budget")
        objectives = point.get("objectives")
        if not isinstance(budget, int) or budget <= 0 or not isinstance(objectives, list):
            raise ValueError("invalid scored point")
        budgets.append(budget)
    if budgets != list(range(1, len(budgets) + 1)):
        raise ValueError("point budgets must be consecutive unique scorer calls")
    costs = payload["costs"]
    missing_costs = [key for key in REQUIRED_COSTS if key not in costs]
    if missing_costs:
        raise ValueError(f"missing cost fields: {missing_costs}")
    if costs["unique_terminal_reward_calls"] != len(payload["points"]):
        raise ValueError("unique scorer count does not match points")
    if not isinstance(payload["anytime"], dict) or "auc" not in payload["anytime"]:
        raise ValueError("anytime AUC is required")
