"""A7 data-quality, distribution, metadata and cleaning-manifest audits."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import (
    CODONS,
    STANDARD_TABLE_1,
    has_unique_terminal_stop,
    is_valid_cds,
    normalize_to_dna,
    protein_of_cds,
)
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import cai
from scripts.audit_distribution import histogram, summarize_lengths


def _rscu_from_counts(counts):
    result = {}
    for codon, aa in STANDARD_TABLE_1.items():
        if aa == "*":
            continue
        group = [c for c in CODONS if STANDARD_TABLE_1[c] == aa]
        total = sum(counts[c] for c in group)
        result[codon] = counts[codon] * len(group) / total if total else 0.0
    return result


def validate_cleaning_manifest(payload):
    input_n = int(payload["n_input"])
    retained_n = int(payload["n_retained"])
    removed = payload.get("removed", {})
    if input_n < 0 or retained_n < 0 or not isinstance(removed, dict):
        raise ValueError("invalid cleaning counts")
    if any(int(value) < 0 for value in removed.values()):
        raise ValueError("negative cleaning removal count")
    if retained_n + sum(int(value) for value in removed.values()) != input_n:
        raise ValueError("cleaning counts do not conserve input records")
    if "fasta_n" in payload and int(payload["fasta_n"]) != retained_n:
        raise ValueError("retained count does not match FASTA")
    return True


def audit_records(records, cai_weights=None, species_map=None, cluster_map=None,
                  min_length=300, max_length=6000):
    ids, cds_values, proteins = set(), set(), set()
    lengths, gcs, cais = [], [], []
    invalid = Counter()
    species = Counter()
    clusters = Counter()
    codon_counts = Counter({codon: 0 for codon in CODONS})
    n = 0
    n_valid = 0
    n_operator_legal = 0
    n_atg_start = 0
    for header, sequence in records:
        n += 1
        ids.add(header)
        sequence = normalize_to_dna(sequence)
        cds_values.add(sequence)
        lengths.append(len(sequence))
        gcs.append((sequence.count("G") + sequence.count("C")) / len(sequence) if sequence else 0.0)
        reasons = []
        if not sequence or any(base not in "ACGT" for base in sequence):
            reasons.append("alphabet")
        if len(sequence) % 3:
            reasons.append("frame")
        if not min_length <= len(sequence) <= max_length:
            reasons.append("length")
        if sequence.startswith("ATG"):
            n_atg_start += 1
        else:
            reasons.append("start")
        if not has_unique_terminal_stop(sequence):
            reasons.append("terminal_or_internal_stop")
        for reason in reasons:
            invalid[reason] += 1
        if not reasons:
            n_valid += 1
        if is_valid_cds(sequence):
            n_operator_legal += 1
            proteins.add(protein_of_cds(sequence))
            if cai_weights is not None:
                cais.append(cai(sequence, cai_weights))
        for index in range(0, len(sequence) - len(sequence) % 3, 3):
            codon = sequence[index:index + 3]
            if codon in codon_counts:
                codon_counts[codon] += 1
        if species_map is not None:
            species[species_map.get(header, species_map.get(header.split()[0], "unmapped"))] += 1
        if cluster_map is not None:
            clusters[cluster_map.get(header, cluster_map.get(header.split()[0], "unmapped"))] += 1
    length_edges = [0] + list(range(300, 6001, 300))
    gc_edges = [index / 50 for index in range(51)]
    return {
        "n": n,
        "n_unique_ids": len(ids),
        "n_unique_cds": len(cds_values),
        "n_unique_proteins": len(proteins),
        "n_duplicate_cds_inputs": n - len(cds_values),
        "n_valid_cds": n_valid,
        "n_operator_legal": n_operator_legal,
        "n_atg_start": n_atg_start,
        "validity_definitions": {
            "n_operator_legal": "valid alphabet + frame + unique terminal stop; ATG and length range are not required",
            "n_valid_cds": "operator legal + ATG start + configured length range",
        },
        "invalid_reason_counts": dict(sorted(invalid.items())),
        "length_nt": summarize_lengths(lengths),
        "gc": summarize_lengths(gcs),
        "cai": summarize_lengths(cais) if cai_weights is not None else None,
        "histograms": {
            "length_nt": histogram(lengths, length_edges) if lengths else None,
            "gc": histogram(gcs, gc_edges) if gcs else None,
        },
        "rscu": _rscu_from_counts(codon_counts),
        "metadata": {
            "species_counts": dict(species),
            "n_species_mapped": n - species.get("unmapped", 0) if species_map is not None else 0,
            "cluster_counts": dict(clusters),
            "n_clusters": len(set(clusters) - {"unmapped"}) if cluster_map is not None else None,
        },
    }


def audit_fasta(path, **kwargs):
    return audit_records(read_fasta(path), **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--rscu-json")
    parser.add_argument("--species-map-json")
    parser.add_argument("--cluster-map-json")
    parser.add_argument("--cleaning-manifest")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    cai_weights = None
    if args.rscu_json:
        from codonflow.eval.metrics import cai_weights_from_rscu
        cai_weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    species_map = json.loads(Path(args.species_map_json).read_text()) if args.species_map_json else None
    cluster_map = json.loads(Path(args.cluster_map_json).read_text()) if args.cluster_map_json else None
    result = audit_fasta(args.fasta, cai_weights=cai_weights,
                         species_map=species_map, cluster_map=cluster_map)
    result["fasta_sha256"] = hashlib.sha256(Path(args.fasta).read_bytes()).hexdigest()
    if args.cleaning_manifest:
        cleaning = json.loads(Path(args.cleaning_manifest).read_text())
        cleaning["fasta_n"] = result["n"]
        validate_cleaning_manifest(cleaning)
        result["cleaning_manifest"] = cleaning
        result["cleaning_manifest_sha256"] = hashlib.sha256(
            Path(args.cleaning_manifest).read_bytes()).hexdigest()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({"out": str(out), "n": result["n"],
                      "n_valid_cds": result["n_valid_cds"]}))


if __name__ == "__main__":
    main()
