#!/usr/bin/env python3
"""Independent RNARL QC verifier; deliberately does not import production code."""

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
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

STOPS = {"TAA", "TAG", "TGA"}
COLUMNS = ["Protein_ID", "Protein_Sequence", "Protein_Length", "CDS_Sequence", "CDS_Length", "CDS_Structure", "CDS_MFE", "CDS_CAI"]
CODE = {}
for _codon, _aa in zip(
    [a + b + c for a in "TCAG" for b in "TCAG" for c in "TCAG"],
    "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG",
):
    CODE[_codon] = _aa


def file_hash(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def parse_int(value) -> Optional[int]:
    text = str(value).strip()
    return int(text) if re.fullmatch(r"[+-]?\d+", text) else None


def parse_float(value) -> Optional[float]:
    try:
        result = float(str(value).strip())
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def valid_structure(value: str) -> bool:
    stack = []
    match = {")": "(", "]": "[", "}": "{", ">": "<"}
    for char in value:
        if char == ".":
            continue
        if char in match.values():
            stack.append(char)
        elif char in match:
            if not stack or stack.pop() != match[char]:
                return False
        else:
            return False
    return not stack


def identity(filename: str) -> Tuple[str, str]:
    matched = re.fullmatch(r"(.+)_(train|val|test)\.csv", filename)
    if not matched:
        raise ValueError(filename)
    return matched.group(1), matched.group(2)


def independent_row(raw: Mapping[str, str], filename: str, row_number: int, lambda_column: Optional[str]) -> Dict[str, object]:
    organism, split = identity(filename)
    pid = str(raw.get("Protein_ID", "")).strip()
    protein = str(raw.get("Protein_Sequence", "")).strip().upper()
    source_cds = str(raw.get("CDS_Sequence", "")).strip().upper()
    cds = source_cds.replace("U", "T")
    structure = str(raw.get("CDS_Structure", "")).strip()
    target = protein[:-1] if protein.endswith("*") else protein
    plen = parse_int(raw.get("Protein_Length"))
    clen = parse_int(raw.get("CDS_Length"))
    mfe = parse_float(raw.get("CDS_MFE"))
    cai = parse_float(raw.get("CDS_CAI"))
    reasons = []
    if not pid: reasons.append("missing_protein_id")
    if not target: reasons.append("missing_protein_sequence")
    if not protein.endswith("*"): reasons.append("missing_protein_terminal_stop_symbol")
    if "*" in target: reasons.append("internal_protein_stop_symbol")
    if not source_cds: reasons.append("missing_cds")
    if set(source_cds) - set("ACGU"): reasons.append("non_acgu_cds")
    if len(cds) % 3: reasons.append("cds_length_not_divisible_by_3")
    if plen is None: reasons.append("invalid_reported_protein_length")
    elif plen != len(protein): reasons.append("protein_length_mismatch")
    if clen is None: reasons.append("invalid_reported_cds_length")
    elif clen != len(cds): reasons.append("cds_length_mismatch")
    if mfe is None: reasons.append("invalid_mfe")
    if cai is None: reasons.append("invalid_cai")
    elif not 0 <= cai <= 1: reasons.append("cai_outside_0_1")
    if len(structure) != len(cds): reasons.append("structure_length_mismatch")
    if not valid_structure(structure): reasons.append("structure_unbalanced_or_unsupported")
    start = terminal = internal = False
    translated = None
    if source_cds and len(source_cds) % 3 == 0 and not set(source_cds) - set("ACGU"):
        codons = [cds[i:i + 3] for i in range(0, len(cds), 3)]
        start = codons[0] == "ATG"
        terminal = codons[-1] in STOPS
        internal = any(codon in STOPS for codon in codons[:-1])
        aa = "".join(CODE[codon] for codon in codons)
        translated = aa[:-1] if terminal else aa
        if translated != target: reasons.append("translation_protein_mismatch")
    if cds and not start: reasons.append("start_not_atg")
    if cds and not terminal: reasons.append("missing_terminal_stop")
    if internal: reasons.append("internal_stop")
    coding = cds[:-3] if terminal else cds
    return {
        "record_id": f"{filename}:{row_number:06d}", "source_file": filename,
        "source_row_number": row_number, "organism": organism, "split": split,
        "protein_id": pid, "protein_sequence": protein, "protein_length": len(target),
        "protein_terminal_stop_symbol": protein.endswith("*"),
        "source_cds_rna": source_cds, "source_alphabet": "RNA",
        "cds_dna": cds, "cds_length_nt": len(cds), "cds_structure": structure,
        "reported_protein_length": plen, "reported_cds_length": clen,
        "reported_mfe_kcal_mol": mfe, "reported_cai": cai,
        "reported_lambda": str(raw.get(lambda_column, "")).strip() if lambda_column else None,
        "translated_protein": translated, "start_atg": start, "terminal_stop": terminal,
        "internal_stop": internal,
        "gc_fraction_full_cds": (cds.count("G") + cds.count("C")) / len(cds) if cds else None,
        "gc_fraction_coding": (coding.count("G") + coding.count("C")) / len(coding) if coding else None,
        "protein_sha256": text_hash(protein), "cds_sha256": text_hash(cds),
        "base_exclusion_reasons": reasons, "base_qc_pass": not reasons,
    }


def distribution(values: List[float]) -> Dict[str, object]:
    values = sorted(values)
    if not values:
        return {"n": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None}
    def q(f):
        x = (len(values) - 1) * f
        lo, hi = math.floor(x), math.ceil(x)
        return values[lo] if lo == hi else values[lo] * (hi - x) + values[hi] * (x - lo)
    return {"n": len(values), "min": values[0], "p25": q(.25), "median": q(.5),
            "p75": q(.75), "max": values[-1], "mean": statistics.fmean(values)}


def write_audit(path: Path, report: Mapping[str, object]) -> None:
    if path.exists():
        raise RuntimeError(f"refusing to overwrite audit: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + f".part.{os.getpid()}")
    part.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(part, path)


def verify(config_path: Path, raw_dir: Path, qc_dir: Path, audit_path: Path,
           production_script: Optional[Path] = None) -> Dict[str, object]:
    checks: List[Dict[str, object]] = []
    def add(name, ok, detail=""):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})
    expected: List[Dict[str, object]] = []
    expected_files: Dict[str, Dict[str, object]] = {}
    groups_by_file = {}
    raw_errors = []
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source = next(item for item in config["sources"] if item["source_id"] == "rnarl_v1")
    csv.field_size_limit(100_000_000)
    for spec in source["files"]:
        filename = spec["filename"]
        path = raw_dir / filename
        try:
            md5 = file_hash(path, "md5")
            if md5.lower() != spec["expected_md5"].lower():
                raise ValueError(f"MD5 {md5} != {spec['expected_md5']}")
            organism, split = identity(filename)
            file_info = {"filename": filename, "organism": organism, "split": split,
                         "bytes": path.stat().st_size, "md5": md5, "sha256": file_hash(path),
                         "rows": 0, "base_qc_pass_rows": 0, "pair_groups": 0,
                         "pair_structure_pass_groups": 0, "pair_pass_groups": 0,
                         "lambda_label_column": None, "lambda_01_pairs": 0}
            groups = defaultdict(list)
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                headers = list(reader.fieldnames or [])
                if any(column not in headers for column in COLUMNS):
                    raise ValueError("required header missing")
                lambda_column = next((column for column in headers if "lambda" in column.lower()), None)
                file_info["lambda_label_column"] = lambda_column
                for row_number, raw in enumerate(reader, 1):
                    row = independent_row(raw, filename, row_number, lambda_column)
                    key = row["protein_id"] if row["protein_id"] else f"__missing_{row_number}"
                    groups[key].append(row)
                    expected.append(row)
            pair_delta_values = defaultdict(list)
            for key, rows in groups.items():
                same = len({row["protein_sequence"] for row in rows}) == 1
                distinct = len({row["cds_dna"] for row in rows}) == len(rows)
                structure_pass = len(rows) == 2 and same and distinct
                base_pass = all(row["base_qc_pass"] for row in rows)
                lambda01 = len(rows) == 2 and {row["reported_lambda"] for row in rows} == {"0", "1"}
                for member, row in enumerate(rows, 1):
                    pair_reasons = []
                    if len(rows) != 2: pair_reasons.append("pair_group_size_not_2")
                    if not same: pair_reasons.append("pair_protein_sequence_mismatch")
                    if not distinct: pair_reasons.append("pair_identical_cds")
                    if not base_pass: pair_reasons.append("pair_member_base_qc_failed")
                    row.update({"pair_id": filename + ":" + text_hash(key)[:24], "pair_member_index": member, "pair_group_size": len(rows),
                                "pair_same_protein_sequence": same, "pair_distinct_cds": distinct,
                                "pair_structure_pass": structure_pass, "pair_lambda_01_recoverable": lambda01,
                                "pair_pass": structure_pass and base_pass,
                                "pair_exclusion_reasons": pair_reasons})
                file_info["pair_groups"] += 1
                file_info["pair_structure_pass_groups"] += int(structure_pass)
                file_info["pair_pass_groups"] += int(structure_pass and base_pass)
                file_info["lambda_01_pairs"] += int(lambda01)
                if len(rows) == 2:
                    if rows[0]["reported_mfe_kcal_mol"] is not None and rows[1]["reported_mfe_kcal_mol"] is not None:
                        pair_delta_values["absolute_mfe_difference"].append(abs(rows[0]["reported_mfe_kcal_mol"] - rows[1]["reported_mfe_kcal_mol"]))
                    if rows[0]["reported_cai"] is not None and rows[1]["reported_cai"] is not None:
                        pair_delta_values["absolute_cai_difference"].append(abs(rows[0]["reported_cai"] - rows[1]["reported_cai"]))
            file_info["rows"] = len(expected) - sum(int(item["rows"]) for item in expected_files.values())
            file_info["base_qc_pass_rows"] = sum(row["base_qc_pass"] for rows in groups.values() for row in rows)
            file_info["rows_per_protein_group_distribution"] = dict(Counter(str(len(rows)) for rows in groups.values()))
            file_info["pair_delta_distributions"] = {key: distribution(values) for key, values in pair_delta_values.items()}
            groups_by_file[filename] = groups
            expected_files[filename] = file_info
        except Exception as exc:
            raw_errors.append(f"{filename}: {type(exc).__name__}: {exc}")
    add("raw_hash_header_translation", not raw_errors, raw_errors[:20])

    pid_index = defaultdict(set); protein_index = defaultdict(set); cds_index = defaultdict(set)
    for row in expected:
        if row["protein_id"]: pid_index[(row["organism"], row["protein_id"])].add(row["split"])
        if row["protein_sequence"]: protein_index[(row["organism"], row["protein_sequence"])].add(row["split"])
        if row["cds_dna"]: cds_index[row["cds_dna"]].add(row["split"])
    def overlap_flags(row):
        return (
            bool(row["protein_id"]) and len(pid_index[(row["organism"], row["protein_id"])]) > 1,
            bool(row["protein_sequence"]) and len(protein_index[(row["organism"], row["protein_sequence"])]) > 1,
            bool(row["cds_dna"]) and len(cds_index[row["cds_dna"]]) > 1,
        )
    pair_flags = {}
    for groups in groups_by_file.values():
        for rows in groups.values():
            flags = [overlap_flags(row) for row in rows]
            pair_flags[rows[0]["pair_id"]] = tuple(any(flag[index] for flag in flags) for index in range(3))
    expected_clean_ids = []
    clean_values = {name: defaultdict(list) for name in expected_files}
    for row in expected:
        flags = overlap_flags(row)
        pair_overlap = pair_flags[row["pair_id"]]
        overlap_reasons = [label for flag, label in zip(flags, ("cross_split_protein_id", "cross_split_protein_sequence", "cross_split_exact_cds")) if flag]
        if any(pair_overlap) and not any(flags):
            overlap_reasons.append("pair_member_cross_split_overlap")
        row["pair_cross_split_overlap"] = any(pair_overlap)
        row["clean_eligible"] = row["pair_pass"] and not any(pair_overlap)
        row["expected_reasons"] = set(row["base_exclusion_reasons"] + row["pair_exclusion_reasons"] + overlap_reasons)
        if row["clean_eligible"]:
            expected_clean_ids.append(row["record_id"])
            expected_files[row["source_file"]].setdefault("clean_rows", 0)
            expected_files[row["source_file"]]["clean_rows"] += 1
            for metric in ("protein_length", "cds_length_nt", "gc_fraction_full_cds", "reported_cai", "reported_mfe_kcal_mol"):
                if row[metric] is not None: clean_values[row["source_file"]][metric].append(float(row[metric]))
    for name, info in expected_files.items():
        info.setdefault("clean_rows", 0)
        info["clean_pair_rows_even"] = info["clean_rows"] % 2 == 0
        info["clean_distributions"] = {metric: distribution(values) for metric, values in clean_values[name].items()}

    max_delta = 0.0; row_errors = []; actual_ids = []
    direct_fields = ["record_id", "source_file", "source_row_number", "organism", "split", "protein_id",
                     "protein_sequence", "protein_length", "protein_terminal_stop_symbol", "source_cds_rna", "source_alphabet",
                     "cds_dna", "cds_length_nt", "cds_structure",
                     "reported_protein_length", "reported_cds_length", "reported_mfe_kcal_mol", "reported_cai",
                     "reported_lambda", "translated_protein", "start_atg", "terminal_stop", "internal_stop",
                     "protein_sha256", "cds_sha256", "base_qc_pass", "pair_group_size", "pair_structure_pass",
                     "pair_lambda_01_recoverable", "pair_pass", "pair_cross_split_overlap", "clean_eligible"]
    try:
        with gzip.open(qc_dir / "rnarl_all_qc.jsonl.gz", "rt", encoding="utf-8") as handle:
            actual = [json.loads(line) for line in handle]
        if len(actual) != len(expected): row_errors.append(f"row count {len(actual)} != {len(expected)}")
        for index, (want, got) in enumerate(zip(expected, actual)):
            actual_ids.append(got.get("record_id"))
            for field in direct_fields:
                if want[field] != got.get(field):
                    row_errors.append(f"{index}:{field}: {got.get(field)!r} != {want[field]!r}")
                    break
            for metric in ("gc_fraction_full_cds", "gc_fraction_coding"):
                left, right = want[metric], got.get(metric)
                if (left is None) != (right is None): row_errors.append(f"{index}:{metric}:null mismatch")
                elif left is not None: max_delta = max(max_delta, abs(left - right))
            if set(got.get("exclusion_reasons", [])) != want["expected_reasons"]:
                row_errors.append(f"{index}:exclusion reasons differ")
            if len(row_errors) >= 100: break
    except Exception as exc:
        row_errors.append(f"{type(exc).__name__}: {exc}")
    add("all_qc_independent_recompute", not row_errors, row_errors[:100])

    clean_errors = []
    try:
        with gzip.open(qc_dir / "rnarl_clean.jsonl.gz", "rt", encoding="utf-8") as handle:
            clean_actual = [json.loads(line) for line in handle]
        clean_ids = [row["record_id"] for row in clean_actual]
        if clean_ids != expected_clean_ids: clean_errors.append("clean ordered record IDs differ")
        if any(not row.get("clean_eligible") for row in clean_actual): clean_errors.append("ineligible clean row")
    except Exception as exc:
        clean_errors.append(f"{type(exc).__name__}: {exc}")
    add("clean_artifact_exact_set", not clean_errors, clean_errors)

    summary = json.loads((qc_dir / "qc_summary.json").read_text(encoding="utf-8"))
    expected_total_pairs = sum(info["pair_groups"] for info in expected_files.values())
    expected_structure_pairs = sum(info["pair_structure_pass_groups"] for info in expected_files.values())
    expected_pair_pass = sum(info["pair_pass_groups"] for info in expected_files.values())
    count_expectations = {
        "expected_file_count": len(source["files"]), "processed_file_count": len(expected_files),
        "total_rows": len(expected), "clean_rows": len(expected_clean_ids),
        "clean_pairs": len(expected_clean_ids) // 2, "pair_groups": expected_total_pairs,
        "pair_structure_pass_groups": expected_structure_pairs, "pair_pass_groups": expected_pair_pass,
    }
    count_errors = [f"{key}: {summary.get(key)} != {value}" for key, value in count_expectations.items() if summary.get(key) != value]
    file_errors = []
    compare_file_fields = ["bytes", "md5", "sha256", "rows", "base_qc_pass_rows", "pair_groups",
                           "pair_structure_pass_groups", "pair_pass_groups", "lambda_label_column",
                           "lambda_01_pairs", "clean_rows", "clean_pair_rows_even",
                           "rows_per_protein_group_distribution"]
    actual_files = {item["filename"]: item for item in summary.get("files", []) if item.get("status") == "processed"}
    for name, want in expected_files.items():
        got = actual_files.get(name, {})
        for field in compare_file_fields:
            if want[field] != got.get(field): file_errors.append(f"{name}:{field}")
        for section in ("clean_distributions", "pair_delta_distributions"):
            for metric, values in want[section].items():
                target = got.get(section, {}).get(metric, {})
                for statistic, value in values.items():
                    other = target.get(statistic)
                    if value is None or other is None:
                        if value != other: file_errors.append(f"{name}:{section}:{metric}:{statistic}")
                    elif isinstance(value, int):
                        if value != other: file_errors.append(f"{name}:{section}:{metric}:{statistic}")
                    else:
                        max_delta = max(max_delta, abs(value - other))
    add("summary_counts_and_file_lineage", not count_errors and not file_errors,
        {"count_errors": count_errors, "file_errors": file_errors[:100], "max_numeric_delta": max_delta})

    expected_overlaps = {
        "protein_id": sum(len(value) > 1 for value in pid_index.values()),
        "protein_sequence": sum(len(value) > 1 for value in protein_index.values()),
        "exact_cds": sum(len(value) > 1 for value in cds_index.values()),
    }
    overlap_errors = [f"{kind}: {summary.get('split_overlaps', {}).get(kind, {}).get('overlapping_keys')} != {count}"
                      for kind, count in expected_overlaps.items()
                      if summary.get("split_overlaps", {}).get(kind, {}).get("overlapping_keys") != count]
    add("split_overlap_recompute", not overlap_errors, overlap_errors)

    expected_long_format = expected_total_pairs > 0 and expected_structure_pairs == expected_total_pairs
    expected_lambda = bool(expected_files) and all(info["lambda_label_column"] and info["lambda_01_pairs"] == info["pair_groups"] for info in expected_files.values())
    scope_expectations = {
        "status": "COMPLETE_QC_PENDING_INDEPENDENT_VERIFICATION",
        "long_format_two_distinct_cds_pattern_observed": expected_long_format,
        "lambda_label_recoverable": expected_lambda,
        "row_order_or_mfe_lambda_assignment_allowed": False,
        "lineardesign_provenance_independently_validated": False,
        "natural_cds_source_validated": False, "natural_distribution_eligible": False,
        "bounded_lineardesign_pair_table_ready_pending_verifier": len(expected_files) == len(source["files"]) and bool(expected_clean_ids),
        "raw_split_overlap_detected": any(expected_overlaps.values()),
        "clean_pair_level_leakage_exclusion_applied": True,
        "lambda_stratified_analysis_ready": False, "functional_training_authorized": False,
        "functional_ood_claim_authorized": False,
    }
    scope_errors = [f"{key}: {summary.get(key)} != {value}" for key, value in scope_expectations.items() if summary.get(key) != value]
    add("scientific_scope_and_lambda_boundary", not scope_errors, scope_errors)

    manifest_errors = []
    try:
        manifest = json.loads((qc_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        for name in ("rnarl_all_qc.jsonl.gz", "rnarl_clean.jsonl.gz", "qc_summary.json"):
            path = qc_dir / name
            recorded = manifest["outputs"][name]
            if recorded["bytes"] != path.stat().st_size or recorded["sha256"] != file_hash(path):
                manifest_errors.append(name)
    except Exception as exc:
        manifest_errors.append(f"{type(exc).__name__}: {exc}")
    add("artifact_manifest_sha256", not manifest_errors, manifest_errors)

    add("expected_21_file_completion", len(expected_files) == len(source["files"]) == 21,
        {"verified": len(expected_files), "registered": len(source["files"])})
    report = {
        "schema_version": "a8-rk03-rnarl-independent-verification-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(check["pass"] for check in checks) else "FAIL",
        "independent_production_import": False,
        "checks": checks, "passed_checks": sum(check["pass"] for check in checks),
        "check_count": len(checks), "max_numeric_delta": max_delta,
        "recomputed": {"rows": len(expected), "clean_rows": len(expected_clean_ids),
                       "clean_pairs": len(expected_clean_ids) // 2, "overlap_keys": expected_overlaps},
        "artifacts": {name: file_hash(qc_dir / name) for name in ("rnarl_all_qc.jsonl.gz", "rnarl_clean.jsonl.gz", "qc_summary.json", "artifact_manifest.json") if (qc_dir / name).is_file()},
        "production_script_sha256": file_hash(production_script) if production_script else None,
        "scope": "Independent QC only; no natural-CDS, lambda-order, functional-OOD, or SOTA authorization.",
    }
    write_audit(audit_path, report)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--qc-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--production-script", type=Path)
    args = parser.parse_args(argv)
    report = verify(args.config, args.raw_dir, args.qc_dir, args.audit, args.production_script)
    print(json.dumps({"status": report["status"], "passed_checks": report["passed_checks"],
                      "check_count": report["check_count"], "max_numeric_delta": report["max_numeric_delta"]}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
