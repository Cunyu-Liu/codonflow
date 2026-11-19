#!/usr/bin/env python3
"""Development-only fixed-GFP observed-R1 structure increment; no untouched/test access."""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import time
from collections import Counter
from pathlib import Path

import numpy as np
import RNA
import scipy
import sklearn
from scipy.stats import pearsonr, spearmanr
from sklearn.linear_model import Ridge

DEPTH_FEATURES = ["log1p_total_assigned_reads"]
SIMPLE_FEATURES = ["log1p_total_assigned_reads", "gc3_observed_5prime", "gc_observed_5prime", "cpg_per_100nt_observed_5prime", "cai_human_def_refs_observed_r1"]
STRUCTURE_FEATURES = ["mfe_observed_r1_full_kcal_mol", "mfe_observed_r1_window48_min_kcal_mol", "mfe_observed_r1_window48_mean_kcal_mol"]
MODEL_FEATURES = {"depth_only": DEPTH_FEATURES, "simple": SIMPLE_FEATURES, "simple_plus_structure": SIMPLE_FEATURES + STRUCTURE_FEATURES}

BASES = "TCAG"
AMINO_ACIDS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODON_TABLE = {a + b + c: aa for a, aa_row in zip(BASES, [AMINO_ACIDS[i:i + 16] for i in range(0, 64, 16)]) for b, aa_subrow in zip(BASES, [aa_row[j:j + 4] for j in range(0, 16, 4)]) for c, aa in zip(BASES, aa_subrow)}
SYNONYMS = {codon: sorted(c for c, aa2 in CODON_TABLE.items() if aa2 == aa and aa != "*") for codon, aa in CODON_TABLE.items() if aa != "*"}
STOPS = {c for c, aa in CODON_TABLE.items() if aa == "*"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def read_fasta(path: Path) -> dict[str, str]:
    records, name, chunks = {}, None, []
    for line in path.read_text().splitlines():
        if line.startswith(">"):
            if name is not None:
                records[name] = "".join(chunks)
            name, chunks = line[1:].split()[0], []
        else:
            chunks.append(line.strip())
    if name is not None:
        records[name] = "".join(chunks)
    return records


def translate(sequence: str) -> str:
    if len(sequence) % 3 or set(sequence) - set("ACGT"):
        raise ValueError("invalid DNA sequence")
    return "".join(CODON_TABLE[sequence[i:i + 3]] for i in range(0, len(sequence), 3))


def load_literal_assignment(path: Path, variable: str):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == variable for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(variable)


def reference_weights(references: list[str]) -> dict[str, float]:
    counts = Counter()
    for sequence in references:
        sequence = sequence.upper()
        translate(sequence)
        counts.update(sequence[i:i + 3] for i in range(0, len(sequence), 3))
    for codon in CODON_TABLE:
        if codon not in STOPS and counts[codon] == 0:
            counts[codon] = 0.5
    rscu = {}
    for codon in CODON_TABLE:
        if codon in STOPS:
            continue
        synonymous = SYNONYMS[codon]
        rscu[codon] = counts[codon] / (sum(counts[c] for c in synonymous) / len(synonymous))
    return {codon: value / max(rscu[c] for c in SYNONYMS[codon]) for codon, value in rscu.items()}


def cai_from_weights(sequence: str, weights: dict[str, float]) -> float:
    values = []
    for i in range(0, len(sequence), 3):
        codon = sequence[i:i + 3]
        if codon in STOPS or codon in {"ATG", "TGG"}:
            continue
        value = float(weights[codon])
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"invalid CAI weight for {codon}")
        values.append(math.log(value))
    if not values:
        raise ValueError("CAI has no synonymous codons with variable weights")
    return math.exp(sum(values) / len(values))


def flowseq_score(counts: list[int]) -> float:
    if len(counts) != 8 or any(c < 0 for c in counts) or sum(counts) <= 0:
        raise ValueError("invalid Flow-seq counts")
    return sum((i + 1) * count for i, count in enumerate(counts)) / sum(counts)


