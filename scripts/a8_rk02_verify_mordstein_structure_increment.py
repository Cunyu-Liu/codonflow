#!/usr/bin/env python3
"""Independent raw-sequence, CAI, ViennaRNA, OOF and resampling verification; no production import."""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import RNA
import CAI
from Bio.Seq import Seq
from scipy.stats import pearsonr, spearmanr

DEPTH = ["log1p_total_assigned_reads"]
SIMPLE = DEPTH + ["gc3_observed_5prime", "gc_observed_5prime", "cpg_per_100nt_observed_5prime", "cai_human_def_refs_observed_r1"]
STRUCTURE = ["mfe_observed_r1_full_kcal_mol", "mfe_observed_r1_window48_min_kcal_mol", "mfe_observed_r1_window48_mean_kcal_mol"]
FEATURE_SETS = {"depth_only": DEPTH, "simple": SIMPLE, "simple_plus_structure": SIMPLE + STRUCTURE}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_fasta(path: Path) -> dict[str, str]:
    out, name, chunks = {}, None, []
    for line in path.read_text().splitlines():
        if line.startswith(">"):
            if name is not None:
                out[name] = "".join(chunks)
            name, chunks = line[1:].split()[0], []
        else:
            chunks.append(line.strip())
    if name is not None:
        out[name] = "".join(chunks)
    return out


