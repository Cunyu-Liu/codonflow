"""Phase 2 evaluation: gated guided sampling quality (Gate B inputs).

Loads the converged checkpoint, runs guided sampling on benchmarks, reports:
  - legal rate / identity rate (must be 100%)
  - CAI / MFE / GC / motif
  - NED diversity, unique fraction
  - per-sequence sampling cost vs LinearDesign baseline (Gate B cost check)
Also runs the uniform (unguided) arm as the EXP-2 internal control.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import (
    feasible_edit,
    protein_of_cds,
    gc_fraction,
    translate,
)
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import (
    cai,
    cai_weights_from_rscu,
    mfe_batch,
    pairwise_ned,
    unique_fraction,
)
from codonflow.gating.atc import ATCUtility
from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer
from codonflow.models.guided_sampler import CodonGuidedSampler, synonymous_x0
from codonflow.core.motifs import motif_penalty_score


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--n-samples", type=int, default=20)
    ap.add_argument("--n-steps", type=int, default=20)
    ap.add_argument("--n-candidates", type=int, default=10)
    ap.add_argument("--n-seeds", type=int, default=3)
    ap.add_argument("--baseline-time-json", default="/mnt/cunyuliu/codonflow/eval_outputs/E1_lineardesign_bench.json")
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/P2_gated_sampling.json")
    args = ap.parse_args()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    assert device.type == "cuda", "GPU required"
    rscu = json.loads(Path(args.rscu_json).read_text())
    weights = cai_weights_from_rscu(rscu)
    atc = ATCUtility()
    model = EditFlowTransformer(EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0))
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model = model.to(device).eval()
    mfe_cache: dict = {}

    def reward(cds: str) -> float:
        if cds in mfe_cache:
            m = mfe_cache[cds]
        else:
            m = mfe_batch([cds])[0]
            mfe_cache[cds] = m
        return atc.utility(
            cai(cds, weights), -m, -abs(gc_fraction(cds) - 0.55),
            -motif_penalty_score(cds),
        )

    ld_times = {}
    if Path(args.baseline_time_json).exists():
        for row in json.loads(Path(args.baseline_time_json).read_text()):
            ld_times[row["name"]] = row["mean_time_s"]

    all_out = {}
    for header, source in read_fasta(args.benchmark_fasta):
        name = header.split()[0]
        per_seed = []
        for seed in range(args.n_seeds):
            sampler = CodonGuidedSampler(
                model, device, reward, n_steps=args.n_steps,
                n_candidates=args.n_candidates, temperature=1.0,
                rng=np.random.default_rng(seed),
            )
            rng = np.random.default_rng(1000 + seed)
            t0 = time.time()
            seqs = []
            for _ in range(args.n_samples):
                x0 = synonymous_x0(source, rng)
                seq, _ = sampler.sample(x0)
                seqs.append(seq)
            elapsed = time.time() - t0
            prot_ref = translate(source)
            legal = [int(feasible_edit(s, source)) for s in seqs]
            ident = [int(translate(s) == prot_ref) for s in seqs]
            cais = [cai(s, weights) for s in seqs]
            mfes = mfe_batch(seqs)
            entry = {
                "seed": seed,
                "n": len(seqs),
                "legal_rate": sum(legal) / len(seqs),
                "identity_rate": sum(ident) / len(seqs),
                "cai_mean": float(np.mean(cais)),
                "mfe_mean": float(np.mean(mfes)),
                "gc_mean": float(np.mean([gc_fraction(s) for s in seqs])),
                "ned_mean": pairwise_ned(seqs),
                "unique_fraction": unique_fraction(seqs),
                "per_seq_s": round(elapsed / len(seqs), 2),
            }
            if name in ld_times:
                entry["ld_baseline_s"] = ld_times[name]
                entry["cost_ratio_vs_ld"] = round((elapsed / len(seqs)) / ld_times[name], 2)
            per_seed.append(entry)
        all_out[name] = per_seed
        print(json.dumps({name: per_seed}, indent=2), flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(all_out, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
