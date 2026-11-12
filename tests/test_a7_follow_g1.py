import json
import os
import sys
from pathlib import Path

import pytest

from scripts.a7_follow_g1 import launcher_running, parse_arm_configs, run_logged


def config(tmp_path, name):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"corruption": "synonymous", "resume": None,
                                "max_epochs": None, "max_steps": None}))
    return path


def test_watcher_accepts_only_unbounded_synonymous_configs(tmp_path):
    full = config(tmp_path, "FULL")
    edit = config(tmp_path, "EDIT")
    assert set(parse_arm_configs([f"FULL={full}", f"EDIT={edit}"])) == {"FULL", "EDIT"}
    payload = json.loads(full.read_text())
    payload["max_steps"] = 100
    full.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="step-bounded"):
        parse_arm_configs([f"FULL={full}"])


def test_watcher_checks_launcher_command(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    log = tmp_path / "train.log"
    log.with_name("train.pid").write_text("123")
    monkeypatch.setattr(os, "kill", lambda pid, signal: None)
    original = Path.read_bytes

    def read_bytes(path):
        if str(path) == "/proc/123/cmdline":
            return f"python a7_run_training.py --config {config_path}\0".encode()
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    assert launcher_running(log, config_path)


def test_run_logged_preserves_failure_output(tmp_path):
    log = tmp_path / "failure.log"
    with pytest.raises(Exception):
        run_logged([sys.executable, "-c", "import sys; print('stdout'); print('stderr', file=sys.stderr); sys.exit(2)"], log)
    assert "stdout" in log.read_text() and "stderr" in log.read_text()
