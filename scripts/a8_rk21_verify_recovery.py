#!/usr/bin/env python3
"""Independently verify RK21 raw-source identity and exported tables."""
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


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def read_fasta(path: Path) -> list[tuple[str, str]]:
    records = []
    identifier = None
    chunks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(">"):
            if identifier is not None:
                records.append((identifier, "".join(chunks)))
            identifier = line[1:]
            chunks = []
        else:
            chunks.append(line)
    if identifier is not None:
        records.append((identifier, "".join(chunks)))
    return records


def close(left: Any, right: Any, tolerance: float = 1e-12) -> bool:
    return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)


def source_cells_match(source: dict[str, Any], exported: dict[str, str], headers: list[str], string_columns: set[str]) -> bool:
    for header in headers:
        left = source[header]
        right = exported[header]
        if header in string_columns:
            if str(left) != right:
                return False
        elif left == "":
            if right != "":
                return False
        elif not close(left, right):
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--recovery-summary", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repo-root", default="/home/codonflow-a8-rk")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    protocol_path = Path(args.protocol).resolve()
    summary_path = Path(args.recovery_summary).resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    primary = protocol["sources"]["primary_table"]
    derivative = protocol["sources"]["independent_derivative_copy"]
    contract = protocol["expected_contract"]
    output_root = Path(protocol["output_root"])
    derived = output_root / "derived"
    main_path = derived / "kudla154_source.csv"
    tagged_path = derived / "kudla_tagged72_source.csv"
    mrna_path = derived / "kudla154_mrna.fasta"
    cds_path = derived / "kudla154_cds.fasta"
    checks = []

    def check(name: str, condition: bool, detail: Any = None) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("protocol_schema", protocol["schema"] == "a8-rk21-kudla-recovery-protocol-v1")
    check("summary_pending_independent", summary["status"] == "PASS_RECOVERY_PENDING_INDEPENDENT_VERIFICATION")
    check("protocol_hash_binding", summary["protocol_sha256"] == sha256(protocol_path))
    check("recovery_script_hash_binding", summary["recovery_script_sha256"] == sha256(repo / "scripts" / "a8_rk21_recover_kudla.py"))
    xls_path = Path(primary["path"])
    zip_path = Path(derivative["path"])
    check("primary_xls_sha", sha256(xls_path) == primary["sha256"])
    check("primary_xls_bytes", xls_path.stat().st_size == primary["bytes"])
    check("derivative_zip_sha", sha256(zip_path) == derivative["sha256"])
    check("derivative_zip_bytes", zip_path.stat().st_size == derivative["bytes"])
    for key, path in (("main_csv", main_path), ("tagged_csv", tagged_path), ("mrna_fasta", mrna_path), ("cds_fasta", cds_path)):
        check(f"output_hash_{key}", summary["outputs"][key]["sha256"] == sha256(path))
        check(f"output_bytes_{key}", summary["outputs"][key]["bytes"] == path.stat().st_size)

    book = xlrd.open_workbook(xls_path, on_demand=True)
    expected_sheets = ["title", primary["main_sheet"], primary["tagged_sheet"], primary["natural_reference_sheet"]]
    check("workbook_sheet_inventory", book.sheet_names() == expected_sheets, book.sheet_names())
    main_sheet = book.sheet_by_name(primary["main_sheet"])
    tagged_sheet = book.sheet_by_name(primary["tagged_sheet"])
    natural_sheet = book.sheet_by_name(primary["natural_reference_sheet"])
    main_headers = [str(value) for value in main_sheet.row_values(0)]
    tagged_headers = [str(value) for value in tagged_sheet.row_values(0)]
    main_source = [dict(zip(main_headers, main_sheet.row_values(row))) for row in range(1, main_sheet.nrows)]
    tagged_source = [dict(zip(tagged_headers, tagged_sheet.row_values(row))) for row in range(1, tagged_sheet.nrows)]
    check("main_source_dimensions", len(main_source) == contract["main_rows"] and len(main_headers) == contract["main_columns"])
    check("tagged_source_dimensions", len(tagged_source) == contract["tagged_rows"] and len(tagged_headers) == contract["tagged_columns"])
    check("natural_reference_dimensions", natural_sheet.nrows == 3920 and natural_sheet.ncols == 71, [natural_sheet.nrows, natural_sheet.ncols])

    main_fields, main_rows = read_csv(main_path)
    tagged_fields, tagged_rows = read_csv(tagged_path)
    check("main_export_rows", len(main_rows) == contract["main_rows"], len(main_rows))
    check("tagged_export_rows", len(tagged_rows) == contract["tagged_rows"], len(tagged_rows))
    check("main_source_columns_preserved", all(main_fields.count(header) == 1 for header in main_headers))
    check("tagged_source_columns_preserved", all(tagged_fields.count(header) == 1 for header in tagged_headers))
    check("main_source_row_order", all(int(row["source_row"]) == index + 2 for index, row in enumerate(main_rows)))
    check("tagged_source_row_order", all(int(row["source_row"]) == index + 2 for index, row in enumerate(tagged_rows)))
    main_string_columns = {"seqId", "is_in_72-sequence_set", "sequenceWithUtr"}
    tagged_string_columns = {"seqId"}
    check("every_main_source_cell_match", all(source_cells_match(source, row, main_headers, main_string_columns) for source, row in zip(main_source, main_rows)))
    check("every_tagged_source_cell_match", all(source_cells_match(source, row, tagged_headers, tagged_string_columns) for source, row in zip(tagged_source, tagged_rows)))
    identifiers = [row["seqId"] for row in main_rows]
    check("seqId_unique", len(set(identifiers)) == contract["main_rows"])
    expression = np.asarray([float(row["expression_value"]) for row in main_rows])
    check("expression_positive_finite", bool(np.isfinite(expression).all() and (expression > 0).all()))
    check("expression_range", float(expression.min()) == contract["expression_min"] and float(expression.max()) == contract["expression_max"], [float(expression.min()), float(expression.max())])
    check("expression_alias_exact", all(close(row["expression_value"], row["pGK8_normalizedFlourescence"]) for row in main_rows))
    check("log10_expression_recomputed", all(close(row["log10_expression"], math.log10(float(row["expression_value"]))) for row in main_rows))

    sequences = [row["sequenceWithUtr"].upper() for row in main_rows]
    check("full_mrna_alphabet_length", all(len(sequence) == contract["full_mrna_nt"] and not set(sequence) - set("ACGT") for sequence in sequences))
    utr = sequences[0][:contract["utr_5prime_nt"]]
    check("shared_utr_recomputed", all(sequence[:contract["utr_5prime_nt"]] == utr and row["utr_5prime"] == utr for sequence, row in zip(sequences, main_rows)))
    check("shared_utr_hash", summary["shared_5prime_utr_sha256"] == hashlib.sha256(utr.encode("ascii")).hexdigest())
    cds_values = [sequence[contract["utr_5prime_nt"]:] for sequence in sequences]
    proteins = []
    terminal_stops = []
    for cds in cds_values:
        protein = "".join(GENETIC_CODE[cds[index:index + 3]] for index in range(0, len(cds), 3))
        proteins.append(protein[:-1])
        terminal_stops.append(protein.count("*") == 1 and protein.endswith("*"))
    check("cds_boundaries", all(len(cds) == contract["cds_nt_including_stop"] and cds.startswith("ATG") for cds in cds_values))
    check("terminal_stop_exactly_one", all(terminal_stops))
    check("one_identical_protein", len(set(proteins)) == 1 and len(proteins[0]) == contract["protein_aa_excluding_stop"])
    check("protein_export_and_hash", all(row["protein_aa"] == proteins[0] for row in main_rows) and summary["protein_sha256"] == hashlib.sha256(proteins[0].encode("ascii")).hexdigest())
    check("cds_export_exact", all(row["cds"] == cds for row, cds in zip(main_rows, cds_values)))
    check("cds_hash_recomputed", all(row["cds_sha256"] == hashlib.sha256(cds.encode("ascii")).hexdigest() for row, cds in zip(main_rows, cds_values)))

    group_to_cds = defaultdict(set)
    cds_to_group = defaultdict(set)
    for row, cds in zip(main_rows, cds_values):
        group_to_cds[row["exact_cds_group"]].add(cds)
        cds_to_group[cds].add(row["exact_cds_group"])
    check("group_bijection", all(len(value) == 1 for value in group_to_cds.values()) and all(len(value) == 1 for value in cds_to_group.values()))
    observed_sizes = Counter(row["exact_cds_group"] for row in main_rows)
    check("unique_exact_cds_150", len(cds_to_group) == contract["unique_exact_cds"], len(cds_to_group))
    duplicate_sizes = {key: value for key, value in observed_sizes.items() if value > 1}
    check("four_duplicate_groups", len(duplicate_sizes) == contract["duplicate_exact_cds_groups"] and set(duplicate_sizes.values()) == {2}, duplicate_sizes)
    check("group_size_column", all(int(row["exact_cds_group_size"]) == observed_sizes[row["exact_cds_group"]] for row in main_rows))

    with zipfile.ZipFile(zip_path) as archive:
        check("derivative_zip_crc", archive.testzip() is None)
        mat_bytes = archive.read(derivative["mat_member"])
        check("mat_member_sha", hashlib.sha256(mat_bytes).hexdigest() == derivative["mat_sha256"])
        check("mat_duplicate_copies_identical", archive.read("FinalCodonModel/Kudla_Dataset_WithEnergy.mat") == mat_bytes)
        mat = loadmat(io.BytesIO(mat_bytes), struct_as_record=False, squeeze_me=True)["Data"]
    check("mat_fields", mat._fieldnames == ["Sequence", "Des", "rnaEnergyMinus4to37", "rnaEnergyEntireProt"], mat._fieldnames)
    mat_sequences = [str(value).upper() for value in mat.Sequence]
    check("mat_row_count", len(mat_sequences) == len(main_rows) == len(mat.Des) == len(mat.rnaEnergyMinus4to37) == len(mat.rnaEnergyEntireProt))
    check("mat_sequences_exact", mat_sequences == sequences)
    check("mat_expression_exact", all(int(value) == float(row["expression_value"]) for value, row in zip(mat.Des, main_rows)))
    check("mat_mfe5_exact", all(close(value, row["mfe_5prime_kcal_mol"]) for value, row in zip(mat.rnaEnergyMinus4to37, main_rows)))
    check("mat_full_mfe_exact", all(close(value, row["rna_energy_entire_prot_kcal_mol"]) for value, row in zip(mat.rnaEnergyEntireProt, main_rows)))
    check("mat_match_flags", all(row["source_sequence_matches_mat"] == "True" and row["source_expression_matches_mat"] == "True" and row["source_mfe5_matches_mat"] == "True" for row in main_rows))

    tagged_ids = [row["seqId"] for row in tagged_rows]
    yes_ids = {row["seqId"] for row in main_rows if row["is_in_72-sequence_set"].lower() == "yes"}
    check("tagged_ids_unique", len(set(tagged_ids)) == contract["tagged_rows"])
    check("tagged_ids_match_yes_flags", set(tagged_ids) == yes_ids and len(yes_ids) == contract["tagged_rows"])
    main_by_id = {row["seqId"]: row for row in main_rows}
    check("tagged_links_exact", all(row["main_cds_group"] == main_by_id[row["seqId"]]["exact_cds_group"] and row["main_sequence_sha256"] == main_by_id[row["seqId"]]["cds_sha256"] for row in tagged_rows))
    check("tagged_expression_positive_log", all(float(row["expression_value"]) > 0 and close(row["expression_value"], row["pGK16_fluo_with_leader_sequence"]) and close(row["log10_expression"], math.log10(float(row["expression_value"]))) for row in tagged_rows))
    check("tagged_sequence_not_imputed", all(row["tagged_sequence_available"] == "False" for row in tagged_rows) and summary["tagged_sequence_available"] is False)

    mrna_fasta = read_fasta(mrna_path)
    cds_fasta = read_fasta(cds_path)
    check("mrna_fasta_roundtrip", mrna_fasta == list(zip(identifiers, sequences)))
    check("cds_fasta_roundtrip", cds_fasta == list(zip(identifiers, cds_values)))
    counts = summary["counts"]
    expected_counts = {
        "main_measurement_rows": 154, "main_source_columns": 71, "unique_seqId": 154,
        "unique_exact_cds": 150, "duplicate_exact_cds_groups": 4,
        "duplicate_measurement_rows_beyond_unique": 4, "tagged_rows": 72,
        "tagged_source_columns": 62, "shared_5prime_utr_nt": 144,
        "cds_nt_including_stop": 720, "protein_aa_excluding_stop": 239,
        "unique_protein_sequences": 1,
    }
    check("summary_counts_recomputed", counts == expected_counts, counts)
    observed_duplicate_summary = []
    for group in sorted(duplicate_sizes, key=lambda key: min(index for index, row in enumerate(main_rows) if row["exact_cds_group"] == key)):
        rows = [row for row in main_rows if row["exact_cds_group"] == group]
        observed_duplicate_summary.append({
            "exact_cds_group": group,
            "seqIds": [row["seqId"] for row in rows],
            "expressions": [float(row["expression_value"]) for row in rows],
            "cds_sha256": rows[0]["cds_sha256"],
        })
    check("duplicate_summary_exact", summary["duplicate_exact_cds"] == observed_duplicate_summary)
    flags = summary["scientific_flags"]
    check("recovery_does_not_claim_scientific_completion", all(flags[key] is False for key in flags))
    check("primary_match_and_tag_link_summary", summary["primary_xls_mat_exact_match"] is True and summary["tagged_ids_match_main_yes_flags"] is True)
    check("source_identity_fields", primary["doi"] == "10.1534/genetics.110.115477" and derivative["doi"] == "10.1371/journal.pone.0150369")
    check("no_untouched_or_generator_claim", flags["functional_untouched_evaluated"] is False and flags["expensive_generation_authorized"] is False and flags["rk_g1_pass"] is False)

    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk21-kudla-recovery-independent-v1",
        "status": "PASS_INDEPENDENT_VERIFICATION" if passed == len(checks) else "FAIL_INDEPENDENT_VERIFICATION",
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "protocol_sha256": sha256(protocol_path),
        "recovery_summary_sha256": sha256(summary_path),
        "verification_script_sha256": sha256(Path(__file__).resolve()),
        "recovery_complete": passed == len(checks),
        "main_measurement_rows": len(main_rows),
        "unique_exact_cds": len(cds_to_group),
        "tagged_rows": len(tagged_rows),
        "primary_xls_mat_exact_match": True,
        "tagged_sequence_available": False,
        "fixed_protein_sequence_ood_evaluated": False,
        "paired_tag_mechanism_evaluated": False,
        "functional_ood_evaluated": False,
        "functional_untouched_evaluated": False,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "sota_claimed": False,
        "output_hashes": {key: sha256(path) for key, path in (("main_csv", main_path), ("tagged_csv", tagged_path), ("mrna_fasta", mrna_path), ("cds_fasta", cds_path))},
    }
    atomic_json(Path(args.output), report)
    print(json.dumps({"status": report["status"], "checks_passed": passed, "checks_total": len(checks)}, indent=2))
    if passed != len(checks):
        for item in checks:
            if not item["pass"]:
                print("FAILED", item)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
