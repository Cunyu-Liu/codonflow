#!/usr/bin/env python3
"""Run the fixed official LinearDesign binary on one frozen benchmark record."""
from __future__ import annotations

import argparse
import csv
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

COMMIT = "f0126ca89a8b853088b4bccfd2cc8c378d3678be"
PROTOCOL = "a8_rk05_lineardesign_official_smoke_v2"
SEQ_RE = re.compile(r"mRNA sequence:\s*([ACGU]+)")
STRUCTURE_RE = re.compile(r"mRNA structure:\s*([.()]+)")
METRIC_RE = re.compile(r"mRNA folding free energy:\s*(-?\d+(?:\.\d+)?) kcal/mol; mRNA CAI:\s*(\d+(?:\.\d+)?)")
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


def read_fasta(path: Path) -> dict[str, str]:
    records: dict[str, list[str]] = {}
    name = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith(">"):
            name = line[1:].split()[0]
            if name in records:
                raise ValueError(f"duplicate FASTA ID: {name}")
            records[name] = []
        elif line and name is not None:
            records[name].append(line)
    return {key: "".join(value).upper().replace("U", "T") for key, value in records.items()}


def translate(sequence: str) -> str:
    sequence = sequence.upper().replace("U", "T")
    if len(sequence) % 3 or any(sequence[i:i+3] not in CODON_TO_AA for i in range(0, len(sequence), 3)):
        raise ValueError("invalid CDS")
    return "".join(CODON_TO_AA[sequence[i:i+3]] for i in range(0, len(sequence), 3))


def load_official_weights(path: Path) -> dict[str, float]:
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))[1:]
    table = {row[0].replace("T", "U"): (row[1], float(row[2])) for row in rows if row}
    if len(table) != 64:
        raise ValueError("official codon table must contain 64 codons")
    maxima: dict[str, float] = {}
    for aa, fraction in table.values():
        maxima[aa] = max(maxima.get(aa, 0.0), fraction)
    return {codon: fraction / maxima[aa] for codon, (aa, fraction) in table.items()}


def cai(sequence: str, weights: dict[str, float]) -> float:
    sequence = sequence.upper().replace("T", "U")
    if len(sequence) % 3 or not sequence:
        raise ValueError("invalid RNA length")
    values = [weights[sequence[i:i+3]] for i in range(0, len(sequence), 3)]
    if any(value <= 0 for value in values):
        raise ValueError("zero CAI weight")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def parse_stdout(stdout: str) -> dict:
    sequences = SEQ_RE.findall(stdout)
    structures = STRUCTURE_RE.findall(stdout)
    metrics = METRIC_RE.findall(stdout)
    if not (len(sequences) == len(structures) == len(metrics) == 1):
        raise ValueError("expected exactly one sequence, structure and metric line")
    sequence, structure = sequences[0], structures[0]
    if len(sequence) != len(structure):
        raise ValueError("sequence/structure length mismatch")
    return {"sequence_rna": sequence, "structure": structure,
            "official_mfe_kcal_mol": float(metrics[0][0]), "official_cai": float(metrics[0][1])}


