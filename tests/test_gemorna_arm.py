from types import SimpleNamespace

import scripts.gemorna_arm as arm


def test_persistent_gemorna_includes_official_src_in_pythonpath(monkeypatch):
    monkeypatch.setattr(arm, "REPO", "/teams/gemorna")
    captured = {}

    def run(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout='{"sequence":"ATG","naturalness":null}\n', stderr="")

    monkeypatch.setattr(arm.subprocess, "run", run)
    assert arm.run_generate_batch("M", 1) == [("ATG", None)]
    assert captured["env"]["PYTHONPATH"].startswith("/teams/gemorna/src:")
