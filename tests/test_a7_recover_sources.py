import gzip
import io
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
    partial = out_dir / "test_species" / "Test.1.cds.all.fa.gz.tmp"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"truncated")
    result = recover_one(record, 112, out_dir, url_override=source.as_uri())
    assert (out_dir / "test_species" / "Test.1.cds.all.fa.truncated").read_bytes() == b"truncated"
    assert result["status"] == "done"
    assert result["n_input"] == 2 and result["n_retained"] == 1
    assert result["cleaning_counts"] == {"too_short": 1, "kept": 1}
    assert result["url"] == source.as_uri()
    assert len(result["raw_sha256"]) == 64 and len(result["cleaned_sha256"]) == 64
    resumed = recover_one(record, 112, out_dir, url_override=source.as_uri())
    assert resumed["recovered_at_utc"] == result["recovered_at_utc"]


def test_corrupt_gzip_is_quarantined_and_redownloaded(tmp_path):
    record = {"species": "test_species", "base": "Test.1"}
    source = tmp_path / "source.gz"
    long_cds = "ATG" + "A" * 297 + "TAA"
    with gzip.open(source, "wt") as handle:
        handle.write(f">keep\n{long_cds}\n")
    out_dir = tmp_path / "out"
    target = out_dir / "test_species"
    target.mkdir(parents=True)
    corrupt = target / "Test.1.cds.all.fa.gz"
    corrupt.write_bytes(b"\x1f\x8b truncated")
    result = recover_one(record, 112, out_dir, url_override=source.as_uri())
    assert result["status"] == "done"
    assert (target / "Test.1.cds.all.fa.corrupt").read_bytes() == b"\x1f\x8b truncated"


def test_range_resume_preserves_valid_partial_download(tmp_path, monkeypatch):
    record = {"species": "test_species", "base": "Test.1"}
    source = tmp_path / "source.gz"
    long_cds = "ATG" + "A" * 297 + "TAA"
    with gzip.open(source, "wt") as handle:
        handle.write(f">keep\n{long_cds}\n")
    compressed = source.read_bytes()
    offset = 100
    response = io.BytesIO(compressed[offset:])
    response.status = 206
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: response)
    out_dir = tmp_path / "out"
    partial = out_dir / "test_species" / "Test.1.cds.all.fa.gz.tmp"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(compressed[:offset])
    result = recover_one(record, 112, out_dir, url_override="https://example.invalid/source.gz")
    assert result["status"] == "done"
    assert (out_dir / "test_species" / "Test.1.cds.all.fa.gz").read_bytes() == compressed
