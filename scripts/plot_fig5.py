"""Plot Fig-5 (EXP-5 main table): per-scenario HV comparison across 5 methods.

Frozen spec: grouped bars per family/scenario, methods on x; HV bars +
NED line overlay; non-dominated share annotated.
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

METHODS = [
    ("codonflow", "CodonFlow"),
    ("codongpt", "codonGPT"),
    ("lineardesign_scan", "LinearDesign-scan"),
    ("cai_greedy", "CAI-greedy"),
    ("uniform_edit_flow", "uniform EF"),
]
SCENS = ["S1_cai", "S2_cai_mfe", "S3_quad"]
SCEN_LBL = {"S1_cai": "S1: CAI", "S2_cai_mfe": "S2: CAI+MFE", "S3_quad": "S3: quad"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="/mnt/cunyuliu/codonflow/eval_outputs/E5_main_table.json")
    args = ap.parse_args()
    d = json.loads(Path(args.json).read_text())
    fams = list(d.keys())
    fig, axes = plt.subplots(
        len(fams), len(SCENS), figsize=(4.6 * len(SCENS), 3.6 * len(fams))
    )
    if len(fams) == 1:
        axes = [axes]
    x = np.arange(len(METHODS))
    for r, fam in enumerate(fams):
        seeds = d[fam]
        for c, scen in enumerate(SCENS):
            ax = axes[r][c] if len(fams) > 1 else axes[c]
            hv = [
                np.mean([s[f"{scen}/{m}/hv"] for s in seeds]) for m, _ in METHODS
            ]
            hv_std = [
                np.std([s[f"{scen}/{m}/hv"] for s in seeds]) for m, _ in METHODS
            ]
            ned = [
                np.mean([s[f"{scen}/{m}/ned"] for s in seeds]) for m, _ in METHODS
            ]
            ax.bar(x, hv, yerr=hv_std, color=["#2a9d8f", "#e9c46a", "#4c7fb0", "#888888", "#b5838d"], capsize=3)
            ax.set_xticks(x)
            ax.set_xticklabels([lbl for _, lbl in METHODS], rotation=18, ha="right", fontsize=8)
            ax.set_ylabel("hypervolume")
            ax.set_title(f"{fam[:16]} {SCEN_LBL[scen]}", fontsize=10)
            ax2 = ax.twinx()
            ax2.plot(x, ned, "ko:", markersize=4, alpha=0.7)
            ax2.set_ylabel("NED", fontsize=8)
            ax2.set_ylim(0, 0.35)
            for xi, v in zip(x, hv):
                if v > 0:
                    ax.text(xi, v + 0.02 * max(hv), f"{v:.1f}", ha="center", fontsize=7)
    fig.suptitle("EXP-5: five methods x three scenarios (30 sols/seed, 3 seeds)")
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "fig5_exp5_main.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
