"""CDS dataset: loads cleaned codon corpora from FASTA into padded batches."""
from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

import torch

from ..core.tokenizer import BOS_ID, EOS_ID, PAD_ID, VOCAB_SIZE, encode_cds
from ..core.codon import is_valid_cds, normalize_to_dna


def read_fasta(path: str) -> Iterator[tuple]:
    """Yield (header, sequence) pairs from a FASTA file."""
    header = None
    chunks: List[str] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(chunks)
                header = line[1:]
                chunks = []
            else:
                chunks.append(line)
    if header is not None:
        yield header, "".join(chunks)


def fasta_sha256(path: str, block_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(block_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


@dataclass
class CDSDataset(torch.utils.data.Dataset):
    sequences: List[str]
    max_len: int = 2002
    drop_invalid: bool = True

    def __post_init__(self):
        if self.drop_invalid:
            self.sequences = [
                s for s in self.sequences if self._quick_ok(s)
            ]
        self._ids = [self._encode(s) for s in self.sequences]

    def _quick_ok(self, s: str) -> bool:
        d = normalize_to_dna(s)
        return (
            len(d) % 3 == 0
            and len(d) >= 300
            and len(d) <= 6000
            and all(c in "ACGT" for c in d)
        )

    def _encode(self, s: str) -> List[int]:
        ids = encode_cds(s)
        return ids[: self.max_len]

    def __len__(self) -> int:
        return len(self._ids)

    def __getitem__(self, idx: int) -> List[int]:
        return self._ids[idx]

    def corpus_sha(self) -> str:
        h = hashlib.sha256()
        for s in self.sequences:
            h.update(normalize_to_dna(s).encode())
        return h.hexdigest()[:8]


def collate_batch(batch: Sequence[List[int]]) -> Dict[str, torch.Tensor]:
    """Pad to batch max; returns ids and pad_mask (True = padded)."""
    L = max(len(b) for b in batch)
    ids = torch.full((len(batch), L), PAD_ID, dtype=torch.long)
    pad_mask = torch.ones((len(batch), L), dtype=torch.bool)
    for i, b in enumerate(batch):
        ids[i, : len(b)] = torch.tensor(b, dtype=torch.long)
        pad_mask[i, : len(b)] = False
    return {"ids": ids, "pad_mask": pad_mask}


def fixed_length_noise_like(
    ids: torch.Tensor, generator: Optional[torch.Generator] = None
) -> torch.Tensor:
    """x_0: uniform random codons (keep special tokens fixed)."""
    rand = torch.randint(0, VOCAB_SIZE, ids.shape, generator=generator)
    out = ids.clone()
    body = (ids != PAD_ID) & (ids != BOS_ID) & (ids != EOS_ID)
    out[body] = rand[body]
    return out


def x0_random_from_amino_acids(
    target_ids: torch.Tensor, generator: Optional[torch.Generator] = None
) -> torch.Tensor:
    """x_0 with synonymous-codon noise: keeps the protein identity plausible
    for warm starts (optional; default is uniform noise)."""
    return fixed_length_noise_like(target_ids, generator)


def split_dataset(
    sequences: List[str],
    train_frac: float = 0.8,
    val_frac: float = 0.1,
    seed: int = 0,
) -> Dict[str, List[str]]:
    rng = random.Random(seed)
    seqs = list(sequences)
    rng.shuffle(seqs)
    n = len(seqs)
    n_train = int(n * train_frac)
    n_val = int(n * val_frac)
    return {
        "train": seqs[:n_train],
        "val": seqs[n_train : n_train + n_val],
        "test": seqs[n_train + n_val :],
    }
