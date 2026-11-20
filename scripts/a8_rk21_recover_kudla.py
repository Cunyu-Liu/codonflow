#!/usr/bin/env python3
"""Recover and cross-check the Kudla GFP sequence-expression tables."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import math
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import xlrd
from scipy.io import loadmat


CODONS = ["".join(item) for item in itertools.product("TCAG", repeat=3)]
AMINO_ACIDS = (
    "FFLLSSSSYY**CC*W"
    "LLLLPPPPHHQQRRRR"
    "IIIMTTTTNNKKSSRR"
    "VVVVAAAADDEEGGGG"
)
GENETIC_CODE = dict(zip(CODONS, AMINO_ACIDS))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def translate(cds: str) -> str:
    if len(cds) % 3:
        raise ValueError("CDS length is not divisible by three")
    return "".join(GENETIC_CODE[cds[index:index + 3]] for index in range(0, len(cds), 3))


def sheet_records(book: xlrd.book.Book, sheet_name: str) -> tuple[list[str], list[dict[str, Any]]]:
    sheet = book.sheet_by_name(sheet_name)
    headers = [str(value) for value in sheet.row_values(0)]
    if len(headers) != len(set(headers)) or any(not value for value in headers):
        raise ValueError(f"Invalid or duplicate headers in {sheet_name}")
    records = []
    for row_index in range(1, sheet.nrows):
        values = sheet.row_values(row_index)
        record = dict(zip(headers, values))
        record["source_row"] = row_index + 1
        records.append(record)
    return headers, records


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def write_csv(path: Path, fieldnames: list[str], records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        for record in records:
            writer.writerow({key: csv_value(record.get(key, "")) for key in fieldnames})
    temporary.replace(path)


def fasta(records: list[tuple[str, str]]) -> str:
    lines = []
    for identifier, sequence in records:
        lines.append(">" + identifier)
        lines.extend(sequence[index:index + 80] for index in range(0, len(sequence), 80))
    return "\n".join(lines) + "\n"


def numeric(value: Any, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite {label}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--repo-root", default="/home/codonflow-a8-rk")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol["schema"] != "a8-rk21-kudla-recovery-protocol-v1":
        raise ValueError("Unexpected protocol schema")
    if not protocol["frozen_before_validated_table_export"]:
        raise ValueError("Protocol was not frozen")

    output_root = Path(protocol["output_root"])
    audit_root = repo / protocol["audit_root"]
    derived_root = output_root / "derived"
    derived_root.mkdir(parents=True, exist_ok=True)
    audit_root.mkdir(parents=True, exist_ok=True)
    primary = protocol["sources"]["primary_table"]
    derivative = protocol["sources"]["independent_derivative_copy"]
    xls_path = Path(primary["path"])
    zip_path = Path(derivative["path"])
    if sha256(xls_path) != primary["sha256"] or xls_path.stat().st_size != primary["bytes"]:
        raise ValueError("Primary XLS identity mismatch")
    if sha256(zip_path) != derivative["sha256"] or zip_path.stat().st_size != derivative["bytes"]:
        raise ValueError("Derivative ZIP identity mismatch")

    book = xlrd.open_workbook(xls_path, on_demand=True)
    expected_sheets = ["title", primary["main_sheet"], primary["tagged_sheet"], primary["natural_reference_sheet"]]
    if book.sheet_names() != expected_sheets:
        raise ValueError(f"Unexpected workbook sheets: {book.sheet_names()}")
    main_headers, main_records = sheet_records(book, primary["main_sheet"])
    tagged_headers, tagged_records = sheet_records(book, primary["tagged_sheet"])
    contract = protocol["expected_contract"]
    if len(main_records) != contract["main_rows"] or len(main_headers) != contract["main_columns"]:
        raise ValueError("Main GFP table dimensions do not match the frozen contract")
    if len(tagged_records) != contract["tagged_rows"] or len(tagged_headers) != contract["tagged_columns"]:
        raise ValueError("Tagged GFP table dimensions do not match the frozen contract")
    for column in contract["required_main_columns"]:
        if column not in main_headers:
            raise ValueError(f"Missing main column {column}")
    for column in contract["required_tagged_columns"]:
        if column not in tagged_headers:
            raise ValueError(f"Missing tagged column {column}")

    with zipfile.ZipFile(zip_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Derivative ZIP CRC failure")
        mat_bytes = archive.read(derivative["mat_member"])
        if sha256_bytes(mat_bytes) != derivative["mat_sha256"]:
            raise ValueError("MAT member identity mismatch")
        mat = loadmat(io.BytesIO(mat_bytes), struct_as_record=False, squeeze_me=True)["Data"]
        if mat._fieldnames != ["Sequence", "Des", "rnaEnergyMinus4to37", "rnaEnergyEntireProt"]:
            raise ValueError(f"Unexpected MAT fields: {mat._fieldnames}")
        if archive.read("FinalCodonModel/Kudla_Dataset_WithEnergy.mat") != mat_bytes:
            raise ValueError("Duplicate MAT copies inside S1 Software differ")

    mat_sequences = [str(value).upper() for value in mat.Sequence]
    mat_expression = np.asarray(mat.Des, dtype=np.int64)
    mat_mfe5 = np.asarray(mat.rnaEnergyMinus4to37, dtype=float)
    mat_mfe_all = np.asarray(mat.rnaEnergyEntireProt, dtype=float)
    if not (len(mat_sequences) == len(mat_expression) == len(mat_mfe5) == len(mat_mfe_all) == len(main_records)):
        raise ValueError("MAT and XLS row counts differ")

    sequences = []
    for index, record in enumerate(main_records):
        sequence = str(record["sequenceWithUtr"]).upper()
        if len(sequence) != contract["full_mrna_nt"] or set(sequence) - set("ACGT"):
            raise ValueError(f"Invalid full mRNA at source row {record['source_row']}")
        if sequence != mat_sequences[index]:
            raise ValueError(f"XLS/MAT sequence mismatch at row {index + 1}")
        expression = numeric(record["pGK8_normalizedFlourescence"], "expression")
        if expression <= 0 or expression != float(mat_expression[index]):
            raise ValueError(f"XLS/MAT expression mismatch at row {index + 1}")
        mfe5 = numeric(record["rnaEnergy_-4..37"], "5prime MFE")
        if not math.isclose(mfe5, float(mat_mfe5[index]), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"XLS/MAT 5prime MFE mismatch at row {index + 1}")
        sequences.append(sequence)

    utr_length = contract["utr_5prime_nt"]
    cds_length = contract["cds_nt_including_stop"]
    if utr_length + cds_length != contract["full_mrna_nt"]:
        raise ValueError("Frozen sequence coordinates do not sum to full mRNA length")
    reference_utr = sequences[0][:utr_length]
    proteins = []
    exact_group_for_sequence: dict[str, str] = {}
    group_members: dict[str, list[str]] = defaultdict(list)
    for index, (record, sequence) in enumerate(zip(main_records, sequences)):
        if sequence[:utr_length] != reference_utr:
            raise ValueError("5prime UTR is not shared by all constructs")
        cds = sequence[utr_length:]
        if len(cds) != cds_length or not cds.startswith("ATG"):
            raise ValueError("Invalid CDS boundary")
        translated = translate(cds)
        if translated.count("*") != 1 or not translated.endswith("*"):
            raise ValueError("CDS must have exactly one terminal stop")
        protein = translated[:-1]
        if len(protein) != contract["protein_aa_excluding_stop"]:
            raise ValueError("Unexpected protein length")
        proteins.append(protein)
        if cds not in exact_group_for_sequence:
            exact_group_for_sequence[cds] = f"KUDLA_CDS_{len(exact_group_for_sequence) + 1:03d}"
        group = exact_group_for_sequence[cds]
        group_members[group].append(str(record["seqId"]))
        record["utr_5prime"] = reference_utr
        record["cds"] = cds
        record["protein_aa"] = protein
        record["expression_value"] = numeric(record["pGK8_normalizedFlourescence"], "expression")
        record["log10_expression"] = math.log10(record["expression_value"])
        record["mfe_5prime_kcal_mol"] = numeric(record["rnaEnergy_-4..37"], "5prime MFE")
        record["rna_energy_entire_prot_kcal_mol"] = float(mat_mfe_all[index])
        record["cds_sha256"] = sha256_bytes(cds.encode("ascii"))
        record["exact_cds_group"] = group
        record["source_sequence_matches_mat"] = True
        record["source_expression_matches_mat"] = True
        record["source_mfe5_matches_mat"] = True
    if len(set(proteins)) != 1:
        raise ValueError("The 154 constructs do not encode one identical protein")
    if len(exact_group_for_sequence) != contract["unique_exact_cds"]:
        raise ValueError("Unique exact-CDS count differs from frozen contract")
    duplicate_groups = {key: value for key, value in group_members.items() if len(value) > 1}
    if len(duplicate_groups) != contract["duplicate_exact_cds_groups"]:
        raise ValueError("Duplicate exact-CDS group count differs from frozen contract")
    for record in main_records:
        record["exact_cds_group_size"] = len(group_members[record["exact_cds_group"]])
    if len({str(record["seqId"]) for record in main_records}) != len(main_records):
        raise ValueError("seqId is not unique in the main table")
    expression_values = [record["expression_value"] for record in main_records]
    if min(expression_values) != contract["expression_min"] or max(expression_values) != contract["expression_max"]:
        raise ValueError("Expression range differs from frozen contract")

    main_by_id = {str(record["seqId"]): record for record in main_records}
    yes_ids = {str(record["seqId"]) for record in main_records if str(record["is_in_72-sequence_set"]).lower() == "yes"}
    tagged_ids = [str(record["seqId"]) for record in tagged_records]
    if len(set(tagged_ids)) != len(tagged_records) or set(tagged_ids) != yes_ids:
        raise ValueError("The 72 tagged IDs and the main-sheet yes flags differ")
    for record in tagged_records:
        linked = main_by_id[str(record["seqId"])]
        record["main_cds_group"] = linked["exact_cds_group"]
        record["main_sequence_sha256"] = linked["cds_sha256"]
        record["expression_value"] = numeric(record["pGK16_fluo_with_leader_sequence"], "tagged expression")
        if record["expression_value"] <= 0:
            raise ValueError("Tagged expression must be positive")
        record["log10_expression"] = math.log10(record["expression_value"])
        record["tagged_sequence_available"] = False

    main_derived = [
        "utr_5prime", "cds", "protein_aa", "expression_value", "log10_expression",
        "mfe_5prime_kcal_mol", "rna_energy_entire_prot_kcal_mol", "cds_sha256",
        "exact_cds_group", "exact_cds_group_size", "source_sequence_matches_mat",
        "source_expression_matches_mat", "source_mfe5_matches_mat",
    ]
    main_fields = ["source_row"] + main_headers + main_derived
    tagged_derived = ["main_cds_group", "main_sequence_sha256", "expression_value", "log10_expression", "tagged_sequence_available"]
    tagged_fields = ["source_row"] + tagged_headers + tagged_derived
    main_csv = derived_root / "kudla154_source.csv"
    tagged_csv = derived_root / "kudla_tagged72_source.csv"
    write_csv(main_csv, main_fields, main_records)
    write_csv(tagged_csv, tagged_fields, tagged_records)
    mrna_fasta = derived_root / "kudla154_mrna.fasta"
    cds_fasta = derived_root / "kudla154_cds.fasta"
    atomic_text(mrna_fasta, fasta([(str(record["seqId"]), str(record["sequenceWithUtr"]).upper()) for record in main_records]))
    atomic_text(cds_fasta, fasta([(str(record["seqId"]), str(record["cds"])) for record in main_records]))

    duplicate_table = []
    for group, identifiers in group_members.items():
        if len(identifiers) == 1:
            continue
        rows = [main_by_id[identifier] for identifier in identifiers]
        duplicate_table.append({
            "exact_cds_group": group,
            "seqIds": identifiers,
            "expressions": [row["expression_value"] for row in rows],
            "cds_sha256": rows[0]["cds_sha256"],
        })

    outputs = {
        "main_csv": main_csv,
        "tagged_csv": tagged_csv,
        "mrna_fasta": mrna_fasta,
        "cds_fasta": cds_fasta,
    }
    summary = {
        "schema": "a8-rk21-kudla-recovery-v1",
        "status": "PASS_RECOVERY_PENDING_INDEPENDENT_VERIFICATION",
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "recovery_script_sha256": sha256(Path(__file__).resolve()),
        "source_chain": {
            "primary_measurements": protocol["sources"]["primary_measurements"],
            "primary_table": primary,
            "independent_derivative_copy": derivative,
        },
        "counts": {
            "main_measurement_rows": len(main_records),
            "main_source_columns": len(main_headers),
            "unique_seqId": len(main_by_id),
            "unique_exact_cds": len(exact_group_for_sequence),
            "duplicate_exact_cds_groups": len(duplicate_groups),
            "duplicate_measurement_rows_beyond_unique": len(main_records) - len(exact_group_for_sequence),
            "tagged_rows": len(tagged_records),
            "tagged_source_columns": len(tagged_headers),
            "shared_5prime_utr_nt": utr_length,
            "cds_nt_including_stop": cds_length,
            "protein_aa_excluding_stop": len(proteins[0]),
            "unique_protein_sequences": len(set(proteins)),
        },
        "expression_range": {"min": min(expression_values), "max": max(expression_values)},
        "shared_5prime_utr_sha256": sha256_bytes(reference_utr.encode("ascii")),
        "protein_sha256": sha256_bytes(proteins[0].encode("ascii")),
        "duplicate_exact_cds": duplicate_table,
        "primary_xls_mat_exact_match": True,
        "tagged_sequence_available": False,
        "tagged_ids_match_main_yes_flags": True,
        "outputs": {key: {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size} for key, path in outputs.items()},
        "scientific_flags": {
            "model_fit_or_mechanism_metric_computed": False,
            "fixed_protein_sequence_ood_evaluated": False,
            "paired_tag_mechanism_evaluated": False,
            "functional_ood_evaluated": False,
            "functional_untouched_evaluated": False,
            "rk_g1_pass": False,
            "expensive_generation_authorized": False,
            "time_matched_comparison": False,
            "sota_claimed": False
        },
        "limitations": [
            "File S2 is the authoritative per-construct table used here; the MAT file is an independently published derivative copy that matches it row by row.",
            "Four pairs of distinct seqIds have identical CDS but different measured expression and must remain grouped in future splits.",
            "The tagged sheet has 72 paired measurements and computed features but no tagged nucleotide sequence; no tagged sequence is imputed.",
            "Recovery alone is not mechanism, OOD, untouched, generator or SOTA evidence."
        ],
    }
    summary_path = derived_root / "recovery_summary.json"
    atomic_json(summary_path, summary)
    atomic_json(audit_root / "rk21_kudla_recovery_summary_v1.json", summary)
    print(json.dumps({
        "status": summary["status"],
        "main_rows": len(main_records),
        "unique_exact_cds": len(exact_group_for_sequence),
        "tagged_rows": len(tagged_records),
        "primary_xls_mat_exact_match": True,
        "output_root": str(derived_root),
    }, indent=2))


if __name__ == "__main__":
    main()