def simple_features(sequence: str, total: int, weights: dict[str, float]) -> dict[str, float]:
    if len(sequence) != 300 or set(sequence) - set("ACGT"):
        raise ValueError("observed R1 must be 300 nt ACGT")
    third = sequence[2::3]
    return {
        "log1p_total_assigned_reads": math.log1p(total),
        "gc3_observed_5prime": sum(b in "GC" for b in third) / 100.0,
        "gc_observed_5prime": sum(b in "GC" for b in sequence) / 300.0,
        "cpg_per_100nt_observed_5prime": 100.0 * sum(sequence[i:i + 2] == "CG" for i in range(299)) / 299.0,
        "cai_human_def_refs_observed_r1": cai_from_weights(sequence, weights),
    }


def structure_features(sequence: str) -> dict[str, float]:
    md = RNA.md()
    md.dangles = 0
    md.temperature = 37.0
    rna = sequence.replace("T", "U")
    full = float(RNA.fold_compound(rna, md).mfe()[1])
    windows = []
    for start in range(len(rna) - 48 + 1):
        value = float(RNA.fold_compound(rna[start:start + 48], md).mfe()[1])
        if not math.isfinite(value) or abs(value) >= 100000:
            raise RuntimeError("ViennaRNA failure sentinel")
        windows.append(value)
    if not math.isfinite(full) or abs(full) >= 100000:
        raise RuntimeError("ViennaRNA failure sentinel")
    return {
        "mfe_observed_r1_full_kcal_mol": full,
        "mfe_observed_r1_window48_min_kcal_mol": min(windows),
        "mfe_observed_r1_window48_mean_kcal_mol": float(np.mean(windows)),
    }


def fold_assignments(variant_ids: list[str], seed: int, folds: int) -> dict[str, int]:
    ordered = sorted(variant_ids, key=lambda v: hashlib.sha256(f"{seed}|{v}".encode()).hexdigest())
    return {variant: rank % folds for rank, variant in enumerate(ordered)}


def cross_validated_predictions(rows: list[dict], features: list[str], assignments: dict[str, int], alpha: float, folds: int) -> np.ndarray:
    x = np.asarray([[r[f] for f in features] for r in rows], dtype=np.float64)
    y = np.asarray([r["flowseq_score_r1_only"] for r in rows], dtype=np.float64)
    fold_array = np.asarray([assignments[r["variant_id"]] for r in rows])
    prediction = np.full(len(rows), np.nan)
    for fold in range(folds):
        train, test = fold_array != fold, fold_array == fold
        xm, xs = x[train].mean(axis=0), x[train].std(axis=0, ddof=0)
        ym, ys = y[train].mean(), y[train].std(ddof=0)
        if np.any(xs <= 0) or ys <= 0:
            raise RuntimeError("degenerate train-fold scaling")
        model = Ridge(alpha=alpha, solver="cholesky")
        model.fit((x[train] - xm) / xs, (y[train] - ym) / ys)
        prediction[test] = model.predict((x[test] - xm) / xs) * ys + ym
    if not np.isfinite(prediction).all():
        raise RuntimeError("non-finite OOF prediction")
    return prediction


def effect(y: np.ndarray, simple: np.ndarray, structure: np.ndarray, kind: str) -> float:
    if kind == "delta_spearman":
        return float(spearmanr(y, structure).statistic - spearmanr(y, simple).statistic)
    if kind == "delta_mse":
        return float(np.mean((y - structure) ** 2) - np.mean((y - simple) ** 2))
    raise ValueError(kind)


def paired_statistics(y: np.ndarray, simple: np.ndarray, structure: np.ndarray, kind: str, seed: int, resamples: int) -> dict:
    observed = effect(y, simple, structure, kind)
    n = len(y)
    rng = np.random.default_rng(seed)
    bootstrap = np.empty(resamples)
    for b in range(resamples):
        take = rng.integers(0, n, size=n)
        bootstrap[b] = effect(y[take], simple[take], structure[take], kind)
    rng = np.random.default_rng(seed + 1)
    permutation = np.empty(resamples)
    for b in range(resamples):
        swap = rng.random(n) < 0.5
        a, c = simple.copy(), structure.copy()
        a[swap], c[swap] = structure[swap], simple[swap]
        permutation[b] = effect(y, a, c, kind)
    if not np.isfinite(bootstrap).all() or not np.isfinite(permutation).all():
        raise RuntimeError("non-finite paired resampling")
    exceedances = int(np.sum(np.abs(permutation) >= abs(observed)))
    return {
        "endpoint": kind,
        "observed": observed,
        "ci95_percentile": [float(np.quantile(bootstrap, .025)), float(np.quantile(bootstrap, .975))],
        "permutation_p_two_sided": (1.0 + exceedances) / (resamples + 1.0),
        "bootstrap_resamples": resamples,
        "permutation_resamples": resamples,
        "seed": seed,
    }


