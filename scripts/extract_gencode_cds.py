"""Extract CDS regions from GENCODE transcripts FASTA (Task 1.1.1).

GENCODE headers carry CDS coordinates: ...|CDS:61-1041|...
Extract the CDS substring (1-based inclusive) and keep transcript id.
"""
from __future__ import annotations

import argparse
import gzip
import re
from pathlib import Path
from typing import Iterator, Tuple

CDS_RE = re.compile(r"CDS:(\d+)-(\d+)")


def iter_fasta(path: str) -> Iterator[Tuple[str, str]]:
    opener = gzip.open if path.endswith(".gz") else open
    header = None
    chunks = []
    with opener(path, "rt") as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(chunks)
                header = line[1:]
                chunks = []
            else:
                chunks.append(line)
    if header is not None:
        yield header, "".join(chunks)


def extract_cds(header: str, seq: str) -> Tuple[str, str]:
    m = CDS_RE.search(header)
    tid = header.split("|")[0]
    if not m:
        return "", ""
    start, end = int(m.group(1)), int(m.group(2))
    cds = seq[start - 1 : end]
    return tid, cds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gencode-fasta", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    n_total = 0
    n_cds = 0
    with open(args.out, "w") as out:
        for header, seq in iter_fasta(args.gencode_fasta):
            n_total += 1
            tid, cds = extract_cds(header, seq)
            if cds and len(cds) >= 3:
                n_cds += 1
                out.write(f">{tid}\n{cds}\n")
    print(f"transcripts={n_total} cds_extracted={n_cds} -> {args.out}")


if __name__ == "__main__":
    main()
