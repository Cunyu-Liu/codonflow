#!/usr/bin/env python3
"""Run fixed official EnsembleDesign with bounded inputs and raw-output evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import time
from pathlib import Path

import RNA

COMMIT = "cd9324f9574a754063d421e76670bc9fd7555324"
PROTOCOL = "a8_rk05_ensembledesign_official_smoke_v2"
EXAMPLE_FASTA_SHA256 = "43332d8bd92565a81de9d14c1c16434d674aea90d0f62ddb2918004ff86a9fd0"
EXPECTED_EXAMPLE = {
    "seq1": {"sequence_rna": "AUGAAUACCUAUCAUAUUACUCUGCCGUGGCCGCCGAGUAAUAAUAGGUAU", "efe": -18.0},
    "seq2": {"sequence_rna": "AUGAAUGAGUACCAGUUUGUGCUCCCCUAUCCGCCGUCAUUGAAUACUUAUUGGCGGCGGAGGGGGAGCCAGUACUACAUU", "efe": -43.71},
    "seq3": {"sequence_rna": "AUGGCGACCGUUCUCCUGGCGCUUCUGGUUUAUUUGGGUGCGCUGGUGGAUGCGUACCCAAUUAAGCCAGAAGCGCCAGGAGAGGACGCCUUCUUAGGG", "efe": -70.29},
}
STDOUT_RE = re.compile(r">([^|\n]+)\|Ensemble Free Energy:\s*(-?\d+(?:\.\d+)?) kcal/mol\n([ACGU]+)")
RESULT_RE = re.compile(r"^\[\s*(\d+|Best)\]\s+([ACGU]+) \| Ensemble Free Energy: (-?\d+(?:\.\d+)?) kcal/mol$")
RUN_SEQ_RE = re.compile(r"Final mRNA sequence:\s*([ACGU]+)")
CODON_TO_AA = {
    "TTT":"F","TTC":"F","TTA":"L","TTG":"L","TCT":"S","TCC":"S","TCA":"S","TCG":"S",
    "TAT":"Y","TAC":"Y","TAA":"*","TAG":"*","TGT":"C","TGC":"C","TGA":"*","TGG":"W",
    "CTT":"L","CTC":"L","CTA":"L","CTG":"L","CCT":"P","CCC":"P","CCA":"P","CCG":"P",
    "CAT":"H","CAC":"H","CAA":"Q","CAG":"Q","CGT":"R","CGC":"R","CGA":"R","CGG":"R",
    "ATT":"I","ATC":"I","ATA":"I","ATG":"M","ACT":"T","ACC":"T","ACA":"T","ACG":"T",
    "AAT":"N","AAC":"N","AAA":"K","AAG":"K","AGT":"S","AGC":"S","AGA":"R","AGG":"R",
    "GTT":"V","GTC":"V","GTA":"V","GTG":"V","GCT":"A","GCC":"A","GCA":"A","GCG":"A",
    "GAT":"D","GAC":"D","GAA":"E","GAG":"E","GGT":"G","GGC":"G","GGA":"G","GGG":"G",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_fasta(path: Path) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    seen: set[str] = set()
    name = None
    chunks: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith(">"):
            if name is not None:
                records.append((name, "".join(chunks).upper()))
            name = line[1:].split()[0]
            if name in seen:
                raise ValueError(f"duplicate FASTA ID: {name}")
            seen.add(name)
            chunks = []
        elif line and name is not None:
            chunks.append(line)
    if name is not None:
        records.append((name, "".join(chunks).upper()))
    if not records or any(not sequence for _, sequence in records):
        raise ValueError("empty FASTA or empty record")
    return records


def translate(sequence: str) -> str:
    sequence = sequence.upper().replace("U", "T")
    if len(sequence) % 3 or any(sequence[i:i+3] not in CODON_TO_AA for i in range(0, len(sequence), 3)):
        raise ValueError("invalid CDS")
    return "".join(CODON_TO_AA[sequence[i:i+3]] for i in range(0, len(sequence), 3))


def vienna_efe(sequence: str) -> float:
    """Independent ensemble free energy at 37 C with no dangling ends."""
    md = RNA.md()
    md.temperature = 37.0
    md.dangles = 0
    result = RNA.fold_compound(sequence, md).pf()
    return float(result[1])


def parse_official_stdout(stdout: str) -> list[dict]:
    records = [{"record_id": m.group(1), "official_efe_kcal_mol": float(m.group(2)), "sequence_rna": m.group(3)}
               for m in STDOUT_RE.finditer(stdout)]
    if not records or stdout.count(">") != len(records):
        raise ValueError("could not parse complete official stdout records")
    return records


def parse_results(text: str) -> tuple[list[dict], dict]:
    runs: list[dict] = []
    best = None
    for raw in text.splitlines():
        match = RESULT_RE.match(raw.strip())
        if not match:
            continue
        item = {"sequence_rna": match.group(2), "official_efe_kcal_mol": float(match.group(3))}
        if match.group(1) == "Best":
            best = item
        else:
            runs.append({"run_id": int(match.group(1)), **item})
    if not runs or best is None:
        raise ValueError("results.txt lacks run or best payloads")
    return runs, best


def main() -> None:
    parser = argparse.ArgumentParser()
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--input-fasta", type=Path, help="Protein FASTA, normally the official example")
    source_group.add_argument("--benchmark-fasta", type=Path, help="CDS FASTA used to derive one protein input")
    parser.add_argument("--record-id", help="Required with --benchmark-fasta")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--python-deps", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--beam-size", type=int, default=100)
    parser.add_argument("--lr", type=float, default=0.03)
    parser.add_argument("--epsilon", type=float, default=0.5)
    parser.add_argument("--num-iters", type=int, default=3)
    parser.add_argument("--num-runs", type=int, default=2)
    parser.add_argument("--num-threads", type=int, default=4)
    parser.add_argument("--timeout-s", type=int, default=3600)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {args.output_dir}")
    if min(args.beam_size, args.num_iters, args.num_runs, args.num_threads) <= 0:
        raise ValueError("beam/iters/runs/threads must be positive")
    materialization = json.loads(args.materialization.read_text())
    build = json.loads(args.build_report.read_text())
    source_dir = args.source_dir.resolve()
    if materialization["commit"] != COMMIT or build["commit"] != COMMIT or build["status"] != "BUILD_COMPLETE":
        raise ValueError("fixed source or completed build mismatch")
    if source_dir != Path(materialization["source_dir"]).resolve() or source_dir != Path(build["source_dir"]).resolve():
        raise ValueError("source directory mismatch")
    if sha256(Path(materialization["archive"])) != materialization["archive_sha256"]:
        raise ValueError("source archive hash mismatch")
    binary_hashes = {Path(item["path"]).resolve(): item["sha256"] for item in build["binaries"]}
    for binary, expected in binary_hashes.items():
        if sha256(binary) != expected:
            raise ValueError(f"binary hash mismatch: {binary}")
    for relative, item in materialization["key_files"].items():
        if sha256(source_dir / relative) != item["sha256"]:
            raise ValueError(f"official source file changed: {relative}")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    benchmark_info = None
    if args.benchmark_fasta is not None:
        if not args.record_id:
            raise ValueError("--record-id is required with --benchmark-fasta")
        cds_records = dict(read_fasta(args.benchmark_fasta))
        if args.record_id not in cds_records:
            raise ValueError("benchmark record not found")
        source_cds = cds_records[args.record_id].replace("U", "T")
        source_translation = translate(source_cds)
        if "*" in source_translation[:-1] or source_translation.count("*") > 1:
            raise ValueError("source has internal or repeated stops")
        protein = source_translation.rstrip("*")
        input_fasta = args.output_dir / "input_protein.fasta"
        input_fasta.write_text(f">{args.record_id}\n{protein}\n")
        records = [(args.record_id, protein)]
        benchmark_info = {
            "benchmark_fasta": str(args.benchmark_fasta.resolve()),
            "benchmark_sha256": sha256(args.benchmark_fasta),
            "record_id": args.record_id,
            "source_cds_sha256": hashlib.sha256(source_cds.encode()).hexdigest(),
            "derived_protein_fasta": str(input_fasta),
            "derived_protein_fasta_sha256": sha256(input_fasta),
        }
        scope = "bounded_single_record_official_baseline_smoke_not_main_comparison"
    else:
        input_fasta = args.input_fasta.resolve()
        records = read_fasta(input_fasta)
        scope = "official_readme_example_bounded_smoke_not_main_comparison" if sha256(input_fasta) == EXAMPLE_FASTA_SHA256 else "bounded_custom_fasta_official_smoke_not_main_comparison"
    for _, protein in records:
        if not protein or "*" in protein or any(aa not in set(CODON_TO_AA.values()) - {"*"} for aa in protein):
            raise ValueError("input protein contains unsupported residues")
    is_official_example = scope == "official_readme_example_bounded_smoke_not_main_comparison"
    if is_official_example and [name for name, _ in records] != list(EXPECTED_EXAMPLE):
        raise ValueError("official example record IDs differ from the frozen README contract")

    command = [
        "/root/miniconda3/envs/codonflow/bin/python", "EnsembleDesign.py",
        "--fasta", str(input_fasta), "--output_dir", str(args.output_dir),
        "--beam_size", str(args.beam_size), "--lr", str(args.lr), "--epsilon", str(args.epsilon),
        "--num_iters", str(args.num_iters), "--num_runs", str(args.num_runs), "--num_threads", str(args.num_threads),
    ]
    env = os.environ.copy()
    env["PATH"] = "/root/miniconda3/envs/codonflow/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    env["PYTHONPATH"] = str(args.python_deps)
    report = {
        "protocol": PROTOCOL,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "RUNNING",
        "scope": scope,
        "commit": COMMIT,
        "official_repository": materialization["official_repository"],
        "paper_doi": materialization["paper_doi"],
        "source_url": materialization["source_url"],
        "source_dir": str(source_dir),
        "archive_sha256": materialization["archive_sha256"],
        "binary_sha256": {str(path): value for path, value in binary_hashes.items()},
        "input_fasta": str(input_fasta),
        "input_fasta_sha256": sha256(input_fasta),
        "input_record_count": len(records),
        "input_proteins": [{"record_id": name, "length_aa": len(protein), "sha256": hashlib.sha256(protein.encode()).hexdigest()} for name, protein in records],
        "benchmark": benchmark_info,
        "parameters": {"beam_size": args.beam_size, "lr": args.lr, "epsilon": args.epsilon, "num_iters": args.num_iters, "num_runs": args.num_runs, "num_threads": args.num_threads},
        "command": command,
        "cwd": str(source_dir),
        "platform": platform.platform(),
        "vienna_rna_python_version": RNA.__version__,
        "efe_scorer_convention": "ViennaRNA partition function at 37 C with dangles=0; official LinearPartition -V -d0 -b0",
        "terminal_stop_policy": "official EnsembleDesign output has no appended stop; append TAA only for disclosed cross-method evaluation",
        "stop_contract_correction": "v1 incorrectly assumed an official terminal stop and failed; v2 verifies exact input-protein identity without changing official source, parameters or scorer tolerance",
        "forward_calls": None,
        "per_run_elapsed_s": None,
        "cost_note": "one aggregate wall time includes threaded generation, per-run LinearDesign initialization and LinearPartition scoring; no per-run wall time is fabricated",
        "records": [],
    }
    stdout_path = args.output_dir / "official.stdout.txt"
    stderr_path = args.output_dir / "official.stderr.txt"
    try:
        start = time.perf_counter()
        proc = subprocess.run(command, cwd=source_dir, env=env, capture_output=True, text=True, timeout=args.timeout_s)
        elapsed = time.perf_counter() - start
        stdout_path.write_text(proc.stdout)
        stderr_path.write_text(proc.stderr)
        report.update({
            "returncode": proc.returncode,
            "total_elapsed_s": elapsed,
            "stdout_path": str(stdout_path), "stdout_sha256": sha256(stdout_path),
            "stderr_path": str(stderr_path), "stderr_sha256": sha256(stderr_path),
        })
        if proc.returncode != 0:
            raise RuntimeError(f"official EnsembleDesign failed with return code {proc.returncode}")
        stdout_records = {item["record_id"]: item for item in parse_official_stdout(proc.stdout)}
        if set(stdout_records) != {name for name, _ in records}:
            raise ValueError("official stdout record set mismatch")
        max_efe_delta = 0.0
        total_runs = 0
        unique_sequences: set[str] = set()
        for record_id, protein in records:
            record_dir = args.output_dir / record_id
            results_path = record_dir / "results.txt"
            runs, best = parse_results(results_path.read_text())
            if len(runs) != args.num_runs or [r["run_id"] for r in runs] != list(range(1, args.num_runs + 1)):
                raise ValueError(f"run count or IDs mismatch for {record_id}")
            expected_best = min(runs, key=lambda r: (r["official_efe_kcal_mol"], r["run_id"]))
            if (best["sequence_rna"] != expected_best["sequence_rna"]
                    or best["official_efe_kcal_mol"] != expected_best["official_efe_kcal_mol"]):
                raise ValueError(f"best selection mismatch for {record_id}")
            stdout_item = stdout_records[record_id]
            if stdout_item["sequence_rna"] != best["sequence_rna"] or stdout_item["official_efe_kcal_mol"] != best["official_efe_kcal_mol"]:
                raise ValueError(f"stdout/best payload mismatch for {record_id}")
            verified_runs = []
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
                if delta > 0.051:
                    raise ValueError(f"independent EFE exceeds official rounding tolerance: {run_path}: {delta}")
                unique_sequences.add(sequence)
                verified_runs.append({
                    **run,
                    "run_file": str(run_path), "run_file_sha256": sha256(run_path),
                    "results_file": str(results_path), "results_file_sha256": sha256(results_path),
                    "sequence_length_nt": len(sequence),
                    "protein_identity_pass": True,
                    "vienna_efe_kcal_mol": independent_efe,
                    "efe_abs_delta_from_rounded_official": delta,
                })
            report["records"].append({
                "record_id": record_id,
                "protein_length_aa": len(protein),
                "best_run_id": best["run_id"] if "run_id" in best else expected_best["run_id"],
                "best_sequence_rna": best["sequence_rna"],
                "best_official_efe_kcal_mol": best["official_efe_kcal_mol"],
                "stdout_sequence_rna": stdout_item["sequence_rna"],
                "stdout_official_efe_kcal_mol": stdout_item["official_efe_kcal_mol"],
                "runs": verified_runs,
            })
            total_runs += len(verified_runs)
        example_result = None
        if is_official_example:
            comparisons = []
            for item in report["records"]:
                expected = EXPECTED_EXAMPLE[item["record_id"]]
                comparisons.append({
                    "record_id": item["record_id"],
                    "expected_sequence_rna": expected["sequence_rna"],
                    "expected_efe_kcal_mol": expected["efe"],
                    "sequence_exact_match": item["best_sequence_rna"] == expected["sequence_rna"],
                    "efe_exact_match_at_reported_precision": item["best_official_efe_kcal_mol"] == expected["efe"],
                })
            example_result = {"pass": all(c["sequence_exact_match"] and c["efe_exact_match_at_reported_precision"] for c in comparisons), "comparisons": comparisons}
            report["official_example"] = example_result
            if not example_result["pass"]:
                raise ValueError("fixed official README example differs from expected sequence or EFE")
        report.update({
            "status": "BOUNDED_OFFICIAL_EXECUTION_COMPLETE",
            "run_count": total_runs,
            "official_generator_run_count": total_runs,
            "lineardesign_initialization_call_count": total_runs,
            "linearpartition_scoring_call_count": total_runs,
            "unique_output_sequences": len(unique_sequences),
            "max_efe_abs_delta_from_rounded_official": max_efe_delta,
            "all_payload_metrics_verified": True,
            "official_source_unmodified": True,
            "main_baseline_comparison": False,
            "matched_lineardesign_comparison": False,
            "dense_budget_complete": False,
            "functional_ood": False,
            "sota_claim": False,
        })
    except Exception as exc:
        report["status"] = "FAILED"
        report["error"] = repr(exc)
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        args.audit.write_text(json.dumps(report, indent=2) + "\n")
        raise
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "status": report["status"], "input_records": report["input_record_count"], "runs": report["run_count"],
        "elapsed_s": report["total_elapsed_s"], "max_efe_delta": report["max_efe_abs_delta_from_rounded_official"],
        "official_example_pass": report.get("official_example", {}).get("pass"), "audit": str(args.audit),
    }, indent=2))


if __name__ == "__main__":
    main()