def load_wrapper(path: Path):
    spec = importlib.util.spec_from_file_location("independent_cai_reference_wrapper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fold_map(ids: list[str], seed: int, k: int) -> dict[str, int]:
    ordered = sorted(ids, key=lambda v: hashlib.sha256(f"{seed}|{v}".encode()).hexdigest())
    return {v: i % k for i, v in enumerate(ordered)}


def independent_oof(rows: list[dict], features: list[str], folds: dict[str, int], alpha: float, k: int) -> np.ndarray:
    x = np.array([[r[f] for f in features] for r in rows], dtype=float)
    y = np.array([r["flowseq_score_r1_only"] for r in rows], dtype=float)
    f = np.array([folds[r["variant_id"]] for r in rows])
    pred = np.full(len(rows), np.nan)
    for fold in range(k):
        tr, te = f != fold, f == fold
        xm, xs = x[tr].mean(0), x[tr].std(0)
        ym, ys = y[tr].mean(), y[tr].std()
        xtr, xte = (x[tr] - xm) / xs, (x[te] - xm) / xs
        design = np.column_stack([np.ones(xtr.shape[0]), xtr])
        penalty = np.eye(design.shape[1]) * alpha
        penalty[0, 0] = 0.0
        beta = np.linalg.solve(design.T @ design + penalty, design.T @ ((y[tr] - ym) / ys))
        pred[te] = np.column_stack([np.ones(xte.shape[0]), xte]) @ beta * ys + ym
    assert np.isfinite(pred).all()
    return pred


def delta(y: np.ndarray, simple: np.ndarray, structure: np.ndarray, endpoint: str) -> float:
    if endpoint == "delta_spearman":
        return float(spearmanr(y, structure).statistic - spearmanr(y, simple).statistic)
    if endpoint == "delta_mse":
        return float(np.mean((y - structure) ** 2) - np.mean((y - simple) ** 2))
    raise ValueError(endpoint)


def resampling(y: np.ndarray, simple: np.ndarray, structure: np.ndarray, endpoint: str, seed: int, B: int) -> dict:
    observed = delta(y, simple, structure, endpoint)
    n = len(y)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(B):
        take = rng.integers(0, n, n)
        boots.append(delta(y[take], simple[take], structure[take], endpoint))
    rng = np.random.default_rng(seed + 1)
    perms = []
    for _ in range(B):
        swap = rng.random(n) < .5
        a, b = simple.copy(), structure.copy()
        a[swap], b[swap] = structure[swap], simple[swap]
        perms.append(delta(y, a, b, endpoint))
    boots, perms = np.asarray(boots), np.asarray(perms)
    return {"endpoint": endpoint, "observed": observed, "ci95_percentile": [float(np.quantile(boots, .025)), float(np.quantile(boots, .975))], "permutation_p_two_sided": (1 + int(np.sum(np.abs(perms) >= abs(observed)))) / (B + 1), "seed": seed}


def holm(items: list[dict]) -> None:
    running, m = 0.0, len(items)
    for rank, idx in enumerate(sorted(range(m), key=lambda i: items[i]["permutation_p_two_sided"])):
        running = max(running, min(1.0, (m - rank) * items[idx]["permutation_p_two_sided"]))
        items[idx]["holm_p"] = running


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--production", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    repo, protocol_path = args.repo.resolve(), args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    production = json.loads(args.production.read_text())
    pre = protocol["prerequisites"]
    summary = json.loads((repo / pre["recovery_summary"]).read_text())
    fasta = read_fasta(Path(pre["references_r1"]))
    wrapper = load_wrapper(Path(pre["cai_wrapper"]))
    references = getattr(wrapper, pre["cai_reference_variable"])
    raw_rows = {}
    with Path(pre["variant_counts"]).open(newline="") as handle:
        for raw in csv.DictReader(handle):
            raw_rows[raw["variant_id"]] = raw
    md = RNA.md(); md.dangles = 0; md.temperature = 37.0
    rows, feature_deltas = [], {name: 0.0 for name in SIMPLE + STRUCTURE}
    for old in production["variant_metrics"]:
        variant = old["variant_id"]
        raw = raw_rows[variant]
        sequence = raw["sequence_5prime_300nt"]
        assert fasta[variant] == sequence and len(sequence) == 300 and not set(sequence) - set("ACGT")
        assert str(Seq(sequence).translate(table=11)) == summary["r1_protein_reference"]
        counts = [int(raw[f"counts_bin{i}"]) for i in range(1, 9)]
        total = sum(counts)
        score = sum((i + 1) * c for i, c in enumerate(counts)) / total
        assert total == old["total_assigned_reads"] and score == old["flowseq_score_r1_only"]
        cai = float(CAI.CAI(sequence, reference=references, genetic_code=11))
        assert math.isfinite(cai) and cai > 0
        third = sequence[2::3]
        row = {"variant_id": variant, "flowseq_score_r1_only": score,
               "log1p_total_assigned_reads": math.log1p(total),
               "gc3_observed_5prime": sum(c in "GC" for c in third) / 100,
               "gc_observed_5prime": sum(c in "GC" for c in sequence) / 300,
               "cpg_per_100nt_observed_5prime": 100 * sum(sequence[i:i+2] == "CG" for i in range(299)) / 299,
               "cai_human_def_refs_observed_r1": cai}
        rna = sequence.replace("T", "U")
        full = float(RNA.fold_compound(rna, md).mfe()[1])
        windows = [float(RNA.fold_compound(rna[i:i+48], md).mfe()[1]) for i in range(253)]
        row.update({"mfe_observed_r1_full_kcal_mol": full, "mfe_observed_r1_window48_min_kcal_mol": min(windows), "mfe_observed_r1_window48_mean_kcal_mol": float(np.mean(windows))})
        for name in SIMPLE + STRUCTURE:
            feature_deltas[name] = max(feature_deltas[name], abs(row[name] - old[name]))
            assert math.isfinite(row[name])
        rows.append(row)
    assert len(rows) == len(raw_rows) == 152
    assert max(feature_deltas.values()) <= 1e-10, feature_deltas
    assignments = fold_map([r["variant_id"] for r in rows], protocol["cross_validation"]["seed"], 5)
    assert assignments == {r["variant_id"]: r["fold"] for r in production["variant_metrics"]}
    predictions = {name: independent_oof(rows, features, assignments, 1.0, 5) for name, features in FEATURE_SETS.items()}
    prediction_deltas = {}
    for name, pred in predictions.items():
        reported = np.array([r["prediction_" + name] for r in production["variant_metrics"]])
        prediction_deltas[name] = float(np.max(np.abs(pred - reported)))
    assert max(prediction_deltas.values()) <= 1e-9, prediction_deltas
    y = np.array([r["flowseq_score_r1_only"] for r in rows])
    metrics = {}
    for name, pred in predictions.items():
        metrics[name] = {"spearman": float(spearmanr(y, pred).statistic), "pearson": float(pearsonr(y, pred).statistic), "mse": float(np.mean((y - pred) ** 2)), "rmse": float(np.sqrt(np.mean((y - pred) ** 2)))}
        for metric, value in metrics[name].items():
            assert abs(value - production["model_metrics"][name][metric]) <= 1e-10
    B = protocol["statistics"]["bootstrap_resamples"]
    effects = []
    for i, endpoint in enumerate(protocol["statistics"]["primary_endpoints"]):
        result = resampling(y, predictions["simple"], predictions["simple_plus_structure"], endpoint, protocol["statistics"]["seed"] + i * protocol["statistics"]["seed_stride"], B)
        reported = production["primary_effects"][endpoint]
        assert abs(result["observed"] - reported["observed"]) <= 1e-10
        assert np.max(np.abs(np.array(result["ci95_percentile"]) - np.array(reported["ci95_percentile"]))) <= 1e-10
        assert result["permutation_p_two_sided"] == reported["permutation_p_two_sided"]
        effects.append(result)
    holm(effects)
    for result in effects:
        reported = production["primary_effects"][result["endpoint"]]
        assert result["holm_p"] == reported["holm_p"]
        direction = result["ci95_percentile"][0] > 0 if result["endpoint"] == "delta_spearman" else result["ci95_percentile"][1] < 0
        assert (direction and result["holm_p"] < .05) == reported["direction_pass"]
    gate = all((r["ci95_percentile"][0] > 0 if r["endpoint"] == "delta_spearman" else r["ci95_percentile"][1] < 0) and r["holm_p"] < .05 for r in effects)
    assert gate == production["structure_increment_pass"]
    assert production["protocol_sha256"] == sha256(protocol_path)
    assert production["cai_wrapper_sha256"] == sha256(Path(pre["cai_wrapper"]))
    assert production["variant_counts_sha256"] == sha256(Path(pre["variant_counts"]))
    assert production["references_r1_sha256"] == sha256(Path(pre["references_r1"]))
    assert production["variant_predictions_csv_sha256"] == sha256(Path(production["variant_predictions_csv"]))
    assert len(references) == 9 and production["n_variants"] == 152
    assert all(not r["variant_id"].startswith("GFP_") for r in production["variant_metrics"])
    for key, value in production["scientific_interpretation"].items():
        if key not in {"note", "development_only"}:
            assert value is False, (key, value)
    checks = [{"name": name, "pass": True} for name in [
        "population_152_unique_variants", "raw_sequences_retranslated", "flowseq_scores_recomputed",
        "external_cai_recomputed_without_silent_zero", "viennarna_features_recomputed",
        "frozen_fold_assignment_recomputed", "oof_predictions_recomputed_without_sklearn",
        "model_metrics_recomputed", "bootstrap_and_sign_flip_recomputed", "holm_and_gate_recomputed",
        "input_and_output_hashes_verified", "scientific_boundaries_preserved",
    ]]
    report = {
        "schema": "a8.rk02.mordstein_structure_increment_dev_independent.v1",
        "status": "PASS", "analysis_status": "DEVELOPMENT_ONLY_NOT_CONFIRMATORY_INDEPENDENT_TEST",
        "production_sha256": sha256(args.production), "protocol_sha256": sha256(protocol_path),
        "n_variants": len(rows), "independent_cai_package": "CAI 1.0.2", "independent_viennarna": RNA.__version__,
        "feature_max_abs_delta": feature_deltas, "prediction_max_abs_delta": prediction_deltas,
        "model_metrics": metrics, "primary_effects": {r["endpoint"]: r for r in effects}, "structure_increment_pass": gate,
        "verification": {"raw_sequences_retranslated": True, "external_cai_recomputed": True, "viennarna_recomputed": True, "oof_predictions_recomputed_without_sklearn": True, "bootstrap_and_sign_flip_recomputed": True, "functional_untouched_access": False, "protein_ood_evaluation": False, "full_cds_analysis": False, "full_rk_g1_gate": False, "generator_training_authorized": False, "sota_claim": False},
        "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "output": str(args.output), "n": len(rows), "feature_max_abs_delta": max(feature_deltas.values()), "prediction_max_abs_delta": max(prediction_deltas.values()), "structure_increment_pass": gate, "primary_effects": report["primary_effects"]}))


if __name__ == "__main__":
    main()
