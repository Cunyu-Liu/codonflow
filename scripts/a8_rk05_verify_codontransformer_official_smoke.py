#!/usr/bin/env python3
"""Independent raw-output, translation, hash and deterministic re-execution audit."""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASES = "TCAG"
AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
TABLE = dict(zip([a + b + c for a in BASES for b in BASES for c in BASES], AAS))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def tr(dna):
    if len(dna) % 3:
        return None
    try:
        return "".join(TABLE[dna[i:i + 3]] for i in range(0, len(dna), 3))
    except KeyError:
        return None


def legal(dna, protein):
    translated = tr(dna) if set(dna) <= set("ACGT") else None
    return bool(translated and len(dna) == 3 * (len(protein) + 1)
                and translated.endswith("*") and "*" not in translated[:-1]
                and translated[:-1] == protein)


def fasta_record(path, wanted):
    found = {}
    key = None
    for line in Path(path).read_text().splitlines():
        if line.startswith(">"):
            key = line[1:].split()[0]
            assert key not in found
            found[key] = []
        elif key:
            found[key].append(line.strip())
    return "".join(found[wanted]).upper()


def read_example(source):
    text = (Path(source) / "README.md").read_text()
    protein = re.search(r'^protein = "([A-Z]+)"', text, re.MULTILINE).group(1)
    organism = re.search(r'^organism = "([^"]+)"', text, re.MULTILINE).group(1)
    expected = re.search(r"\|\s+Predicted DNA\s+\|\s*\n-+\n([ACGT]+)", text).group(1)
    return protein, organism, expected


