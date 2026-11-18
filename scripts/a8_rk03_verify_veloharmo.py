#!/usr/bin/env python3
"""Independent fixed-archive verifier for VeloHARMO E. coli materialization/QC."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import os
import re
import statistics
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

COMMIT = "38b48079856aeb9d33a1b10844d77aa8f6640032"
ARCHIVE_SHA256 = "68b029b667029827d9c7213249eebcac32e6152d80ef7c0e24e53d8437d5a0ef"
ROOT = f"VeloHARMO-{COMMIT}/"
DATA = "E.coli.summary.add.pro.SS.txt"
MATRIX_ZIP = "VeloBERT/E.coli.summary.add.pro.SS.txt.zip"
OTHER_ZIP = "VeloGRU/E.coli.summary.add.pro.SS.txt.zip"
SS = set("-STIGEBH")
STOPS = {"TAA", "TAG", "TGA"}


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def summary(values) -> dict[str, Any]:
    values = sorted(float(x) for x in values)
    if not values:
        return {"n": 0, "min": None, "median": None, "max": None, "mean": None}
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    return {"n": len(values), "min": values[0], "median": median, "max": values[-1], "mean": statistics.fmean(values)}


def parse(data: bytes):
    lines = data.decode("utf-8").splitlines()
    if len(lines) % 4:
        raise RuntimeError("matrix line count is not divisible by four")
    records = []
    dim_counts = Counter()
    for i in range(len(lines) // 4):
        h, s, v, f = lines[4 * i : 4 * i + 4]
        match = re.fullmatch(r">(\S+)\s+(\d+)", h.strip())
        gene = match.group(1) if match else f"__invalid_header_{i + 1}"
        declared = int(match.group(2)) if match else None
        codons = s.split()
        vtokens = v.split()
        ftokens = f.split()
        reasons = []
        if not match: reasons.append("invalid_header")
        if not len(codons) == len(vtokens) == len(ftokens): reasons.append("four_track_length_mismatch")
        if declared != len(codons): reasons.append("declared_codon_count_mismatch")
        if any(not re.fullmatch(r"[ACGT]{3}", c) for c in codons): reasons.append("invalid_codon_alphabet")
        speeds = []
        for token in vtokens:
            try: value = float(token)
            except ValueError: value = math.nan
            speeds.append(value)
        if any(not math.isfinite(x) or x < 0 for x in speeds): reasons.append("invalid_or_negative_velocity")
        features, structures, dims = [], [], set()
        for token in ftokens:
            parts = token.split(",")
            structures.append(parts[-1] if parts else "")
            try: values = [float(x) for x in parts[:-1]]
            except ValueError: values = [math.nan]
            features.append(values)
            dims.add(len(values))
        if any(not values or any(not math.isfinite(x) for x in values) for values in features): reasons.append("invalid_numeric_structure_feature")
        if len(dims) > 1: reasons.append("within_record_feature_dim_mismatch")
        if any(x not in SS for x in structures): reasons.append("invalid_secondary_structure_symbol")
        positive = [x for x in speeds if x > 0.5 and math.isfinite(x)]
        avg = sum(positive) / len(positive) if positive else None
        if avg is None or not math.isfinite(avg) or avg <= 0: reasons.append("normalization_no_velocity_above_0_5")
        density = [(x / avg if x > 0.5 else 0.0) for x in speeds] if avg else None
        if density is not None and any(not math.isfinite(x) for x in density): reasons.append("nonfinite_normalized_density")
        dim = next(iter(dims)) if len(dims) == 1 else None
        dim_counts[dim] += 1
        records.append({
            "record_id": f"ecoli:{i + 1:06d}", "source_record_number": i + 1,
            "gene_id": gene, "declared_codon_count": declared, "codons": codons,
            "velocity_values": speeds, "structure_numeric_features": features,
            "secondary_structure": structures, "normalization_mean_above_0_5": avg,
            "normalized_density": density, "codon_count": len(codons),
            "start_atg": bool(codons and codons[0] == "ATG"),
            "terminal_stop": bool(codons and codons[-1] in STOPS),
            "coverage_fraction_above_0_5": len(positive) / len(codons) if codons else None,
            "feature_numeric_dim": dim, "base_exclusion_reasons": reasons,
        })
    return records, dim_counts


def equal_number(a, b, tolerance=1e-12):
    if a is None or b is None:
        return a is b
    if isinstance(a, (float, int)) and isinstance(b, (float, int)):
        if math.isnan(float(a)) and math.isnan(float(b)):
            return True
        return abs(float(a) - float(b)) <= tolerance
    return a == b


def nested_equal(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(nested_equal(x, y) for x, y in zip(a, b))
    return equal_number(a, b)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--payload-dir", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    args = parser.parse_args()
    qc_dir = args.payload_dir / "qc_v1"
    checks = []
    max_delta = 0.0
    def add(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    archive_ok = file_sha(args.archive) == ARCHIVE_SHA256
    with zipfile.ZipFile(args.archive) as outer:
        archive_ok &= outer.testzip() is None
        zip_a = outer.read(ROOT + MATRIX_ZIP)
        zip_b = outer.read(ROOT + OTHER_ZIP)
        archive_ok &= zip_a == zip_b
        with zipfile.ZipFile(io.BytesIO(zip_a)) as inner:
            archive_ok &= inner.testzip() is None
            matrix_bytes = inner.read(DATA)
    matrix_path = args.payload_dir / "shared" / DATA
    archive_ok &= matrix_path.is_file() and file_sha(matrix_path) == hashlib.sha256(matrix_bytes).hexdigest()
    add("fixed_outer_inner_archive_and_matrix", archive_ok, {"matrix_bytes": len(matrix_bytes), "matrix_sha256": hashlib.sha256(matrix_bytes).hexdigest()})

    expected, dim_counts = parse(matrix_bytes)
    gene_counts = Counter(r["gene_id"] for r in expected)
    positive_dims = {k: v for k, v in dim_counts.items() if k is not None}
    ranked = sorted(positive_dims.items(), key=lambda item: (-item[1], item[0]))
    modal = ranked[0][0] if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]) else None
    clean_expected = []
    reason_counts = Counter()
    for record in expected:
        reasons = list(record["base_exclusion_reasons"])
        if gene_counts[record["gene_id"]] > 1: reasons.append("duplicate_gene_id")
        if modal is None: reasons.append("dataset_feature_dim_tie")
        elif record["feature_numeric_dim"] != modal: reasons.append("dataset_feature_dim_not_modal")
        record["exclusion_reasons"] = reasons
        record["clean_eligible"] = not reasons
        reason_counts.update(reasons)
        if not reasons: clean_expected.append(record)

    errors = []
    with gzip.open(qc_dir / "veloharmo_ecoli_all_qc.jsonl.gz", "rt", encoding="utf-8") as handle:
        actual = [json.loads(line) for line in handle]
    if len(actual) != len(expected): errors.append(f"row count {len(actual)} != {len(expected)}")
    direct = ["record_id", "source_record_number", "gene_id", "declared_codon_count", "codons", "secondary_structure", "codon_count", "start_atg", "terminal_stop", "feature_numeric_dim", "base_exclusion_reasons", "exclusion_reasons", "clean_eligible"]
    numeric = ["velocity_values", "structure_numeric_features", "normalization_mean_above_0_5", "normalized_density", "coverage_fraction_above_0_5"]
    for i, (want, got) in enumerate(zip(expected, actual)):
        for field in direct:
            if want[field] != got.get(field):
                errors.append(f"{i}:{field}")
                break
        for field in numeric:
            if not nested_equal(want[field], got.get(field)):
                errors.append(f"{i}:{field}")
                break
        if len(errors) >= 100: break
    add("all_rows_independent_recompute", not errors, errors[:100])

    with gzip.open(qc_dir / "veloharmo_ecoli_clean.jsonl.gz", "rt", encoding="utf-8") as handle:
        clean_actual = [json.loads(line) for line in handle]
    clean_ids = [r["record_id"] for r in clean_actual]
    expected_ids = [r["record_id"] for r in clean_expected]
    add("clean_exact_ordered_record_set", clean_ids == expected_ids and all(r["clean_eligible"] for r in clean_actual), {"clean_records": len(clean_ids)})

    produced = json.loads((qc_dir / "qc_summary.json").read_text())
    expected_counts = {
        "raw_records": len(expected), "clean_records": len(clean_expected),
        "excluded_records": len(expected) - len(clean_expected), "unique_gene_ids": len(gene_counts),
        "duplicate_gene_ids": sum(v > 1 for v in gene_counts.values()),
        "duplicate_gene_rows": sum(v for v in gene_counts.values() if v > 1),
        "modal_feature_numeric_dim": modal,
        "start_atg_records": sum(r["start_atg"] for r in expected),
        "terminal_stop_records": sum(r["terminal_stop"] for r in expected),
    }
    count_errors = [f"{k}:{produced.get(k)}!={v}" for k, v in expected_counts.items() if produced.get(k) != v]
    if produced.get("feature_numeric_dim_counts") != {str(k): v for k, v in dim_counts.items()}: count_errors.append("feature_numeric_dim_counts")
    if produced.get("exclusion_reason_counts") != dict(reason_counts): count_errors.append("exclusion_reason_counts")
    expected_ss = dict(Counter(ss for r in expected for ss in r["secondary_structure"]))
    if produced.get("secondary_structure_counts") != expected_ss: count_errors.append("secondary_structure_counts")
    expected_distributions = {
        "clean_length_distribution": summary(r["codon_count"] for r in clean_expected),
        "clean_coverage_distribution": summary(r["coverage_fraction_above_0_5"] for r in clean_expected),
        "clean_record_mean_velocity_distribution": summary(statistics.fmean(r["velocity_values"]) for r in clean_expected),
    }
    for section, values in expected_distributions.items():
        for key, value in values.items():
            other = produced.get(section, {}).get(key)
            if not equal_number(value, other):
                count_errors.append(f"{section}:{key}")
            elif isinstance(value, float) and isinstance(other, (float, int)):
                max_delta = max(max_delta, abs(value - other))
    add("summary_counts_dimensions_and_distributions", not count_errors, {"errors": count_errors[:100], "max_numeric_delta": max_delta})

    material = json.loads((args.audit_dir / "veloharmo_materialization.json").read_text())
    material_errors = []
    with zipfile.ZipFile(args.archive) as outer:
        for record in material["files"]:
            rel = record["path"]
            raw = outer.read(ROOT + rel)
            actual = args.payload_dir / rel if record["storage"] == "teams" else args.source_dir / rel
            if not actual.is_file() or file_sha(actual) != hashlib.sha256(raw).hexdigest(): material_errors.append(rel)
            if record["storage"] == "teams" and (not (args.source_dir / rel).is_symlink() or (args.source_dir / rel).resolve() != actual.resolve()): material_errors.append(rel + ":symlink")
    for subdir in ("VeloBERT", "VeloGRU"):
        link = args.source_dir / subdir / DATA
        if not link.is_symlink() or link.resolve() != matrix_path.resolve(): material_errors.append(str(link))
    add("home_code_teams_payload_weights_and_symlinks", not material_errors, material_errors)

    manifest_errors = []
    manifest = json.loads((qc_dir / "artifact_manifest.json").read_text())
    for name, record in manifest["outputs"].items():
        path = qc_dir / name
        if record["bytes"] != path.stat().st_size or record["sha256"] != file_sha(path): manifest_errors.append(name)
    add("artifact_manifest_bytes_sha256", not manifest_errors, manifest_errors)

    scope = {
        "status": "COMPLETE_ECOLI_QC_PENDING_INDEPENDENT_VERIFICATION",
        "organism": "Escherichia_coli", "matrix_sha256": hashlib.sha256(matrix_bytes).hexdigest(),
        "official_four_line_structure": True,
        "ecoli_single_matrix_bounded_ready_pending_verifier": bool(clean_expected),
        "raw_reads_or_p_site_remapping_independently_performed": False,
        "five_species_processed_matrices_complete": False,
        "publisher_cross_validation_reproduced": False,
        "model_training_authorized": False,
        "functional_ood_or_sota_claim_authorized": False,
    }
    scope_errors = [f"{k}:{produced.get(k)}!={v}" for k, v in scope.items() if produced.get(k) != v]
    add("bounded_scientific_scope", not scope_errors, scope_errors)

    passed = sum(c["pass"] for c in checks)
    report = {
        "schema_version": "a8-rk03-veloharmo-independent-verification-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed == len(checks) else "FAIL",
        "independent_production_import": False,
        "checks": checks, "passed_checks": passed, "check_count": len(checks),
        "max_numeric_delta": max_delta,
        "recomputed": {"raw_records": len(expected), "clean_records": len(clean_expected), "unique_gene_ids": len(gene_counts), "duplicate_gene_ids": sum(v > 1 for v in gene_counts.values()), "modal_feature_numeric_dim": modal},
        "artifacts": {name: file_sha(qc_dir / name) for name in ("veloharmo_ecoli_all_qc.jsonl.gz", "veloharmo_ecoli_clean.jsonl.gz", "qc_summary.json", "artifact_manifest.json")},
        "scope": "E. coli processed matrix only; no five-species completeness, raw-read remapping, training, OOD or SOTA authorization.",
    }
    output = args.audit_dir / "veloharmo_ecoli_independent_verification.json"
    if output.exists(): raise RuntimeError(f"refusing to overwrite {output}")
    part = output.with_name(output.name + f".part-{os.getpid()}")
    part.write_text(json.dumps(report, indent=2) + "\n")
    os.replace(part, output)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "max_numeric_delta": max_delta, "recomputed": report["recomputed"]}, indent=2))
    if report["status"] != "PASS": raise SystemExit(1)


if __name__ == "__main__":
    main()
