#!/usr/bin/env python3
"""Independent streaming verifier for CodonTransformer row QC artifacts."""
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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

COLUMNS = ["dna", "protein", "organism", "GeneID", "description", "tokenized", "fine_tuned", "len"]
STOPS = {"TAA", "TAG", "TGA"}
CODE = {}
for codon, aa in zip(
    (a + b + c for a in "TCAG" for b in "TCAG" for c in "TCAG"),
    "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG",
):
    CODE[codon] = "_" if aa == "*" else aa
ACCESSION = re.compile(r"\b([A-Z]{1,4}_\d+\.\d+):(\d+)-(\d+)\b")


def file_hash(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def summary(values: List[float]) -> Dict[str, object]:
    values = sorted(values)
    if not values:
        return {"n": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None}
    def q(fraction):
        position = (len(values) - 1) * fraction
        low, high = math.floor(position), math.ceil(position)
        return values[low] if low == high else values[low] * (high - position) + values[high] * (position - low)
    return {"n": len(values), "min": values[0], "p25": q(.25), "median": q(.5),
            "p75": q(.75), "max": values[-1], "mean": statistics.fmean(values)}


def independent_row(raw: Mapping[str, str]) -> Dict[str, object]:
    dna = str(raw.get("dna", "")).strip().upper()
    protein = str(raw.get("protein", "")).strip().upper()
    organism = " ".join(str(raw.get("organism", "")).split())
    gene_id = str(raw.get("GeneID", "")).strip()
    description = str(raw.get("description", ""))
    tokens = str(raw.get("tokenized", "")).strip()
    fine = str(raw.get("fine_tuned", "")).strip()
    reasons = []
    if not dna: reasons.append("missing_dna")
    if set(dna) - set("ACGT"): reasons.append("non_acgt_dna")
    if len(dna) % 3: reasons.append("dna_length_not_divisible_by_3")
    if not protein: reasons.append("missing_protein")
    if not protein.endswith("_"): reasons.append("missing_protein_terminal_stop")
    if "_" in protein[:-1]: reasons.append("internal_protein_stop_symbol")
    if set(protein[:-1]) - set("ACDEFGHIKLMNPQRSTVWY"): reasons.append("unsupported_protein_alphabet")
    if not organism: reasons.append("missing_organism")
    if not re.fullmatch(r"\d+(?:\.0+)?", gene_id): reasons.append("invalid_gene_id")
    if fine not in {"True", "False"}: reasons.append("invalid_fine_tuned")
    try:
        length = int(str(raw.get("len", "")).strip())
        if length != len(protein): reasons.append("protein_length_field_mismatch")
    except ValueError:
        reasons.append("invalid_length_field")
    matched = ACCESSION.search(description)
    if not matched:
        accession = None; coordinate = False; reasons.append("accession_or_coordinates_missing")
    else:
        accession = matched.group(1); start, end = int(matched.group(2)), int(matched.group(3))
        coordinate = start >= 1 and end >= start and end - start + 1 == len(dna)
        if not coordinate: reasons.append("accession_coordinate_length_mismatch")
    if dna and len(dna) % 3 == 0 and not set(dna) - set("ACGT"):
        codons = [dna[index:index + 3] for index in range(0, len(dna), 3)]
        start_atg = codons[0] == "ATG"; terminal = codons[-1] in STOPS
        internal = any(codon in STOPS for codon in codons[:-1])
        translated = "".join(CODE[codon] for codon in codons)
        if translated != protein: reasons.append("translation_protein_mismatch")
        expected_tokens = " ".join(f"{aa}_{codon}" for aa, codon in zip(translated, codons))
        if tokens != expected_tokens: reasons.append("tokenized_sequence_mismatch")
    else:
        start_atg = terminal = internal = False
    if dna and not start_atg: reasons.append("start_not_atg")
    if dna and not terminal: reasons.append("missing_terminal_stop")
    if internal: reasons.append("internal_stop")
    gc = (dna.count("G") + dna.count("C")) / len(dna) if dna else None
    return {"dna": dna, "protein": protein, "organism": organism, "gene_id": gene_id,
            "fine": fine, "accession": accession, "coordinate": coordinate, "gc": gc,
            "reasons": reasons, "valid": not reasons}


def write_audit(path: Path, report: Mapping[str, object]) -> None:
    if path.exists(): raise RuntimeError(f"refusing to overwrite audit: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + f".part.{os.getpid()}")
    part.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(part, path)


def verify(config_path: Path, raw_path: Path, qc_dir: Path, audit_path: Path,
           production_script: Optional[Path] = None) -> Dict[str, object]:
    checks = []
    def add(name, ok, detail=""): checks.append({"name": name, "pass": bool(ok), "detail": detail})
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source = next(item for item in config["sources"] if item["source_id"] == "codontransformer_training")
    spec = next(item for item in source["files"] if item["filename"] == raw_path.name)
    raw_errors = []; row_errors = []; clean_errors = []
    raw_hash = file_hash(raw_path); raw_bytes = raw_path.stat().st_size
    if raw_bytes != int(spec["expected_bytes"]): raw_errors.append("raw byte mismatch")
    if raw_hash.lower() != str(spec["expected_sha256"]).lower(): raw_errors.append("raw SHA256 mismatch")
    all_fields = ["source_row_number", "dna_sha256", "protein_sha256", "organism", "GeneID",
                  "accession", "valid", "exclusion_reasons", "gc_fraction", "dna_length",
                  "protein_length", "fine_tuned", "coordinate_length_match"]
    clean_fields = COLUMNS + ["source_row_number", "accession"]
    raw_organisms = Counter(); clean_organisms = Counter(); fine_counts = Counter(); reason_counts = Counter()
    first_dna = {}; duplicate_keys = set(); cross_keys = set(); clean_lengths = []; clean_gc = []
    raw_rows = clean_rows = duplicate_rows = cross_rows = 0
    csv.field_size_limit(100_000_000)
    try:
        with raw_path.open("r", encoding="utf-8-sig", newline="") as raw_handle, \
                gzip.open(qc_dir / "codontransformer_all_qc.csv.gz", "rt", encoding="utf-8", newline="") as all_handle, \
                gzip.open(qc_dir / "codontransformer_clean.csv.gz", "rt", encoding="utf-8", newline="") as clean_handle:
            raw_reader = csv.DictReader(raw_handle); all_reader = csv.DictReader(all_handle); clean_reader = csv.DictReader(clean_handle)
            if list(raw_reader.fieldnames or []) != COLUMNS: raise ValueError("raw columns differ")
            if list(all_reader.fieldnames or []) != all_fields: raise ValueError("all-QC columns differ")
            if list(clean_reader.fieldnames or []) != clean_fields: raise ValueError("clean columns differ")
            clean_next = next(clean_reader, None)
            for number, raw in enumerate(raw_reader, 1):
                expected = independent_row(raw); actual = next(all_reader, None); raw_rows += 1
                if actual is None:
                    row_errors.append(f"missing all-QC row {number}"); break
                organism = expected["organism"]; raw_organisms[organism] += 1; fine_counts[expected["fine"]] += 1
                reason_counts.update(expected["reasons"])
                dna_hash = text_hash(expected["dna"])
                if dna_hash in first_dna:
                    duplicate_rows += 1; duplicate_keys.add(dna_hash)
                    if first_dna[dna_hash] != organism: cross_rows += 1; cross_keys.add(dna_hash)
                else: first_dna[dna_hash] = organism
                expected_all = {"source_row_number": str(number), "dna_sha256": dna_hash,
                    "protein_sha256": text_hash(expected["protein"]), "organism": organism,
                    "GeneID": expected["gene_id"], "accession": expected["accession"] or "",
                    "valid": str(int(expected["valid"])), "exclusion_reasons": ";".join(expected["reasons"]),
                    "gc_fraction": "" if expected["gc"] is None else format(expected["gc"], ".17g"),
                    "dna_length": str(len(expected["dna"])), "protein_length": str(len(expected["protein"])),
                    "fine_tuned": expected["fine"], "coordinate_length_match": str(int(expected["coordinate"]))}
                for field in all_fields:
                    if actual.get(field) != expected_all[field]:
                        if len(row_errors) < 20: row_errors.append(f"row {number} field {field}: {actual.get(field)!r} != {expected_all[field]!r}")
                if expected["valid"]:
                    clean_rows += 1; clean_organisms[organism] += 1
                    clean_lengths.append(len(expected["protein"])); clean_gc.append(expected["gc"])
                    if clean_next is None:
                        clean_errors.append(f"missing clean row {number}")
                    else:
                        expected_clean = {**{column: raw[column] for column in COLUMNS},
                                          "source_row_number": str(number), "accession": expected["accession"]}
                        for field in clean_fields:
                            if clean_next.get(field) != expected_clean[field]:
                                if len(clean_errors) < 20: clean_errors.append(f"clean row {number} field {field}")
                        clean_next = next(clean_reader, None)
            if next(all_reader, None) is not None: row_errors.append("extra all-QC rows")
            if clean_next is not None: clean_errors.append("extra clean rows")
    except Exception as exc:
        raw_errors.append(f"{type(exc).__name__}: {exc}")
    add("raw_hash_header_translation", not raw_errors, raw_errors[:20])
    add("all_qc_exact_rows", not row_errors, row_errors[:20])
    add("clean_artifact_exact_set", not clean_errors, clean_errors[:20])
    try:
        produced = json.loads((qc_dir / "qc_summary.json").read_text(encoding="utf-8"))
        expected_counts = {"raw_rows": raw_rows, "clean_rows": clean_rows,
            "raw_organism_count": len(raw_organisms), "clean_organism_count": len(clean_organisms),
            "raw_organism_counts": dict(sorted(raw_organisms.items())),
            "clean_organism_counts": dict(sorted(clean_organisms.items())),
            "fine_tuned_counts": dict(sorted(fine_counts.items())),
            "exclusion_reason_counts": dict(sorted(reason_counts.items())),
            "duplicate_dna_rows_after_first": duplicate_rows, "duplicate_dna_keys": len(duplicate_keys),
            "cross_organism_duplicate_dna_rows_after_first": cross_rows,
            "cross_organism_duplicate_dna_keys": len(cross_keys)}
        mismatches = {key: {"actual": produced.get(key), "expected": value}
                      for key, value in expected_counts.items() if produced.get(key) != value}
        add("summary_counts_and_duplicates", not mismatches, mismatches)
        expected_distributions = {"protein_length_including_stop": summary(clean_lengths),
                                  "gc_fraction_full_cds": summary(clean_gc)}
        distribution_delta = 0.0; distribution_mismatch = []
        for metric, values in expected_distributions.items():
            for key, value in values.items():
                actual = produced.get("clean_distributions", {}).get(metric, {}).get(key)
                if value is None:
                    if actual is not None: distribution_mismatch.append([metric, key, actual, value])
                elif actual is None: distribution_mismatch.append([metric, key, actual, value])
                elif key == "n":
                    if actual != value: distribution_mismatch.append([metric, key, actual, value])
                else:
                    distribution_delta = max(distribution_delta, abs(float(actual) - float(value)))
        add("independent_distributions", not distribution_mismatch and distribution_delta <= 1e-12,
            {"mismatches": distribution_mismatch[:10], "max_numeric_delta": distribution_delta})
        scope_ok = (raw_rows == 1001197 and len(raw_organisms) == 164) if raw_bytes == 4652159854 else True
        add("publisher_scope_reconciliation", scope_ok,
            {"applicable": raw_bytes == 4652159854, "raw_rows": raw_rows, "organisms": len(raw_organisms)})
        scope_flags = produced.get("clean_table_ready_pending_verifier") is True and \
            produced.get("natural_distribution_eligible") is False and \
            produced.get("functional_training_authorized") is False and \
            produced.get("functional_ood_claim_authorized") is False
        add("scientific_scope_flags", scope_flags)
    except Exception as exc:
        add("summary_counts_and_duplicates", False, f"{type(exc).__name__}: {exc}")
        add("independent_distributions", False, "not reached")
        add("publisher_scope_reconciliation", False, "not reached")
        add("scientific_scope_flags", False, "not reached")
        produced = {}; distribution_delta = float("nan")
    try:
        manifest = json.loads((qc_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        artifact_errors = []
        for name, registered in manifest["outputs"].items():
            path = qc_dir / name
            if not path.is_file() or path.stat().st_size != int(registered["bytes"]) or file_hash(path) != registered["sha256"]:
                artifact_errors.append(name)
        if manifest["raw"]["bytes"] != raw_bytes or manifest["raw"]["sha256"] != raw_hash:
            artifact_errors.append("raw")
        add("artifact_manifest_sha256", not artifact_errors, artifact_errors)
    except Exception as exc:
        add("artifact_manifest_sha256", False, f"{type(exc).__name__}: {exc}")
    report = {"schema_version": "a8-rk03-codontransformer-independent-verification-v1",
              "created_at": datetime.now(timezone.utc).isoformat(),
              "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
              "check_count": len(checks), "passed_checks": sum(item["pass"] for item in checks),
              "checks": checks, "recomputed": {"raw_rows": raw_rows, "clean_rows": clean_rows,
              "raw_organisms": len(raw_organisms), "clean_organisms": len(clean_organisms)},
              "max_numeric_delta": distribution_delta,
              "production_script_sha256": file_hash(production_script) if production_script else None,
              "bounded_natural_sequence_distribution_ready": all(item["pass"] for item in checks),
              "functional_training_authorized": False, "functional_ood_claim_authorized": False,
              "provenance_boundary": "Independent row checks do not re-download every NCBI accession."}
    write_audit(audit_path, report)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True); parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--qc-dir", type=Path, required=True); parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--production-script", type=Path)
    args = parser.parse_args(argv)
    report = verify(args.config, args.raw, args.qc_dir, args.audit, args.production_script)
    print(json.dumps({"status": report["status"], "passed_checks": report["passed_checks"],
                      "check_count": report["check_count"], "recomputed": report["recomputed"]}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
