#!/usr/bin/env python3
"""Independent, standard-library-only verification of the RK38 inventory."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def close(a: Any, b: Any) -> bool:
    return math.isclose(float(a), float(b), rel_tol=1e-11, abs_tol=1e-11)


def numeric(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


class Verification:
    def __init__(self):
        self.checks: list[dict[str, Any]] = []

    def require(self, name: str, condition: bool, detail: Any = "") -> None:
        self.checks.append({"check": name, "status": "PASS" if condition else "FAIL", "detail": detail})
        if not condition:
            raise AssertionError(f"{name}: {detail}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    parser.add_argument("--cells", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verification = Verification()
    started = datetime.now(timezone.utc).isoformat()
    try:
        protocol = load(args.protocol)
        summary = load(args.summary)
        with args.details.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        with args.cells.open(newline="") as handle:
            cells = list(csv.DictReader(handle))
        v = verification
        v.require("protocol_sha", summary["protocol_sha256"] == file_sha(args.protocol))
        v.require("detail_row_count", len(rows) == 846, len(rows))
        v.require("external_cell_count", len(cells) == 126, len(cells))
        v.require("detail_source_counts", dict(Counter(row["source_line"] for row in rows)) == protocol["output"]["expected_raw_run_rows"], dict(Counter(row["source_line"] for row in rows)))
        v.require("summary_artifact_detail_sha", summary["artifacts"]["baseline_run_inventory_csv"]["sha256"] == file_sha(args.details))
        v.require("summary_artifact_cells_sha", summary["artifacts"]["external_actual_set_cells_csv"]["sha256"] == file_sha(args.cells))
        raw_cache: dict[Path, Any] = {}

        def raw(path: Path) -> Any:
            if path not in raw_cache:
                raw_cache[path] = load(path)
            return raw_cache[path]

        a7_spec = protocol["inputs"]["a7_g2"]
        rk06_spec = protocol["inputs"]["rk06_dense"]
        external_spec = protocol["inputs"]["external_actual_set"]
        grid = raw(Path(external_spec["lineardesign_grid"]))
        ensemble = raw(Path(external_spec["ensemble_report"]))
        grid_by_record: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for run in grid["runs"]:
            grid_by_record[run["record_id"]].append(run)
        ensemble_by_record = {record["record_id"]: record for record in ensemble["records"]}
        for index, row in enumerate(rows):
            path = Path(row["raw_path"])
            v.require(f"raw_sha_{index}", file_sha(path) == row["raw_sha256"], str(path))
            payload = raw(path)
            if row["source_line"] in {"a7_g2", "rk06_dense"}:
                points = payload["points"]
                sequences = [point["sequence"] for point in points]
                unique = set(sequences)
                costs = payload.get("costs") or payload.get("cost")
                wall = costs.get("elapsed_s", costs.get("wall_clock_seconds"))
                forward = costs.get("model_forward_calls", costs.get("forward_calls"))
                unique_calls = costs.get("unique_terminal_reward_calls", costs.get("unique_scorer_calls"))
                valid = (
                    payload["record_id"] == row["record_id"] and str(payload["seed"]) == row["seed"]
                    and payload["status"] == row["status"] == "done"
                    and len(points) == int(row["n_attempts_or_points"]) == 500
                    and [point["budget"] for point in points] == list(range(1, 501))
                    and len(unique) == int(row["n_unique_outputs"])
                    and (payload.get("n_unique") is None or len(unique) == payload["n_unique"])
                    and len(points) - len(unique) == int(row["n_duplicate_or_unreturned"])
                    and close(wall, row["elapsed_s"])
                    and str(costs.get("generator_calls", "")) == row["generator_calls"]
                    and (numeric(forward) == numeric(row["model_forward_calls"]))
                    and str(unique_calls) == row["unique_terminal_reward_calls"]
                    and payload.get("source_sha256", "") == row["source_sha256"]
                    and payload.get("code_commit", "") == row["code_commit"]
                    and row["ordered_real_scorer_prefix"] == "True" and row["dense_auc_available"] == "True"
                )
                if row["source_line"] == "a7_g2" and row["method"] == "codonflow_learned":
                    valid = valid and str(payload.get("device", "")).startswith("cuda") and bool(forward)
                if row["source_line"] == "rk06_dense":
                    valid = valid and payload["method"] == row["method"]
                v.require(f"trajectory_{index}", valid, f"{row['source_line']}:{row['record_id']}:{row['method']}:s{row['seed']}")
            elif row["source_line"] == "a6_legacy_five_methods":
                result = payload["methods"][row["method"]]
                unique = set(result.get("solutions", []))
                calls = result.get("generator_calls")
                attempts = calls if calls is not None else len(result.get("solutions", []))
                valid = (
                    payload["record_id"] == row["record_id"] and str(payload["seed"]) == row["seed"]
                    and result.get("status") == row["status"]
                    and len(unique) == int(row["n_unique_outputs"])
                    and (result.get("n_unique") is None or len(unique) == result["n_unique"])
                    and attempts == int(row["n_attempts_or_points"])
                    and attempts - len(unique) == int(row["n_duplicate_or_unreturned"])
                    and numeric(result.get("elapsed_s")) == numeric(row["elapsed_s"])
                    and (str(calls) if calls is not None else "") == row["generator_calls"]
                    and row["ordered_real_scorer_prefix"] == "False" and row["dense_auc_available"] == "False"
                )
                v.require(f"a6_method_{index}", valid, f"{row['record_id']}:{row['method']}:s{row['seed']}")
            elif row["source_line"] == "lineardesign_lambda11":
                runs = grid_by_record[row["record_id"]]
                unique = set(run["evaluation_sequence_dna"] for run in runs)
                valid = (
                    len(runs) == int(row["n_attempts_or_points"]) == 11
                    and len(unique) == int(row["n_unique_outputs"])
                    and close(sum(run["elapsed_s"] for run in runs), row["elapsed_s"])
                    and row["generator_calls"] == "11" and row["dense_auc_available"] == "False"
                    and row["budget_label"] == "11_lambda_calls_not_scorer_budget"
                    and runs[0]["source_sha256"] == row["source_sha256"]
                )
                v.require(f"lineardesign_{index}", valid, row["record_id"])
            elif row["source_line"] == "ensembledesign_11run":
                record = ensemble_by_record[row["record_id"]]
                unique = set(run["evaluation_sequence_dna"] for run in record["runs"])
                valid = (
                    len(record["runs"]) == int(row["n_attempts_or_points"]) == 11
                    and len(unique) == int(row["n_unique_outputs"]) == record["unique_output_sequences"]
                    and close(record["elapsed_s"], row["elapsed_s"])
                    and row["generator_calls"] == "11" and row["dense_auc_available"] == "False"
                    and record["source_cds_sha256"] == row["source_sha256"]
                )
                v.require(f"ensemble_{index}", valid, row["record_id"])
            else:
                v.require(f"known_source_{index}", False, row["source_line"])

        matrix = raw(Path(external_spec["matrix"]))
        matrix_records = {record["record_id"]: record for record in matrix["records"]}
        legacy_cache: dict[tuple[int, str], Any] = {}
        for index, cell in enumerate(cells):
            record_id, method = cell["record_id"], cell["method"]
            if method in external_spec["legacy_methods"]:
                key = (0, record_id)
                if key not in legacy_cache:
                    legacy_cache[key] = raw(Path(external_spec["legacy_root_template"].format(seed=0)) / f"{record_id}_s0.json")
                raw_sequences = legacy_cache[key]["methods"][method].get("solutions", [])
            elif method == "lineardesign_lambda11":
                raw_sequences = [run["evaluation_sequence_dna"] for run in grid_by_record[record_id]]
            else:
                raw_sequences = [run["evaluation_sequence_dna"] for run in ensemble_by_record[record_id]["runs"]]
            matrix_method = matrix_records[record_id]["methods"][method]
            matrix_sequences = [point["sequence"] for point in matrix_method["points"]]
            valid = (
                len(set(raw_sequences)) == int(cell["raw_n_unique"]) == int(cell["matrix_n_unique"]) == matrix_method["n_unique"]
                and set(raw_sequences) == set(matrix_sequences) and len(matrix_sequences) == len(set(matrix_sequences))
                and cell["sequence_set_exact"] == "True"
                and close(cell["hypervolume_normalized"], matrix_method["actual_set"]["hypervolume_normalized"])
                and close(cell["pairwise_ned"], matrix_method["ned"])
                and close(cell["identity_rate"], matrix_method["identity_rate"])
            )
            v.require(f"external_sequence_cell_{index}", valid, f"{record_id}:{method}")
        for method in external_spec["method_order"]:
            selected = [cell for cell in cells if cell["method"] == method]
            observed = {
                "mean_hypervolume_normalized": mean(float(cell["hypervolume_normalized"]) for cell in selected),
                "mean_ned": mean(float(cell["pairwise_ned"]) for cell in selected),
                "total_actual_outputs": sum(int(cell["matrix_n_unique"]) for cell in selected),
                "min_identity_rate": min(float(cell["identity_rate"]) for cell in selected),
            }
            frozen = matrix["method_summary"][method]
            v.require(f"method_summary_{method}", all(close(observed[key], frozen[key]) for key in observed), observed)

        rk16_spec = protocol["inputs"]["rk16_dense_prefix"]
        rk16 = raw(Path(rk16_spec["audit"]))
        v.require("rk16_call_count", rk16["primary_real_generation_call_count"] == 792 and summary["counts"]["rk16_b11_real_generation_calls"] == 792)
        v.require("rk16_method_summary", summary["rk16_dense_prefix"]["method_summary"] == rk16["method_summary"])
        v.require("rk16_no_time_match", rk16["time_matched_comparison"] is False and summary["rk16_dense_prefix"]["time_matched_comparison"] is False)

        split = raw(Path(protocol["inputs"]["functional_untouched_metadata_only"]["split_summary"]))
        untouched = summary["functional_untouched"]
        counts = split["counts"]["functional_untouched"]
        v.require("untouched_counts", untouched["rows"] == counts["rows"] == 19072 and untouched["clusters"] == counts["clusters"] == 1)
        v.require("untouched_groups", untouched["unique_construct_signature_groups"] == counts["unique_construct_signature_groups"] == 13569)
        v.require("untouched_synonymous_subset", untouched["synonymous_single_codon_rows"] == counts["variant_classes"]["synonymous_single_codon"] == 362)
        v.require("untouched_not_evaluated", untouched["functional_untouched_evaluated"] is False and untouched["new_label_or_outcome_read"] is False)
        v.require("untouched_not_multiprotein", untouched["independent_multiprotein_untouched_dataset_count"] == 0 and untouched["generalizable_fixed_protein_multiprotein_claim_supported"] is False)
        v.require("rk20_robustness_boundary", untouched["functional_robustness_pass"] is False and untouched["fully_passed_sequence_ood_tests"] == "2/8")
        for item in untouched["stat_only_files"]:
            path = Path(item["path"])
            v.require(f"untouched_stat_{path.name}", path.stat().st_size == item["bytes"] and item["access"] == "stat_only" and item["frozen_sha256_not_recomputed"])
        for flag in ["scientific_gate_passed", "codonflow_external_sota_evaluated", "time_matched_comparison", "functional_untouched_evaluated", "new_functional_labels_read", "sota_claim", "rk_g1_pass", "expensive_generator_training_authorized", "manuscript_submittable"]:
            v.require(f"negative_boundary_{flag}", summary[flag] is False)
        status = "PASS"
        error = None
    except Exception as exc:
        status = "FAIL"
        error = f"{type(exc).__name__}: {exc}"
    report = {
        "schema": "a8-rk38-baseline-untouched-inventory-independent-v1",
        "created_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "implementation": "separate standard-library CSV/raw-JSON verifier; does not import production code",
        "summary": str(args.summary), "summary_sha256": file_sha(args.summary),
        "details": str(args.details), "details_sha256": file_sha(args.details),
        "cells": str(args.cells), "cells_sha256": file_sha(args.cells),
        "checks": verification.checks,
        "n_checks": len(verification.checks),
        "n_pass": sum(check["status"] == "PASS" for check in verification.checks),
        "n_fail": sum(check["status"] == "FAIL" for check in verification.checks),
        "error": error,
        "functional_untouched_labels_read": False,
        "scientific_gate_passed": False,
        "sota_claim": False,
    }
    if args.output.exists():
        raise FileExistsError(args.output)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    os.replace(temp, args.output)
    print(json.dumps({"status": status, "n_checks": len(verification.checks), "n_pass": report["n_pass"], "n_fail": report["n_fail"], "error": error, "output": str(args.output), "sha256": file_sha(args.output)}, indent=2))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
