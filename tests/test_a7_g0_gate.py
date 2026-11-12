import json
from pathlib import Path

from scripts.a7_g0_gate import evaluate_g0


def make_g0_evidence(tmp_path):
    registry = json.loads((Path(__file__).parents[1] / "configs" / "a7_source_recovery.json").read_text())
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry))
    full = tmp_path / "full.json"
    full.write_text(json.dumps({"passed": True, "v3_all": {"passed": True},
                                "species_distribution": {"passed": True}}))
    frozen = tmp_path / "frozen.json"
    frozen.write_text(json.dumps({"passed": True, "checks": {"all": True}}))
    source_manifests = []
    for index, record in enumerate(registry["records"]):
        species_dir = tmp_path / record["species"]
        species_dir.mkdir()
        raw = species_dir / "raw.fa"
        clean = species_dir / "clean.fa"
        raw.write_text(">x\nATGTAA\n")
        clean.write_text(">x\nATGTAA\n")
        source_manifests.append({"status": "done", "species": record["species"],
                                 "release": record.get("release", 112), "n_input": 1,
                                 "n_retained": 1, "cleaning_counts": {"kept": 1},
                                 "raw_sha256": "a" * 64, "cleaned_sha256": "b" * 64,
                                 "raw_path": str(raw), "cleaned_path": str(clean)})
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps({"records": source_manifests}))
    unique_paths = []
    for seed in (0, 1, 2):
        path = tmp_path / f"unique{seed}.json"
        path.write_text(json.dumps({"seeds": [seed], "complete_all_requested_seeds": True,
                                    "mfe_ned_independently_recomputed": True, "n_records": 18,
                                    "records": [{"matches": True}] * 18}))
        unique_paths.append(path)
    cuda = tmp_path / "cuda.json"
    cuda.write_text(json.dumps({"passed": True, "device": "cuda", "matmul_synchronized": True}))
    return full, frozen, [source_path], unique_paths, cuda, registry_path


def test_g0_gate_passes_only_complete_evidence(tmp_path):
    full, frozen, sources, unique, cuda, registry = make_g0_evidence(tmp_path)
    result = evaluate_g0(full, frozen, sources, unique, cuda, registry)
    assert result["passed"]
    assert all(result["checks"].values())


def test_g0_gate_rejects_missing_seed_and_source(tmp_path):
    full, frozen, sources, unique, cuda, registry = make_g0_evidence(tmp_path)
    unique = unique[:-1]
    source_payload = json.loads(sources[0].read_text())
    source_payload["records"] = source_payload["records"][:-1]
    sources[0].write_text(json.dumps(source_payload))
    result = evaluate_g0(full, frozen, sources, unique, cuda, registry)
    assert not result["passed"]
    assert not result["checks"]["unique18_all_seeds"]
    assert not result["checks"]["source_recovery"]
