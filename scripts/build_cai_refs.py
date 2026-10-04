"""CAI reference tables (Task 1.4.1): HPA high-TPM and RefSeq/Ensembl all-CDS.

Computes RSCU over: (a) high-expression human transcripts (HPA TPM filter),
(b) the full cleaned corpus. Writes configs/cai_ref_{hpa,refseq}.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from codonflow.eval.metrics import compute_rscu
from codonflow.data.dataset import read_fasta


def rscu_from_fasta(path: str) -> Dict[str, float]:
    seqs = [s for _, s in read_fasta(path)]
    return compute_rscu(seqs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-fasta", required=True, help="cleaned corpus")
    ap.add_argument("--hpm-fasta", help="optional high-TPM subset fasta")
    ap.add_argument("--out-hpa", default="configs/cai_ref_hpa.json")
    ap.add_argument("--out-refseq", default="configs/cai_ref_refseq.json")
    args = ap.parse_args()
    rscu_full = rscu_from_fasta(args.corpus_fasta)
    Path(args.out_refseq).write_text(json.dumps(rscu_full, indent=2))
    print(f"wrote {args.out_refseq} ({len(rscu_full)} codons)")
    if args.hpm_fasta:
        rscu_hpa = rscu_from_fasta(args.hpm_fasta)
        Path(args.out_hpa).write_text(json.dumps(rscu_hpa, indent=2))
        print(f"wrote {args.out_hpa}")


if __name__ == "__main__":
    main()
