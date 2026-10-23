#!/usr/bin/env python
"""fig11 RLOO 增益条件性图（house style）——v3 vs v3rloo 的 S3 adaptive-ref HV 对照。

主张：在 862k 预训练基座上，RLOO 微调不再带来正向增益（对照 215k 基座上的 v2→RLOO v4 正增益），
即 RL 增益随基座预训练充分度衰减（A4 条件性结论；最终裁决等 17/17 arm）。

数据：S3R2_full_adaptive.json（39 arm per-gene adaptive ref 重算）中
E5_v3_56m_* 与 E5_v3rloo56m_* 的 codonflow/hv 配对。
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PALETTE = {
    "blue_main": "#0F4D92",
    "blue_secondary": "#3775BA",
    "red_strong": "#B64342",
    "teal": "#42949E",
    "violet": "#9A4D8E",
    "neutral": "#CFCECE",
    "green_3": "#8BCF8B",
}

DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("S3R2_full_adaptive.json")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("figures_v2/fig11_rloo_gain")


def apply_style():
    plt.rcParams.update({
        "font.family": ("Helvetica", "Arial", "DejaVu Sans"),
        "font.size": 15,
        "axes.linewidth": 2.0,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "savefig.dpi": 300,
    })


def main():
    apply_style()
    d = json.loads(DATA.read_text())
    pairs = []
    for gene in ("egfp", "nluc", "zfish", "mouse", "fly"):
        for s in (0, 1, 2):
            a = d.get(f"E5_v3_56m_{gene}_s{s}|seed{s}", {}).get("codonflow/hv")
            b = d.get(f"E5_v3rloo56m_{gene}_s{s}|seed{s}", {}).get("codonflow/hv")
            if a is not None and b is not None and a > 0:
                pairs.append((f"{gene}_s{s}", a, b))
    if not pairs:
        print("no pairs found")
        sys.exit(1)

    labels = [p[0] for p in pairs]
    v3 = np.array([p[1] for p in pairs])
    rloo = np.array([p[2] for p in pairs])
    delta = 100 * (rloo - v3) / v3

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))

    # Panel A: paired bars
    ax = axes[0]
    xs = np.arange(len(labels))
    w = 0.38
    ax.bar(xs - w / 2, v3, w, color=PALETTE["blue_main"], edgecolor="black",
           linewidth=1.0, label="v3 base (862k pretrain)")
    ax.bar(xs + w / 2, rloo, w, color=PALETTE["red_strong"], edgecolor="black",
           linewidth=1.0, label="v3 + RLOO")
    ax.set_xticks(xs, labels, rotation=45, ha="right", fontsize=11)
    ax.set_ylabel("S3 hypervolume (adaptive ref)")
    ax.set_title("A  S3 HV: base vs RLOO fine-tuned", loc="left", fontweight="bold")
    ax.legend(fontsize=11)

    # Panel B: delta %
    ax = axes[1]
    colors = [PALETTE["red_strong"] if x < 0 else PALETTE["green_3"] for x in delta]
    ax.bar(xs, delta, 0.6, color=colors, edgecolor="black", linewidth=1.0)
    ax.axhline(0, color="black", lw=1.5)
    ax.set_xticks(xs, labels, rotation=45, ha="right", fontsize=11)
    ax.set_ylabel("Δ HV (RLOO − base, %)")
    n_pos = int((delta > 0).sum())
    ax.set_title(f"B  Δ per arm  ({n_pos}/{len(delta)} positive)", loc="left", fontweight="bold")
    ymin = min(delta.min() * 1.25, -5)
    ymax = max(delta.max() * 1.4, 5)
    ax.set_ylim(ymin, ymax)

    fig.tight_layout(pad=1.2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(f"{OUT}.{ext}", dpi=300, bbox_inches="tight")
    print(f"saved: {OUT}.pdf/.png  | pairs={len(labels)} | mean delta={delta.mean():+.1f}% | "
          f"pos={n_pos}/{len(labels)}")


if __name__ == "__main__":
    main()
