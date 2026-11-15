import json

import pytest

from scripts.a7_run_simple_search import completed_result
from tests.test_a7_protocol import payload


def test_resume_accepts_only_matching_clean_complete_result(tmp_path):
    result = payload()
    result.update({"method": "uniform", "code_dirty": False, "code_commit": "abc",
                   "initial_sha256": "d" * 64})
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result))
    expected = {"record_id": "g1", "seed": 0, "method": "uniform",
                "code_commit": "abc", "initial_sha256": "d" * 64}
    assert completed_result(path, expected) == result


def test_resume_rejects_input_mismatch(tmp_path):
    result = payload()
    result.update({"method": "uniform", "code_dirty": False, "code_commit": "abc"})
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="resume mismatch"):
        completed_result(path, {"record_id": "different"})


def test_resume_rejects_partial_result(tmp_path):
    result = payload()
    result["status"] = "partial"
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="incomplete or dirty"):
        completed_result(path, {})


def test_resume_accepts_only_explicit_code_commit_set(tmp_path):
    result = payload()
    result.update({"method": "uniform", "code_dirty": False, "code_commit": "abc"})
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result))
    expected = {"code_commit": frozenset({"abc", "def"})}
    assert completed_result(path, expected) == result
    with pytest.raises(ValueError, match="resume mismatch for code_commit"):
        completed_result(path, {"code_commit": frozenset({"def"})})
