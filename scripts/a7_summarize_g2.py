"""Summarize raw G2 Pareto fronts, best objectives, coverage, and costs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.train.run_pretrain import git_commit
from scripts.a7_plot_g2 import load_gate_inputs

BUDGETS = (50, 100, 500)


def domination_matrix(first, second):
    first_values = np.asarray(first, dtype=float)
    second_values = np.asarray(second, dtype=float)
    if (first_values.ndim != 2 or second_values.ndim != 2
            or first_values.shape[1] != second_values.shape[1]
            or not np.isfinite(first_values).all() or not np.isfinite(second_values).all()):
        raise ValueError("dominance requires finite objective matrices with matching dimensions")
    return (np.all(first_values[:, None, :] >= second_values[None, :, :], axis=2)
            & np.any(first_values[:, None, :] > second_values[None, :, :], axis=2))


def pareto_indices(points):
    values = np.asarray([point["objectives"] for point in points], dtype=float)
    dominated = domination_matrix(values, values).any(axis=0)
    return np.flatnonzero(~dominated).tolist()


def dominated_fraction(first, second):
    if not first or not second:
        raise ValueError("non-dominated coverage requires two nonempty fronts")
    return float(domination_matrix(
        [point["objectives"] for point in first],
        [point["objectives"] for point in second],
    ).any(axis=0).mean())


def point_at_budget(points, budget):
    selected = [point for point in points if point["budget"] <= budget]
    if not selected:
        raise ValueError("each run must have scored points at every frozen budget")
    front = [selected[index] for index in pareto_indices(selected)]
    best = []
    values = np.asarray([point["objectives"] for point in selected], dtype=float)
    for objective in range(values.shape[1]):
        point = selected[int(np.argmax(values[:, objective]))]
        best.append({
            "objective_index": objective,
            "value": float(point["objectives"][objective]),
            "objectives": point["objectives"],
            "budget": point["budget"],
            "sequence_sha256": hashlib.sha256(point["sequence"].encode()).hexdigest(),
        })
    return {"pareto_front": front, "best_by_objective": best}


def summarize_run(arm, gene, seed, method, payload):
    if len(payload["points"]) != 500 or payload["status"] != "done":
        raise ValueError("secondary analysis requires complete 500-point runs")
    return {
        "arm": arm,
        "gene": gene,
        "seed": seed,
        "method": method,
        "n_unique": len({point["sequence"] for point in payload["points"]}),
        "auc": payload["anytime"]["auc"],
        "ned": payload["ned"],
        "costs": payload["costs"],
        "budgets": {str(budget): point_at_budget(payload["points"], budget) for budget in BUDGETS},
    }


def write_csv(path, fields, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def generate_summary(gate_path, out_prefix):
    gate, arms = load_gate_inputs(gate_path)
    runs = []
    comparisons = []
    for arm, payloads in arms:
        arm_runs = {}
        for (gene, seed, method), payload in sorted(payloads.items()):
            run = summarize_run(arm["arm"], gene, seed, method, payload)
            runs.append(run)
            arm_runs[(gene, seed, method)] = run
        diversity = {row["gene"]: row for row in arm["diversity"]}
        for gene_row in arm["statistics"]["per_gene"]:
            gene = gene_row["gene"]
            baseline = gene_row["strongest_simple_method"]
            for seed in (0, 1, 2):
                learned = arm_runs[(gene, seed, "learned")]
                simple = arm_runs[(gene, seed, baseline)]
                row = {
                    "arm": arm["arm"],
                    "gene": gene,
                    "seed": seed,
                    "strongest_simple_method": baseline,
                    "learned_auc": learned["auc"],
                    "simple_auc": simple["auc"],
                    "learned_ned": learned["ned"],
                    "simple_ned": simple["ned"],
                    "ned_ratio": diversity[gene]["ratio"],
                    "learned_elapsed_s": learned["costs"]["elapsed_s"],
                    "simple_elapsed_s": simple["costs"]["elapsed_s"],
                    "learned_forward_calls": learned["costs"]["forward_calls"],
                    "simple_forward_calls": simple["costs"]["forward_calls"],
                }
                for budget in BUDGETS:
                    learned_front = learned["budgets"][str(budget)]["pareto_front"]
                    simple_front = simple["budgets"][str(budget)]["pareto_front"]
                    row[f"learned_nondominated_b{budget}"] = len(learned_front)
                    row[f"simple_nondominated_b{budget}"] = len(simple_front)
                    row[f"simple_dominated_by_learned_b{budget}"] = dominated_fraction(
                        learned_front, simple_front)
                    row[f"learned_dominated_by_simple_b{budget}"] = dominated_fraction(
                        simple_front, learned_front)
                comparisons.append(row)
    out = Path(out_prefix)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw_path = Path(f"{out}.secondary.json")
    raw_path.write_text(json.dumps({
        "protocol": "a7_g2_secondary_v1",
        "gate_sha256": hashlib.sha256(Path(gate_path).read_bytes()).hexdigest(),
        "gate_passed": gate["passed"],
        "objective_direction": "maximize_all_four",
        "budgets": list(BUDGETS),
        "runs": runs,
    }, indent=2))
    comparison_fields = list(comparisons[0])
    comparison_path = Path(f"{out}.comparison.csv")
    write_csv(comparison_path, comparison_fields, comparisons)
    best_rows = []
    cost_rows = []
    for run in runs:
        identity = {key: run[key] for key in ("arm", "gene", "seed", "method")}
        cost_rows.append({**identity, "n_unique": run["n_unique"], "auc": run["auc"],
                          "ned": run["ned"], **run["costs"]})
        for budget in BUDGETS:
            for best in run["budgets"][str(budget)]["best_by_objective"]:
                best_rows.append({
                    **identity, "scorer_budget": budget,
                    "objective_index": best["objective_index"], "value": best["value"],
                    "objectives": best["objectives"], "first_best_budget": best["budget"],
                    "sequence_sha256": best["sequence_sha256"],
                })
    best_path = Path(f"{out}.best_at_budget.csv")
    write_csv(best_path, ["arm", "gene", "seed", "method", "scorer_budget", "objective_index",
                          "value", "objectives", "first_best_budget", "sequence_sha256"], best_rows)
    cost_path = Path(f"{out}.costs.csv")
    cost_fields = ["arm", "gene", "seed", "method", "n_unique", "auc", "ned",
                   "forward_calls", "base_state_evaluations", "rollout_batch_forwards",
                   "rollout_state_transitions", "terminal_reward_evaluations",
                   "unique_terminal_reward_calls", "elapsed_s"]
    write_csv(cost_path, cost_fields, cost_rows)
    outputs = {}
    for path in (raw_path, comparison_path, best_path, cost_path):
        outputs[path.name] = {"path": str(path),
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {
        "protocol": "a7_g2_secondary_manifest_v1",
        "gate_path": str(gate_path),
        "gate_sha256": hashlib.sha256(Path(gate_path).read_bytes()).hexdigest(),
        "gate_passed": gate["passed"],
        "code_commit": git_commit(),
        "n_runs_including_shared_baselines_per_arm": len(runs),
        "outputs": outputs,
    }
    manifest_path = Path(f"{out}.secondary.manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", required=True)
    parser.add_argument("--out-prefix", required=True)
    args = parser.parse_args()
    print(generate_summary(args.gate, args.out_prefix))


if __name__ == "__main__":
    main()