def fold_with_dangles(sequence: str, dangles: int) -> tuple[str, float]:
    """Score at 37 C with an explicit dangling-end convention."""
    md = RNA.md()
    md.temperature = 37.0
    md.dangles = dangles
    structure, energy = RNA.fold_compound(sequence, md).mfe()
    return structure, float(energy)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-fasta", type=Path, required=True)
    parser.add_argument("--record-id", default="C01H6.8b.1")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--lambdas", nargs="+", default=["0", "0.5", "1"])
    parser.add_argument("--timeout-s", type=int, default=1800)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {args.output_dir}")
    materialization = json.loads(args.materialization.read_text())
    build = json.loads(args.build_report.read_text())
    source_dir = args.source_dir.resolve()
    archive = Path(materialization["archive"])
    binary = source_dir / "bin/LinearDesign_2D"
    table = source_dir / "codon_usage_freq_table_human.csv"
    if materialization["commit"] != COMMIT or build["commit"] != COMMIT:
        raise ValueError("source commit mismatch")
    if source_dir != Path(materialization["source_dir"]).resolve() or source_dir != Path(build["source_dir"]).resolve():
        raise ValueError("source directory mismatch")
    if sha256(archive) != materialization["archive_sha256"] or sha256(binary) != build["binary_sha256"]:
        raise ValueError("archive or binary hash mismatch")
    records = read_fasta(args.benchmark_fasta)
    source = records[args.record_id]
    translated = translate(source)
    if translated.count("*") > 1 or ("*" in translated[:-1]):
        raise ValueError("source has internal or repeated stops")
    protein = translated.rstrip("*")
    if not protein or any(aa not in set(CODON_TO_AA.values()) - {"*"} for aa in protein):
        raise ValueError("source protein contains unsupported residues")
    weights = load_official_weights(table)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "protocol": PROTOCOL,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "RUNNING",
        "scope": "bounded_single_record_official_baseline_smoke_not_main_comparison",
        "commit": COMMIT,
        "source_url": materialization["source_url"],
        "archive_sha256": materialization["archive_sha256"],
        "binary_sha256": build["binary_sha256"],
        "compiler": build["compiler"],
        "record_id": args.record_id,
        "benchmark_fasta": str(args.benchmark_fasta.resolve()),
        "benchmark_sha256": sha256(args.benchmark_fasta),
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "protein_length_aa": len(protein),
        "protein_sha256": hashlib.sha256(protein.encode()).hexdigest(),
        "codon_table_sha256": sha256(table),
        "vienna_rna_python_version": RNA.__version__,
        "official_mfe_scorer_convention": "ViennaRNA fold_compound at 37 C with dangles=0",
        "default_vienna_mfe_convention": "ViennaRNA fold_compound at 37 C with dangles=2; retained separately",
        "scorer_protocol_change": "v1 default-dangles MFE gate failed; v2 uses dangles=0 for official consistency and retains dangles=2 without hiding the difference",
        "platform": platform.platform(),
        "terminal_stop_policy": "official output has no stop; append TAA only for disclosed cross-method evaluation",
        "forward_calls": None,
        "forward_note": "not exposed by official dynamic-programming binary",
        "generator_calls_per_lambda": 1,
        "runs": [],
    }
    for lambda_text in args.lambdas:
        lambda_value = float(lambda_text)
        if not math.isfinite(lambda_value) or lambda_value < 0:
            raise ValueError("lambda must be finite and nonnegative")
        tag = lambda_text.replace(".", "p")
        command = [str(binary), lambda_text, "1", "codon_usage_freq_table_human.csv"]
        start = time.perf_counter()
        proc = subprocess.run(command, cwd=source_dir, input=protein + "\n", capture_output=True,
                              text=True, timeout=args.timeout_s, env=os.environ.copy())
        elapsed = time.perf_counter() - start
        stdout_path = args.output_dir / f"lambda_{tag}.stdout.txt"
        stderr_path = args.output_dir / f"lambda_{tag}.stderr.txt"
        stdout_path.write_text(proc.stdout)
        stderr_path.write_text(proc.stderr)
        if proc.returncode != 0:
            raise RuntimeError(f"LinearDesign lambda={lambda_text} failed: {proc.stderr}")
        parsed = parse_stdout(proc.stdout)
        sequence = parsed["sequence_rna"]
        dna = sequence.replace("U", "T")
        if translate(dna) != protein or len(dna) != 3 * len(protein):
            raise ValueError("official output is not synonymous with the frozen input")
        independent_cai = cai(sequence, weights)
        independent_structure, independent_mfe = fold_with_dangles(sequence, 0)
        default_structure, default_mfe = fold_with_dangles(sequence, 2)
        run = {
            "lambda": lambda_value,
            "lambda_text": lambda_text,
            "command": command,
            "cwd": str(source_dir),
            "returncode": proc.returncode,
            "elapsed_s": elapsed,
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
            "independent_mfe_kcal_mol": independent_mfe,
            "mfe_abs_delta_from_rounded_official": abs(independent_mfe - parsed["official_mfe_kcal_mol"]),
            "independent_structure": independent_structure,
            "structure_exact_match": independent_structure == parsed["structure"],
            "independent_default_dangles2_mfe_kcal_mol": default_mfe,
            "independent_default_dangles2_structure": default_structure,
            "default_dangles2_structure_exact_match": default_structure == parsed["structure"],
            "default_dangles2_mfe_abs_delta_from_rounded_official": abs(default_mfe - parsed["official_mfe_kcal_mol"]),
        }
        if run["cai_abs_delta_from_rounded_official"] > 0.00101:
            raise ValueError("independent CAI exceeds official rounding tolerance")
        if run["mfe_abs_delta_from_rounded_official"] > 0.051:
            raise ValueError("independent MFE exceeds official rounding tolerance")
        (args.output_dir / f"lambda_{tag}.json").write_text(json.dumps(run, indent=2) + "\n")
        report["runs"].append(run)
        print(json.dumps({"record": args.record_id, "lambda": lambda_value, "elapsed_s": elapsed,
                          "official_mfe": parsed["official_mfe_kcal_mol"],
                          "official_cai": parsed["official_cai"]}), flush=True)
    report["status"] = "BOUNDED_OFFICIAL_EXECUTION_COMPLETE"
    report["run_count"] = len(report["runs"])
    report["total_elapsed_s"] = sum(run["elapsed_s"] for run in report["runs"])
    report["unique_output_sequences"] = len({run["sequence_rna"] for run in report["runs"]})
    report["all_payload_metrics_verified"] = True
    report["main_baseline_comparison"] = False
    report["sota_claim"] = False
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "run_count": report["run_count"],
                      "audit": str(args.audit)}, indent=2))


if __name__ == "__main__":
    main()
