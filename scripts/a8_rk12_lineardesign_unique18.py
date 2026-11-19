#!/usr/bin/env python3
"""Run fixed-source LinearDesign on the frozen unique18 x 11-lambda grid."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

import RNA

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.a8_rk05_lineardesign_official_smoke import (
    cai,
    fold_with_dangles,
    load_official_weights,
    parse_stdout,
    read_fasta,
    sha256,
    translate,
)


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
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["schema"] != "a8-rk12-lineardesign-unique18-grid-v1":
        raise ValueError("unexpected protocol")
    if args.output_dir.exists() or args.audit.exists():
        raise FileExistsError("refusing to overwrite a previous RK-12 production")
    benchmark = Path(protocol["benchmark_fasta"])
    source_dir = Path(protocol["source_dir"]).resolve()
    binary = source_dir / "bin/LinearDesign_2D"
    table = source_dir / protocol["codon_table"]
    materialization = json.loads(args.materialization.read_text())
    build = json.loads(args.build_report.read_text())
    if materialization["commit"] != protocol["source_commit"] or build["commit"] != protocol["source_commit"]:
        raise ValueError("source commit mismatch")
    if sha256(benchmark) != protocol["benchmark_sha256"] or sha256(binary) != protocol["binary_sha256"]:
        raise ValueError("benchmark or binary hash mismatch")
    if Path(materialization["source_dir"]).resolve() != source_dir or Path(build["source_dir"]).resolve() != source_dir:
        raise ValueError("source directory mismatch")
    records = read_fasta(benchmark)
    ordered_ids = protocol["record_order"]
    if (
        not ordered_ids
        or len(ordered_ids) != protocol["expected_record_count"]
        or len(set(ordered_ids)) != len(ordered_ids)
        or any(record_id not in records for record_id in ordered_ids)
        or (protocol["expected_record_count"] == 18 and list(records) != ordered_ids)
    ):
        raise ValueError("record order or count differs from frozen protocol")
    weights = load_official_weights(table)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    report = {
        "schema": protocol["schema"],
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256(args.protocol),
        "created_at": started,
        "status": "RUNNING",
        "scope": protocol["scope"],
        "source_commit": protocol["source_commit"],
        "source_url": materialization["source_url"],
        "archive_sha256": materialization["archive_sha256"],
        "binary_sha256": protocol["binary_sha256"],
        "compiler": build["compiler"],
        "benchmark_fasta": str(benchmark),
        "benchmark_sha256": protocol["benchmark_sha256"],
        "codon_table_sha256": sha256(table),
        "lambda_grid": protocol["lambda_grid"],
        "record_order": protocol["record_order"],
        "execution": protocol["execution"],
        "platform": platform.platform(),
        "vienna_rna_python_version": RNA.__version__,
        "official_mfe_scorer_convention": "ViennaRNA fold_compound at 37 C with dangles=0",
        "secondary_mfe_scorer_convention": "ViennaRNA fold_compound at 37 C with dangles=2",
        "terminal_stop_policy": protocol["execution"]["stop_policy"],
        "forward_calls": None,
        "forward_note": protocol["cost"]["forward_note"],
        "dense_budget_step_auc_v2": None,
        "dense_auc_unavailable_reason": protocol["dense_auc_unavailable_reason"],
        "untouched24_used": False,
        "functional_untouched_used": False,
        "scientific_gate_passed": False,
        "sota_claim": False,
        "runs": [],
        "records": [],
    }
    progress = args.audit.with_name(args.audit.stem + "_in_progress.json")
    try:
        for record_id in protocol["record_order"]:
            source = records[record_id]
            translated = translate(source)
            if translated.count("*") > 1 or "*" in translated[:-1]:
                raise ValueError(f"invalid source stops: {record_id}")
            protein = translated.rstrip("*")
            record_dir = args.output_dir / record_id
            record_dir.mkdir()
            record_started = time.perf_counter()
            record_generation = 0.0
            record_scoring = 0.0
            for lambda_value in protocol["lambda_grid"]:
                lambda_text = f"{lambda_value:.1f}"
                tag = lambda_text.replace(".", "p")
                command = [str(binary), lambda_text, "1", protocol["codon_table"]]
                generation_started = time.perf_counter()
                proc = subprocess.run(
                    command,
                    cwd=source_dir,
                    input=protein + "\n",
                    capture_output=True,
                    text=True,
                    timeout=protocol["execution"]["timeout_seconds_per_call"],
                    env=os.environ.copy(),
                )
                elapsed = time.perf_counter() - generation_started
                stdout_path = record_dir / f"lambda_{tag}.stdout.txt"
                stderr_path = record_dir / f"lambda_{tag}.stderr.txt"
                stdout_path.write_text(proc.stdout)
                stderr_path.write_text(proc.stderr)
                if proc.returncode != 0:
                    raise RuntimeError(f"LinearDesign failed for {record_id} lambda={lambda_text}: {proc.stderr}")
                parsed = parse_stdout(proc.stdout)
                scoring_started = time.perf_counter()
                sequence = parsed["sequence_rna"]
                dna = sequence.replace("U", "T")
                if translate(dna) != protein or len(dna) != 3 * len(protein):
                    raise ValueError(f"non-synonymous official output: {record_id} lambda={lambda_text}")
                independent_cai = cai(sequence, weights)
                structure0, mfe0 = fold_with_dangles(sequence, 0)
                structure2, mfe2 = fold_with_dangles(sequence, 2)
                scoring_elapsed = time.perf_counter() - scoring_started
                run = {
                    "record_id": record_id,
                    "protein_length_aa": len(protein),
                    "protein_sha256": hashlib.sha256(protein.encode()).hexdigest(),
                    "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                    "lambda": lambda_value,
                    "lambda_text": lambda_text,
                    "command": command,
                    "cwd": str(source_dir),
                    "returncode": proc.returncode,
                    "elapsed_s": elapsed,
                    "independent_scoring_elapsed_s_not_generation_cost": scoring_elapsed,
                    "stdout_path": str(stdout_path),
                    "stdout_sha256": sha256(stdout_path),
                    "stderr_path": str(stderr_path),
                    "stderr_sha256": sha256(stderr_path),
                    **parsed,
                    "sequence_dna": dna,
                    "evaluation_sequence_dna": dna + "TAA",
                    "sequence_length_nt": len(dna),
                    "protein_identity_pass": True,
                    "independent_official_table_cai": independent_cai,
                    "cai_abs_delta_from_rounded_official": abs(independent_cai - parsed["official_cai"]),
                    "independent_mfe_kcal_mol": mfe0,
                    "mfe_abs_delta_from_rounded_official": abs(mfe0 - parsed["official_mfe_kcal_mol"]),
                    "independent_structure": structure0,
                    "structure_exact_match": structure0 == parsed["structure"],
                    "independent_default_dangles2_mfe_kcal_mol": mfe2,
                    "independent_default_dangles2_structure": structure2,
                    "default_dangles2_structure_exact_match": structure2 == parsed["structure"],
                    "default_dangles2_mfe_abs_delta_from_rounded_official": abs(mfe2 - parsed["official_mfe_kcal_mol"]),
                }
                if run["cai_abs_delta_from_rounded_official"] > protocol["execution"]["cai_rounding_tolerance"]:
                    raise ValueError(f"CAI rounding gate failed: {record_id} lambda={lambda_text}")
                if run["mfe_abs_delta_from_rounded_official"] > protocol["execution"]["mfe_rounding_tolerance"]:
                    raise ValueError(f"MFE rounding gate failed: {record_id} lambda={lambda_text}")
                if not run["structure_exact_match"]:
                    raise ValueError(f"official-structure mismatch: {record_id} lambda={lambda_text}")
                atomic_json(record_dir / f"lambda_{tag}.json", run)
                report["runs"].append(run)
                record_generation += elapsed
                record_scoring += scoring_elapsed
                report["completed_run_count"] = len(report["runs"])
                report["generation_elapsed_s_so_far"] = sum(x["elapsed_s"] for x in report["runs"])
                report["independent_scoring_elapsed_s_so_far_not_generation_cost"] = sum(
                    x["independent_scoring_elapsed_s_not_generation_cost"] for x in report["runs"]
                )
                atomic_json(progress, report)
                print(json.dumps({
                    "record_id": record_id,
                    "lambda": lambda_value,
                    "completed": len(report["runs"]),
                    "expected": protocol["expected_run_count"],
                    "elapsed_s": elapsed,
                    "official_mfe": parsed["official_mfe_kcal_mol"],
                    "official_cai": parsed["official_cai"],
                }), flush=True)
            record_runs = [x for x in report["runs"] if x["record_id"] == record_id]
            report["records"].append({
                "record_id": record_id,
                "protein_length_aa": len(protein),
                "protein_sha256": hashlib.sha256(protein.encode()).hexdigest(),
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "run_count": len(record_runs),
                "unique_output_sequences": len({x["sequence_rna"] for x in record_runs}),
                "generation_elapsed_s": record_generation,
                "independent_scoring_elapsed_s_not_generation_cost": record_scoring,
                "record_wall_elapsed_s_including_scoring": time.perf_counter() - record_started,
                "best_official_mfe_kcal_mol": min(x["official_mfe_kcal_mol"] for x in record_runs),
                "best_official_cai": max(x["official_cai"] for x in record_runs),
                "all_protein_identity_pass": all(x["protein_identity_pass"] for x in record_runs),
            })
            atomic_json(progress, report)
        if len(report["runs"]) != protocol["expected_run_count"] or len(report["records"]) != protocol["expected_record_count"]:
            raise ValueError("final grid counts do not match frozen protocol")
        report["status"] = (
            "COMPLETE_UNIQUE18_OFFICIAL_LINEARDESIGN_LAMBDA_GRID"
            if protocol["expected_record_count"] == 18
            else "COMPLETE_DEVELOPMENT_OFFICIAL_LINEARDESIGN_LAMBDA_GRID"
        )
        report["run_count"] = len(report["runs"])
        report["record_count"] = len(report["records"])
        report["total_generation_elapsed_s"] = sum(x["elapsed_s"] for x in report["runs"])
        report["total_independent_scoring_elapsed_s_not_generation_cost"] = sum(
            x["independent_scoring_elapsed_s_not_generation_cost"] for x in report["runs"]
        )
        report["unique_output_sequences_global"] = len({(x["record_id"], x["sequence_rna"]) for x in report["runs"]})
        report["all_payload_metrics_verified_in_production"] = True
        report["main_cross_method_comparison"] = False
        atomic_json(args.audit, report)
        print(json.dumps({
            "status": report["status"],
            "records": report["record_count"],
            "runs": report["run_count"],
            "generation_elapsed_s": report["total_generation_elapsed_s"],
            "audit": str(args.audit),
        }), flush=True)
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        atomic_json(args.audit, report)
        raise


if __name__ == "__main__":
    main()
