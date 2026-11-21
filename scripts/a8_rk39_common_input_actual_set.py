#!/usr/bin/env python3
"""RK39 common-input, matched-cardinality actual-set comparison.

Search receives protein plus fixed TAA only. Native-source calibration is loaded
only after each search has finished and is used solely for common evaluation.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import time
from typing import Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codonflow.core.codon import (
    STANDARD_TABLE_1,
    SYNONYMOUS_CODONS,
    gc_fraction,
    normalize_to_dna,
    split_codons,
)
from codonflow.core.motifs import motif_penalty_score
from codonflow.data.dataset import read_fasta
from codonflow.eval.actual_set import summarize_actual_set
from codonflow.eval.anytime import FrozenReference
from codonflow.eval.metrics import cai, cai_weights_from_rscu, mfe, pairwise_ned
from codonflow.models.guided_sampler import synonymous_x0
from codonflow.models.simple_search import SimpleSearch

METHOD = "rk39_common_input_actual_set_v1"
SUMMARY_VERSION = 1


def sha(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def atomic_json(path: str | Path, payload: Mapping) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, target)


def safe_name(text: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in text)


def protein_from_cds(sequence: str) -> str:
    codons = split_codons(normalize_to_dna(sequence))
    if not codons:
        raise ValueError("empty CDS")
    aas = []
    for index, codon in enumerate(codons):
        if codon not in STANDARD_TABLE_1:
            raise ValueError(f"non-standard codon {codon}")
        aa = STANDARD_TABLE_1[codon]
        if aa == "*" and index != len(codons) - 1:
            raise ValueError("internal stop")
        aas.append(aa)
    if aas[-1] != "*" or aas.count("*") != 1:
        raise ValueError("CDS must contain exactly one terminal stop")
    return "".join(aas)


def protein_only_template(native_source_for_translation: str) -> str:
    """Translate to protein, then discard every native synonymous choice.

    The terminal stop is fixed to TAA to match the two primary external design
    families; no native nucleotide or native stop is retained.
    """
    protein = protein_from_cds(native_source_for_translation)
    codons = []
    for aa in protein:
        if aa == "*":
            codons.append("TAA")
        else:
            codons.append(SYNONYMOUS_CODONS[aa][0])
    return "".join(codons)


def protein_only_initial(native_source_for_translation: str, seed: int) -> str:
    template = protein_only_template(native_source_for_translation)
    initial = synonymous_x0(template, np.random.default_rng(seed * 1009))
    if not initial.endswith("TAA") or protein_from_cds(initial) != protein_from_cds(template):
        raise ValueError("protein-only initialization violated protein or fixed-stop identity")
    return initial


def objective_vector(sequence: str, cai_weights: Mapping[str, float], gc_target: float):
    return np.asarray([
        cai(sequence, cai_weights),
        -mfe(sequence),
        -abs(gc_fraction(sequence) - gc_target),
        -motif_penalty_score(sequence) / len(split_codons(sequence)),
    ], dtype=float)


def evaluate_actual_set(points: Sequence[Mapping], frozen: FrozenReference) -> dict:
    rows = [{
        "output_id": str(point.get("output_id", index)),
        "sequence": point["sequence"],
        "objectives": point["objectives"],
    } for index, point in enumerate(points)]
    summary = summarize_actual_set(rows, frozen)
    sequences = [row["sequence"] for row in rows]
    return {
        "n_actual_outputs": int(len(rows)),
        "n_unique_objective_vectors": int(summary["n_unique_objective_vectors"]),
        "n_pareto_points": int(summary["n_pareto_points"]),
        "hypervolume_normalized": float(summary["hypervolume_normalized"]),
        "pairwise_ned": float(pairwise_ned(sequences, rng=np.random.default_rng(0))),
        "dense_budget_step_auc_v2": None,
    }


def run_path(output_root: Path, record_id: str, seed: int, method: str) -> Path:
    return output_root / "runs" / safe_name(record_id) / f"seed{seed}" / f"{method}.json"


def valid_existing(path: Path, job: Mapping) -> dict | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    checks = [
        payload.get("schema") == "a8-rk39-common-input-run-v1",
        payload.get("status") == "done",
        payload.get("record_id") == job["record_id"],
        payload.get("seed") == job["seed"],
        payload.get("method") == job["method"],
        payload.get("protocol_sha256") == job["protocol_sha256"],
        payload.get("code_commit") == job["code_commit"],
        payload.get("source_sha256") == job["source_sha256"],
        payload.get("rscu_sha256") == job["rscu_sha256"],
        payload.get("initial_state_sha256") == text_sha(protein_only_initial(job["source"], job["seed"])),
        payload.get("matched_linear_design_k") == job["k"],
        len(payload.get("points", [])) == 11,
        [p.get("budget") for p in payload.get("points", [])] == list(range(1, 12)),
        payload.get("unique_scorer_calls") == 11,
        payload.get("search_normalization") is None,
        payload.get("native_source_used_in_search") is False,
        payload.get("terminal_stop") == "TAA",
    ]
    if not all(checks):
        raise ValueError(f"incomplete or mismatched existing run: {path}")
    return payload


def execute_job(job: Mapping) -> dict:
    started = time.perf_counter()
    record_id = job["record_id"]
    seed = int(job["seed"])
    method = job["method"]
    output_root = Path(job["output_root"])
    path = run_path(output_root, record_id, seed, method)
    if path.exists():
        if not job.get("resume"):
            raise ValueError(f"refuse to overwrite existing run: {path}")
        existing = valid_existing(path, job)
        assert existing is not None
        return run_descriptor(path, existing)

    initial = protein_only_initial(job["source"], seed)
    rscu = json.loads(Path(job["rscu_json"]).read_text())
    if sha(job["rscu_json"]) != job["rscu_sha256"]:
        raise ValueError("RSCU identity mismatch")
    cai_weights = cai_weights_from_rscu(rscu)
    scoring_seconds = [0.0]

    def objectives(sequence):
        before = time.perf_counter()
        values = objective_vector(sequence, cai_weights, job["gc_target"])
        scoring_seconds[0] += time.perf_counter() - before
        return values

    search = SimpleSearch(
        initial,
        objectives,
        job["weights"],
        seed=seed,
        initial_temperature=job["initial_temperature"],
        final_temperature=job["final_temperature"],
        rho=job["rho"],
        uniform_operator=job["uniform_operator"],
        normalization=None,
    )
    result = search.run(method, max_unique_scorer=job["max_unique_scorer"],
                        max_attempts=job["max_attempts"])
    if result.status != "done" or len(result.points) != 11:
        raise ValueError(f"search did not produce 11 real points: {record_id} seed{seed} {method}")
    if [point["budget"] for point in result.points] != list(range(1, 12)):
        raise ValueError("non-contiguous search budgets")
    if len(result.points) != 11:
        raise ValueError("unique-scorer accounting mismatch")

    template = protein_only_template(job["source"])
    protein = protein_from_cds(template)
    for point in result.points:
        if not point["sequence"].endswith("TAA"):
            raise ValueError("fixed TAA stop was not preserved")
        if protein_from_cds(point["sequence"]) != protein:
            raise ValueError("non-synonymous search output")
        if not np.isfinite(point["objectives"]).all():
            raise ValueError("non-finite objective")

    # Evaluation-only native calibration is deliberately loaded after search.
    calibration_path = Path(job["calibration_dir"]) / f"{safe_name(record_id)}.json"
    calibration = json.loads(calibration_path.read_text())
    if sha(calibration_path) != calibration["calibration_sha256"]:
        raise ValueError("calibration artifact identity mismatch")
    if calibration["source_sha256"] != job["source_sha256"]:
        raise ValueError("calibration source mismatch")
    frozen = FrozenReference.from_dict(calibration)
    prefix = [{
        "output_id": point["budget"],
        "sequence": point["sequence"],
        "objectives": point["objectives"],
    } for point in result.points[:job["k"]]]
    matched = evaluate_actual_set(prefix, frozen)

    payload = {
        "schema": "a8-rk39-common-input-run-v1",
        "protocol_id": job["protocol_id"],
        "protocol_sha256": job["protocol_sha256"],
        "code_commit": job["code_commit"],
        "status": "done",
        "record_id": record_id,
        "seed": seed,
        "method": method,
        "source_sha256": job["source_sha256"],
        "rscu_sha256": job["rscu_sha256"],
        "protein_sha256": text_sha(protein),
        "protein_only_template": template,
        "protein_only_template_sha256": text_sha(template),
        "initial_state": initial,
        "initial_state_sha256": text_sha(initial),
        "search_input_semantics": "protein_plus_fixed_TAA_only",
        "native_source_used_in_search": False,
        "native_derived_normalization_in_search": False,
        "search_normalization": None,
        "native_calibration_read_after_search": True,
        "terminal_stop": "TAA",
        "points": [{"budget": point["budget"], "sequence": point["sequence"],
                    "objectives": point["objectives"]} for point in result.points],
        "matched_linear_design_k": int(job["k"]),
        "matched_actual_set": matched,
        "max_attempts": int(job["max_attempts"]),
        "proposal_attempts": int(result.attempts),
        "cache_hits": int(result.terminal_evaluations - len(result.points)),
        "terminal_evaluations": int(result.terminal_evaluations),
        "unique_scorer_calls": int(len(result.points)),
        "cache_before_requests": 0,
        "model_forward_calls": 0,
        "objective_scoring_seconds": float(scoring_seconds[0]),
        "residual_generation_cache_proposal_seconds": float(max(0.0, result.elapsed_s - scoring_seconds[0])),
        "search_wall_seconds": float(result.elapsed_s),
        "run_wall_seconds_including_evaluation": float(time.perf_counter() - started),
        "dense_budget_step_auc_v2": None,
        "time_matched_comparison": False,
        "functional_untouched_evaluated": False,
        "sota_claim": False,
    }
    atomic_json(path, payload)
    return run_descriptor(path, payload)


def run_descriptor(path: Path, payload: Mapping) -> dict:
    return {
        "record_id": payload["record_id"],
        "seed": payload["seed"],
        "method": payload["method"],
        "path": str(path),
        "sha256": sha(path),
        "initial_state_sha256": payload["initial_state_sha256"],
        "matched_linear_design_k": payload["matched_linear_design_k"],
        "hypervolume_normalized": payload["matched_actual_set"]["hypervolume_normalized"],
        "pairwise_ned": payload["matched_actual_set"]["pairwise_ned"],
        "unique_scorer_calls": payload["unique_scorer_calls"],
        "objective_scoring_seconds": payload["objective_scoring_seconds"],
        "run_wall_seconds_including_evaluation": payload["run_wall_seconds_including_evaluation"],
    }


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    order = np.argsort(np.asarray(p_values, dtype=float))
    adjusted = np.empty(len(p_values), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted.tolist()


def paired_test(delta: np.ndarray, protocol: Mapping) -> dict:
    delta = np.asarray(delta, dtype=float)
    observed = float(delta.mean())
    stats = protocol["statistics"]
    rng = np.random.default_rng(stats["bootstrap_seed"])
    indices = rng.integers(0, len(delta), size=(stats["paired_bootstrap_resamples"], len(delta)))
    boot = delta[indices].mean(axis=1)
    rng = np.random.default_rng(stats["permutation_seed"])
    flips = rng.choice(np.asarray([-1.0, 1.0]),
                       size=(stats["paired_sign_flip_permutations"], len(delta)))
    null = (flips * delta).mean(axis=1)
    p = (1 + int(np.sum(np.abs(null) >= abs(observed) - 1e-15))) / (len(null) + 1)
    return {
        "effect": observed,
        "ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
        "sign_flip_p": float(min(1.0, p)),
        "per_record_effects": delta.tolist(),
        "n_records": int(len(delta)),
    }


def inference(descriptors: Sequence[Mapping], external: Mapping[str, Mapping], protocol: Mapping) -> dict:
    records = sorted(external)
    endpoints = protocol["primary_endpoints"]
    tests = []
    per_record = {record: {"record_id": record, "external": external[record], "methods": {}}
                  for record in records}
    for method in protocol["methods"]:
        for endpoint in endpoints:
            values = np.empty((len(records), len(protocol["seeds"])), dtype=float)
            baseline = np.asarray([external[record][endpoint] for record in records], dtype=float)
            for i, record in enumerate(records):
                per_record[record]["methods"][method] = {}
                for j, seed in enumerate(protocol["seeds"]):
                    row = next(row for row in descriptors if row["record_id"] == record
                               and row["seed"] == seed and row["method"] == method)
                    values[i, j] = float(row[endpoint])
                    per_record[record]["methods"][method][str(seed)] = {
                        "hypervolume_normalized": float(row["hypervolume_normalized"]),
                        "pairwise_ned": float(row["pairwise_ned"]),
                        "k": int(row["matched_linear_design_k"]),
                    }
            delta_by_seed = values - baseline[:, None]
            test = paired_test(delta_by_seed.mean(axis=1), protocol)
            test.update({
                "method": method,
                "comparator": protocol["primary_external_method"],
                "endpoint": endpoint,
                "seed_mean_effects": delta_by_seed.mean(axis=0).tolist(),
                "all_seed_effects_positive": bool(np.all(delta_by_seed.mean(axis=0) > 0)),
                "confirmatory": method == protocol["primary_method"],
                "supported_advantage": None,
                "holm_p": None,
            })
            tests.append(test)
    primary = [row for row in tests if row["confirmatory"]]
    adjusted = holm_adjust([row["sign_flip_p"] for row in primary])
    for row, holm in zip(primary, adjusted):
        row["holm_p"] = float(holm)
        row["supported_advantage"] = bool(row["ci95"][0] > 0 and holm < 0.05
                                            and row["all_seed_effects_positive"])
    gate = bool(all(row["supported_advantage"] for row in primary))
    return {"tests": tests, "primary_gate_passed": gate, "per_record": [per_record[r] for r in records]}


def git_state() -> tuple[str, bool]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    return commit, dirty


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/a8_rk39_common_input_actual_set_protocol_v1.json")
    parser.add_argument("--output-root")
    parser.add_argument("--summary")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    protocol_path = ROOT / args.protocol
    protocol = json.loads(protocol_path.read_text())
    if protocol["status"] != "FROZEN_BEFORE_PRODUCTION":
        raise ValueError("protocol is not frozen")
    protocol_sha = sha(protocol_path)
    benchmark = read_fasta(protocol["benchmark_fasta"])
    if sha(protocol["benchmark_fasta"]) != protocol["benchmark_sha256"]:
        raise ValueError("benchmark identity mismatch")
    matrix_path = Path(protocol["external_matrix"])
    if sha(matrix_path) != protocol["external_matrix_sha256"]:
        raise ValueError("external matrix identity mismatch")
    matrix = json.loads(matrix_path.read_text())
    matrix_records = {row["record_id"]: row for row in matrix["records"]}
    if set(benchmark) != set(matrix_records) or len(benchmark) != 18:
        raise ValueError("benchmark/external population mismatch")

    code_commit, dirty = git_state()
    if not args.smoke and dirty:
        raise ValueError("formal production requires a clean detached-commit worktree")
    output_root = Path(args.output_root or protocol["artifact_root"])
    summary_path = Path(args.summary or protocol["summary"])
    if args.smoke:
        records = [protocol["execution"]["smoke_record"]]
        seeds = [protocol["execution"]["smoke_seed"]]
    else:
        records = list(benchmark)
        seeds = list(protocol["seeds"])

    jobs = []
    for record_id in records:
        source = benchmark[record_id]
        source_sha = text_sha(source)
        external_record = matrix_records[record_id]
        if external_record["source_sha256"] != source_sha:
            raise ValueError(f"external source identity mismatch for {record_id}")
        points = external_record["methods"][protocol["primary_external_method"]]["points"]
        k = len({point["sequence"] for point in points})
        if not 1 <= k <= 11 or k != len(points):
            raise ValueError(f"invalid matched cardinality for {record_id}: {k}")
        if any(not point["sequence"].endswith("TAA") for point in points):
            raise ValueError("LinearDesign terminal-stop convention mismatch")
        for seed in seeds:
            for method in protocol["methods"]:
                jobs.append({**protocol, "protocol_path": str(protocol_path),
                             "protocol_sha256": protocol_sha, "code_commit": code_commit,
                             "output_root": str(output_root), "record_id": record_id,
                             "source": source, "source_sha256": source_sha,
                             "seed": seed, "method": method, "k": k})

    expected_jobs = 9 if args.smoke else protocol["expected_run_count"]
    if len(jobs) != expected_jobs:
        raise ValueError(f"job-count mismatch: {len(jobs)} != {expected_jobs}")
    for job in jobs:
        if Path(run_path(output_root, job["record_id"], job["seed"], job["method"])).exists() and not args.resume:
            raise ValueError("formal/smoke output already exists; use a new root or explicit validated resume")

    started = time.perf_counter()
    if args.workers == 1:
        descriptors = [execute_job(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            descriptors = list(pool.map(execute_job, jobs))
    descriptors.sort(key=lambda row: (list(benchmark).index(row["record_id"]),
                                      row["seed"], protocol["methods"].index(row["method"])))

    base = {
        "schema": "a8-rk39-common-input-actual-set-summary-v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_path": str(protocol_path),
        "protocol_sha256": protocol_sha,
        "code_commit": code_commit,
        "code_tracked_dirty_at_launch": dirty,
        "status": "PASS_SMOKE" if args.smoke else "PASS_COMPLETE_COMMON_INPUT_EVALUATION",
        "smoke": bool(args.smoke),
        "artifact_root": str(output_root),
        "benchmark_sha256": protocol["benchmark_sha256"],
        "external_matrix_sha256": protocol["external_matrix_sha256"],
        "rscu_sha256": protocol["rscu_sha256"],
        "n_runs": len(descriptors),
        "n_unique_scorer_calls": sum(row["unique_scorer_calls"] for row in descriptors),
        "runs": descriptors,
        "wall_seconds": float(time.perf_counter() - started),
        "input_semantics": protocol["input_semantics"],
        "time_matched_comparison": False,
        "functional_untouched_evaluated": False,
        "untouched24_evaluated": False,
        "new_functional_labels_read": False,
        "dense_external_curve_inferred": False,
        "external_sota_authorized": False,
        "sota_claim": False,
        "rk_g1_pass": False,
        "manuscript_submittable": False,
    }
    if args.smoke:
        base["expected_smoke_runs"] = 9
        base["expected_smoke_unique_scorer_calls"] = 99
        if base["n_unique_scorer_calls"] != 99:
            raise ValueError("smoke unique-scorer total mismatch")
        base["smoke_gate_passed"] = True
    else:
        if base["n_unique_scorer_calls"] != protocol["expected_unique_scorer_calls"]:
            raise ValueError("formal unique-scorer total mismatch")
        external = {}
        for record_id, record in matrix_records.items():
            calibration = json.loads((Path(protocol["calibration_dir"]) / f"{safe_name(record_id)}.json").read_text())
            frozen = FrozenReference.from_dict(calibration)
            method = record["methods"][protocol["primary_external_method"]]
            metrics = evaluate_actual_set(method["points"], frozen)
            if not np.isclose(metrics["hypervolume_normalized"], method["actual_set"]["hypervolume_normalized"],
                              rtol=0, atol=1e-12):
                raise ValueError(f"external hypervolume reproduction failed for {record_id}")
            if not np.isclose(metrics["pairwise_ned"], method["ned"], rtol=0, atol=1e-12):
                raise ValueError(f"external NED reproduction failed for {record_id}")
            external[record_id] = {**metrics, "k": len(method["points"])}
        infer = inference(descriptors, external, protocol)
        base.update(infer)
        base["common_input_proxy_task_resolved"] = infer["primary_gate_passed"]
        base["decision"] = ("PRIMARY_COMMON_INPUT_PROXY_PASS_DEVELOPMENT_ONLY"
                            if infer["primary_gate_passed"] else "COMMON_INPUT_ACTUAL_SET_TASK_UNRESOLVED")
        base["scientific_gate_passed"] = False
        base["allowed_conclusion"] = protocol["allowed_conclusion"]
        base["forbidden_conclusion"] = protocol["forbidden_conclusion"]
    atomic_json(summary_path, base)
    print(json.dumps({"summary": str(summary_path), "summary_sha256": sha(summary_path),
                      "n_runs": base["n_runs"], "n_unique_scorer_calls": base["n_unique_scorer_calls"],
                      "decision": base.get("decision", "SMOKE_ONLY")}, indent=2))


if __name__ == "__main__":
    main()