def write_json(path, value):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source-dir", type=Path, required=True)
    p.add_argument("--model-dir", type=Path, required=True)
    p.add_argument("--materialization", type=Path, required=True)
    p.add_argument("--benchmark", type=Path, required=True)
    p.add_argument("--record-id", default="C01H6.8b.1")
    p.add_argument("--production-report", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--device", default="cuda")
    args = p.parse_args()
    production = json.loads(args.production_report.read_text())
    materialization = json.loads(args.materialization.read_text())
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    source_hash_details = []
    for relative, expected in materialization["source"]["key_file_sha256"].items():
        observed = sha(args.source_dir / relative)
        source_hash_details.append({"file": relative, "match": observed == expected})
    model_hash_details = []
    for item in materialization["model"]["files"]:
        observed = sha(args.model_dir / item["name"])
        model_hash_details.append({"file": item["name"], "match": observed == item["sha256"]})
    identity = (production["source_commit"] == "4a447b01dab860feb81b647ff1ff88ad598517f4"
                and production["model_commit"] == "9744dcc920d813066391fc828d7a590207f148e8"
                and production["materialization_sha256"] == sha(args.materialization)
                and all(x["match"] for x in source_hash_details + model_hash_details))
    check("fixed_source_model_identity_and_hashes", identity,
          {"source": source_hash_details, "model": model_hash_details})

    cds = fasta_record(args.benchmark, args.record_id)
    translated = tr(cds)
    protein = translated[:-1]
    benchmark_ok = (sha(args.benchmark) == production["benchmark_sha256"]
                    == "30e3dbbfc3480287b1f87177fe476d7ca283219f08949476da6d08555d0ab4e0"
                    and translated.endswith("*") and "*" not in translated[:-1]
                    and protein == production["benchmark_protein"]
                    and hashlib.sha256(cds.encode()).hexdigest() == production["benchmark_cds_sha256"])
    check("benchmark_identity_and_translation", benchmark_ok,
          {"record": args.record_id, "protein_aa": len(protein), "cds_nt": len(cds)})

    raw_runs = []
    raw_identity = True
    for run in production["runs"]:
        path = Path(run["raw_output"])
        raw = json.loads(path.read_text())
        raw_runs.append(raw)
        raw_identity &= sha(path) == run["raw_output_sha256"]
        for key in ("record_id", "mode", "protein", "organism", "match_protein", "predicted_dna"):
            raw_identity &= raw[key] == run[key]
    expected_keys = {("official_example", False), ("official_example", True),
                     (args.record_id, False), (args.record_id, True)}
    observed_keys = {(r["record_id"], r["match_protein"]) for r in raw_runs}
    raw_identity &= len(raw_runs) == 4 and observed_keys == expected_keys
    check("four_raw_outputs_and_report_identity", raw_identity, {"runs": len(raw_runs)})

    qc_details = []
    for raw in raw_runs:
        translated_run = tr(raw["predicted_dna"])
        independent_legal = legal(raw["predicted_dna"], raw["protein"])
        qc_details.append({"record": raw["record_id"], "mode": raw["mode"],
                           "legal": independent_legal,
                           "translation": translated_run,
                           "reported_legal": raw["qc"]["legal_synonymous_cds"]})
    check("independent_translation_and_raw_qc",
          all(x["legal"] == x["reported_legal"] for x in qc_details), qc_details)

    example_protein, organism, expected_example = read_example(args.source_dir)
    example = next(r for r in raw_runs if r["record_id"] == "official_example" and not r["match_protein"])
    example_ok = (example["protein"] == example_protein and example["organism"] == organism
                  and example["predicted_dna"] == expected_example
                  and production["official_example_readme_exact_match"] is True)
    check("official_readme_example_exact", example_ok,
          {"expected_sha256": hashlib.sha256(expected_example.encode()).hexdigest(),
           "observed_sha256": hashlib.sha256(example["predicted_dna"].encode()).hexdigest()})

    constrained = [r for r in raw_runs if r["match_protein"]]
    defaults = [r for r in raw_runs if not r["match_protein"]]
    constrained_count = sum(legal(r["predicted_dna"], r["protein"]) for r in constrained)
    default_count = sum(legal(r["predicted_dna"], r["protein"]) for r in defaults)
    check("match_protein_runs_all_legal",
          len(constrained) == 2 and constrained_count == 2
          and production["constrained_legal_count"] == 2
          and production["constrained_run_count"] == 2,
          {"legal": constrained_count, "total": len(constrained)})
    check("default_behavior_retained_not_overwritten",
          len(defaults) == 2 and production["default_legal_count"] == default_count
          and production["default_run_count"] == 2,
          {"legal": default_count, "total": len(defaults)})

    fasta_path = Path(production["outputs_fasta"])
    fasta_sequences = {}
    key = None
    for line in fasta_path.read_text().splitlines():
        if line.startswith(">"):
            key = line[1:]
            fasta_sequences[key] = []
        elif key:
            fasta_sequences[key].append(line.strip())
    fasta_ok = sha(fasta_path) == production["outputs_fasta_sha256"]
    for raw in raw_runs:
        key = f"{raw['record_id']}|{raw['mode']}"
        fasta_ok &= "".join(fasta_sequences.get(key, [])) == raw["predicted_dna"]
    check("fasta_sequence_identity", fasta_ok, {"records": len(fasta_sequences)})

    inference_sum = sum(r["inference_seconds"] for r in production["runs"])
    cost_ok = (abs(inference_sum - production["total_inference_seconds"]) < 1e-9
               and production["model_load_seconds"] >= 0
               and all(r["inference_seconds"] >= 0 for r in production["runs"]))
    check("aggregate_cost_reconciliation", cost_ok,
          {"recomputed_inference_seconds": inference_sum,
           "model_load_seconds": production["model_load_seconds"]})

    sys.path.insert(0, str(args.source_dir))
    import torch
    import transformers
    from transformers import AutoTokenizer, BigBirdForMaskedLM
    from CodonTransformer.CodonPrediction import predict_dna_sequence
    device = torch.device(args.device if args.device != "cuda" or torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)
    model = BigBirdForMaskedLM.from_pretrained(str(args.model_dir), local_files_only=True).to(device)
    model.eval()
    reexecution = []
    exact = True
    for raw in raw_runs:
        started = time.perf_counter()
        output = predict_dna_sequence(
            protein=raw["protein"], organism=raw["organism"], device=device,
            tokenizer=tokenizer, model=model, attention_type="original_full",
            deterministic=True, match_protein=raw["match_protein"])
        elapsed = time.perf_counter() - started
        match = output.predicted_dna.upper() == raw["predicted_dna"]
        exact &= match
        reexecution.append({"record": raw["record_id"], "mode": raw["mode"],
                            "exact": match, "seconds": elapsed,
                            "dna_sha256": hashlib.sha256(output.predicted_dna.upper().encode()).hexdigest()})
    check("independent_deterministic_reexecution_exact", exact, reexecution)

    environment_ok = (production["transformers"] == transformers.__version__ == "4.40.2"
                      and production["model_parameter_count"] == sum(x.numel() for x in model.parameters())
                      and str(device) == production["device"])
    check("environment_and_model_parameter_reconciliation", environment_ok,
          {"torch": torch.__version__, "transformers": transformers.__version__,
           "parameters": sum(x.numel() for x in model.parameters())})

    scope_names = ["main_baseline_comparison", "dense_budget_complete",
                   "matched_lineardesign_or_ensembledesign_comparison", "functional_ood", "sota_claim"]
    check("scientific_scope_flags", all(production[x] is False for x in scope_names),
          {x: production[x] for x in scope_names})
    check("production_status_reconciled",
          production["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE"
          and production["official_example_pass"] is True
          and production["constrained_all_legal"] is True,
          production["status"])

    passed = sum(x["pass"] for x in checks)
    report = {
        "schema_version": "a8-rk05-codontransformer-independent-verification-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed == len(checks) else "FAIL",
        "check_count": len(checks), "passed_checks": passed, "checks": checks,
        "production_report": str(args.production_report),
        "production_report_sha256": sha(args.production_report),
        "max_numeric_delta": 0.0,
        "default_legal_count": default_count, "default_run_count": len(defaults),
        "constrained_legal_count": constrained_count, "constrained_run_count": len(constrained),
        "main_baseline_comparison": False, "functional_ood": False, "sota_claim": False,
    }
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}",
                      "output": str(args.output)}))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
