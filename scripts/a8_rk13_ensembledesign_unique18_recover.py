#!/usr/bin/env python3
"""Recover RK-13 after the preserved unscaled-ViennaRNA failure without overwriting v1."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

import RNA

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import a8_rk13_ensembledesign_unique18 as base


def vienna_efe_stable(sequence: str) -> float:
    """EFE with the ViennaRNA-supported MFE fold-compound rescaling procedure."""
    md = RNA.md()
    md.temperature = 37.0
    md.dangles = 0
    fc = RNA.fold_compound(sequence, md)
    _, mfe = fc.mfe()
    fc.exp_params_rescale(mfe)
    value = float(fc.pf()[1])
    if not (-1e6 < value < 1e6) or value == 100000.0:
        raise ValueError(f"ViennaRNA rescaled EFE failure sentinel: {value}")
    return value


def verify_record(record_id: str, work: Path, source_cds: str, protein: str,
                  command: list[str], returncode: int, elapsed: float,
                  protocol: dict) -> dict:
    stdout_path = work / "official.stdout.txt"
    stderr_path = work / "official.stderr.txt"
    stdout_records = base.parse_official_stdout(stdout_path.read_text())
    if len(stdout_records) != 1 or stdout_records[0]["record_id"] != record_id:
        raise ValueError(f"official stdout record mismatch: {record_id}")
    stdout_item = stdout_records[0]
    record_dir = work / record_id
    results_path = record_dir / "results.txt"
    runs, best = base.parse_results(results_path.read_text())
    parameters = protocol["parameters"]
    if len(runs) != parameters["num_runs"] or [r["run_id"] for r in runs] != list(range(1, parameters["num_runs"] + 1)):
        raise ValueError(f"run count or IDs mismatch: {record_id}")
    expected_best = min(runs, key=lambda r: (r["official_efe_kcal_mol"], r["run_id"]))
    if best["sequence_rna"] != expected_best["sequence_rna"] or best["official_efe_kcal_mol"] != expected_best["official_efe_kcal_mol"]:
        raise ValueError(f"best selection mismatch: {record_id}")
    if stdout_item["sequence_rna"] != best["sequence_rna"] or stdout_item["official_efe_kcal_mol"] != best["official_efe_kcal_mol"]:
        raise ValueError(f"stdout/best payload mismatch: {record_id}")
    verified_runs = []
    max_efe_delta = 0.0
    source_translation = base.translate(source_cds)
    for run in runs:
        run_path = record_dir / f"run_{run['run_id']}.txt"
        raw_sequences = base.RUN_SEQ_RE.findall(run_path.read_text())
        if len(raw_sequences) != 1 or raw_sequences[0] != run["sequence_rna"]:
            raise ValueError(f"raw run sequence mismatch: {run_path}")
        sequence = run["sequence_rna"]
        if base.translate(sequence) != protein or len(sequence) != 3 * len(protein):
            raise ValueError(f"non-synonymous or length-contract failure: {run_path}")
        independent_efe = vienna_efe_stable(sequence)
        delta = abs(independent_efe - run["official_efe_kcal_mol"])
        max_efe_delta = max(max_efe_delta, delta)
        if delta > protocol["execution"]["efe_rounding_tolerance"]:
            raise ValueError(f"independent rescaled EFE exceeds tolerance: {run_path}: {delta}")
        evaluation_sequence = sequence.replace("U", "T") + "TAA"
        if base.translate(evaluation_sequence) != source_translation:
            raise ValueError(f"disclosed TAA evaluation identity failure: {run_path}")
        verified_runs.append({
            **run,
            "run_file": str(run_path), "run_file_sha256": base.sha256(run_path),
            "results_file": str(results_path), "results_file_sha256": base.sha256(results_path),
            "sequence_length_nt": len(sequence),
            "protein_identity_pass": True,
            "vienna_efe_kcal_mol": independent_efe,
            "independent_efe_method": "mfe_then_exp_params_rescale_then_pf",
            "efe_abs_delta_from_rounded_official": delta,
            "evaluation_sequence_dna": evaluation_sequence,
            "evaluation_sequence_sha256": hashlib.sha256(evaluation_sequence.encode()).hexdigest(),
        })
    return {
        "record_id": record_id,
        "source_cds_sha256": hashlib.sha256(source_cds.encode()).hexdigest(),
        "protein_length_aa": len(protein),
        "input_protein_fasta": str(work / "input_protein.fasta"),
        "input_protein_fasta_sha256": base.sha256(work / "input_protein.fasta"),
        "command": command,
        "returncode": returncode,
        "elapsed_s": elapsed,
        "stdout_path": str(stdout_path), "stdout_sha256": base.sha256(stdout_path),
        "stderr_path": str(stderr_path), "stderr_sha256": base.sha256(stderr_path),
        "best_run_id": expected_best["run_id"],
        "best_sequence_rna": best["sequence_rna"],
        "best_official_efe_kcal_mol": best["official_efe_kcal_mol"],
        "stdout_sequence_rna": stdout_item["sequence_rna"],
        "stdout_official_efe_kcal_mol": stdout_item["official_efe_kcal_mol"],
        "unique_output_sequences": len({r["sequence_rna"] for r in verified_runs}),
        "max_efe_abs_delta_from_rounded_official": max_efe_delta,
        "runs": verified_runs,
    }


def reanalyze_prefix(record: dict, tolerance: float) -> dict:
    record = copy.deepcopy(record)
    max_delta = 0.0
    for run in record["runs"]:
        value = vienna_efe_stable(run["sequence_rna"])
        delta = abs(value - run["official_efe_kcal_mol"])
        if delta > tolerance:
            raise ValueError(f"prefix rescaled EFE exceeds tolerance: {record['record_id']} run {run['run_id']}: {delta}")
        run["vienna_efe_kcal_mol"] = value
        run["independent_efe_method"] = "mfe_then_exp_params_rescale_then_pf"
        run["efe_abs_delta_from_rounded_official"] = delta
        max_delta = max(max_delta, delta)
    record["max_efe_abs_delta_from_rounded_official"] = max_delta
    record["recovery_efe_recomputed"] = True
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--recovery-protocol", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    recovery = json.loads(args.recovery_protocol.read_text())
    if recovery["schema"] != "a8-rk13-ensembledesign-unique18-recovery-v1" or recovery["status"] != "FROZEN_BEFORE_RECOVERY":
        raise ValueError("unexpected or non-frozen recovery protocol")
    if recovery["parent_protocol_sha256"] != base.sha256(args.protocol):
        raise ValueError("parent protocol hash mismatch")
    output_root = Path(recovery["new_output_root"])
    if output_root.exists() or args.audit.exists():
        raise FileExistsError("refusing to overwrite recovery outputs or audit")
    for key in ["failed_report", "failed_console_log"]:
        if base.sha256(Path(recovery[key])) != recovery[key + "_sha256"]:
            raise ValueError(f"preserved failure hash mismatch: {key}")
    for name, expected in recovery["failed_record_files"].items():
        if base.sha256(Path(name)) != expected:
            raise ValueError(f"failed raw evidence changed: {name}")
    failed = json.loads(Path(recovery["failed_report"]).read_text())
    if failed["status"] != "FAILED" or len(failed["records"]) != recovery["accepted_prefix_record_count"]:
        raise ValueError("unexpected failed-report state")
    if [r["record_id"] for r in failed["records"]] != protocol["record_order"][:recovery["accepted_prefix_record_count"]]:
        raise ValueError("accepted prefix order mismatch")
    if recovery["reexecute_record_order"] != protocol["record_order"][recovery["accepted_prefix_record_count"]:]:
        raise ValueError("recovery order does not cover exactly the remaining records")

    materialization = json.loads(args.materialization.read_text())
    build = json.loads(args.build_report.read_text())
    commit = protocol["source_commit"]
    source_dir = Path(protocol["source_dir"]).resolve()
    if materialization["commit"] != commit or build["commit"] != commit or build["status"] != "BUILD_COMPLETE":
        raise ValueError("fixed source or completed build mismatch")
    if base.sha256(Path(materialization["archive"])) != protocol["archive_sha256"]:
        raise ValueError("source archive hash mismatch")
    for item in build["binaries"]:
        if base.sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"binary hash mismatch: {item['path']}")
    for relative, item in materialization["key_files"].items():
        if base.sha256(source_dir / relative) != item["sha256"]:
            raise ValueError(f"official source file changed: {relative}")
    benchmark = Path(protocol["benchmark_fasta"])
    if base.sha256(benchmark) != protocol["benchmark_sha256"]:
        raise ValueError("benchmark hash mismatch")
    records = dict(base.read_fasta(benchmark))
    if list(records) != protocol["record_order"]:
        raise ValueError("record order mismatch")

    output_root.mkdir(parents=True, exist_ok=False)
    report = copy.deepcopy(failed)
    report.pop("error", None)
    report["status"] = "RUNNING_RECOVERY"
    report["records"] = []
    report["recovery"] = {
        **{k: v for k, v in recovery.items() if k != "failed_record_files"},
        "recovery_protocol_sha256": base.sha256(args.recovery_protocol),
        "failed_record_files": recovery["failed_record_files"],
        "selected_records_from_failed_report": [r["record_id"] for r in failed["records"]],
        "selected_records_reexecuted": recovery["reexecute_record_order"],
        "failed_attempt_preserved": True,
        "failed_outputs_overwritten": False,
        "tolerance_changed": False,
    }
    progress = args.audit.with_name(args.audit.stem + "_in_progress.json")
    started = time.perf_counter()
    try:
        tolerance = protocol["execution"]["efe_rounding_tolerance"]
        for old in failed["records"]:
            report["records"].append(reanalyze_prefix(old, tolerance))
        print(json.dumps({"status": "PREFIX_REANALYZED", "records": len(report["records"])}), flush=True)
        for record_id in recovery["reexecute_record_order"]:
            source_cds = records[record_id].replace("U", "T")
            source_translation = base.translate(source_cds)
            if "*" in source_translation[:-1] or source_translation.count("*") != 1:
                raise ValueError(f"invalid source stop contract: {record_id}")
            protein = source_translation[:-1]
            work = output_root / record_id
            work.mkdir(parents=False, exist_ok=False)
            input_fasta = work / "input_protein.fasta"
            input_fasta.write_text(f">{record_id}\n{protein}\n")
            parameters = protocol["parameters"]
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
            proc = base.subprocess.run(command, cwd=source_dir, env=env, capture_output=True, text=True,
                                       timeout=parameters["timeout_seconds_per_record"])
            elapsed = time.perf_counter() - start
            (work / "official.stdout.txt").write_text(proc.stdout)
            (work / "official.stderr.txt").write_text(proc.stderr)
            if proc.returncode != 0:
                raise RuntimeError(f"official EnsembleDesign recovery failed for {record_id}: {proc.returncode}")
            record = verify_record(record_id, work, source_cds, protein, command, proc.returncode, elapsed, protocol)
            record["recovery_reexecution"] = True
            report["records"].append(record)
            compact = {"status": "RUNNING_RECOVERY", "record_id": record_id,
                       "completed_records": len(report["records"]),
                       "completed_runs": sum(len(r["runs"]) for r in report["records"]),
                       "elapsed_s": elapsed, "unique_output_sequences": record["unique_output_sequences"],
                       "max_efe_abs_delta_from_rounded_official": record["max_efe_abs_delta_from_rounded_official"]}
            base.atomic_json(progress, compact)
            print(json.dumps(compact), flush=True)
        if [r["record_id"] for r in report["records"]] != protocol["record_order"]:
            raise ValueError("combined record order mismatch")
        all_runs = [run for record in report["records"] for run in record["runs"]]
        if len(all_runs) != protocol["expected_run_count"]:
            raise ValueError("combined run count mismatch")
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
            "reanalysis_elapsed_s_including_independent_efe_not_generation_cost": time.perf_counter() - started,
            "main_baseline_comparison": False,
            "matched_lineardesign_comparison": False,
            "functional_ood": False,
            "platform_recovery": platform.platform(),
            "recovery_completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
    except Exception as exc:
        report["status"] = "FAILED_RECOVERY"
        report["error"] = repr(exc)
        base.atomic_json(args.audit, report)
        raise
    base.atomic_json(args.audit, report)
    print(json.dumps({"status": report["status"], "records": report["record_count"],
                      "runs": report["run_count"], "unique_output_sequences": report["unique_output_sequences"],
                      "generation_seconds": report["total_generation_elapsed_s"],
                      "max_efe_delta": report["max_efe_abs_delta_from_rounded_official"],
                      "audit": str(args.audit)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
