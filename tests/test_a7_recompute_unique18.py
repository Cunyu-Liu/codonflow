import hashlib
import json

from codonflow.core.codon import CODONS
from codonflow.core.motifs import motif_penalty_score
from codonflow.eval.metrics import cai, cai_weights_from_rscu, pairwise_ned
from scripts.a7_recompute_unique18 import recompute_payload, recompute_unique18


SOURCE = "ATGGCTTAA"
SOLUTIONS = ["ATGGCTTAA", "ATGGCCTAA"]
MFES = [-10.0, -20.0]
WEIGHTS = cai_weights_from_rscu({codon: 1.0 for codon in CODONS})


def method_payload():
    objectives = [[cai(sequence, WEIGHTS), -mfe,
                   -abs((sequence.count("G") + sequence.count("C")) / len(sequence) - 0.55),
                   -motif_penalty_score(sequence)]
                  for sequence, mfe in zip(SOLUTIONS, MFES)]
    return {"status": "done", "solutions": SOLUTIONS, "obj_vectors": objectives,
            "ned": pairwise_ned(SOLUTIONS), "n_solutions": len(SOLUTIONS),
            "n_unique": len(set(SOLUTIONS)), "identity_rate": 1.0}


def payload():
    return {"record_id": "gene", "seed": 0, "status": "done",
            "source_sha256": hashlib.sha256(SOURCE.encode()).hexdigest(),
            "gc_target": 0.55, "methods": {name: method_payload() for name in
            ("lineardesign_scan", "codongpt", "gemorna", "cai_greedy", "uniform_synonymous")}}


def test_recompute_matches_all_objectives_and_ned():
    result = recompute_payload(payload(), SOURCE, WEIGHTS, fold=lambda sequences: MFES)
    assert result["matches"]
    assert all(row["recomputed"] for row in result["methods"].values())
    assert result["methods"]["cai_greedy"]["recomputed_mfes"] == MFES


def test_recompute_rejects_stale_mfe_ned_and_source():
    stale = payload()
    stale["methods"]["gemorna"]["obj_vectors"][0][1] += 1.0
    stale["methods"]["codongpt"]["ned"] += 0.1
    stale["source_sha256"] = "0" * 64
    result = recompute_payload(stale, SOURCE, WEIGHTS, fold=lambda sequences: MFES)
    assert not result["matches"]
    assert not result["methods"]["gemorna"]["matches"]
    assert not result["methods"]["codongpt"]["matches"]
    assert not result["source_sha256_matches"]


def test_recompute_rejects_misaligned_and_duplicate_solutions():
    broken = payload()
    broken["methods"]["gemorna"]["obj_vectors"] = broken["methods"]["gemorna"]["obj_vectors"][:-1]
    broken["methods"]["codongpt"]["solutions"] = [SOLUTIONS[0], SOLUTIONS[0]]
    result = recompute_payload(broken, SOURCE, WEIGHTS, fold=lambda sequences: MFES)
    assert not result["methods"]["gemorna"]["recomputed"]
    assert not result["methods"]["codongpt"]["recomputed"]
    assert not result["matches"]


def test_directory_audit_requires_every_requested_seed(tmp_path):
    fasta = tmp_path / "unique.fasta"
    fasta.write_text(">gene\nATGGCTTAA\n")
    rscu = tmp_path / "rscu.json"
    rscu.write_text(json.dumps({codon: 1.0 for codon in CODONS}))
    input_dir = tmp_path / "results"
    input_dir.mkdir()
    item = payload()
    item["benchmark_sha256"] = hashlib.sha256(fasta.read_bytes()).hexdigest()
    item["rscu_sha256"] = hashlib.sha256(rscu.read_bytes()).hexdigest()
    (input_dir / "gene_s0.json").write_text(json.dumps(item))
    result = recompute_unique18(input_dir, fasta, rscu, seeds=(0, 1), fold=lambda sequences: MFES)
    assert len(result["records"]) == 2
    assert result["records"][1]["status"] == "missing"
    assert not result["mfe_ned_independently_recomputed"]
    shard = recompute_unique18(input_dir, fasta, rscu, seeds=(0,), fold=lambda sequences: MFES,
                               record_ids=["gene"])
    assert shard["n_records"] == 1
    assert len(shard["records"]) == 1
    assert shard["mfe_ned_independently_recomputed"]
