#!/usr/bin/env python3
"""Run the compatibility-patched official RiboMIMO loader on complete matrices."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

DATASETS = ("Subtelny14", "Mohammad16", "Mohammad19-1", "Mohammad19-2")
SOURCE_COMMIT = "094c693d4df45f4b29f5a3209b31c452a39092a5"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-src", required=True)
    parser.add_argument("--matrix-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    runtime_src = Path(args.runtime_src).resolve()
    matrix_root = Path(args.matrix_root).resolve()
    output_root = Path(args.output_root).resolve()
    report_path = Path(args.report).resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Output root must be absent or empty: {output_root}")
    if report_path.exists():
        raise FileExistsError(f"Refusing to overwrite report: {report_path}")
    (output_root / "data").mkdir(parents=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(runtime_src))
    from model import DataLoader  # compatibility-patched official implementation

    results = {}
    for dataset in DATASETS:
        source_matrix = matrix_root / f"{dataset}.txt"
        runtime_matrix = output_root / "data" / f"{dataset}.txt"
        shutil.copy2(source_matrix, runtime_matrix)
        if sha256(source_matrix) != sha256(runtime_matrix):
            raise RuntimeError(f"Matrix copy differs: {dataset}")
        loader = DataLoader(str(output_root) + "/", dataset)
        genes = list(loader.list_gene)
        if not genes:
            raise RuntimeError(f"No official-loader-eligible genes: {dataset}")
        lengths = np.array([len(loader.dict_seq_codon[gene]) for gene in genes])
        counts = Counter(genes)
        duplicate_ids = sorted(gene for gene, count in counts.items() if count > 1)
        results[dataset] = {
            "matrix_path": str(source_matrix),
            "matrix_sha256": sha256(source_matrix),
            "runtime_matrix_path": str(runtime_matrix),
            "runtime_matrix_sha256": sha256(runtime_matrix),
            "raw_records": sum(1 for _ in source_matrix.open()) // 3,
            "valid_sequence_records": len(loader.list_gene_all),
            "eligible_official_coverage_gt_0.6": len(genes),
            "unique_eligible_ids": len(counts),
            "duplicate_eligible_rows": len(genes) - len(counts),
            "duplicate_eligible_ids": duplicate_ids,
            "length_min": int(lengths.min()),
            "length_median": float(np.median(lengths)),
            "length_mean": float(np.mean(lengths)),
            "length_max": int(lengths.max()),
            "total_eligible_codons": int(lengths.sum()),
            "coverage_gt_0.7": len(loader.list_gene_coverage_7),
            "coverage_gt_0.8": len(loader.list_gene_coverage_8),
            "coverage_gt_0.9": len(loader.list_gene_coverage_9),
            "split_warning": "Official random gene splitting is not homology-, protein-, study- or functional-OOD; duplicate IDs are retained exactly as the official loader sees them.",
        }
        print(json.dumps({dataset: {k: v for k, v in results[dataset].items() if k != "duplicate_eligible_ids"}}, indent=2))

    report = {
        "schema_version": "a8-rk05-ribomimo-full-loader-preflight-v1",
        "status": "PASS",
        "source_commit": SOURCE_COMMIT,
        "runtime_src": str(runtime_src),
        "runtime_file_sha256": {
            name: sha256(runtime_src / name)
            for name in ("runRiboMIMO.py", "model.py", "utils.py", "getSaliency.py")
        },
        "output_root": str(output_root),
        "datasets": results,
        "official_protocol_defaults": {
            "num_repeat": 1,
            "num_fold": 10,
            "batch_size": 16,
            "max_epoch": 100,
            "early_stop": 5,
            "learning_rate": 0.001,
            "weight_decay": 0.000001,
            "seed": 1234,
            "sim": -1,
            "add_nt": True,
            "add_aa": True,
            "use_median": False,
        },
        "training_executed": False,
        "publication_metrics_reproduced": False,
        "ood_or_sota_claim": False,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "PASS", "report": str(report_path), "report_sha256": sha256(report_path)}, indent=2))


if __name__ == "__main__":
    main()
