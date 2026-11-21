#!/usr/bin/env python3
"""Count Mordstein R1 reads against the frozen 152 observed-R1 references."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import a8_rk02_mordstein_reference_recovery as recovery


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def flow_score(counts) -> float:
    values = np.asarray(counts, dtype=np.int64)
    if values.shape != (8,) or (values < 0).any() or values.sum() <= 0:
        raise ValueError("Flow-seq score requires eight nonnegative bins with positive support")
    return float(np.dot(np.arange(1, 9, dtype=float), values) / values.sum())


def parse_runs(protocol: dict, require_files: bool = True) -> list[dict]:
    metadata = Path(protocol["inputs"]["metadata_tsv"]["path"])
    if sha256(metadata) != protocol["inputs"]["metadata_tsv"]["sha256"]:
        raise RuntimeError("metadata hash mismatch")
    root = Path(protocol["inputs"]["raw_r1_root"])
    expected = {(name, rep, bin_number)
                for name, context in protocol["contexts"].items()
                for rep in context["replicates"] for bin_number in range(1, 9)}
    observed = []
    import csv
    with metadata.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            matches = [name for name, context in protocol["contexts"].items()
                       if row["experiment_title"] == context["experiment_title"]]
            if not matches:
                continue
            context = matches[0]
            match = re.search(r"^(CM\d+[a-z]?)_Bin([1-8])(?:\D|$)", row["library_name"])
            if not match:
                raise ValueError(f"Missing replicate/Bin in {row['library_name']}")
            replicate = match.group(1)
            bin_number = int(match.group(2))
            key = (context, replicate, bin_number)
            if key not in expected:
                raise ValueError(f"Unexpected context/replicate/bin {key}")
            path = root / row["run_accession"] / f"{row['run_accession']}_1.fastq.gz"
            if require_files and not path.exists():
                raise FileNotFoundError(path)
            observed.append({
                "context": context, "replicate": replicate, "bin": bin_number,
                "run": row["run_accession"], "library_name": row["library_name"],
                "r1": path, "r2": None,
                "expected_md5": row["fastq_md5"].split(";")[0],
                "expected_bytes": int(row["fastq_bytes"].split(";")[0]),
                "url": "https://" + row["fastq_ftp"].split(";")[0],
            })
    keys = [(row["context"], row["replicate"], row["bin"]) for row in observed]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError(f"Context/bin coverage mismatch: observed={len(keys)} expected={len(expected)}")
    return sorted(observed, key=lambda row: (row["context"], row["replicate"], row["bin"]))


def select_runs(protocol: dict, only_runs: list[str]) -> list[dict]:
    selected = set(only_runs)
    runs = parse_runs(protocol, require_files=False)
    if selected:
        runs = [row for row in runs if row["run"] in selected]
        if len(runs) != len(selected):
            raise ValueError("Not all requested runs found")
    for run in runs:
        if not run["r1"].exists():
            raise FileNotFoundError(run["r1"])
    return runs


def outcome_table(counts: pd.DataFrame, protocol: dict) -> tuple[pd.DataFrame, dict]:
    required = {"variant_id", "context", "replicate", "bin", "count"}
    if not required.issubset(counts.columns):
        raise ValueError(f"Missing count columns: {required - set(counts.columns)}")
    references = pd.read_csv(protocol["inputs"]["reference_csv"]["path"],
                             usecols=["variant_id", "sequence_5prime_300nt"])
    expected_variants = references["variant_id"].astype(str).tolist()
    if len(expected_variants) != 152 or len(set(expected_variants)) != 152:
        raise ValueError("The frozen cohort must contain 152 unique variant IDs")
    replicate_rows = []
    qc_rows = []
    for (variant, context, replicate), group in counts.groupby(["variant_id", "context", "replicate"], sort=True):
        bins = group.sort_values("bin")["bin"].astype(int).tolist()
        values = group.sort_values("bin")["count"].astype(np.int64).to_numpy()
        total = int(values.sum())
        passed = bins == list(range(1, 9)) and total >= protocol["outcome_and_qc"]["minimum_assigned_reads_per_variant_per_replicate"]
        qc_rows.append({"variant_id": variant, "context": context, "replicate": replicate,
                        "total_assigned_reads": total, "complete_bins": bins == list(range(1, 9)),
                        "passes_read_support": bool(passed)})
        if passed:
            replicate_rows.append({"variant_id": variant, "context": context, "replicate": replicate,
                                   "total_assigned_reads": total, "replicate_score": flow_score(values)})
    qc = pd.DataFrame(qc_rows)
    expected_cells = 152 * sum(len(c["replicates"]) for c in protocol["contexts"].values())
    if len(qc) != expected_cells:
        raise ValueError(f"Expected {expected_cells} variant/replicate cells, found {len(qc)}")
    replicate_scores = pd.DataFrame(replicate_rows)
    contexts = {}
    for context, definition in protocol["contexts"].items():
        current = replicate_scores[replicate_scores["context"] == context]
        if current.empty:
            contexts[context] = pd.Series(dtype=float)
            continue
        pivot = current.pivot(index="variant_id", columns="replicate", values="replicate_score")
        pivot = pivot.reindex(columns=definition["replicates"])
        pivot = pivot.dropna()
        contexts[context] = pivot.mean(axis=1)
    common = set(expected_variants)
    for scores in contexts.values():
        common &= set(scores.index)
    common = sorted(common)
    rows = []
    for variant in common:
        row = {"variant_id": variant}
        for context, scores in contexts.items():
            row[f"target__{context}"] = float(scores.loc[variant])
        rows.append(row)
    outcome_columns = ["variant_id"] + [f"target__{context}" for context in protocol["contexts"]]
    outcomes = pd.DataFrame(rows, columns=outcome_columns)
    facts = pd.read_csv(protocol["inputs"]["cluster_facts_csv"]["path"])
    outcomes = outcomes.merge(facts[["variant_id", "sequence_cluster_id"]], on="variant_id",
                              how="left", validate="one_to_one")
    if len(outcomes) and outcomes["sequence_cluster_id"].isna().any():
        raise ValueError("Common-cohort variant is missing its frozen sequence cluster")
    n_clusters = int(outcomes["sequence_cluster_id"].nunique()) if len(outcomes) else 0
    feasible = (len(outcomes) >= protocol["outcome_and_qc"]["minimum_common_variants"] and
                n_clusters >= protocol["outcome_and_qc"]["minimum_common_clusters"])
    diagnostics = {
        "expected_variant_replicate_cells": expected_cells,
        "common_variants": len(outcomes),
        "common_clusters": n_clusters,
        "coverage_feasible": bool(feasible),
        "context_pass_counts": {context: int(len(scores)) for context, scores in contexts.items()},
        "qc": qc,
        "replicate_scores": replicate_scores,
    }
    return outcomes, diagnostics


def count_one_run(task: tuple[dict, int, dict, list[str], str]) -> dict:
    """Count one independent run; global outcomes are never written here."""
    run, run_index, protocol, sequences, run_dir_string = task
    run_dir = Path(run_dir_string)
    checkpoint = run_dir / f"{run['run']}.json"
    input_hash = sha256(run["r1"])
    if checkpoint.exists():
        record = json.loads(checkpoint.read_text())
        if record["input_sha256"] != input_hash or len(record["counts"]) != 152:
            raise RuntimeError(f"Checkpoint mismatch: {checkpoint}")
        record["status"] = "existing_verified"
        return record
    assigner = recovery.SeedAssigner(sequences, 8)
    empty = recovery.SeedAssigner([], 8)
    counts, _, _, metrics, audit = recovery.assign_reads(
        [run], 0, False, assigner, empty,
        assignment_cache_max=protocol["fixed_reference_counting"]["assignment_cache_max_unique_sequences_per_run"],
        audit_sample_per_run=protocol["fixed_reference_counting"]["audit_reservoir_reads_per_run"],
        audit_seed=protocol["fixed_reference_counting"]["audit_seed"] + run_index,
    )
    record = {
        "run": run["run"], "context": run["context"], "replicate": run["replicate"],
        "bin": run["bin"], "library_name": run["library_name"],
        "input_path": str(run["r1"]), "input_sha256": input_hash,
        "input_bytes": run["r1"].stat().st_size, "expected_md5": run["expected_md5"],
        "counts": counts[:, 0].astype(int).tolist(), "metrics": metrics[0],
        "audit_samples": audit, "status": "counted",
    }
    temporary = checkpoint.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    temporary.replace(checkpoint)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--freeze-report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--only-runs", nargs="*", default=[])
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        raise ValueError("workers must be between 1 and 16")
    protocol = json.loads(args.protocol.read_text())
    if protocol["schema"] != "a8-rk30-mordstein-matched-context-protocol-v1":
        raise ValueError("wrong protocol")
    freeze = json.loads(args.freeze_report.read_text())
    if freeze.get("status") != "PASS_RK30_LABEL_FREE_FREEZE" or not freeze.get("new_outcome_read_authorized"):
        raise RuntimeError("A passing post-commit label-free freeze is required")
    if freeze.get("protocol_sha256") != sha256(args.protocol):
        raise RuntimeError("Protocol changed after freeze")
    for key in ["reference_csv", "cluster_facts_csv", "feature_implementation", "recovery_implementation"]:
        item = protocol["inputs"][key]
        if sha256(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"Input hash mismatch: {key}")
    references = pd.read_csv(protocol["inputs"]["reference_csv"]["path"],
                             usecols=["variant_id", "sequence_5prime_300nt"])
    variant_ids = references["variant_id"].astype(str).tolist()
    sequences = references["sequence_5prime_300nt"].astype(str).str.upper().tolist()
    if len(set(sequences)) != 152 or {len(seq) for seq in sequences} != {300}:
        raise ValueError("Reference cohort is not 152 unique 300-nt sequences")
    runs = select_runs(protocol, args.only_runs)
    selected = set(args.only_runs)
    args.output_root.mkdir(parents=True, exist_ok=True)
    run_dir = args.output_root / "per_run"
    run_dir.mkdir(exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    wall = time.perf_counter()
    tasks = [(run, run_index, protocol, sequences, str(run_dir)) for run_index, run in enumerate(runs)]
    records = []
    if args.workers == 1:
        results = map(count_one_run, tasks)
        for record in results:
            records.append(record)
            print(json.dumps({"phase": "fixed_reference_count", "run": record["run"],
                              "assigned": record["metrics"]["r1_assigned"],
                              "scanned": record["metrics"]["pairs_scanned"],
                              "status": record["status"]}), flush=True)
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(count_one_run, task) for task in tasks]
            for future in concurrent.futures.as_completed(futures):
                record = future.result()
                records.append(record)
                print(json.dumps({"phase": "fixed_reference_count", "run": record["run"],
                                  "assigned": record["metrics"]["r1_assigned"],
                                  "scanned": record["metrics"]["pairs_scanned"],
                                  "status": record["status"]}), flush=True)
        order = {run["run"]: index for index, run in enumerate(runs)}
        records.sort(key=lambda record: order[record["run"]])
    if selected:
        print(json.dumps({"status": "PASS_SELECTED_RUNS", "runs": len(records)}))
        return
    rows = []
    audits = []
    for record in records:
        for variant, count in zip(variant_ids, record["counts"]):
            rows.append({"variant_id": variant, "context": record["context"],
                         "replicate": record["replicate"], "run": record["run"],
                         "bin": record["bin"], "count": int(count)})
        for sample in record["audit_samples"]:
            sample = dict(sample)
            sample["context"] = record["context"]
            sample["replicate"] = record["replicate"]
            audits.append(sample)
    long_counts = pd.DataFrame(rows)
    counts_path = args.output_root / "fixed_reference_r1_counts.csv"
    if counts_path.exists():
        raise FileExistsError(counts_path)
    long_counts.to_csv(counts_path, index=False)
    pd.DataFrame(audits).to_csv(args.output_root / "assignment_audit.csv", index=False)
    outcomes, diagnostics = outcome_table(long_counts, protocol)
    qc = diagnostics.pop("qc")
    replicate_scores = diagnostics.pop("replicate_scores")
    qc.to_csv(args.output_root / "variant_replicate_qc.csv", index=False)
    replicate_scores.to_csv(args.output_root / "replicate_scores.csv", index=False)
    outcomes.to_csv(args.output_root / "matched_context_outcomes.csv", index=False)
    report = {
        "schema": "a8.rk30.fixed_reference_counts.v1",
        "status": "PASS_COUNTING_COVERAGE_FEASIBLE" if diagnostics["coverage_feasible"] else "MATCHED_CONTEXT_COVERAGE_INFEASIBLE_ZERO_FITS",
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - wall,
        "protocol_sha256": sha256(args.protocol), "reference_order": variant_ids,
        "n_runs": len(records), "n_experiments": 8, "n_variants_before_qc": 152,
        "workers": args.workers,
        **diagnostics,
        "counts_sha256": sha256(counts_path),
        "outcomes_sha256": sha256(args.output_root / "matched_context_outcomes.csv"),
        "qc_sha256": sha256(args.output_root / "variant_replicate_qc.csv"),
        "replicate_scores_sha256": sha256(args.output_root / "replicate_scores.csv"),
        "r2_used": False, "de_novo_centroids": False,
        "new_outcomes_generated": True,
    }
    (args.output_root / "RK30_COUNTING.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "reference_order"}, indent=2))


if __name__ == "__main__":
    main()
