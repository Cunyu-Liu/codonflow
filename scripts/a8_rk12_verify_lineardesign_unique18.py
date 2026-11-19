#!/usr/bin/env python3
"""Independent raw-output and ViennaRNA verification for the RK-12 grid."""
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
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_fasta(path: Path) -> dict[str, str]:
    records = {}
    name = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith(">"):
            name = line[1:].split()[0]
            if name in records:
                raise ValueError("duplicate FASTA ID")
            records[name] = []
        elif line and name is not None:
            records[name].append(line)
    return {key: "".join(value).upper().replace("U", "T") for key, value in records.items()}


def translate(sequence: str) -> str:
    if len(sequence) % 3:
        raise ValueError("invalid CDS length")
    return "".join(CODON_TO_AA[sequence[i:i+3]] for i in range(0, len(sequence), 3))


def load_weights(path: Path) -> dict[str, float]:
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))[1:]
    table = {row[0].replace("T", "U"): (row[1], float(row[2])) for row in rows if row}
    if len(table) != 64:
        raise ValueError("codon table must have 64 rows")
    maxima = {}
    for aa, fraction in table.values():
        maxima[aa] = max(maxima.get(aa, 0.0), fraction)
    return {codon: fraction / maxima[aa] for codon, (aa, fraction) in table.items()}


def cai(sequence: str, weights: dict[str, float]) -> float:
    values = [weights[sequence[i:i+3]] for i in range(0, len(sequence), 3)]
    return math.exp(sum(math.log(value) for value in values) / len(values))


