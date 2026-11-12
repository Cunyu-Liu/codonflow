import hashlib
import json

import pytest

from scripts.a7_g2_preflight import verify_gate_pair


def evidence(tmp_path, monkeypatch):
    benchmark = tmp_path / "benchmark.fasta"
    records = {f"g{i}": "ATGGCTTAA" for i in range(18)}
    benchmark.write_text("".join(f">{key}\n{value}\n" for key, value in records.items()))
    hashes = {str(benchmark): "b" * 64, "/teams/model.pt": "9" * 64}
    monkeypatch.setattr("scripts.a7_g2_preflight.file_sha256", lambda path: hashes[str(path)])
    convergence = tmp_path / "convergence.json"
    convergence.write_text(json.dumps({
        "protocol": "a7_convergence_audit_v1", "passed": True, "device": "cuda:0",
        "checkpoint_paths": {"converged.pt": "/teams/model.pt"},
        "checkpoint_sha256": {"converged.pt": "9" * 64},
    }))
    behavior = tmp_path / "g1.json"
    behavior.write_text(json.dumps({
        "protocol": "a7_g1_behavior_v1", "passed": True, "device": "cuda:0",
        "checkpoint_path": "/teams/model.pt", "checkpoint_sha256": "9" * 64,
        "benchmark_sha256": "b" * 64, "rscu_sha256": "r" * 64,
        "n_samples": 100, "records": [{"passed": True}] * 3,
    }))
    calibration = tmp_path / "calibration"
    calibration.mkdir()
    for record_id, source in records.items():
        (calibration / f"{record_id}.json").write_text(json.dumps({
            "source_role": "independent_calibration_not_test",
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "rscu_sha256": "r" * 64, "reference": [0, 0, 0, 0], "scale": [1, 1, 1, 1],
        }))
    return convergence, behavior, benchmark, calibration


def test_g2_preflight_binds_convergence_g1_and_calibration(tmp_path, monkeypatch):
    paths = evidence(tmp_path, monkeypatch)
    result = verify_gate_pair(*paths)
    assert len(result["records"]) == 18
    assert result["checkpoint_sha256"] == "9" * 64


def test_g2_preflight_rejects_checkpoint_mismatch(tmp_path, monkeypatch):
    convergence, behavior, benchmark, calibration = evidence(tmp_path, monkeypatch)
    payload = json.loads(behavior.read_text())
    payload["checkpoint_sha256"] = "0" * 64
    behavior.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="checkpoint"):
        verify_gate_pair(convergence, behavior, benchmark, calibration)
