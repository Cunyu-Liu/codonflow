"""EXP-4 evaluation: post-training greedy decoding metrics for the ablation
matrix (spec R8 EXP-4, Task 3.2.5).

Groups (all initialized from the same pretrain ckpt, trained to plateau):
  - v4_equal (lambda=0.5, ungated rollouts)      [GrammarRL recipe]
  - v4_lam025 / v4_lam075                        [lambda scan]
  - v4_direct_only (lambda=0) / v4_reverse_only (lambda=1)
  - v3_gated (lambda=0.5, GATED rollouts)        [guidance ablation]
  - v2_weak_guide (dead-axis ATC era)            [historical control]
  - pretrain (no RL, pure guidance)              [no-RL anchor]

Metrics per group (greedy decode: argmax at each position iteratively):
  hypervolume (3-D), NED, identity rate (greedy decode AND rollout
  reported separately), training reward curve stats.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import (
    SYNONYMOUS_CODONS,
    gc_fraction,
    protein_of_cds,
    split_codons,
    STANDARD_TABLE_1,
    translate,
)
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import (
    cai,
    cai_weights_from_rscu,
    hypervolume,
    pairwise_ned,
    unique_fraction,
)
from codonflow.eval.mfe_parallel import mfe_batch_parallel
from codonflow.gating.atc import ATCUtility
from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer
from codonflow.models.batched_sampler import BatchedGuidedSampler, BatchedReward
from codonflow.core.tokenizer import CODON_TO_INDEX, BOS_ID, EOS_ID
from codonflow.models.guided_sampler import synonymous_x0
from codonflow.core.motifs import motif_penalty_score

ATC_YAML = "/home/cunyuliu/codonflow/configs/atc_norm.yaml"

GROUPS = [
    ("v4_equal", "/mnt/cunyuliu/codonflow/checkpoints/p3_rloo_v4_ungated/converged.pt"),
    ("v4_equal_s1", "/mnt/cunyuliu/codonflow/checkpoints/p3_v4s1_equal/converged.pt"),
    ("v4_equal_s2", "/mnt/cunyuliu/codonflow/checkpoints/p3_v4s2_equal/converged.pt"),
    ("v4_lam025", "/mnt/cunyuliu/codonflow/checkpoints/p3_rloo_v4_lam025/converged.pt"),
    ("v4_lam025_s1", "/mnt/cunyuliu/codonflow/checkpoints/p3_v4s1_lam025/converged.pt"),
    ("v4_lam025_s2", "/mnt/cunyuliu/codonflow/checkpoints/p3_v4s2_lam025/converged.pt"),
    ("v4_lam075", "/mnt/cunyuliu/codonflow/checkpoints/p3_rloo_v4_lam075/converged.pt"),
    ("v4_lam075_s1", "/mnt/cunyuliu/codonflow/checkpoints/p3_v4s1_lam075/converged.pt"),
    ("v4_lam075_s2", "/mnt/cunyuliu/codonflow/checkpoints/p3_v4s2_lam075/converged.pt"),
    ("v4_direct_only", "/mnt/cunyuliu/codonflow/checkpoints/p3_rloo_v4_direct_only/converged.pt"),
    ("v4_direct_s1", "/mnt/cunyuliu/codonflow/checkpoints/p3_v4s1_direct/converged.pt"),
    ("v4_direct_s2", "/mnt/cunyuliu/codonflow/checkpoints/p3_v4s2_direct/converged.pt"),
    ("v4_reverse_only", "/mnt/cunyuliu/codonflow/checkpoints/p3_rloo_v4_reverse_only/converged.pt"),
    ("v4_reverse_s1", "/mnt/cunyuliu/codonflow/checkpoints/p3_v4s1_reverse/converged.pt"),
    ("v4_reverse_s2", "/mnt/cunyuliu/codonflow/checkpoints/p3_v4s2_reverse/converged.pt"),
    ("v3_gated", "/mnt/cunyuliu/codonflow/checkpoints/p3_rloo_v3/last.pt"),
    ("v2_weak_guide", "/mnt/cunyuliu/codonflow/checkpoints/p3_rloo_v2/last.pt"),
    ("pretrain", "/mnt/cunyuliu/codonflow/checkpoints/p2_pretrain_768d/converged.pt"),
    ("pretrain_v2", "/mnt/cunyuliu/codonflow/checkpoints/p2_pretrain_v2_corrupt/last.pt"),
    ("pretrain_v2_conv", "/mnt/cunyuliu/codonflow/checkpoints/p2_pretrain_v2_corrupt/converged.pt"),
    ("rloo_v5", "/mnt/cunyuliu/codonflow/checkpoints/p3_rloo_v5_v2base/converged.pt"),
    ("pretrain_v2_ep18", "/mnt/cunyuliu/codonflow/checkpoints/p2_pretrain_v2_corrupt/last.pt"),
]


def greedy_decode(model, x0: str, device, n_steps: int = 20,
                  reward_fn=None, temperature: float = 0.1) -> str:
    """Near-greedy guided decode: the token head was trained on noise->target
    denoising, so raw per-position argmax collapses to high-frequency codons
    (non-synonymous). The CORRECT decode for an edit flow is the gated
    guided sampler with near-zero temperature (argmax over the Doob-h
    weighted synonymous candidates)."""
    sampler = _get_sampler(model, device, reward_fn, temperature)
    seq, _ = sampler.sample(x0)
    return seq


_SAMPLER_CACHE = {}


def _get_sampler(model, device, reward_fn, temperature):
    key = (id(model), temperature)
    if key not in _SAMPLER_CACHE:
        from codonflow.models.batched_sampler import BatchedGuidedSampler

        _SAMPLER_CACHE[key] = BatchedGuidedSampler(
            model, device, reward_fn, n_steps=20, n_candidates=10,
            temperature=temperature, rng=np.random.default_rng(0),
        )
    return _SAMPLER_CACHE[key]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--n-decodes", type=int, default=30)
    ap.add_argument("--n-steps", type=int, default=20)
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/E4_ablation.json")
    ap.add_argument("--only", default="", help="comma-separated group filter (default: all)")
    ap.add_argument("--append", action="store_true", help="merge into existing --out json")
    args = ap.parse_args()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    assert device.type == "cuda", "GPU required"
    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    atc = ATCUtility.from_yaml(ATC_YAML)

    sources = [(h.split()[0], s) for h, s in read_fasta(args.benchmark_fasta)]
    out = {}
    if args.append and Path(args.out).exists():
        out = json.loads(Path(args.out).read_text())
    only = {g.strip() for g in args.only.split(",") if g.strip()}
    for gname, ckpt in GROUPS:
        if only and gname not in only:
            continue
        if not Path(ckpt).exists():
            print(f"skip {gname}: no ckpt {ckpt}", flush=True)
            continue
        model = EditFlowTransformer(EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0))
        state = torch.load(ckpt, map_location="cpu", weights_only=True)
        model.load_state_dict(state)
        model = model.to(device).eval()

        per_family = {}
        for name, cds in sources:
            rng = np.random.default_rng(0)
            mfe_cache: dict = {}
            reward = BatchedReward(weights, atc, mfe_cache)
            decodes = []
            for i in range(args.n_decodes):
                x0 = synonymous_x0(cds, rng)
                decodes.append(greedy_decode(model, x0, device, args.n_steps, reward))
            _SAMPLER_CACHE.clear()
            prot_ref = translate(cds)
            ident = [int(translate(s) == prot_ref) for s in decodes]
            mfes = mfe_batch_parallel(decodes, n_procs=16)
            cais = [cai(s, weights) for s in decodes]
            pts = [
                [c, -m, -abs(gc_fraction(s) - 0.55)] for c, m, s in zip(cais, mfes, decodes)
            ]
            hv = hypervolume(pts, (0.5, 100.0, -0.2)) if pts else 0.0
            per_family[name] = {
                "identity_rate_greedy": sum(ident) / max(len(ident), 1),
                "cai_mean": float(np.mean(cais)),
                "mfe_mean": float(np.mean(mfes)),
                "hypervolume": hv,
                "ned_mean": pairwise_ned(decodes),
                "unique_fraction": unique_fraction(decodes),
                "u_mean": float(
                    np.mean(
                        [
                            atc.utility(c, -m, -abs(gc_fraction(s) - 0.55), -motif_penalty_score(s))
                            for c, m, s in zip(cais, mfes, decodes)
                        ]
                    )
                ),
            }
        out[gname] = per_family
        f0 = sources[0][0]
        print(f"{gname}: {f0} HV {per_family[f0]['hypervolume']:.2f} "
              f"ident {per_family[f0]['identity_rate_greedy']:.2f} "
              f"NED {per_family[f0]['ned_mean']:.3f}", flush=True)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
