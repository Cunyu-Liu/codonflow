#!/usr/bin/env python3
"""Download only the 56 HeLa R1 Flow-seq files with the verified range engine.

No FASTQ sequence or functional outcome is parsed by this program. Complete-file
size/MD5 gates and atomic renames are inherited from the frozen RK02 engine.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import a8_rk02_download_mordstein_ranges as engine

EXPECTED_ENGINE_SHA256 = "9011052e4518cb5b6f49f108c6062271ebe664e75d1b4cd8631759bc406dfedd"
TITLES = {
    "Illumina MiSeq sequencing: Flow-Seq of GFP library without intron in HeLa cells",
    "Illumina MiSeq sequencing: Flow-Seq of GFP library with intron in HeLa cells",
}


def jobs_from_metadata(metadata: Path, root: Path, only: list[str]) -> list[dict]:
    tokens = set(only)
    jobs = []
    with metadata.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["experiment_title"] not in TITLES:
                continue
            run = row["run_accession"]
            token = f"{run}_1"
            if tokens and run not in tokens and token not in tokens:
                continue
            jobs.append({
                "run": run,
                "mate": 1,
                "token": token,
                "url": "https://" + row["fastq_ftp"].split(";")[0],
                "expected_md5": row["fastq_md5"].split(";")[0],
                "expected_bytes": int(row["fastq_bytes"].split(";")[0]),
                "path": root / run / f"{token}.fastq.gz",
                "experiment_accession": row["experiment_accession"],
                "experiment_title": row["experiment_title"],
                "library_name": row["library_name"],
            })
    if not jobs:
        raise ValueError("no HeLa R1 jobs selected")
    for job in jobs:
        path = job["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + ".part")
        if not path.exists() and not part.exists():
            part.touch()
    return sorted(jobs, key=lambda job: job["run"])


def main() -> None:
    actual = hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest()
    if actual != EXPECTED_ENGINE_SHA256:
        raise RuntimeError(f"Unexpected range-download engine: {actual}")
    engine.jobs_from_metadata = jobs_from_metadata
    original_atomic_json = engine.atomic_json

    def atomic_json(path, value):
        value["schema"] = "a8.rk30.mordstein_hela_r1_download.v1"
        value["context_titles"] = sorted(TITLES)
        value["mate"] = 1
        value["fastq_sequence_or_outcome_parsed"] = False
        original_atomic_json(path, value)

    engine.atomic_json = atomic_json
    engine.main()


if __name__ == "__main__":
    main()
