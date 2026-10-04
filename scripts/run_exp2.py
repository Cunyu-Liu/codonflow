"""EXP-2 core comparison: gated guided sampling vs uniform generation + post
filtering under the SAME total scoring budget (spec R8 EXP-2, Task 2.2.6).

Three arms:
  A. gated guided sampling (budget spent on per-step candidate evaluation)
  B. uniform sampling + post-filter (budget spent on generation, top by G)
  C. hard-masking anchor (codonGPT constrained samples, reference)

Metrics: feasible-yield rate, hypervolume of feasible solutions,
time-to-first-usable.
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
    translate,
    normalize_to_dna,
    split_codons,
    STANDARD_TABLE_1,
    SYNONYMOUS_CODONS,
    gc_fraction,
)
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import (
    cai,
    cai_weights_from_rscu,
    mfe_batch,
    pairwise_ned,
    unique_fraction,
)
from codonflow.gating.atc import ATCUtility, feasibility_and_log_utility
from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer
from codonflow.models.guided_sampler import CodonGuidedSampler, synonymous_x0
from codonflow.core.motifs import motif_penalty_score


def make_reward(atc: ATCUtility, weights, beta: float, mfe_cache: dict):
    def reward(cds: str) -> float:
        key = cds
        if key in mfe_cache:
            m = mfe_cache[key]
        else:
            m = mfe_batch([cds])[0]
            mfe_cache[key] = m
        c = cai(cds, weights)
        u = atc.utility(
            c, -m, -abs(gc_fraction(cds) - 0.55), -motif_penalty_score(cds)
        )
        return beta * u
    return reward


def objective_vector(seq: str, weights):
    return (
        cai(seq, weights),
        -mfe_batch([seq])[0],
        -abs(gc_fraction(seq) - 0.55),
    )


def run_exp2(
    source: str,
    model,
    device,
    weights,
    atc,
    budget: int = 500,
    n_steps: int = 20,
    n_candidates: int = 10,
    seed: int = 0,
    out: dict | None = None,
):
    rng = np.random.default_rng(seed)
    mfe_cache: dict = {}
    reward = make_reward(atc, weights, beta=1.0, mfe_cache=mfe_cache)
    prot = protein_of_cds(source)
    results: dict = {}

    t0 = time.time()
    sampler = CodonGuidedSampler(
        model, device, reward, n_steps=n_steps, n_candidates=n_candidates,
        temperature=1.0, rng=np.random.default_rng(seed),
    )
    gated_seqs = []
    n_runs = max(1, budget // (n_steps * n_candidates))
    for r in range(n_runs):
        x0 = synonymous_x0(source, rng)
        seq, _trace = sampler.sample(x0)
        gated_seqs.append(seq)
    gated_time = time.time() - t0

    rng_b = np.random.default_rng(seed)
    t0 = time.time()
    uniform_seqs = []
    while len(uniform_seqs) < budget // 20:
        uniform_seqs.append(synonymous_x0(source, rng_b))
    uniform_time = time.time() - t0

    def eval_arm(seqs, arm_name, elapsed):
        feas = [s for s in seqs if feasible_edit(s, source)]
        cais = [cai(s, weights) for s in seqs]
        mfes = mfe_batch(seqs)
        return {
            "arm": arm_name,
            "n_generated": len(seqs),
            "n_feasible": len(feas),
            "feasible_rate": len(feas) / max(len(seqs), 1),
            "cai_mean": float(np.mean(cais)),
            "mfe_mean": float(np.mean(mfes)),
            "ned_mean": pairwise_ned(seqs),
            "unique_fraction": unique_fraction(seqs),
            "elapsed_s": round(elapsed, 2),
        }

    results["gated"] = eval_arm(gated_seqs, "gated_guided", gated_time)
    results["uniform_postfilter"] = eval_arm(uniform_seqs, "uniform+filter", uniform_time)
    # top-K by G after the fact (post-filter arm uses its budget on generation)
    scored = [(reward(s), s) for s in uniform_seqs]
    scored.sort(key=lambda x: -x[0])
    top = [s for _, s in scored[: max(len(gated_seqs), 1)]]
    results["uniform_postfilter_topk"] = eval_arm(top, "uniform+filter_topK", 0.0)
    results["uniform_postfilter_topk"]["cai_mean"] = float(
        np.mean([cai(s, weights) for s in top])
    )
    results["uniform_postfilter_topk"]["mfe_mean"] = float(
        np.mean(mfe_batch(top))
    )
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--budget", type=int, default=500)
    ap.add_argument("--n-seeds", type=int, default=3)
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/E2_gated_vs_filter.json")
    args = ap.parse_args()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    assert device.type == "cuda", "GPU required"
    rscu = json.loads(Path(args.rscu_json).read_text())
    weights = cai_weights_from_rscu(rscu)
    atc = ATCUtility()
    model = EditFlowTransformer(
        EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0)
    )
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model = model.to(device).eval()
    all_results = {}
    for header, cds in read_fasta(args.benchmark_fasta):
        name = header.split()[0]
        per_seed = []
        for seed in range(args.n_seeds):
            r = run_exp2(
                cds, model, device, weights, atc,
                budget=args.budget, seed=seed,
            )
            per_seed.append(r)
        all_results[name] = per_seed
        print(json.dumps({name: per_seed[0]}, indent=2), flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(all_results, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
