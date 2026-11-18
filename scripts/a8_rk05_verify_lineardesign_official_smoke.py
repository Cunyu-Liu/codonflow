#!/usr/bin/env python3
"""Independent raw-output verification for the bounded LinearDesign smoke."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path

import RNA

COMMIT = "f0126ca89a8b853088b4bccfd2cc8c378d3678be"
EXPECTED_LAMBDAS = [0.0, 0.5, 1.0]
OFFICIAL_MFE_DANGLES = 0
DEFAULT_VIENNA_DANGLES = 2
GENETIC_CODE = {
    "TTT":"F","TTC":"F","TTA":"L","TTG":"L","TCT":"S","TCC":"S","TCA":"S","TCG":"S",
    "TAT":"Y","TAC":"Y","TAA":"*","TAG":"*","TGT":"C","TGC":"C","TGA":"*","TGG":"W",
    "CTT":"L","CTC":"L","CTA":"L","CTG":"L","CCT":"P","CCC":"P","CCA":"P","CCG":"P",
    "CAT":"H","CAC":"H","CAA":"Q","CAG":"Q","CGT":"R","CGC":"R","CGA":"R","CGG":"R",
    "ATT":"I","ATC":"I","ATA":"I","ATG":"M","ACT":"T","ACC":"T","ACA":"T","ACG":"T",
    "AAT":"N","AAC":"N","AAA":"K","AAG":"K","AGT":"S","AGC":"S","AGA":"R","AGG":"R",
    "GTT":"V","GTC":"V","GTA":"V","GTG":"V","GCT":"A","GCC":"A","GCA":"A","GCG":"A",
    "GAT":"D","GAC":"D","GAA":"E","GAG":"E","GGT":"G","GGC":"G","GGA":"G","GGG":"G",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fasta_record(path: Path, record_id: str) -> str:
    chunks: list[str] = []
    found = False
    for raw in path.read_text().splitlines():
        if raw.startswith(">"):
            if found:
                break
            found = raw[1:].split()[0] == record_id
        elif found:
            chunks.append(raw.strip())
    if not found or not chunks:
        raise ValueError("record not found")
    return "".join(chunks).upper().replace("U", "T")


def translate(sequence: str) -> str:
    if len(sequence) % 3:
        raise ValueError("invalid CDS length")
    return "".join(GENETIC_CODE[sequence[i:i+3]] for i in range(0, len(sequence), 3))


def official_weights(path: Path) -> dict[str, float]:
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))[1:]
    values = {r[0]: (r[1], float(r[2])) for r in rows if r}
    maxima: dict[str, float] = {}
    for aa, value in values.values():
        maxima[aa] = max(maxima.get(aa, 0.0), value)
    return {codon: value / maxima[aa] for codon, (aa, value) in values.items()}


def geometric_cai(sequence: str, weights: dict[str, float]) -> float:
    return math.exp(sum(math.log(weights[sequence[i:i+3]]) for i in range(0, len(sequence), 3)) / (len(sequence) // 3))


def fold_with_dangles(sequence: str, dangles: int) -> tuple[str, float]:
    md = RNA.md()
    md.temperature = 37.0
    md.dangles = dangles
    structure, energy = RNA.fold_compound(sequence, md).mfe()
    return structure, float(energy)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    materialization = json.loads(args.materialization.read_text())
    build = json.loads(args.build_report.read_text())
    checks: list[dict] = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    source_dir = args.source_dir.resolve()
    binary = source_dir / "bin/LinearDesign_2D"
    table = source_dir / "codon_usage_freq_table_human.csv"
    fixed = (report["commit"] == materialization["commit"] == build["commit"] == COMMIT
             and digest(Path(materialization["archive"])) == materialization["archive_sha256"] == report["archive_sha256"]
             and digest(binary) == build["binary_sha256"] == report["binary_sha256"])
    check("fixed_source_archive_binary", fixed, {"commit": COMMIT, "archive_sha256": report["archive_sha256"], "binary_sha256": report["binary_sha256"]})
    fasta = Path(report["benchmark_fasta"])
    source = fasta_record(fasta, report["record_id"])
    source_translation = translate(source)
    protein = source_translation.rstrip("*")
    input_ok = (digest(fasta) == report["benchmark_sha256"]
                and hashlib.sha256(source.encode()).hexdigest() == report["source_sha256"]
                and hashlib.sha256(protein.encode()).hexdigest() == report["protein_sha256"]
                and len(protein) == report["protein_length_aa"] and "*" not in protein)
    check("frozen_input_identity", input_ok, {"record_id": report["record_id"], "protein_length_aa": len(protein)})
    runs = report["runs"]
    check("bounded_lambda_grid", [r["lambda"] for r in runs] == EXPECTED_LAMBDAS and report["run_count"] == 3,
          {"lambdas": [r["lambda"] for r in runs]})
    weights = official_weights(table)
    raw_ok = True
    identity_ok = True
    per_run_ok = True
    max_cai_production_delta = 0.0
    max_mfe_production_delta = 0.0
    max_default_mfe_production_delta = 0.0
    max_cai_official_delta = 0.0
    max_mfe_official_delta = 0.0
    structure_matches = 0
    recomputed = []
    for run in runs:
        stdout_path = Path(run["stdout_path"])
        stderr_path = Path(run["stderr_path"])
        stdout = stdout_path.read_text()
        raw_ok &= (digest(stdout_path) == run["stdout_sha256"] and digest(stderr_path) == run["stderr_sha256"]
                   and run["returncode"] == 0 and run["command"][1] == run["lambda_text"])
        sequences = re.findall(r"mRNA sequence:\s*([ACGU]+)", stdout)
        structures = re.findall(r"mRNA structure:\s*([.()]+)", stdout)
        metrics = re.findall(r"mRNA folding free energy:\s*(-?\d+(?:\.\d+)?) kcal/mol; mRNA CAI:\s*(\d+(?:\.\d+)?)", stdout)
        if not (len(sequences) == len(structures) == len(metrics) == 1):
            raw_ok = False
            continue
        sequence = sequences[0]
        dna = sequence.replace("U", "T")
        identity_ok &= (translate(dna) == protein and len(dna) == 3 * len(protein)
                        and dna == run["sequence_dna"] and dna + "TAA" == run["evaluation_sequence_dna"])
        cai_value = geometric_cai(sequence, weights)
        structure, mfe_value = fold_with_dangles(sequence, OFFICIAL_MFE_DANGLES)
        default_structure, default_mfe_value = fold_with_dangles(sequence, DEFAULT_VIENNA_DANGLES)
        cai_production_delta = abs(cai_value - run["independent_official_table_cai"])
        mfe_production_delta = abs(mfe_value - run["independent_mfe_kcal_mol"])
        default_mfe_production_delta = abs(default_mfe_value - run["independent_default_dangles2_mfe_kcal_mol"])
        cai_official_delta = abs(cai_value - float(metrics[0][1]))
        mfe_official_delta = abs(mfe_value - float(metrics[0][0]))
        max_cai_production_delta = max(max_cai_production_delta, cai_production_delta)
        max_mfe_production_delta = max(max_mfe_production_delta, mfe_production_delta)
        max_default_mfe_production_delta = max(max_default_mfe_production_delta, default_mfe_production_delta)
        max_cai_official_delta = max(max_cai_official_delta, cai_official_delta)
        max_mfe_official_delta = max(max_mfe_official_delta, mfe_official_delta)
        structure_matches += int(structure == structures[0])
        run_json = json.loads((stdout_path.parent / f"lambda_{run['lambda_text'].replace('.', 'p')}.json").read_text())
        per_run_ok &= (run_json["sequence_rna"] == sequence == run["sequence_rna"]
                       and run_json["structure"] == structures[0] == run["structure"]
                       and float(metrics[0][0]) == run["official_mfe_kcal_mol"]
                       and float(metrics[0][1]) == run["official_cai"]
                       and run_json["independent_default_dangles2_mfe_kcal_mol"] == run["independent_default_dangles2_mfe_kcal_mol"])
        recomputed.append({"lambda": run["lambda"], "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
                           "cai": cai_value, "mfe_dangles0_kcal_mol": mfe_value,
                           "mfe_dangles2_kcal_mol": default_mfe_value,
                           "structure_matches_official": structure == structures[0],
                           "default_structure_matches_official": default_structure == structures[0]})
    check("raw_output_hashes_and_exit", raw_ok, {"runs": len(runs)})
    check("synonymous_identity_and_stop_policy", identity_ok, {"stop_policy": report["terminal_stop_policy"]})
    check("per_run_payload_consistency", per_run_ok, {"runs": len(recomputed)})
    check("independent_cai", max_cai_production_delta <= 1e-12 and max_cai_official_delta <= 0.00101,
          {"max_production_delta": max_cai_production_delta, "max_rounded_official_delta": max_cai_official_delta})
    check("independent_mfe", max_mfe_production_delta <= 1e-9 and max_default_mfe_production_delta <= 1e-9 and max_mfe_official_delta <= 0.051,
          {"official_convention": "dangles=0", "max_production_delta": max_mfe_production_delta,
           "default_dangles2_max_production_delta": max_default_mfe_production_delta,
           "max_rounded_official_delta": max_mfe_official_delta,
           "vienna_rna_python_version": RNA.__version__, "structure_exact_matches": structure_matches})
    costs_ok = (all(math.isfinite(r["elapsed_s"]) and r["elapsed_s"] > 0 for r in runs)
                and math.isclose(report["total_elapsed_s"], sum(r["elapsed_s"] for r in runs), rel_tol=0, abs_tol=1e-9)
                and report["forward_calls"] is None)
    check("bounded_cost_ledger", costs_ok, {"total_elapsed_s": report["total_elapsed_s"], "forward_calls": None})
    flags_ok = (report["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE"
                and report["scope"] == "bounded_single_record_official_baseline_smoke_not_main_comparison"
                and report["all_payload_metrics_verified"] is True
                and report["main_baseline_comparison"] is False and report["sota_claim"] is False
                and report["unique_output_sequences"] == len({r["sequence_rna"] for r in runs}))
    check("scientific_scope_flags", flags_ok, {"main_baseline_comparison": False, "sota_claim": False})
    passed = sum(c["pass"] for c in checks)
    output = {
        "protocol": "a8_rk05_lineardesign_independent_verification_v2",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if passed == len(checks) else "FAIL",
        "source_report": str(args.report),
        "source_report_sha256": digest(args.report),
        "independent_production_import": False,
        "check_count": len(checks),
        "passed_checks": passed,
        "checks": checks,
        "max_numeric_delta": max(max_cai_production_delta, max_mfe_production_delta, max_default_mfe_production_delta),
        "recomputed": recomputed,
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"status": output["status"], "passed": passed, "total": len(checks),
                      "max_numeric_delta": output["max_numeric_delta"]}, indent=2))
    if output["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
