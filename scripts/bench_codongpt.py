"""codonGPT baseline: official HF checkpoint + synonymous logit masking (Task 1.2.1).

Uses the cached official checkpoint (naniltx/codonGPT @ ee7017c4, SHA
recorded). Claim discipline: 'constrained generation with the official
pretrained checkpoint' - we do NOT claim to reproduce the paper's RL.
Generates N constrained samples per benchmark CDS, reports
CAI/MFE/identity/NED/entropy (E1 baseline table + EXP-1).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

CKPT_DIR = "/home/cunyuliu/mrna_editflow_goal/mrna_editflow/external_tools/codonGPT_hf_ee7017c4"

from codonflow.core.codon import (
    SYNONYMOUS_CODONS,
    protein_of_cds,
    split_codons,
    translate,
    normalize_to_dna,
    is_valid_cds,
)
from codonflow.eval.metrics import (
    cai,
    cai_weights_from_rscu,
    mfe_batch,
    pairwise_ned,
    unique_fraction,
    codon_entropy_per_aa_position,
)


def load_codongpt():
    sys.path.insert(0, CKPT_DIR)
    from transformers import GPT2LMHeadModel

    from tokenizer import CodonTokenizer

    tokenizer = CodonTokenizer.from_pretrained(CKPT_DIR)
    model = GPT2LMHeadModel.from_pretrained(CKPT_DIR)
    model.eval()
    return model, tokenizer


def sha256_of_ckpt() -> str:
    import hashlib

    h = hashlib.sha256()
    with open(f"{CKPT_DIR}/pytorch_model.bin", "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


@torch.no_grad()
def constrained_sample(model, tokenizer, protein: str, n_samples: int,
                       device: str = "cuda:0", seed: int = 0, temperature: float = 1.0):
    """Per-position sampling with synonymous masking (codonGPT mechanism)."""
    torch.manual_seed(seed)
    samples = []
    bos = tokenizer.convert_tokens_to_ids(["[BOS]"])[0]
    eos = tokenizer.convert_tokens_to_ids(["[EOS]"])[0]
    for _ in range(n_samples):
        input_ids = torch.tensor([[bos]], device=device)
        codons = []
        for aa in protein + "*":
            opts = SYNONYMOUS_CODONS.get(aa, ["TAA"])
            opt_ids = tokenizer.convert_tokens_to_ids(opts)
            logits = model(input_ids=input_ids).logits[0, -1].float()
            mask = torch.full_like(logits, float("-inf"))
            mask[opt_ids] = 0.0
            logits = logits + mask
            probs = torch.softmax(logits / temperature, dim=-1)
            next_id = torch.multinomial(probs, 1).item()
            codons.append(tokenizer.convert_ids_to_tokens(next_id))
            input_ids = torch.cat(
                [input_ids, torch.tensor([[next_id]], device=device)], dim=1
            )
        seq = "".join(c for c in codons if not c.startswith("["))
        samples.append(seq)
    return samples


def summarize(samples, source_cds, weights):
    prot_src = translate(source_cds)
    legal = [int(is_valid_cds(s)) for s in samples]
    ident = [int(translate(s) == prot_src) for s in samples]
    cais = [cai(s, weights) for s in samples]
    mfes = mfe_batch(samples)
    return {
        "n": len(samples),
        "legal_rate": sum(legal) / len(samples),
        "identity_rate": sum(ident) / len(samples),
        "cai_mean": sum(cais) / len(cais),
        "cai_std": (sum((c - sum(cais) / len(cais)) ** 2 for c in cais) / len(cais)) ** 0.5,
        "mfe_mean": sum(mfes) / len(mfes),
        "ned_mean": pairwise_ned(samples),
        "unique_fraction": unique_fraction(samples),
        "codon_entropy": codon_entropy_per_aa_position(samples),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--n-samples", type=int, default=100)
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/E1_codongpt.json")
    args = ap.parse_args()
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    assert device == "cuda:0", "GPU required (R6)"
    rscu = json.loads(Path(args.rscu_json).read_text())
    weights = cai_weights_from_rscu(rscu)
    model, tokenizer = load_codongpt()
    model = model.to(device)
    ckpt_sha = sha256_of_ckpt()
    print(f"checkpoint SHA-256 prefix: {ckpt_sha}", flush=True)
    from codonflow.data.dataset import read_fasta

    results = []
    for header, cds in read_fasta(args.benchmark_fasta):
        name = header.split()[0]
        protein = protein_of_cds(cds)
        t0 = time.time()
        samples = constrained_sample(
            model, tokenizer, protein, args.n_samples, device, seed=args.seed,
            temperature=args.temperature,
        )
        elapsed = time.time() - t0
        entry = {
            "name": name,
            "n_aa": len(protein),
            "n_samples": args.n_samples,
            "elapsed_total_s": round(elapsed, 1),
            "per_sample_s": round(elapsed / args.n_samples, 3),
            "temperature": args.temperature,
            "summary": summarize(samples, cds, weights),
            "samples_head": samples[:3],
        }
        results.append(entry)
        print(json.dumps(entry, indent=2), flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps({"ckpt_sha": ckpt_sha, "results": results}, indent=2)
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
