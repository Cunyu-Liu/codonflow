"""Distribution audit (Task 1.1.3): length/GC/CAI/RSCU four-dimension plots.

Writes PNG plots + a JSON summary into docs/data_audit/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import gc_fraction
from codonflow.eval.metrics import (
    cai,
    cai_weights_from_rscu,
    compute_rscu,
    mfe_batch,
)
from codonflow.data.dataset import read_fasta


def audit(fasta: str, cai_weights, tag: str, out_dir: str, n_mfe: int = 400) -> Dict:
    lens, gcs, cais = [], [], []
    rscu_seqs = []
    for i, (h, s) in enumerate(read_fasta(fasta)):
        lens.append(len(s))
        gcs.append(gc_fraction(s))
        if i < 50000:
            cais.append(cai(s, cai_weights))
            rscu_seqs.append(s)
    rscu = compute_rscu(rscu_seqs)
    rng = np.random.default_rng(0)
    mfe_sample_idx = rng.choice(len(rscu_seqs), size=min(n_mfe, len(rscu_seqs)), replace=False)
    mfes = mfe_batch([rscu_seqs[i] for i in mfe_sample_idx])
    summary = {
        "tag": tag,
        "n": len(lens),
        "length": {
            "mean": float(np.mean(lens)),
            "std": float(np.std(lens)),
            "q5": float(np.percentile(lens, 5)),
            "q50": float(np.percentile(lens, 50)),
            "q95": float(np.percentile(lens, 95)),
        },
        "gc": {
            "mean": float(np.mean(gcs)),
            "std": float(np.std(gcs)),
            "q5": float(np.percentile(gcs, 5)),
            "q95": float(np.percentile(gcs, 95)),
        },
        "cai": {
            "mean": float(np.mean(cais)),
            "std": float(np.std(cais)),
            "q5": float(np.percentile(cais, 5)),
            "q95": float(np.percentile(cais, 95)),
        },
        "mfe_sample": {
            "mean": float(np.mean(mfes)),
            "q5": float(np.percentile(mfes, 5)),
            "q95": float(np.percentile(mfes, 95)),
        },
        "rscu_top": dict(sorted(rscu.items(), key=lambda kv: -kv[1])[:10]),
        "rscu_bottom": dict(sorted(rscu.items(), key=lambda kv: kv[1])[:10]),
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(11, 8))
        axes[0, 0].hist(lens, bins=80, color="#3b7dd8")
        axes[0, 0].set_title(f"{tag} length (nt)")
        axes[0, 1].hist(gcs, bins=60, color="#d86f3b")
        axes[0, 1].set_title(f"{tag} GC")
        axes[1, 0].hist(cais, bins=60, color="#3bd87a")
        axes[1, 0].set_title(f"{tag} CAI")
        axes[1, 1].hist(mfes, bins=40, color="#8a3bd8")
        axes[1, 1].set_title(f"{tag} MFE (sample {len(mfes)})")
        for ax in axes.flat:
            ax.set_yscale("log")
        fig.tight_layout()
        fig.savefig(out / f"audit_{tag}.png", dpi=120)
        plt.close(fig)
    except Exception as e:
        summary["plot_error"] = str(e)
    (out / f"audit_{tag}.json").write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fasta", required=True)
    ap.add_argument("--rscu-json", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out-dir", default="docs/data_audit")
    args = ap.parse_args()
    rscu = json.loads(Path(args.rscu_json).read_text())
    weights = cai_weights_from_rscu(rscu)
    s = audit(args.fasta, weights, args.tag, args.out_dir)
    print(json.dumps(s, indent=2))
