import json

import pytest

from codonflow.eval.protocol import validate_result_payload
from scripts.a7_compare import compare_paths


def payload():
    return {
        "protocol_version": "a7_evaluation_v1",
        "run_id": "r1",
        "status": "done",
        "seed": 0,
        "record_id": "g1",
        "source_sha256": "a" * 64,
        "benchmark_sha256": "b" * 64,
        "data_split_sha256": "c" * 64,
        "code_commit": "unknown",
        "code_dirty": None,
        "checkpoint_path": None,
        "checkpoint_sha256": None,
        "points": [{"budget": 1, "sequence": "TTTTAA", "objectives": [1, 1]}],
        "anytime": {"auc": 1.0},
        "costs": {
            "forward_calls": 0,
            "base_state_evaluations": 0,
            "rollout_batch_forwards": 0,
            "rollout_state_transitions": 0,
            "terminal_reward_evaluations": 1,
            "unique_terminal_reward_calls": 1,
            "elapsed_s": 0.1,
        },
        "missing_methods": [],
        "exclusions": [],
    }


def test_schema_accepts_complete_result():
    validate_result_payload(payload())


def test_schema_rejects_missing_cost_and_nonconsecutive_budget():
    broken = payload()
    del broken["costs"]["elapsed_s"]
    with pytest.raises(ValueError, match="missing cost"):
        validate_result_payload(broken)
    broken = payload()
    broken["points"].append({"budget": 3, "sequence": "TTCTAA", "objectives": [1, 1]})
    with pytest.raises(ValueError, match="consecutive"):
        validate_result_payload(broken)


def test_compare_uses_gene_level_paired_effects(tmp_path):
    paths = []
    for method, auc in [("learned", 1.2), ("uniform", 0.8), ("hill_climbing", 1.0)]:
        for gene in ["g1", "g2", "g3"]:
            item = payload()
            item.update({"record_id": gene, "method": method})
            item["anytime"] = {"auc": auc}
            path = tmp_path / f"{gene}_{method}.json"
            path.write_text(json.dumps(item))
            paths.append(str(path))
    result = compare_paths(paths, ["uniform", "hill_climbing"], n_bootstrap=100)
    assert result["n_genes"] == 3
    assert result["median_relative_improvement"] > 0
    assert result["holm_adjusted_p"] == result["wilcoxon_greater_p"]
