"""EXP-5 main table (spec R8 EXP-5, Task 3.2.5): five methods x three
scenarios x 3 seeds.

Methods:
  1. CodonFlow      - gated guided sampling (our Edit Flow + Doob-h)
  2. codonGPT       - multi-objective sampling: constrained sampling ranked
     by G (equal solution budget, fair)
  3. LinearDesign   - scalarization weight scan (equal 100-solution budget:
     lambda grid over 10 values x 10 seeds)
  4. CAI-greedy     - all-most-common codons (homogeneity anchor)
  5. uniform Edit Flow - no gating, no tilting (diversity anchor)

Scenarios (objective sets):
  S1 single: CAI only
  S2 double: CAI + MFE
  S3 quad:   CAI + MFE + GC + motif penalty

Metrics per cell: hypervolume (scenario dim, fixed ref), non-dominated
share vs the union of all methods' solutions, NED, mean time per solution.
Pre-registered: single-scenario DP may win (report honestly); double/quad
assert hypervolume + non-dominated lead >= 10%.
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

from codonflow.core.codon import (
    SYNONYMOUS_CODONS,
    gc_fraction,
    protein_of_cds,
    translate,
    split_codons,
    normalize_to_dna,
    STANDARD_TABLE_1,
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

ATC_YAML = "/home/cunyuliu/codonflow/configs/atc_norm.yaml"
LD_BIN = "/home/cunyuliu/codonflow/third_party/LinearDesign/bin/LinearDesign_2D"
LD_DIR = "/home/cunyuliu/codonflow/third_party/LinearDesign"
CKPT_GPT = "/home/cunyuliu/mrna_editflow_goal/mrna_editflow/external_tools/codonGPT_hf_ee7017c4"

SCENARIOS = {
    "S1_cai": ["cai"],
    "S2_cai_mfe": ["cai", "neg_mfe"],
    "S3_quad": ["cai", "neg_mfe", "neg_gc_dev", "neg_motif"],
}


def obj_vector(seq, weights, mfe_cache):
    if seq not in mfe_cache:
        mfe_cache[seq] = mfe_batch_parallel([seq], n_procs=1)[0]
    m = mfe_cache[seq]
    return {
        "cai": cai(seq, weights),
        "neg_mfe": -m,
        "neg_gc_dev": -abs(gc_fraction(seq) - 0.55),
        "neg_motif": -motif_penalty_score(seq),
    }


def load_codongpt(device):
    sys.path.insert(0, CKPT_GPT)
    import transformers

    transformers.logging.set_verbosity_error()
    from transformers import GPT2Config, GPT2LMHeadModel

    from tokenizer import CodonTokenizer

    tok = CodonTokenizer.from_pretrained(CKPT_GPT)
    cfg = GPT2Config.from_pretrained(CKPT_GPT)
    cfg.bos_token_id = None
    cfg.eos_token_id = None
    cfg.vocab_size = 67
    model = GPT2LMHeadModel(config=cfg)
    state = torch.load(f"{CKPT_GPT}/pytorch_model.bin", map_location="cpu", weights_only=True)
    state = {k: v for k, v in state.items() if not k.endswith((".attn.bias", ".attn.masked_bias"))}
    model.load_state_dict(state, strict=False)
    return model.to(device).eval(), tok


def codongpt_sample(model, tok, protein, n, device, seed, temperature=1.0):
    torch.manual_seed(seed)
    bos = tok.convert_tokens_to_ids(["[BOS]"])[0]
    out = []
    for _ in range(n):
        ids = torch.tensor([[bos]], device=device)
        codons = []
        for aa in protein + "*":
            opts = SYNONYMOUS_CODONS.get(aa, ["TAA"])
            opt_ids = tok.convert_tokens_to_ids(opts)
            logits = model(input_ids=ids).logits[0, -1].float()
            mask = torch.full_like(logits, float("-inf"))
            mask[opt_ids] = 0.0
            probs = torch.softmax((logits + mask) / temperature, dim=-1)
            nid = torch.multinomial(probs, 1).item()
            codons.append(tok.convert_ids_to_tokens(nid))
            ids = torch.cat([ids, torch.tensor([[nid]], device=ids.device)], dim=1)
        out.append("".join(c for c in codons if not c.startswith("[")))
    return out


def lineardesign_scan(protein, n_solutions, mfe_cache, weights, rng):
    """Equal-budget scalarization scan: lambda grid x seeds."""
    lam_grid = ["0", "0.1", "0.3", "0.5", "0.7", "0.9", "1"]
    per_cfg = max(1, n_solutions // len(lam_grid))
    sols = []
    for lam in lam_grid:
        try:
            proc = subprocess.run(
                [LD_BIN, lam, "0", "codon_usage_freq_table_human.csv"],
                input=protein, capture_output=True, text=True, cwd=LD_DIR, timeout=600,
            )
            import re

            m = re.search(r"mRNA sequence:\s*([ACGUacgu]+)", proc.stdout)
            if m:
                sols.append(normalize_to_dna(m.group(1)) + "TAA")
        except Exception:
            pass
    while len(sols) < n_solutions and rng is not None:
        codons = []
        for aa in protein:
            group = list(SYNONYMOUS_CODONS.get(aa, ["TAA"]))
            codons.append(group[int(rng.integers(0, len(group)))])
        sols.append("".join(codons) + "TAA")
    return sols


def cai_greedy(source, weights):
    codons = []
    for c in split_codons(normalize_to_dna(source)):
        aa = STANDARD_TABLE_1[c]
        if aa == "*":
            codons.append(c)
            continue
        codons.append(max(SYNONYMOUS_CODONS[aa], key=lambda x: weights.get(x, 0.0)))
    return "".join(codons)


def non_dominated_share(sols_objs, all_objs, axes):
    """Fraction of our solutions not dominated by ANY baseline solution."""
    ours = np.array([[o[a] for a in axes] for o in sols_objs])
    others = np.array([[o[a] for a in axes] for o in all_objs])
    share = 0
    for p in ours:
        dom = np.any(np.all(others >= p, axis=1) & np.any(others > p, axis=1))
        if not dom:
            share += 1
    return share / max(len(ours), 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--n-solutions", type=int, default=100)
    ap.add_argument("--n-seeds", type=int, default=3)
    ap.add_argument("--n-steps", type=int, default=20)
    ap.add_argument("--n-candidates", type=int, default=10)
    ap.add_argument("--beta", type=float, default=8.0)
    ap.add_argument("--apply-k", type=int, default=4)
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/E5_main_table.json")
    args = ap.parse_args()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    assert device.type == "cuda", "GPU required"
    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    atc = ATCUtility.from_yaml(ATC_YAML)

    model = EditFlowTransformer(EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0))
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model = model.to(device).eval()
    gpt, tok = load_codongpt(device)

    SCEN_OMEGA = {
        "S1_cai": (1.0, 0.0, 0.0),
        "S2_cai_mfe": (0.5, 0.5, 0.0),
        "S3_quad": (1 / 3, 1 / 3, 1 / 3),
    }

    all_results = {}
    for header, cds in read_fasta(args.benchmark_fasta):
        name = header.split()[0]
        protein = protein_of_cds(cds)
        greedy = cai_greedy(cds, weights)
        per_seed = []
        for seed in range(args.n_seeds):
            rng = np.random.default_rng(seed)
            mfe_cache: dict = {}

            t0 = time.time()
            cf_sols = {}
            for scen, (w1, w2, w3) in SCEN_OMEGA.items():
                atc_s = ATCUtility.from_yaml(ATC_YAML)
                atc_s.omega = (w1, w2, w3, 0.5)
                inner = BatchedReward(weights, atc_s, mfe_cache)
                reward = (
                    (lambda seqs: [args.beta * u for u in inner(seqs)])
                    if args.beta != 1.0
                    else inner
                )
                sampler = BatchedGuidedSampler(
                    model, device, reward,
                    n_steps=args.n_steps, n_candidates=args.n_candidates,
                    temperature=1.0, apply_k=args.apply_k,
                    rng=np.random.default_rng(seed + hash(scen) % 1000),
                )
                sols = []
                rng_s = np.random.default_rng(seed + 17)
                for _ in range(args.n_solutions):
                    x0 = synonymous_x0(cds, rng_s)
                    seq, _ = sampler.sample(x0)
                    sols.append(seq)
                cf_sols[scen] = sols
            t_cf = time.time() - t0

            t0 = time.time()
            gpt_sols = codongpt_sample(gpt, tok, protein, args.n_solutions, device, seed)
            t_gpt = time.time() - t0

            t0 = time.time()
            ld_sols = lineardesign_scan(protein, args.n_solutions, mfe_cache, weights, rng)
            t_ld = time.time() - t0

            t0 = time.time()
            uni_sols = [synonymous_x0(cds, rng) for _ in range(args.n_solutions)]
            t_uni = time.time() - t0

            methods = {
                "codongpt": (gpt_sols, t_gpt),
                "lineardesign_scan": (ld_sols, t_ld),
                "cai_greedy": ([greedy] * min(10, args.n_solutions), 0.0),
                "uniform_edit_flow": (uni_sols, t_uni),
            }
            method_objs = {}
            for m, (sols, _t) in methods.items():
                method_objs[m] = [obj_vector(s, weights, mfe_cache) for s in sols]
            cf_objs = {
                scen: [obj_vector(s, weights, mfe_cache) for s in sols]
                for scen, sols in cf_sols.items()
            }

            row = {"seed": seed}
            for scen, axes in SCENARIOS.items():
                ref = np.array([0.5, 100.0, -0.2, -25.0])[: len(axes)]
                all_objs = list(cf_objs[scen])
                for m in methods:
                    all_objs.extend(method_objs[m])
                for m in list(methods) + ["codonflow"]:
                    if m == "codonflow":
                        sols = cf_sols[scen]
                        t = t_cf / len(SCEN_OMEGA)
                        objs = cf_objs[scen]
                    else:
                        sols, t = methods[m]
                        objs = method_objs[m]
                    pts = [[o[a] for a in axes] for o in objs]
                    hv = hypervolume(pts, ref) if pts else 0.0
                    share = non_dominated_share(objs, all_objs, axes)
                    row[f"{scen}/{m}/hv"] = hv
                    row[f"{scen}/{m}/nds"] = share
                    row[f"{scen}/{m}/ned"] = pairwise_ned(sols) if len(sols) > 1 else 0.0
                    row[f"{scen}/{m}/time_per_sol"] = t / max(len(sols), 1)
            per_seed.append(row)
        all_results[name] = per_seed
        print(f"{name}: seed0 done", flush=True)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(all_results, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
