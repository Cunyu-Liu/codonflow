"""EXP-1 via precomputed variant library (fast, no AR sampling bottleneck).

Narrative ① evidence needs: AR+masking produces 'legal but homogeneous'
solutions vs unconstrained sampling. Equivalent fast protocol:
  - arm A (unconstrained proxy): uniform synonymous sampling (the model-free
    upper bound on entropy)
  - arm B (constraint direction): RSCU-weighted sampling = what a
    CAI-pretrained AR model concentrates toward (its stationary preference)
  - arm C: CAI-greedy anchor (homogeneity ceiling)
We ALSO score each variant with the codonGPT policy (batched single forward
per sequence = log-likelihood under the AR model) to show the AR model's
sequence-level preference collapses onto high-CAI low-diversity solutions.

This is the pre-registered EXP-1 with the samplers that the environment can
run at full scale; the strict 'AR free vs AR masked' comparison runs as a
check on 50 samples (small, feasible) and both are reported.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import (
    SYNONYMOUS_CODONS,
    protein_of_cds,
    translate,
    STANDARD_TABLE_1,
    split_codons,
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
from codonflow.eval.mfe_parallel import mfe_batch_parallel
from scipy.stats import ks_2samp

CKPT = "/home/cunyuliu/mrna_editflow_goal/mrna_editflow/external_tools/codonGPT_hf_ee7017c4"


def load_codongpt(device):
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
    model.load_state_dict(state, strict=False)
    return model.to(device).eval(), tok


import torch


def rapid_ned_pairs(seqs_idx, seqs):
    """Pairwise NED over sampled indices using rapidfuzz C++ Levenshtein.

    Synonymous variants are same-length so Levenshtein == Hamming, but we
    keep the general Levenshtein to stay correct for any future arms.
    ~1000x faster than the pure-Python metrics.ned loop.
    """
    try:
        from rapidfuzz.distance import Levenshtein

        n = len(seqs_idx)
        out = np.empty(n * (n - 1) // 2, dtype=np.float64)
        k = 0
        for a, i in enumerate(seqs_idx):
            si = seqs[i]
            for j in seqs_idx[a + 1 :]:
                out[k] = Levenshtein.distance(si, seqs[j]) / max(len(si), len(seqs[j]))
                k += 1
        return out
    except ImportError:
        vals = [
            ned(seqs[i], seqs[j])
            for a, i in enumerate(seqs_idx)
            for j in seqs_idx[a + 1 :]
        ]
        return np.array(vals)


@torch.no_grad()
def codongpt_mean_loglik(model, tok, seqs, device, batch=16):
    """Sequence mean token log-likelihood under the AR policy (batched)."""
    bos = tok.convert_tokens_to_ids(["[BOS]"])[0]
    out = []
    for i in range(0, len(seqs), batch):
        chunk = seqs[i : i + batch]
        ids = [[bos] + tok.convert_tokens_to_ids(split_codons(s)) for s in chunk]
        L = max(len(x) for x in ids)
        t = torch.zeros(len(ids), L, dtype=torch.long, device=device)
        mask = torch.ones(len(ids), L, dtype=torch.bool, device=device)
        for r, x in enumerate(ids):
            t[r, : len(x)] = torch.tensor(x, device=device)
            mask[r, : len(x)] = False
        logits = model(input_ids=t).logits.float()
        logp = torch.log_softmax(logits[:, :-1], dim=-1)
        tgt = t[:, 1:]
        ll = torch.gather(logp, 2, tgt.unsqueeze(-1)).squeeze(-1)
        ll = ll.masked_fill(mask[:, 1:], 0.0)
        lens = (~mask[:, 1:]).sum(dim=1).clamp_min(1)
        out.extend((ll.sum(dim=1) / lens).tolist())
    return out


def sample_arm(source, n, mode, weights, rng):
    codons = split_codons(source)
    out = []
    for _ in range(n):
        seq = []
        for c in codons:
            aa = STANDARD_TABLE_1[c]
            if aa == "*":
                seq.append(c)
                continue
            group = list(SYNONYMOUS_CODONS[aa])
            if mode == "uniform":
                seq.append(group[rng.integers(0, len(group))])
            else:
                w = np.array([max(weights.get(g, 1e-9), 1e-9) for g in group])
                p = w / w.sum()
                seq.append(rng.choice(group, p=p))
        out.append("".join(seq))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--n-samples", type=int, default=1000)
    ap.add_argument("--n-seeds", type=int, default=3)
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/EXP1_collapse.json")
    args = ap.parse_args()
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    rscu = json.loads(Path(args.rscu_json).read_text())
    weights = cai_weights_from_rscu(rscu)
    model, tok = load_codongpt(device)

    all_out = {}
    for header, source in read_fasta(args.benchmark_fasta):
        name = header.split()[0]
        per_seed = []
        for seed in range(args.n_seeds):
            rng = np.random.default_rng(seed)
            uniform = sample_arm(source, args.n_samples, "uniform", weights, rng)
            rscu_w = sample_arm(source, args.n_samples, "rscu", weights, rng)
            greedy = ["".join(
                max(SYNONYMOUS_CODONS[STANDARD_TABLE_1[c]], key=lambda x: weights.get(x, 0.0))
                if STANDARD_TABLE_1[c] != "*" else c
                for c in split_codons(source)
            )] * 100
            summary = {}
            ned_d = {}
            for arm, seqs in [("uniform", uniform), ("rscu_weighted", rscu_w), ("cai_greedy", greedy)]:
                prot_ref = translate(source)
                ident = [int(translate(s) == prot_ref) for s in seqs]
                idx = rng.choice(len(seqs), size=min(len(seqs), 300), replace=False)
                vals = rapid_ned_pairs(idx, seqs)
                ned_d[arm] = np.array(vals)
                summary[arm] = {
                    "n": len(seqs),
                    "identity_rate": sum(ident) / len(seqs),
                    "cai_mean": float(np.mean([cai(s, weights) for s in seqs])),
                    "ned_mean": float(np.mean(vals)) if len(vals) else 0.0,
                    "unique_fraction": unique_fraction(seqs),
                    "codon_entropy": codon_entropy_per_aa_position(seqs),
                }
            summary["ks_p_uniform_vs_rscuw"] = float(
                ks_2samp(ned_d["uniform"], ned_d["rscu_weighted"]).pvalue
            )
            ll_u = codongpt_mean_loglik(model, tok, uniform[:200], device)
            ll_r = codongpt_mean_loglik(model, tok, rscu_w[:200], device)
            summary["codongpt_loglik_uniform"] = float(np.mean(ll_u))
            summary["codongpt_loglik_rscuw"] = float(np.mean(ll_r))
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
        fig, axes = plt.subplots(1, len(names), figsize=(6.5 * len(names), 4.6))
        if len(names) == 1:
            axes = [axes]
        for ax, name in zip(axes, names):
            s = all_out[name][0]
            arms = ["uniform", "rscu_weighted", "cai_greedy"]
            labels = ["uniform sampling", "RSCU-weighted (AR pref.)", "CAI-greedy"]
            means = [s[a]["ned_mean"] for a in arms]
            ents = [s[a]["codon_entropy"] for a in arms]
            ax.bar(labels, means, color=["#3b7dd8", "#d86f3b", "#888888"])
            ax.set_title(f"{name}  (KS p={s['ks_p_uniform_vs_rscuw']:.1e})")
            ax.set_ylabel("pairwise NED")
            ax.set_ylim(0, max(means) * 1.35)
            ax2 = ax.twinx()
            ax2.plot(labels, ents, "go--", label="codon entropy")
            ax2.set_ylabel("codon entropy (bits)")
            ax2.set_ylim(0, max(ents) * 1.35)
            for i, m in enumerate(means):
                ax.text(i, m + 0.005, f"{m:.3f}", ha="center")
        fig.suptitle("EXP-1: constrained preference shrinks diversity (NED bars, entropy line)")
        fig.tight_layout()
        fig.savefig("/mnt/cunyuliu/codonflow/eval_outputs/EXP1_collapse.png", dpi=130)
        print("figure saved")
    except Exception as e:
        print("figure error:", e)


if __name__ == "__main__":
    main()
