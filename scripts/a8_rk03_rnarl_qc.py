#!/usr/bin/env python3
"""Hash-gated, row-level QC for the RNARL Zenodo long-format CDS pairs.

The source describes two LinearDesign CDS rows per protein. This script tests
that statement without inferring lambda labels from row order or MFE. It never
labels these records as natural CDS and never authorizes functional/OOD claims.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

USER_AGENT = "CodonFlow-A8-RK03-RNARL-QC/1.0"
STOP_CODONS = {"TAA", "TAG", "TGA"}
REQUIRED_COLUMNS = [
    "Protein_ID", "Protein_Sequence", "Protein_Length", "CDS_Sequence",
    "CDS_Length", "CDS_Structure", "CDS_MFE", "CDS_CAI",
]
BASES = "TCAG"
AMINO_ACIDS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODON_TABLE = {
    a + b + c: AMINO_ACIDS[i]
    for i, (a, b, c) in enumerate(
        (a, b, c) for a in BASES for b in BASES for c in BASES
    )
}


class QCError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest_file(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_json(path: Path, value: Mapping[str, object], *, refuse_existing: bool = True) -> None:
    if refuse_existing and path.exists():
        raise QCError(f"refusing to overwrite existing JSON: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def translate_dna(cds: str) -> str:
    if len(cds) % 3 or any(codon not in CODON_TABLE for codon in (cds[i:i + 3] for i in range(0, len(cds), 3))):
        raise QCError("DNA sequence is not an unambiguous complete-codon sequence")
    return "".join(CODON_TABLE[cds[i:i + 3]] for i in range(0, len(cds), 3))


def structure_is_balanced(structure: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{", ">": "<"}
    openings = set(pairs.values())
    stack: List[str] = []
    for char in structure:
        if char == ".":
            continue
        if char in openings:
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return False
        else:
            return False
    return not stack


def numeric_summary(values: Iterable[float]) -> Dict[str, Optional[float]]:
    ordered = sorted(float(x) for x in values if x is not None and math.isfinite(float(x)))
    if not ordered:
        return {"n": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None}

    def quantile(fraction: float) -> float:
        position = (len(ordered) - 1) * fraction
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return ordered[lower]
        weight = position - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    return {
        "n": len(ordered), "min": ordered[0], "p25": quantile(0.25),
        "median": quantile(0.5), "p75": quantile(0.75), "max": ordered[-1],
        "mean": statistics.fmean(ordered),
    }


def _integer(value: object) -> Optional[int]:
    try:
        text = str(value).strip()
        if not re.fullmatch(r"[+-]?\d+", text):
            return None
        return int(text)
    except (TypeError, ValueError):
        return None


def _finite_float(value: object) -> Optional[float]:
    try:
        result = float(str(value).strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def qc_row(raw: Mapping[str, str], filename: str, organism: str, split: str, row_number: int,
           lambda_column: Optional[str]) -> Dict[str, object]:
    protein = str(raw.get("Protein_Sequence", "")).strip().upper()
    source_cds = str(raw.get("CDS_Sequence", "")).strip().upper()
    cds = source_cds.replace("U", "T")
    structure = str(raw.get("CDS_Structure", "")).strip()
    protein_id = str(raw.get("Protein_ID", "")).strip()
    protein_for_comparison = protein[:-1] if protein.endswith("*") else protein
    reasons: List[str] = []
    if not protein_id:
        reasons.append("missing_protein_id")
    if not protein_for_comparison:
        reasons.append("missing_protein_sequence")
    if not protein.endswith("*"):
        reasons.append("missing_protein_terminal_stop_symbol")
    if "*" in protein_for_comparison:
        reasons.append("internal_protein_stop_symbol")
    if not source_cds:
        reasons.append("missing_cds")
    if set(source_cds) - set("ACGU"):
        reasons.append("non_acgu_cds")
    if len(cds) % 3:
        reasons.append("cds_length_not_divisible_by_3")
    reported_protein_length = _integer(raw.get("Protein_Length"))
    reported_cds_length = _integer(raw.get("CDS_Length"))
    if reported_protein_length is None:
        reasons.append("invalid_reported_protein_length")
    elif reported_protein_length != len(protein):
        reasons.append("protein_length_mismatch")
    if reported_cds_length is None:
        reasons.append("invalid_reported_cds_length")
    elif reported_cds_length != len(cds):
        reasons.append("cds_length_mismatch")
    mfe = _finite_float(raw.get("CDS_MFE"))
    cai = _finite_float(raw.get("CDS_CAI"))
    if mfe is None:
        reasons.append("invalid_mfe")
    if cai is None:
        reasons.append("invalid_cai")
    elif not 0.0 <= cai <= 1.0:
        reasons.append("cai_outside_0_1")
    if len(structure) != len(cds):
        reasons.append("structure_length_mismatch")
    if not structure_is_balanced(structure):
        reasons.append("structure_unbalanced_or_unsupported")

    terminal_stop = False
    internal_stop = False
    start_atg = False
    translated: Optional[str] = None
    if source_cds and not set(source_cds) - set("ACGU") and len(source_cds) % 3 == 0:
        codons = [cds[i:i + 3] for i in range(0, len(cds), 3)]
        start_atg = codons[0] == "ATG"
        terminal_stop = codons[-1] in STOP_CODONS
        internal_stop = any(codon in STOP_CODONS for codon in codons[:-1])
        translated_all = translate_dna(cds)
        translated = translated_all[:-1] if terminal_stop else translated_all
        if translated != protein_for_comparison:
            reasons.append("translation_protein_mismatch")
    if cds and not start_atg:
        reasons.append("start_not_atg")
    if cds and not terminal_stop:
        reasons.append("missing_terminal_stop")
    if internal_stop:
        reasons.append("internal_stop")

    coding = cds[:-3] if terminal_stop else cds
    return {
        "record_id": f"{filename}:{row_number:06d}",
        "source_file": filename, "source_row_number": row_number,
        "organism": organism, "split": split,
        "protein_id": protein_id,
        "protein_sequence": protein,
        "protein_length": len(protein_for_comparison),
        "protein_terminal_stop_symbol": protein.endswith("*"),
        "source_cds_rna": source_cds, "source_alphabet": "RNA",
        "cds_dna": cds, "cds_length_nt": len(cds),
        "cds_structure": structure,
        "reported_protein_length": reported_protein_length,
        "reported_cds_length": reported_cds_length,
        "reported_mfe_kcal_mol": mfe, "reported_cai": cai,
        "reported_lambda": str(raw.get(lambda_column, "")).strip() if lambda_column else None,
        "translated_protein": translated,
        "start_atg": start_atg, "terminal_stop": terminal_stop, "internal_stop": internal_stop,
        "gc_fraction_full_cds": (cds.count("G") + cds.count("C")) / len(cds) if cds else None,
        "gc_fraction_coding": (coding.count("G") + coding.count("C")) / len(coding) if coding else None,
        "protein_sha256": sha256_text(protein), "cds_sha256": sha256_text(cds),
        "base_exclusion_reasons": reasons, "base_qc_pass": not reasons,
    }


def source_identity(filename: str) -> Tuple[str, str]:
    match = re.fullmatch(r"(.+)_(train|val|test)\.csv", filename)
    if not match:
        raise QCError(f"cannot parse organism/split from {filename}")
    return match.group(1), match.group(2)


def prepare_output_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise QCError(f"refusing to use nonempty output directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def process_file(path: Path, spec: Mapping[str, object], initial_handle) -> Tuple[Dict[str, object], Dict[str, object]]:
    filename = path.name
    organism, split = source_identity(filename)
    groups: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    per_file: Dict[str, object] = {
        "filename": filename, "organism": organism, "split": split, "status": "processed",
        "bytes": path.stat().st_size, "md5": digest_file(path, "md5"), "sha256": digest_file(path),
        "rows": 0, "base_qc_pass_rows": 0, "pair_groups": 0,
        "pair_structure_pass_groups": 0, "pair_pass_groups": 0,
        "lambda_label_column": None, "lambda_01_pairs": 0,
    }
    pair_deltas: Dict[str, List[float]] = defaultdict(list)
    csv.field_size_limit(100_000_000)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        missing = [column for column in REQUIRED_COLUMNS if column not in headers]
        if missing:
            raise QCError(f"{filename}: missing required columns {missing}")
        lambda_column = next((column for column in headers if "lambda" in column.lower()), None)
        per_file["lambda_label_column"] = lambda_column
        for row_number, raw in enumerate(reader, start=1):
            record = qc_row(raw, filename, organism, split, row_number, lambda_column)
            groups[str(record["protein_id"]) if record["protein_id"] else f"__missing_{row_number}"].append(record)

    rows_per_protein = Counter()
    for group_key, records in groups.items():
        rows_per_protein[len(records)] += 1
        same_protein = len({str(record["protein_sequence"]) for record in records}) == 1
        distinct_cds = len({str(record["cds_dna"]) for record in records}) == len(records)
        structure_pass = len(records) == 2 and same_protein and distinct_cds
        both_base_pass = all(bool(record["base_qc_pass"]) for record in records)
        lambda_values = {str(record["reported_lambda"]) for record in records}
        lambda_01 = len(records) == 2 and lambda_values == {"0", "1"}
        pair_id = filename + ":" + sha256_text(group_key)[:24]
        for member_index, record in enumerate(records, start=1):
            pair_reasons: List[str] = []
            if len(records) != 2:
                pair_reasons.append("pair_group_size_not_2")
            if not same_protein:
                pair_reasons.append("pair_protein_sequence_mismatch")
            if not distinct_cds:
                pair_reasons.append("pair_identical_cds")
            if not both_base_pass:
                pair_reasons.append("pair_member_base_qc_failed")
            record.update({
                "pair_id": pair_id, "pair_member_index": member_index,
                "pair_group_size": len(records), "pair_same_protein_sequence": same_protein,
                "pair_distinct_cds": distinct_cds, "pair_structure_pass": structure_pass,
                "pair_lambda_01_recoverable": lambda_01,
                "pair_pass": structure_pass and both_base_pass,
                "pair_exclusion_reasons": pair_reasons,
            })
            initial_handle.write((json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        per_file["pair_groups"] += 1
        per_file["pair_structure_pass_groups"] += int(structure_pass)
        per_file["pair_pass_groups"] += int(structure_pass and both_base_pass)
        per_file["lambda_01_pairs"] += int(lambda_01)
        if len(records) == 2:
            left, right = records
            if left["reported_mfe_kcal_mol"] is not None and right["reported_mfe_kcal_mol"] is not None:
                pair_deltas["absolute_mfe_difference"].append(abs(float(left["reported_mfe_kcal_mol"]) - float(right["reported_mfe_kcal_mol"])))
            if left["reported_cai"] is not None and right["reported_cai"] is not None:
                pair_deltas["absolute_cai_difference"].append(abs(float(left["reported_cai"]) - float(right["reported_cai"])))
    per_file["rows"] = sum(rows_per_protein[size] * size for size in rows_per_protein)
    per_file["base_qc_pass_rows"] = sum(
        1 for records in groups.values() for record in records if record["base_qc_pass"]
    )
    per_file["rows_per_protein_group_distribution"] = {str(size): count for size, count in sorted(rows_per_protein.items())}
    return per_file, {"pair_deltas": {key: numeric_summary(values) for key, values in pair_deltas.items()}, "groups": groups}


def add_location(index: MutableMapping, key, split: str, location: Tuple[str, int]) -> None:
    index[key][split].append(location)


def build_overlap_indexes(groups_by_file: Mapping[str, Mapping[str, List[Dict[str, object]]]]):
    protein_ids = defaultdict(lambda: defaultdict(list))
    protein_sequences = defaultdict(lambda: defaultdict(list))
    exact_cds = defaultdict(lambda: defaultdict(list))
    for file_groups in groups_by_file.values():
        for records in file_groups.values():
            for record in records:
                location = (str(record["source_file"]), int(record["source_row_number"]))
                split = str(record["split"])
                if record["protein_id"]:
                    add_location(protein_ids, (record["organism"], record["protein_id"]), split, location)
                if record["protein_sequence"]:
                    add_location(protein_sequences, (record["organism"], record["protein_sequence"]), split, location)
                if record["cds_dna"]:
                    add_location(exact_cds, record["cds_dna"], split, location)
    return protein_ids, protein_sequences, exact_cds


def is_cross_split(index: Mapping, key) -> bool:
    return key in index and len(index[key]) > 1


def overlap_summary(index: Mapping, kind: str, limit: int = 20) -> Dict[str, object]:
    examples = []
    count = 0
    for key, splits in index.items():
        if len(splits) <= 1:
            continue
        count += 1
        if len(examples) >= limit:
            continue
        if kind == "protein_id":
            identity: object = {"organism": key[0], "protein_id": key[1]}
        elif kind == "protein_sequence":
            identity = {"organism": key[0], "protein_sha256": sha256_text(key[1])}
        else:
            identity = {"cds_sha256": sha256_text(key)}
        examples.append({"identity": identity, "locations": {split: values[:4] for split, values in sorted(splits.items())}})
    return {"overlapping_keys": count, "examples": examples}


def run_qc(config_path: Path, raw_dir: Path, output_dir: Path, audit_path: Optional[Path] = None,
           allow_partial: bool = False) -> Dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source = next(item for item in config["sources"] if item["source_id"] == "rnarl_v1")
    specs = list(source["files"])
    if not specs:
        raise QCError("no RNARL files registered")
    prepare_output_dir(output_dir)
    initial_path = output_dir / ".rnarl_all_qc.initial.jsonl.gz"
    all_path = output_dir / "rnarl_all_qc.jsonl.gz"
    clean_path = output_dir / "rnarl_clean.jsonl.gz"
    per_files: List[Dict[str, object]] = []
    groups_by_file: Dict[str, Mapping[str, List[Dict[str, object]]]] = {}
    pair_delta_by_file: Dict[str, object] = {}
    with gzip.open(initial_path, "wb", compresslevel=5) as initial_handle:
        for spec in specs:
            filename = str(spec["filename"])
            path = raw_dir / filename
            try:
                if not path.is_file():
                    raise QCError("missing raw file")
                expected_md5 = str(spec.get("expected_md5", "")).lower()
                actual_md5 = digest_file(path, "md5")
                if expected_md5 and actual_md5.lower() != expected_md5:
                    raise QCError(f"MD5 mismatch: expected={expected_md5}, actual={actual_md5}")
                per_file, extras = process_file(path, spec, initial_handle)
                per_files.append(per_file)
                groups_by_file[filename] = extras["groups"]
                pair_delta_by_file[filename] = extras["pair_deltas"]
            except Exception as exc:
                if not allow_partial:
                    raise
                per_files.append({"filename": filename, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    processed = [item for item in per_files if item["status"] == "processed"]
    if not processed:
        raise QCError("no verified RNARL files were processed")

    protein_ids, protein_sequences, exact_cds = build_overlap_indexes(groups_by_file)
    overlaps = {
        "protein_id": overlap_summary(protein_ids, "protein_id"),
        "protein_sequence": overlap_summary(protein_sequences, "protein_sequence"),
        "exact_cds": overlap_summary(exact_cds, "exact_cds"),
    }
    def record_overlap_flags(record: Mapping[str, object]) -> Tuple[bool, bool, bool]:
        id_key = (record["organism"], record["protein_id"])
        protein_key = (record["organism"], record["protein_sequence"])
        return (
            bool(record["protein_id"]) and is_cross_split(protein_ids, id_key),
            bool(record["protein_sequence"]) and is_cross_split(protein_sequences, protein_key),
            bool(record["cds_dna"]) and is_cross_split(exact_cds, record["cds_dna"]),
        )

    pair_overlap_flags: Dict[str, Tuple[bool, bool, bool]] = {}
    for file_groups in groups_by_file.values():
        for records in file_groups.values():
            own = [record_overlap_flags(record) for record in records]
            pair_overlap_flags[str(records[0]["pair_id"])] = tuple(
                any(flags[index] for flags in own) for index in range(3)
            )

    clean_values: Dict[str, Dict[str, List[float]]] = {
        item["filename"]: defaultdict(list) for item in processed
    }
    clean_by_file = Counter()
    overlap_rows = Counter()
    total_rows = 0
    clean_rows = 0
    with gzip.open(initial_path, "rt", encoding="utf-8") as source_handle, \
            gzip.open(all_path, "wt", encoding="utf-8", compresslevel=5) as all_handle, \
            gzip.open(clean_path, "wt", encoding="utf-8", compresslevel=5) as clean_handle:
        for line in source_handle:
            record = json.loads(line)
            id_overlap, protein_overlap, cds_overlap = record_overlap_flags(record)
            pair_flags = pair_overlap_flags[str(record["pair_id"])]
            reasons = list(record["base_exclusion_reasons"]) + list(record["pair_exclusion_reasons"])
            for flag, label in ((id_overlap, "cross_split_protein_id"), (protein_overlap, "cross_split_protein_sequence"), (cds_overlap, "cross_split_exact_cds")):
                if flag:
                    reasons.append(label)
                    overlap_rows[label] += 1
            if any(pair_flags) and not any((id_overlap, protein_overlap, cds_overlap)):
                reasons.append("pair_member_cross_split_overlap")
            clean = bool(record["pair_pass"]) and not any(pair_flags)
            record.update({
                "cross_split_protein_id": id_overlap,
                "cross_split_protein_sequence": protein_overlap,
                "cross_split_exact_cds": cds_overlap,
                "pair_cross_split_overlap": any(pair_flags),
                "exclusion_reasons": reasons, "clean_eligible": clean,
                "natural_cds_source_validated": False,
                "lambda_identity_inferred_from_order_or_mfe": False,
            })
            all_handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            total_rows += 1
            if clean:
                clean_handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                clean_rows += 1
                clean_by_file[record["source_file"]] += 1
                values = clean_values[record["source_file"]]
                for metric in ("protein_length", "cds_length_nt", "gc_fraction_full_cds", "reported_cai", "reported_mfe_kcal_mol"):
                    if record[metric] is not None:
                        values[metric].append(float(record[metric]))
    initial_path.unlink()
    for item in processed:
        item["clean_rows"] = clean_by_file[item["filename"]]
        item["clean_pair_rows_even"] = clean_by_file[item["filename"]] % 2 == 0
        item["clean_distributions"] = {
            metric: numeric_summary(values) for metric, values in clean_values[item["filename"]].items()
        }
        item["pair_delta_distributions"] = pair_delta_by_file[item["filename"]]
    if clean_rows % 2:
        raise QCError("clean pair table has an odd row count")

    total_pair_groups = sum(int(item["pair_groups"]) for item in processed)
    structure_groups = sum(int(item["pair_structure_pass_groups"]) for item in processed)
    pair_pass_groups = sum(int(item["pair_pass_groups"]) for item in processed)
    full_source = len(processed) == len(specs)
    long_format_observed = total_pair_groups > 0 and structure_groups == total_pair_groups
    lambda_recoverable = bool(processed) and all(
        item["lambda_label_column"] and item["lambda_01_pairs"] == item["pair_groups"] for item in processed
    )
    any_overlap = any(value["overlapping_keys"] for value in overlaps.values())
    bounded_pair_table_ready = full_source and clean_rows > 0
    status = "COMPLETE_QC_PENDING_INDEPENDENT_VERIFICATION" if full_source else "PARTIAL_SMOKE_ONLY"
    summary: Dict[str, object] = {
        "schema_version": "a8-rk03-rnarl-qc-v2", "created_at": utc_now(), "status": status,
        "config_path": str(config_path), "config_sha256": digest_file(config_path),
        "raw_dir": str(raw_dir), "output_dir": str(output_dir),
        "source_record": source["record"], "license": source["license"],
        "repository_commit": source["repository_commit"],
        "expected_file_count": len(specs), "processed_file_count": len(processed),
        "total_rows": total_rows, "clean_rows": clean_rows, "clean_pairs": clean_rows // 2,
        "pair_groups": total_pair_groups, "pair_structure_pass_groups": structure_groups,
        "pair_pass_groups": pair_pass_groups,
        "long_format_two_distinct_cds_pattern_observed": long_format_observed,
        "lambda_label_recoverable": lambda_recoverable,
        "row_order_or_mfe_lambda_assignment_allowed": False,
        "lineardesign_provenance_independently_validated": False,
        "natural_cds_source_validated": False,
        "natural_distribution_eligible": False,
        "bounded_lineardesign_pair_table_ready_pending_verifier": bounded_pair_table_ready,
        "lambda_stratified_analysis_ready": False,
        "functional_training_authorized": False, "functional_ood_claim_authorized": False,
        "split_overlaps": overlaps, "overlap_row_counts": dict(overlap_rows),
        "raw_split_overlap_detected": any_overlap,
        "clean_pair_level_leakage_exclusion_applied": True,
        "files": per_files,
        "unavailable_source_metadata": [
            "natural_CDS_accession", "explicit_lambda_per_row", "UTR", "vector", "host",
            "promoter", "chemical_modification", "assay_batch", "experimental_function", "EFE",
        ],
        "scope": "QC of publisher-provided LinearDesign-like pair table; not natural-CDS validation, functional training, OOD, or SOTA evidence.",
        "artifacts": {"all_qc": all_path.name, "clean": clean_path.name},
    }
    summary_path = output_dir / "qc_summary.json"
    atomic_write_json(summary_path, summary)
    manifest = {
        "schema_version": "a8-rk03-rnarl-artifact-manifest-v1", "created_at": utc_now(),
        "source_files": per_files,
        "outputs": {
            path.name: {"bytes": path.stat().st_size, "sha256": digest_file(path)}
            for path in (all_path, clean_path, summary_path)
        },
    }
    atomic_write_json(output_dir / "artifact_manifest.json", manifest)
    if audit_path is not None:
        atomic_write_json(audit_path, summary)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args(argv)
    summary = run_qc(args.config, args.raw_dir, args.output_dir, args.audit, args.allow_partial)
    print(json.dumps({key: summary[key] for key in (
        "status", "processed_file_count", "total_rows", "clean_rows", "clean_pairs",
        "long_format_two_distinct_cds_pattern_observed", "lambda_label_recoverable",
        "bounded_lineardesign_pair_table_ready_pending_verifier",
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