def fold(sequence: str, dangles: int) -> tuple[str, float]:
    md = RNA.md()
    md.temperature = 37.0
    md.dangles = dangles
    structure, energy = RNA.fold_compound(sequence, md).mfe()
    return structure, float(energy)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    protocol = json.loads(args.protocol.read_text())
    production = json.loads(args.production.read_text())
    materialization = json.loads(args.materialization.read_text())
    build = json.loads(args.build_report.read_text())
    expected_status = (
        "COMPLETE_UNIQUE18_OFFICIAL_LINEARDESIGN_LAMBDA_GRID"
        if protocol["expected_record_count"] == 18
        else "COMPLETE_DEVELOPMENT_OFFICIAL_LINEARDESIGN_LAMBDA_GRID"
    )
    if production["status"] != expected_status:
        raise ValueError("production is not complete")
    benchmark = Path(protocol["benchmark_fasta"])
    source_dir = Path(protocol["source_dir"])
    binary = source_dir / "bin/LinearDesign_2D"
    table = source_dir / protocol["codon_table"]
    records = read_fasta(benchmark)
    weights = load_weights(table)
    checks = []
    failures = []

    def record(name, passed, evidence=None):
        checks.append({"check": name, "pass": bool(passed), "evidence": evidence})
        if not passed:
            failures.append(name)

    record("protocol_hash", production["protocol_sha256"] == sha256(args.protocol))
    record("benchmark_hash", production["benchmark_sha256"] == sha256(benchmark) == protocol["benchmark_sha256"])
    record("source_commit", production["source_commit"] == materialization["commit"] == build["commit"] == protocol["source_commit"])
    record("binary_hash", production["binary_sha256"] == sha256(binary) == build["binary_sha256"] == protocol["binary_sha256"])
    record("table_hash", production["codon_table_sha256"] == sha256(table))
    record("grid_counts", len(production["runs"]) == protocol["expected_run_count"] and len(production["records"]) == protocol["expected_record_count"])
    expected_pairs = [(r, float(l)) for r in protocol["record_order"] for l in protocol["lambda_grid"]]
    observed_pairs = [(r["record_id"], float(r["lambda"])) for r in production["runs"]]
    record("single_worker_grid_order", observed_pairs == expected_pairs)
    record("untouched_and_sota_exclusions", production["untouched24_used"] is False and production["functional_untouched_used"] is False and production["sota_claim"] is False)
    record("dense_auc_null", production["dense_budget_step_auc_v2"] is None and "not successive real-scorer budgets" in production["dense_auc_unavailable_reason"])

    max_cai_delta = 0.0
    max_mfe_delta = 0.0
    max_structure_mismatch = 0
    raw_mismatches = []
    identity_failures = []
    timing_failures = []
    tolerance_failures = []
    for index, run in enumerate(production["runs"]):
        label = f"{run['record_id']}/lambda_{run['lambda_text']}"
        stdout_path = Path(run["stdout_path"])
        stderr_path = Path(run["stderr_path"])
        if not stdout_path.exists() or sha256(stdout_path) != run["stdout_sha256"] or sha256(stderr_path) != run["stderr_sha256"]:
            raw_mismatches.append(label + ":file_hash")
            continue
        stdout = stdout_path.read_text()
        sequences = SEQ_RE.findall(stdout)
        structures = STRUCTURE_RE.findall(stdout)
        metrics = METRIC_RE.findall(stdout)
        if not (len(sequences) == len(structures) == len(metrics) == 1):
            raw_mismatches.append(label + ":parse")
            continue
        sequence, structure = sequences[0], structures[0]
        official_mfe, official_cai = float(metrics[0][0]), float(metrics[0][1])
        if sequence != run["sequence_rna"] or structure != run["structure"] or official_mfe != run["official_mfe_kcal_mol"] or official_cai != run["official_cai"]:
            raw_mismatches.append(label + ":payload")
        source = records[run["record_id"]]
        protein = translate(source).rstrip("*")
        if translate(sequence.replace("U", "T")) != protein or len(sequence) != 3 * len(protein):
            identity_failures.append(label)
        independent_cai = cai(sequence, weights)
        structure0, mfe0 = fold(sequence, 0)
        structure2, mfe2 = fold(sequence, 2)
        cai_delta = abs(independent_cai - run["independent_official_table_cai"])
        mfe_delta = abs(mfe0 - run["independent_mfe_kcal_mol"])
        mfe2_delta = abs(mfe2 - run["independent_default_dangles2_mfe_kcal_mol"])
        max_cai_delta = max(max_cai_delta, cai_delta)
        max_mfe_delta = max(max_mfe_delta, mfe_delta, mfe2_delta)
        if structure0 != run["independent_structure"] or structure2 != run["independent_default_dangles2_structure"] or structure0 != structure:
            max_structure_mismatch += 1
        if cai_delta > 1e-12 or mfe_delta > 1e-9 or mfe2_delta > 1e-9:
            raw_mismatches.append(label + ":independent_numeric")
        if abs(independent_cai - official_cai) > protocol["execution"]["cai_rounding_tolerance"] or abs(mfe0 - official_mfe) > protocol["execution"]["mfe_rounding_tolerance"]:
            tolerance_failures.append(label)
        if not math.isfinite(run["elapsed_s"]) or run["elapsed_s"] <= 0 or not math.isfinite(run["independent_scoring_elapsed_s_not_generation_cost"]) or run["independent_scoring_elapsed_s_not_generation_cost"] < 0:
            timing_failures.append(label)
        if run["evaluation_sequence_dna"] != run["sequence_dna"] + "TAA":
            raw_mismatches.append(label + ":stop_contract")
    record("all_raw_stdout_and_payloads", not raw_mismatches, raw_mismatches[:20])
    record("all_protein_identities", not identity_failures, identity_failures[:20])
    record("all_official_rounding_gates", not tolerance_failures, tolerance_failures[:20])
    record("all_independent_structures", max_structure_mismatch == 0, max_structure_mismatch)
    record("all_generation_and_scoring_times", not timing_failures, timing_failures[:20])
    recomputed_generation = sum(x["elapsed_s"] for x in production["runs"])
    recomputed_scoring = sum(x["independent_scoring_elapsed_s_not_generation_cost"] for x in production["runs"])
    record("total_generation_cost", math.isclose(recomputed_generation, production["total_generation_elapsed_s"], rel_tol=0.0, abs_tol=1e-9), recomputed_generation)
    record("separate_scoring_cost", math.isclose(recomputed_scoring, production["total_independent_scoring_elapsed_s_not_generation_cost"], rel_tol=0.0, abs_tol=1e-9), recomputed_scoring)
    record("unique_sequence_count", production["unique_output_sequences_global"] == len({(x["record_id"], x["sequence_rna"]) for x in production["runs"]}))
    for summary in production["records"]:
        runs = [x for x in production["runs"] if x["record_id"] == summary["record_id"]]
        ok = (
            summary["run_count"] == len(runs) == len(protocol["lambda_grid"])
            and summary["unique_output_sequences"] == len({x["sequence_rna"] for x in runs})
            and math.isclose(summary["generation_elapsed_s"], sum(x["elapsed_s"] for x in runs), rel_tol=0.0, abs_tol=1e-9)
            and summary["best_official_mfe_kcal_mol"] == min(x["official_mfe_kcal_mol"] for x in runs)
            and summary["best_official_cai"] == max(x["official_cai"] for x in runs)
            and summary["all_protein_identity_pass"] is True
        )
        record(f"record_summary:{summary['record_id']}", ok)
    report = {
        "schema": "a8-rk12-lineardesign-independent-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "production": str(args.production),
        "production_sha256": sha256(args.production),
        "protocol_sha256": sha256(args.protocol),
        "run_count": len(production["runs"]),
        "record_count": len(production["records"]),
        "checks": checks,
        "checks_passed": sum(x["pass"] for x in checks),
        "checks_total": len(checks),
        "failed_checks": failures,
        "max_independent_cai_recompute_delta": max_cai_delta,
        "max_independent_mfe_recompute_delta": max_mfe_delta,
        "structure_mismatch_count": max_structure_mismatch,
        "production_module_imported": False,
        "scientific_scope": "official development-panel lambda grid and costs only; no dense budget AUC, untouched, cross-method SOTA or biological-function claim",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
