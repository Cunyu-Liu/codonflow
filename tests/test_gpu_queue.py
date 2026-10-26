import json

import scripts.gpu_queue as queue


def test_completion_returns_only_finished_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(queue, "QUEUE_DIR", tmp_path)
    (tmp_path / "exit_done").write_text("0\n")
    (tmp_path / "exit_failed").write_text("2\n")
    jobs = [{"run_id": "done"}, {"run_id": "running"}, {"run_id": "failed"}]
    active, completed = queue.check_finished(jobs)
    assert [j["run_id"] for j in active] == ["running"]
    assert [(j["run_id"], j["status"]) for j in completed] == [("done", "done"), ("failed", "failed")]


def test_gpu_snapshot_parses_lines(monkeypatch):
    class Result:
        stdout = "0, 100, 32000, 7\n"
    monkeypatch.setattr(queue.subprocess, "run", lambda *a, **kw: Result())
    assert queue.gpu_snapshot()[0]["index"] == 0


def test_resource_accounting_within_iteration(monkeypatch):
    gpus = [{"index": 0, "total_gb": 32, "used_gb": 11, "util": 0}]
    assert queue.find_free_gpus(gpus, 16, 1) == [0]
    gpus[0]["used_gb"] += 16
    assert queue.find_free_gpus(gpus, 2, 1) is None
