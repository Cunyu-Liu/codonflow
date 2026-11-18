#!/usr/bin/env python3
"""Build auditable codon/A-site tables from RiboMIMO's fixed-commit matrices.

The source contains author-processed codon-level A-site counts, not raw reads.
This script preserves every source record, recomputes the official >0.5/>0.6
coverage and positive-count normalization, checks reference proteins, and only
then emits a clean table. It never silently collapses duplicate source keys.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from scipy.stats import rankdata

from scripts.a8_rk_functional_data import translate_dna

SOURCE_COMMIT = "094c693d4df45f4b29f5a3209b31c452a39092a5"
COUNT_POSITIVE_THRESHOLD = 0.5
COVERAGE_THRESHOLD = 0.6
STOP_CODONS = {"TAA", "TAG", "TGA"}
DATASETS = {
    "Mohammad16": {
        "organism": "Escherichia coli str. K-12 substr. MG1655",
        "accession": "GSE72899",
        "reference": "ecoli",
        "allowed_starts": {"ATG", "GTG", "TTG"},
    },
    "Mohammad19-1": {
        "organism": "Escherichia coli str. K-12 substr. MG1655",
        "accession": "GSE119104/GSM3358140",
        "reference": "ecoli",
        "allowed_starts": {"ATG", "GTG", "TTG"},
    },
    "Mohammad19-2": {
        "organism": "Escherichia coli str. K-12 substr. MG1655",
        "accession": "GSE119104/GSM3358142",
        "reference": "ecoli",
        "allowed_starts": {"ATG", "GTG", "TTG"},
    },
    "Subtelny14": {
        "organism": "Saccharomyces cerevisiae S288C",
        "accession": "GSE53268/GSM1289257",
        "reference": "yeast",
        "allowed_starts": {"ATG"},
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open("r", encoding="utf-8")


def read_fasta(path: Path) -> Dict[str, str]:
    records: Dict[str, str] = {}
    header: Optional[str] = None
    sequence: List[str] = []
    with open_text(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    key = header[1:].split()[0]
                    if key in records:
                        raise ValueError(f"duplicate FASTA key {key} in {path}")
                    records[key] = "".join(sequence).upper().rstrip("*")
                header, sequence = line, []
            else:
                if header is None:
                    raise ValueError(f"sequence before FASTA header in {path}")
                sequence.append(line)
    if header is not None:
        key = header[1:].split()[0]
        if key in records:
            raise ValueError(f"duplicate FASTA key {key} in {path}")
        records[key] = "".join(sequence).upper().rstrip("*")
    if not records:
        raise ValueError(f"empty FASTA: {path}")
    return records


def field(header: str, name: str) -> Optional[str]:
    match = re.search(rf"\[{re.escape(name)}=([^\]]*)\]", header)
    return match.group(1) if match else None


def source_key(header: str, reference: str) -> Optional[str]:
    token = header[1:].split()[0] if header.startswith(">") else ""
    if reference == "yeast":
        return token or None
    protein_id = field(header, "protein_id")
    if protein_id:
        return protein_id
    match = re.search(r"(?:^|_)(NP_\d+\.\d+)(?:_|$)", token)
    if match:
        return match.group(1)
    return token if token.startswith("NP_") else None


def translate_record(codons: Sequence[str], allowed_starts: set) -> str:
    dna = "".join(codons)
    protein_with_stop = translate_dna(dna)
    if codons and codons[0] != "ATG" and codons[0] in allowed_starts:
        protein_with_stop = "M" + protein_with_stop[1:]
    return protein_with_stop[:-1] if protein_with_stop.endswith("*") else protein_with_stop


def normalize_counts(counts: Sequence[float]) -> Tuple[List[Optional[float]], Optional[float]]:
    array = np.asarray(counts, dtype=float)
    positive = array > COUNT_POSITIVE_THRESHOLD
    if not np.any(positive) or not np.all(np.isfinite(array)):
        return [None] * len(counts), None
    mean = float(np.mean(array[positive]))
    density = positive * array / mean
    return [float(value) for value in density], mean


def distribution(values: Sequence[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {"count": 0, "min": None, "q1": None, "median": None, "q3": None, "max": None, "mean": None}
    array = np.asarray(values, dtype=float)
    return {
        "count": int(array.size),
        "min": float(np.min(array)),
        "q1": float(np.quantile(array, 0.25)),
        "median": float(np.median(array)),
        "q3": float(np.quantile(array, 0.75)),
        "max": float(np.max(array)),
        "mean": float(np.mean(array)),
    }


def process_dataset(
    dataset: str,
    raw_path: Path,
    reference_proteins: Mapping[str, str],
) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    if dataset not in DATASETS:
        raise ValueError(f"unknown dataset {dataset}")
    metadata = DATASETS[dataset]
    lines = raw_path.read_text(encoding="utf-8").splitlines()
    if len(lines) % 3:
        raise ValueError(f"{raw_path}: line count {len(lines)} is not divisible by 3")
    records: List[Dict[str, object]] = []
    key_counts = Counter(
        source_key(lines[index], str(metadata["reference"]))
        for index in range(0, len(lines), 3)
    )
    for index in range(0, len(lines), 3):
        header, codon_line, count_line = lines[index:index + 3]
        codons = codon_line.split()
        try:
            counts = [float(value) for value in count_line.split()]
        except ValueError as exc:
            raise ValueError(f"{raw_path}: nonnumeric count at record {index // 3}") from exc
        key = source_key(header, str(metadata["reference"]))
        density, normalization_mean = normalize_counts(counts)
        reasons: List[str] = []
        if not key:
            reasons.append("missing_source_key")
        if key and key_counts[key] > 1:
            reasons.append("duplicate_source_key")
        if len(codons) != len(counts):
            reasons.append("codon_count_length_mismatch")
        if not codons or any(not re.fullmatch(r"[ACGT]{3}", codon) for codon in codons):
            reasons.append("invalid_codon_alphabet")
        if not np.all(np.isfinite(counts)) or any(value < 0 for value in counts):
            reasons.append("nonfinite_or_negative_count")
        if normalization_mean is None:
            reasons.append("no_positive_or_nonfinite_normalizer")
        if codons:
            if codons[0] not in metadata["allowed_starts"]:
                reasons.append("noncanonical_start")
            if codons[-1] not in STOP_CODONS:
                reasons.append("missing_terminal_stop")
            if any(codon in STOP_CODONS for codon in codons[:-1]):
                reasons.append("internal_stop")
        coverage = (
            float(np.mean(np.asarray(counts) > COUNT_POSITIVE_THRESHOLD))
            if counts else 0.0
        )
        if not coverage > COVERAGE_THRESHOLD:
            reasons.append("coverage_not_strictly_gt_0_6")
        translated = translate_record(codons, metadata["allowed_starts"]) if codons else ""
        reference_protein = reference_proteins.get(key) if key else None
        if reference_protein is None:
            reference_status = "reference_id_not_found"
            reasons.append("reference_id_not_found")
        elif translated == reference_protein:
            reference_status = "exact_translation_match"
        else:
            reference_status = "translation_mismatch"
            reasons.append("translation_mismatch")
        dna = "".join(codons)
        record = {
            "record_id": f"{dataset}:{index // 3:06d}",
            "dataset": dataset,
            "organism": metadata["organism"],
            "source_accession": metadata["accession"],
            "source_commit": SOURCE_COMMIT,
            "source_record_index": index // 3,
            "source_header": header,
            "source_key": key,
            "gene": field(header, "gene"),
            "locus_tag": field(header, "locus_tag"),
            "location": field(header, "location"),
            "cds_dna": dna,
            "translated_protein": translated,
            "n_codons": len(codons),
            "n_count_values": len(counts),
            "start_codon": codons[0] if codons else None,
            "terminal_codon": codons[-1] if codons else None,
            "alternative_start": bool(codons and codons[0] != "ATG" and codons[0] in metadata["allowed_starts"]),
            "gc_fraction": (dna.count("G") + dna.count("C")) / len(dna) if dna else None,
            "counts_raw": counts,
            "total_count": float(sum(counts)),
            "coverage_count_gt_0_5": coverage,
            "normalization_mean_count_gt_0_5": normalization_mean,
            "density_normalized": density,
            "reference_protein_status": reference_status,
            "reference_protein_sha256": (
                hashlib.sha256(reference_protein.encode()).hexdigest()
                if reference_protein is not None else None
            ),
            "clean_eligible": not reasons,
            "exclusion_reasons": reasons,
        }
        records.append(record)
    clean = [record for record in records if record["clean_eligible"]]
    reason_counts = Counter(
        reason for record in records for reason in record["exclusion_reasons"]
    )
    summary = {
        "dataset": dataset,
        "organism": metadata["organism"],
        "source_accession": metadata["accession"],
        "raw_path": str(raw_path),
        "raw_sha256": sha256_file(raw_path),
        "records": len(records),
        "unique_source_keys": len({record["source_key"] for record in records if record["source_key"]}),
        "clean_records": len(clean),
        "clean_fraction": len(clean) / len(records) if records else 0.0,
        "alternative_start_records": sum(bool(record["alternative_start"]) for record in records),
        "reference_exact_translation_records": sum(record["reference_protein_status"] == "exact_translation_match" for record in records),
        "coverage_gt_0_6_records": sum(record["coverage_count_gt_0_5"] > COVERAGE_THRESHOLD for record in records),
        "exclusion_reason_counts": dict(sorted(reason_counts.items())),
        "clean_n_codons": distribution([record["n_codons"] for record in clean]),
        "clean_gc_fraction": distribution([record["gc_fraction"] for record in clean]),
        "clean_coverage": distribution([record["coverage_count_gt_0_5"] for record in clean]),
    }
    return records, summary


def correlation_summary(pairs: Sequence[Tuple[Mapping[str, object], Mapping[str, object]]]) -> Dict[str, object]:
    pearson: List[float] = []
    spearman: List[float] = []
    total_1: List[float] = []
    total_2: List[float] = []
    for left, right in pairs:
        x = np.asarray(left["density_normalized"], dtype=float)
        y = np.asarray(right["density_normalized"], dtype=float)
        if x.size == y.size and x.size > 1 and np.std(x) > 0 and np.std(y) > 0:
            pearson.append(float(np.corrcoef(x, y)[0, 1]))
            rx, ry = rankdata(x), rankdata(y)
            spearman.append(float(np.corrcoef(rx, ry)[0, 1]))
        total_1.append(float(left["total_count"]))
        total_2.append(float(right["total_count"]))
    result = {
        "paired_genes": len(pairs),
        "valid_profile_correlations": len(pearson),
        "profile_pearson": distribution(pearson),
        "profile_spearman": distribution(spearman),
        "log1p_total_count_pearson": None,
    }
    if len(total_1) > 1 and np.std(total_1) > 0 and np.std(total_2) > 0:
        result["log1p_total_count_pearson"] = float(
            np.corrcoef(np.log1p(total_1), np.log1p(total_2))[0, 1]
        )
    return result


def replicate_qc(records_by_dataset: Mapping[str, Sequence[Mapping[str, object]]]) -> Dict[str, object]:
    left = {
        record["source_key"]: record
        for record in records_by_dataset.get("Mohammad19-1", [])
        if record["source_key"] and "duplicate_source_key" not in record["exclusion_reasons"]
    }
    right = {
        record["source_key"]: record
        for record in records_by_dataset.get("Mohammad19-2", [])
        if record["source_key"] and "duplicate_source_key" not in record["exclusion_reasons"]
    }
    shared = sorted(left.keys() & right.keys())
    sequence_pairs = [(left[key], right[key]) for key in shared if left[key]["cds_dna"] == right[key]["cds_dna"]]
    clean_pairs = [
        (left_record, right_record)
        for left_record, right_record in sequence_pairs
        if left_record["clean_eligible"] and right_record["clean_eligible"]
    ]
    return {
        "comparison": "Mohammad19-1_vs_Mohammad19-2",
        "replicate_type_boundary": "distinct GSM samples; biological/technical replicate status not inferred",
        "shared_unique_source_keys": len(shared),
        "identical_cds_pairs": len(sequence_pairs),
        "both_clean_pairs": len(clean_pairs),
        "all_identical_cds_pairs": correlation_summary(sequence_pairs),
        "both_clean_pairs_metrics": correlation_summary(clean_pairs),
    }


def write_jsonl_gz(records: Iterable[Mapping[str, object]], path: Path) -> None:
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(temporary, path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--ecoli-protein-fasta", default="ecoli_protein.faa.gz")
    parser.add_argument("--yeast-protein-fasta", default="orf_trans_all.fasta.gz")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    references = {
        "ecoli": read_fasta(args.reference_dir / args.ecoli_protein_fasta),
        "yeast": read_fasta(args.reference_dir / args.yeast_protein_fasta),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_records: Dict[str, List[Dict[str, object]]] = {}
    summaries = []
    clean_records = []
    for dataset, metadata in DATASETS.items():
        records, summary = process_dataset(
            dataset, args.raw_dir / f"{dataset}.txt", references[str(metadata["reference"])]
        )
        all_records[dataset] = records
        summaries.append(summary)
        clean_records.extend(record for record in records if record["clean_eligible"])
        print(json.dumps({"dataset": dataset, "records": len(records), "clean": summary["clean_records"]}))
    all_path = args.output_dir / "ribomimo_all_qc.jsonl.gz"
    clean_path = args.output_dir / "ribomimo_clean.jsonl.gz"
    write_jsonl_gz((record for dataset in DATASETS for record in all_records[dataset]), all_path)
    write_jsonl_gz(clean_records, clean_path)
    summary = {
        "schema_version": "a8-rk03-ribomimo-qc-v1",
        "source_commit": SOURCE_COMMIT,
        "source_semantics": "author-processed codon-level ribosomal A-site counts; raw reads/P-site remapping unavailable in these files",
        "normalization": {
            "positive_rule": "count > 0.5",
            "density_rule": "(count > 0.5) * count / mean(count[count > 0.5])",
            "coverage_rule": "mean(count > 0.5) > 0.6 (strict)",
            "end_masking_not_applied_by_this_qc": "RiboMIMO model later masks first 5 and last 4 codons; raw and pre-mask normalized values are preserved here",
        },
        "reference_protein_fastas": {
            key: {"path": str(args.reference_dir / value), "sha256": sha256_file(args.reference_dir / value), "entries": len(references[key])}
            for key, value in (("ecoli", args.ecoli_protein_fasta), ("yeast", args.yeast_protein_fasta))
        },
        "clean_rule": "no duplicate key, aligned lengths, canonical sequence/start/stop, finite nonnegative counts, strict coverage, and exact translated-reference protein match",
        "utr_status": "not_provided_by_ribomimo_source",
        "datasets": summaries,
        "total_records": sum(item["records"] for item in summaries),
        "total_clean_records": sum(item["clean_records"] for item in summaries),
        "replicate_qc": replicate_qc(all_records),
        "artifacts": {},
    }
    summary_path = args.output_dir / "qc_summary.json"
    summary["artifacts"] = {
        "all_qc_jsonl_gz": {"path": str(all_path), "sha256": sha256_file(all_path)},
        "clean_jsonl_gz": {"path": str(clean_path), "sha256": sha256_file(clean_path)},
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "qc_summary": {"path": str(summary_path), "sha256": sha256_file(summary_path)},
        **summary["artifacts"],
    }
    (args.output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
