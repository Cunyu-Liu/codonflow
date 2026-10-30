"""Run auditable A6 baseline arms without CodonFlow or legacy HV verdicts.

Output is one JSON per gene and seed. Every method retains its actual compact
solution set; invalid identity and unavailable cost fields are never hidden.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import feasible_edit, protein_of_cds, translate
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import cai, cai_weights_from_rscu, pairwise_ned
from codonflow.eval.mfe_parallel import mfe_batch_parallel
from codonflow.core.motifs import motif_penalty_score
from codonflow.models.guided_sampler import synonymous_x0
from codonflow.train.run_pretrain import file_sha256, git_commit
from scripts.gemorna_arm import normalized_identity_pass, run_generate
from scripts.run_exp5_ood import cai_greedy, lineardesign_scan

METHODS = ("lineardesign_scan", "codongpt", "gemorna", "cai_greedy", "uniform_synonymous")


def generate_method(method, source, weights, n, seed, device, gpt=None):
    """Return raw solutions and generation costs before objective scoring."""
    protein = protein_of_cds(source)
    if method == "cai_greedy":
        start = time.perf_counter()
        return [cai_greedy(source, weights)], {
            "elapsed_s": time.perf_counter() - start, "forward_calls": 0,
            "generator_calls": 1, "n_requested": 1,
        }
    if method == "uniform_synonymous":
        start = time.perf_counter()
        solutions = [synonymous_x0(source, np.random.default_rng(seed * 1009 + i)) for i in range(n)]
        return solutions, {"elapsed_s": time.perf_counter() - start, "forward_calls": 0,
                           "generator_calls": n, "n_requested": n}
    if method == "lineardesign_scan":
        start = time.perf_counter()
        solutions = lineardesign_scan(protein, n, {}, None, np.random.default_rng(seed))
        if len(solutions) != 7:
            raise RuntimeError(f"LinearDesign returned {len(solutions)}/7 DP calls; inspect errors")
        return solutions, {"elapsed_s": time.perf_counter() - start, "forward_calls": None,
                           "forward_note": "not exposed by official DP binary",
                           "generator_calls": 7, "n_requested": 7}
    if method == "gemorna":
        start = time.perf_counter()
        solutions = []
        for _ in range(n):
            sequence, _ = run_generate(protein)
            if sequence is not None:
                solutions.append(sequence)
        return solutions, {"elapsed_s": time.perf_counter() - start, "forward_calls": None,
                           "forward_note": "not exposed by official GEMORNA generator",
                           "generator_calls": n, "n_requested": n,
                           "sampling_note": "official generator has no seed parameter"}
    if method == "codongpt":
        if gpt is None:
            raise ValueError("codonGPT model was not loaded")
        if len(protein) + 1 > 1024:
            return [], {"status": "architectural_exclusion",
                        "reason": f"codonGPT context 1024 < {len(protein) + 1} codons",
                        "forward_calls": 0, "generator_calls": 0, "n_requested": 0}
        model, tokenizer = gpt
        start = time.perf_counter()
        solutions = []
        bos = tokenizer.convert_tokens_to_ids(["[BOS]"])[0]
        torch.manual_seed(seed)
        from codonflow.core.codon import SYNONYMOUS_CODONS
        with torch.no_grad():
            for _ in range(n):
                ids = torch.tensor([[bos]], device=device)
                codons = []
                for aa in protein + "*":
                    alternatives = SYNONYMOUS_CODONS.get(aa, ("TAA",))
                    option_ids = tokenizer.convert_tokens_to_ids(list(alternatives))
                    logits = model(input_ids=ids).logits[0, -1].float()
                    mask = torch.full_like(logits, -torch.inf)
                    mask[option_ids] = 0.0
                    next_id = torch.multinomial(torch.softmax(logits + mask, dim=-1), 1).item()
                    codons.append(tokenizer.convert_ids_to_tokens(next_id))
                    ids = torch.cat([ids, torch.tensor([[next_id]], device=device)], dim=1)
                solutions.append("".join(c for c in codons if not c.startswith("[")))
        return solutions, {"elapsed_s": time.perf_counter() - start,
                           "forward_calls": n * (len(protein) + 1),
                           "generator_calls": n, "n_requested": n}
    raise ValueError(f"unknown method {method}")


def score_method(method, raw_solutions, source, weights, generation, gc_target=0.55):
    valid, seen = [], set()
    n_invalid = 0
    for sequence in raw_solutions:
        sequence = normalized_identity_pass(sequence, protein_of_cds(source))
        if sequence is None:
            n_invalid += 1
            continue
        if not translate(sequence).endswith("*"):
            sequence += "TAA"
        if sequence in seen:
            continue
        seen.add(sequence)
        valid.append(sequence)
    mfes = mfe_batch_parallel(valid) if valid else []
    if not valid:
        raise ValueError(f"{method}: no valid unique synonymous solutions")
    objectives = [[cai(sequence, weights), -mfe,
                   -abs((sequence.count("G") + sequence.count("C")) / len(sequence) - gc_target),
                   -motif_penalty_score(sequence)]
                  for sequence, mfe in zip(valid, mfes)]
    if not np.isfinite(objectives).all():
        raise ValueError(f"{method}: non-finite objective")
    return {
        "method": method, "status": generation.get("status", "done"),
        "solutions": valid, "obj_vectors": objectives,
        "n_solutions": len(valid), "n_unique": len(seen),
        "n_invalid_identity": n_invalid,
        "identity_rate": float(np.mean([feasible_edit(s, source) for s in valid])) if valid else None,
        "ned": pairwise_ned(valid),
        "unique_terminal_reward_calls": len(valid),
        "terminal_reward_evaluations": len(valid),
        **generation,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    parser.add_argument("--n-solutions", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--atc-yaml", default="/home/codonflow/configs/atc_norm.yaml",
                        help="single source of truth for the GC target; fallback 0.55 only if the file is absent")
    parser.add_argument("--record-id", default=None)
    parser.add_argument("--resume", action="store_true",
                        help="reuse only completed methods from the matching output file")
    args = parser.parse_args()
    if args.n_solutions < 1 or not args.methods:
        raise ValueError("positive n-solutions and at least one method required")
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    if "codongpt" in args.methods and device.type != "cuda":
        raise RuntimeError("codonGPT requires CUDA; silent CPU fallback forbidden")
    records = [(h.split()[0], s) for h, s in read_fasta(args.benchmark_fasta)]
    if args.record_id is not None:
        records = [row for row in records if row[0] == args.record_id]
        if len(records) != 1:
            raise ValueError("record-id must match exactly one benchmark sequence")
    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    gc_target = 0.55
    if args.atc_yaml and Path(args.atc_yaml).exists():
        from codonflow.gating.atc import ATCUtility
        gc_target = float(ATCUtility.from_yaml(args.atc_yaml).gc_target)
    print(json.dumps({"gc_target": gc_target, "atc_yaml": args.atc_yaml}), flush=True)
    gpt = None
    if "codongpt" in args.methods:
        from scripts.run_exp5_ood import load_codongpt
        gpt = load_codongpt(device)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for header, source in records:
        path = out_dir / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', header)}_s{args.seed}.json"
        output = {
            "protocol": "a6_baselines_v1", "record_id": header, "seed": args.seed,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "benchmark_fasta": str(Path(args.benchmark_fasta).resolve()),
            "benchmark_sha256": file_sha256(args.benchmark_fasta),
            "rscu_sha256": file_sha256(args.rscu_json), "code_commit": git_commit(),
            "gc_target": gc_target, "atc_yaml": str(args.atc_yaml),
            "methods": {},
        }
        if args.resume and path.exists():
            previous = json.loads(path.read_text())
            if (previous.get("protocol") != output["protocol"]
                    or previous.get("source_sha256") != output["source_sha256"]
                    or previous.get("benchmark_sha256") != output["benchmark_sha256"]):
                raise ValueError(f"refusing to resume mismatched baseline artifact: {path}")
            output = previous

        def save():
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(output, indent=2))
            temporary.replace(path)

        output["status"] = "running"
        for method in args.methods:
            if output["methods"].get(method, {}).get("status") in ("done", "architectural_exclusion"):
                continue
            try:
                raw, generation = generate_method(
                    method, source, weights, args.n_solutions, args.seed, device, gpt,
                )
                if generation.get("status") == "architectural_exclusion":
                    output["methods"][method] = {"method": method, **generation,
                                                 "solutions": [], "obj_vectors": []}
                else:
                    output["methods"][method] = score_method(method, raw, source, weights, generation, gc_target)
                output["methods"][method]["code_commit"] = git_commit()
            except Exception as error:
                output["methods"][method] = {"method": method, "status": "failed",
                                             "error": str(error), "code_commit": git_commit()}
                output["status"] = "failed"
                save()
                raise
            print(json.dumps({"record": header, "seed": args.seed, "method": method,
                              "status": output["methods"][method]["status"],
                              "n": output["methods"][method].get("n_solutions")}), flush=True)
            save()
        output["status"] = "done"
        save()


if __name__ == "__main__":
    main()
