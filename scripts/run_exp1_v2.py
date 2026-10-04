"""EXP-1 v2: batched AR sampling (fast) for the baseline collapse figure.

Uses GPT2 `generate` in batch mode with per-batch synonymous masking via
custom logits warp. 200 samples per arm per sequence in ~minutes.
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

CKPT = "/home/cunyuliu/mrna_editflow_goal/mrna_editflow/external_tools/codonGPT_hf_ee7017c4"


def load_model(device):
    sys.path.insert(0, CKPT)
    import transformers

    transformers.logging.set_verbosity_error()
    from transformers import GPT2Config, GPT2LMHeadModel

    from tokenizer import CodonTokenizer

    tok = CodonTokenizer.from_pretrained(CKPT)
    cfg = GPT2Config.from_pretrained(CKPT)
    cfg.bos_token_id = None
    cfg.eos_token_id = None
    cfg.vocab_size = 67
    model = GPT2LMHeadModel(config=cfg)
    state = torch.load(f"{CKPT}/pytorch_model.bin", map_location="cpu", weights_only=True)
    state = {k: v for k, v in state.items() if not k.endswith((".attn.bias", ".attn.masked_bias"))}
    missing, unexpected = model.load_state_dict(state, strict=False)
    assert not unexpected
    assert not [k for k in missing if not k.endswith((".attn.bias", ".attn.masked_bias"))]
    model = model.to(device).eval()
    return model, tok


@torch.no_grad()
def batch_sample(model, tok, protein: str, n: int, device, seed: int,
                 constrained: bool, batch: int = 32) -> list:
    bos = tok.convert_tokens_to_ids(["[BOS]"])[0]
    L = len(protein) + 2
    torch.manual_seed(seed)
    outs = []
    aa_seq = protein + "*"
    for start in range(0, n, batch):
        b = min(batch, n - start)
        input_ids = torch.full((b, 1), bos, dtype=torch.long, device=device)
        generated = input_ids
        finished = torch.zeros(b, dtype=torch.bool, device=device)
        seqs = [[] for _ in range(b)]
        for t in range(len(aa_seq)):
            logits = model(input_ids=generated).logits[:, -1].float()
            if constrained:
                aa = aa_seq[t]
                opts = SYNONYMOUS_CODONS.get(aa, ["TAA"])
                opt_ids = tok.convert_tokens_to_ids(opts)
                mask = torch.full_like(logits, float("-inf"))
                mask[:, opt_ids] = 0.0
                logits = logits + mask
            probs = torch.softmax(logits, dim=-1)
            nxt = torch.multinomial(probs, 1)
            for i in range(b):
                if not finished[i]:
                    tok_s = tok.convert_ids_to_tokens(nxt[i].item())
                    if tok_s.startswith("["):
                        finished[i] = True
                    else:
                        seqs[i].append(tok_s)
            generated = torch.cat([generated, nxt], dim=1)
        outs.extend("".join(s) for s in seqs)
    return outs


def sample_ned_distribution(seqs, sample_limit: int = 300, seed: int = 0) -> np.ndarray:
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
    ap.add_argument("--n-samples", type=int, default=200)
    ap.add_argument("--n-seeds", type=int, default=3)
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/EXP1_collapse.json")
    args = ap.parse_args()
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    assert device == "cuda:0", "GPU required"
    rscu = json.loads(Path(args.rscu_json).read_text())
    weights = cai_weights_from_rscu(rscu)
    model, tok = load_model(device)
    from scipy.stats import ks_2samp

    def cai_greedy(protein: str) -> str:
        return "".join(
            max(SYNONYMOUS_CODONS[aa], key=lambda c: weights.get(c, 0.0))
            for aa in protein
        ) + "TAA"

    all_out = {}
    for header, source in read_fasta(args.benchmark_fasta):
        name = header.split()[0]
        protein = protein_of_cds(source)
        per_seed = []
        for seed in range(args.n_seeds):
            uncon = batch_sample(model, tok, protein, args.n_samples, device, seed, False)
            cons = batch_sample(model, tok, protein, args.n_samples, device, seed, True)
            greedy = [cai_greedy(protein)] * 50
            summary = {}
            ned_d = {}
            for arm, seqs in [("unconstrained", uncon), ("constrained", cons), ("cai_greedy", greedy)]:
                prot_ref = translate(source)
                ident = [int(translate(s) == prot_ref) for s in seqs if s]
                ned_d[arm] = sample_ned_distribution(seqs, seed=seed)
                summary[arm] = {
                    "n": len(seqs),
                    "identity_rate": sum(ident) / max(len(seqs), 1),
                    "cai_mean": float(np.mean([cai(s, weights) for s in seqs])),
                    "ned_mean": float(np.mean(ned_d[arm])) if len(ned_d[arm]) else 0.0,
                    "unique_fraction": unique_fraction(seqs),
                    "codon_entropy": codon_entropy_per_aa_position(seqs),
                }
            summary["ks_p_uncon_vs_cons"] = float(
                ks_2samp(ned_d["unconstrained"], ned_d["constrained"]).pvalue
            )
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

        names = list(all_out.keys())
        fig, axes = plt.subplots(1, len(names), figsize=(6 * len(names), 4.5))
        if len(names) == 1:
            axes = [axes]
        for ax, name in zip(axes, names):
            seed_data = all_out[name][0]
            arms = ["unconstrained", "constrained"]
            means = [seed_data[a]["ned_mean"] for a in arms]
            ents = [seed_data[a]["codon_entropy"] for a in arms]
            ax.bar(["AR free", "AR + syn mask"], means, color=["#3b7dd8", "#d86f3b"])
            ax.set_title(f"{name}\nKS p={seed_data['ks_p_uncon_vs_cons']:.2e}")
            ax.set_ylabel("pairwise NED (mean)")
            ax2 = ax.twinx()
            ax2.plot(["AR free", "AR + syn mask"], ents, "go-", label="codon entropy")
            ax2.set_ylabel("codon entropy")
        fig.suptitle("EXP-1: AR+masking diversity collapse (NED & codon entropy)")
        fig.tight_layout()
        fig.savefig("/mnt/cunyuliu/codonflow/eval_outputs/EXP1_collapse.png", dpi=130)
        print("figure saved")
    except Exception as e:
        print("figure error:", e)


if __name__ == "__main__":
    main()
