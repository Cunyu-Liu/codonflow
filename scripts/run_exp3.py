"""EXP-3 preference scan (spec R8 EXP-3, Task 3.2.5c).

7 weight directions on the three objectives (CAI / -MFE / -|GC-0.55|):
  3 corners + 4 edge-interior points, 100 solutions each (spec line 215).
For each direction we set ATC omega (f1..f3; f4 fixed at 0.5) and sample
with the gated guided sampler. Reference front = non-dominated union of
all methods' solutions (computed post-hoc from all arms' outputs).

Outputs: objective-space scatter (2 projections), per-cluster non-
dominated share, front coverage.
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

from codonflow.core.codon import gc_fraction
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import cai, cai_weights_from_rscu
from codonflow.eval.mfe_parallel import mfe_batch_parallel
from codonflow.gating.atc import ATCUtility
from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer
from codonflow.models.batched_sampler import BatchedGuidedSampler, BatchedReward
from codonflow.models.guided_sampler import synonymous_x0

DIRECTIONS = [
    ("cai_only", (1.0, 0.0, 0.0)),
    ("mfe_only", (0.0, 1.0, 0.0)),
    ("gc_only", (0.0, 0.0, 1.0)),
    ("cai_mfe_half", (0.5, 0.5, 0.0)),
    ("cai_gc_half", (0.5, 0.0, 0.5)),
    ("mfe_gc_half", (0.0, 0.5, 0.5)),
    ("balanced", (1 / 3, 1 / 3, 1 / 3)),
]

ATC_YAML = "/home/cunyuliu/codonflow/configs/atc_norm.yaml"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--n-solutions", type=int, default=100)
    ap.add_argument("--n-steps", type=int, default=20)
    ap.add_argument("--n-candidates", type=int, default=10)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/E3_preference_scan.json")
    args = ap.parse_args()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    assert device.type == "cuda", "GPU required"
    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))

    model = EditFlowTransformer(
        EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0)
    )
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model = model.to(device).eval()

    all_out = {}
    for header, cds in read_fasta(args.benchmark_fasta):
        name = header.split()[0]
        per_dir = {}
        for dir_name, (w1, w2, w3) in DIRECTIONS:
            atc = ATCUtility.from_yaml(ATC_YAML)
            atc.omega = (w1, w2, w3, 0.5)
            seqs = []
            rng = np.random.default_rng(7)
            mfe_cache: dict = {}
            sampler = BatchedGuidedSampler(
                model, device,
                BatchedReward(weights, atc, mfe_cache),
                n_steps=args.n_steps, n_candidates=args.n_candidates,
                temperature=1.0, rng=np.random.default_rng(11),
            )
            for _ in range(args.n_solutions):
                x0 = synonymous_x0(cds, rng)
                seq, _ = sampler.sample(x0)
                seqs.append(seq)
            mfes = mfe_batch_parallel(seqs, n_procs=16)
            cais = [cai(s, weights) for s in seqs]
            gcs = [gc_fraction(s) for s in seqs]
            objs = [[c, -m, -abs(g - 0.55)] for c, m, g in zip(cais, mfes, gcs)]
            per_dir[dir_name] = {
                "omega": [w1, w2, w3],
                "n": len(seqs),
                "cai_mean": float(np.mean(cais)),
                "cai_std": float(np.std(cais)),
                "mfe_mean": float(np.mean(mfes)),
                "gc_mean": float(np.mean(gcs)),
                "gc_std": float(np.std(gcs)),
                "obj_vectors": objs,
                "samples_head": seqs[:5],
            }
            print(f"{name} {dir_name}: CAI {np.mean(cais):.3f} MFE {np.mean(mfes):.1f} GC {np.mean(gcs):.3f}", flush=True)
        all_out[name] = per_dir

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(all_out, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
