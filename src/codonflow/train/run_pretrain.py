"""Pretraining entry point: token-budget packed batches + MIG/whole-GPU agnostic.

Convergence: stop when val loss plateaus 3 consecutive epochs (< 0.1% relative
drop). Checkpoints to /mnt/cunyuliu/codonflow/checkpoints/.
Usage: python -m codonflow.train.run_pretrain --train-fasta ... --out-dir ...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import torch
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from codonflow.data.dataset import (
    CDSDataset,
    collate_batch,
    fixed_length_noise_like,
    length_bucketed_batches,
    read_fasta,
)
from codonflow.models.edit_flow import (
    EditFlowConfig,
    EditFlowTransformer,
    edit_flow_loss,
)
from codonflow.train.pretrain import ConvergenceTracker, validate


def batch_to_tensors(batch, dev):
    L = max(len(b) for b in batch)
    ids = torch.full((len(batch), L), 64, dtype=torch.long, device=dev)
    pad = torch.ones((len(batch), L), dtype=torch.bool, device=dev)
    for i, b in enumerate(batch):
        ids[i, : len(b)] = torch.tensor(b, dtype=torch.long, device=dev)
        pad[i, : len(b)] = False
    return ids, pad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-fasta", required=True)
    ap.add_argument("--val-fasta", default=None)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--d-model", type=int, default=768)
    ap.add_argument("--n-layers", type=int, default=8)
    ap.add_argument("--n-heads", type=int, default=12)
    ap.add_argument("--dropout", type=float, default=0.0)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--wd", type=float, default=0.03)
    ap.add_argument("--batch-tokens", type=int, default=24000)
    ap.add_argument("--max-batch", type=int, default=128)
    ap.add_argument("--grad-accum", type=int, default=1)
    ap.add_argument("--grad-clip", type=float, default=1.0)
    ap.add_argument("--val-batch-tokens", type=int, default=24000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--epochs-per-checkpoint", type=int, default=1)
    args = ap.parse_args()

    assert torch.cuda.is_available(), "CUDA required - no CPU fallback"
    dev = torch.device("cuda:0")
    torch.manual_seed(args.seed)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_seqs = [s for _, s in read_fasta(args.train_fasta)]
    val_seqs = (
        [s for _, s in read_fasta(args.val_fasta)]
        if args.val_fasta
        else train_seqs[:1000]
    )
    print(f"train={len(train_seqs)} val={len(val_seqs)}", flush=True)

    model_cfg = EditFlowConfig(
        d_model=args.d_model,
        n_layers=args.n_layers,
        n_heads=args.n_heads,
        dropout=args.dropout,
    )
    model = EditFlowTransformer(model_cfg).to(dev)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"model params: {n_params/1e6:.1f}M", flush=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.wd)

    train_batches = length_bucketed_batches(
        train_seqs, batch_tokens=args.batch_tokens, max_batch=args.max_batch, seed=args.seed
    )
    val_batches = length_bucketed_batches(
        val_seqs, batch_tokens=args.val_batch_tokens, max_batch=args.max_batch, seed=123
    )
    print(f"train batches: {len(train_batches)}", flush=True)

    tracker = ConvergenceTracker(rel_tol=1e-3, patience=3)
    epoch = 0
    t_start = time.time()
    from codonflow.data.dataset import corrupt_x_t

    while True:
        epoch += 1
        model.train()
        total_loss = 0.0
        total_tok = 0
        n_updates = 0
        optimizer.zero_grad(set_to_none=True)
        for bi, batch in enumerate(train_batches):
            ids, pad = batch_to_tensors(batch, dev)
            x_t = corrupt_x_t(ids)
            blank, tok = model(x_t, pad)
            loss, _, _ = edit_flow_loss(blank, tok, ids, (x_t != ids), pad)
            (loss / args.grad_accum).backward()
            if (bi + 1) % args.grad_accum == 0 or bi == len(train_batches) - 1:
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                n_updates += 1
            total_loss += loss.item() * ids.numel()
            total_tok += ids.numel()
            if args.log_every and bi % args.log_every == 0:
                elapsed = time.time() - t_start
                print(
                    f"e{epoch} b{bi}/{len(train_batches)} loss {total_loss/max(total_tok,1):.4f} "
                    f"({elapsed/60:.1f}m)",
                    flush=True,
                )
        train_loss = total_loss / max(total_tok, 1)

        model.eval()
        val_loss = validate_packed(model, val_batches, dev)
        cond_gap = conditionality_probe(model, dev)
        converged = tracker.update(val_loss)
        lr_now = optimizer.param_groups[0]["lr"]
        print(
            f"[epoch {epoch}] train {train_loss:.4f} val {val_loss:.4f} "
            f"condgap {cond_gap:.3f} "
            f"lr {lr_now:.2e} plateau {tracker._plateau}/3 elapsed {(time.time()-t_start)/60:.1f}m",
            flush=True,
        )
        with open(out_dir / "log.jsonl", "a") as f:
            f.write(
                json.dumps(
                    {
                        "epoch": epoch,
                        "train_loss": train_loss,
                        "val_loss": val_loss,
                        "cond_gap": cond_gap,
                        "elapsed_min": (time.time() - t_start) / 60,
                    }
                )
                + "\n"
            )
        torch.save(model.state_dict(), out_dir / "last.pt")
        if converged:
            torch.save(model.state_dict(), out_dir / "converged.pt")
            (out_dir / "converged.json").write_text(
                json.dumps({"epoch": epoch, "val_loss": val_loss, "history": tracker.history}, indent=2)
            )
            print("CONVERGENCE CRITERION TRIGGERED - stopping", flush=True)
            break
        if epoch >= 200:
            print("Safety cap 200 epochs reached without plateau - continuing flag off", flush=True)
            break


@torch.no_grad()
def conditionality_probe(model, dev, n=8) -> float:
    """|Δlogp| between two different x_t draws at matched corruption t=0.5.

    v1 degenerate model measured 0.031 nats (predicts the global codon
    frequency table regardless of input). A conditional model must react
    to the surviving evidence in x_t; healthy values grow toward O(1).
    """
    from codonflow.data.dataset import read_fasta
    from codonflow.core.tokenizer import encode_cds

    seqs = []
    for h, s in read_fasta("/mnt/cunyuliu/codonflow/corpora/bench.fasta"):
        seqs.append(encode_cds(s))
    seqs = seqs[:n]
    L = max(len(s) for s in seqs)
    ids = torch.full((len(seqs), L), 64, dtype=torch.long, device=dev)
    for i, s in enumerate(seqs):
        ids[i, : len(s)] = torch.tensor(s, dtype=torch.long, device=dev)
    pad = torch.ones_like(ids, dtype=torch.bool)
    for i, s in enumerate(seqs):
        pad[i, : len(s)] = False
    t_half = torch.full((len(seqs),), 0.5, device=dev)
    g1, g2 = torch.Generator().manual_seed(1), torch.Generator().manual_seed(2)
    from codonflow.data.dataset import corrupt_x_t

    x_a = corrupt_x_t(ids, t_half, g1)
    x_b = corrupt_x_t(ids, t_half, g2)
    _, tok_a = model(x_a, pad)
    _, tok_b = model(x_b, pad)
    la = torch.log_softmax(tok_a.float(), -1)
    lb = torch.log_softmax(tok_b.float(), -1)
    return float((la - lb).abs().mean().item())


@torch.no_grad()
def validate_packed(model, batches, dev) -> float:
    total, n = 0.0, 0
    from codonflow.data.dataset import corrupt_x_t

    for batch in batches:
        ids, pad = batch_to_tensors(batch, dev)
        x_t = corrupt_x_t(ids)
        blank, tok = model(x_t, pad)
        loss, _, _ = edit_flow_loss(blank, tok, ids, (x_t != ids), pad)
        total += loss.item()
        n += 1
    return total / max(n, 1)


if __name__ == "__main__":
    main()
