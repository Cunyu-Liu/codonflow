#!/usr/bin/env python3
"""Independent raw-output and scorer verification for bounded EnsembleDesign."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path

import RNA

COMMIT = "cd9324f9574a754063d421e76670bc9fd7555324"
EXPECTED_EXAMPLE = {
    "seq1": ("AUGAAUACCUAUCAUAUUACUCUGCCGUGGCCGCCGAGUAAUAAUAGGUAU", -18.0),
    "seq2": ("AUGAAUGAGUACCAGUUUGUGCUCCCCUAUCCGCCGUCAUUGAAUACUUAUUGGCGGCGGAGGGGGAGCCAGUACUACAUU", -43.71),
    "seq3": ("AUGGCGACCGUUCUCCUGGCGCUUCUGGUUUAUUUGGGUGCGCUGGUGGAUGCGUACCCAAUUAAGCCAGAAGCGCCAGGAGAGGACGCCUUCUUAGGG", -70.29),
}
STDOUT_RE = re.compile(r">([^|\n]+)\|Ensemble Free Energy:\s*(-?\d+(?:\.\d+)?) kcal/mol\n([ACGU]+)")
RESULT_RE = re.compile(r"^\[\s*(\d+|Best)\]\s+([ACGU]+) \| Ensemble Free Energy: (-?\d+(?:\.\d+)?) kcal/mol$")
RUN_SEQ_RE = re.compile(r"Final mRNA sequence:\s*([ACGU]+)")
EFE_RE = re.compile(r"Free Energy of Ensemble:\s*(-?\d+(?:\.\d+)?) kcal/mol", re.IGNORECASE)
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


def fasta(path: Path) -> list[tuple[str, str]]:
    records = []
    name = None
    chunks = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith(">"):
            if name is not None:
                records.append((name, "".join(chunks).upper()))
            name = line[1:].split()[0]
            chunks = []
        elif line and name is not None:
            chunks.append(line)
    if name is not None:
        records.append((name, "".join(chunks).upper()))
    if not records or len({name for name, _ in records}) != len(records):
        raise ValueError("invalid or duplicate FASTA records")
    return records


def translate(sequence: str) -> str:
    sequence = sequence.upper().replace("U", "T")
    if len(sequence) % 3:
        raise ValueError("invalid CDS length")
    return "".join(GENETIC_CODE[sequence[i:i+3]] for i in range(0, len(sequence), 3))


def pf_efe(sequence: str) -> float:
    md = RNA.md()
    md.temperature = 37.0
    md.dangles = 0
    return float(RNA.fold_compound(sequence, md).pf()[1])


def parse_results(text: str) -> tuple[list[dict], dict]:
    runs, best = [], None
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
        raise ValueError("incomplete results.txt")
    return runs, best


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--python-deps", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    materialization = json.loads(args.materialization.read_text())
    build = json.loads(args.build_report.read_text())
    source_dir = args.source_dir.resolve()
    checks: list[dict] = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    key_files_ok = all(digest(source_dir / rel) == item["sha256"] for rel, item in materialization["key_files"].items())
    fixed = (report["commit"] == materialization["commit"] == build["commit"] == COMMIT
             and source_dir == Path(materialization["source_dir"]).resolve() == Path(build["source_dir"]).resolve()
             and digest(Path(materialization["archive"])) == materialization["archive_sha256"] == report["archive_sha256"]
             and materialization["crc_pass"] is True and key_files_ok)
    check("fixed_source_archive_and_key_files", fixed, {"commit": COMMIT, "archive_sha256": report["archive_sha256"], "official_source_unmodified_after_run": key_files_ok})
    binary_ok = all(digest(Path(path)) == expected for path, expected in report["binary_sha256"].items())
    build_ok = (build["status"] == "BUILD_COMPLETE" and not build["missing_binaries"]
                and all(item["returncode"] == 0 and digest(Path(item["stdout_log"])) == item["stdout_sha256"] and digest(Path(item["stderr_log"])) == item["stderr_sha256"] for item in build["builds"])
                and all(digest(Path(item["path"])) == item["sha256"] for item in build["initial_logs"])
                and build["reporting_recovery"]["initial_logs_preserved"] is True and binary_ok)
    check("confirmation_build_and_binary_hashes", build_ok, {"builds": [{"name": b["name"], "returncode": b["returncode"]} for b in build["builds"]], "reporting_recovery": build["reporting_recovery"]})

    input_records = fasta(Path(report["input_fasta"]))
    input_ok = (digest(Path(report["input_fasta"])) == report["input_fasta_sha256"]
                and [name for name, _ in input_records] == [item["record_id"] for item in report["input_proteins"]]
                and all(hashlib.sha256(protein.encode()).hexdigest() == item["sha256"] and len(protein) == item["length_aa"] for (name, protein), item in zip(input_records, report["input_proteins"])))
    benchmark = report.get("benchmark")
    if benchmark is not None:
        source_records = dict(fasta(Path(benchmark["benchmark_fasta"])))
        source_cds = source_records[benchmark["record_id"]].replace("U", "T")
        derived = dict(input_records)[benchmark["record_id"]]
        input_ok &= (digest(Path(benchmark["benchmark_fasta"])) == benchmark["benchmark_sha256"]
                     and hashlib.sha256(source_cds.encode()).hexdigest() == benchmark["source_cds_sha256"]
                     and translate(source_cds).rstrip("*") == derived
                     and digest(Path(benchmark["derived_protein_fasta"])) == benchmark["derived_protein_fasta_sha256"])
    check("frozen_input_identity", input_ok, {"records": [name for name, _ in input_records], "benchmark_record": benchmark["record_id"] if benchmark else None})

    stdout_path = Path(report["stdout_path"])
    stderr_path = Path(report["stderr_path"])
    raw_process_ok = (report["returncode"] == 0 and digest(stdout_path) == report["stdout_sha256"] and digest(stderr_path) == report["stderr_sha256"]
                      and f"All {report['run_count']} runs completed." in stderr_path.read_text())
    check("official_process_exit_and_raw_hashes", raw_process_ok, {"returncode": report["returncode"], "run_count": report["run_count"]})
    params = report["parameters"]
    protocol_ok = (report["protocol"] == "a8_rk05_ensembledesign_official_smoke_v2"
                   and params["beam_size"] == 100 and params["lr"] == 0.03 and params["epsilon"] == 0.5
                   and params["num_iters"] == 3 and params["num_runs"] == 2 and params["num_threads"] == 4
                   and report["run_count"] == report["input_record_count"] * 2 == sum(len(r["runs"]) for r in report["records"]))
    check("bounded_protocol_and_run_counts", protocol_ok, {"parameters": params, "run_count": report["run_count"]})

    env = os.environ.copy()
    env["PATH"] = "/root/miniconda3/envs/codonflow/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    env["PYTHONPATH"] = str(args.python_deps)
    raw_consistency = True
    identity_ok = True
    lp_ok = True
    vienna_ok = True
    best_ok = True
    max_lp_delta = 0.0
    max_vienna_official_delta = 0.0
    max_production_delta = 0.0
    recomputed = []
    stdout_items = {m.group(1): (m.group(3), float(m.group(2))) for m in STDOUT_RE.finditer(stdout_path.read_text())}
    for record in report["records"]:
        record_id = record["record_id"]
        protein = dict(input_records)[record_id]
        record_dir = stdout_path.parent / record_id
        results_path = record_dir / "results.txt"
        runs, best = parse_results(results_path.read_text())
        production_runs = {r["run_id"]: r for r in record["runs"]}
        raw_consistency &= len(runs) == len(production_runs) == 2
        for run in runs:
            production = production_runs[run["run_id"]]
            run_path = record_dir / f"run_{run['run_id']}.txt"
            raw_sequences = RUN_SEQ_RE.findall(run_path.read_text())
            raw_consistency &= (len(raw_sequences) == 1 and raw_sequences[0] == run["sequence_rna"] == production["sequence_rna"]
                                and run["official_efe_kcal_mol"] == production["official_efe_kcal_mol"]
                                and digest(run_path) == production["run_file_sha256"] and digest(results_path) == production["results_file_sha256"])
            sequence = run["sequence_rna"]
            identity_ok &= translate(sequence) == protein and len(sequence) == 3 * len(protein) and production["protein_identity_pass"] is True
            proc = subprocess.run(["/root/miniconda3/envs/codonflow/bin/python", "./linearpartition", "-V", "-d0", "-b0"], cwd=source_dir / "tools/LinearPartition", env=env, input=sequence + "\n", text=True, capture_output=True, timeout=300)
            match = EFE_RE.search(proc.stderr)
            lp_value = float(match.group(1)) if proc.returncode == 0 and match else math.nan
            lp_delta = abs(lp_value - run["official_efe_kcal_mol"]) if math.isfinite(lp_value) else math.inf
            max_lp_delta = max(max_lp_delta, lp_delta)
            lp_ok &= lp_delta <= 0.011
            vienna_value = pf_efe(sequence)
            production_delta = abs(vienna_value - production["vienna_efe_kcal_mol"])
            official_delta = abs(vienna_value - run["official_efe_kcal_mol"])
            max_production_delta = max(max_production_delta, production_delta)
            max_vienna_official_delta = max(max_vienna_official_delta, official_delta)
            vienna_ok &= production_delta <= 1e-9 and official_delta <= 0.051
            recomputed.append({"record_id": record_id, "run_id": run["run_id"], "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(), "official_efe": run["official_efe_kcal_mol"], "rerun_linearpartition_efe": lp_value, "vienna_efe": vienna_value, "protein_identity_pass": translate(sequence) == protein})
        expected_best = min(runs, key=lambda r: (r["official_efe_kcal_mol"], r["run_id"]))
        best_ok &= (best["sequence_rna"] == expected_best["sequence_rna"] == record["best_sequence_rna"]
                    and best["official_efe_kcal_mol"] == expected_best["official_efe_kcal_mol"] == record["best_official_efe_kcal_mol"]
                    and stdout_items.get(record_id) == (record["best_sequence_rna"], record["best_official_efe_kcal_mol"])
                    and record["best_run_id"] == expected_best["run_id"])
    check("raw_run_and_results_consistency", raw_consistency, {"records": len(report["records"]), "runs": len(recomputed)})
    check("synonymous_identity_and_no_appended_stop", identity_ok, {"terminal_stop_policy": report["terminal_stop_policy"]})
    check("independent_linearpartition_efe", lp_ok, {"max_abs_delta": max_lp_delta, "convention": "-V -d0 -b0"})
    check("independent_vienna_partition_efe", vienna_ok, {"max_production_delta": max_production_delta, "max_rounded_official_delta": max_vienna_official_delta, "vienna_rna_python_version": RNA.__version__})
    check("best_selection_and_stdout", best_ok, {"records": len(stdout_items)})
    if report["scope"] == "official_readme_example_bounded_smoke_not_main_comparison":
        example_ok = set(EXPECTED_EXAMPLE) == set(stdout_items)
        for record_id, (sequence, efe) in EXPECTED_EXAMPLE.items():
            example_ok &= stdout_items.get(record_id) == (sequence, efe)
        example_ok &= report.get("official_example", {}).get("pass") is True
        check("official_readme_example_exact", example_ok, {"records": 3, "expected_efe": {key: value[1] for key, value in EXPECTED_EXAMPLE.items()}})
    else:
        check("bounded_benchmark_scope", report["scope"] == "bounded_single_record_official_baseline_smoke_not_main_comparison" and benchmark is not None and len(input_records) == 1, {"record_id": benchmark["record_id"] if benchmark else None, "official_example_claim": False})
    costs_ok = (math.isfinite(report["total_elapsed_s"]) and report["total_elapsed_s"] > 0
                and report["forward_calls"] is None and report["per_run_elapsed_s"] is None
                and report["official_generator_run_count"] == report["lineardesign_initialization_call_count"] == report["linearpartition_scoring_call_count"] == report["run_count"])
    check("aggregate_cost_ledger", costs_ok, {"total_elapsed_s": report["total_elapsed_s"], "generator_and_scorer_calls": report["run_count"], "per_run_elapsed_s": None})
    flags_ok = (report["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE" and report["all_payload_metrics_verified"] is True
                and report["main_baseline_comparison"] is False and report["matched_lineardesign_comparison"] is False
                and report["dense_budget_complete"] is False and report["functional_ood"] is False and report["sota_claim"] is False
                and report["unique_output_sequences"] == len({r["sequence_rna"] for rec in report["records"] for r in rec["runs"]}))
    check("scientific_scope_flags", flags_ok, {"main_baseline_comparison": False, "matched_lineardesign_comparison": False, "sota_claim": False})

    passed = sum(c["pass"] for c in checks)
    output = {
        "protocol": "a8_rk05_ensembledesign_independent_verification_v2",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if passed == len(checks) else "FAIL",
        "source_report": str(args.report),
        "source_report_sha256": digest(args.report),
        "independent_production_import": False,
        "check_count": len(checks),
        "passed_checks": passed,
        "checks": checks,
        "max_numeric_delta": max_production_delta,
        "max_linearpartition_rounded_delta": max_lp_delta,
        "max_vienna_official_rounded_delta": max_vienna_official_delta,
        "recomputed": recomputed,
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"status": output["status"], "passed": passed, "total": len(checks), "max_numeric_delta": max_production_delta, "max_linearpartition_rounded_delta": max_lp_delta, "max_vienna_official_rounded_delta": max_vienna_official_delta}, indent=2))
    if output["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
