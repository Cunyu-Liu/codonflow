import gzip
import json
from pathlib import Path

from scripts.a7_recover_sources import recover_one, source_url, validate_registry


def test_registry_has_25_unique_release112_species():
    path = Path(__file__).parents[1] / "configs" / "a7_source_recovery.json"
    payload = json.loads(path.read_text())
    records = validate_registry(payload)
    assert len(records) == 25
    assert len({row["species"] for row in records}) == 25
    assert all(source_url(row, payload["release"]).startswith(
        f"https://ftp.ensembl.org/pub/release-{row.get('release', payload['release'])}/fasta/")
        for row in records)


def test_recover_one_records_hashes_and_cleaning_counts(tmp_path):
    record = {"species": "test_species", "base": "Test.1"}
    source = tmp_path / "source.gz"
    long_cds = "ATG" + "A" * 297 + "TAA"
    with gzip.open(source, "wt") as handle:
        handle.write(f">keep\n{long_cds}\n>short\nATGTAA\n")
    out_dir = tmp_path / "out"
    result = recover_one(record, 112, out_dir, url_override=source.as_uri())
    assert result["status"] == "done"
    assert result["n_input"] == 2 and result["n_retained"] == 1
    assert result["cleaning_counts"] == {"too_short": 1, "kept": 1}
    assert result["url"] == source.as_uri()
    assert len(result["raw_sha256"]) == 64 and len(result["cleaned_sha256"]) == 64
    resumed = recover_one(record, 112, out_dir, url_override=source.as_uri())
    assert resumed["recovered_at_utc"] == result["recovered_at_utc"]
