import hashlib
import json

import pytest

from scripts.a7_follow_g2 import ready_status


def watcher_status(tmp_path, status="g1_passed_g2_preflight_ready"):
    arms = {}
    for arm in ("FULL", "EDIT"):
        path = tmp_path / f"{arm}.json"
        path.write_text(json.dumps({"arm": arm}))
        arms[arm] = {"status": "g1_passed", "g2_preflight": str(path),
                     "g2_preflight_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"status": status, "arms": arms}))
    return path


def test_g2_watcher_waits_without_claiming_readiness(tmp_path):
    assert ready_status(watcher_status(tmp_path, "waiting_for_convergence")) is None


def test_g2_watcher_requires_both_verified_preflights(tmp_path):
    paths = ready_status(watcher_status(tmp_path))
    assert set(paths) == {"FULL", "EDIT"}


def test_g2_watcher_stops_on_g1_failure(tmp_path):
    with pytest.raises(RuntimeError, match="G1 watcher failed"):
        ready_status(watcher_status(tmp_path, "failed"))
