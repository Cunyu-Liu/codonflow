import json

import pytest
import torch

from codonflow.train.run_pretrain import file_sha256
from scripts.a7_follow_g1 import parse_arm_configs
from scripts.a7_resume_training import prepare_resume
from scripts.a7_run_training import training_command


def make_resume(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    train = tmp_path / "train.fasta"
    val = tmp_path / "val.fasta"
    train.write_text(">a\nATGGCTTAA\n")
    val.write_text(">b\nATGGCCTAA\n")
    source = tmp_path / "r4"
    source.mkdir()
    history = [{"epoch": 1, "val_loss": 1.0}, {"epoch": 2, "val_loss": 0.9}]
    (source / "log.jsonl").write_text("".join(json.dumps(row) + "\n" for row in history))
    torch.save({"weight": torch.tensor([1.0])}, source / "best.pt")
    state = {"model": {"weight": torch.tensor([1.0])}, "optimizer": {"state": {"step": 2}},
             "epoch": 2, "best_epoch": 2, "best_val_loss": 0.9,
             "rng": {"cpu": torch.tensor([1]), "cuda": [torch.tensor([2])]}}
    gate = tmp_path / "g0.json"
    gate.write_text(json.dumps({"passed": True}))
    config_path = tmp_path / "r5.json"
    config = {"protocol_version": "a7_train_d4_v1", "run_id": "M_SYN_D4_FULL_seed0_r5",
              "status": "frozen_resume_from_complete_epoch", "corruption": "synonymous",
              "resume": str(source / "training_state.pt"), "max_epochs": None, "max_steps": None,
              "train_fasta": str(train), "val_fasta": str(val),
              "train_sha256": file_sha256(train), "val_sha256": file_sha256(val),
              "out_dir": str(tmp_path / "r5"), "d_model": 768, "n_layers": 8, "n_heads": 12,
              "dropout": 0.0, "lr": 1e-5, "wd": 0.03, "batch_tokens": 20000, "max_batch": 128,
              "grad_accum": 3, "grad_clip": 1.0, "val_batch_tokens": 24000,
              "val_micro_batch_tokens": 4000, "seed": 0,
              "validation_seed": 1729, "token_only_at_edits": False, "gpu_mem_fraction": 0.35}
    state["config"] = dict(config)
    torch.save(state, source / "training_state.pt")
    config_path.write_text(json.dumps(config))
    return config_path, gate, source


def test_resume_command_requires_explicit_frozen_state(tmp_path):
    config_path, _gate, _source = make_resume(tmp_path)
    config = json.loads(config_path.read_text())
    assert "--resume" in training_command(config, allow_resume=True)
    with pytest.raises(ValueError, match="status"):
        training_command(config)


def test_prepare_resume_copies_and_binds_complete_state(tmp_path):
    config_path, gate, source = make_resume(tmp_path)
    command, provenance = prepare_resume(config_path, gate)
    out_dir = tmp_path / "r5"
    assert command[command.index("--resume") + 1] == str(out_dir / "resume_input.pt")
    assert provenance["resume_epoch"] == 2 and provenance["passed"] is True
    assert file_sha256(out_dir / "resume_input.pt") == file_sha256(source / "training_state.pt")
    assert file_sha256(out_dir / "best.pt") == file_sha256(source / "best.pt")
    assert set(parse_arm_configs([f"FULL={config_path}"])) == {"FULL"}


def test_resume_rejects_inconsistent_history_and_existing_output(tmp_path):
    config_path, gate, source = make_resume(tmp_path)
    (source / "log.jsonl").write_text(json.dumps({"epoch": 1, "val_loss": 1.0}) + "\n")
    with pytest.raises(ValueError, match="does not match"):
        prepare_resume(config_path, gate)
    assert not (tmp_path / "r5").exists()
    config_path, gate, _source = make_resume(tmp_path / "second")
    (tmp_path / "second" / "r5").mkdir()
    with pytest.raises(FileExistsError):
        prepare_resume(config_path, gate)


def test_watcher_rejects_tampered_resume_provenance(tmp_path):
    config_path, gate, _source = make_resume(tmp_path)
    _command, _provenance = prepare_resume(config_path, gate)
    manifest = tmp_path / "r5" / "resume_provenance.json"
    payload = json.loads(manifest.read_text())
    payload["frozen_resume_sha256"] = "0" * 64
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="provenance"):
        parse_arm_configs([f"FULL={config_path}"])


def test_resume_rejects_training_config_mismatch(tmp_path):
    config_path, gate, source = make_resume(tmp_path)
    state = torch.load(source / "training_state.pt", map_location="cpu", weights_only=True)
    state["config"]["lr"] = 0.1
    torch.save(state, source / "training_state.pt")
    with pytest.raises(ValueError, match="run configuration mismatch"):
        prepare_resume(config_path, gate)