def holm(items: list[dict]) -> None:
    order = sorted(range(len(items)), key=lambda i: items[i]["permutation_p_two_sided"])
    running, m = 0.0, len(items)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * items[index]["permutation_p_two_sided"]))
        items[index]["holm_p"] = running


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--protocol", type=Path, required=True)
    args = ap.parse_args()
    started = time.perf_counter()
    repo, protocol_path = args.repo.resolve(), args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    if not protocol["created_before_production"] or protocol["confirmatory_independent_test"]:
        raise RuntimeError("invalid development protocol gate")
    pre = protocol["prerequisites"]
    summary = json.loads((repo / pre["recovery_summary"]).read_text())
    independent = json.loads((repo / pre["recovery_independent"]).read_text())
    finalization = json.loads((repo / pre["recovery_finalization"]).read_text())
    if independent["status"] != "PASS" or finalization["status"] != "PASS" or summary["library_recovery_status"] != "REVIEW_REQUIRED_COUNT_NOT_217":
        raise RuntimeError("recovery prerequisites changed")
    cai_path = Path(pre["cai_wrapper"])
    if sha256(cai_path) != pre["cai_wrapper_sha256"]:
        raise RuntimeError("CAI wrapper hash mismatch")
    references = load_literal_assignment(cai_path, pre["cai_reference_variable"])
    if len(references) != pre["cai_expected_reference_count"]:
        raise RuntimeError("CAI reference count mismatch")
    weights = reference_weights(references)
    fasta = read_fasta(Path(pre["references_r1"]))
    rows = []
    with Path(pre["variant_counts"]).open(newline="") as handle:
        for raw in csv.DictReader(handle):
            counts = [int(raw[f"counts_bin{i}"]) for i in range(1, 9)]
            total = sum(counts)
            if total != int(raw["r1_assigned_reads"]) or total < 1000:
                raise RuntimeError("count/support mismatch")
            sequence = raw["sequence_5prime_300nt"]
            if fasta.get(raw["variant_id"]) != sequence or translate(sequence) != summary["r1_protein_reference"]:
                raise RuntimeError("R1/protein mismatch")
            score = flowseq_score(counts)
            if abs(score - float(raw["flowseq_score_r1_only"])) > 1e-12:
                raise RuntimeError("Flow-seq mismatch")
            row = {"variant_id": raw["variant_id"], "total_assigned_reads": total, "counts_bin1_to_8": counts, "flowseq_score_r1_only": score, "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest()}
            row.update(simple_features(sequence, total, weights))
            row.update(structure_features(sequence))
            rows.append(row)
    expected = protocol["analysis_population"]["expected_rows"]
    if len(rows) != expected or len({r["variant_id"] for r in rows}) != expected or any(r["variant_id"].startswith("GFP_") for r in rows):
        raise RuntimeError("analysis population/identity mismatch")
    assignments = fold_assignments([r["variant_id"] for r in rows], protocol["cross_validation"]["seed"], protocol["cross_validation"]["folds"])
    predictions = {name: cross_validated_predictions(rows, features, assignments, protocol["model"]["alpha"], protocol["cross_validation"]["folds"]) for name, features in MODEL_FEATURES.items()}
    y = np.asarray([r["flowseq_score_r1_only"] for r in rows])
    metrics = {}
    for name, prediction in predictions.items():
        metrics[name] = {"spearman": float(spearmanr(y, prediction).statistic), "pearson": float(pearsonr(y, prediction).statistic), "mse": float(np.mean((y - prediction) ** 2)), "rmse": float(np.sqrt(np.mean((y - prediction) ** 2)))}
    stats = protocol["statistics"]
    B = int(stats["bootstrap_resamples"])
    if int(stats["permutation_resamples"]) != B:
        raise RuntimeError("frozen implementation requires equal B")
    primary = []
    for i, endpoint in enumerate(stats["primary_endpoints"]):
        result = paired_statistics(y, predictions["simple"], predictions["simple_plus_structure"], endpoint, int(stats["seed"]) + i * int(stats["seed_stride"]), B)
        primary.append(result)
    holm(primary)
    for item in primary:
        if item["endpoint"] == "delta_spearman":
            item["direction_pass"] = item["ci95_percentile"][0] > 0 and item["holm_p"] < .05
        else:
            item["direction_pass"] = item["ci95_percentile"][1] < 0 and item["holm_p"] < .05
    gate = all(item["direction_pass"] for item in primary)
    for i, row in enumerate(rows):
        row["fold"] = assignments[row["variant_id"]]
        for name, prediction in predictions.items():
            row["prediction_" + name] = float(prediction[i])
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    status = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"], text=True)
    diff = subprocess.check_output(["git", "-C", str(repo), "diff", "--binary", "HEAD"], text=False)
    output_dir = Path(protocol["output"]["directory"])
    output_dir.mkdir(parents=True, exist_ok=False)
    fields = ["variant_id", "fold", "total_assigned_reads", "flowseq_score_r1_only", *SIMPLE_FEATURES, *STRUCTURE_FEATURES, "prediction_depth_only", "prediction_simple", "prediction_simple_plus_structure", "sequence_sha256"]
    metrics_csv = output_dir / "variant_predictions.csv"
    with metrics_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    payload = {
        "schema": "a8.rk02.mordstein_structure_increment_dev.v1",
        "status": "DEV_STRUCTURE_INCREMENT_PASS_PENDING_INDEPENDENT" if gate else "DEV_STRUCTURE_INCREMENT_NO_GO_PENDING_INDEPENDENT",
        "analysis_status": "DEVELOPMENT_ONLY_NOT_CONFIRMATORY_INDEPENDENT_TEST",
        "protocol_id": protocol["protocol_id"], "protocol_sha256": sha256(protocol_path), "source_article": protocol["source_article"],
        "recovery_summary_sha256": sha256(repo / pre["recovery_summary"]), "recovery_independent_sha256": sha256(repo / pre["recovery_independent"]), "recovery_finalization_sha256": sha256(repo / pre["recovery_finalization"]),
        "variant_counts_sha256": sha256(Path(pre["variant_counts"])), "references_r1_sha256": sha256(Path(pre["references_r1"])), "cai_wrapper_sha256": sha256(cai_path),
        "code_commit": commit, "tracked_tree_clean_at_launch": not bool(status.strip()), "diff_sha256_at_launch": hashlib.sha256(diff).hexdigest(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__, "ViennaRNA": RNA.__version__},
        "n_variants": len(rows), "total_assigned_reads": int(sum(r["total_assigned_reads"] for r in rows)),
        "fold_sizes": {str(f): sum(v == f for v in assignments.values()) for f in range(protocol["cross_validation"]["folds"])},
        "model_metrics": metrics, "primary_effects": {item["endpoint"]: item for item in primary},
        "structure_increment_pass": gate, "variant_metrics": rows,
        "scientific_interpretation": {"development_only": True, "confirmatory_test": False, "functional_untouched_access": False, "protein_ood_evaluation": False, "complete_cds_analysis": False, "causal_inference": False, "full_rk_g1_gate": False, "generator_training_authorized": False, "sota_claim": False, "note": "A positive gate would be a fixed-GFP observed-R1 development signal only; a negative gate remains a valid development result."},
        "variant_predictions_csv": str(metrics_csv), "variant_predictions_csv_sha256": sha256(metrics_csv), "wall_elapsed_s": time.perf_counter() - started,
    }
    audit_path = repo / protocol["output"]["audit"]
    write_json(audit_path, payload)
    print(json.dumps({"status": payload["status"], "structure_increment_pass": gate, "audit": str(audit_path), "n": len(rows), "metrics": metrics, "primary_effects": payload["primary_effects"], "wall_s": payload["wall_elapsed_s"]}))


if __name__ == "__main__":
    main()
