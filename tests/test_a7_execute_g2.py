import json
from unittest.mock import patch

import pytest

from scripts.a7_execute_g2 import load_preflights, result_path
from scripts.a7_g2_gate import expand_arm_spec


def preflight(tmp_path, arm):
    value = {"protocol": "a7_g2_preflight_v1", "ready_for_g2": True,
             "scientific_gate_passed": False, "arm": arm, "code_dirty": False,
             "checkpoint_sha256": "9" * 64, "record_ids": [f"g{i}" for i in range(18)],
             "seeds": [0, 1, 2], "benchmark_fasta": "/teams/benchmark.fasta",
             "benchmark_sha256": "b" * 64, "calibration_dir": "/teams/calibration",
             "rscu_sha256": "r" * 64, "code_commit": "abc", "budget": 500,
             "terminal_step": 4, "path_batch_size": 32}
    path = tmp_path / f"{arm}.json"
    path.write_text(json.dumps(value))
    return path, value


def test_g2_executor_requires_matching_complete_preflights(tmp_path):
    full, _ = preflight(tmp_path, "FULL")
    edit, edit_value = preflight(tmp_path, "EDIT")
    arms = load_preflights([f"FULL={full}", f"EDIT={edit}"])
    assert len(arms["FULL"]["record_ids"]) == 18
    edit_value["record_ids"] = edit_value["record_ids"][:-1]
    edit.write_text(json.dumps(edit_value))
    with pytest.raises(ValueError):
        load_preflights([f"FULL={full}", f"EDIT={edit}"])


def test_gate_arm_combines_learned_and_shared_simple_globs():
    with patch("glob.glob", side_effect=lambda pattern: [pattern]):
        arm = expand_arm_spec(f"FULL,{'9' * 64},/teams/FULL/*_learned_s*.json,/teams/shared_simple/*_s*.json")
    assert len(arm["paths"]) == 2


def test_shared_simple_path_is_not_arm_specific(tmp_path):
    assert result_path(tmp_path, None, "g1", 0, "uniform") == tmp_path / "shared_simple/g1_uniform_s0.json"
