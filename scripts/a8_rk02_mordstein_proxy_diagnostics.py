#!/usr/bin/env python3
"""Frozen fixed-GFP observed-end proxy associations; no predictive training."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path

import numpy as np
import scipy
from scipy.stats import pearsonr, spearmanr

FEATURES = ("gc3_observed_5prime", "gc_observed_5prime", "cpg_per_100nt_observed_5prime")


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


def flowseq_score(counts: list[int]) -> float:
    if len(counts) != 8 or any(count < 0 for count in counts) or sum(counts) <= 0:
        raise ValueError("Flow-seq requires eight non-negative bins with positive total reads")
    return sum((i + 1) * count for i, count in enumerate(counts)) / sum(counts)


def feature_values(sequence: str) -> dict[str, float]:
    if len(sequence) != 300 or set(sequence) - set("ACGT"):
        raise ValueError("observed R1 sequence must be 300 nt ACGT")
    third = sequence[2::3]
    if len(third) != 100:
        raise AssertionError("observed R1 must contain exactly 100 codon-third positions")
    return {
        "gc3_observed_5prime": sum(base in "GC" for base in third) / len(third),
        "gc_observed_5prime": sum(base in "GC" for base in sequence) / len(sequence),
        "cpg_per_100nt_observed_5prime": 100.0 * sum(sequence[i:i + 2] == "CG" for i in range(299)) / 299.0,
    }


def correlation(kind: str, x: np.ndarray, y: np.ndarray) -> float:
    if kind == "spearman":
        return float(spearmanr(x, y).statistic)
    if kind == "pearson":
        return float(pearsonr(x, y).statistic)
    raise ValueError(kind)


def association(x: np.ndarray, y: np.ndarray, kind: str, seed: int, resamples: int) -> dict:
    observed = correlation(kind, x, y)
    n = len(x)
    bootstrap = np.empty(resamples, dtype=np.float64)
    rng = np.random.default_rng(seed)
    for index in range(resamples):
        take = rng.integers(0, n, size=n)
        bootstrap[index] = correlation(kind, x[take], y[take])
    if not np.isfinite(bootstrap).all():
        raise RuntimeError("non-finite bootstrap correlation")
    permutation = np.empty(resamples, dtype=np.float64)
    rng = np.random.default_rng(seed + 1)
    for index in range(resamples):
        permutation[index] = correlation(kind, x, rng.permutation(y))
    if not np.isfinite(permutation).all():
        raise RuntimeError("non-finite permutation correlation")
    exceedances = int(np.sum(np.abs(permutation) >= abs(observed)))
    return {
        "metric": kind,
        "observed": observed,
        "ci95_percentile": [float(np.quantile(bootstrap, 0.025)), float(np.quantile(bootstrap, 0.975))],
        "permutation_p_two_sided": (1.0 + exceedances) / (resamples + 1.0),
        "bootstrap_resamples": resamples,
        "permutation_resamples": resamples,
        "seed": seed,
    }


def holm(items: list[dict]) -> None:
    order = sorted(range(len(items)), key=lambda i: items[i]["permutation_p_two_sided"])
    running = 0.0
    m = len(items)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * items[index]["permutation_p_two_sided"]))
        items[index]["holm_p"] = running


def read_fasta(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    name = None
    chunks: list[str] = []
    for line in path.read_text().splitlines():
        if line.startswith(">"):
            if name is not None:
                records[name] = "".join(chunks)
            name = line[1:].split()[0]
            chunks = []
        else:
            chunks.append(line.strip())
    if name is not None:
        records[name] = "".join(chunks)
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    repo = args.repo.resolve()
    protocol_path = args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    if not protocol["created_before_production"]:
        raise RuntimeError("protocol was not frozen before production")
    pre = protocol["prerequisites"]
    summary = json.loads((repo / pre["recovery_summary"]).read_text())
    independent = json.loads((repo / pre["recovery_independent"]).read_text())
    finalization = json.loads((repo / pre["recovery_finalization"]).read_text())
    if independent["status"] != "PASS" or finalization["status"] != "PASS":
        raise RuntimeError("full observed-end recovery is not finalized")
    if summary["library_recovery_status"] != "REVIEW_REQUIRED_COUNT_NOT_217":
        raise RuntimeError("scientific library boundary changed; refreeze protocol")
    table_path = Path(pre["variant_counts"])
    fasta = read_fasta(Path(pre["references_r1"]))
    rows = []
    with table_path.open(newline="") as handle:
        for raw in csv.DictReader(handle):
            counts = [int(raw[f"counts_bin{i}"]) for i in range(1, 9)]
            total = sum(counts)
            if total != int(raw["r1_assigned_reads"]) or total < 1000:
                raise RuntimeError(f"count/support mismatch: {raw['variant_id']}")
            score = flowseq_score(counts)
            if abs(score - float(raw["flowseq_score_r1_only"])) > 1e-12:
                raise RuntimeError(f"Flow-seq score mismatch: {raw['variant_id']}")
            sequence = raw["sequence_5prime_300nt"]
            if fasta.get(raw["variant_id"]) != sequence:
                raise RuntimeError(f"R1 FASTA mismatch: {raw['variant_id']}")
            features = feature_values(sequence)
            rows.append({
                "variant_id": raw["variant_id"],
                "total_assigned_reads": total,
                "counts_bin1_to_8": counts,
                "flowseq_score_r1_only": score,
                "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
                **features,
            })
    expected = protocol["analysis_population"]["expected_rows"]
    if len(rows) != expected or len({r["variant_id"] for r in rows}) != expected:
        raise RuntimeError("analysis population mismatch")
    if any(r["variant_id"].startswith("GFP_") for r in rows):
        raise RuntimeError("author GFP identity must not be introduced")
    y = np.asarray([r["flowseq_score_r1_only"] for r in rows], dtype=np.float64)
    stats = protocol["statistics"]
    B = int(stats["bootstrap_resamples"])
    if int(stats["permutation_resamples"]) != B:
        raise RuntimeError("this frozen implementation requires equal bootstrap/permutation B")
    results: dict[str, dict] = {}
    primary = []
    for feature_index, feature in enumerate(stats["primary_features"]):
        x = np.asarray([r[feature] for r in rows], dtype=np.float64)
        seed = int(stats["seed"]) + feature_index * int(stats["seed_stride"])
        spearman = association(x, y, "spearman", seed, B)
        pearson = association(x, y, "pearson", seed + 2, B)
        spearman["feature"] = feature
        pearson["feature"] = feature
        primary.append(spearman)
        results[feature] = {"spearman": spearman, "pearson": pearson}
    holm(primary)
    for item in primary:
        item["positive_gate"] = bool(item["ci95_percentile"][0] > 0 and item["holm_p"] < 0.05)
    secondary_feature = "cpg_per_100nt_observed_5prime"
    x = np.asarray([r[secondary_feature] for r in rows], dtype=np.float64)
    secondary_seed = int(stats["seed"]) + len(stats["primary_features"]) * int(stats["seed_stride"])
    secondary = association(x, y, "spearman", secondary_seed, B)
    secondary["feature"] = secondary_feature
    secondary["multiplicity"] = "secondary descriptive; not included in the two-primary Holm family"
    results[secondary_feature] = {"spearman": secondary}
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    status = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"], text=True)
    diff = subprocess.check_output(["git", "-C", str(repo), "diff", "--binary", "HEAD"], text=False)
    output_dir = Path(protocol["output"]["directory"])
    output_dir.mkdir(parents=True, exist_ok=False)
    metrics_csv = output_dir / "variant_metrics.csv"
    with metrics_csv.open("w", newline="") as handle:
        fields = ["variant_id", "total_assigned_reads", "flowseq_score_r1_only", *FEATURES, "sequence_sha256"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    scores = [r["flowseq_score_r1_only"] for r in rows]
    audit_path = repo / protocol["output"]["audit"]
    payload = {
        "schema": "a8.rk02.mordstein_observed_end_proxy_diagnostics.v1",
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256(protocol_path),
        "source_article": protocol["source_article"],
        "recovery_summary_sha256": sha256(repo / pre["recovery_summary"]),
        "recovery_independent_sha256": sha256(repo / pre["recovery_independent"]),
        "recovery_finalization_sha256": sha256(repo / pre["recovery_finalization"]),
        "variant_counts_sha256": sha256(table_path),
        "references_r1_sha256": sha256(Path(pre["references_r1"])),
        "code_commit": commit,
        "tracked_tree_clean_at_launch": not bool(status.strip()),
        "diff_sha256_at_launch": hashlib.sha256(diff).hexdigest(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "n_variants": len(rows),
        "total_assigned_reads": int(sum(r["total_assigned_reads"] for r in rows)),
        "score_summary": {"min": min(scores), "max": max(scores), "mean": float(np.mean(scores)), "sd_sample": float(np.std(scores, ddof=1))},
        "variant_metrics": rows,
        "associations": results,
        "primary_gates": {item["feature"]: item["positive_gate"] for item in primary},
        "scientific_interpretation": {
            "association_only": True,
            "simple_proxy_failure_supported": False,
            "mechanism_model_superiority_supported": False,
            "protein_ood_evaluation": False,
            "complete_cds_analysis": False,
            "author_identity_mapping": False,
            "generator_training_authorized": False,
            "sota_claim": False,
            "note": "Positive GC/GC3 associations would reproduce a simple-proxy association on recovered observed ends, not test incremental mechanism value."
        },
        "variant_metrics_csv": str(metrics_csv),
        "variant_metrics_csv_sha256": sha256(metrics_csv),
        "wall_elapsed_s": time.perf_counter() - started,
    }
    write_json(audit_path, payload)
    print(json.dumps({"status": payload["status"], "audit": str(audit_path), "n": len(rows), "primary_gates": payload["primary_gates"], "wall_s": payload["wall_elapsed_s"]}))


if __name__ == "__main__":
    main()
