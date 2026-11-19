#!/usr/bin/env python3
"""Independent raw-file and numerical verification for EnsembleDesign unique18."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path

import RNA

RESULT_RE = re.compile(r"^\[\s*(\d+|Best)\]\s+([ACGU]+) \| Ensemble Free Energy: (-?\d+(?:\.\d+)?) kcal/mol$")
RUN_SEQ_RE = re.compile(r"Final mRNA sequence:\s*([ACGU]+)")
STDOUT_RE = re.compile(r">([^|\n]+)\|Ensemble Free Energy:\s*(-?\d+(?:\.\d+)?) kcal/mol\n([ACGU]+)")
BASES = "TCAG"
CODONS = [a + b + c for a in BASES for b in BASES for c in BASES]
AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
TABLE = dict(zip(CODONS, AAS))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_fasta(path: Path) -> list[tuple[str, str]]:
    records = []
    name = None
    chunks = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith(">"):
            if name is not None:
                records.append((name, "".join(chunks)))
            name = line[1:].split()[0]
            chunks = []
        elif line and name is not None:
            chunks.append(line.upper())
    if name is not None:
        records.append((name, "".join(chunks)))
    return records


def translate(sequence: str) -> str:
    sequence = sequence.replace("U", "T")
    if len(sequence) % 3:
        raise ValueError("partial codon")
    return "".join(TABLE[sequence[i:i + 3]] for i in range(0, len(sequence), 3))


def efe(sequence: str) -> float:
    md = RNA.md()
    md.temperature = 37.0
    md.dangles = 0
    return float(RNA.fold_compound(sequence, md).pf()[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    if args.audit.exists():
        raise FileExistsError("refusing to overwrite independent audit")
    protocol = json.loads(args.protocol.read_text())
    report = json.loads(args.report.read_text())
    materialization = json.loads(args.materialization.read_text())
    build = json.loads(args.build_report.read_text())
    failures = []
    per_record = []
    max_efe_delta = 0.0

    def require(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    require(protocol["schema"] == "a8-rk13-ensembledesign-unique18-v1", "protocol schema")
    require(report["protocol_sha256"] == sha256(args.protocol), "report protocol hash")
    require(report["status"] == "COMPLETE_UNIQUE18_OFFICIAL_ENSEMBLEDESIGN_11RUN", "production completion status")
    require(report["commit"] == protocol["source_commit"] == materialization["commit"] == build["commit"], "source commit chain")
    require(build["status"] == "BUILD_COMPLETE", "build status")
    require(sha256(Path(materialization["archive"])) == protocol["archive_sha256"], "source archive")
    for item in build["binaries"]:
        require(sha256(Path(item["path"])) == item["sha256"], f"binary {item['path']}")
    for relative, item in materialization["key_files"].items():
        require(sha256(Path(protocol["source_dir"]) / relative) == item["sha256"], f"source key file {relative}")
    benchmark_records = dict(read_fasta(Path(protocol["benchmark_fasta"])))
    require(sha256(Path(protocol["benchmark_fasta"])) == protocol["benchmark_sha256"], "benchmark hash")
    require(list(benchmark_records) == protocol["record_order"], "benchmark order")
    require(report["record_order"] == protocol["record_order"], "report order")
    require([r["record_id"] for r in report["records"]] == protocol["record_order"], "record output order")
    require(len(report["records"]) == protocol["expected_record_count"] == 18, "record count")

    observed_runs = 0
    observed_unique = set()
    elapsed_sum = 0.0
    for record in report["records"]:
        record_id = record["record_id"]
        local_failures_before = len(failures)
        try:
            source = benchmark_records[record_id].replace("U", "T")
            source_translation = translate(source)
            require(source_translation.endswith("*") and "*" not in source_translation[:-1], f"{record_id} source stop")
            protein = source_translation[:-1]
            require(record["source_cds_sha256"] == hashlib.sha256(source.encode()).hexdigest(), f"{record_id} source CDS hash")
            require(record["protein_length_aa"] == len(protein), f"{record_id} protein length")
            input_fasta = Path(record["input_protein_fasta"])
            require(sha256(input_fasta) == record["input_protein_fasta_sha256"], f"{record_id} input FASTA hash")
            require(read_fasta(input_fasta) == [(record_id, protein)], f"{record_id} input protein identity")
            stdout_path = Path(record["stdout_path"])
            stderr_path = Path(record["stderr_path"])
            require(sha256(stdout_path) == record["stdout_sha256"], f"{record_id} stdout hash")
            require(sha256(stderr_path) == record["stderr_sha256"], f"{record_id} stderr hash")
            stdout_records = list(STDOUT_RE.finditer(stdout_path.read_text()))
            require(len(stdout_records) == 1, f"{record_id} stdout count")
            if len(stdout_records) == 1:
                match = stdout_records[0]
                require(match.group(1) == record_id, f"{record_id} stdout ID")
                require(match.group(3) == record["best_sequence_rna"], f"{record_id} stdout best sequence")
                require(math.isclose(float(match.group(2)), record["best_official_efe_kcal_mol"], abs_tol=1e-12), f"{record_id} stdout best EFE")
            result_path = Path(record["runs"][0]["results_file"])
            parsed = []
            best = None
            for raw in result_path.read_text().splitlines():
                match = RESULT_RE.match(raw.strip())
                if not match:
                    continue
                item = (match.group(2), float(match.group(3)))
                if match.group(1) == "Best":
                    best = item
                else:
                    parsed.append((int(match.group(1)), *item))
            require(len(parsed) == protocol["parameters"]["num_runs"], f"{record_id} results run count")
            require([r[0] for r in parsed] == list(range(1, protocol["parameters"]["num_runs"] + 1)), f"{record_id} results run order")
            require(best is not None, f"{record_id} best exists")
            expected_best = min(parsed, key=lambda r: (r[2], r[0]))
            if best is not None:
                require(best == (expected_best[1], expected_best[2]), f"{record_id} best recomputation")
                require(best == (record["best_sequence_rna"], record["best_official_efe_kcal_mol"]), f"{record_id} best report")
                require(record["best_run_id"] == expected_best[0], f"{record_id} best run ID")
            require(len(record["runs"]) == protocol["parameters"]["num_runs"], f"{record_id} report run count")
            record_max_delta = 0.0
            for run in record["runs"]:
                observed_runs += 1
                run_path = Path(run["run_file"])
                require(sha256(run_path) == run["run_file_sha256"], f"{record_id} run {run['run_id']} raw hash")
                require(sha256(result_path) == run["results_file_sha256"], f"{record_id} run {run['run_id']} results hash")
                raw_sequences = RUN_SEQ_RE.findall(run_path.read_text())
                require(raw_sequences == [run["sequence_rna"]], f"{record_id} run {run['run_id']} raw sequence")
                require((run["run_id"], run["sequence_rna"], run["official_efe_kcal_mol"]) in parsed, f"{record_id} run {run['run_id']} results payload")
                require(translate(run["sequence_rna"]) == protein, f"{record_id} run {run['run_id']} synonymous identity")
                require(len(run["sequence_rna"]) == 3 * len(protein), f"{record_id} run {run['run_id']} raw length")
                independent = efe(run["sequence_rna"])
                delta = abs(independent - run["official_efe_kcal_mol"])
                max_efe_delta = max(max_efe_delta, delta)
                record_max_delta = max(record_max_delta, delta)
                require(delta <= protocol["execution"]["efe_rounding_tolerance"], f"{record_id} run {run['run_id']} independent EFE")
                require(math.isclose(independent, run["vienna_efe_kcal_mol"], abs_tol=1e-9), f"{record_id} run {run['run_id']} reported independent EFE")
                evaluation = run["sequence_rna"].replace("U", "T") + "TAA"
                require(run["evaluation_sequence_dna"] == evaluation, f"{record_id} run {run['run_id']} disclosed TAA")
                require(translate(evaluation) == source_translation, f"{record_id} run {run['run_id']} evaluation identity")
                require(run["evaluation_sequence_sha256"] == hashlib.sha256(evaluation.encode()).hexdigest(), f"{record_id} run {run['run_id']} evaluation hash")
                observed_unique.add(run["sequence_rna"])
            require(math.isclose(record["max_efe_abs_delta_from_rounded_official"], record_max_delta, abs_tol=1e-12), f"{record_id} max EFE delta")
            require(record["unique_output_sequences"] == len({r["sequence_rna"] for r in record["runs"]}), f"{record_id} unique count")
            require(record["returncode"] == 0 and record["elapsed_s"] > 0, f"{record_id} return and cost")
            elapsed_sum += record["elapsed_s"]
        except Exception as exc:
            failures.append(f"{record_id} verifier exception: {exc!r}")
        per_record.append({"record_id": record_id, "pass": len(failures) == local_failures_before})

    require(observed_runs == protocol["expected_run_count"] == report["run_count"] == 198, "total run count")
    require(len(observed_unique) == report["unique_output_sequences"], "global unique count")
    require(math.isclose(elapsed_sum, report["total_generation_elapsed_s"], abs_tol=1e-9), "generation cost sum")
    require(math.isclose(max_efe_delta, report["max_efe_abs_delta_from_rounded_official"], abs_tol=1e-12), "reported max EFE delta")
    require(report["official_process_count"] == 18, "official process count")
    require(report["official_generator_run_count"] == 198, "official generator run count")
    require(report["lineardesign_initialization_call_count"] == 198, "LinearDesign initialization count")
    require(report["linearpartition_scoring_call_count"] == 198, "LinearPartition scoring count")
    require(report["dense_budget_step_auc_v2"] is None, "dense AUC remains null")
    require(report["time_matched_comparison"] is False, "time-matched remains false")
    require(report["scientific_gate_passed"] is False and report["sota_claim"] is False, "scientific and SOTA gates")
    require(report["main_baseline_comparison"] is False and report["matched_lineardesign_comparison"] is False, "comparison not prematurely claimed")

    audit = {
        "schema": "a8-rk13-ensembledesign-unique18-independent-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "protocol_sha256": sha256(args.protocol),
        "report": str(args.report),
        "report_sha256": sha256(args.report),
        "record_count": len(report["records"]),
        "run_count": observed_runs,
        "unique_output_sequences": len(observed_unique),
        "total_generation_elapsed_s": elapsed_sum,
        "max_efe_abs_delta_from_rounded_official": max_efe_delta,
        "per_record": per_record,
        "failures": failures,
        "dense_budget_step_auc_v2": None,
        "time_matched_comparison": False,
        "scientific_gate_passed": False,
        "sota_claim": False,
    }
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({k: audit[k] for k in ["status", "record_count", "run_count", "unique_output_sequences", "total_generation_elapsed_s", "max_efe_abs_delta_from_rounded_official", "failures"]}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
