#!/usr/bin/env python3
"""Materialize the fixed VeloHARMO archive and QC its E. coli matrix.

Code is written under /home; archives, matrix, weights and QC artifacts stay
under /teams. The four-line publisher matrix is never edited in place.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import statistics
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Optional, Sequence

COMMIT = "38b48079856aeb9d33a1b10844d77aa8f6640032"
ARCHIVE_SHA256 = "68b029b667029827d9c7213249eebcac32e6152d80ef7c0e24e53d8437d5a0ef"
ARCHIVE_ROOT = f"VeloHARMO-{COMMIT}"
DATA_REL = "E.coli.summary.add.pro.SS.txt"
MATRIX_ZIPS = ["VeloBERT/E.coli.summary.add.pro.SS.txt.zip", "VeloGRU/E.coli.summary.add.pro.SS.txt.zip"]
EXPECTED_FILES = [
    "Genetic_algorithm/E.coli.fold_0_best_network.pth",
    "Genetic_algorithm/ga_velocity_pattern.add.time.pearson.ss.py",
    "Genetic_algorithm/yeast.fold_0_best_network.pth",
    "README.md",
    "VeloBERT/E.coli.summary.add.pro.SS.txt.zip",
    "VeloBERT/dataset.py",
    "VeloBERT/train.py",
    "VeloBERT/utils.py",
    "VeloGRU/E.coli.summary.add.pro.SS.txt.zip",
    "VeloGRU/VeloGRU_data.py",
    "VeloGRU/VeloGRU_train.py",
    "VeloGRU/models.py",
    "VeloGRU/run.py",
    "VeloGRU/utils.py",
]
SS = set("-STIGEBH")
STOP = {"TAA", "TAG", "TGA"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_bytes(path: Path, data: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise RuntimeError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + f".part-{os.getpid()}")
    part.write_bytes(data)
    os.replace(part, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode())


def prepare_empty(path: Path) -> None:
    if path.exists() and (path.is_symlink() or any(path.iterdir())):
        raise RuntimeError(f"output directory is nonempty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def safe_relative(name: str) -> str:
    if not name.startswith(ARCHIVE_ROOT + "/"):
        raise RuntimeError(f"unexpected archive root: {name}")
    rel = name[len(ARCHIVE_ROOT) + 1 :]
    pure = PurePosixPath(rel)
    if not rel or pure.is_absolute() or ".." in pure.parts:
        raise RuntimeError(f"unsafe archive member: {name}")
    return rel


def materialize(archive: Path, source_dir: Path, payload_dir: Path, audit: Path) -> dict[str, Any]:
    if sha256(archive) != ARCHIVE_SHA256:
        raise RuntimeError("outer archive SHA256 differs from the frozen download")
    prepare_empty(source_dir)
    prepare_empty(payload_dir)
    records = []
    with zipfile.ZipFile(archive) as outer:
        if outer.testzip() is not None:
            raise RuntimeError("outer archive CRC failure")
        files = [i for i in outer.infolist() if not i.is_dir()]
        relatives = sorted(safe_relative(i.filename) for i in files)
        if relatives != sorted(EXPECTED_FILES):
            raise RuntimeError(f"fixed file set differs: {relatives}")
        payloads: dict[str, bytes] = {}
        for info in files:
            rel = safe_relative(info.filename)
            data = outer.read(info)
            is_payload = rel.endswith(".zip") or rel.endswith(".pth")
            actual = payload_dir / rel if is_payload else source_dir / rel
            atomic_bytes(actual, data)
            if is_payload:
                payloads[rel] = data
                link = source_dir / rel
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(actual)
            records.append({"path": rel, "storage": "teams" if is_payload else "home", "bytes": len(data), "sha256": digest_bytes(data)})
        if payloads[MATRIX_ZIPS[0]] != payloads[MATRIX_ZIPS[1]]:
            raise RuntimeError("the two publisher matrix ZIPs differ")
        matrix_bytes = None
        inner_sha = None
        for rel in MATRIX_ZIPS:
            import io
            with zipfile.ZipFile(io.BytesIO(payloads[rel])) as inner:
                if inner.testzip() is not None or [i.filename for i in inner.infolist() if not i.is_dir()] != [DATA_REL]:
                    raise RuntimeError(f"unexpected inner matrix archive: {rel}")
                current = inner.read(DATA_REL)
                if matrix_bytes is None:
                    matrix_bytes = current
                    inner_sha = digest_bytes(current)
                elif current != matrix_bytes:
                    raise RuntimeError("inner matrices differ")
        assert matrix_bytes is not None
        matrix_path = payload_dir / "shared" / DATA_REL
        atomic_bytes(matrix_path, matrix_bytes)
        for subdir in ("VeloBERT", "VeloGRU"):
            link = source_dir / subdir / DATA_REL
            link.symlink_to(matrix_path)
    result = {
        "schema_version": "a8-rk03-veloharmo-materialization-v1",
        "created_at": now(),
        "status": "PASS_MATERIALIZATION_ONLY",
        "repository": "https://github.com/BianBian2021/VeloHARMO",
        "commit": COMMIT,
        "outer_archive": str(archive),
        "outer_archive_bytes": archive.stat().st_size,
        "outer_archive_sha256": sha256(archive),
        "source_dir": str(source_dir),
        "payload_dir": str(payload_dir),
        "files": records,
        "matrix": {"path": str(matrix_path), "bytes": len(matrix_bytes), "sha256": inner_sha, "two_archives_identical": True},
        "weights_stored_under_teams": True,
        "source_symlinks_resolve": all((source_dir / rel).resolve().is_file() for rel in MATRIX_ZIPS + ["Genetic_algorithm/E.coli.fold_0_best_network.pth", "Genetic_algorithm/yeast.fold_0_best_network.pth"]),
        "five_species_processed_matrices_complete": False,
        "model_training_or_sota_claim_authorized": False,
    }
    if not result["source_symlinks_resolve"]:
        raise RuntimeError("source symlink resolution failed")
    atomic_json(audit, result)
    return result


def numeric_summary(values: Iterable[float]) -> dict[str, Any]:
    ordered = sorted(float(x) for x in values)
    if not ordered:
        return {"n": 0, "min": None, "median": None, "max": None, "mean": None}
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {"n": len(ordered), "min": ordered[0], "median": median, "max": ordered[-1], "mean": statistics.fmean(ordered)}


def parse_records(matrix: Path) -> tuple[list[dict[str, Any]], Counter]:
    lines = matrix.read_text(encoding="utf-8").splitlines()
    if len(lines) % 4:
        raise RuntimeError(f"matrix line count {len(lines)} is not divisible by four")
    records = []
    global_feature_dims = Counter()
    for index in range(len(lines) // 4):
        header, seq_line, speed_line, feature_line = lines[4 * index : 4 * index + 4]
        match = re.fullmatch(r">(\S+)\s+(\d+)", header.strip())
        gene_id = match.group(1) if match else f"__invalid_header_{index + 1}"
        declared = int(match.group(2)) if match else None
        codons = seq_line.split()
        speed_tokens = speed_line.split()
        feature_tokens = feature_line.split()
        reasons = []
        if not match:
            reasons.append("invalid_header")
        if not (len(codons) == len(speed_tokens) == len(feature_tokens)):
            reasons.append("four_track_length_mismatch")
        if declared != len(codons):
            reasons.append("declared_codon_count_mismatch")
        if any(not re.fullmatch(r"[ACGT]{3}", codon) for codon in codons):
            reasons.append("invalid_codon_alphabet")
        speeds = []
        for token in speed_tokens:
            try:
                value = float(token)
            except ValueError:
                value = math.nan
            speeds.append(value)
        if any(not math.isfinite(x) or x < 0 for x in speeds):
            reasons.append("invalid_or_negative_velocity")
        features: list[list[float]] = []
        structures = []
        feature_dims = set()
        for token in feature_tokens:
            parts = token.split(",")
            structures.append(parts[-1] if parts else "")
            try:
                values = [float(x) for x in parts[:-1]]
            except ValueError:
                values = [math.nan]
            features.append(values)
            feature_dims.add(len(values))
        if any(not values or any(not math.isfinite(x) for x in values) for values in features):
            reasons.append("invalid_numeric_structure_feature")
        if len(feature_dims) > 1:
            reasons.append("within_record_feature_dim_mismatch")
        if any(value not in SS for value in structures):
            reasons.append("invalid_secondary_structure_symbol")
        positive = [x for x in speeds if x > 0.5 and math.isfinite(x)]
        avg = sum(positive) / len(positive) if positive else None
        if avg is None or not math.isfinite(avg) or avg <= 0:
            reasons.append("normalization_no_velocity_above_0_5")
        density = [(x / avg if x > 0.5 else 0.0) for x in speeds] if avg else None
        if density is not None and any(not math.isfinite(x) for x in density):
            reasons.append("nonfinite_normalized_density")
        record = {
            "record_id": f"ecoli:{index + 1:06d}",
            "source_record_number": index + 1,
            "gene_id": gene_id,
            "declared_codon_count": declared,
            "codons": codons,
            "velocity_values": speeds,
            "structure_numeric_features": features,
            "secondary_structure": structures,
            "normalization_mean_above_0_5": avg,
            "normalized_density": density,
            "codon_count": len(codons),
            "start_atg": bool(codons and codons[0] == "ATG"),
            "terminal_stop": bool(codons and codons[-1] in STOP),
            "coverage_fraction_above_0_5": len(positive) / len(codons) if codons else None,
            "feature_numeric_dim": next(iter(feature_dims)) if len(feature_dims) == 1 else None,
            "base_exclusion_reasons": reasons,
        }
        global_feature_dims[record["feature_numeric_dim"]] += 1
        records.append(record)
    return records, global_feature_dims


def run_qc(matrix: Path, output_dir: Path, audit: Path) -> dict[str, Any]:
    prepare_empty(output_dir)
    records, feature_dims = parse_records(matrix)
    gene_counts = Counter(record["gene_id"] for record in records)
    positive_dims = {key: value for key, value in feature_dims.items() if key is not None}
    modal_dim = None
    if positive_dims:
        ranked = sorted(positive_dims.items(), key=lambda item: (-item[1], item[0]))
        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            modal_dim = ranked[0][0]
    clean_records = []
    reason_counts = Counter()
    for record in records:
        reasons = list(record["base_exclusion_reasons"])
        if gene_counts[record["gene_id"]] > 1:
            reasons.append("duplicate_gene_id")
        if modal_dim is None:
            reasons.append("dataset_feature_dim_tie")
        elif record["feature_numeric_dim"] != modal_dim:
            reasons.append("dataset_feature_dim_not_modal")
        record["exclusion_reasons"] = reasons
        record["clean_eligible"] = not reasons
        reason_counts.update(reasons)
        if not reasons:
            clean_records.append(record)
    all_path = output_dir / "veloharmo_ecoli_all_qc.jsonl.gz"
    clean_path = output_dir / "veloharmo_ecoli_clean.jsonl.gz"
    with gzip.open(all_path, "wt", encoding="utf-8", compresslevel=5) as all_handle, gzip.open(clean_path, "wt", encoding="utf-8", compresslevel=5) as clean_handle:
        for record in records:
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            all_handle.write(line)
            if record["clean_eligible"]:
                clean_handle.write(line)
    summary = {
        "schema_version": "a8-rk03-veloharmo-ecoli-qc-v1",
        "created_at": now(),
        "status": "COMPLETE_ECOLI_QC_PENDING_INDEPENDENT_VERIFICATION",
        "organism": "Escherichia_coli",
        "matrix_path": str(matrix),
        "matrix_bytes": matrix.stat().st_size,
        "matrix_sha256": sha256(matrix),
        "official_four_line_structure": True,
        "raw_records": len(records),
        "clean_records": len(clean_records),
        "excluded_records": len(records) - len(clean_records),
        "unique_gene_ids": len(gene_counts),
        "duplicate_gene_ids": sum(count > 1 for count in gene_counts.values()),
        "duplicate_gene_rows": sum(count for count in gene_counts.values() if count > 1),
        "feature_numeric_dim_counts": {str(key): value for key, value in feature_dims.items()},
        "modal_feature_numeric_dim": modal_dim,
        "exclusion_reason_counts": dict(reason_counts),
        "start_atg_records": sum(record["start_atg"] for record in records),
        "terminal_stop_records": sum(record["terminal_stop"] for record in records),
        "secondary_structure_counts": dict(Counter(ss for record in records for ss in record["secondary_structure"])),
        "clean_length_distribution": numeric_summary(record["codon_count"] for record in clean_records),
        "clean_coverage_distribution": numeric_summary(record["coverage_fraction_above_0_5"] for record in clean_records),
        "clean_record_mean_velocity_distribution": numeric_summary(statistics.fmean(record["velocity_values"]) for record in clean_records),
        "ecoli_single_matrix_bounded_ready_pending_verifier": len(records) > 0 and len(clean_records) > 0,
        "raw_reads_or_p_site_remapping_independently_performed": False,
        "five_species_processed_matrices_complete": False,
        "publisher_cross_validation_reproduced": False,
        "model_training_authorized": False,
        "functional_ood_or_sota_claim_authorized": False,
        "scope": "Publisher E. coli processed matrix QC only; not five-species completeness, raw-read remapping, training, OOD or SOTA evidence.",
        "artifacts": {"all_qc": all_path.name, "clean": clean_path.name},
    }
    summary_path = output_dir / "qc_summary.json"
    atomic_json(summary_path, summary)
    manifest = {
        "schema_version": "a8-rk03-veloharmo-ecoli-artifact-manifest-v1",
        "created_at": now(),
        "outputs": {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)} for path in (all_path, clean_path, summary_path)},
    }
    atomic_json(output_dir / "artifact_manifest.json", manifest)
    atomic_json(audit, summary)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--payload-dir", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    args.audit_dir.mkdir(parents=True, exist_ok=True)
    material = materialize(args.archive, args.source_dir, args.payload_dir, args.audit_dir / "veloharmo_materialization.json")
    summary = run_qc(Path(material["matrix"]["path"]), args.payload_dir / "qc_v1", args.audit_dir / "veloharmo_ecoli_qc.json")
    print(json.dumps({key: summary[key] for key in ("status", "raw_records", "clean_records", "excluded_records", "duplicate_gene_ids", "modal_feature_numeric_dim")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
