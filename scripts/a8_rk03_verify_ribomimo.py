#!/usr/bin/env python3
"""Independent raw-source verification for the RK03 RiboMIMO production tables."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
from scipy.stats import spearmanr

SOURCE_COMMIT = "094c693d4df45f4b29f5a3209b31c452a39092a5"
RAW_SHA256 = {
    "Mohammad16": "d093a3b0c53aa90d0626cc277a65a558c538ecbeb4d1cda091f02aad134588bc",
    "Mohammad19-1": "acc8c3adc9290611a6dc84049c10345428f752f0f62ed7069ed1ac3e9105f9a5",
    "Mohammad19-2": "e11f552ef958a381d1aec9a6d12f8e850d050fe001c31243491e08865b65cef1",
    "Subtelny14": "d982f6d8c14ba309ce26e29c8d81793df190b11d063c1333878d3dc6c0efa118",
}
ORGANISM = {
    "Mohammad16": "ecoli", "Mohammad19-1": "ecoli", "Mohammad19-2": "ecoli", "Subtelny14": "yeast"
}
CODONS = [a + b + c for a in "TCAG" for b in "TCAG" for c in "TCAG"]
AMINO_ACIDS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODON_TABLE = dict(zip(CODONS, AMINO_ACIDS))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl_gz(path: Path) -> List[dict]:
    with gzip.open(path, "rt") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_fasta(path: Path) -> Dict[str, str]:
    opener = gzip.open if path.suffix == ".gz" else open
    records: Dict[str, str] = {}
    key = None
    chunks: List[str] = []
    with opener(path, "rt") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                if key is not None:
                    if key in records:
                        raise AssertionError(f"duplicate FASTA key: {key}")
                    records[key] = "".join(chunks).removesuffix("*")
                key = line[1:].split()[0]
                chunks = []
            elif line:
                assert key is not None
                chunks.append(line)
    if key is not None:
        if key in records:
            raise AssertionError(f"duplicate FASTA key: {key}")
        records[key] = "".join(chunks).removesuffix("*")
    return records


def accession(header: str, organism: str) -> str | None:
    token = header[1:].split()[0]
    if organism == "yeast":
        return token
    match = re.search(r"(?:^|_)((?:NP|YP|WP)_\d+\.\d+)(?:_|$)", token)
    if match:
        return match.group(1)
    return token if token.startswith(("NP_", "YP_", "WP_")) else None


def translate(cds: str, organism: str) -> str:
    amino = [CODON_TABLE.get(cds[index:index + 3], "?") for index in range(0, len(cds), 3)]
    if amino and organism == "ecoli" and cds[:3] in {"GTG", "TTG"}:
        amino[0] = "M"
    return "".join(amino).removesuffix("*")


def distribution(values: Sequence[float]) -> dict:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return {"count": 0, "min": None, "q1": None, "median": None, "q3": None, "max": None, "mean": None}
    return {
        "count": int(array.size), "min": float(array.min()), "q1": float(np.quantile(array, 0.25)),
        "median": float(np.quantile(array, 0.5)), "q3": float(np.quantile(array, 0.75)),
        "max": float(array.max()), "mean": float(array.mean()),
    }


def compare_json(actual: object, expected: object, path: str, errors: List[str], tolerance: float = 1e-10) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            errors.append(f"{path}: type mismatch")
            return
        for key, value in expected.items():
            if key not in actual:
                errors.append(f"{path}.{key}: missing")
            else:
                compare_json(actual[key], value, f"{path}.{key}", errors, tolerance)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            errors.append(f"{path}: list mismatch")
            return
        for index, value in enumerate(expected):
            compare_json(actual[index], value, f"{path}[{index}]", errors, tolerance)
    elif isinstance(expected, float):
        if actual is None or not math.isfinite(float(actual)) or not math.isclose(float(actual), expected, rel_tol=tolerance, abs_tol=tolerance):
            errors.append(f"{path}: {actual} != {expected}")
    elif actual != expected:
        errors.append(f"{path}: {actual!r} != {expected!r}")


def profile_metrics(pairs: Sequence[Tuple[dict, dict]]) -> dict:
    pearson, spearman, totals_left, totals_right = [], [], [], []
    for left, right in pairs:
        if math.isfinite(float(left["total_count"])) and math.isfinite(float(right["total_count"])):
            totals_left.append(math.log1p(float(left["total_count"])))
            totals_right.append(math.log1p(float(right["total_count"])))
        x, y = left["density_normalized"], right["density_normalized"]
        if not isinstance(x, list) or not isinstance(y, list) or len(x) != len(y) or len(x) < 2:
            continue
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in x + y):
            continue
        xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        if xa.std() == 0 or ya.std() == 0:
            continue
        pearson.append(float(np.corrcoef(xa, ya)[0, 1]))
        spearman.append(float(spearmanr(xa, ya).statistic))
    return {
        "paired_genes": len(pairs),
        "valid_profile_correlations": len(pearson),
        "profile_pearson": distribution(pearson),
        "profile_spearman": distribution(spearman),
        "log1p_total_count_pearson": float(np.corrcoef(totals_left, totals_right)[0, 1]),
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--clean-dir", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    checks: List[dict] = []

    def check(name: str, passed: bool, details: object) -> None:
        checks.append({"name": name, "pass": bool(passed), "details": details})

    raw_errors = []
    for dataset, expected in RAW_SHA256.items():
        actual = sha256(args.raw_dir / f"{dataset}.txt")
        if actual != expected:
            raw_errors.append({"dataset": dataset, "actual": actual, "expected": expected})
    check("raw_source_sha256", not raw_errors, raw_errors or RAW_SHA256)

    references = {
        "ecoli": read_fasta(args.reference_dir / "ecoli_protein.faa.gz"),
        "yeast": read_fasta(args.reference_dir / "orf_trans_all.fasta.gz"),
    }
    supplement = read_fasta(args.reference_dir / "ecoli_protein_supplement.fasta")
    for key, value in supplement.items():
        assert key not in references["ecoli"] or references["ecoli"][key] == value
    references["ecoli"].update(supplement)
    all_qc = read_jsonl_gz(args.clean_dir / "ribomimo_all_qc.jsonl.gz")
    clean = read_jsonl_gz(args.clean_dir / "ribomimo_clean.jsonl.gz")
    summary = json.loads((args.clean_dir / "qc_summary.json").read_text())
    all_by_id = {record["record_id"]: record for record in all_qc}
    clean_by_id = {record["record_id"]: record for record in clean}
    check("unique_output_record_ids", len(all_by_id) == len(all_qc) and len(clean_by_id) == len(clean), {
        "all_rows": len(all_qc), "all_unique": len(all_by_id), "clean_rows": len(clean), "clean_unique": len(clean_by_id)
    })
    check("clean_subset_of_all_qc", set(clean_by_id) <= set(all_by_id), {
        "unexpected_clean_ids": sorted(set(clean_by_id) - set(all_by_id))[:20]
    })

    expected_clean_ids = set()
    independently_computed: Dict[str, List[dict]] = {}
    per_dataset_results = {}
    all_field_errors: List[str] = []
    for dataset in ORGANISM:
        organism = ORGANISM[dataset]
        lines = (args.raw_dir / f"{dataset}.txt").read_text().splitlines()
        assert len(lines) % 3 == 0
        raw_records = [lines[index:index + 3] for index in range(0, len(lines), 3)]
        keys = [accession(record[0], organism) for record in raw_records]
        key_counts = Counter(key for key in keys if key)
        reason_counts: Counter[str] = Counter()
        exact_reference = coverage_pass = alternate_start = 0
        computed_records = []
        clean_lengths, clean_gc, clean_coverage = [], [], []
        for index, ((header, codon_line, count_line), key) in enumerate(zip(raw_records, keys)):
            codons = [codon.strip().replace("U", "T") for codon in codon_line.rstrip("\t").split("\t")]
            cds = "".join(codons)
            counts = [float(value) for value in count_line.rstrip("\t").split("\t")]
            protein = translate(cds, organism) if len(cds) % 3 == 0 else ""
            reasons = []
            if key is None:
                reasons.append("missing_source_key")
            elif key_counts[key] > 1:
                reasons.append("duplicate_source_key")
            if len(codons) != len(counts):
                reasons.append("codon_count_length_mismatch")
            if len(cds) % 3:
                reasons.append("cds_length_not_multiple_of_3")
            if any(len(codon) != 3 or set(codon) - set("ACGT") for codon in codons):
                reasons.append("invalid_codon_or_base")
            if organism == "ecoli":
                if cds[:3] not in {"ATG", "GTG", "TTG"}:
                    reasons.append("noncanonical_start")
                if cds[:3] in {"GTG", "TTG"}:
                    alternate_start += 1
            elif cds[:3] != "ATG":
                reasons.append("noncanonical_start")
            if cds[-3:] not in {"TAA", "TAG", "TGA"}:
                reasons.append("missing_terminal_stop")
            if "*" in protein:
                reasons.append("internal_stop")
            if not all(math.isfinite(value) and value >= 0 for value in counts):
                reasons.append("invalid_count")
            positive = [value for value in counts if value > 0.5]
            normalizer = float(np.mean(positive)) if positive else None
            coverage = len(positive) / len(counts) if counts else None
            density = [value / normalizer if value > 0.5 and normalizer else 0.0 for value in counts] if normalizer else [None] * len(counts)
            if normalizer is None or not math.isfinite(normalizer):
                reasons.append("no_positive_or_nonfinite_normalizer")
            if coverage is not None and coverage > 0.6:
                coverage_pass += 1
            else:
                reasons.append("coverage_not_strictly_gt_0_6")
            reference = references[organism].get(key) if key else None
            if reference is None:
                reasons.append("reference_id_not_found")
            elif protein != reference:
                reasons.append("translation_mismatch")
            else:
                exact_reference += 1
            record_id = f"{dataset}:{index:06d}"
            eligible = not reasons
            if eligible:
                expected_clean_ids.add(record_id)
                clean_lengths.append(len(codons))
                clean_gc.append(sum(base in "GC" for base in cds) / len(cds))
                clean_coverage.append(coverage)
            reason_counts.update(set(reasons))
            computed = {
                "record_id": record_id, "source_key": key, "cds_dna": cds, "translated_protein": protein,
                "coverage_count_gt_0_5": coverage, "density_normalized": density, "total_count": sum(counts),
                "clean_eligible": eligible, "exclusion_reasons": sorted(set(reasons)),
            }
            computed_records.append(computed)
            produced = all_by_id.get(record_id)
            if produced is None:
                all_field_errors.append(f"{record_id}: missing from all-QC")
                continue
            if produced.get("source_key") != key or produced.get("cds_dna") != cds:
                all_field_errors.append(f"{record_id}: accession/CDS mismatch")
            if bool(produced.get("clean_eligible")) != eligible:
                all_field_errors.append(f"{record_id}: clean flag {produced.get('clean_eligible')} != {eligible}")
            if set(produced.get("exclusion_reasons", [])) != set(reasons):
                all_field_errors.append(f"{record_id}: reasons {produced.get('exclusion_reasons')} != {sorted(set(reasons))}")
            if produced.get("density_normalized") is not None:
                compare_json(produced.get("density_normalized"), density, f"{record_id}.density", all_field_errors, 1e-12)
        independently_computed[dataset] = computed_records
        print(json.dumps({"independent_dataset": dataset, "clean": len(clean_lengths), "reasons": dict(reason_counts)}), flush=True)
        per_dataset_results[dataset] = {
            "records": len(raw_records), "clean_records": len(clean_lengths),
            "coverage_gt_0_6_records": coverage_pass, "reference_exact_translation_records": exact_reference,
            "alternative_start_records": alternate_start, "exclusion_reason_counts": dict(sorted(reason_counts.items())),
            "clean_n_codons": distribution(clean_lengths), "clean_gc_fraction": distribution(clean_gc),
            "clean_coverage": distribution(clean_coverage),
        }
        expected_summary = next(item for item in summary["datasets"] if item["dataset"] == dataset)
        errors: List[str] = []
        compare_json(expected_summary, per_dataset_results[dataset], dataset, errors)
        check(f"raw_recompute_{dataset}", not errors, errors or per_dataset_results[dataset])

    check("all_qc_row_level_recompute", not all_field_errors and len(all_by_id) == sum(item["records"] for item in per_dataset_results.values()), {
        "error_count": len(all_field_errors), "first_errors": all_field_errors[:30], "expected_rows": sum(item["records"] for item in per_dataset_results.values()), "actual_rows": len(all_by_id)
    })
    check("exact_clean_set", set(clean_by_id) == expected_clean_ids, {
        "expected": len(expected_clean_ids), "actual": len(clean_by_id),
        "missing": sorted(expected_clean_ids - set(clean_by_id))[:20], "extra": sorted(set(clean_by_id) - expected_clean_ids)[:20],
    })
    clean_errors: List[str] = []
    for record_id, produced in clean_by_id.items():
        dataset = produced["dataset"]
        expected = independently_computed[dataset][produced["source_record_index"]]
        for field in ("source_key", "cds_dna", "translated_protein", "total_count", "coverage_count_gt_0_5"):
            compare_json(produced.get(field), expected[field], f"{record_id}.{field}", clean_errors, 1e-12)
        compare_json(produced.get("density_normalized"), expected["density_normalized"], f"{record_id}.density", clean_errors, 1e-12)
        reference = references[ORGANISM[dataset]].get(produced["source_key"])
        if reference != produced["translated_protein"]:
            clean_errors.append(f"{record_id}: reference translation mismatch")
    check("clean_row_values_and_reference_translation", not clean_errors, {"error_count": len(clean_errors), "first_errors": clean_errors[:30]})

    def unique_map(records: Iterable[dict]) -> Dict[str, dict]:
        groups: Dict[str, List[dict]] = defaultdict(list)
        for record in records:
            if record["source_key"]:
                groups[record["source_key"]].append(record)
        return {key: values[0] for key, values in groups.items() if len(values) == 1}

    left_all = unique_map(independently_computed["Mohammad19-1"])
    right_all = unique_map(independently_computed["Mohammad19-2"])
    shared = sorted(set(left_all) & set(right_all))
    identical = [(left_all[key], right_all[key]) for key in shared if left_all[key]["cds_dna"] == right_all[key]["cds_dna"]]
    left_clean = {record["source_key"]: record for record in independently_computed["Mohammad19-1"] if record["clean_eligible"]}
    right_clean = {record["source_key"]: record for record in independently_computed["Mohammad19-2"] if record["clean_eligible"]}
    both_clean = [(left_clean[key], right_clean[key]) for key in sorted(set(left_clean) & set(right_clean)) if left_clean[key]["cds_dna"] == right_clean[key]["cds_dna"]]
    replicate_errors: List[str] = []
    expected_replicate = summary["replicate_qc"]
    for key, value in (("shared_unique_source_keys", len(shared)), ("identical_cds_pairs", len(identical)), ("both_clean_pairs", len(both_clean))):
        compare_json(expected_replicate.get(key), value, f"replicate.{key}", replicate_errors)
    compare_json(expected_replicate["all_identical_cds_pairs"], profile_metrics(identical), "replicate.all", replicate_errors)
    compare_json(expected_replicate["both_clean_pairs_metrics"], profile_metrics(both_clean), "replicate.clean", replicate_errors)
    check("replicate_metrics_recompute", not replicate_errors, replicate_errors or {
        "shared_unique_source_keys": len(shared), "identical_cds_pairs": len(identical), "both_clean_pairs": len(both_clean),
        "both_clean_metrics": profile_metrics(both_clean),
    })

    artifact_errors = []
    for item in summary["artifacts"].values():
        path = Path(item["path"])
        if sha256(path) != item["sha256"]:
            artifact_errors.append(str(path))
    check("artifact_sha256", not artifact_errors, artifact_errors or summary["artifacts"])
    check("source_and_boundary_metadata", summary["source_commit"] == SOURCE_COMMIT and summary["utr_status"] == "not_provided_by_ribomimo_source" and "raw reads" in summary["source_semantics"], {
        "source_commit": summary["source_commit"], "utr_status": summary["utr_status"], "source_semantics": summary["source_semantics"]
    })

    git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.repo, text=True).strip()
    report = {
        "task": "RK-03", "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "verification": "independent raw-source recompute without importing the production QC module",
        "production_code_git_commit": git_commit,
        "production_script_sha256": sha256(args.repo / "scripts/a8_rk03_ribomimo_qc.py"),
        "checks": checks,
        "totals": {
            "raw_records": sum(item["records"] for item in per_dataset_results.values()),
            "clean_records": len(expected_clean_ids),
            "per_dataset": per_dataset_results,
        },
        "limitations": [
            "Author-processed A-site count matrices; no independent raw-read alignment or P-site remapping was performed.",
            "The source matrices do not provide UTRs.",
            "Clean is a reference- and coverage-qualified mechanism table, not authorization for functional-model training or a functional OOD result.",
        ],
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    for source, name in (
        (args.clean_dir / "qc_summary.json", "ribomimo_qc_summary.json"),
        (args.clean_dir / "artifact_manifest.json", "ribomimo_artifact_manifest.json"),
        (args.raw_dir / "ribomimo_integrity.json", "ribomimo_raw_integrity.json"),
        (args.reference_dir / "refseq_download_manifest.json", "reference_download_manifest.json"),
        (args.reference_dir / "ecoli_protein_supplement_manifest.json", "ecoli_protein_supplement_manifest.json"),
    ):
        if source.exists():
            (args.output.parent / name).write_bytes(source.read_bytes())
    print(json.dumps({"status": report["status"], "checks": len(checks), "failed": [item["name"] for item in checks if not item["pass"]], "totals": report["totals"]}, ensure_ascii=False))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
