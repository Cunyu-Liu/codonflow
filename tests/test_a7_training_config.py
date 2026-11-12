import json
from pathlib import Path

import pytest


@pytest.mark.parametrize("name,expected_fraction,expected_edits", [
    ("M_SYN_D4_FULL_seed0", 0.35, False),
    ("M_SYN_D4_EDIT_seed0", 0.30, True),
])
def test_frozen_d4_training_contract(name, expected_fraction, expected_edits):
    path = Path(__file__).parents[1] / "configs" / "a7" / f"{name}.json"
    config = json.loads(path.read_text())
    assert config["status"] == "frozen_pending_g0"
    assert config["corruption"] == "synonymous"
    assert config["resume"] is None
    assert config["max_epochs"] is None and config["max_steps"] is None
    assert config["gpu_mem_fraction"] == expected_fraction
    assert config["token_only_at_edits"] is expected_edits
    assert config["batch_tokens"] * config["grad_accum"] == config["effective_batch_tokens"] == 60000
    assert config["convergence"] == {"relative_tolerance": 0.001, "patience_epochs": 3}
    assert config["train_fasta"] != config["val_fasta"]
    assert config["train_sha256"] != config["val_sha256"]


def test_r4_preserves_validation_protocol_and_provides_headroom():
    root = Path(__file__).parents[1] / "configs" / "a7"
    full = json.loads((root / "M_SYN_D4_FULL_seed0_r4.json").read_text())
    edit = json.loads((root / "M_SYN_D4_EDIT_seed0_r4.json").read_text())
    for config in (full, edit):
        assert config["resume"] is None
        assert config["val_batch_tokens"] == 24000
        assert config["val_micro_batch_tokens"] == 4000
        assert config["corruption"] == "synonymous"
        assert config["out_dir"].endswith("_r4")
        assert config["batch_tokens"] * config["grad_accum"] == 60000
        assert config["max_epochs"] is None and config["max_steps"] is None
    assert full["gpu_mem_fraction"] == 0.35
    assert edit["gpu_mem_fraction"] == 0.42
    assert full["gpu_mem_fraction"] + edit["gpu_mem_fraction"] < 0.8
