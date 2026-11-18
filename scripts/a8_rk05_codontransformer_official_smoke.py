#!/usr/bin/env python3
"""Bounded official CodonTransformer inference with retained default outputs."""
import argparse
import hashlib
import json
import os
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASES = "TCAG"
AMINO_ACIDS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODONS = [a + b + c for a in BASES for b in BASES for c in BASES]
CODON_TABLE = dict(zip(CODONS, AMINO_ACIDS))
BENCHMARK_SHA256 = "30e3dbbfc3480287b1f87177fe476d7ca283219f08949476da6d08555d0ab4e0"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temporary, path)


def translate(dna):
    dna = dna.upper()
    if len(dna) % 3:
        raise ValueError("DNA length is not divisible by three")
    try:
        return "".join(CODON_TABLE[dna[i:i + 3]] for i in range(0, len(dna), 3))
    except KeyError as error:
        raise ValueError(f"invalid DNA codon: {error}") from error


def read_fasta_record(path, record_id):
    records = {}
    current = None
    for line in Path(path).read_text().splitlines():
        if line.startswith(">"):
            current = line[1:].split()[0]
            if current in records:
                raise ValueError(f"duplicate FASTA record: {current}")
            records[current] = []
        elif current is not None:
            records[current].append(line.strip())
    if record_id not in records:
        raise ValueError(f"missing FASTA record: {record_id}")
    return "".join(records[record_id]).upper()


def protein_from_cds(cds):
    translated = translate(cds)
    if not translated.endswith("*") or "*" in translated[:-1]:
        raise ValueError("CDS must have one terminal stop and no internal stop")
    return translated[:-1]


def readme_example(source_dir):
    text = (Path(source_dir) / "README.md").read_text()
    protein = re.search(r'^protein = "([A-Z]+)"', text, re.MULTILINE).group(1)
    organism = re.search(r'^organism = "([^"]+)"', text, re.MULTILINE).group(1)
    match = re.search(r"\|\s+Predicted DNA\s+\|\s*\n-+\n([ACGT]+)", text)
    if not match:
        raise ValueError("README predicted DNA not found")
    return protein, organism, match.group(1)


