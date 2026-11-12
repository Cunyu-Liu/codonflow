import json

import pytest

from codonflow.train.run_pretrain import file_sha256
from scripts.a7_run_training import preflight, training_command


def make_config(tmp_path):
    train = tmp_path / "train.fasta"
    val = tmp_path / "val.fasta"
    train.write_text(">a\nATGGCTTAA\n")
    val.write_text(">b\nATGGCCTAA\n")
    return {"status": "frozen_pending_g0", "corruption": "synonymous", "resume": None,
            "max_epochs": None, "max_steps": None, "train_fasta": str(train),
            "val_fasta": str(val), "train_sha256": file_sha256(train), "val_sha256": file_sha256(val),
            "out_dir": str(tmp_path / "out"), "d_model": 768, "n_layers": 8, "n_heads": 12,
            "dropout": 0.0, "lr": 1e-5, "wd": 0.03, "batch_tokens": 20000, "max_batch": 128,
            "grad_accum": 3, "grad_clip": 1.0, "val_batch_tokens": 24000, "seed": 0,
            "validation_seed": 1729, "token_only_at_edits": False, "gpu_mem_fraction": 0.35}


def test_training_command_preserves_frozen_contract(tmp_path):
    config = make_config(tmp_path)
    command = training_command(config)
    assert "--corruption" in command and "synonymous" in command
    assert "--resume" not in command and "--token-only-at-edits" not in command


def test_preflight_requires_g0_and_matching_hashes(tmp_path):
    config = make_config(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"passed": False}))
    with pytest.raises(ValueError, match="G0"):
        preflight(config_path, gate)
    gate.write_text(json.dumps({"passed": True}))
    assert "codonflow.train.run_pretrain" in preflight(config_path, gate)
