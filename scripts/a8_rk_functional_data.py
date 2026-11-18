#!/usr/bin/env python3
"""Download and audit A8-RK public functional data without third-party packages."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
from collections import Counter, defaultdict
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

USER_AGENT = "CodonFlow-A8-RK-public-data-audit/1.0"
NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


class DataValidationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def looks_like_html(prefix: bytes) -> bool:
    text = prefix.decode("utf-8", errors="ignore").lstrip().lower()
    return (
        text.startswith("<!doctype html")
        or text.startswith("<html")
        or "<html" in text[:2048]
        or "preparing to download" in text[:4096]
        or "cloudflare" in text[:4096] and "<body" in text[:4096]
    )


def validate_payload(path: Path, media_type: str) -> None:
    if not path.is_file():
        raise DataValidationError(f"missing payload: {path}")
    size = path.stat().st_size
    if size < 16:
        raise DataValidationError(f"payload too small: {size} bytes")
    with path.open("rb") as handle:
        prefix = handle.read(8192)
    if looks_like_html(prefix):
        raise DataValidationError("HTML/challenge page received instead of data")
    kind = media_type.lower()
    if kind == "application/pdf" and not prefix.startswith(b"%PDF"):
        raise DataValidationError("PDF magic header not found")
    if kind.endswith("spreadsheetml.sheet"):
        if not prefix.startswith(b"PK\x03\x04") or not zipfile.is_zipfile(path):
            raise DataValidationError("invalid XLSX ZIP container")
        with zipfile.ZipFile(path) as archive:
            if "xl/workbook.xml" not in archive.namelist():
                raise DataValidationError("XLSX workbook.xml not found")
    elif kind in {"text/csv", "text/plain", "text/tab-separated-values"}:
        try:
            text = prefix.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = prefix.decode("latin-1")
        if "\x00" in text or not text.strip():
            raise DataValidationError("empty or binary text payload")
        if kind == "text/csv" and not any(mark in text for mark in (",", "\t", ";")):
            raise DataValidationError("CSV delimiter not found in first block")


def download_file(
    url: str,
    destination: Path,
    media_type: str,
    timeout: float = 60.0,
    retries: int = 3,
    refresh: bool = False,
) -> Dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not refresh:
        validate_payload(destination, media_type)
        return {
            "status": "reused",
            "path": str(destination),
            "bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
            "attempts": 0,
        }
    last_error: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        temporary = destination.with_name(destination.name + f".part.{os.getpid()}")
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", None)
                response_type = response.headers.get("Content-Type")
                with temporary.open("wb") as handle:
                    shutil.copyfileobj(response, handle, length=1024 * 1024)
            validate_payload(temporary, media_type)
            os.replace(temporary, destination)
            return {
                "status": "downloaded",
                "path": str(destination),
                "bytes": destination.stat().st_size,
                "sha256": sha256_file(destination),
                "attempts": attempt,
                "http_status": status,
                "response_content_type": response_type,
            }
        except (OSError, urllib.error.URLError, DataValidationError, zipfile.BadZipFile) as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(min(2 ** (attempt - 1), 4))
    raise DataValidationError(
        f"download failed after {retries} attempts: {type(last_error).__name__}: {last_error}"
    )


def _xml_path(root: ET.Element, tag: str) -> str:
    return f"{{{NS_MAIN}}}{tag}"


def _column_index(reference: str) -> int:
    match = re.match(r"([A-Z]+)", reference.upper())
    if not match:
        raise DataValidationError(f"invalid spreadsheet cell reference: {reference}")
    result = 0
    for char in match.group(1):
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def read_xlsx_sheets(path: Path) -> Dict[str, List[List[str]]]:
    """Read ordinary worksheet values, including shared and inline strings."""
    with zipfile.ZipFile(path) as archive:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(_xml_path(root, "si")):
                shared.append("".join(node.text or "" for node in item.iter(_xml_path(root, "t"))))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in relationships.findall(f"{{{NS_REL_PKG}}}Relationship")
        }
        sheets: Dict[str, List[List[str]]] = {}
        for sheet in workbook.findall(f".//{_xml_path(workbook, 'sheet')}"):
            name = sheet.attrib["name"]
            relationship_id = sheet.attrib[f"{{{NS_REL_DOC}}}id"]
            target = targets[relationship_id]
            if target.startswith("/"):
                member = target.lstrip("/")
            else:
                member = str(PurePosixPath("xl") / target)
            root = ET.fromstring(archive.read(member))
            rows: List[List[str]] = []
            for row in root.findall(f".//{_xml_path(root, 'row')}"):
                values: List[str] = []
                for cell in row.findall(_xml_path(root, "c")):
                    index = _column_index(cell.attrib.get("r", "A1"))
                    while len(values) <= index:
                        values.append("")
                    cell_type = cell.attrib.get("t", "n")
                    if cell_type == "inlineStr":
                        value = "".join(
                            node.text or "" for node in cell.iter(_xml_path(root, "t"))
                        )
                    else:
                        value_node = cell.find(_xml_path(root, "v"))
                        value = "" if value_node is None or value_node.text is None else value_node.text
                        if cell_type == "s" and value:
                            shared_index = int(value)
                            if shared_index >= len(shared):
                                raise DataValidationError("shared string index out of range")
                            value = shared[shared_index]
                        elif cell_type == "b" and value:
                            value = "TRUE" if value == "1" else "FALSE"
                    values[index] = value
                rows.append(values)
            sheets[name] = rows
        return sheets


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def rows_as_dicts(rows: Sequence[Sequence[str]], header_row: int = 0) -> Tuple[List[str], List[Dict[str, str]]]:
    if header_row >= len(rows):
        raise DataValidationError("header row outside worksheet")
    headers = [str(value).strip() for value in rows[header_row]]
    if not any(headers):
        raise DataValidationError("empty table header")
    records: List[Dict[str, str]] = []
    for values in rows[header_row + 1 :]:
        padded = list(values) + [""] * max(0, len(headers) - len(values))
        record = {headers[index]: str(padded[index]).strip() for index in range(len(headers)) if headers[index]}
        if any(record.values()):
            records.append(record)
    return headers, records


def read_csv_records(path: Path, delimiter: str = ",") -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise DataValidationError(f"CSV header missing: {path}")
        records = [
            {str(key).strip(): (value or "").strip() for key, value in row.items() if key is not None}
            for row in reader
        ]
        return [name.strip() for name in reader.fieldnames], records


def safe_raw_name(file_id: str, url: str, media_type: str) -> str:
    suffix = PurePosixPath(url.split("?", 1)[0]).suffix
    if not suffix:
        suffix = {
            "application/pdf": ".pdf",
            "text/csv": ".csv",
            "text/plain": ".txt",
            "text/tab-separated-values": ".txt",
        }.get(media_type, ".bin")
    return file_id + suffix


def download_priority_one(config_path: Path, data_root: Path, refresh: bool = False) -> Dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    records: List[Dict[str, object]] = []
    failures: List[Dict[str, object]] = []
    for source in config["sources"]:
        if source.get("priority") != 1:
            continue
        for file_spec in source.get("files", []):
            media_type = file_spec["media_type"]
            relative = Path("raw") / source["source_id"] / safe_raw_name(
                file_spec["file_id"], file_spec["url"], media_type
            )
            destination = data_root / relative
            record: Dict[str, object] = {
                "source_id": source["source_id"],
                "file_id": file_spec["file_id"],
                "role": file_spec.get("role", ""),
                "required": bool(file_spec.get("required", False)),
                "url": file_spec["url"],
                "expected_media_type": media_type,
                "relative_path": str(relative),
            }
            try:
                result = download_file(
                    file_spec["url"], destination, media_type, refresh=refresh
                )
                record.update(result)
                record["path"] = str(relative)
            except Exception as exc:  # failure evidence is a required output
                record.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
                failures.append(dict(record))
            records.append(record)
    return {
        "schema_version": "a8-rk-download-manifest-v1",
        "created_at": utc_now(),
        "config": str(config_path),
        "data_root": str(data_root),
        "records": records,
        "failures": failures,
        "status": "partial" if failures else "complete",
    }


def write_download_outputs(manifest: Mapping[str, object], audit_dir: Path) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "download_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    failures = manifest["failures"]
    fields = [
        "source_id", "file_id", "required", "url", "relative_path",
        "expected_media_type", "status", "error",
    ]
    with (audit_dir / "download_failures.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(failures)


GENETIC_CODE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}

LONG_FIELDS = [
    "source_id", "dataset_id", "source_file", "source_row", "protein_id",
    "protein_family", "construct_id", "mutation_signature", "record_class",
    "variant_class", "sequence_status", "cds", "protein_sequence",
    "codon_position", "wt_codon", "mutant_codon", "amino_acid",
    "expression_type", "expression_value", "expression_stdev", "protocol_id",
    "host", "vector", "medium", "temperature_c", "induction_time", "replicate",
    "split_unit", "split_assignment", "leakage_risk", "features_json",
]


def translate_codon(codon: str) -> str:
    return GENETIC_CODE.get(codon.strip().upper(), "?")


def translate_dna(sequence: str) -> str:
    return "".join(translate_codon(sequence[index:index + 3]) for index in range(0, len(sequence), 3))


def finite_number(value: str) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise DataValidationError(f"invalid numeric value: {value!r}") from exc
    if not math.isfinite(number):
        raise DataValidationError(f"non-finite numeric value: {value!r}")
    return number


def blank_long_row() -> Dict[str, object]:
    return {field: "" for field in LONG_FIELDS}


def write_csv_atomic(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def artifact_record(path: Path, data_root: Path, rows: int) -> Dict[str, object]:
    return {
        "path": str(path.relative_to(data_root)),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "rows": rows,
    }


def audit_boel_records(
    records: Sequence[Mapping[str, str]], source_file: str
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], Dict[str, object]]:
    clean: List[Dict[str, object]] = []
    exclusions: List[Dict[str, object]] = []
    seen_exact = set()
    name_counts = Counter(str(record.get("name", "")).strip() for record in records)
    sequence_counts = Counter(str(record.get("seq", "")).strip().upper() for record in records)
    expression_counts: Counter = Counter()
    lengths: List[int] = []
    for index, record in enumerate(records, start=2):
        name = str(record.get("name", "")).strip()
        expression = str(record.get("E", "")).strip()
        sequence = str(record.get("seq", "")).strip().upper()
        exact_key = (name, expression, sequence)
        try:
            if not name or not expression or not sequence:
                raise DataValidationError("missing name, E or seq")
            if exact_key in seen_exact:
                raise DataValidationError("exact duplicate row")
            seen_exact.add(exact_key)
            score = int(expression)
            if str(score) != expression or not 0 <= score <= 5:
                raise DataValidationError("E is not an integer in 0..5")
            if not re.fullmatch(r"[ACGT]+", sequence):
                raise DataValidationError("CDS contains non-ACGT symbols")
            if len(sequence) % 3:
                raise DataValidationError("CDS length is not divisible by 3")
            if not sequence.startswith("ATG"):
                raise DataValidationError("CDS does not start with ATG")
            protein = translate_dna(sequence)
            if not protein.endswith("*"):
                raise DataValidationError("terminal stop codon missing")
            if "*" in protein[:-1]:
                raise DataValidationError("internal stop codon")
            row = blank_long_row()
            row.update({
                "source_id": "boel_2016_nesg6348",
                "dataset_id": "protein_dataset_xlsx",
                "source_file": source_file,
                "source_row": index,
                "protein_id": name,
                "protein_family": "not_provided_in_supplementary_data_2",
                "construct_id": f"boel:{name}",
                "record_class": "heterologous_protein_expression",
                "variant_class": "cross_protein_natural_nonsynonymous_pool",
                "sequence_status": "full_cds_with_terminal_stop_and_c_terminal_tag",
                "cds": sequence,
                "protein_sequence": protein[:-1],
                "expression_type": "ordinal_total_protein_expression_score_0_5",
                "expression_value": score,
                "protocol_id": "boel_2016_t7_pet_defined_medium_18c",
                "host": "Escherichia coli BL21(DE3) with pMGK-argU",
                "vector": "pET plasmid; T7 RNA polymerase; C-terminal LEHHHHHH",
                "medium": "defined medium (exact formulation not in Supplementary Data 2)",
                "temperature_c": "18",
                "induction_time": "overnight",
                "replicate": "two isolates summarized by E; isolate-level values not supplied",
                "split_unit": "protein_family_plus_recombined_construct",
                "split_assignment": "UNASSIGNED_FAMILY_MAP_REQUIRED",
                "leakage_risk": (
                    "not a fixed-protein synonymous library; family mapping absent"
                    + ("; duplicate CDS across names" if sequence_counts[sequence] > 1 else "")
                    + ("; duplicate name" if name_counts[name] > 1 else "")
                ),
                "features_json": json.dumps({
                    "Gz48v": record.get("Gz48v", ""),
                    "Gave96": record.get("Gave96", ""),
                    "Gave48": record.get("Gave48", ""),
                    "Gave144": record.get("Gave144", ""),
                }, sort_keys=True),
            })
            clean.append(row)
            expression_counts[str(score)] += 1
            lengths.append(len(sequence))
        except DataValidationError as exc:
            exclusions.append({
                "source_id": "boel_2016_nesg6348", "dataset_id": "protein_dataset_xlsx",
                "source_row": index, "raw_key": name, "reason": str(exc),
            })
    summary = {
        "raw_rows": len(records), "clean_rows": len(clean), "excluded_rows": len(exclusions),
        "unique_names": len({row["protein_id"] for row in clean}),
        "unique_cds": len({row["cds"] for row in clean}),
        "duplicate_name_groups": sum(count > 1 for name, count in name_counts.items() if name),
        "duplicate_cds_groups": sum(count > 1 for seq, count in sequence_counts.items() if seq),
        "expression_distribution": dict(sorted(expression_counts.items())),
        "min_cds_nt": min(lengths) if lengths else None,
        "max_cds_nt": max(lengths) if lengths else None,
        "design": "cross-protein heterologous expression, not a within-protein synonymous library",
    }
    return clean, exclusions, summary


def mage_base(source_file: str, source_row: int, dataset_id: str) -> Dict[str, object]:
    row = blank_long_row()
    row.update({
        "source_id": "kelsic_2016_mage_seq", "dataset_id": dataset_id,
        "source_file": source_file, "source_row": source_row,
        "protein_id": "infA", "protein_family": "infA",
        "sequence_status": "variant_only_full_construct_sequence_not_in_supplement",
        "protocol_id": "kelsic_2016_mage_seq_growth_selection",
        "host": "Escherichia coli chromosomal infA",
        "vector": "chromosomal MAGE; no secreted-expression vector",
        "temperature_c": "", "induction_time": "growth-selection time course; source summary fitness",
        "replicate": "source summary with standard deviation",
        "split_unit": "fixed_protein_family_infA_plus_construct",
        "split_assignment": "UNASSIGNED_FIXED_INFA_FAMILY_REQUIRED",
        "leakage_risk": "all constructs share infA; random row split forbidden; overlapping pair/single constructs",
    })
    return row


def audit_mage_single(
    records: Sequence[Mapping[str, str]], source_file: str
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], Dict[str, object]]:
    exclusions: List[Dict[str, object]] = []
    valid: List[Tuple[int, Mapping[str, str]]] = []
    wt_by_position: Dict[int, str] = {}
    for index, record in enumerate(records, start=2):
        try:
            position = int(str(record.get("pos", "")).strip())
            codon = str(record.get("codon", "")).strip().upper()
            aa = str(record.get("aa", "")).strip().upper()
            is_wt = str(record.get("is_wt", "")).strip()
            if len(codon) != 3 or not re.fullmatch(r"[ACGT]{3}", codon):
                raise DataValidationError("invalid codon")
            if translate_codon(codon) != aa:
                raise DataValidationError("codon/amino-acid mismatch")
            if is_wt not in {"0", "1"}:
                raise DataValidationError("is_wt is not 0/1")
            for field in ("fitness_min", "fitness_rich", "fitness_stdev_min", "fitness_stdev_rich"):
                finite_number(record.get(field, ""))
            if is_wt == "1":
                if position in wt_by_position and wt_by_position[position] != codon:
                    raise DataValidationError("conflicting WT codons at position")
                wt_by_position[position] = codon
            valid.append((index, record))
        except (ValueError, DataValidationError) as exc:
            exclusions.append({"source_id": "kelsic_2016_mage_seq", "dataset_id": "data_s1_single_codon_csv",
                               "source_row": index, "raw_key": str(record), "reason": str(exc)})
    clean: List[Dict[str, object]] = []
    seen = set()
    signatures = set()
    for index, record in valid:
        position = int(record["pos"].strip())
        codon = record["codon"].strip().upper()
        is_wt = record["is_wt"].strip() == "1"
        wt = wt_by_position.get(position)
        key = (position, codon)
        if wt is None:
            exclusions.append({"source_id": "kelsic_2016_mage_seq", "dataset_id": "data_s1_single_codon_csv",
                               "source_row": index, "raw_key": key, "reason": "WT codon missing at position"})
            continue
        if key in seen:
            exclusions.append({"source_id": "kelsic_2016_mage_seq", "dataset_id": "data_s1_single_codon_csv",
                               "source_row": index, "raw_key": key, "reason": "duplicate position/codon"})
            continue
        seen.add(key)
        signature = "" if is_wt else f"{position}:{wt}>{codon}"
        if signature:
            signatures.add(signature)
        for suffix, expression_type, medium in (
            ("min", "relative_fitness_minimal", "MOPS minimal"),
            ("rich", "relative_fitness_rich", "MOPS rich"),
        ):
            row = mage_base(source_file, index, "data_s1_single_codon_csv")
            row.update({
                "construct_id": f"infA:single:{signature or str(position) + ':WT'}",
                "mutation_signature": signature,
                "record_class": "wild_type_control" if is_wt else "single_codon_variant",
                "variant_class": "wild_type_control" if is_wt else (
                    "synonymous_single_codon" if translate_codon(wt) == translate_codon(codon) else "nonsynonymous_single_codon"
                ),
                "codon_position": position, "wt_codon": wt, "mutant_codon": codon,
                "amino_acid": record["aa"].strip(), "expression_type": expression_type,
                "expression_value": record[f"fitness_{suffix}"].strip(),
                "expression_stdev": record[f"fitness_stdev_{suffix}"].strip(), "medium": medium,
                "features_json": json.dumps({"RCS": record.get("RCS", "").strip(),
                    "mfe_ddG_43nt_sliding": record.get("mfe_ddG_43nt_sliding", "").strip()}, sort_keys=True),
            })
            clean.append(row)
    summary = {
        "raw_rows": len(records), "clean_long_rows": len(clean), "excluded_rows": len(exclusions),
        "wild_type_controls": sum(row["record_class"] == "wild_type_control" and row["expression_type"] == "relative_fitness_rich" for row in clean),
        "single_codon_variants": len(signatures), "positions": len(wt_by_position),
        "codons_per_position": dict(Counter(int(record["pos"]) for _, record in valid)),
        "unique_position_codon_keys": len(seen), "unique_nonwt_mutation_signatures": len(signatures),
        "assays_per_construct": 2, "paper_reported_single_codon_variants": 4599,
        "matches_paper_variant_count": len(signatures) == 4599,
    }
    return clean, exclusions, summary


def audit_mage_pairs(
    records: Sequence[Mapping[str, str]], source_file: str
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], Dict[str, object]]:
    exclusions: List[Dict[str, object]] = []
    valid: List[Tuple[int, Mapping[str, str]]] = []
    wt_pairs: Dict[Tuple[int, int], Tuple[str, str]] = {}
    for index, record in enumerate(records, start=2):
        try:
            pos1, pos2 = int(record["pos1"].strip()), int(record["pos2"].strip())
            codon1, codon2 = record["codon1"].strip().upper(), record["codon2"].strip().upper()
            aa1, aa2 = record["aa1"].strip().upper(), record["aa2"].strip().upper()
            is_wt = record["is_wt"].strip()
            if translate_codon(codon1) != aa1 or translate_codon(codon2) != aa2:
                raise DataValidationError("codon/amino-acid mismatch")
            if is_wt not in {"0", "1"}:
                raise DataValidationError("is_wt is not 0/1")
            finite_number(record.get("fitness_rich", ""))
            finite_number(record.get("fitness_stdev_rich", ""))
            if is_wt == "1":
                wt_pairs[(pos1, pos2)] = (codon1, codon2)
            valid.append((index, record))
        except (KeyError, ValueError, DataValidationError) as exc:
            exclusions.append({"source_id": "kelsic_2016_mage_seq", "dataset_id": "data_s2_codon_pair_csv",
                               "source_row": index, "raw_key": str(record), "reason": str(exc)})
    clean: List[Dict[str, object]] = []
    seen = set()
    nonwt_signatures = set()
    signature_counts: Counter = Counter()
    for index, record in valid:
        pos1, pos2 = int(record["pos1"]), int(record["pos2"])
        codon1, codon2 = record["codon1"].strip().upper(), record["codon2"].strip().upper()
        wt1, wt2 = wt_pairs[(pos1, pos2)]
        key = (pos1, codon1, pos2, codon2)
        if key in seen:
            exclusions.append({"source_id": "kelsic_2016_mage_seq", "dataset_id": "data_s2_codon_pair_csv",
                               "source_row": index, "raw_key": key, "reason": "duplicate pair row"})
            continue
        seen.add(key)
        changes = []
        if codon1 != wt1:
            changes.append(f"{pos1}:{wt1}>{codon1}")
        if codon2 != wt2:
            changes.append(f"{pos2}:{wt2}>{codon2}")
        signature = ";".join(changes)
        is_wt = not changes
        if signature:
            nonwt_signatures.add(signature)
            signature_counts[signature] += 1
        row = mage_base(source_file, index, "data_s2_codon_pair_csv")
        row.update({
            "construct_id": f"infA:pair:{pos1}-{pos2}:{signature or 'WT'}",
            "mutation_signature": signature,
            "record_class": "wild_type_control" if is_wt else (
                "single_codon_variant_in_pair_assay" if len(changes) == 1 else "codon_pair_variant"
            ),
            "variant_class": "wild_type_control" if is_wt else (
                "single_codon_variant_in_pair_assay" if len(changes) == 1 else "codon_pair_variant"
            ),
            "codon_position": f"{pos1};{pos2}", "wt_codon": f"{wt1};{wt2}",
            "mutant_codon": f"{codon1};{codon2}", "amino_acid": f"{record['aa1'].strip()};{record['aa2'].strip()}",
            "expression_type": "relative_fitness_rich", "expression_value": record["fitness_rich"].strip(),
            "expression_stdev": record["fitness_stdev_rich"].strip(), "medium": "MOPS rich",
            "features_json": json.dumps({"mfe_ddG_100nt": record.get("mfe_ddG(100nt)", "").strip(),
                "RBS_calc": record.get("RBS_calc", "").strip(), "SD_like_ddG": record.get("SD-like-ddG", "").strip(),
                "RCS": record.get("RCS", "").strip()}, sort_keys=True),
        })
        clean.append(row)
    summary = {
        "raw_rows": len(records), "clean_long_rows": len(clean), "excluded_rows": len(exclusions),
        "wild_type_controls": sum(row["record_class"] == "wild_type_control" for row in clean),
        "raw_nonwt_rows": sum(bool(row["mutation_signature"]) for row in clean),
        "unique_nonwt_mutation_signatures": len(nonwt_signatures),
        "cross_window_duplicate_signature_rows": sum(count - 1 for count in signature_counts.values()),
        "single_codon_rows_in_pair_assay": sum(row["record_class"] == "single_codon_variant_in_pair_assay" for row in clean),
        "true_pair_variant_rows": sum(row["record_class"] == "codon_pair_variant" for row in clean),
        "paper_reported_pair_construct_count": 8127,
        "matches_paper_construct_count": len(nonwt_signatures) == 8127,
    }
    return clean, exclusions, summary


def audit_mage_utr(
    records: Sequence[Mapping[str, str]], source_file: str
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], Dict[str, object]]:
    clean: List[Dict[str, object]] = []
    exclusions: List[Dict[str, object]] = []
    seen = set()
    for index, record in enumerate(records, start=2):
        try:
            nt12, nt34 = record["nt12"].strip().upper(), record["nt34"].strip().upper()
            if not re.fullmatch(r"[ACGT]{2}", nt12) or not re.fullmatch(r"[ACGT]{2}", nt34):
                raise DataValidationError("invalid UTR dinucleotides")
            finite_number(record.get("f", "")); finite_number(record.get("f_std", ""))
            is_wt = record["is_wt"].strip()
            if is_wt not in {"0", "1"}:
                raise DataValidationError("is_wt is not 0/1")
            signature = f"UTR:{record['5prime_index'].strip()}:{record['3prime_index'].strip()}:{record['oligo_index'].strip()}:{nt12}:{nt34}"
            key = (record["replica"].strip(), signature)
            if key in seen:
                raise DataValidationError("duplicate replicate/construct row")
            seen.add(key)
            row = mage_base(source_file, index, "data_s3_utr_csv")
            row.update({
                "construct_id": f"infA:{signature}", "mutation_signature": "" if is_wt == "1" else signature,
                "record_class": "wild_type_control" if is_wt == "1" else "utr_hairpin_variant",
                "variant_class": "wild_type_control" if is_wt == "1" else "utr_hairpin_variant",
                "expression_type": "UTR_relative_fitness_rich", "expression_value": record["f"].strip(),
                "expression_stdev": record["f_std"].strip(), "medium": "MOPS rich",
                "replicate": record["replica"].strip(),
                "features_json": json.dumps({"5prime_index": record["5prime_index"].strip(),
                    "3prime_index": record["3prime_index"].strip(), "oligo_index": record["oligo_index"].strip(),
                    "nt12": nt12, "nt34": nt34, "num_mismatches": record["num_mismatches"].strip()}, sort_keys=True),
            })
            clean.append(row)
        except (KeyError, ValueError, DataValidationError) as exc:
            exclusions.append({"source_id": "kelsic_2016_mage_seq", "dataset_id": "data_s3_utr_csv",
                               "source_row": index, "raw_key": str(record), "reason": str(exc)})
    summary = {
        "raw_rows": len(records), "clean_long_rows": len(clean), "excluded_rows": len(exclusions),
        "unique_replicate_construct_keys": len(seen),
        "wild_type_controls": sum(row["record_class"] == "wild_type_control" for row in clean),
        "utr_variant_rows": sum(row["record_class"] == "utr_hairpin_variant" for row in clean),
    }
    return clean, exclusions, summary


def register_browser_downloads(
    manifest_path: Path, data_root: Path, audit_dir: Path, registrations: Sequence[Tuple[str, str, str]]
) -> Dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    resolved = list(manifest.get("resolved_failures", []))
    for source_id, file_id, method in registrations:
        matches = [record for record in manifest["records"]
                   if record["source_id"] == source_id and record["file_id"] == file_id]
        if len(matches) != 1:
            raise DataValidationError(f"registration does not match one file: {source_id}/{file_id}")
        record = matches[0]
        path = data_root / record["relative_path"]
        validate_payload(path, record["expected_media_type"])
        if record.get("status") == "failed":
            resolved.append({key: record.get(key) for key in
                             ("source_id", "file_id", "url", "relative_path", "status", "error")})
        record.update({
            "status": "browser_downloaded", "path": record["relative_path"],
            "bytes": path.stat().st_size, "sha256": sha256_file(path),
            "http_status": 200, "response_content_type": record["expected_media_type"],
            "download_method": method, "resolved_at": utc_now(),
        })
        record.pop("error", None)
    manifest["resolved_failures"] = resolved
    manifest["failures"] = [record for record in manifest["records"] if record.get("status") == "failed"]
    manifest["status"] = "partial" if manifest["failures"] else "complete"
    manifest["updated_at"] = utc_now()
    write_download_outputs(manifest, audit_dir)
    return manifest


def _record_path(manifest: Mapping[str, object], data_root: Path, file_id: str) -> Tuple[Dict[str, object], Path]:
    matches = [record for record in manifest["records"] if record["file_id"] == file_id]
    if len(matches) != 1 or matches[0].get("status") == "failed":
        raise DataValidationError(f"required raw file unavailable: {file_id}")
    record = matches[0]
    path = data_root / record["relative_path"]
    if sha256_file(path) != record["sha256"]:
        raise DataValidationError(f"raw SHA256 changed since download: {file_id}")
    return record, path


def audit_all(config_path: Path, data_root: Path, audit_dir: Path) -> Dict[str, object]:
    manifest_path = audit_dir / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_clean: List[Dict[str, object]] = []
    all_exclusions: List[Dict[str, object]] = []
    summaries: Dict[str, object] = {}
    artifacts: Dict[str, object] = {}

    boel_record, boel_path = _record_path(manifest, data_root, "protein_dataset_xlsx")
    sheets = read_xlsx_sheets(boel_path)
    sheet_name = max(sheets, key=lambda name: len(sheets[name]))
    _, boel_raw = rows_as_dicts(sheets[sheet_name])
    boel_clean, boel_exclusions, boel_summary = audit_boel_records(boel_raw, boel_record["relative_path"])
    boel_summary["worksheet"] = sheet_name
    boel_summary["raw_sha256"] = boel_record["sha256"]
    summaries["boel_2016_nesg6348"] = boel_summary
    all_exclusions.extend(boel_exclusions)
    boel_output = data_root / "clean" / "boel_2016_nesg6348" / "sequence_expression.csv"
    write_csv_atomic(boel_output, boel_clean, LONG_FIELDS)
    artifacts["boel_2016_nesg6348"] = artifact_record(boel_output, data_root, len(boel_clean))
    all_clean.extend(boel_clean)

    mage_outputs = (
        ("data_s1_single_codon_csv", audit_mage_single, "single_codon_fitness.csv"),
        ("data_s2_codon_pair_csv", audit_mage_pairs, "codon_pair_fitness.csv"),
        ("data_s3_utr_csv", audit_mage_utr, "utr_fitness.csv"),
    )
    for file_id, auditor, output_name in mage_outputs:
        raw_record, raw_path = _record_path(manifest, data_root, file_id)
        _, raw_rows = read_csv_records(raw_path)
        clean, exclusions, summary = auditor(raw_rows, raw_record["relative_path"])
        summary["raw_sha256"] = raw_record["sha256"]
        summaries[file_id] = summary
        all_exclusions.extend(exclusions)
        output = data_root / "clean" / "kelsic_2016_mage_seq" / output_name
        write_csv_atomic(output, clean, LONG_FIELDS)
        artifacts[file_id] = artifact_record(output, data_root, len(clean))
        all_clean.extend(clean)
    s4_record, _ = _record_path(manifest, data_root, "data_s4_genomewide_csv")
    summaries["data_s4_genomewide_csv"] = {
        "status": "excluded_from_sequence_label_long_table",
        "reason": "genome-wide structure context, not per-construct expression/fitness labels",
        "raw_sha256": s4_record["sha256"],
    }
    all_exclusions.append({"source_id": "kelsic_2016_mage_seq", "dataset_id": "data_s4_genomewide_csv",
                           "source_row": "all", "raw_key": "Data S4", "reason": summaries["data_s4_genomewide_csv"]["reason"]})
    kudla_records = [record for record in manifest["records"] if record["source_id"] == "kudla_2009_gfp"]
    kudla_failure = {
        "source_id": "kudla_2009_gfp", "required_product": "154 row-level EGFP sequence-expression records",
        "status": "unavailable_not_downloaded", "actual_sequence_label_rows": 0,
        "evidence": "SOM contains Materials and Methods, Figs. S1-S9 and references; oligos are degenerate synthesis primers, not the 154-variant table",
        "action": "obtain the original row-level table from the authors or a verified archival copy; do not digitize figure values",
    }
    summaries["kudla_2009_gfp"] = {
        "status": "supporting_files_downloaded_row_level_sequence_expression_table_unavailable",
        "raw_supporting_files": [{"path": record["relative_path"], "sha256": record.get("sha256"),
                                   "role": record.get("role"), "status": record.get("status")}
                                  for record in kudla_records],
        "actual_sequence_label_rows": 0, "clean_rows": 0,
        "paper_reported_construct_count": 154,
    }
    all_exclusions.append({"source_id": "kudla_2009_gfp", "dataset_id": "row_level_sequence_expression",
                           "source_row": "all", "raw_key": "154 reported constructs", "reason": kudla_failure["evidence"]})

    long_output = data_root / "clean" / "functional_long.csv"
    write_csv_atomic(long_output, all_clean, LONG_FIELDS)
    artifacts["functional_long"] = artifact_record(long_output, data_root, len(all_clean))
    protocols = [
        {"source_id": "boel_2016_nesg6348", "protocol_id": "boel_2016_t7_pet_defined_medium_18c",
         "host": "E. coli BL21(DE3), pMGK-argU", "construct": "pET/T7 RNAP; C-terminal LEHHHHHH",
         "medium": "defined medium", "temperature_c": "18", "time": "overnight induction",
         "measurement": "Coomassie SDS-PAGE whole-cell lysate; integer E=0..5; two isolates",
         "license": "publisher supplement; no open reuse license asserted"},
        {"source_id": "kelsic_2016_mage_seq", "protocol_id": "kelsic_2016_mage_seq_growth_selection",
         "host": "E. coli chromosomal infA", "construct": "single-codon, codon-pair and 5prime-UTR MAGE",
         "medium": "MOPS rich and/or minimal by assay", "temperature_c": "not imputed",
         "time": "growth-selection time course", "measurement": "amplicon sequencing relative fitness with source stdev",
         "license": "author manuscript supplement; no open reuse license asserted"},
        {"source_id": "kudla_2009_gfp", "protocol_id": "kudla_2009_pgk8_iptg_37c",
         "host": "E. coli BL21(DE3); DH5alpha/pGK14 comparison",
         "construct": "EGFP synonymous library; pGK8; degenerate synthesis oligos; row-level sequences unavailable",
         "medium": "M9 and LB compared; per-row medium not available", "temperature_c": "37", "time": "1 mM IPTG, 3 h",
         "measurement": "Spectramax fluorescence; 12 controls for cross-plate normalization; no per-row values obtained",
         "license": "publisher supporting material; no open reuse license asserted"},
    ]
    protocol_fields = ["source_id", "protocol_id", "host", "construct", "medium", "temperature_c", "time", "measurement", "license"]
    write_csv_atomic(audit_dir / "protocols.csv", protocols, protocol_fields)
    write_csv_atomic(audit_dir / "row_exclusions.csv", all_exclusions,
                     ["source_id", "dataset_id", "source_row", "raw_key", "reason"])
    write_csv_atomic(audit_dir / "data_product_failures.csv", [kudla_failure],
                     ["source_id", "required_product", "status", "actual_sequence_label_rows", "evidence", "action"])
    leakage = {
        "random_row_split_forbidden": True,
        "boel": "Natural non-synonymous cross-protein pool; family labels unavailable in Supplementary Data 2; fixed family mapping required before split.",
        "mage": "Single infA family; single/pair windows overlap. Keep all infA constructs in one fixed partition or use construct-signature grouping; never random rows.",
        "duplicate_policy": "Exact duplicate rows quarantined; cross-window mutation signatures counted separately from measurement rows.",
        "current_split_assignment": "UNASSIGNED; no train/dev/test split has been created.",
    }
    (audit_dir / "leakage_report.json").write_text(json.dumps(leakage, indent=2) + "\n", encoding="utf-8")
    summary = {
        "schema_version": "a8-rk-functional-audit-v1", "created_at": utc_now(),
        "config": str(config_path), "data_root": str(data_root),
        "status": "PARTIAL_KUDLA_ROW_DATA_UNAVAILABLE",
        "paper_reported_counts": {"kudla_2009_gfp": 154, "boel_2016_nesg6348": 6348,
                                   "kelsic_2016_total_in_situ_codon_mutants": 12726},
        "actual_download_and_clean_counts": summaries,
        "clean_artifacts": artifacts, "functional_long_rows": len(all_clean),
        "row_exclusions_including_s4_source_exclusion": len(all_exclusions),
        "unresolved_download_failures": manifest["failures"],
        "unresolved_data_products": [kudla_failure],
        "resolved_download_failures": manifest.get("resolved_failures", []),
        "leakage": leakage, "training_or_split_created": False,
    }
    (audit_dir / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--register-browser-file", nargs=3, action="append", default=[],
                        metavar=("SOURCE_ID", "FILE_ID", "METHOD"),
                        help="Validate an existing raw file and mark a browser-assisted download resolved")
    args = parser.parse_args(argv)
    selected = sum((args.download_only, args.audit, bool(args.register_browser_file)))
    if selected != 1:
        parser.error("choose exactly one of --download-only, --register-browser-file, or --audit")
    if args.register_browser_file:
        manifest = register_browser_downloads(
            args.audit_dir / "download_manifest.json", args.data_root, args.audit_dir,
            [tuple(item) for item in args.register_browser_file],
        )
    elif args.audit:
        manifest = audit_all(args.config, args.data_root, args.audit_dir)
        print(json.dumps({"status": manifest["status"], "functional_long_rows": manifest["functional_long_rows"]}, sort_keys=True))
        return 0
    else:
        manifest = download_priority_one(args.config, args.data_root, refresh=args.refresh)
        write_download_outputs(manifest, args.audit_dir)
    counts: Dict[str, int] = {}
    for record in manifest["records"]:
        key = str(record["status"])
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({"status": manifest["status"], "counts": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
