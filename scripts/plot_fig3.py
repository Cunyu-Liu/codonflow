"""Plot Fig-3 (EXP-3 preference scan): objective-space scatter, two 2-D
projections, 7 direction clusters, per-cluster non-dominated share."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path("/mnt/cunyuliu/codonflow/eval_outputs/figures")

COLORS = {
    "cai_only": "#d62728",
    "mfe_only": "#1f77b4",
    "gc_only": "#2ca02c",
    "cai_mfe_half": "#ff7f0e",
    "cai_gc_half": "#9467bd",
    "mfe_gc_half": "#8c564b",
    "balanced": "#e377c2",
}


def nd_share(pts):
    pts = np.asarray(pts)
    keep = np.ones(len(pts), dtype=bool)
    for i, p in enumerate(pts):
        for j, q in enumerate(pts):
            if i != j and np.all(q >= p) and np.any(q > p):
                keep[i] = False
                break
    return keep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="/mnt/cunyuliu/codonflow/eval_outputs/E3_preference_scan.json")
    args = ap.parse_args()
    d = json.loads(Path(args.json).read_text())
    fams = list(d.keys())
    fig, axes = plt.subplots(len(fams), 2, figsize=(11, 4.6 * len(fams)))
    if len(fams) == 1:
        axes = [axes]
    for r, fam in enumerate(fams):
        all_pts = []
        for dir_name, m in d[fam].items():
            pts = np.array(m["obj_vectors"])
            all_pts.append((dir_name, pts))
        union = np.vstack([p for _, p in all_pts])
        nd = nd_share(union)
        for c, (xi, yi, xlbl, ylbl) in enumerate(
            [(0, 1, "CAI", "-MFE (kcal/mol)"), (0, 2, "CAI", "-|GC-0.55|")]
        ):
            ax = axes[r][c] if len(fams) > 1 else axes[c]
            for dir_name, pts in all_pts:
                ax.scatter(
                    pts[:, xi], pts[:, yi], s=14, alpha=0.55,
                    color=COLORS.get(dir_name, "gray"), label=dir_name,
                )
            ndp = union[nd]
            ax.scatter(ndp[:, xi], ndp[:, yi], s=42, facecolors="none",
                       edgecolors="k", linewidths=1.2, label="ref front")
            ax.set_xlabel(xlbl)
            ax.set_ylabel(ylbl)
            ax.set_title(f"{fam[:18]}  ({xlbl} vs {ylbl})", fontsize=10)
            if c == 0:
                ax.legend(fontsize=7, ncol=2, loc="best")
    fig.suptitle("EXP-3: preference scan (7 omega directions, beta=8, apply_k=4, 30 sols)")
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "fig3_exp3_preference_scan.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
