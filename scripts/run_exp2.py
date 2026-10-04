"""EXP-2 core comparison: gated guided sampling vs uniform generation + post
filtering under the SAME total scoring budget (spec R8 EXP-2, Task 3.2.5b).

Pre-registered design (spec line 208-213):
  - three arms share total rollout budget B (default 500 scoring calls/seq):
    A. gated guided (budget spent on per-step candidate evaluation)
    B. uniform generate + post-filter (budget all spent on generation; rank
       by G(x) and take top-K)
    C. hard-masking anchor (codonGPT constrained sampling reference)
  - metrics: feasible-solution yield (per 1000 samples legal AND identity-
    keeping), hypervolume of feasible solutions, time-to-first-usable
  - stats: >=3 families x 3 seeds, Wilcoxon paired test

Budget semantics (strict): a "scoring call" = one RNAfold/CAI/GC/motif
evaluation of a candidate terminal sequence. Gated: n_steps*n_candidates
calls per rollout. Post-filter: 1 call per generated sequence (generation
itself is not counted - both arms pay it via sampling).
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
    gc_fraction,
    STANDARD_TABLE_1,
    SYNONYMOUS_CODONS,
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
from codonflow.models.guided_sampler import synonymous_x0
from codonflow.core.motifs import motif_penalty_score

try:
    from scipy.stats import wilcoxon
except ImportError:
    wilcoxon = None

ATC_YAML = "/home/cunyuliu/codonflow/configs/atc_norm.yaml"


def obj_vector(seq: str, weights, mfe_cache: dict):
    if seq not in mfe_cache:
        mfe_cache[seq] = mfe_batch_parallel([seq], n_procs=1)[0]
    m = mfe_cache[seq]
    return [
        cai(seq, weights),
        -m,
        -abs(gc_fraction(seq) - 0.55),
    ]


def hypervolume_3d(seqs, weights, mfe_cache, ref_point=(0.5, 100.0, -0.2)):
    pts = [obj_vector(s, weights, mfe_cache) for s in seqs]
    if not pts:
        return 0.0
    return float(hypervolume(pts, ref_point))


def time_to_first_usable(seqs, source, threshold: float, atc, weights, mfe_cache):
    """Index (per-1000) of the first solution with U >= threshold."""
    n = 0
    for s in seqs:
        n += 1
        u = score_u(s, atc, weights, mfe_cache)
        if u >= threshold:
            return (n - 1) / max(len(seqs), 1), n
    return 1.0, n


def score_u(s, atc, weights, mfe_cache):
    if s not in mfe_cache:
        mfe_cache[s] = mfe_batch_parallel([s], n_procs=1)[0]
    m = mfe_cache[s]
    return atc.utility(
        cai(s, weights), -m, -abs(gc_fraction(s) - 0.55), -motif_penalty_score(s)
    )


def run_exp2_arm_a(
    source, model, device, weights, atc, budget, n_steps, n_candidates, seed, rng,
    mfe_cache: dict,
):
    """Gated guided arm: budget = n_steps * n_candidates calls per rollout."""
    calls_per_rollout = n_steps * n_candidates
    n_rollouts = max(1, budget // calls_per_rollout)
    t0 = time.time()
    sampler = BatchedGuidedSampler(
        model, device,
        BatchedReward(weights, atc, mfe_cache),
        n_steps=n_steps, n_candidates=n_candidates,
        temperature=1.0, rng=np.random.default_rng(seed),
    )
    seqs = []
    for _ in range(n_rollouts):
        x0 = synonymous_x0(source, rng)
        seq, _trace = sampler.sample(x0)
        seqs.append(seq)
    elapsed = time.time() - t0
    return seqs, elapsed, n_rollouts * calls_per_rollout


def run_exp2_arm_b(source, weights, budget, seed, rng):
    """Uniform + post-filter arm: 1 scoring call per generated sequence."""
    mfe_cache: dict = {}
    t0 = time.time()
    seqs = [synonymous_x0(source, rng) for _ in range(budget)]
    elapsed = time.time() - t0
    return seqs, elapsed, budget


def eval_arm(seqs, source, weights, atc, mfe_cache, arm_name, elapsed, scoring_calls):
    feas = [s for s in seqs if feasible_edit(s, source)]
    cais = [cai(s, weights) for s in feas]
    us = [score_u(s, atc, weights, mfe_cache) for s in feas]
    mfes = [mfe_cache[s] for s in feas]
    hv = hypervolume_3d(feas, weights, mfe_cache)
    ned = pairwise_ned(seqs) if len(seqs) > 1 else 0.0
    return {
        "arm": arm_name,
        "n_generated": len(seqs),
        "n_feasible": len(feas),
        "feasible_rate": len(feas) / max(len(seqs), 1),
        "cai_mean": float(np.mean(cais)) if cais else 0.0,
        "mfe_mean": float(np.mean(mfes)) if mfes else 0.0,
        "u_mean": float(np.mean(us)) if us else 0.0,
        "hypervolume": hv,
        "ned_mean": float(ned),
        "unique_fraction": unique_fraction(seqs),
        "elapsed_s": round(elapsed, 2),
        "scoring_calls": scoring_calls,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--budget", type=int, default=500)
    ap.add_argument("--n-seeds", type=int, default=3)
    ap.add_argument("--n-steps", type=int, default=20)
    ap.add_argument("--n-candidates", type=int, default=10)
    ap.add_argument("--families", nargs="*", default=None,
                    help="family accessions to use; default: all in fasta")
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/E2_gated_vs_filter.json")
    args = ap.parse_args()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    assert device.type == "cuda", "GPU required"
    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    atc = ATCUtility.from_yaml(ATC_YAML)
    model = EditFlowTransformer(
        EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0)
    )
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model = model.to(device).eval()

    families = []
    for header, cds in read_fasta(args.benchmark_fasta):
        name = header.split()[0]
        if args.families and name not in args.families:
            continue
        families.append((name, cds))
    print(f"families: {[n for n, _ in families]}", flush=True)

    all_results = {}
    hv_gated, hv_filter = [], []
    for name, cds in families:
        per_seed = []
        for seed in range(args.n_seeds):
            rng = np.random.default_rng(seed)
            mfe_cache: dict = {}
            gated_seqs, gated_time, gated_calls = run_exp2_arm_a(
                cds, model, device, weights, atc,
                args.budget, args.n_steps, args.n_candidates, seed, rng,
                mfe_cache,
            )
            rng_b = np.random.default_rng(seed)
            uni_seqs, uni_time, uni_calls = run_exp2_arm_b(
                cds, weights, args.budget, seed, rng_b
            )
            arm_a = eval_arm(
                gated_seqs, cds, weights, atc, mfe_cache,
                "gated_guided", gated_time, gated_calls,
            )
            mfe_cache_b: dict = {}
            scored = [
                (score_u(s, atc, weights, mfe_cache_b), s) for s in uni_seqs
            ]
            scored.sort(key=lambda x: -x[0])
            topk = [s for _, s in scored[: max(len(gated_seqs), 1)]]
            u_med = float(np.median([u for u, _ in scored[:50]]))

            arm_b = eval_arm(
                uni_seqs, cds, weights, atc, mfe_cache_b,
                "uniform+filter(all)", uni_time, uni_calls,
            )
            arm_b_top = eval_arm(
                topk, cds, weights, atc, mfe_cache_b,
                "uniform+filter(topK)", uni_time, uni_calls,
            )
            tt1, n_t1 = time_to_first_usable(
                gated_seqs, cds, u_med, atc, weights, mfe_cache
            )
            tt1_b, n_t1b = time_to_first_usable(
                uni_seqs, cds, u_med, atc, weights, mfe_cache_b
            )
            per_seed.append({
                "seed": seed,
                "gated": arm_a,
                "uniform_postfilter": arm_b,
                "uniform_postfilter_topk": arm_b_top,
                "time_to_first_usable_gated": {"frac": tt1, "index": n_t1},
                "time_to_first_usable_filter": {"frac": tt1_b, "index": n_t1b},
                "u_threshold": u_med,
            })
            hv_gated.append(arm_a["hypervolume"])
            hv_filter.append(arm_b_top["hypervolume"])
        all_results[name] = per_seed
        print(json.dumps({name: per_seed[0]["gated"]}, indent=2), flush=True)
    if wilcoxon is not None and len(hv_gated) >= 6:
        stat, p = wilcoxon(hv_gated, hv_filter)
        all_results["_wilcoxon_hv"] = {"stat": float(stat), "p": float(p)}
        print(f"Wilcoxon HV gated vs filter: stat={stat:.4f} p={p:.2e}", flush=True)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(all_results, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
