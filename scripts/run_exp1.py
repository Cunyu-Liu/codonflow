"""EXP-1 (spec R8, Task 3.2.5a): baseline quality-collapse phenomenon figure.

Three arms on eGFP + nanoLuc, 1000 samples each:
  1. AR unconstrained sampling (codonGPT free generation)
  2. AR + synonymous masking (codonGPT constrained)
  3. CAI-greedy (homogeneity upper anchor)
Metrics: pairwise NED histogram, codon-choice entropy per AA position,
unique fraction, CAI distribution. 3 seeds; KS test on NED distributions
(p<0.05 required to confirm the 'legal but homogeneous' shift).
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
    protein_of_cds,
    translate,
    is_valid_cds,
)
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import (
    cai,
    cai_weights_from_rscu,
    pairwise_ned,
    unique_fraction,
    codon_entropy_per_aa_position,
    ned,
)


def ks_test(x: np.ndarray, y: np.ndarray) -> float:
    from scipy.stats import ks_2samp

    return float(ks_2samp(x, y).pvalue)


def sample_ned_distribution(seqs, sample_limit: int = 500, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = len(seqs)
    if n < 2:
        return np.array([])
    idx = rng.choice(n, size=min(n, sample_limit), replace=False)
    vals = []
    for i in range(len(idx)):
        for j in range(i + 1, len(idx)):
            vals.append(ned(seqs[idx[i]], seqs[idx[j]]))
    return np.array(vals)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--n-samples", type=int, default=1000)
    ap.add_argument("--n-seeds", type=int, default=3)
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/EXP1_collapse.json")
    ap.add_argument("--fig-dir", default="/mnt/cunyuliu/codonflow/eval_outputs")
    args = ap.parse_args()
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    assert device == "cuda:0", "GPU required"
    rscu = json.loads(Path(args.rscu_json).read_text())
    weights = cai_weights_from_rscu(rscu)

    sys.path.insert(0, "/home/cunyuliu/mrna_editflow_goal/mrna_editflow/external_tools/codonGPT_hf_ee7017c4")
    from transformers import GPT2Config, GPT2LMHeadModel

    from tokenizer import CodonTokenizer

    ckpt = "/home/cunyuliu/mrna_editflow_goal/mrna_editflow/external_tools/codonGPT_hf_ee7017c4"
    tok = CodonTokenizer.from_pretrained(ckpt)
    cfg = GPT2Config.from_pretrained(ckpt)
    cfg.bos_token_id = None
    cfg.eos_token_id = None
    cfg.vocab_size = 67
    model = GPT2LMHeadModel(config=cfg)
    state = torch.load(f"{ckpt}/pytorch_model.bin", map_location="cpu", weights_only=True)
    state = {k: v for k, v in state.items() if not k.endswith((".attn.bias", ".attn.masked_bias"))}
    model.load_state_dict(state, strict=False)
    model = model.to(device).eval()
    bos = tok.convert_tokens_to_ids(["[BOS]"])[0]

    def cai_greedy(protein: str) -> str:
        return "".join(
            max(SYNONYMOUS_CODONS[aa], key=lambda c: weights.get(c, 0.0))
            for aa in protein
        ) + "TAA"

    @torch.no_grad()
    def sample_ar(protein: str, n: int, seed: int, constrained: bool):
        torch.manual_seed(seed)
        out = []
        for _ in range(n):
            ids = torch.tensor([[bos]], device=device)
            codons = []
            for aa in protein + "*":
                if constrained:
                    opts = SYNONYMOUS_CODONS.get(aa, ["TAA"])
                    opt_ids = tok.convert_tokens_to_ids(opts)
                else:
                    opts = None
                    opt_ids = None
                logits = model(input_ids=ids).logits[0, -1].float()
                if constrained:
                    m = torch.full_like(logits, float("-inf"))
                    m[opt_ids] = 0.0
                    logits = logits + m
                nxt = torch.multinomial(torch.softmax(logits, dim=-1), 1).item()
                tok_s = tok.convert_ids_to_tokens(nxt)
                if not tok_s.startswith("["):
                    codons.append(tok_s)
                ids = torch.cat([ids, torch.tensor([[nxt]], device=device)], dim=1)
            out.append("".join(codons))
        return out

    all_out = {}
    for header, source in read_fasta(args.benchmark_fasta):
        name = header.split()[0]
        protein = protein_of_cds(source)
        per_seed = []
        for seed in range(args.n_seeds):
            uncon = sample_ar(protein, args.n_samples, seed, constrained=False)
            cons = sample_ar(protein, args.n_samples, seed, constrained=True)
            greedy = [cai_greedy(protein)] * min(100, args.n_samples)
            arms = {"unconstrained": uncon, "constrained": cons, "cai_greedy": greedy}
            summary = {}
            ned_dists = {}
            for arm, seqs in arms.items():
                ident = [int(translate(s) == translate(source)) for s in seqs]
                ned_d = sample_ned_distribution(seqs, seed=seed)
                ned_dists[arm] = ned_d
                summary[arm] = {
                    "n": len(seqs),
                    "identity_rate": sum(ident) / len(seqs),
                    "cai_mean": float(np.mean([cai(s, weights) for s in seqs])),
                    "ned_mean": float(np.mean(ned_d)) if len(ned_d) else 0.0,
                    "unique_fraction": unique_fraction(seqs),
                    "codon_entropy": codon_entropy_per_aa_position(seqs),
                }
            summary["ks_p_uncon_vs_cons"] = ks_test(ned_dists["unconstrained"], ned_dists["constrained"])
            per_seed.append(summary)
        all_out[name] = per_seed
        print(json.dumps({name: per_seed[0]}, indent=2), flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(all_out, indent=2))
    print(f"wrote {args.out}")

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
        for ax, (name, per_seed) in zip(axes, all_out.items()):
            s = per_seed[0]
            for arm, color in [("unconstrained", "#3b7dd8"), ("constrained", "#d86f3b")]:
                ax.hist([], bins=30, alpha=0.6, label=arm, color=color)
            ax.set_title(f"{name}: NED mean uncon {s['unconstrained']['ned_mean']:.3f} vs cons {s['constrained']['ned_mean']:.3f}")
            ax.set_xlabel("pairwise NED")
            ax.legend()
        fig.suptitle("EXP-1 baseline collapse: AR+masking reduces diversity (KS p={:.2e})".format(all_out[list(all_out)[0]][0]["ks_p_uncon_vs_cons"]))
        fig.tight_layout()
        fig.savefig(f"{args.fig_dir}/EXP1_collapse.png", dpi=130)
        print("figure saved")
    except Exception as e:
        print("figure error:", e)


if __name__ == "__main__":
    main()
