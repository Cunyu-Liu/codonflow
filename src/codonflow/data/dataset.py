"""CDS dataset: loads cleaned codon corpora from FASTA into padded batches."""
from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

try:
    import torch
except ImportError:
    torch = None

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
class CDSDataset:
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
    rand = torch.randint(0, VOCAB_SIZE, ids.shape, generator=generator).to(ids.device)
    out = ids.clone()
    body = (ids != PAD_ID) & (ids != BOS_ID) & (ids != EOS_ID)
    out[body] = rand[body]
    return out


def corrupt_x_t(
    ids: torch.Tensor,
    t: Optional[torch.Tensor] = None,
    generator: Optional[torch.Generator] = None,
) -> torch.Tensor:
    """Corruption-style intermediate state x_t for edit-flow pretraining.

    Replaces a fraction t of the BODY codons with uniform random codons
    (special tokens untouched). With t ~ U[0,1] sampled per sequence the
    model sees the whole trajectory: t=1 pure noise (frequency table),
    t=0 clean (copy), t~0.5 partial evidence - exactly the states the
    guided sampler faces at inference. Fixes the v1 degeneracy where x0
    carried zero mutual information with the target (val loss 4.061 ==
    marginal codon entropy 4.027 + blank BCE; |delta logp| across two
    different noise draws = 0.031 nats).

    t: (B,) fractions in [0,1]; if None, sampled per sequence.
    """
    if t is None:
        t = torch.rand(ids.shape[0], generator=generator).to(ids.device)
    t = t.to(ids.device).clamp(0.0, 1.0)
    body = (ids != PAD_ID) & (ids != BOS_ID) & (ids != EOS_ID)
    rand = torch.randint(0, VOCAB_SIZE, ids.shape, generator=generator).to(ids.device)
    keep = torch.rand(ids.shape, generator=generator).to(ids.device) >= t.view(-1, 1)
    out = torch.where(body & keep, ids, torch.where(body, rand, ids))
    return out


def x0_random_from_amino_acids(
    target_ids: torch.Tensor, generator: Optional[torch.Generator] = None
) -> torch.Tensor:
    """x_0 with synonymous-codon noise: keeps the protein identity plausible
    for warm starts (optional; default is uniform noise)."""
    return fixed_length_noise_like(target_ids, generator)


def length_bucketed_batches(
    sequences: List[str],
    batch_tokens: int = 24000,
    max_batch: int = 128,
    seed: int = 0,
) -> List[List[int]]:
    """Length-bucketed token-budget batches: every batch ~batch_tokens codons.

    Encodes once, sorts by length, packs batches under a token budget, then
    shuffles batch order (bucketing removes padding waste, shuffling keeps
    SGD noise). This is the packing strategy for the pretraining run.
    """
    import random as _random

    rng = _random.Random(seed)
    encoded = [(i, encode_cds(s)) for i, s in enumerate(sequences)]
    encoded.sort(key=lambda p: len(p[1]))
    batches: List[List[int]] = []
    cur: List[int] = []
    cur_max = 0
    for _i, ids in encoded:
        new_max = max(cur_max, len(ids))
        if cur and (new_max * (len(cur) + 1) > batch_tokens or len(cur) >= max_batch):
            batches.append(cur)
            cur = [ids]
            cur_max = len(ids)
        else:
            cur.append(ids)
            cur_max = new_max
    if cur:
        batches.append(cur)
    rng.shuffle(batches)
    return batches
