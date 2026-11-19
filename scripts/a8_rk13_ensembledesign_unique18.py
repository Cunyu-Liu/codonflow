#!/usr/bin/env python3
"""Execute frozen official EnsembleDesign 11-run actual sets on unique18."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

import RNA

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.a8_rk05_ensembledesign_official_smoke import (
    parse_official_stdout,
    parse_results,
    read_fasta,
    translate,
    vienna_efe,
    RUN_SEQ_RE,
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists() or args.audit.exists():
        raise FileExistsError("refusing to overwrite EnsembleDesign unique18 outputs or audit")
    protocol = json.loads(args.protocol.read_text())
    if protocol["schema"] != "a8-rk13-ensembledesign-unique18-v1" or protocol["status"] != "FROZEN_BEFORE_EXECUTION":
        raise ValueError("unexpected or non-frozen unique18 protocol")
    materialization = json.loads(args.materialization.read_text())
    build = json.loads(args.build_report.read_text())
    commit = protocol["source_commit"]
    source_dir = Path(protocol["source_dir"]).resolve()
    if materialization["commit"] != commit or build["commit"] != commit or build["status"] != "BUILD_COMPLETE":
        raise ValueError("fixed source or completed build mismatch")
    if source_dir != Path(materialization["source_dir"]).resolve() or source_dir != Path(build["source_dir"]).resolve():
        raise ValueError("source directory mismatch")
    if sha256(Path(materialization["archive"])) != protocol["archive_sha256"] or materialization["archive_sha256"] != protocol["archive_sha256"]:
        raise ValueError("source archive hash mismatch")
    binary_hashes = {Path(item["path"]).resolve(): item["sha256"] for item in build["binaries"]}
    for binary, expected in binary_hashes.items():
        if sha256(binary) != expected:
            raise ValueError(f"binary hash mismatch: {binary}")
    for relative, item in materialization["key_files"].items():
        if sha256(source_dir / relative) != item["sha256"]:
            raise ValueError(f"official source file changed: {relative}")
    benchmark = Path(protocol["benchmark_fasta"])
    if sha256(benchmark) != protocol["benchmark_sha256"]:
        raise ValueError("benchmark hash mismatch")
    records = dict(read_fasta(benchmark))
    if list(records) != protocol["record_order"] or len(records) != protocol["expected_record_count"]:
        raise ValueError("record order or count mismatch")
    parameters = protocol["parameters"]
    if parameters["num_runs"] * len(records) != protocol["expected_run_count"]:
        raise ValueError("run-count contract mismatch")

    args.output_root.mkdir(parents=True, exist_ok=False)
    report = {
        "schema": protocol["schema"],
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256(args.protocol),
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "RUNNING",
        "scope": protocol["scope"],
        "commit": commit,
        "official_repository": materialization["official_repository"],
        "paper_doi": materialization["paper_doi"],
        "source_url": materialization["source_url"],
        "source_dir": str(source_dir),
        "archive_sha256": protocol["archive_sha256"],
        "binary_sha256": {str(path): value for path, value in binary_hashes.items()},
        "benchmark_fasta": str(benchmark),
        "benchmark_sha256": protocol["benchmark_sha256"],
        "record_order": protocol["record_order"],
        "parameters": parameters,
        "execution": protocol["execution"],
        "platform": platform.platform(),
        "vienna_rna_python_version": RNA.__version__,
        "terminal_stop_policy": protocol["execution"]["stop_policy"],
        "cost": protocol["cost"],
        "dense_budget_step_auc_v2": None,
        "time_matched_comparison": False,
        "scientific_gate_passed": False,
        "sota_claim": False,
        "records": [],
    }
    progress = args.audit.with_name(args.audit.stem + "_in_progress.json")
    started_all = time.perf_counter()
    try:
        for record_index, record_id in enumerate(protocol["record_order"]):
            source_cds = records[record_id].replace("U", "T")
            source_translation = translate(source_cds)
            if "*" in source_translation[:-1] or source_translation.count("*") != 1:
                raise ValueError(f"invalid source stop contract: {record_id}")
            protein = source_translation[:-1]
            work = args.output_root / record_id
            work.mkdir(parents=False, exist_ok=False)
            input_fasta = work / "input_protein.fasta"
            input_fasta.write_text(f">{record_id}\n{protein}\n")
            command = [
                "/root/miniconda3/envs/codonflow/bin/python", "EnsembleDesign.py",
                "--fasta", str(input_fasta), "--output_dir", str(work),
                "--beam_size", str(parameters["beam_size"]), "--lr", str(parameters["lr"]),
                "--epsilon", str(parameters["epsilon"]), "--num_iters", str(parameters["num_iters"]),
                "--num_runs", str(parameters["num_runs"]), "--num_threads", str(parameters["num_threads"]),
            ]
            env = os.environ.copy()
            env["PATH"] = "/root/miniconda3/envs/codonflow/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            env["PYTHONPATH"] = build["python_deps"]
            start = time.perf_counter()
            proc = subprocess.run(command, cwd=source_dir, env=env, capture_output=True, text=True,
                                  timeout=parameters["timeout_seconds_per_record"])
            elapsed = time.perf_counter() - start
            stdout_path = work / "official.stdout.txt"
            stderr_path = work / "official.stderr.txt"
            stdout_path.write_text(proc.stdout)
            stderr_path.write_text(proc.stderr)
            if proc.returncode != 0:
                raise RuntimeError(f"official EnsembleDesign failed for {record_id}: {proc.returncode}: {stderr_path}")
            stdout_records = parse_official_stdout(proc.stdout)
            if len(stdout_records) != 1 or stdout_records[0]["record_id"] != record_id:
                raise ValueError(f"official stdout record mismatch: {record_id}")
            stdout_item = stdout_records[0]
            record_dir = work / record_id
            results_path = record_dir / "results.txt"
            runs, best = parse_results(results_path.read_text())
            if len(runs) != parameters["num_runs"] or [r["run_id"] for r in runs] != list(range(1, parameters["num_runs"] + 1)):
                raise ValueError(f"run count or IDs mismatch: {record_id}")
            expected_best = min(runs, key=lambda r: (r["official_efe_kcal_mol"], r["run_id"]))
            if best["sequence_rna"] != expected_best["sequence_rna"] or best["official_efe_kcal_mol"] != expected_best["official_efe_kcal_mol"]:
                raise ValueError(f"best selection mismatch: {record_id}")
            if stdout_item["sequence_rna"] != best["sequence_rna"] or stdout_item["official_efe_kcal_mol"] != best["official_efe_kcal_mol"]:
                raise ValueError(f"stdout/best payload mismatch: {record_id}")
            verified_runs = []
            max_efe_delta = 0.0
            for run in runs:
                run_path = record_dir / f"run_{run['run_id']}.txt"
                raw = run_path.read_text()
                raw_sequences = RUN_SEQ_RE.findall(raw)
                if len(raw_sequences) != 1 or raw_sequences[0] != run["sequence_rna"]:
                    raise ValueError(f"raw run sequence mismatch: {run_path}")
                sequence = run["sequence_rna"]
                if translate(sequence) != protein or len(sequence) != 3 * len(protein):
                    raise ValueError(f"non-synonymous or length-contract failure: {run_path}")
                independent_efe = vienna_efe(sequence)
                delta = abs(independent_efe - run["official_efe_kcal_mol"])
                max_efe_delta = max(max_efe_delta, delta)
                if delta > protocol["execution"]["efe_rounding_tolerance"]:
                    raise ValueError(f"independent EFE exceeds tolerance: {run_path}: {delta}")
                evaluation_sequence = sequence.replace("U", "T") + "TAA"
                if translate(evaluation_sequence) != source_translation:
                    raise ValueError(f"disclosed TAA evaluation identity failure: {run_path}")
                verified_runs.append({
                    **run,
                    "run_file": str(run_path), "run_file_sha256": sha256(run_path),
                    "results_file": str(results_path), "results_file_sha256": sha256(results_path),
                    "sequence_length_nt": len(sequence),
                    "protein_identity_pass": True,
                    "vienna_efe_kcal_mol": independent_efe,
                    "efe_abs_delta_from_rounded_official": delta,
                    "evaluation_sequence_dna": evaluation_sequence,
                    "evaluation_sequence_sha256": hashlib.sha256(evaluation_sequence.encode()).hexdigest(),
                })
            record_result = {
                "record_id": record_id,
                "source_cds_sha256": hashlib.sha256(source_cds.encode()).hexdigest(),
                "protein_length_aa": len(protein),
                "input_protein_fasta": str(input_fasta),
                "input_protein_fasta_sha256": sha256(input_fasta),
                "command": command,
                "returncode": proc.returncode,
                "elapsed_s": elapsed,
                "stdout_path": str(stdout_path), "stdout_sha256": sha256(stdout_path),
                "stderr_path": str(stderr_path), "stderr_sha256": sha256(stderr_path),
                "best_run_id": expected_best["run_id"],
                "best_sequence_rna": best["sequence_rna"],
                "best_official_efe_kcal_mol": best["official_efe_kcal_mol"],
                "stdout_sequence_rna": stdout_item["sequence_rna"],
                "stdout_official_efe_kcal_mol": stdout_item["official_efe_kcal_mol"],
                "unique_output_sequences": len({r["sequence_rna"] for r in verified_runs}),
                "max_efe_abs_delta_from_rounded_official": max_efe_delta,
                "runs": verified_runs,
            }
            report["records"].append(record_result)
            compact = {
                "status": "RUNNING",
                "record_id": record_id,
                "completed_records": len(report["records"]),
                "completed_runs": sum(len(r["runs"]) for r in report["records"]),
                "elapsed_s": elapsed,
                "unique_output_sequences": record_result["unique_output_sequences"],
                "max_efe_abs_delta_from_rounded_official": max_efe_delta,
            }
            atomic_json(progress, compact)
            print(json.dumps(compact), flush=True)
        if len(report["records"]) != protocol["expected_record_count"]:
            raise ValueError("incomplete unique18 records")
        all_runs = [run for record in report["records"] for run in record["runs"]]
        if len(all_runs) != protocol["expected_run_count"]:
            raise ValueError("incomplete official runs")
        report.update({
            "status": "COMPLETE_UNIQUE18_OFFICIAL_ENSEMBLEDESIGN_11RUN",
            "record_count": len(report["records"]),
            "run_count": len(all_runs),
            "official_process_count": len(report["records"]),
            "official_generator_run_count": len(all_runs),
            "lineardesign_initialization_call_count": len(all_runs),
            "linearpartition_scoring_call_count": len(all_runs),
            "unique_output_sequences": len({run["sequence_rna"] for run in all_runs}),
            "total_generation_elapsed_s": sum(record["elapsed_s"] for record in report["records"]),
            "max_efe_abs_delta_from_rounded_official": max(run["efe_abs_delta_from_rounded_official"] for run in all_runs),
            "all_payload_metrics_verified": True,
            "official_source_unmodified": True,
            "reanalysis_elapsed_s_including_independent_efe_not_generation_cost": time.perf_counter() - started_all,
            "main_baseline_comparison": False,
            "matched_lineardesign_comparison": False,
            "functional_ood": False,
        })
    except Exception as exc:
        report["status"] = "FAILED"
        report["error"] = repr(exc)
        atomic_json(args.audit, report)
        raise
    atomic_json(args.audit, report)
    print(json.dumps({
        "status": report["status"], "records": report["record_count"], "runs": report["run_count"],
        "unique_output_sequences": report["unique_output_sequences"],
        "generation_seconds": report["total_generation_elapsed_s"],
        "max_efe_delta": report["max_efe_abs_delta_from_rounded_official"], "audit": str(args.audit),
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
