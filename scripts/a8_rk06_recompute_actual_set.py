"""A8-RK06: independently rescore actual external CDS sets without dense padding."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from codonflow.core.codon import feasible_edit, gc_fraction, split_codons
from codonflow.core.motifs import motif_penalty_score
from codonflow.data.dataset import read_fasta
from codonflow.eval.actual_set import summarize_actual_set
from codonflow.eval.anytime import FrozenReference
from codonflow.eval.metrics import cai, cai_weights_from_rscu, mfe, pairwise_ned


def recompute_actual_set(payload, source, calibration, rscu):
    """Recompute objectives from raw CDS; reported objectives are only compared."""
    if payload.get("status") != "done" or payload.get("benchmark_sha256") is None:
        raise ValueError("external reference requires a completed benchmark payload")
    if payload["source_sha256"] != hashlib.sha256(source.encode()).hexdigest():
        raise ValueError("external source hash mismatch")
    weights = cai_weights_from_rscu(rscu)
    frozen = FrozenReference.from_dict(calibration)
    methods = {}
    for name, method in payload["methods"].items():
        if method.get("status") == "architectural_exclusion":
            methods[name] = {
                "status": "architectural_exclusion",
                "reason": method.get("reason"),
                "solutions": [],
                "n_unique": 0,
                "dense_budget_step_auc_v2": None,
            }
            continue
        if method.get("status") != "done":
            raise ValueError(f"incomplete external method: {name}")
        solutions = method["solutions"]
        if len(solutions) != method["n_unique"] or len(set(solutions)) != len(solutions):
            raise ValueError(f"external solution count mismatch: {name}")
        if not solutions or not all(feasible_edit(sequence, source) for sequence in solutions):
            raise ValueError(f"external identity failure: {name}")

        points = []
        for index, sequence in enumerate(solutions, 1):
            objectives = [
                cai(sequence, weights),
                -mfe(sequence),
                -abs(gc_fraction(sequence) - 0.55),
                -motif_penalty_score(sequence) / len(split_codons(sequence)),
            ]
            if not np.isfinite(objectives).all():
                raise ValueError(f"non-finite external objective: {name}")
            points.append({
                "output_id": f"{name}_{index:04d}",
                "sequence": sequence,
                "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
                "objectives": objectives,
            })

        reported = method.get("obj_vectors")
        max_abs_difference = None
        objectives_match = None
        if reported is not None:
            reported_array = np.asarray(reported, dtype=float)
            recomputed_array = np.asarray([point["objectives"] for point in points], dtype=float)
            if reported_array.shape != recomputed_array.shape or not np.isfinite(reported_array).all():
                raise ValueError(f"reported objective shape/value mismatch: {name}")
            max_abs_difference = float(np.max(np.abs(reported_array - recomputed_array)))
            objectives_match = bool(np.allclose(reported_array, recomputed_array, rtol=0.0, atol=1e-9))

        actual = summarize_actual_set(points, frozen)
        methods[name] = {
            "status": "done",
            "n_unique": len(points),
            "identity_rate": 1.0,
            "evaluation_mode": "actual_set_only",
            "dense_budget_step_auc_v2": None,
            "dense_auc_unavailable_reason": "no_real_dense_budget_trajectory",
            "actual_set": actual,
            "ned": pairwise_ned(solutions),
            "points": points,
            "reported_objectives_match": objectives_match,
            "max_abs_reported_objective_difference": max_abs_difference,
            "stored_objectives_used_for_scoring": False,
            "legacy_generation_costs": {
                "cache_before_requests": method.get("cache_before_requests"),
                "generation_seconds": method.get("elapsed_s"),
                "wall_clock_seconds": None,
                "forward_calls": method.get("forward_calls"),
                "generator_calls": method.get("generator_calls"),
                "terminal_reward_evaluations": method.get("terminal_reward_evaluations"),
                "unique_terminal_reward_calls": method.get("unique_terminal_reward_calls"),
                "hardware": None,
                "parallelism": None,
                "time_semantics": "legacy_generation_time_not_end_to_end; unknown fields remain null",
            },
        }
    return methods


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--calibration-dir", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()

    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True).strip())
    code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    if dirty and not args.allow_dirty:
        raise ValueError("refusing real rescoring with a dirty scorer worktree; commit code first or use --allow-dirty for diagnostics")

    started = time.perf_counter()
    source_path = Path(args.input)
    payload = json.loads(source_path.read_text())
    benchmark_path = Path(args.benchmark_fasta)
    records = {header.split()[0]: sequence for header, sequence in read_fasta(benchmark_path)}
    source = records[payload["record_id"]]
    if hashlib.sha256(benchmark_path.read_bytes()).hexdigest() != payload["benchmark_sha256"]:
        raise ValueError("benchmark hash mismatch")
    rscu_path = Path(args.rscu_json)
    if hashlib.sha256(rscu_path.read_bytes()).hexdigest() != payload["rscu_sha256"]:
        raise ValueError("RSCU hash mismatch")
    rscu = json.loads(rscu_path.read_text())
    calibration_path = Path(args.calibration_dir) / f"{payload['record_id']}.json"
    calibration = json.loads(calibration_path.read_text())
    if calibration["source_sha256"] != payload["source_sha256"]:
        raise ValueError("calibration source mismatch")

    methods = recompute_actual_set(payload, source, calibration, rscu)
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(f"refusing to overwrite actual-set audit: {out}")
    result = {
        "protocol": "a8_rk06_actual_set_v1",
        "exploratory_not_gate": True,
        "scientific_gate_passed": False,
        "not_a_method_ranking": True,
        "record_id": payload["record_id"],
        "seed": payload["seed"],
        "input_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "benchmark_sha256": payload["benchmark_sha256"],
        "rscu_sha256": payload["rscu_sha256"],
        "calibration_sha256": hashlib.sha256(calibration_path.read_bytes()).hexdigest(),
        "original_generator_code_commit": payload.get("code_commit"),
        "scorer_code_commit": code_commit,
        "scorer_code_dirty": dirty,
        "initialization": "protein_only_external_reference",
        "objectives_recomputed_from_raw_sequences": True,
        "stored_objectives_used_for_scoring": False,
        "reanalysis_elapsed_s_not_generation_cost": time.perf_counter() - started,
        "methods": methods,
        "interpretation": "Actual external output only. No dense padding, no synthetic origin, no natural-source comparison, no SOTA claim.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(out)
    print(json.dumps({
        "out": str(out),
        "methods": sorted(methods),
        "not_a_method_ranking": True,
        "scorer_code_commit": code_commit,
        "scorer_code_dirty": dirty,
    }))


if __name__ == "__main__":
    main()
