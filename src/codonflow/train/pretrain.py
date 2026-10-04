"""Pretraining loop for the codon-level edit-flow backbone (Task 2.1.2).

DDP-ready; convergence criterion: validation loss plateau (3 consecutive
epochs with relative drop < 0.1%). Runs until convergence - no fixed cap.
GPU usage is maximized via batch-size auto-tuning to fill memory.
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Dict, List, Optional

import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader, DistributedSampler

from ..data.dataset import CDSDataset, collate_batch, fixed_length_noise_like
from ..models.edit_flow import EditFlowConfig, EditFlowTransformer, edit_flow_loss
from ..core.tokenizer import BOS_ID, EOS_ID, PAD_ID


class ConvergenceTracker:
    """Val-loss plateau: stop when 3 consecutive epochs have relative
    improvement < 0.1% (spec R6-2)."""

    def __init__(self, rel_tol: float = 1e-3, patience: int = 3):
        self.rel_tol = rel_tol
        self.patience = patience
        self.history: List[float] = []
        self._plateau = 0

    def update(self, val_loss: float) -> bool:
        self.history.append(val_loss)
        if len(self.history) >= 2:
            prev = self.history[-2]
            rel = (prev - val_loss) / max(abs(prev), 1e-12)
            if rel < self.rel_tol:
                self._plateau += 1
            else:
                self._plateau = 0
        return self._plateau >= self.patience

    @property
    def converged(self) -> bool:
        return self._plateau >= self.patience


def auto_batch_size(
    model, sample_batch, device, start: int = 8, max_size: int = 512
) -> int:
    """Grow batch size until OOM to fill GPU memory (R6-1)."""
    opt = torch.optim.AdamW(model.parameters(), lr=1e-5)
    batch = 8
    best = batch
    while batch <= max_size:
        try:
            ids = sample_batch["ids"][:batch].to(device)
            pad = sample_batch["pad_mask"][:batch].to(device)
            x0 = fixed_length_noise_like(ids)
            blank, tok = model(x0)
            loss, _, _ = edit_flow_loss(blank, tok, ids, edit_mask=(x0 != ids), pad_mask=pad)
            loss.backward()
            opt.zero_grad(set_to_none=True)
            best = batch
            batch *= 2
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            break
    torch.cuda.empty_cache()
    return best


def train_one_epoch(
    model, loader, optimizer, device, grad_clip: float = 1.0, log_every: int = 200
) -> Dict[str, float]:
    model.train()
    totals = {"loss": 0.0, "blank": 0.0, "token": 0.0, "n": 0}
    t0 = time.time()
    for step, batch in enumerate(loader):
        ids = batch["ids"].to(device, non_blocking=True)
        pad = batch["pad_mask"].to(device, non_blocking=True)
        gen = torch.Generator(device="cpu")
        x0 = fixed_length_noise_like(ids)
        edit_mask = (x0 != ids) & (~pad)
        blank, tok = model(x0, pad)
        loss, b_loss, t_loss = edit_flow_loss(blank, tok, ids, edit_mask, pad)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        optimizer.step()
        bs = ids.size(0)
        totals["loss"] += loss.item() * bs
        totals["blank"] += b_loss.item() * bs
        totals["token"] += t_loss.item() * bs
        totals["n"] += bs
        if log_every and step % log_every == 0:
            print(
                f"step {step}/{len(loader)} loss {totals['loss']/max(totals['n'],1):.4f} "
                f"({time.time()-t0:.0f}s)",
                flush=True,
            )
    n = max(totals["n"], 1)
    return {k: v / n for k, v in totals.items() if k != "n"}


@torch.no_grad()
def validate(model, loader, device) -> float:
    model.eval()
    total, n = 0.0, 0
    for batch in loader:
        ids = batch["ids"].to(device)
        pad = batch["pad_mask"].to(device)
        x0 = fixed_length_noise_like(ids)
        edit_mask = (x0 != ids) & (~pad)
        blank, tok = model(x0, pad)
        loss, _, _ = edit_flow_loss(blank, tok, ids, edit_mask, pad)
        total += loss.item() * ids.size(0)
        n += ids.size(0)
    return total / max(n, 1)


def main(cfg: Dict) -> None:
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    world_size = int(os.environ.get("WORLD_SIZE", 1))
    distributed = world_size > 1
    if distributed:
        dist.init_process_group("nccl")
        torch.cuda.set_device(local_rank)
    device = torch.device("cuda", local_rank) if torch.cuda.is_available() else torch.device("cpu")
    assert torch.cuda.is_available(), "CUDA unavailable - refusing CPU fallback (R6)"

    train_ds = CDSDataset(sequences=cfg["train_sequences"], max_len=cfg.get("max_len", 2002))
    val_ds = CDSDataset(sequences=cfg["val_sequences"], max_len=cfg.get("max_len", 2002))

    model_cfg = EditFlowConfig(
        d_model=cfg.get("d_model", 768),
        n_layers=cfg.get("n_layers", 8),
        n_heads=cfg.get("n_heads", 12),
    )
    model = EditFlowTransformer(model_cfg).to(device)
    if distributed:
        model = DDP(model, device_ids=[local_rank])

    raw_model = model.module if distributed else model

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=cfg.get("lr", 1e-5),
        weight_decay=cfg.get("wd", 0.03),
    )
    total_steps_hint = cfg.get("total_steps_hint", 200_000)
    warmup = cfg.get("warmup_steps", 1000)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lambda s: min(
            (s + 1) / warmup,
            0.5 * (1 + math.cos(math.pi * min(s / max(total_steps_hint, 1), 1.0))),
        )
        * cfg.get("lr", 1e-5)
        / cfg.get("lr", 1e-5)
        + 0.0,
    )

    train_sampler = DistributedSampler(train_ds, shuffle=True) if distributed else None
    val_sampler = DistributedSampler(val_ds, shuffle=False, drop_last=False) if distributed else None

    train_loader = DataLoader(
        train_ds,
        batch_size=cfg.get("batch_size", 64),
        sampler=train_sampler,
        shuffle=train_sampler is None,
        collate_fn=collate_batch,
        num_workers=cfg.get("num_workers", 8),
        pin_memory=True,
        drop_last=True,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=cfg.get("batch_size", 64),
        sampler=val_sampler,
        shuffle=False,
        collate_fn=collate_batch,
        num_workers=4,
        pin_memory=True,
    )

    tracker = ConvergenceTracker(rel_tol=1e-3, patience=3)
    epoch = 0
    out_dir = cfg["out_dir"]
    os.makedirs(out_dir, exist_ok=True)
    while True:
        epoch += 1
        if train_sampler is not None:
            train_sampler.set_epoch(epoch)
        tr = train_one_epoch(model, train_loader, optimizer, device)
        val_loss = validate(model, val_loader, device)
        scheduler.step()
        converged = tracker.update(val_loss)
        if local_rank == 0:
            print(
                f"[epoch {epoch}] train {tr['loss']:.4f} val {val_loss:.4f} "
                f"plateau {tracker._plateau}/3",
                flush=True,
            )
            torch.save(raw_model.state_dict(), os.path.join(out_dir, "last.pt"))
            with open(os.path.join(out_dir, "log.jsonl"), "a") as f:
                f.write(json.dumps({"epoch": epoch, "train": tr, "val": val_loss}) + "\n")
            if converged:
                torch.save(
                    raw_model.state_dict(), os.path.join(out_dir, "converged.pt")
                )
                with open(os.path.join(out_dir, "converged.json"), "w") as f:
                    json.dump(
                        {"epoch": epoch, "val_loss": val_loss,
                         "history": tracker.history}, f, indent=2
                    )
                print("Convergence criterion triggered - stopping.", flush=True)
        if converged:
            break
    if distributed:
        dist.destroy_process_group()


if __name__ == "__main__":
    import argparse

    from ..data.dataset import read_fasta, split_dataset

    ap = argparse.ArgumentParser()
    ap.add_argument("--train-fasta", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--d-model", type=int, default=768)
    ap.add_argument("--n-layers", type=int, default=8)
    ap.add_argument("--n-heads", type=int, default=12)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--max-len", type=int, default=2002)
    args = ap.parse_args()
    seqs = [s for _, s in read_fasta(args.train_fasta)]
    splits = split_dataset(seqs, seed=0)
    cfg = dict(
        train_sequences=splits["train"],
        val_sequences=splits["val"],
        out_dir=args.out_dir,
        batch_size=args.batch_size,
        d_model=args.d_model,
        n_layers=args.n_layers,
        n_heads=args.n_heads,
        lr=args.lr,
        max_len=args.max_len,
    )
    main(cfg)
