#!/usr/bin/env python3
"""Read-only RK38 inventory of real baseline runs and untouched-data boundaries."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

SCHEMA = "a8-rk38-baseline-untouched-inventory-v1"
DETAIL_FIELDS = [
    "source_line", "raw_path", "raw_sha256", "record_id", "arm", "method", "seed",
    "status", "input_semantics", "budget_label", "n_attempts_or_points", "n_unique_outputs",
    "n_duplicate_or_unreturned", "identity_rate", "elapsed_s", "generator_calls",
    "model_forward_calls", "unique_terminal_reward_calls", "source_sha256", "code_commit",
    "device", "ordered_real_scorer_prefix", "actual_output_set", "dense_auc_available",
    "cost_semantics", "coverage_note",
]
CELL_FIELDS = [
    "record_id", "method", "matrix_status", "raw_n_unique", "matrix_n_unique",
    "sequence_set_exact", "hypervolume_normalized", "pairwise_ned", "n_pareto_points",
    "identity_rate", "seed", "raw_source",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path, expected_sha: str | None = None) -> dict[str, Any]:
    if expected_sha is not None:
        actual = sha256(path)
        if actual != expected_sha:
            raise ValueError(f"SHA256 mismatch for {path}: {actual} != {expected_sha}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def unique_sequences(sequences: list[str], declared_n_unique: int | None = None) -> list[str]:
    unique = list(dict.fromkeys(sequences))
    if any(not isinstance(seq, str) or not seq for seq in sequences):
        raise ValueError("Empty or non-string sequence in raw output")
    if declared_n_unique is not None and len(unique) != declared_n_unique:
        raise ValueError(f"Unique-count mismatch: observed {len(unique)} != declared {declared_n_unique}")
    return unique


def sequence_set_exact(raw_sequences: list[str], matrix_points: list[dict[str, Any]]) -> bool:
    matrix_sequences = [point.get("sequence") for point in matrix_points]
    if any(not isinstance(seq, str) for seq in matrix_sequences):
        raise ValueError("Matrix point lacks a raw sequence")
    return set(raw_sequences) == set(matrix_sequences) and len(raw_sequences) == len(matrix_sequences)


def cost_value(costs: dict[str, Any], *keys: str) -> float | int | None:
    for key in keys:
        value = costs.get(key)
        if value is not None:
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"Non-finite cost field {key}: {value}")
            return value
    return None


def dense_prefix_row(payload: dict[str, Any], path: Path, raw_sha: str, source_line: str,
                     arm: str, method: str, expected_points: int) -> dict[str, Any]:
    if payload.get("status") != "done":
        raise ValueError(f"Non-complete trajectory: {path}")
    points = payload.get("points", [])
    if len(points) != expected_points:
        raise ValueError(f"Point-count mismatch for {path}: {len(points)}")
    budgets = [point.get("budget") for point in points]
    if budgets != list(range(1, expected_points + 1)):
        raise ValueError(f"Non-contiguous real-scorer budgets: {path}")
    sequences = unique_sequences([point["sequence"] for point in points], payload.get("n_unique"))
    costs = payload.get("costs") or payload.get("cost") or {}
    wall = cost_value(costs, "elapsed_s", "wall_clock_seconds")
    if wall is None:
        wall = payload.get("elapsed_s", payload.get("wall_clock_seconds"))
    if wall is None or float(wall) < 0:
        raise ValueError(f"Missing wall-clock cost: {path}")
    return {
        "source_line": source_line,
        "raw_path": str(path),
        "raw_sha256": raw_sha,
        "record_id": payload["record_id"],
        "arm": arm,
        "method": method,
        "seed": payload["seed"],
        "status": payload["status"],
        "input_semantics": "natural_CDS_warm_start",
        "budget_label": f"B{expected_points}_ordered_unique_scorer_calls",
        "n_attempts_or_points": len(points),
        "n_unique_outputs": len(sequences),
        "n_duplicate_or_unreturned": len(points) - len(sequences),
        "identity_rate": 1.0,
        "elapsed_s": wall,
        "generator_calls": cost_value(costs, "generator_calls"),
        "model_forward_calls": cost_value(costs, "model_forward_calls", "forward_calls"),
        "unique_terminal_reward_calls": cost_value(costs, "unique_terminal_reward_calls", "unique_scorer_calls"),
        "source_sha256": payload.get("source_sha256"),
        "code_commit": payload.get("code_commit"),
        "device": payload.get("device", "cpu"),
        "ordered_real_scorer_prefix": True,
        "actual_output_set": True,
        "dense_auc_available": True,
        "cost_semantics": "raw frozen run-specific costs; not a uniform cross-method time comparison",
        "coverage_note": "contiguous B1..B500 points; no zero-filling or repeated-call padding",
    }


def inventory_a7(protocol: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spec = protocol["inputs"]["a7_g2"]
    root = Path(spec["root"])
    gate = read_json(Path(spec["gate"]), spec["gate_sha256"])
    execution = read_json(Path(spec["execution"]), spec["execution_sha256"])
    if gate.get("passed") is not False or execution.get("status") != "g2_complete":
        raise ValueError("A7 gate/execution boundary changed")
    if execution.get("scientific_gate_passed") is not False:
        raise ValueError("A7 execution unexpectedly claims scientific success")
    rows: list[dict[str, Any]] = []
    for arm in spec["arms"]:
        arm_root = root / arm
        learned_paths = sorted(arm_root.glob("*_learned_s*.json"))
        if len(learned_paths) != 54:
            raise ValueError(f"Expected 54 learned files for {arm}, found {len(learned_paths)}")
        for path in learned_paths:
            raw_sha = sha256(path)
            payload = read_json(path)
            row = dense_prefix_row(payload, path, raw_sha, "a7_g2", arm, "codonflow_learned", 500)
            if not str(row["device"]).startswith("cuda") or not row["model_forward_calls"]:
                raise ValueError(f"Learned run lacks real CUDA/forward calls: {path}")
            rows.append(row)
    shared_root = root / "shared_simple"
    for method in spec["simple_methods"]:
        paths = sorted(shared_root.glob(f"*_{method}_s*.json"))
        if len(paths) != 54:
            raise ValueError(f"Expected 54 shared {method} files, found {len(paths)}")
        for path in paths:
            raw_sha = sha256(path)
            payload = read_json(path)
            rows.append(dense_prefix_row(payload, path, raw_sha, "a7_g2", "shared_simple", method, 500))
    if len(rows) != spec["expected_raw_files"]:
        raise ValueError(f"A7 row count mismatch: {len(rows)}")
    return rows, {
        "raw_file_count": len(rows),
        "learned_cuda_runs": sum(row["method"] == "codonflow_learned" for row in rows),
        "simple_search_runs": sum(row["method"] != "codonflow_learned" for row in rows),
        "scientific_gate_passed": gate["passed"],
        "execution_status": execution["status"],
        "gate_sha256": spec["gate_sha256"],
        "execution_sha256": spec["execution_sha256"],
    }


def inventory_rk06(protocol: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spec = protocol["inputs"]["rk06_dense"]
    summary = read_json(Path(spec["summary"]), spec["summary_sha256"])
    runs = summary.get("runs", [])
    if len(runs) != spec["expected_runs"]:
        raise ValueError(f"RK06 summary run mismatch: {len(runs)}")
    rows = []
    for entry in runs:
        path = Path(entry["path"])
        raw_sha = sha256(path)
        if raw_sha != entry["sha256"]:
            raise ValueError(f"RK06 raw SHA mismatch: {path}")
        payload = read_json(path)
        for key in ("record_id", "method", "seed"):
            if payload[key] != entry[key]:
                raise ValueError(f"RK06 summary/raw {key} mismatch: {path}")
        row = dense_prefix_row(payload, path, raw_sha, "rk06_dense", "shared_simple", payload["method"], 500)
        if row["n_attempts_or_points"] != entry["n_points"] or row["unique_terminal_reward_calls"] != entry["cost"]["unique_scorer_calls"]:
            raise ValueError(f"RK06 summary/raw counts mismatch: {path}")
        rows.append(row)
    unique_calls = sum(int(row["unique_terminal_reward_calls"]) for row in rows)
    if unique_calls != spec["expected_unique_scorer_calls"]:
        raise ValueError(f"RK06 unique scorer total mismatch: {unique_calls}")
    return rows, {
        "raw_file_count": len(rows),
        "unique_scorer_calls": unique_calls,
        "summary_sha256": spec["summary_sha256"],
        "shared_with_a7_simple_search": True,
        "cost_note": "RK06 supplies terminal-scoring and finer cost fields for the same shared simple-search runs; not an additional independent method family.",
    }


def inventory_external(protocol: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    spec = protocol["inputs"]["external_actual_set"]
    matrix = read_json(Path(spec["matrix"]), spec["matrix_sha256"])
    independent = read_json(Path(spec["independent"]), spec["independent_sha256"])
    if independent.get("status") != "PASS" or matrix.get("scientific_gate_passed") is not False:
        raise ValueError("External matrix verification/boundary mismatch")
    if matrix.get("time_matched_comparison") is not False or matrix.get("sota_claim") is not False:
        raise ValueError("External matrix claim boundary mismatch")
    grid = read_json(Path(spec["lineardesign_grid"]), spec["lineardesign_grid_sha256"])
    grid_runs = grid.get("runs", [])
    if len(grid_runs) != spec["lineardesign_expected_runs"]:
        raise ValueError("LinearDesign grid count mismatch")
    ensemble = read_json(Path(spec["ensemble_report"]), spec["ensemble_report_sha256"])
    ensemble_records = ensemble.get("records", [])
    if len(ensemble_records) != spec["ensemble_expected_records"]:
        raise ValueError("EnsembleDesign record count mismatch")
    grid_by_record: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in grid_runs:
        if run.get("returncode") != 0:
            raise ValueError(f"LinearDesign failed run: {run.get('record_id')}")
        grid_by_record[run["record_id"]].append(run)
    ensemble_by_record = {record["record_id"]: record for record in ensemble_records}
    if len(ensemble_by_record) != len(ensemble_records):
        raise ValueError("Duplicate EnsembleDesign record")
    record_order = [record["record_id"] for record in matrix["records"]]
    if len(record_order) != 18 or len(set(record_order)) != 18:
        raise ValueError("External matrix must contain 18 unique records")
    legacy_by_seed_record: dict[tuple[int, str], tuple[Path, str, dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    for seed in range(3):
        root = Path(spec["legacy_root_template"].format(seed=seed))
        paths = [root / f"{record_id}_s{seed}.json" for record_id in record_order]
        if len(paths) != spec["legacy_files_per_seed"] or any(not path.is_file() for path in paths):
            raise ValueError(f"A6 seed{seed} frozen record files are incomplete")
        for path in paths:
            raw_sha = sha256(path)
            payload = read_json(path)
            if payload.get("status") != "done" or payload.get("seed") != seed:
                raise ValueError(f"A6 invalid payload: {path}")
            record_id = payload["record_id"]
            legacy_by_seed_record[(seed, record_id)] = (path, raw_sha, payload)
            for method in spec["legacy_methods"]:
                result = payload["methods"][method]
                sequences = result.get("solutions", [])
                unique = unique_sequences(sequences, result.get("n_unique"))
                calls = result.get("generator_calls")
                attempts = calls if calls is not None else len(sequences)
                status = result.get("status")
                rows.append({
                    "source_line": "a6_legacy_five_methods", "raw_path": str(path), "raw_sha256": raw_sha,
                    "record_id": record_id, "arm": "shared_legacy", "method": method, "seed": seed,
                    "status": status, "input_semantics": "protein_to_CDS_or_legacy_external",
                    "budget_label": "actual_output_set_not_ordered_budget",
                    "n_attempts_or_points": attempts, "n_unique_outputs": len(unique),
                    "n_duplicate_or_unreturned": attempts - len(unique),
                    "identity_rate": 1.0 if status == "done" else None,
                    "elapsed_s": result.get("elapsed_s"), "generator_calls": calls,
                    "model_forward_calls": None, "unique_terminal_reward_calls": None,
                    "source_sha256": payload.get("source_sha256"), "code_commit": payload.get("code_commit"),
                    "device": payload.get("device"), "ordered_real_scorer_prefix": False,
                    "actual_output_set": status == "done", "dense_auc_available": False,
                    "cost_semantics": "legacy generation wall clock; incomplete uniform hardware/end-to-end semantics",
                    "coverage_note": result.get("exclusion_reason") or "unordered actual outputs; repeated-call dense prefix unavailable",
                })
    for record_id in record_order:
        runs = grid_by_record[record_id]
        if len(runs) != 11:
            raise ValueError(f"LinearDesign record does not have 11 runs: {record_id}")
        sequences = unique_sequences([run["evaluation_sequence_dna"] for run in runs])
        grid_path = Path(spec["lineardesign_grid"])
        rows.append({
            "source_line": "lineardesign_lambda11", "raw_path": str(grid_path), "raw_sha256": spec["lineardesign_grid_sha256"],
            "record_id": record_id, "arm": "official_DP_grid", "method": "lineardesign_lambda11", "seed": None,
            "status": "done", "input_semantics": "protein_to_CDS", "budget_label": "11_lambda_calls_not_scorer_budget",
            "n_attempts_or_points": 11, "n_unique_outputs": len(sequences), "n_duplicate_or_unreturned": 11-len(sequences),
            "identity_rate": 1.0, "elapsed_s": sum(float(run["elapsed_s"]) for run in runs), "generator_calls": 11,
            "model_forward_calls": None, "unique_terminal_reward_calls": None,
            "source_sha256": runs[0].get("source_sha256"), "code_commit": grid.get("source_commit"),
            "device": "cpu", "ordered_real_scorer_prefix": False, "actual_output_set": True, "dense_auc_available": False,
            "cost_semantics": "sum of 11 single-worker official-process wall clocks; shared rescoring excluded",
            "coverage_note": "lambda values are objective weights; B11 prefix exists only in separately frozen RK16",
        })
        record = ensemble_by_record[record_id]
        if record.get("returncode") != 0 or len(record.get("runs", [])) != 11:
            raise ValueError(f"EnsembleDesign incomplete record: {record_id}")
        sequences = unique_sequences([run["evaluation_sequence_dna"] for run in record["runs"]], record.get("unique_output_sequences"))
        rows.append({
            "source_line": "ensembledesign_11run", "raw_path": spec["ensemble_report"], "raw_sha256": spec["ensemble_report_sha256"],
            "record_id": record_id, "arm": "official_ensemble", "method": "ensembledesign_11run", "seed": None,
            "status": "done", "input_semantics": "protein_to_CDS", "budget_label": "11_internal_runs_not_unified_scorer_budget",
            "n_attempts_or_points": 11, "n_unique_outputs": len(sequences), "n_duplicate_or_unreturned": 11-len(sequences),
            "identity_rate": 1.0, "elapsed_s": record["elapsed_s"], "generator_calls": 11,
            "model_forward_calls": None, "unique_terminal_reward_calls": None,
            "source_sha256": record.get("source_cds_sha256"), "code_commit": ensemble.get("commit"),
            "device": "cpu", "ordered_real_scorer_prefix": False, "actual_output_set": True, "dense_auc_available": False,
            "cost_semantics": "one four-thread official process including 11 runs and internal EFE scoring",
            "coverage_note": "B11 prefix exists only in separately frozen RK16; no unified time-matched comparison",
        })
    matrix_records = {record["record_id"]: record for record in matrix["records"]}
    cells: list[dict[str, Any]] = []
    for record_id in record_order:
        for method in spec["method_order"]:
            matrix_method = matrix_records[record_id]["methods"][method]
            if method in spec["legacy_methods"]:
                path, _, payload = legacy_by_seed_record[(0, record_id)]
                raw_sequences = payload["methods"][method].get("solutions", [])
                raw_source = str(path)
            elif method == "lineardesign_lambda11":
                raw_sequences = [run["evaluation_sequence_dna"] for run in grid_by_record[record_id]]
                raw_source = spec["lineardesign_grid"]
            else:
                raw_sequences = [run["evaluation_sequence_dna"] for run in ensemble_by_record[record_id]["runs"]]
                raw_source = spec["ensemble_report"]
            raw_unique = unique_sequences(raw_sequences)
            points = matrix_method.get("points", [])
            exact = sequence_set_exact(raw_unique, points)
            if not exact or len(raw_unique) != matrix_method.get("n_unique"):
                raise ValueError(f"External raw/matrix sequence mismatch: {record_id}/{method}")
            actual_set = matrix_method.get("actual_set", {})
            cells.append({
                "record_id": record_id, "method": method, "matrix_status": matrix_method.get("status"),
                "raw_n_unique": len(raw_unique), "matrix_n_unique": matrix_method.get("n_unique"),
                "sequence_set_exact": exact, "hypervolume_normalized": actual_set.get("hypervolume_normalized"),
                "pairwise_ned": matrix_method.get("ned"), "n_pareto_points": actual_set.get("n_pareto_points"),
                "identity_rate": matrix_method.get("identity_rate"), "seed": 0 if method in spec["legacy_methods"] else None,
                "raw_source": raw_source,
            })
    if len(cells) != 126:
        raise ValueError("External cell count mismatch")
    recomputed_summary = {}
    for method in spec["method_order"]:
        selected = [cell for cell in cells if cell["method"] == method]
        recomputed_summary[method] = {
            "mean_hypervolume_normalized": mean(float(cell["hypervolume_normalized"]) for cell in selected),
            "mean_ned": mean(float(cell["pairwise_ned"]) for cell in selected),
            "total_actual_outputs": sum(int(cell["matrix_n_unique"]) for cell in selected),
            "min_identity_rate": min(float(cell["identity_rate"]) for cell in selected),
        }
        frozen = matrix["method_summary"][method]
        for key, value in recomputed_summary[method].items():
            if not math.isclose(float(value), float(frozen[key]), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"External method summary mismatch: {method}/{key}")
    return rows, cells, {
        "legacy_raw_files": 54,
        "legacy_rows_three_seeds": 270,
        "seed0_actual_set_cells": len(cells),
        "method_summary": recomputed_summary,
        "descriptive_highest_mean_hv_method": matrix.get("descriptive_highest_mean_hv_method"),
        "dense_budget_step_auc_v2": None,
        "time_matched_comparison": False,
        "sota_claim": False,
        "matrix_sha256": spec["matrix_sha256"],
        "independent_sha256": spec["independent_sha256"],
    }


def untouched_inventory(protocol: dict[str, Any]) -> dict[str, Any]:
    spec = protocol["inputs"]["functional_untouched_metadata_only"]
    split = read_json(Path(spec["split_summary"]), spec["split_summary_sha256"])
    independent = read_json(Path(spec["split_independent"]), spec["split_independent_sha256"])
    sequence = read_json(Path(spec["sequence_ood_summary"]), spec["sequence_ood_summary_sha256"])
    rk20 = read_json(Path(spec["rk20_finalization"]), spec["rk20_finalization_sha256"])
    counts = split["counts"]["functional_untouched"]
    if counts["rows"] != spec["expected_rows"] or counts["clusters"] != spec["expected_clusters"]:
        raise ValueError("Untouched row/cluster boundary changed")
    if counts["unique_construct_signature_groups"] != spec["expected_signature_groups"]:
        raise ValueError("Untouched signature-group boundary changed")
    if counts["variant_classes"].get("synonymous_single_codon") != spec["expected_synonymous_single_codon_rows"]:
        raise ValueError("Untouched synonymous subset boundary changed")
    if independent.get("status") != "PASS" or any(check.get("status") != "PASS" for check in independent.get("checks", [])):
        raise ValueError("Frozen split independent verification is not clean")
    overlaps = split.get("leakage", {}).get("pairwise_overlaps", {})
    nonzero = {kind: {pair: value for pair, value in values.items() if value != 0} for kind, values in overlaps.items()}
    nonzero = {kind: values for kind, values in nonzero.items() if values}
    if nonzero:
        raise ValueError(f"Frozen split contains nonzero overlap: {nonzero}")
    if sequence.get("functional_untouched_evaluated") is not False or rk20.get("functional_untouched_evaluated") is not False:
        raise ValueError("Frozen records indicate untouched evaluation occurred")
    if rk20.get("functional_robustness_pass") is not False or rk20.get("rk_g1_pass") is not False:
        raise ValueError("RK20 gate boundary changed")
    stat_files = []
    for item in [sequence["inputs"]["original_split"], sequence["artifacts"]["sequence_ood_csv"]]:
        path = Path(item["path"])
        stat = path.stat()  # metadata only: never open, hash, or parse the frozen partition rows
        if stat.st_size != item["bytes"]:
            raise ValueError(f"Frozen partition byte count mismatch: {path}")
        stat_files.append({"path": str(path), "bytes": stat.st_size, "frozen_sha256_not_recomputed": item["sha256"], "access": "stat_only"})
    return {
        "rows": counts["rows"], "clusters": counts["clusters"],
        "unique_construct_signature_groups": counts["unique_construct_signature_groups"],
        "sources": counts["sources"], "datasets": counts["datasets"], "variant_classes": counts["variant_classes"],
        "synonymous_single_codon_rows": counts["variant_classes"]["synonymous_single_codon"],
        "independent_multiprotein_untouched_dataset_count": 0,
        "potential_single_protein_confirmation_cohorts": 1,
        "generalizable_fixed_protein_multiprotein_claim_supported": False,
        "functional_robustness_pass": rk20["functional_robustness_pass"],
        "fully_passed_sequence_ood_tests": rk20["fully_passed_sequence_ood_tests"],
        "functional_untouched_evaluated": False,
        "functional_untouched_evaluation_authorized_now": False,
        "new_label_or_outcome_read": False,
        "new_file_sha256_computed": False,
        "stat_only_files": stat_files,
        "reason_not_opened": "RK20 passed only 2/8 sequence-OOD tests and did not pass functional robustness; no new untouched protocol or authorization exists.",
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    if path.exists():
        raise FileExistsError(f"Refuse to overwrite {path}")
    with path.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"Refuse to overwrite {path}")
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    os.replace(temp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, default=None, help="Optional clean-reproduction output override")
    parser.add_argument("--audit-root", type=Path, default=None, help="Optional clean-reproduction audit override")
    args = parser.parse_args()
    protocol = read_json(args.protocol)
    if protocol.get("schema") != "a8-rk38-baseline-untouched-inventory-protocol-v1":
        raise ValueError("Unexpected protocol schema")
    if not protocol["population"]["functional_untouched_used"] is False:
        raise ValueError("This inventory is not authorized for functional-untouched evaluation")
    a7_rows, a7_summary = inventory_a7(protocol)
    rk06_rows, rk06_summary = inventory_rk06(protocol)
    external_rows, external_cells, external_summary = inventory_external(protocol)
    rows = a7_rows + rk06_rows + external_rows
    expected = protocol["output"]["expected_raw_run_rows"]
    observed = dict(Counter(row["source_line"] for row in rows))
    if observed != expected or len(rows) != protocol["output"]["expected_detailed_rows"]:
        raise ValueError(f"Detailed inventory count mismatch: {observed}")
    rk16_spec = protocol["inputs"]["rk16_dense_prefix"]
    rk16_matrix = read_json(Path(rk16_spec["matrix"]), rk16_spec["matrix_sha256"])
    rk16_audit = read_json(Path(rk16_spec["audit"]), rk16_spec["audit_sha256"])
    if rk16_audit.get("status") != "PASS" or rk16_audit.get("primary_real_generation_call_count") != rk16_spec["expected_primary_real_generation_calls"]:
        raise ValueError("RK16 prefix audit mismatch")
    if rk16_audit.get("time_matched_comparison") is not False or rk16_matrix.get("time_matched_comparison") is not False:
        raise ValueError("RK16 time boundary changed")
    untouched = untouched_inventory(protocol)
    artifact_root = args.artifact_root or Path(protocol["output"]["artifact_root"])
    audit_root = args.audit_root or Path(protocol["output"]["audit_root"])
    artifact_root.mkdir(parents=True, exist_ok=False)
    audit_root.mkdir(parents=True, exist_ok=True)
    detail_path = artifact_root / "baseline_run_inventory_v1.csv"
    cells_path = artifact_root / "external_actual_set_cells_v1.csv"
    summary_path = audit_root / "rk38_baseline_untouched_inventory_v1.json"
    write_csv(detail_path, rows, DETAIL_FIELDS)
    write_csv(cells_path, external_cells, CELL_FIELDS)
    now = datetime.now(timezone.utc).isoformat()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd="/home/codonflow-a8-rk", text=True).strip()
    summary = {
        "schema": SCHEMA, "protocol_id": protocol["protocol_id"], "protocol_sha256": sha256(args.protocol),
        "created_at": now, "status": "PASS_INVENTORY_ONLY_SCIENTIFIC_GATES_UNRESOLVED",
        "code_commit_at_execution": commit, "platform": platform.platform(),
        "counts": {
            "detailed_rows": len(rows), "detailed_rows_by_source": observed,
            "external_seed0_actual_set_cells": len(external_cells),
            "rk16_b11_methods": rk16_audit["primary_method_count"],
            "rk16_b11_real_generation_calls": rk16_audit["primary_real_generation_call_count"],
            "functional_untouched_rows_metadata_only": untouched["rows"],
        },
        "a7_g2": a7_summary, "rk06_dense": rk06_summary, "external_actual_set": external_summary,
        "rk16_dense_prefix": {
            "method_summary": rk16_audit["method_summary"], "secondary_b100_descriptive_summary": rk16_audit.get("secondary_b100_descriptive_summary"),
            "matrix_sha256": rk16_spec["matrix_sha256"], "audit_sha256": rk16_spec["audit_sha256"],
            "ordered_prefix": True, "budget": 11, "time_matched_comparison": False,
            "scope": "Four-method shared proxy-output B11 prefixes; no CodonFlow arm and no external SOTA claim.",
        },
        "functional_untouched": untouched,
        "missing_or_not_comparable": [
            "No CodonFlow arm in the seven-method external actual-set or RK16 four-method B11 matrix.",
            "No common dense prefix for GEMORNA, CAI-greedy, or legacy LinearDesign-scan; repeated-call positions are not zero-filled.",
            "No uniform end-to-end hardware, parallelism, generator-plus-scorer wall clock across external and natural-source arms.",
            "Protein-to-CDS external input semantics are not causally exchangeable with natural-CDS warm-start CodonFlow.",
            "No eligible multi-protein fixed-protein functional-untouched cohort; the 19,072-row MAGE partition has one operational cluster and only 362 synonymous single-codon rows.",
            "Functional robustness remains failed (2/8 sequence-OOD tests passed); no untouched outcomes were opened or evaluated.",
        ],
        "scientific_gate_passed": False, "codonflow_external_sota_evaluated": False,
        "time_matched_comparison": False, "functional_untouched_evaluated": False,
        "new_functional_labels_read": False, "sota_claim": False, "rk_g1_pass": False,
        "expensive_generator_training_authorized": False, "manuscript_submittable": False,
        "artifacts": {
            "baseline_run_inventory_csv": {"path": str(detail_path), "sha256": sha256(detail_path)},
            "external_actual_set_cells_csv": {"path": str(cells_path), "sha256": sha256(cells_path)},
        },
    }
    atomic_json(summary_path, summary)
    print(json.dumps({"status": summary["status"], "counts": summary["counts"], "summary": str(summary_path), "summary_sha256": sha256(summary_path)}, indent=2))


if __name__ == "__main__":
    main()
