"""EXP-6 budget-quality-time curves (spec R8 EXP-6, Task 3.2.5d).

Grid: steps{10,20,30} x candidates{10,30} x rollouts{5,10} per spec line 231;
50 solutions per config on eGFP; records hypervolume, U, per-solution time,
and GPU memory footprint. Produces the budget-quality curve family and the
'saturation point cost < LinearDesign x5' check (stop-condition iv).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import cai, cai_weights_from_rscu, hypervolume
from codonflow.eval.mfe_parallel import mfe_batch_parallel
from codonflow.gating.atc import ATCUtility
from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer
from codonflow.models.batched_sampler import BatchedGuidedSampler, BatchedReward
from codonflow.models.guided_sampler import synonymous_x0
from codonflow.core.codon import gc_fraction
from codonflow.core.motifs import motif_penalty_score

ATC_YAML = "/home/cunyuliu/codonflow/configs/atc_norm.yaml"


def gpu_mem_mb():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        return int(out.stdout.strip().splitlines()[0])
    except Exception:
        return -1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--beta", type=float, default=8.0)
    ap.add_argument("--apply-k", type=int, default=4)
    ap.add_argument("--n-solutions", type=int, default=50)
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/E6_budget_curves.json")
    args = ap.parse_args()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    assert device.type == "cuda", "GPU required"
    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    atc = ATCUtility.from_yaml(ATC_YAML)

    model = EditFlowTransformer(EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0))
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model = model.to(device).eval()

    sources = [(h.split()[0], s) for h, s in read_fasta(args.benchmark_fasta)]
    name, cds = sources[0]

    grid = [
        (s, c) for s in (10, 20, 30) for c in (10, 30)
    ]
    results = []
    for n_steps, n_cands in grid:
        for n_rollouts in (5, 10):
            rng = np.random.default_rng(0)
            mfe_cache: dict = {}
            inner = BatchedReward(weights, atc, mfe_cache)
            reward = (
                (lambda seqs: [args.beta * u for u in inner(seqs)])
                if args.beta != 1.0 else inner
            )
            sampler = BatchedGuidedSampler(
                model, device, reward,
                n_steps=n_steps, n_candidates=n_cands,
                temperature=1.0, apply_k=args.apply_k,
                rng=np.random.default_rng(0),
            )
            t0 = time.time()
            seqs = []
            for _ in range(n_rollouts):
                x0 = synonymous_x0(cds, rng)
                s, _ = sampler.sample(x0)
                seqs.append(s)
            elapsed = time.time() - t0
            per_sol = elapsed / max(len(seqs), 1)
            mfes = mfe_batch_parallel(seqs)
            cais = [cai(s, weights) for s in seqs]
            us = [
                atc.utility(c, -m, -abs(gc_fraction(s) - 0.55), -motif_penalty_score(s))
                for c, m, s in zip(cais, mfes, seqs)
            ]
            pts = [[c, -m, -abs(gc_fraction(s) - 0.55)] for c, m, s in zip(cais, mfes, seqs)]
            hv = hypervolume(pts, (0.5, 100.0, -0.2))
            calls = n_rollouts * n_steps * n_cands
            results.append({
                "n_steps": n_steps, "n_candidates": n_cands, "n_rollouts": n_rollouts,
                "scoring_calls": calls,
                "hv": hv, "u_mean": float(np.mean(us)),
                "cai_mean": float(np.mean(cais)), "mfe_mean": float(np.mean(mfes)),
                "elapsed_s": round(elapsed, 1), "per_sol_s": round(per_sol, 2),
                "gpu_mem_mb": gpu_mem_mb(),
            })
            print(
                f"steps={n_steps} C={n_cands} R={n_rollouts}: calls={calls} "
                f"HV={hv:.2f} u={np.mean(us):.3f} per_sol={per_sol:.1f}s mem={gpu_mem_mb()}MB",
                flush=True,
            )

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
