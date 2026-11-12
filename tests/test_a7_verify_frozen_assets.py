import hashlib
import json

from codonflow.eval.anytime import FrozenReference
from codonflow.train.run_pretrain import file_sha256
from scripts import a7_verify_frozen_assets as verifier


def make_assets(tmp_path, monkeypatch):
    fasta = tmp_path / "confirmation.fasta"
    fasta.write_text(">g1\nATGGCTTAA\n>g2\nATGGCCTAA\n")
    rscu = tmp_path / "rscu.json"
    rscu.write_text("{}")
    monkeypatch.setattr(verifier, "EXPECTED_CONFIRMATION_SHA256", file_sha256(fasta))
    monkeypatch.setattr(verifier, "EXPECTED_D5_RSCU_SHA256", file_sha256(rscu))
    calibration = tmp_path / "calibration"
    pools = calibration / "pools"
    pools.mkdir(parents=True)
    manifest = {"source_role": "independent_calibration_generation_not_final_evaluation",
                "benchmark_sha256": file_sha256(fasta), "rscu_sha256": file_sha256(rscu), "records": []}
    points = [[0.1, 0.2, 0.3, 0.4], [0.2, 0.3, 0.4, 0.5],
              [0.3, 0.1, 0.6, 0.2], [0.4, 0.5, 0.2, 0.7]]
    for record_id, source in (("g1", "ATGGCTTAA"), ("g2", "ATGGCCTAA")):
        frozen = FrozenReference.from_calibration(points)
        reference = {"source_role": "independent_calibration_not_test", "record_id": record_id,
                     "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                     "rscu_sha256": file_sha256(rscu), "n_calibration_points": len(points),
                     **frozen.to_dict()}
        pool = {"record_id": record_id, "source_sha256": reference["source_sha256"],
                "objectives": points}
        reference_path = calibration / f"{record_id}.json"
        pool_path = pools / f"{record_id}.json"
        reference_path.write_text(json.dumps(reference))
        pool_path.write_text(json.dumps(pool))
        manifest["records"].append({"record_id": record_id, "status": "done",
                                    "n_calibration_points": len(points),
                                    "reference_sha256": file_sha256(reference_path),
                                    "pool_sha256": file_sha256(pool_path)})
    (calibration / "manifest.json").write_text(json.dumps(manifest))
    return fasta, rscu, calibration


def test_verify_frozen_assets_passes_complete_assets(tmp_path, monkeypatch):
    fasta, rscu, calibration = make_assets(tmp_path, monkeypatch)
    result = verifier.verify_frozen_assets(fasta, rscu, calibration, expected_n=2)
    assert result["passed"]
    assert all(row["reference_recomputed"] for row in result["records"])


def test_verify_frozen_assets_rejects_nonpositive_scale(tmp_path, monkeypatch):
    fasta, rscu, calibration = make_assets(tmp_path, monkeypatch)
    path = calibration / "g1.json"
    reference = json.loads(path.read_text())
    reference["scale"][0] = 0
    path.write_text(json.dumps(reference))
    manifest_path = calibration / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["records"][0]["reference_sha256"] = file_sha256(path)
    manifest_path.write_text(json.dumps(manifest))
    result = verifier.verify_frozen_assets(fasta, rscu, calibration, expected_n=2)
    assert not result["passed"]
    assert not result["records"][0]["scale_positive_finite"]


def test_verify_frozen_assets_rejects_pool_hash_mismatch(tmp_path, monkeypatch):
    fasta, rscu, calibration = make_assets(tmp_path, monkeypatch)
    pool_path = calibration / "pools" / "g2.json"
    pool = json.loads(pool_path.read_text())
    pool["objectives"][0][0] = 0.9
    pool_path.write_text(json.dumps(pool))
    result = verifier.verify_frozen_assets(fasta, rscu, calibration, expected_n=2)
    assert not result["passed"]
    assert not result["records"][1]["pool_sha256"]
