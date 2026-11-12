import json

from scripts.a7_run_unique18_shards import pending_records


def test_pending_records_skips_only_complete_genes(tmp_path):
    fasta = tmp_path / "unique.fasta"
    fasta.write_text(">g1\nATGTAA\n>g2\nATGTAA\n>g3\nATGTAA\n")
    output = tmp_path / "out"
    output.mkdir()
    (output / "g1_s1.json").write_text(json.dumps({"status": "done"}))
    (output / "g2_s1.json").write_text(json.dumps({"status": "running"}))
    assert pending_records(fasta, output, 1) == ["g2", "g3"]