def design_qc(dna, protein):
    dna = dna.upper()
    alphabet_valid = bool(dna) and set(dna) <= set("ACGT")
    length_valid = len(dna) == 3 * (len(protein) + 1)
    translated = translate(dna) if alphabet_valid and len(dna) % 3 == 0 else ""
    terminal_stop = translated.endswith("*")
    internal_stop = "*" in translated[:-1]
    observed = translated[:-1] if terminal_stop else translated.rstrip("*")
    return {
        "alphabet_valid": alphabet_valid,
        "length_valid": length_valid,
        "terminal_stop": terminal_stop,
        "internal_stop": internal_stop,
        "translation_exact": observed == protein,
        "legal_synonymous_cds": all((alphabet_valid, length_valid, terminal_stop,
                                      not internal_stop, observed == protein)),
        "translated_protein": observed,
        "dna_nt": len(dna),
        "protein_aa": len(protein),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--record-id", default="C01H6.8b.1")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise RuntimeError("output directory must be new or empty")
    if args.report.exists():
        raise RuntimeError(f"refusing to overwrite {args.report}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if sha256(args.benchmark) != BENCHMARK_SHA256:
        raise ValueError("benchmark SHA256 mismatch")
    materialization = json.loads(args.materialization.read_text())
    if materialization["status"] != "COMPLETE":
        raise ValueError("materialization incomplete")
    for relative, expected in materialization["source"]["key_file_sha256"].items():
        if sha256(args.source_dir / relative) != expected:
            raise ValueError(f"source hash mismatch: {relative}")
    for item in materialization["model"]["files"]:
        if sha256(args.model_dir / item["name"]) != item["sha256"]:
            raise ValueError(f"model hash mismatch: {item['name']}")

    sys.path.insert(0, str(args.source_dir))
    import torch
    import transformers
    from transformers import AutoTokenizer, BigBirdForMaskedLM
    from CodonTransformer.CodonPrediction import predict_dna_sequence

    example_protein, organism, expected_example_dna = readme_example(args.source_dir)
    benchmark_cds = read_fasta_record(args.benchmark, args.record_id)
    benchmark_protein = protein_from_cds(benchmark_cds)
    device = torch.device(args.device if args.device != "cuda" or torch.cuda.is_available() else "cpu")
    load_started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)
    model = BigBirdForMaskedLM.from_pretrained(str(args.model_dir), local_files_only=True).to(device)
    model.eval()
    model_load_seconds = time.perf_counter() - load_started

    jobs = [
        ("official_example", example_protein, False),
        ("official_example", example_protein, True),
        (args.record_id, benchmark_protein, False),
        (args.record_id, benchmark_protein, True),
    ]
    runs = []
    for record_id, protein, match_protein in jobs:
        mode = "match_protein" if match_protein else "official_default"
        started = time.perf_counter()
        output = predict_dna_sequence(
            protein=protein,
            organism=organism,
            device=device,
            tokenizer=tokenizer,
            model=model,
            attention_type="original_full",
            deterministic=True,
            match_protein=match_protein,
        )
        elapsed = time.perf_counter() - started
        dna = output.predicted_dna.upper()
        run = {
            "record_id": record_id,
            "mode": mode,
            "protein": protein,
            "organism": organism,
            "attention_type": "original_full",
            "deterministic": True,
            "temperature": 0.2,
            "top_p": 0.95,
            "num_sequences": 1,
            "match_protein": match_protein,
            "predicted_dna": dna,
            "processed_input": output.processed_input,
            "inference_seconds": elapsed,
            "qc": design_qc(dna, protein),
        }
        if record_id == "official_example" and not match_protein:
            run["readme_predicted_dna"] = expected_example_dna
            run["readme_exact_match"] = dna == expected_example_dna
        raw_path = args.output_dir / f"{record_id}_{mode}.json"
        atomic_json(raw_path, run)
        run["raw_output"] = str(raw_path)
        run["raw_output_sha256"] = sha256(raw_path)
        runs.append(run)
        print(json.dumps({"record": record_id, "mode": mode, "seconds": elapsed,
                          "legal": run["qc"]["legal_synonymous_cds"],
                          "dna_sha256": hashlib.sha256(dna.encode()).hexdigest()}), flush=True)

    fasta = "".join(f">{r['record_id']}|{r['mode']}\n{r['predicted_dna']}\n" for r in runs)
    (args.output_dir / "outputs.fasta").write_text(fasta)
    example_default = runs[0]
    constrained = [r for r in runs if r["match_protein"]]
    defaults = [r for r in runs if not r["match_protein"]]
    example_pass = example_default["readme_exact_match"] and example_default["qc"]["legal_synonymous_cds"]
    constrained_pass = all(r["qc"]["legal_synonymous_cds"] for r in constrained)
    status = "BOUNDED_OFFICIAL_EXECUTION_COMPLETE" if example_pass and constrained_pass else "FAILED"
    report = {
        "schema_version": "a8-rk05-codontransformer-official-smoke-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source_commit": materialization["source"]["commit"],
        "model_commit": materialization["model"]["commit"],
        "materialization": str(args.materialization),
        "materialization_sha256": sha256(args.materialization),
        "benchmark": str(args.benchmark),
        "benchmark_sha256": sha256(args.benchmark),
        "benchmark_record": args.record_id,
        "benchmark_cds_sha256": hashlib.sha256(benchmark_cds.encode()).hexdigest(),
        "benchmark_protein": benchmark_protein,
        "organism": organism,
        "device": str(device),
        "gpu_name": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "model_parameter_count": sum(p.numel() for p in model.parameters()),
        "model_load_seconds": model_load_seconds,
        "total_inference_seconds": sum(r["inference_seconds"] for r in runs),
        "official_example_pass": example_pass,
        "official_example_readme_exact_match": example_default["readme_exact_match"],
        "constrained_all_legal": constrained_pass,
        "constrained_legal_count": sum(r["qc"]["legal_synonymous_cds"] for r in constrained),
        "constrained_run_count": len(constrained),
        "default_legal_count": sum(r["qc"]["legal_synonymous_cds"] for r in defaults),
        "default_run_count": len(defaults),
        "unique_sequence_count": len({r["predicted_dna"] for r in runs}),
        "runs": runs,
        "outputs_fasta": str(args.output_dir / "outputs.fasta"),
        "outputs_fasta_sha256": sha256(args.output_dir / "outputs.fasta"),
        "main_baseline_comparison": False,
        "dense_budget_complete": False,
        "matched_lineardesign_or_ensembledesign_comparison": False,
        "functional_ood": False,
        "sota_claim": False,
        "scope": "Official README example plus one C01 record, deterministic default and match_protein modes only; not a main benchmark, dense budget, functional OOD, or SOTA result.",
    }
    atomic_json(args.report, report)
    print(json.dumps({"status": status, "report": str(args.report),
                      "example_exact": example_default["readme_exact_match"],
                      "constrained_legal": f"{report['constrained_legal_count']}/{len(constrained)}",
                      "default_legal": f"{report['default_legal_count']}/{len(defaults)}"}), flush=True)
    if status != "BOUNDED_OFFICIAL_EXECUTION_COMPLETE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
