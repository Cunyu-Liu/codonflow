"""Recover species metadata from frozen transcript identifier conventions."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.dataset import read_fasta
from codonflow.train.run_pretrain import file_sha256

ENSEMBL_PREFIX_SPECIES = {
    "ENST": "homo_sapiens",
    "ENSECAT": "equus_caballus",
    "ENSBTAT": "bos_taurus",
    "ENSTRUT": "takifugu_rubripes",
    "ENSXETT": "xenopus_tropicalis",
    "ENSMUST": "mus_musculus",
    "ENSPTRT": "pan_troglodytes",
    "ENSRNOT": "rattus_norvegicus",
    "ENSSSCT": "sus_scrofa",
    "ENSGALT": "gallus_gallus",
    "ENSDART": "danio_rerio",
    "ENSGGOT": "gorilla_gorilla",
    "ENSCAFT": "canis_lupus_familiaris",
    "ENSOCUT": "ovis_aries",
    "ENSORLT": "oryctolagus_cuniculus",
    "ENSACAT": "anolis_carolinensis",
    "ENSCPOT": "cavia_porcellus",
    "ENSOART": "oryzias_latipes",
    "ENSMMUT": "macaca_mulatta",
    "ENSCINT": "ciona_intestinalis",
    "ENSFCAT": "felis_catus",
    "ENSCSAVT": "ciona_savignyi",
}


def species_for_header(header):
    identifier = header.split()[0]
    if identifier.startswith("ENS"):
        prefix = identifier[:identifier.index("0")] if "0" in identifier else identifier
        if prefix not in ENSEMBL_PREFIX_SPECIES:
            raise ValueError(f"unmapped Ensembl identifier: {identifier}")
        return ENSEMBL_PREFIX_SPECIES[prefix]
    if identifier.startswith("FBtr"):
        return "drosophila_melanogaster"
    if identifier.endswith("_mRNA"):
        return "saccharomyces_cerevisiae"
    return "caenorhabditis_elegans"


def audit_species(fasta_paths, map_out=None):
    mapping = {}
    rows = []
    for fasta in fasta_paths:
        counts = Counter()
        for header, _sequence in read_fasta(fasta):
            species = species_for_header(header)
            mapping[header.split()[0]] = species
            counts[species] += 1
        rows.append({"fasta": str(fasta), "fasta_sha256": file_sha256(fasta),
                     "n": sum(counts.values()), "n_species": len(counts),
                     "species_counts": dict(sorted(counts.items()))})
    if map_out:
        Path(map_out).write_text(json.dumps(mapping))
    return {"protocol": "a7_species_identifier_recovery_v1",
            "mapping_rule": "22 Ensembl prefixes + FlyBase + WormBase + S. cerevisiae _mRNA",
            "n_records": sum(row["n"] for row in rows), "passed": True, "records": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fasta", nargs="+", required=True)
    parser.add_argument("--map-out")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = audit_species(args.fasta, args.map_out)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({"out": str(out), "n_records": result["n_records"],
                      "n_species_per_fasta": [row["n_species"] for row in result["records"]]}))


if __name__ == "__main__":
    main()
