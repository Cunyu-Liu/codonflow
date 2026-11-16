import json

import pytest

import scripts.a7_execute_proposal_in_loop as executor
from scripts.a7_execute_proposal_in_loop import parse_arm


def test_execute_diagnostic_arm_parser():
    assert parse_arm("FULL=/teams/model.pt:" + "a" * 64) == ("FULL", "/teams/model.pt", "a" * 64)
    with pytest.raises(ValueError):
        parse_arm("INVALID=/teams/model.pt:" + "a" * 64)
    with pytest.raises(ValueError):
        parse_arm("FULL=/teams/model.pt:short")


def test_development15_dry_run_has_90_tasks(monkeypatch, capsys, tmp_path):
    records = [(f"g{index}", "TTTGCTTAA") for index in range(18)]
    monkeypatch.setattr(executor, "read_fasta", lambda _path: records)
    monkeypatch.setattr(executor, "file_sha256", lambda _path: "a" * 64)
    monkeypatch.setattr(executor, "validate_baseline", lambda *_args: {})
    monkeypatch.setattr(executor, "resolve_accepted_code_commits", lambda _values: frozenset({"a" * 40}))
    monkeypatch.setattr(executor.subprocess, "check_output", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(executor, "git_commit", lambda: "a" * 40)
    argv = ["execute", "--benchmark-fasta", str(tmp_path / "benchmark.fasta"),
            "--baseline-dir", "/teams/baseline", "--rscu-json", "/teams/rscu.json",
            "--calibration-dir", "/teams/calibration", "--data-split-sha256", "b" * 64,
            "--baseline-code-commit", "a" * 64,
            "--out-root", "/teams/development15", "--dry-run"]
    for arm in ("FULL", "EDIT"):
        argv.extend(["--arm", f"{arm}=/teams/{arm}.pt:{'a' * 64}"])
    for record_id in ("g0", "g1", "g2"):
        argv.extend(["--exclude-record-id", record_id])
    monkeypatch.setattr("sys.argv", argv)
    executor.main()
    result = json.loads(capsys.readouterr().out)
    assert result["ready"] is True and result["n_tasks"] == 90
    assert result["selected_record_ids"] == [f"g{index}" for index in range(3, 18)]
    assert result["excluded_record_ids"] == ["g0", "g1", "g2"]
    assert result["scientific_gate_passed"] is False
