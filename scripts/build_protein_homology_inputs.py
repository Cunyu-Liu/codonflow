"""Build unique-protein FASTA including benchmark seeds for homology clustering."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_splits import file_sha256
from scripts.gemorna_arm import cds_protein, read_fasta_records


def build_protein_fasta(cds_paths, benchmark_paths, out_fasta, out_manifest):
    representatives = {}
    seen_ids = set()
    source_hashes = {}
    for role, paths in (("corpus", cds_paths), ("benchmark", benchmark_paths)):
        for path in paths:
            source_hashes[str(Path(path).resolve())] = file_sha256(path)
            for header, sequence in read_fasta_records(path):
                sequence = sequence.upper().replace("U", "T")
                protein = cds_protein(sequence)
                if protein is None:
                    raise ValueError(f"invalid CDS in {path}: {header}")
                if protein not in representatives:
                    identifier = header.split()[0] if role == "corpus" else f"benchmark__{header.split()[0]}"
                    if identifier in seen_ids:
                        raise ValueError(f"duplicate protein identifier: {identifier}")
                    seen_ids.add(identifier)
                    representatives[protein] = {
                        "id": identifier, "role": role,
                        "cds_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
                        "protein_sha256": hashlib.sha256(protein.encode()).hexdigest(),
                    }
    out = Path(out_fasta)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(
        f">{row['id']}\n{protein}\n" for protein, row in representatives.items()
    ))
    manifest = {
        "protocol": "unique_protein_with_benchmark_seeds_v1",
        "scope": "MMseqs2 homology clusters are not curated family annotations",
        "n_unique_proteins": len(representatives),
        "n_benchmark_seed_proteins": sum(row["role"] == "benchmark" for row in representatives.values()),
        "input_sha256": source_hashes,
        "protein_fasta": str(out.resolve()),
        "protein_fasta_sha256": file_sha256(out),
        "records": list(representatives.values()),
    }
    Path(out_manifest).parent.mkdir(parents=True, exist_ok=True)
    Path(out_manifest).write_text(json.dumps(manifest, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cds-fasta", nargs="+", required=True)
    parser.add_argument("--benchmark-fasta", nargs="+", required=True)
    parser.add_argument("--out-fasta", required=True)
    parser.add_argument("--out-manifest", required=True)
    args = parser.parse_args()
    manifest = build_protein_fasta(
        args.cds_fasta, args.benchmark_fasta, args.out_fasta, args.out_manifest,
    )
    print(json.dumps({key: value for key, value in manifest.items() if key != "records"}, indent=2))


if __name__ == "__main__":
    main()
