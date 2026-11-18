#!/usr/bin/env python3
"""Independently verify RK-04 split lineage, conservation and leakage checks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from scripts.a8_rk_functional_data import LONG_FIELDS, sha256_file, translate_dna


def read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def independent_infa(rows: Sequence[Mapping[str, str]]) -> Tuple[str, str]:
    controls = {}
    for row in rows:
        if (
            row["source_id"] == "kelsic_2016_mage_seq"
            and row["dataset_id"] == "data_s1_single_codon_csv"
            and row["record_class"] == "wild_type_control"
            and row["expression_type"] == "relative_fitness_rich"
        ):
            position = int(row["codon_position"])
            codon = row["mutant_codon"]
            assert position not in controls or controls[position] == codon
            controls[position] = codon
    assert set(controls) == set(range(1, 74))
    cds = "".join(controls[position] for position in range(1, 74))
    protein = translate_dna(cds)
    assert protein.endswith("*") and "*" not in protein[:-1]
    return cds, protein[:-1]


def read_fasta(path: Path) -> Dict[str, str]:
    records: Dict[str, str] = {}
    identifier = None
    chunks: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith(">"):
            if identifier is not None:
                assert identifier not in records
                records[identifier] = "".join(chunks)
            identifier = raw[1:]
            chunks = []
        else:
            assert identifier is not None and raw
            chunks.append(raw.strip())
    if identifier is not None:
        assert identifier not in records
        records[identifier] = "".join(chunks)
    return records


def verify(args: argparse.Namespace) -> Dict[str, object]:
    checks: List[Dict[str, object]] = []

    def check(name: str, condition: bool, detail: object = "") -> None:
        checks.append({"check": name, "status": "PASS" if condition else "FAIL", "detail": detail})

    summary = json.loads((args.audit_dir / "split_summary.json").read_text(encoding="utf-8"))
    input_fields, original = read_csv(args.input)
    split_path = Path(summary["artifacts"]["functional_long_split"]["path"])
    split_fields, split = read_csv(split_path)
    check("input_schema", input_fields == LONG_FIELDS, len(input_fields))
    check("row_conservation", len(original) == len(split) == summary["input_rows"], len(split))
    check("original_input_sha", sha256_file(args.input) == summary["input"]["sha256"])

    common_unchanged = [name for name in LONG_FIELDS if name not in {"split_unit", "split_assignment"}]
    mismatch_counts = {}
    for field in common_unchanged:
        mismatch_counts[field] = sum(before[field] != after[field] for before, after in zip(original, split))
    check("all_source_fields_unchanged", all(count == 0 for count in mismatch_counts.values()),
          {key: value for key, value in mismatch_counts.items() if value})
    check("no_unassigned_rows", all(row["split_assignment"] in {"train", "dev", "test", "functional_untouched"} for row in split))
    check("protocol_id_complete", all(row["split_protocol_id"] == summary["protocol"]["protocol_id"] for row in split))

    # Independent cluster reconstruction from the raw MMseqs2 TSV.
    cluster_path = Path(summary["artifacts"]["cluster_tsv"]["path"])
    member_to_rep: Dict[str, str] = {}
    rep_to_members: Dict[str, List[str]] = defaultdict(list)
    for line in cluster_path.read_text(encoding="utf-8").splitlines():
        rep, member = line.split("\t")
        assert member not in member_to_rep
        member_to_rep[member] = rep
        rep_to_members[rep].append(member)
    fasta = read_fasta(Path(summary["artifacts"]["protein_fasta"]["path"]))
    check("cluster_fasta_coverage", set(member_to_rep) == set(fasta), len(fasta))
    check("cluster_representatives_valid", set(rep_to_members) <= set(fasta), len(rep_to_members))

    expected_proteins = {f"boel__{row['protein_id']}": row["protein_sequence"] for row in original if row["source_id"] == "boel_2016_nesg6348"}
    infa_cds, infa_protein = independent_infa(original)
    expected_proteins["mage__infA"] = infa_protein
    check("protein_fasta_exact_recalculation", fasta == expected_proteins, len(expected_proteins))
    check("infa_reference_length_and_stop", len(infa_cds) == 219 and len(infa_protein) == 72,
          {"cds_nt": len(infa_cds), "protein_aa": len(infa_protein)})

    def sequence_id(row: Mapping[str, str]) -> str:
        return f"boel__{row['protein_id']}" if row["source_id"] == "boel_2016_nesg6348" else "mage__infA"

    row_cluster_mismatch = sum(row["operational_protein_cluster"] != member_to_rep[sequence_id(row)] for row in split)
    check("row_cluster_mapping", row_cluster_mismatch == 0, row_cluster_mismatch)
    infa_rep = member_to_rep["mage__infA"]
    check("infa_cluster_untouched", all(row["split_assignment"] == "functional_untouched" for row in split if row["operational_protein_cluster"] == infa_rep), infa_rep)
    check("all_mage_untouched", all(row["split_assignment"] == "functional_untouched" for row in split if row["source_id"] == "kelsic_2016_mage_seq"))
    check("no_mage_in_model_dev", not any(row["source_id"] == "kelsic_2016_mage_seq" and row["split_assignment"] != "functional_untouched" for row in split))
    check("functional_untouched_not_evaluated", summary["functional_untouched_evaluated"] is False)
    check("no_training_or_selection_claim", summary["training_or_model_selection_performed"] is False and summary["training_ready"] is False)

    partitions = sorted({row["split_assignment"] for row in split})
    overlap_results: Dict[str, object] = {}
    key_functions = {
        "exact_cds": lambda row: row["cds"],
        "exact_protein_or_derived_infa": lambda row: row["protein_sequence"] if row["source_id"] == "boel_2016_nesg6348" else infa_protein,
        "source_protein_id": lambda row: f"{row['source_id']}|{row['protein_id']}",
        "operational_cluster": lambda row: row["operational_protein_cluster"],
        "construct_signature_group": lambda row: row["construct_signature_group"],
        "nonblank_mutation_signature": lambda row: f"{row['source_id']}|{row['protein_id']}|{row['mutation_signature']}" if row["mutation_signature"] else "",
    }
    for name, function in key_functions.items():
        values = {partition: {function(row) for row in split if row["split_assignment"] == partition and function(row)} for partition in partitions}
        pairs = {}
        for index, left in enumerate(partitions):
            for right in partitions[index + 1:]:
                pairs[f"{left}__{right}"] = len(values[left] & values[right])
        overlap_results[name] = pairs
        check(f"zero_overlap_{name}", all(value == 0 for value in pairs.values()), pairs)

    # Split assignment table must agree with both the cluster map and the long table.
    _, assignment_rows = read_csv(Path(summary["artifacts"]["split_assignments"]["path"]))
    assignment_map = {row["sequence_id"]: row for row in assignment_rows}
    check("assignment_table_coverage", set(assignment_map) == set(fasta), len(assignment_map))
    check("assignment_table_clusters", all(row["operational_protein_cluster"] == member_to_rep[identifier] for identifier, row in assignment_map.items()))
    long_assignment = {sequence_id(row): row["split_assignment"] for row in split}
    check("assignment_table_splits", all(row["split_assignment"] == long_assignment[identifier] for identifier, row in assignment_map.items()))
    sequence_counts = Counter(sequence_id(item) for item in split)
    check("assignment_row_counts", all(int(row["assay_rows"]) == sequence_counts[identifier] for identifier, row in assignment_map.items()))

    # Recompute all summary counts directly from the split table.
    recomputed = {}
    for partition in partitions:
        subset = [row for row in split if row["split_assignment"] == partition]
        recomputed[partition] = {
            "rows": len(subset),
            "clusters": len({row["operational_protein_cluster"] for row in subset}),
            "sources": dict(sorted(Counter(row["source_id"] for row in subset).items())),
            "datasets": dict(sorted(Counter(row["dataset_id"] for row in subset).items())),
            "expression_types": dict(sorted(Counter(row["expression_type"] for row in subset).items())),
            "variant_classes": dict(sorted(Counter(row["variant_class"] for row in subset).items())),
            "unique_construct_signature_groups": len({row["construct_signature_group"] for row in subset}),
        }
    check("summary_counts_exact", summary["counts"] == recomputed)

    artifact_results = {}
    for name, record in summary["artifacts"].items():
        path = Path(record["path"])
        digest = sha256_file(path)
        artifact_results[name] = digest
        check(f"artifact_sha_{name}", digest == record["sha256"] and path.stat().st_size == record["bytes"], digest)
    check("scientific_boundary_retained", any("No multi-protein synonymous functional training corpus" in item for item in summary["scientific_boundaries"]))
    check("all_pairwise_overlap_flag", summary["leakage"]["all_pairwise_overlaps_zero"] is True)

    status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    report = {
        "schema_version": "a8-rk-functional-split-independent-verification-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "checks": checks,
        "rows": len(split),
        "counts": {name: value["rows"] for name, value in recomputed.items()},
        "clusters": len(rep_to_members),
        "infa_cluster": infa_rep,
        "boel_rows_frozen_with_infa_cluster": sum(row["source_id"] == "boel_2016_nesg6348" and row["split_assignment"] == "functional_untouched" for row in split),
        "artifact_sha256": artifact_results,
        "training_ready": False,
        "functional_untouched_evaluated": False,
    }
    (args.audit_dir / "independent_split_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report = verify(args)
    print(json.dumps({
        "status": report["status"],
        "checks": len(report["checks"]),
        "failed": [item for item in report["checks"] if item["status"] != "PASS"],
        "rows": report["rows"],
        "counts": report["counts"],
    }, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
