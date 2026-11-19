#!/usr/bin/env python3
"""Independent raw-table recompute for Mordstein observed-end proxy associations."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
from scipy.stats import rankdata


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def corr(x: np.ndarray, y: np.ndarray, kind: str) -> float:
    if kind == "spearman":
        x = rankdata(x, method="average")
        y = rankdata(y, method="average")
    elif kind != "pearson":
        raise ValueError(kind)
    return float(np.corrcoef(x, y)[0, 1])


def recompute_association(x: np.ndarray, y: np.ndarray, kind: str, seed: int, B: int) -> dict:
    observed = corr(x, y, kind)
    n = len(x)
    boot = []
    rng = np.random.default_rng(seed)
    for _ in range(B):
        take = rng.integers(0, n, size=n)
        boot.append(corr(x[take], y[take], kind))
    null = []
    rng = np.random.default_rng(seed + 1)
    for _ in range(B):
        null.append(corr(x, rng.permutation(y), kind))
    boot_array = np.asarray(boot)
    null_array = np.asarray(null)
    if not np.isfinite(boot_array).all() or not np.isfinite(null_array).all():
        raise RuntimeError("non-finite resampling result")
    return {
        "observed": observed,
        "ci95_percentile": [float(np.quantile(boot_array, 0.025)), float(np.quantile(boot_array, 0.975))],
        "permutation_p_two_sided": float((1 + np.count_nonzero(np.abs(null_array) >= abs(observed))) / (B + 1)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    protocol_path = args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    production_path = args.production.resolve()
    production = json.loads(production_path.read_text())
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}
    pre = protocol["prerequisites"]
    checks["production_pending_independent"] = production["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION"
    checks["protocol_identity"] = production["protocol_id"] == protocol["protocol_id"]
    checks["protocol_hash"] = production["protocol_sha256"] == sha256(protocol_path)
    checks["source_formula_and_population_contract"] = (
        protocol["source_article"]["doi"] == "10.1016/j.cels.2020.03.001"
        and protocol["endpoint"]["formula"] == "sum_{i=1..8} i * counts_bin_i / sum_{i=1..8} counts_bin_i"
        and protocol["analysis_population"]["minimum_total_assigned_reads_per_variant"] == 1000
        and protocol["analysis_population"]["no_complete_cds_imputation"] is True
    )
    checks["recovery_independent_pass"] = json.loads((repo / pre["recovery_independent"]).read_text())["status"] == "PASS"
    checks["recovery_finalization_pass"] = json.loads((repo / pre["recovery_finalization"]).read_text())["status"] == "PASS"
    prerequisite_hashes = {
        "recovery_summary_sha256": repo / pre["recovery_summary"],
        "recovery_independent_sha256": repo / pre["recovery_independent"],
        "recovery_finalization_sha256": repo / pre["recovery_finalization"],
        "variant_counts_sha256": Path(pre["variant_counts"]),
        "references_r1_sha256": Path(pre["references_r1"]),
    }
    checks["prerequisite_hashes"] = all(production[key] == sha256(path) for key, path in prerequisite_hashes.items())
    fasta_records: dict[str, str] = {}
    name = None
    for line in Path(pre["references_r1"]).read_text().splitlines():
        if line.startswith(">"):
            name = line[1:].split()[0]
            fasta_records[name] = ""
        elif name is not None:
            fasta_records[name] += line.strip()
    raw_rows = list(csv.DictReader(Path(pre["variant_counts"]).open(newline="")))
    production_rows = production["variant_metrics"]
    checks["population_152_unique_reconstructed_ids"] = (
        len(raw_rows) == len(production_rows) == 152
        and len({r["variant_id"] for r in raw_rows}) == 152
        and all(r["variant_id"].startswith("CF_MORD_") for r in raw_rows)
    )
    max_score_delta = 0.0
    max_feature_delta = 0.0
    feature_ok = True
    sequence_ok = True
    count_ok = True
    recomputed_rows = []
    for raw, saved in zip(raw_rows, production_rows):
        count_ok &= raw["variant_id"] == saved["variant_id"]
        counts = [int(raw[f"counts_bin{i}"]) for i in range(1, 9)]
        total = sum(counts)
        count_ok &= total == int(raw["r1_assigned_reads"]) == saved["total_assigned_reads"] and total >= 1000
        score = math.fsum((i + 1) * c for i, c in enumerate(counts)) / total
        max_score_delta = max(max_score_delta, abs(score - saved["flowseq_score_r1_only"]), abs(score - float(raw["flowseq_score_r1_only"])))
        seq = raw["sequence_5prime_300nt"]
        sequence_ok &= len(seq) == 300 and set(seq) <= set("ACGT") and fasta_records.get(raw["variant_id"]) == seq
        sequence_ok &= hashlib.sha256(seq.encode()).hexdigest() == saved["sequence_sha256"]
        gc3 = sum(c in "GC" for c in seq[2::3]) / 100.0
        gc = sum(c in "GC" for c in seq) / 300.0
        cpg = 100.0 * sum(seq[i:i + 2] == "CG" for i in range(299)) / 299.0
        expected = {"gc3_observed_5prime": gc3, "gc_observed_5prime": gc, "cpg_per_100nt_observed_5prime": cpg}
        for key, value in expected.items():
            max_feature_delta = max(max_feature_delta, abs(value - saved[key]))
        recomputed_rows.append({"variant_id": raw["variant_id"], "flowseq_score_r1_only": score, **expected})
    checks["counts_support_and_row_alignment"] = bool(count_ok)
    checks["sequence_fasta_and_hash_match"] = bool(sequence_ok)
    checks["flowseq_formula_max_abs_delta_le_1e_12"] = max_score_delta <= 1e-12
    checks["feature_formula_max_abs_delta_le_1e_12"] = max_feature_delta <= 1e-12
    details["max_score_delta"] = max_score_delta
    details["max_feature_delta"] = max_feature_delta
    y = np.asarray([r["flowseq_score_r1_only"] for r in recomputed_rows], dtype=np.float64)
    stats = protocol["statistics"]
    B = int(stats["bootstrap_resamples"])
    association_ok = True
    max_association_delta = 0.0
    primary_for_holm = []
    recomputed_associations = {}
    for feature_index, feature in enumerate(stats["primary_features"]):
        x = np.asarray([r[feature] for r in recomputed_rows], dtype=np.float64)
        seed = int(stats["seed"]) + feature_index * int(stats["seed_stride"])
        recomputed_associations[feature] = {}
        for kind, offset in (("spearman", 0), ("pearson", 2)):
            result = recompute_association(x, y, kind, seed + offset, B)
            recomputed_associations[feature][kind] = result
            saved = production["associations"][feature][kind]
            association_ok &= saved["seed"] == seed + offset and saved["bootstrap_resamples"] == B and saved["permutation_resamples"] == B
            for key in ("observed", "permutation_p_two_sided"):
                max_association_delta = max(max_association_delta, abs(result[key] - saved[key]))
            max_association_delta = max(max_association_delta, *(abs(a - b) for a, b in zip(result["ci95_percentile"], saved["ci95_percentile"])))
            if kind == "spearman":
                primary_for_holm.append({"feature": feature, **result})
    order = sorted(range(2), key=lambda i: primary_for_holm[i]["permutation_p_two_sided"])
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (2 - rank) * primary_for_holm[index]["permutation_p_two_sided"]))
        primary_for_holm[index]["holm_p"] = running
    for item in primary_for_holm:
        saved = production["associations"][item["feature"]]["spearman"]
        max_association_delta = max(max_association_delta, abs(item["holm_p"] - saved["holm_p"]))
        gate = item["ci95_percentile"][0] > 0 and item["holm_p"] < 0.05
        association_ok &= gate == saved["positive_gate"] == production["primary_gates"][item["feature"]]
    cpg_feature = "cpg_per_100nt_observed_5prime"
    cpg_seed = int(stats["seed"]) + 2 * int(stats["seed_stride"])
    x = np.asarray([r[cpg_feature] for r in recomputed_rows], dtype=np.float64)
    cpg_result = recompute_association(x, y, "spearman", cpg_seed, B)
    saved_cpg = production["associations"][cpg_feature]["spearman"]
    for key in ("observed", "permutation_p_two_sided"):
        max_association_delta = max(max_association_delta, abs(cpg_result[key] - saved_cpg[key]))
    max_association_delta = max(max_association_delta, *(abs(a - b) for a, b in zip(cpg_result["ci95_percentile"], saved_cpg["ci95_percentile"])))
    association_ok &= max_association_delta <= 1e-12
    checks["all_bootstrap_permutation_and_holm_values_match"] = bool(association_ok)
    details["max_association_delta"] = max_association_delta
    details["recomputed_primary"] = primary_for_holm
    details["recomputed_cpg_spearman"] = cpg_result
    csv_rows = list(csv.DictReader(Path(production["variant_metrics_csv"]).open(newline="")))
    checks["metrics_csv_hash_and_rows"] = (
        sha256(Path(production["variant_metrics_csv"])) == production["variant_metrics_csv_sha256"]
        and len(csv_rows) == 152
        and [r["variant_id"] for r in csv_rows] == [r["variant_id"] for r in production_rows]
    )
    score_summary = production["score_summary"]
    checks["score_summary_recompute"] = (
        abs(score_summary["min"] - float(np.min(y))) <= 1e-12
        and abs(score_summary["max"] - float(np.max(y))) <= 1e-12
        and abs(score_summary["mean"] - float(np.mean(y))) <= 1e-12
        and abs(score_summary["sd_sample"] - float(np.std(y, ddof=1))) <= 1e-12
    )
    checks["total_reads_conservation"] = production["total_assigned_reads"] == sum(r["total_assigned_reads"] for r in production_rows) == 9037593
    interpretation = production["scientific_interpretation"]
    checks["scientific_boundaries_preserved"] = (
        interpretation["association_only"] is True
        and interpretation["simple_proxy_failure_supported"] is False
        and interpretation["mechanism_model_superiority_supported"] is False
        and interpretation["protein_ood_evaluation"] is False
        and interpretation["complete_cds_analysis"] is False
        and interpretation["author_identity_mapping"] is False
        and interpretation["generator_training_authorized"] is False
        and interpretation["sota_claim"] is False
    )
    checks["no_forced_217_or_author_identity"] = len(production_rows) == 152 and not any(r["variant_id"].startswith("GFP_") for r in production_rows)
    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema": "a8.rk02.mordstein_observed_end_proxy_diagnostics_independent.v1",
        "status": "PASS" if not failed else "FAIL",
        "production_sha256": sha256(production_path),
        "protocol_sha256": sha256(protocol_path),
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed),
        "checks": checks,
        "failed_checks": failed,
        "details": details,
        "scientific_gate": "OBSERVED_END_ASSOCIATION_ONLY_NOT_PROTEIN_OOD_NOT_GENERATOR_AUTHORIZATION",
    }
    write_json(args.output, payload)
    print(json.dumps({"status": payload["status"], "checks": f"{payload['checks_passed']}/{payload['checks_total']}", "failed": failed, "max_association_delta": max_association_delta}))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
