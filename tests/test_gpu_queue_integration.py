import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.integration
def test_queue_lifecycle_in_isolated_tmux(tmp_path):
    if os.environ.get("CODONFLOW_RUN_TMUX_TEST") != "1":
        pytest.skip("explicit tmux integration opt-in")
    repo = Path(__file__).resolve().parents[1]
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo / "scripts")
    env["CODONFLOW_QUEUE_DIR"] = str(queue_dir)
    env["CODONFLOW_REGISTRY"] = str(tmp_path / "REGISTRY.md")
    result = subprocess.run(
        [sys.executable, "-c",
         "import gpu_queue as q; q.QUEUE_DIR=q.Path(q.os.environ['CODONFLOW_QUEUE_DIR']); q.REGISTRY=q.Path(q.os.environ['CODONFLOW_REGISTRY']); q.PENDING=q.QUEUE_DIR/'pending.json'; q.RUNNING=q.QUEUE_DIR/'running.json'; q.FAILED=q.QUEUE_DIR/'failed.json'; q.LOGS=q.QUEUE_DIR/'logs'; q.gpu_snapshot=lambda: [{'index':0,'used_gb':0,'total_gb':32,'util':0}]; q.write_json_atomic(q.PENDING, [{'run_id':'queue_smoke','cmd':'true','vram_gb':1,'priority':1}]); q.main_loop(once=True)"],
        env=env, cwd=repo, check=True, capture_output=True, text=True,
    )
    running = json.loads((queue_dir / "running.json").read_text())
    assert running[0]["run_id"] == "queue_smoke"
    for _ in range(100):
        if (queue_dir / "exit_queue_smoke").exists():
            break
        time.sleep(0.05)
    else:
        raise AssertionError("tmux command did not produce an exit file")
    subprocess.run(
        [sys.executable, "-c",
         "import gpu_queue as q; q.QUEUE_DIR=q.Path(q.os.environ['CODONFLOW_QUEUE_DIR']); q.REGISTRY=q.Path(q.os.environ['CODONFLOW_REGISTRY']); q.PENDING=q.QUEUE_DIR/'pending.json'; q.RUNNING=q.QUEUE_DIR/'running.json'; q.FAILED=q.QUEUE_DIR/'failed.json'; q.LOGS=q.QUEUE_DIR/'logs'; q.main_loop(once=True)"],
        env=env, cwd=repo, check=True, capture_output=True, text=True,
    )
    assert json.loads((queue_dir / "running.json").read_text()) == []
    assert "queue_smoke" in (tmp_path / "REGISTRY.md").read_text()
