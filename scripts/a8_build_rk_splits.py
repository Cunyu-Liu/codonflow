#!/usr/bin/env python3
"""Build leakage-controlled A8-RK functional splits without using labels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from scripts.a8_rk_functional_data import (
    LONG_FIELDS,
    DataValidationError,
    sha256_file,
    translate_dna,
    write_csv_atomic,
)

SPLIT_FIELDS = LONG_FIELDS + [
    "operational_protein_cluster",
    "construct_signature_group",
    "split_protocol_id",
    "split_leakage_note",
]
SPLITS = ("train", "dev", "test")
UNTOUCHED = "functional_untouched"
PROTOCOL_ID = "a8_rk_split_v1_mmseqs2_id050_cov080_seed20261118"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_long_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != LONG_FIELDS:
            raise DataValidationError("unexpected functional_long schema")
        rows = [dict(row) for row in reader]
    if not rows:
        raise DataValidationError("functional_long is empty")
    return rows


def derive_infa_reference(rows: Sequence[Mapping[str, str]]) -> Tuple[str, str]:
    """Reconstruct infA WT CDS from S1 WT controls; remove terminal stop from protein."""
    wt: Dict[int, str] = {}
    for row in rows:
        if not (
            row["source_id"] == "kelsic_2016_mage_seq"
            and row["dataset_id"] == "data_s1_single_codon_csv"
            and row["record_class"] == "wild_type_control"
            and row["expression_type"] == "relative_fitness_rich"
        ):
            continue
        position = int(row["codon_position"])
        codon = row["mutant_codon"].strip().upper()
        if position in wt and wt[position] != codon:
            raise DataValidationError(f"conflicting infA WT codon at position {position}")
        wt[position] = codon
    if not wt or set(wt) != set(range(1, max(wt) + 1)):
        raise DataValidationError("infA WT positions are incomplete")
    cds = "".join(wt[position] for position in range(1, max(wt) + 1))
    protein_with_stop = translate_dna(cds)
    if not protein_with_stop.endswith("*") or "*" in protein_with_stop[:-1]:
        raise DataValidationError("derived infA CDS does not have exactly one terminal stop")
    if len(cds) % 3 or not cds.startswith("ATG"):
        raise DataValidationError("derived infA CDS is not a complete ATG-start CDS")
    return cds, protein_with_stop[:-1]


def protein_inputs(rows: Sequence[Mapping[str, str]]) -> Tuple[Dict[str, str], str, str]:
    proteins: Dict[str, str] = {}
    for row in rows:
        if row["source_id"] != "boel_2016_nesg6348":
            continue
        identifier = f"boel__{row['protein_id']}"
        sequence = row["protein_sequence"].strip().upper()
        if not sequence or "*" in sequence:
            raise DataValidationError(f"invalid Boël protein: {row['protein_id']}")
        if identifier in proteins and proteins[identifier] != sequence:
            raise DataValidationError(f"conflicting protein sequence: {identifier}")
        proteins[identifier] = sequence
    infa_cds, infa_protein = derive_infa_reference(rows)
    proteins["mage__infA"] = infa_protein
    return proteins, infa_cds, infa_protein


def write_fasta(path: Path, proteins: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as handle:
        for identifier in sorted(proteins):
            handle.write(f">{identifier}\n{proteins[identifier]}\n")
    os.replace(temporary, path)


def run_mmseqs(
    mmseqs: Path, fasta: Path, output_dir: Path, threads: int, tmp_dir: Optional[Path] = None
) -> Tuple[Path, str, List[str]]:
    prefix = output_dir / "protein_clusters"
    cluster_tsv = prefix.with_name(prefix.name + "_cluster.tsv")
    mmseqs_tmp = tmp_dir if tmp_dir is not None else output_dir / "mmseqs_tmp"
    mmseqs_tmp.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(mmseqs), "easy-cluster", str(fasta), str(prefix), str(mmseqs_tmp),
        "--min-seq-id", "0.5", "-c", "0.8", "--cov-mode", "0", "--threads", str(threads),
    ]
    version = subprocess.check_output([str(mmseqs), "version"], text=True).strip()
    completed = subprocess.run(command, text=True, capture_output=True)
    (output_dir / "mmseqs_stdout.log").write_text(completed.stdout, encoding="utf-8")
    (output_dir / "mmseqs_stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode or not cluster_tsv.is_file():
        raise DataValidationError(f"MMseqs2 easy-cluster failed with exit code {completed.returncode}")
    return cluster_tsv, version, command


def read_clusters(path: Path, expected_ids: Iterable[str]) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    member_to_rep: Dict[str, str] = {}
    rep_to_members: Dict[str, List[str]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_number, line in enumerate(handle, start=1):
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 2 or not all(fields):
                raise DataValidationError(f"invalid cluster TSV line {line_number}")
            rep, member = fields
            if member in member_to_rep:
                raise DataValidationError(f"duplicate cluster member: {member}")
            member_to_rep[member] = rep
            rep_to_members[rep].append(member)
    expected = set(expected_ids)
    if set(member_to_rep) != expected:
        missing = sorted(expected - set(member_to_rep))
        extra = sorted(set(member_to_rep) - expected)
        raise DataValidationError(f"cluster coverage mismatch: missing={missing[:3]}, extra={extra[:3]}")
    if set(rep_to_members) - expected:
        raise DataValidationError("cluster representative is absent from input FASTA")
    return member_to_rep, dict(rep_to_members)


def row_sequence_id(row: Mapping[str, str]) -> str:
    if row["source_id"] == "boel_2016_nesg6348":
        return f"boel__{row['protein_id']}"
    if row["source_id"] == "kelsic_2016_mage_seq" and row["protein_id"] == "infA":
        return "mage__infA"
    raise DataValidationError(f"unsupported source/protein: {row['source_id']}/{row['protein_id']}")


def sequence_row_counts(rows: Sequence[Mapping[str, str]]) -> Counter:
    return Counter(row_sequence_id(row) for row in rows)


def allocate_clusters(
    rep_to_members: Mapping[str, Sequence[str]],
    counts: Mapping[str, int],
    held_out_reps: Iterable[str],
    seed: int,
    fractions: Mapping[str, float] = {"train": 0.8, "dev": 0.1, "test": 0.1},
) -> Dict[str, str]:
    """Greedy deterministic size balancing; labels and measurements are not inputs."""
    held = set(held_out_reps)
    assignments = {rep: UNTOUCHED for rep in held}
    eligible = [rep for rep in rep_to_members if rep not in held]
    sizes = {rep: sum(counts[member] for member in rep_to_members[rep]) for rep in eligible}
    total = sum(sizes.values())
    if total <= 0 or any(fractions[name] <= 0 for name in SPLITS):
        raise DataValidationError("no eligible rows or invalid split fractions")
    targets = {name: total * fractions[name] for name in SPLITS}
    used = {name: 0 for name in SPLITS}

    def tie(rep: str, split: str = "") -> str:
        return hashlib.sha256(f"{seed}|{rep}|{split}".encode("utf-8")).hexdigest()

    for rep in sorted(eligible, key=lambda item: (-sizes[item], tie(item))):
        split = min(
            SPLITS,
            key=lambda name: ((used[name] + sizes[rep]) / targets[name], tie(rep, name)),
        )
        assignments[rep] = split
        used[split] += sizes[rep]
    if set(assignments) != set(rep_to_members):
        raise DataValidationError("not every cluster received a split")
    return assignments


def construct_signature_group(row: Mapping[str, str]) -> str:
    signature = row["mutation_signature"].strip()
    if signature:
        return f"{row['source_id']}|{row['protein_id']}|{signature}"
    return f"{row['source_id']}|{row['construct_id']}"


def build_split_rows(
    rows: Sequence[Mapping[str, str]],
    member_to_rep: Mapping[str, str],
    rep_assignments: Mapping[str, str],
) -> List[Dict[str, object]]:
    output: List[Dict[str, object]] = []
    for source in rows:
        row: Dict[str, object] = dict(source)
        rep = member_to_rep[row_sequence_id(source)]
        assignment = rep_assignments[rep]
        row.update({
            "split_unit": "mmseqs2_operational_protein_cluster",
            "split_assignment": assignment,
            "operational_protein_cluster": rep,
            "construct_signature_group": construct_signature_group(source),
            "split_protocol_id": PROTOCOL_ID,
            "split_leakage_note": (
                "Operational homology cluster, not curated family; all infA and its cluster are frozen untouched; "
                "Boël is cross-protein nonsynonymous expression, not a fixed-protein synonymous library"
            ),
        })
        output.append(row)
    return output


def overlap_audit(rows: Sequence[Mapping[str, str]]) -> Dict[str, object]:
    partitions = sorted({row["split_assignment"] for row in rows})
    key_functions = {
        "exact_cds": lambda row: row["cds"],
        "exact_protein_or_derived_infa": lambda row: (
            row["protein_sequence"] if row["source_id"] == "boel_2016_nesg6348" else "DERIVED_INFA_WT"
        ),
        "source_protein_id": lambda row: f"{row['source_id']}|{row['protein_id']}",
        "operational_cluster": lambda row: row["operational_protein_cluster"],
        "construct_signature_group": lambda row: row["construct_signature_group"],
        "nonblank_mutation_signature": lambda row: (
            f"{row['source_id']}|{row['protein_id']}|{row['mutation_signature']}"
            if row["mutation_signature"] else ""
        ),
    }
    overlaps: Dict[str, object] = {}
    for name, key_function in key_functions.items():
        by_split = {
            split: {key_function(row) for row in rows if row["split_assignment"] == split and key_function(row)}
            for split in partitions
        }
        pair_counts = {}
        for index, left in enumerate(partitions):
            for right in partitions[index + 1:]:
                pair_counts[f"{left}__{right}"] = len(by_split[left] & by_split[right])
        overlaps[name] = pair_counts
    return {
        "pairwise_overlaps": overlaps,
        "all_pairwise_overlaps_zero": all(
            count == 0 for pairs in overlaps.values() for count in pairs.values()
        ),
    }


def summarize_counts(rows: Sequence[Mapping[str, str]]) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for split in sorted({row["split_assignment"] for row in rows}):
        subset = [row for row in rows if row["split_assignment"] == split]
        result[split] = {
            "rows": len(subset),
            "clusters": len({row["operational_protein_cluster"] for row in subset}),
            "sources": dict(sorted(Counter(row["source_id"] for row in subset).items())),
            "datasets": dict(sorted(Counter(row["dataset_id"] for row in subset).items())),
            "expression_types": dict(sorted(Counter(row["expression_type"] for row in subset).items())),
            "variant_classes": dict(sorted(Counter(row["variant_class"] for row in subset).items())),
            "unique_construct_signature_groups": len({row["construct_signature_group"] for row in subset}),
        }
    return result


def artifact(path: Path) -> Dict[str, object]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def build_splits(args: argparse.Namespace) -> Dict[str, object]:
    rows = read_long_rows(args.input)
    if args.expected_input_sha256 and sha256_file(args.input) != args.expected_input_sha256:
        raise DataValidationError("input SHA256 does not match frozen RK-02 artifact")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    args.audit_dir.mkdir(parents=True, exist_ok=True)
    proteins, infa_cds, infa_protein = protein_inputs(rows)
    fasta = args.output_dir / "proteins.fasta"
    write_fasta(fasta, proteins)
    cluster_tsv, mmseqs_version, command = run_mmseqs(
        args.mmseqs, fasta, args.output_dir, args.threads, args.tmp_dir
    )
    member_to_rep, rep_to_members = read_clusters(cluster_tsv, proteins)
    counts = sequence_row_counts(rows)
    infa_rep = member_to_rep["mage__infA"]
    assignments = allocate_clusters(rep_to_members, counts, {infa_rep}, args.seed)
    split_rows = build_split_rows(rows, member_to_rep, assignments)
    split_csv = args.output_dir / "functional_long_split.csv"
    write_csv_atomic(split_csv, split_rows, SPLIT_FIELDS)

    assignment_rows = []
    for identifier in sorted(proteins):
        rep = member_to_rep[identifier]
        assignment_rows.append({
            "sequence_id": identifier,
            "operational_protein_cluster": rep,
            "split_assignment": assignments[rep],
            "protein_sha256": hashlib.sha256(proteins[identifier].encode("utf-8")).hexdigest(),
            "assay_rows": counts[identifier],
            "is_infa_reference": identifier == "mage__infA",
        })
    assignments_csv = args.output_dir / "split_assignments.csv"
    write_csv_atomic(
        assignments_csv, assignment_rows,
        ["sequence_id", "operational_protein_cluster", "split_assignment", "protein_sha256", "assay_rows", "is_infa_reference"],
    )
    leakage = overlap_audit(split_rows)
    if not leakage["all_pairwise_overlaps_zero"]:
        raise DataValidationError("split leakage audit failed")
    if any(row["source_id"] == "kelsic_2016_mage_seq" and row["split_assignment"] != UNTOUCHED for row in split_rows):
        raise DataValidationError("MAGE escaped functional_untouched")
    held_boel = sum(row["source_id"] == "boel_2016_nesg6348" and row["split_assignment"] == UNTOUCHED for row in split_rows)
    summary = {
        "schema_version": "a8-rk-functional-split-v1",
        "created_at": utc_now(),
        "status": "PASS_WITH_SCIENTIFIC_BOUNDARIES",
        "input": artifact(args.input),
        "input_rows": len(rows),
        "protocol": {
            "protocol_id": PROTOCOL_ID,
            "seed": args.seed,
            "mmseqs_version": mmseqs_version,
            "mmseqs_binary": artifact(args.mmseqs),
            "command": command,
            "temporary_directory": str(args.tmp_dir if args.tmp_dir is not None else args.output_dir / "mmseqs_tmp"),
            "identity": 0.5,
            "bidirectional_coverage": 0.8,
            "coverage_mode": 0,
            "allocation": "deterministic cluster-size balancing; no expression labels or model results used",
            "cluster_scope": "operational MMseqs2 homology clusters, not curated protein families",
        },
        "infa_reference": {
            "source": "73 S1 WT controls; positions 1..73; position 73 is terminal stop",
            "cds_nt": len(infa_cds),
            "protein_aa": len(infa_protein),
            "cds_sha256": hashlib.sha256(infa_cds.encode("utf-8")).hexdigest(),
            "protein_sha256": hashlib.sha256(infa_protein.encode("utf-8")).hexdigest(),
            "operational_cluster": infa_rep,
        },
        "counts": summarize_counts(split_rows),
        "boel_rows_frozen_with_infa_cluster": held_boel,
        "leakage": leakage,
        "artifacts": {
            "functional_long_split": artifact(split_csv),
            "protein_fasta": artifact(fasta),
            "cluster_tsv": artifact(cluster_tsv),
            "split_assignments": artifact(assignments_csv),
        },
        "training_ready": False,
        "training_or_model_selection_performed": False,
        "functional_untouched_evaluated": False,
        "scientific_boundaries": [
            "Boël supports cross-protein heterologous expression modeling, not fixed-protein synonymous-function prediction.",
            "All MAGE infA rows and every Boël member of the infA cluster are frozen before model training.",
            "No multi-protein synonymous functional training corpus is currently available; no RK-G0/G1 or SOTA claim is authorized.",
            "Split creation does not close RK-03/RK-05/RK-06 and does not authorize generator training.",
        ],
    }
    summary_path = args.audit_dir / "split_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-input-sha256")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tmp-dir", type=Path, help="MMseqs2 temporary directory; use a symlink-capable local filesystem")
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--mmseqs", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20261118)
    args = parser.parse_args(argv)
    summary = build_splits(args)
    print(json.dumps({
        "status": summary["status"],
        "input_rows": summary["input_rows"],
        "counts": {name: value["rows"] for name, value in summary["counts"].items()},
        "boel_rows_frozen_with_infa_cluster": summary["boel_rows_frozen_with_infa_cluster"],
        "all_pairwise_overlaps_zero": summary["leakage"]["all_pairwise_overlaps_zero"],
        "training_ready": summary["training_ready"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
