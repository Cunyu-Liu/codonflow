import copy
import json

import pytest

from scripts.a7_g2_gate import SIMPLE_METHODS, evaluate_g2


def paired_payload(gene, seed, method):
    learned = method == "learned"
    return {
        "protocol_version": "a7_evaluation_v1",
        "run_id": f"{gene}_{method}_{seed}",
        "method": method,
        "status": "done",
        "seed": seed,
        "record_id": gene,
        "source_sha256": "a" * 64,
        "initial_sha256": "b" * 64,
        "benchmark_sha256": "c" * 64,
        "data_split_sha256": "d" * 64,
        "calibration_sha256": "e" * 64,
        "rscu_sha256": "f" * 64,
        "code_commit": "1234567",
        "code_dirty": False,
        "checkpoint_path": "/teams/model.pt" if learned else None,
        "checkpoint_sha256": "9" * 64 if learned else None,
        "device": "cuda:0" if learned else None,
        "points": [{"budget": i, "sequence": f"sequence-{i}", "objectives": [1, 1, 1, 1]}
                   for i in range(1, 501)],
        "costs": {"forward_calls": 2000 if learned else 0, "base_state_evaluations": 0,
                  "rollout_batch_forwards": 0, "rollout_state_transitions": 0,
                  "terminal_reward_evaluations": 500, "unique_terminal_reward_calls": 500,
                  "elapsed_s": 1.0},
        "identity_rate": 1.0,
        "ned": 0.8 if learned else 0.7,
        "anytime": {"auc": 1.2 if learned else (1.0 if method == "hill_climbing" else 0.8),
                    "curve": [{"budget": budget, "hv": (1.2 if learned else (1.0 if method == "hill_climbing" else 0.8)) * fraction}
                              for budget, fraction in ((50, 0.5), (100, 0.75), (500, 1.0))]},
        "missing_methods": [],
        "exclusions": [],
    }


def make_arm(tmp_path, n_genes=18):
    paths = []
    for gene in range(n_genes):
        for seed in range(3):
            for method in ("learned", *SIMPLE_METHODS):
                payload = paired_payload(f"g{gene}", seed, method)
                path = tmp_path / f"g{gene}_{method}_{seed}.json"
                path.write_text(json.dumps(payload))
                paths.append(str(path))
    return {"name": "FULL", "checkpoint_sha256": "9" * 64, "paths": paths}


def test_g2_gate_accepts_complete_paired_positive_example(tmp_path):
    arm = make_arm(tmp_path)
    result = evaluate_g2([arm], {f"g{i}" for i in range(18)})
    assert result["passed"]
    assert len(result["arms"][0]["inputs"]) == 18 * 3 * 5
    assert result["arms"][0]["diversity"][0]["baseline"] == "hill_climbing"


@pytest.mark.parametrize("field,value", [("seed", 3), ("status", "partial"),
                                         ("identity_rate", 0.99), ("code_dirty", True)])
def test_g2_gate_rejects_invalid_or_unpaired_observations(tmp_path, field, value):
    arm = make_arm(tmp_path)
    payload = json.loads((tmp_path / "g0_learned_0.json").read_text())
    payload[field] = value
    (tmp_path / "g0_learned_0.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        evaluate_g2([arm], {f"g{i}" for i in range(18)})


def test_g2_gate_rejects_mismatched_initialization(tmp_path):
    arm = make_arm(tmp_path)
    payload = json.loads((tmp_path / "g0_uniform_0.json").read_text())
    payload["initial_sha256"] = "0" * 64
    (tmp_path / "g0_uniform_0.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="unmatched initial_sha256"):
        evaluate_g2([arm], {f"g{i}" for i in range(18)})
