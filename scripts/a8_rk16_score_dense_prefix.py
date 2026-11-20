"""Score real ordered generation-call prefixes for the RK16 common-budget matrix."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from codonflow.eval.anytime import FrozenReference, dense_budget_step_auc_v2

EXPECTED_SIX_HYPOTHESES = 6


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=p_values.get)
    adjusted: dict[str, float] = {}
    running = 0.0
    for index, key in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - index) * p_values[key]))
        adjusted[key] = running
    return adjusted


def paired_effect(new_values, comparator_values, resamples: int, seed: int) -> dict:
    new = np.asarray(new_values, dtype=float)
    comparator = np.asarray(comparator_values, dtype=float)
    effects = new - comparator
    if effects.shape != (18,) or not np.isfinite(effects).all():
        raise ValueError("RK16 primary effects require exactly 18 finite paired records")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(effects), size=(resamples, len(effects)))
    distribution = effects[indices].mean(axis=1)
    lower, upper = np.quantile(distribution, [0.025, 0.975])
    p_less = (1 + int(np.sum(distribution <= 0.0))) / (resamples + 1)
    p_greater = (1 + int(np.sum(distribution >= 0.0))) / (resamples + 1)
    return {
        "n_records": 18,
        "new_mean": float(new.mean()),
        "comparator_mean": float(comparator.mean()),
        "mean_effect": float(effects.mean()),
        "median_effect": float(np.median(effects)),
        "sd_effect": float(effects.std(ddof=1)),
        "ci95": [float(lower), float(upper)],
        "bootstrap_p_two_sided": float(min(1.0, 2.0 * min(p_less, p_greater))),
        "per_record_effects": effects.tolist(),
        "bootstrap_seed": seed,
        "bootstrap_resamples": resamples,
    }


def objective_lookup(method_payload: dict) -> dict[str, tuple[str, list[float]]]:
    lookup: dict[str, tuple[str, list[float]]] = {}
    for point in method_payload["points"]:
        sequence = point["sequence"]
        digest = point["sequence_sha256"]
        if digest != sequence_sha256(sequence):
            raise ValueError("matrix point sequence/hash mismatch")
        if digest in lookup:
            raise ValueError("duplicate sequence hash in verified objective map")
        lookup[digest] = (sequence, [float(x) for x in point["objectives"]])
    if not lookup:
        raise ValueError("empty objective map")
    return lookup


def raw_legacy(payload: dict, record_id: str, method: str) -> list[str]:
    if payload["status"] != "done" or payload["record_id"] != record_id:
        raise ValueError(f"incomplete or mismatched legacy record {record_id}")
    method_payload = payload["methods"][method]
    if method_payload["status"] != "done":
        raise ValueError(f"incomplete legacy method {method}")
    sequences = method_payload["solutions"]
    if len(sequences) != method_payload["n_solutions"]:
        raise ValueError("legacy solution count mismatch")
    return sequences


def raw_lineardesign(report: dict, record_id: str, lambda_order: list[float]) -> list[str]:
    runs = [run for run in report["runs"] if run["record_id"] == record_id]
    by_lambda = {round(float(run["lambda"]), 1): run for run in runs}
    if len(runs) != len(lambda_order) or set(by_lambda) != set(lambda_order):
        raise ValueError(f"LinearDesign lambda grid mismatch for {record_id}")
    sequences = []
    for value in lambda_order:
        run = by_lambda[value]
        if run["status"] != "done" or not run["evaluation_sequence_dna"]:
            raise ValueError(f"incomplete LinearDesign run {record_id} lambda={value}")
        sequences.append(run["evaluation_sequence_dna"])
    return sequences


def raw_ensemble(report: dict, record_id: str, run_order: list[int]) -> list[str]:
    records = [record for record in report["records"] if record["record_id"] == record_id]
    if len(records) != 1 or records[0]["status"] != "done":
        raise ValueError(f"incomplete EnsembleDesign record {record_id}")
    runs = records[0]["runs"]
    by_id = {int(run["run_id"]): run for run in runs}
    if len(runs) != len(run_order) or set(by_id) != set(run_order):
        raise ValueError(f"EnsembleDesign run grid mismatch for {record_id}")
    sequences = []
    for run_id in run_order:
        run = by_id[run_id]
        if run["status"] != "done" or not run["evaluation_sequence_dna"]:
            raise ValueError(f"incomplete EnsembleDesign run {record_id} run={run_id}")
        sequences.append(run["evaluation_sequence_dna"])
    return sequences


def trajectory_records(
    raw_sequences: list[str],
    lookup: dict[str, tuple[str, list[float]]],
    max_budget: int,
) -> list[dict]:
    if len(raw_sequences) < max_budget:
        raise ValueError(f"insufficient real outputs: {len(raw_sequences)} < {max_budget}")
    records = []
    for budget, sequence in enumerate(raw_sequences[:max_budget], start=1):
        digest = sequence_sha256(sequence)
        if digest not in lookup:
            raise ValueError(f"raw sequence absent from independently verified objective map at B{budget}")
        mapped_sequence, objectives = lookup[digest]
        if mapped_sequence != sequence or not np.isfinite(objectives).all():
            raise ValueError(f"objective binding failure at B{budget}")
        records.append({"budget": budget, "objectives": objectives, "sequence_sha256": digest})
    return records


def score_trajectory(records: list[dict], reference: FrozenReference, max_budget: int) -> dict:
    dense = dense_budget_step_auc_v2(records, reference, max_budget=max_budget)
    if len(records) != max_budget or not math.isfinite(dense["auc"]):
        raise ValueError("a complete real dense trajectory is required")
    seen = set()
    rows = []
    by_budget = {row["budget"]: row for row in dense["curve"]}
    for record in records:
        budget = record["budget"]
        digest = record["sequence_sha256"]
        novel = digest not in seen
        seen.add(digest)
        rows.append({
            **by_budget[budget],
            "sequence_sha256": digest,
            "novel_sequence": novel,
            "n_unique_so_far": len(seen),
            "objectives": record["objectives"],
        })
    return {
        "evaluation_mode": "real_ordered_generation_call_prefix",
        "max_budget": max_budget,
        "n_real_generation_calls": len(records),
        "n_unique_terminal": len(seen),
        "dense_budget_step_auc_v2": dense["auc"],
        "endpoint_hypervolume_normalized": rows[-1]["hv"],
        "endpoint_hv": dense["endpoint_hv"],
        "curve": rows,
        "padding_used": False,
        "synthetic_origin_used": False,
        "zero_filled_budgets": False,
    }


def metric_value(record: dict, method: str, metric: str) -> float:
    trajectory = record["primary"][method]
    if metric == "dense_budget_step_auc_v2":
        return trajectory["dense_budget_step_auc_v2"]
    if metric == "endpoint_hypervolume_normalized_b11":
        return trajectory["endpoint_hypervolume_normalized"]
    raise KeyError(metric)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--comparisons-csv", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.audit, args.comparisons_csv):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")

    protocol_path = args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    if protocol["schema"] != "a8-rk16-dense-prefix-v1" or protocol["status"] != "FROZEN_BEFORE_DENSE_PREFIX_SCORING":
        raise ValueError("unexpected or non-frozen RK16 protocol")
    if protocol["holm_family_size"] != EXPECTED_SIX_HYPOTHESES:
        raise ValueError("the primary Holm family must contain six tests")

    def repo_path(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else REPO / path

    matrix_path = repo_path(protocol["inputs"]["matrix"]["path"])
    ld_path = repo_path(protocol["inputs"]["lineardesign_report"]["path"])
    ensemble_path = repo_path(protocol["inputs"]["ensemble_report"]["path"])
    manifest_path = repo_path(protocol["inputs"]["legacy_manifest"]["path"])
    for key, path in (("matrix", matrix_path), ("lineardesign_report", ld_path), ("ensemble_report", ensemble_path), ("legacy_manifest", manifest_path)):
        if sha256(path) != protocol["inputs"][key]["sha256"]:
            raise ValueError(f"frozen input hash mismatch: {key}")

    matrix = json.loads(matrix_path.read_text())
    ld_report = json.loads(ld_path.read_text())
    ensemble_report = json.loads(ensemble_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    if matrix["status"] != "COMPLETE_UNIQUE18_SEVEN_METHOD_ACTUAL_SET_MATRIX_DEVELOPMENT_ONLY" or len(matrix["records"]) != protocol["record_count"]:
        raise ValueError("complete frozen RK13 matrix required")
    if ld_report["status"] != "COMPLETE_UNIQUE18_OFFICIAL_LINEARDESIGN_LAMBDA_GRID":
        raise ValueError("complete official LinearDesign report required")
    if ensemble_report["status"] != "COMPLETE_UNIQUE18_OFFICIAL_ENSEMBLEDESIGN_11RUN":
        raise ValueError("complete official EnsembleDesign recovery required")
    if manifest["file_count"] != protocol["record_count"] or Path(manifest["root"]) != Path(protocol["inputs"]["legacy_manifest"]["root"]):
        raise ValueError("legacy manifest root/count mismatch")

    primary_methods = protocol["primary_methods"]
    secondary_methods = protocol["secondary_methods"]
    output_records = []
    for matrix_record in matrix["records"]:
        record_id = matrix_record["record_id"]
        filename = f"{record_id}_s0.json"
        if filename not in manifest["files"]:
            raise ValueError(f"missing frozen legacy file {filename}")
        legacy_path = Path(manifest["root"]) / filename
        if sha256(legacy_path) != manifest["files"][filename]:
            raise ValueError(f"legacy file hash mismatch {filename}")
        legacy = json.loads(legacy_path.read_text())
        calibration = Path(matrix_record["calibration"])
        if sha256(calibration) != matrix_record["calibration_sha256"]:
            raise ValueError(f"reference hash mismatch {record_id}")
        reference = FrozenReference.from_dict(json.loads(calibration.read_text()))
        raw = {
            "lineardesign_lambda11": raw_lineardesign(ld_report, record_id, protocol["lineardesign_lambda_order"]),
            "codongpt": raw_legacy(legacy, record_id, "codongpt"),
            "uniform_synonymous": raw_legacy(legacy, record_id, "uniform_synonymous"),
            "ensembledesign_11run": raw_ensemble(ensemble_report, record_id, protocol["ensemble_run_order"]),
        }
        if len(raw["codongpt"]) < protocol["secondary_max_budget"] or len(raw["uniform_synonymous"]) < protocol["secondary_max_budget"]:
            raise ValueError(f"incomplete B100 legacy trajectory {record_id}")
        primary = {}
        for method in primary_methods:
            lookup = objective_lookup(matrix_record["methods"][method])
            records = trajectory_records(raw[method], lookup, protocol["primary_max_budget"])
            primary[method] = score_trajectory(records, reference, protocol["primary_max_budget"])
        secondary = {}
        for method in secondary_methods:
            lookup = objective_lookup(matrix_record["methods"][method])
            records = trajectory_records(raw[method], lookup, protocol["secondary_max_budget"])
            secondary[method] = score_trajectory(records, reference, protocol["secondary_max_budget"])
        output_records.append({
            "record_id": record_id,
            "source_sha256": matrix_record["source_sha256"],
            "calibration_sha256": matrix_record["calibration_sha256"],
            "primary": primary,
            "secondary_b100_descriptive": secondary,
        })

    record_order = [record["record_id"] for record in output_records]
    method_summary = {}
    for method in primary_methods:
        auc = [metric_value(record, method, "dense_budget_step_auc_v2") for record in output_records]
        endpoint = [metric_value(record, method, "endpoint_hypervolume_normalized_b11") for record in output_records]
        method_summary[method] = {
            "mean_dense_budget_step_auc_v2": float(np.mean(auc)),
            "median_dense_budget_step_auc_v2": float(np.median(auc)),
            "mean_endpoint_hypervolume_normalized_b11": float(np.mean(endpoint)),
            "median_endpoint_hypervolume_normalized_b11": float(np.median(endpoint)),
            "total_real_generation_calls_primary": len(output_records) * protocol["primary_max_budget"],
        }
    secondary_summary = {}
    for method in secondary_methods:
        values = [record["secondary_b100_descriptive"][method]["dense_budget_step_auc_v2"] for record in output_records]
        endpoints = [record["secondary_b100_descriptive"][method]["endpoint_hypervolume_normalized"] for record in output_records]
        secondary_summary[method] = {
            "mean_dense_budget_step_auc_v2_b1_b99": float(np.mean(values)),
            "mean_endpoint_hypervolume_normalized_b100": float(np.mean(endpoints)),
            "scope": "descriptive two-method long-budget curve; excluded from primary Holm family",
        }

    comparisons = {}
    raw_p_values = {}
    for comparator_index, comparator in enumerate(protocol["comparators"]):
        for metric_index, metric in enumerate(protocol["primary_metrics"]):
            key = f"{protocol['reference_method']}_minus_{comparator}:{metric}"
            new_values = [metric_value(record, protocol["reference_method"], metric) for record in output_records]
            comparator_values = [metric_value(record, comparator, metric) for record in output_records]
            seed = protocol["bootstrap_seed_base"] + 100 * comparator_index + metric_index
            comparisons[key] = paired_effect(new_values, comparator_values, protocol["bootstrap_resamples"], seed)
            raw_p_values[key] = comparisons[key]["bootstrap_p_two_sided"]
    adjusted = holm_adjust(raw_p_values)
    for key, comparison in comparisons.items():
        low, high = comparison["ci95"]
        comparison["holm_p"] = adjusted[key]
        comparison["ci_excludes_zero"] = low > 0.0 or high < 0.0
        comparison["pass"] = comparison["mean_effect"] > 0.0 and low > 0.0 and adjusted[key] < protocol["holm_alpha"]

    per_comparator = {}
    for comparator in protocol["comparators"]:
        keys = [f"{protocol['reference_method']}_minus_{comparator}:{metric}" for metric in protocol["primary_metrics"]]
        per_comparator[comparator] = all(comparisons[key]["pass"] for key in keys)
    dense_prefix_superiority_pass = all(item["pass"] for item in comparisons.values())

    payload = {
        "schema": "a8-rk16-dense-prefix-matrix-v1",
        "status": "PASS_RK16_DENSE_PREFIX_COMPLETE",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "protocol_sha256": sha256(protocol_path),
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "evaluation_mode": protocol["evaluation_mode"],
        "budget_semantics": protocol["budget_semantics"],
        "record_order": record_order,
        "primary_max_budget": protocol["primary_max_budget"],
        "primary_methods": primary_methods,
        "exclusions": protocol["exclusions"],
        "method_summary": method_summary,
        "secondary_b100_descriptive_summary": secondary_summary,
        "primary_comparisons": comparisons,
        "per_comparator_two_metric_pass": per_comparator,
        "dense_prefix_superiority_pass": dense_prefix_superiority_pass,
        "time_matched_comparison": False,
        "scientific_gate_passed": False,
        "codonflow_rk_evaluated": False,
        "functional_ood_evaluated": False,
        "functional_untouched_evaluated": False,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "external_sota_authorized": False,
        "sota_claimed": False,
        "records": output_records,
    }
    atomic_json(args.output, payload)

    args.comparisons_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.comparisons_csv.open("x", newline="") as handle:
        fields = ["comparison", "metric", "new_mean", "comparator_mean", "mean_effect", "ci95_low", "ci95_high", "bootstrap_p", "holm_p", "pass"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for key, comparison in comparisons.items():
            writer.writerow({
                "comparison": key.split(":")[0],
                "metric": key.split(":")[1],
                "new_mean": comparison["new_mean"],
                "comparator_mean": comparison["comparator_mean"],
                "mean_effect": comparison["mean_effect"],
                "ci95_low": comparison["ci95"][0],
                "ci95_high": comparison["ci95"][1],
                "bootstrap_p": comparison["bootstrap_p_two_sided"],
                "holm_p": comparison["holm_p"],
                "pass": comparison["pass"],
            })

    audit = {
        "schema": "a8-rk16-dense-prefix-audit-v1",
        "status": "PASS",
        "protocol_sha256": payload["protocol_sha256"],
        "code_commit": payload["code_commit"],
        "output": str(args.output),
        "output_sha256": sha256(args.output),
        "comparisons_csv_sha256": sha256(args.comparisons_csv),
        "record_count": len(output_records),
        "primary_method_count": len(primary_methods),
        "primary_real_generation_call_count": len(output_records) * len(primary_methods) * protocol["primary_max_budget"],
        "secondary_real_generation_call_count": len(output_records) * len(secondary_methods) * protocol["secondary_max_budget"],
        "method_summary": method_summary,
        "secondary_b100_descriptive_summary": secondary_summary,
        "primary_comparisons": comparisons,
        "per_comparator_two_metric_pass": per_comparator,
        "dense_prefix_superiority_pass": dense_prefix_superiority_pass,
        "time_matched_comparison": False,
        "scientific_gate_passed": False,
        "codonflow_rk_evaluated": False,
        "functional_ood_evaluated": False,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "external_sota_authorized": False,
        "sota_claimed": False,
    }
    atomic_json(args.audit, audit)
    print(json.dumps({key: value for key, value in audit.items() if key not in ("primary_comparisons",)}, indent=2))


if __name__ == "__main__":
    main()
