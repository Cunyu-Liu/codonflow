#!/usr/bin/env python3
"""Execute frozen real-budget simple-search trajectories on unique18 development records."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from codonflow.core.codon import feasible_edit, gc_fraction, split_codons
from codonflow.core.motifs import motif_penalty_score
from codonflow.data.dataset import read_fasta
from codonflow.eval.anytime import FrozenReference, dense_budget_step_auc_v2
from codonflow.eval.metrics import cai, cai_weights_from_rscu, mfe, pairwise_ned
from codonflow.models.guided_sampler import synonymous_x0
from codonflow.models.simple_search import SimpleSearch


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def text_sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    os.replace(temporary, path)
    return text_sha256(text)


def safe_name(record_id):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", record_id)


def pareto_indices(values):
    points = np.asarray(values, dtype=float)
    if points.ndim != 2 or not len(points):
        raise ValueError("pareto input must be a nonempty matrix")
    ge = np.all(points[None, :, :] >= points[:, None, :], axis=2)
    gt = np.any(points[None, :, :] > points[:, None, :], axis=2)
    dominated = np.any(ge & gt, axis=1)
    return np.flatnonzero(~dominated).tolist()


def summarize_budget(points, dense_curve, budget):
    selected = points[:budget]
    if len(selected) != budget:
        raise ValueError("incomplete real-budget prefix")
    objectives = np.asarray([row["objectives"] for row in selected], dtype=float)
    return {
        "budget": budget,
        "hypervolume_normalized": float(dense_curve[budget - 1]["hv"]),
        "n_scored": len(selected),
        "n_pareto_points": len(pareto_indices(objectives)),
        "per_axis_best": np.max(objectives, axis=0).tolist(),
        "pairwise_ned": float(pairwise_ned([row["sequence"] for row in selected], rng=np.random.default_rng(0))),
    }


def run_path(root, record_id, method, seed):
    return Path(root) / "runs" / safe_name(record_id) / f"{method}_s{seed}.json"


def valid_existing(path, protocol_sha, record_id, source, initial, method, seed, budget, calibration_sha, rscu_sha):
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    expected = {
        "protocol_sha256": protocol_sha,
        "record_id": record_id,
        "source_sha256": text_sha256(source),
        "initial_sha256": text_sha256(initial),
        "method": method,
        "seed": seed,
        "status": "done",
        "n_points": budget,
        "calibration_sha256": calibration_sha,
        "rscu_sha256": rscu_sha,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"existing output mismatch {key}: {path}")
    if [row.get("budget") for row in payload.get("points", [])] != list(range(1, budget + 1)):
        raise ValueError(f"existing output is not a complete dense trajectory: {path}")
    if payload.get("dense", {}).get("auc") is None:
        raise ValueError(f"existing output has no dense AUC: {path}")
    return payload


def execute_job(job):
    (protocol, protocol_sha, record_id, source, seed, method, output_root,
     budget, code_commit, resume) = job
    started = time.perf_counter()
    calibration_path = Path(protocol["calibration_dir"]) / f"{safe_name(record_id)}.json"
    calibration = json.loads(calibration_path.read_text())
    calibration_sha = sha256(calibration_path)
    if calibration["source_sha256"] != text_sha256(source):
        raise ValueError(f"calibration source mismatch: {record_id}")
    initial = synonymous_x0(source, np.random.default_rng(seed * 1009))
    output = run_path(output_root, record_id, method, seed)
    if output.exists():
        if not resume:
            raise FileExistsError(f"refusing to overwrite existing output: {output}")
        existing = valid_existing(output, protocol_sha, record_id, source, initial, method, seed,
                                  budget, calibration_sha, protocol["rscu_sha256"])
        return descriptor(existing, output, skipped=True)

    cai_weights = cai_weights_from_rscu(json.loads(Path(protocol["rscu_json"]).read_text()))
    scoring_seconds = [0.0]

    def objectives(sequence):
        before = time.perf_counter()
        values = [
            cai(sequence, cai_weights),
            -mfe(sequence),
            -abs(gc_fraction(sequence) - protocol["gc_target"]),
            -motif_penalty_score(sequence) / len(split_codons(sequence)),
        ]
        scoring_seconds[0] += time.perf_counter() - before
        return values

    frozen = FrozenReference.from_dict(calibration)
    result = SimpleSearch(
        initial,
        objectives,
        protocol["weights"],
        seed=seed,
        rho=protocol["rho"],
        initial_temperature=protocol["initial_temperature"],
        final_temperature=protocol["final_temperature"],
        normalization=(frozen.reference, frozen.scale),
        uniform_operator=protocol["uniform_operator"],
    ).run(method, max_unique_scorer=budget, max_attempts=protocol["max_attempts"])
    if result.status != "done" or len(result.points) != budget:
        raise RuntimeError(f"incomplete search {record_id}/{method}/s{seed}: {result.status}, {len(result.points)}")
    if [row["budget"] for row in result.points] != list(range(1, budget + 1)):
        raise RuntimeError("non-contiguous real scorer budgets")
    identities = [feasible_edit(row["sequence"], source) for row in result.points]
    if not all(identities):
        raise RuntimeError("non-synonymous output")
    dense = dense_budget_step_auc_v2(result.points, frozen, max_budget=budget)
    secondary = [summarize_budget(result.points, dense["curve"], b)
                 for b in protocol["secondary_budgets"] if b <= budget]
    wall = time.perf_counter() - started
    payload = {
        "schema": "a8-rk06-simple-search-dense-run-v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha,
        "status": "done",
        "record_id": record_id,
        "seed": seed,
        "method": method,
        "source_sha256": text_sha256(source),
        "initial_sha256": text_sha256(initial),
        "initial_index": 0,
        "benchmark_sha256": protocol["benchmark_sha256"],
        "calibration_sha256": calibration_sha,
        "rscu_sha256": protocol["rscu_sha256"],
        "code_commit": code_commit,
        "n_points": len(result.points),
        "points": result.points,
        "dense": dense,
        "dense_budget_step_auc_v2": dense["auc"],
        "secondary_budgets": secondary,
        "identity_rate": float(np.mean(identities)),
        "cost": {
            "cache_before_requests": 0,
            "unique_scorer_calls": len(result.points),
            "model_forward_calls": 0,
            "generator_calls": result.attempts,
            "terminal_reward_evaluations": result.terminal_evaluations,
            "wall_clock_seconds": wall,
            "search_elapsed_seconds": result.elapsed_s,
            "scoring_seconds": scoring_seconds[0],
            "generation_cache_proposal_seconds": max(0.0, result.elapsed_s - scoring_seconds[0]),
            "dense_metric_and_audit_seconds": max(0.0, wall - result.elapsed_s),
            "worker_per_run": 1,
        },
        "scope": "real development proxy-scorer trajectory; no functional label, external dense trajectory, CodonFlow generator, or SOTA result",
        "untouched24_used": False,
        "functional_untouched_used": False,
        "sota_claim": False,
    }
    atomic_json(output, payload)
    return descriptor(payload, output, skipped=False)


def descriptor(payload, path, skipped=False):
    secondary = {str(row["budget"]): row for row in payload["secondary_budgets"]}
    return {
        "record_id": payload["record_id"],
        "seed": payload["seed"],
        "method": payload["method"],
        "path": str(path),
        "sha256": sha256(path),
        "status": payload["status"],
        "n_points": payload["n_points"],
        "identity_rate": payload["identity_rate"],
        "dense_budget_step_auc_v2": payload["dense"]["auc"],
        "dense_area": payload["dense"]["area"],
        "endpoint_hv": payload["dense"]["endpoint_hv"],
        "endpoint_hv_B500": payload["dense"]["endpoint_hv"] if payload["n_points"] == 500 else None,
        "secondary_budgets": secondary,
        "cost": payload["cost"],
        "initial_sha256": payload["initial_sha256"],
        "calibration_sha256": payload["calibration_sha256"],
        "skipped_existing": skipped,
    }


def holm_adjust(p_values):
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty(len(p), dtype=float)
    running = 0.0
    m = len(p)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[index]))
        adjusted[index] = running
    return adjusted


def paired_inference(descriptors, protocol):
    records = sorted({row["record_id"] for row in descriptors})
    methods = protocol["methods"][1:]
    endpoints = protocol["primary_endpoints"]
    values = {}
    for method in protocol["methods"]:
        for endpoint in endpoints:
            matrix = np.empty((len(records), len(protocol["seeds"])), dtype=float)
            for i, record in enumerate(records):
                for j, seed in enumerate(protocol["seeds"]):
                    row = next(row for row in descriptors if row["record_id"] == record
                               and row["seed"] == seed and row["method"] == method)
                    if endpoint == "dense_budget_step_auc_v2":
                        matrix[i, j] = row["dense_budget_step_auc_v2"]
                    else:
                        matrix[i, j] = row["secondary_budgets"]["500"]["hypervolume_normalized"]
            values[(method, endpoint)] = matrix.mean(axis=1)
    tests = []
    for method in methods:
        for endpoint in endpoints:
            delta = values[(method, endpoint)] - values[("uniform", endpoint)]
            observed = float(delta.mean())
            boot_rng = np.random.default_rng(protocol["statistics"]["bootstrap_seed"])
            indices = boot_rng.integers(0, len(records), size=(protocol["statistics"]["paired_bootstrap_resamples"], len(records)))
            boot = delta[indices].mean(axis=1)
            perm_rng = np.random.default_rng(protocol["statistics"]["permutation_seed"])
            flips = perm_rng.choice(np.array([-1.0, 1.0]), size=(protocol["statistics"]["paired_sign_flip_permutations"], len(records)))
            null = (flips * delta).mean(axis=1)
            p = (1 + int(np.sum(np.abs(null) >= abs(observed) - 1e-15))) / (len(null) + 1)
            tests.append({
                "method": method,
                "comparator": "uniform",
                "endpoint": endpoint,
                "effect": observed,
                "ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
                "sign_flip_p": float(min(1.0, p)),
                "per_record_effects": delta.tolist(),
                "n_records": len(records),
            })
    adjusted = holm_adjust([row["sign_flip_p"] for row in tests])
    for row, holm in zip(tests, adjusted):
        row["holm_p"] = float(holm)
        row["supported_advantage"] = bool(row["ci95"][0] > 0 and holm < 0.05)
    return tests


def strict_dominance(descriptors):
    loaded = {(row["record_id"], row["seed"], row["method"]): json.loads(Path(row["path"]).read_text())
              for row in descriptors}
    methods = sorted({row["method"] for row in descriptors})
    output = []
    for method_a in methods:
        for method_b in methods:
            if method_a >= method_b:
                continue
            fractions = []
            for row in descriptors:
                if row["method"] != method_a:
                    continue
                key = (row["record_id"], row["seed"])
                a = np.asarray([p["objectives"] for p in loaded[key + (method_a,)]["points"]], dtype=float)
                b = np.asarray([p["objectives"] for p in loaded[key + (method_b,)]["points"]], dtype=float)
                a = a[pareto_indices(a)]
                b = b[pareto_indices(b)]
                a_dominated = np.any(np.all(b[None, :, :] >= a[:, None, :], axis=2)
                                     & np.any(b[None, :, :] > a[:, None, :], axis=2), axis=1)
                b_dominated = np.any(np.all(a[None, :, :] >= b[:, None, :], axis=2)
                                     & np.any(a[None, :, :] > b[:, None, :], axis=2), axis=1)
                fractions.append([float(a_dominated.mean()), float(b_dominated.mean())])
            output.append({
                "method_a": method_a,
                "method_b": method_b,
                "budget": 500,
                "mean_fraction_a_strictly_dominated_by_b": float(np.mean(fractions, axis=0)[0]),
                "mean_fraction_b_strictly_dominated_by_a": float(np.mean(fractions, axis=0)[1]),
                "interpretation": "secondary proxy-output dominance only; not functional superiority",
            })
    return output


def aggregate(descriptors, protocol, protocol_sha, formal, code_commit):
    try:
        import RNA
        rna_version = RNA.__version__
    except ImportError:
        rna_version = None
    checks = []
    def check(name, condition):
        checks.append({"check": name, "pass": bool(condition)})
    expected = protocol["expected_run_count"] if formal else len(descriptors)
    expected_points = protocol["max_unique_scorer"] if formal else None
    check("expected_run_count", len(descriptors) == expected)
    check("all_runs_done", all(row["status"] == "done" for row in descriptors))
    check("all_identity", all(row["identity_rate"] == 1.0 for row in descriptors))
    check("all_finite_auc", all(math.isfinite(row["dense_budget_step_auc_v2"]) for row in descriptors))
    if formal:
        check("all_500_real_points", all(row["n_points"] == expected_points for row in descriptors))
        check("expected_unique_calls", sum(row["n_points"] for row in descriptors) == protocol["expected_unique_scorer_calls"])
        check("18_records", len({row["record_id"] for row in descriptors}) == protocol["expected_record_count"])
        check("four_methods", {row["method"] for row in descriptors} == set(protocol["methods"]))
        check("three_seeds", {row["seed"] for row in descriptors} == set(protocol["seeds"]))
    method_summary = []
    for method in protocol["methods"]:
        rows = [row for row in descriptors if row["method"] == method]
        if not rows:
            continue
        method_summary.append({
            "method": method,
            "n_runs": len(rows),
            "mean_dense_auc": float(np.mean([row["dense_budget_step_auc_v2"] for row in rows])),
            "mean_hv_B500": float(np.mean([row["endpoint_hv_B500"] for row in rows])) if all(row["n_points"] == 500 for row in rows) else None,
            "mean_endpoint_hv": float(np.mean([row["endpoint_hv"] for row in rows])),
            "mean_hv_B50": float(np.mean([row["secondary_budgets"]["50"]["hypervolume_normalized"] for row in rows])) if rows[0]["n_points"] >= 50 else None,
            "mean_hv_B100": float(np.mean([row["secondary_budgets"]["100"]["hypervolume_normalized"] for row in rows])) if rows[0]["n_points"] >= 100 else None,
            "sum_unique_scorer_calls": sum(row["n_points"] for row in rows),
            "sum_terminal_requests": sum(row["cost"]["terminal_reward_evaluations"] for row in rows),
            "sum_wall_clock_seconds": sum(row["cost"]["wall_clock_seconds"] for row in rows),
            "sum_scoring_seconds": sum(row["cost"]["scoring_seconds"] for row in rows),
            "sum_generation_cache_proposal_seconds": sum(row["cost"]["generation_cache_proposal_seconds"] for row in rows),
            "sum_dense_metric_and_audit_seconds": sum(row["cost"]["dense_metric_and_audit_seconds"] for row in rows),
        })
    tests = paired_inference(descriptors, protocol) if formal else []
    dominance = strict_dominance(descriptors) if formal else []
    ok = all(row["pass"] for row in checks)
    return {
        "schema": "a8-rk06-simple-search-dense-unique18-v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha,
        "status": "DONE_SIMPLE_SEARCH_DENSE_DEVELOPMENT" if formal and ok else ("SMOKE_PASS" if ok else "PRODUCTION_FAILED"),
        "overall_pass": ok,
        "formal_full_panel": formal,
        "code_commit": code_commit,
        "population": protocol["population"],
        "n_runs": len(descriptors),
        "n_unique_scorer_calls": sum(row["n_points"] for row in descriptors),
        "method_summary": method_summary,
        "primary_tests": tests,
        "bidirectional_strict_dominance_B500": dominance,
        "runs": sorted(descriptors, key=lambda row: (row["record_id"], row["seed"], row["method"])),
        "checks": checks,
        "check_counts": {"total": len(checks), "passed": sum(row["pass"] for row in checks), "failed": sum(not row["pass"] for row in checks)},
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "ViennaRNA": rna_version, "platform": platform.platform()},
        "external_actual_set_dense_policy": protocol["external_actual_sets"],
        "time_matched_external_comparison": False,
        "untouched24_used": False,
        "functional_untouched_used": False,
        "functional_labels_used": False,
        "scientific_gate_passed": False,
        "rk_g1_closed": False,
        "expensive_generator_training_authorized": False,
        "manuscript_submittable": False,
        "sota_claim": False,
        "conclusion": "Real dense simple-search proxy trajectories only; positive or negative paired effects do not establish functional effectiveness, CodonFlow-RK improvement, external SOTA, RK-G1, or generator readiness.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--summary-output")
    parser.add_argument("--record-id")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--methods", nargs="+")
    parser.add_argument("--max-budget", type=int)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    protocol_path = Path(args.protocol)
    protocol = json.loads(protocol_path.read_text())
    protocol_sha = sha256(protocol_path)
    if not math.isfinite(mfe("AUGAAAUAA")):
        raise RuntimeError("ViennaRNA is unavailable or returned non-finite MFE; refusing production")
    if sha256(protocol["benchmark_fasta"]) != protocol["benchmark_sha256"]:
        raise ValueError("benchmark hash mismatch")
    if sha256(protocol["rscu_json"]) != protocol["rscu_sha256"]:
        raise ValueError("RSCU hash mismatch")
    if sha256(protocol["calibration_acceptance"]) != protocol["calibration_acceptance_sha256"]:
        raise ValueError("calibration acceptance hash mismatch")
    records = [(header.split()[0], sequence) for header, sequence in read_fasta(protocol["benchmark_fasta"])]
    if args.record_id:
        records = [row for row in records if row[0] == args.record_id]
        if len(records) != 1:
            raise ValueError("record-id must identify exactly one benchmark record")
    seeds = [args.seed] if args.seed is not None else protocol["seeds"]
    if any(seed not in protocol["seeds"] for seed in seeds):
        raise ValueError("seed outside frozen protocol")
    methods = args.methods or protocol["methods"]
    if any(method not in protocol["methods"] for method in methods):
        raise ValueError("method outside frozen protocol")
    budget = args.max_budget or protocol["max_unique_scorer"]
    if budget < 2 or budget > protocol["max_unique_scorer"]:
        raise ValueError("budget outside frozen protocol")
    output_root = Path(args.output_root or protocol["artifact_root"])
    formal = (not args.record_id and args.seed is None and not args.methods
              and budget == protocol["max_unique_scorer"]
              and output_root == Path(protocol["artifact_root"]))
    code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if formal:
        tracked = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).strip()
        staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True).strip()
        if tracked or staged:
            raise RuntimeError("formal production requires clean tracked worktree")
    jobs = [(protocol, protocol_sha, record, source, seed, method, str(output_root), budget, code_commit, args.resume)
            for record, source in records for seed in seeds for method in methods]
    workers = args.workers or (protocol["execution"]["formal_workers"] if formal else 1)
    descriptors = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(execute_job, job) for job in jobs]
        for future in as_completed(futures):
            row = future.result()
            descriptors.append(row)
            print(json.dumps({"record_id": row["record_id"], "seed": row["seed"], "method": row["method"],
                              "status": row["status"], "dense_auc": row["dense_budget_step_auc_v2"],
                              "skipped_existing": row["skipped_existing"]}), flush=True)
    descriptors.sort(key=lambda row: (row["record_id"], row["seed"], row["method"]))
    summary = aggregate(descriptors, protocol, protocol_sha, formal, code_commit)
    default_summary = ROOT / "audits/20261120/RK06" / ("simple_search_dense_unique18_v1.json" if formal else "simple_search_dense_smoke_v1.json")
    summary_path = Path(args.summary_output or default_summary)
    text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(text)
    if formal:
        artifact_summary = output_root / "simple_search_dense_unique18_v1.json"
        artifact_summary.parent.mkdir(parents=True, exist_ok=True)
        artifact_summary.write_text(text)
        manifest = {
            "schema": "a8-rk06-simple-search-dense-artifact-manifest-v1",
            "protocol_sha256": protocol_sha,
            "summary_path": str(summary_path),
            "summary_sha256": sha256(summary_path),
            "artifact_summary_path": str(artifact_summary),
            "artifact_summary_sha256": sha256(artifact_summary),
            "run_count": len(descriptors),
            "run_files": [{"path": row["path"], "sha256": row["sha256"]} for row in descriptors],
        }
        atomic_json(ROOT / "audits/20261120/RK06/simple_search_dense_artifact_manifest.json", manifest)
    print(json.dumps({"status": summary["status"], "overall_pass": summary["overall_pass"],
                      "n_runs": summary["n_runs"], "n_unique_scorer_calls": summary["n_unique_scorer_calls"],
                      "summary": str(summary_path)}), flush=True)
    if not summary["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
