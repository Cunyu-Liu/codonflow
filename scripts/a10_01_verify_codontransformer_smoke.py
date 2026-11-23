#!/usr/bin/env python3
"""Independently verify a CodonTransformer execution-smoke report."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

EXPECTED_MODEL_REVISION = "9744dcc920d813066391fc828d7a590207f148e8"
EXPECTED_SOURCE_REVISION = "4a447b01dab860feb81b647ff1ff88ad598517f4"
EXPECTED_SCOPE = "execution_smoke_only_no_scientific_or_performance_claim"
EXPECTED_RUN_COUNTS = {"deterministic": 1, "stochastic_seed0": 2}
PROTEIN_LENGTH = 110
DNA_LENGTH = 333
STOP_CODONS = {"TAA", "TAG", "TGA"}
AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}
COST_METADATA = {"monetary_usd", "monetary_cost_status"}


def translate_dna(dna: str) -> str:
    return "".join(CODON_TABLE[dna[index:index + 3]] for index in range(0, len(dna), 3))


def _cost_checks(cost: Any) -> tuple[bool, bool]:
    if not isinstance(cost, dict):
        return False, False
    metadata_ok = (
        "monetary_usd" in cost
        and cost["monetary_usd"] is None
        and cost.get("monetary_cost_status") == "not_measured"
    )
    measurements = [(key, value) for key, value in cost.items() if key not in COST_METADATA]
    measurements_ok = bool(measurements)
    for _, value in measurements:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            measurements_ok = False
        elif not math.isfinite(value) or value < 0:
            measurements_ok = False
    keys = [key.lower() for key, _ in measurements]
    has_time = any(any(token in key for token in ("time", "duration", "latency", "elapsed", "wall", "second")) for key in keys)
    has_memory = any(any(token in key for token in ("memory", "vram")) for key in keys)
    return metadata_ok, measurements_ok and has_time and has_memory


def verify_report(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {"checks": {"input_object": False}, "passed": False}

    input_data = report.get("input")
    runs = report.get("runs")
    model = report.get("model")
    commit = report.get("commit")
    environment = report.get("environment")

    protein = input_data.get("protein") if isinstance(input_data, dict) else None
    protein_ok = isinstance(protein, str) and len(protein) == PROTEIN_LENGTH and set(protein) <= AMINO_ACIDS

    runs_ok = (
        isinstance(runs, list)
        and len(runs) == len(EXPECTED_RUN_COUNTS)
        and all(isinstance(run, dict) and isinstance(run.get("name"), str) for run in runs)
    )
    runs_by_name = {run.get("name"): run for run in runs} if runs_ok else {}
    runs_ok = runs_ok and set(runs_by_name) == set(EXPECTED_RUN_COUNTS)

    run_counts = {}
    nested_outputs = []
    stochastic_seed_ok = False
    for name, expected_count in EXPECTED_RUN_COUNTS.items():
        run = runs_by_name.get(name, {})
        configuration = run.get("configuration")
        outputs = run.get("outputs")
        configuration_ok = isinstance(configuration, dict)
        declared_count = configuration.get("num_sequences") if configuration_ok else None
        declared_count_ok = configuration_ok and (
            (name == "deterministic" and "num_sequences" not in configuration)
            or (type(declared_count) is int and declared_count == expected_count)
        )
        outputs_ok = isinstance(outputs, list)
        run_counts[name] = (
            runs_ok
            and declared_count_ok
            and outputs_ok
            and len(outputs) == expected_count
        )
        if outputs_ok:
            nested_outputs.extend(outputs)
        if name == "stochastic_seed0":
            seed = configuration.get("seed") if configuration_ok else None
            stochastic_seed_ok = type(seed) is int and seed == 0

    dna_ok = True
    stop_ok = True
    translation_ok = True
    reported_translation_ok = True
    for output in nested_outputs:
        if not isinstance(output, dict):
            dna_ok = stop_ok = translation_ok = reported_translation_ok = False
            continue
        dna = output.get("dna")
        current_dna_ok = isinstance(dna, str) and len(dna) == DNA_LENGTH and set(dna) <= set("ACGT")
        dna_ok = dna_ok and current_dna_ok
        if not current_dna_ok:
            stop_ok = translation_ok = reported_translation_ok = False
            continue
        stop_ok = stop_ok and dna[-3:] in STOP_CODONS
        translation_ok = translation_ok and translate_dna(dna) == f"{protein}*"
        reported_translation_ok = reported_translation_ok and output.get("translated_protein") == protein

    all_run_counts_ok = all(run_counts.values()) and len(nested_outputs) == 3
    gpu = environment.get("gpu") if isinstance(environment, dict) else None
    gpu_name = gpu.get("name") if isinstance(gpu, dict) else None
    normalized_gpu_name = "".join(character for character in gpu_name.lower() if character.isalnum()) if isinstance(gpu_name, str) else ""
    cost_metadata_ok, cost_measurements_ok = _cost_checks(report.get("cost"))
    checks = {
        "schema.no_top_level_outputs": "outputs" not in report,
        "runs.schema": runs_ok,
        "runs.deterministic_one": run_counts["deterministic"],
        "runs.stochastic_seed0_two": run_counts["stochastic_seed0"] and stochastic_seed_ok,
        "outputs.dna_333nt": all_run_counts_ok and dna_ok,
        "outputs.terminal_stop": all_run_counts_ok and stop_ok,
        "outputs.independent_translation": protein_ok and all_run_counts_ok and translation_ok,
        "outputs.translated_protein": protein_ok and all_run_counts_ok and reported_translation_ok,
        "model.revision": isinstance(model, dict) and model.get("revision") == EXPECTED_MODEL_REVISION,
        "commit.codontransformer": isinstance(commit, dict) and commit.get("codontransformer") == EXPECTED_SOURCE_REVISION,
        "environment.cuda_0": isinstance(environment, dict) and environment.get("device") == "cuda:0",
        "environment.rtx5090": "rtx5090" in normalized_gpu_name,
        "environment.cpu_fallback_false": isinstance(environment, dict) and environment.get("cpu_fallback") is False,
        "cost.monetary_metadata": cost_metadata_ok,
        "cost.nonnegative_time_and_memory": cost_measurements_ok,
        "scope.execution_smoke_only": report.get("scope") == EXPECTED_SCOPE,
    }
    return {"checks": checks, "passed": all(checks.values())}


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        with args.report_json.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"Cannot read smoke report: {error}", file=sys.stderr)
        result = {"checks": {"input_json": False}, "passed": False}
    else:
        result = verify_report(report)

    try:
        _write_new_json(args.output, result)
    except FileExistsError:
        print(f"Refusing to overwrite existing output: {args.output}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"Cannot write verification output: {error}", file=sys.stderr)
        return 2
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
