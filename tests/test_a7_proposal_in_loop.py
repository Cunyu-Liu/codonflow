import json

import pytest

from scripts.a7_run_proposal_in_loop import validate_baseline
from tests.test_a7_protocol import payload


def baseline_payload():
    result = payload()
    result.update({
        "method": "hill_climbing",
        "code_dirty": False,
        "identity_rate": 1.0,
        "points": [{"budget": index, "sequence": str(index), "objectives": [1, 1]}
                   for index in range(1, 501)],
    })
    result["costs"]["unique_terminal_reward_calls"] = 500
    result["costs"]["terminal_reward_evaluations"] = 500
    return result


def test_baseline_validation_requires_complete_unique_legal_paired_result(tmp_path):
    path = tmp_path / "baseline.json"
    result = baseline_payload()
    path.write_text(json.dumps(result))
    assert validate_baseline(path, {"record_id": "g1", "code_commit": "unknown"}) == result
    with pytest.raises(ValueError, match="resume mismatch"):
        validate_baseline(path, {"record_id": "other"})


def test_baseline_validation_rejects_duplicate_or_incomplete_results(tmp_path):
    path = tmp_path / "baseline.json"
    result = baseline_payload()
    result["points"][1]["sequence"] = result["points"][0]["sequence"]
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="500 unique legal solutions"):
        validate_baseline(path, {})
    result["status"] = "partial"
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="incomplete or dirty"):
        validate_baseline(path, {})
