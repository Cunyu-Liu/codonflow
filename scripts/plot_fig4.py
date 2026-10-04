"""Plot Fig-4 (EXP-4 ablation) from E4_ablation.json.

Grouped bars: hypervolume per family; overlaid NED line (twin axis).
Frozen figure spec: bars HV, diamonds feasible/identity, line NED.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path("/mnt/cunyuliu/codonflow/eval_outputs/figures")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="/mnt/cunyuliu/codonflow/eval_outputs/E4_ablation.json")
    args = ap.parse_args()
    d = json.loads(Path(args.json).read_text())
    fams = sorted({f for g in d.values() for f in g})
    groups = list(d.keys())
    fig, axes = plt.subplots(1, len(fams), figsize=(0.95 * len(groups) * len(fams), 4.8))
    if len(fams) == 1:
        axes = [axes]
    order = [
        ("pretrain", "pretrain (no RL)"),
        ("v4_reverse_only", "reverse-only"),
        ("v3_gated", "gated rollout"),
        ("v4_direct_only", "direct-only"),
        ("v4_lam025", "lambda=0.25"),
        ("v4_lam075", "lambda=0.75"),
        ("v4_equal", "lambda=0.5 (equal)"),
        ("v2_weak_guide", "v2 weak-guide"),
    ]
    order = [(k, lbl) for k, lbl in order if k in d]
    x = np.arange(len(order))
    for ax, fam in zip(axes, fams):
        hv = [np.mean([d[k][f]["hypervolume"] for f in d[k] if fam in f]) for k, _ in order]
        ned = [np.mean([d[k][f]["ned_mean"] for f in d[k] if fam in f]) for k, _ in order]
        bars = ax.bar(x, hv, color="#4c7fb0", label="hypervolume")
        for xi, v in zip(x, hv):
            ax.text(xi, v + 0.03, f"{v:.2f}", ha="center", fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels([lbl for _, lbl in order], rotation=28, ha="right", fontsize=8)
        ax.set_ylabel("hypervolume")
        ax.set_title(fam[:20])
        ax2 = ax.twinx()
        ax2.plot(x, ned, "ro--", label="NED", markersize=5)
        ax2.set_ylabel("pairwise NED")
        ax2.set_ylim(0, 0.3)
    fig.suptitle("EXP-4: bi-reward ablation (guided decode, 20 sols/group/family)")
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "fig4_exp4_ablation.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
