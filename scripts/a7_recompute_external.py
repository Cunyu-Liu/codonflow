"""Recompute actual-budget external reference outputs without ranking or padding."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import feasible_edit, gc_fraction, split_codons
from codonflow.core.motifs import motif_penalty_score
from codonflow.data.dataset import read_fasta
from codonflow.eval.anytime import FrozenReference, anytime_curve
from codonflow.eval.metrics import cai, cai_weights_from_rscu, mfe, pairwise_ned
from scripts.a7_summarize_g2 import BUDGETS, point_at_budget


def recompute_external(payload, source, calibration, rscu):
    if payload.get("status") != "done" or payload.get("benchmark_sha256") is None:
        raise ValueError("external reference requires a completed benchmark payload")
    if payload["source_sha256"] != hashlib.sha256(source.encode()).hexdigest():
        raise ValueError("external source hash mismatch")
    weights = cai_weights_from_rscu(rscu)
    frozen = FrozenReference.from_dict(calibration)
    methods = {}
    for name, method in payload["methods"].items():
        if method.get("status") == "architectural_exclusion":
            methods[name] = {"status": "architectural_exclusion", "reason": method.get("reason"),
                             "solutions": [], "n_unique": 0}
            continue
        if method.get("status") != "done":
            raise ValueError(f"incomplete external method: {name}")
        solutions = method["solutions"]
        if len(solutions) != method["n_unique"] or len(set(solutions)) != len(solutions):
            raise ValueError(f"external solution count mismatch: {name}")
        if not solutions or not all(feasible_edit(sequence, source) for sequence in solutions):
            raise ValueError(f"external identity failure: {name}")
        points = []
        for budget, sequence in enumerate(solutions, 1):
            objectives = [cai(sequence, weights), -mfe(sequence),
                          -abs(gc_fraction(sequence) - 0.55),
                          -motif_penalty_score(sequence) / len(split_codons(sequence))]
            if not np.isfinite(objectives).all():
                raise ValueError(f"non-finite external objective: {name}")
            points.append({"budget": budget, "sequence": sequence, "objectives": objectives})
        covered = [budget for budget in BUDGETS if len(points) >= budget]
        methods[name] = {
            "status": "done", "n_unique": len(points), "identity_rate": 1.0,
            "actual_budget_auc": anytime_curve(points, frozen)["auc"],
            "ned": pairwise_ned(solutions), "covered_frozen_budgets": covered,
            "missing_frozen_budgets": [budget for budget in BUDGETS if budget not in covered],
            "budgets": {str(budget): point_at_budget(points, budget) for budget in covered},
            "points": points,
            "legacy_generation_costs": {
                "elapsed_s": method.get("elapsed_s"), "forward_calls": method.get("forward_calls"),
                "generator_calls": method.get("generator_calls"),
                "terminal_reward_evaluations": method.get("terminal_reward_evaluations"),
                "unique_terminal_reward_calls": method.get("unique_terminal_reward_calls"),
                "time_semantics": "legacy_generation_time_not_end_to_end",
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
    args = parser.parse_args()
    source_path = Path(args.input)
    payload = json.loads(source_path.read_text())
    records = {header.split()[0]: sequence for header, sequence in read_fasta(args.benchmark_fasta)}
    source = records[payload["record_id"]]
    if hashlib.sha256(Path(args.benchmark_fasta).read_bytes()).hexdigest() != payload["benchmark_sha256"]:
        raise ValueError("benchmark hash mismatch")
    rscu_path = Path(args.rscu_json)
    if hashlib.sha256(rscu_path.read_bytes()).hexdigest() != payload["rscu_sha256"]:
        raise ValueError("RSCU hash mismatch")
    rscu = json.loads(rscu_path.read_text())
    calibration_path = Path(args.calibration_dir) / f"{payload['record_id']}.json"
    calibration = json.loads(calibration_path.read_text())
    if calibration["source_sha256"] != payload["source_sha256"]:
        raise ValueError("calibration source mismatch")
    methods = recompute_external(payload, source, calibration, rscu)
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(f"refusing to overwrite external audit: {out}")
    result = {
        "protocol": "a7_external_actual_budget_v1", "exploratory_not_gate": True,
        "scientific_gate_passed": False, "not_a_method_ranking": True,
        "record_id": payload["record_id"], "seed": payload["seed"],
        "input_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "benchmark_sha256": payload["benchmark_sha256"], "rscu_sha256": payload["rscu_sha256"],
        "calibration_sha256": hashlib.sha256(calibration_path.read_bytes()).hexdigest(),
        "initialization": "protein_only_external_reference",
        "objectives_recomputed_from_raw_sequences": True, "methods": methods,
        "interpretation": "Actual external output only. No padding, no natural-source comparison, no SOTA claim.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(out)
    print(json.dumps({"out": str(out), "methods": sorted(methods), "not_a_method_ranking": True}))


if __name__ == "__main__":
    main()
