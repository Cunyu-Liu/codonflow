"""Recover release-frozen raw CDS sources with hashes and cleaning ledgers."""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import shutil
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.pipeline import clean_fasta
from codonflow.train.run_pretrain import file_sha256


def source_url(record, release):
    release = record.get("release", release)
    return (f"https://ftp.ensembl.org/pub/release-{release}/fasta/{record['species']}/cds/"
            f"{record['base']}.cds.all.fa.gz")


def validate_registry(payload):
    records = payload.get("records", [])
    if payload.get("release") != 112 or len(records) != 25:
        raise ValueError("A7 source recovery requires exactly 25 release-112 species")
    if len({row["species"] for row in records}) != 25 or len({row["base"] for row in records}) != 25:
        raise ValueError("duplicate species or assembly in source registry")
    return records


def atomic_json(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2))
    temporary.replace(path)


def recover_one(record, release, out_dir, url_override=None):
    species = record["species"]
    target = Path(out_dir) / species
    target.mkdir(parents=True, exist_ok=True)
    url = url_override or source_url(record, release)
    gz_path = target / f"{record['base']}.cds.all.fa.gz"
    raw_path = target / f"{record['base']}.cds.all.fa"
    clean_path = target / "cleaned.fasta"
    metadata_path = target / "recovery.json"
    if metadata_path.exists():
        previous = json.loads(metadata_path.read_text())
        if (previous.get("status") == "done" and previous.get("url") == url
                and previous.get("raw_sha256") == file_sha256(raw_path)
                and previous.get("cleaned_sha256") == file_sha256(clean_path)):
            return previous
    if not gz_path.exists():
        temporary = gz_path.with_suffix(".gz.tmp")
        if temporary.exists():
            temporary.replace(gz_path.with_suffix(".truncated"))
        with urllib.request.urlopen(url, timeout=900) as response, temporary.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        temporary.replace(gz_path)
    with gz_path.open("rb") as handle:
        gzip_magic = handle.read(2)
    if gzip_magic != b"\x1f\x8b":
        raise ValueError(f"invalid gzip source: {url}")
    if not raw_path.exists():
        temporary = raw_path.with_suffix(".fa.tmp")
        with gzip.open(gz_path, "rb") as source, temporary.open("wb") as handle:
            shutil.copyfileobj(source, handle)
        temporary.replace(raw_path)
    temporary_clean = clean_path.with_suffix(".tmp")
    counts = clean_fasta(str(raw_path), str(temporary_clean))
    temporary_clean.replace(clean_path)
    result = {
        "status": "done",
        "species": species,
        "assembly": record["base"],
        "source": "Ensembl FTP",
        "release": record.get("release", release),
        "url": url,
        "recovered_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "recovery_note": "new recovery timestamp; original download timestamp is not claimed",
        "gzip_path": str(gz_path),
        "gzip_sha256": file_sha256(gz_path),
        "raw_path": str(raw_path),
        "raw_sha256": file_sha256(raw_path),
        "cleaned_path": str(clean_path),
        "cleaned_sha256": file_sha256(clean_path),
        "cleaning_counts": counts,
        "n_input": sum(counts.values()),
        "n_retained": counts.get("kept", 0),
    }
    if result["n_input"] < 1 or result["n_retained"] < 1:
        raise ValueError(f"empty recovered corpus: {species}")
    atomic_json(metadata_path, result)
    return result


def recover_safe(record, release, out_dir):
    try:
        return recover_one(record, release, out_dir)
    except Exception as error:
        return {"status": "failed", "species": record["species"],
                "url": source_url(record, release), "error": str(error)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--species", action="append")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    registry = json.loads(Path(args.registry).read_text())
    records = validate_registry(registry)
    if args.species:
        unknown = set(args.species) - {row["species"] for row in records}
        if unknown:
            raise ValueError(f"unknown species: {sorted(unknown)}")
        records = [row for row in records if row["species"] in args.species]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda row: recover_safe(row, registry["release"], args.out_dir), records))
    out = Path(args.out_dir) / "manifest.json"
    existing = {}
    if out.exists():
        existing = {row["species"]: row for row in json.loads(out.read_text()).get("records", [])}
    existing.update({row["species"]: row for row in rows})
    combined = list(existing.values())
    manifest = {"protocol": "a7_source_recovery_manifest_v1", "release": registry["release"],
                "n_requested": len(combined), "n_done": sum(row["status"] == "done" for row in combined),
                "records": combined}
    manifest["passed"] = len(combined) == 25 and manifest["n_done"] == 25
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(out, manifest)
    print(json.dumps({"out": str(out), "n_done": manifest["n_done"],
                      "n_requested": len(combined), "passed": manifest["passed"]}))


if __name__ == "__main__":
    main()
