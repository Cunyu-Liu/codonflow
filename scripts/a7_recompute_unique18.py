"""Independently recompute unique18 objectives and NED from frozen solutions."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import feasible_edit
from codonflow.core.motifs import motif_penalty_score
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import cai, cai_weights_from_rscu, pairwise_ned
from codonflow.eval.mfe_parallel import mfe_batch_parallel
from codonflow.train.run_pretrain import file_sha256, git_commit
from scripts.a7_audit_unique18 import EXPECTED_METHODS


def recompute_method(result, source, weights, gc_target, fold):
    if result.get("status") != "done":
        return {"status": result.get("status", "missing"), "recomputed": False,
                "matches": False, "reason": "method_not_done"}
    solutions = result.get("solutions", [])
    stored = result.get("obj_vectors", [])
    if not solutions or len(solutions) != len(stored) or len(set(solutions)) != len(solutions):
        return {"status": "done", "recomputed": False, "matches": False,
                "reason": "empty_duplicate_or_misaligned_solutions"}
    mfes = fold(solutions)
    recomputed = np.asarray([
        [cai(sequence, weights), -mfe,
         -abs((sequence.count("G") + sequence.count("C")) / len(sequence) - gc_target),
         -motif_penalty_score(sequence)]
        for sequence, mfe in zip(solutions, mfes)
    ], dtype=float)
    stored_array = np.asarray(stored, dtype=float)
    if stored_array.shape != recomputed.shape or not np.isfinite(recomputed).all():
        return {"status": "done", "recomputed": False, "matches": False,
                "reason": "invalid_objective_shape_or_nonfinite_recomputation"}
    recomputed_ned = pairwise_ned(solutions)
    stored_ned = result.get("ned")
    objective_matches = np.allclose(stored_array, recomputed, rtol=1e-9, atol=1e-9)
    ned_matches = stored_ned is not None and math.isclose(
        float(stored_ned), recomputed_ned, rel_tol=1e-9, abs_tol=1e-9)
    identities = [feasible_edit(sequence, source) for sequence in solutions]
    counts_match = (result.get("n_solutions") == len(solutions)
                    and result.get("n_unique") == len(set(solutions)))
    return {
        "status": "done",
        "recomputed": True,
        "matches": bool(objective_matches and ned_matches and all(identities)
                        and counts_match and result.get("identity_rate") == 1.0),
        "n_solutions": len(solutions),
        "n_unique": len(set(solutions)),
        "counts_match": counts_match,
        "identity_all": all(identities),
        "stored_ned": stored_ned,
        "recomputed_ned": recomputed_ned,
        "max_abs_objective_difference": float(np.max(np.abs(stored_array - recomputed))),
        "max_abs_axis_differences": np.max(np.abs(stored_array - recomputed), axis=0).tolist(),
        "recomputed_mfes": [float(value) for value in mfes],
    }


def recompute_payload(payload, source, weights, fold=mfe_batch_parallel):
    methods = payload.get("methods", {})
    gc_target = float(payload.get("gc_target", 0.55))
    rows = {name: recompute_method(methods.get(name, {}), source, weights, gc_target, fold)
            for name in EXPECTED_METHODS}
    source_matches = payload.get("source_sha256") == hashlib.sha256(source.encode()).hexdigest()
    return {
        "record_id": payload.get("record_id"),
        "seed": payload.get("seed"),
        "status": payload.get("status", "unknown"),
        "source_sha256_matches": source_matches,
        "methods": rows,
        "matches": bool(payload.get("status") == "done" and source_matches
                        and all(row["matches"] for row in rows.values())),
    }


def recompute_unique18(input_dir, benchmark_fasta, rscu_json, seeds=(0, 1, 2),
                       fold=mfe_batch_parallel, record_ids=None):
    benchmark_records = {header.split()[0]: sequence for header, sequence in read_fasta(benchmark_fasta)}
    if record_ids:
        unknown = set(record_ids) - set(benchmark_records)
        if unknown:
            raise ValueError(f"unknown record-id values: {sorted(unknown)}")
        benchmark_records = {record_id: benchmark_records[record_id] for record_id in record_ids}
    weights = cai_weights_from_rscu(json.loads(Path(rscu_json).read_text()))
    rows = []
    for record_id, source in benchmark_records.items():
        for seed in seeds:
            path = Path(input_dir) / f"{record_id}_s{seed}.json"
            if not path.exists():
                rows.append({"record_id": record_id, "seed": seed, "path": str(path),
                             "status": "missing", "matches": False})
                continue
            payload = json.loads(path.read_text())
            row = recompute_payload(payload, source, weights, fold=fold)
            row.update({"path": str(path), "artifact_sha256": file_sha256(path),
                        "benchmark_sha256_matches": payload.get("benchmark_sha256") == file_sha256(benchmark_fasta),
                        "rscu_sha256_matches": payload.get("rscu_sha256") == file_sha256(rscu_json),
                        "metadata_matches": payload.get("record_id") == record_id and payload.get("seed") == seed})
            row["matches"] = bool(row["matches"] and row["benchmark_sha256_matches"]
                                  and row["rscu_sha256_matches"] and row["metadata_matches"])
            rows.append(row)
    try:
        import RNA
        rna_version = RNA.__version__
    except ImportError:
        rna_version = None
    complete = bool(rows) and all(row["matches"] for row in rows)
    return {
        "protocol": "a7_unique18_independent_mfe_ned_v1",
        "code_commit": git_commit(),
        "benchmark_sha256": file_sha256(benchmark_fasta),
        "rscu_sha256": file_sha256(rscu_json),
        "rna_version": rna_version,
        "folding_conditions": "ViennaRNA default fold_compound.mfe; DNA converted T->U",
        "ned_rule": "all unordered pairs; Levenshtein/max(length); pairwise_ned default seed only if >200 sequences",
        "objective_rtol": 1e-9,
        "objective_atol": 1e-9,
        "n_records": len(benchmark_records),
        "seeds": list(seeds),
        "mfe_ned_independently_recomputed": complete,
        "complete_all_requested_seeds": complete,
        "records": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--record-id", action="append", dest="record_ids",
                        help="restrict to one or more exact record IDs for independent sharding")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = recompute_unique18(args.input_dir, args.benchmark_fasta, args.rscu_json,
                                args.seeds, record_ids=args.record_ids)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(out.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(out)
    print(json.dumps({"out": str(out), "n_rows": len(result["records"]),
                      "n_matching": sum(row["matches"] for row in result["records"]),
                      "complete_all_requested_seeds": result["complete_all_requested_seeds"]}))


if __name__ == "__main__":
    main()
