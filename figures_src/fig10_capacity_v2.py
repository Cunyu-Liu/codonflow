#!/usr/bin/env python
"""fig10 容量曲线（house style 重制版）——数据点来自集群 figures_src/data/capacity_curves.json。

主张：固定 56M 架构下 4x 数据只带来边际损失下降（饱和）；355M 容量档打开新的损失水平。
输出：figures_v2/fig10_capacity.pdf + png（300dpi）。
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
    "highlight": "#FFD700",
}

DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("capacity_curves.json")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("figures_v2/fig10_capacity")


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


def load_curves():
    d = json.loads(DATA.read_text())
    curves = {}
    for key, val in d.items():
        if isinstance(val, dict):
            ep = val.get("epochs") or val.get("epoch")
            vl = val.get("val_loss") or val.get("vals") or val.get("val")
            if ep and vl:
                curves[key] = (list(ep), list(vl))
        elif isinstance(val, list):
            # 纯数值序列：epoch 从 1 开始
            nums = [v for v in val if isinstance(v, (int, float))]
            if nums:
                curves[key] = (list(range(1, len(nums) + 1)), nums)
    return curves


def main():
    apply_style()
    curves = load_curves()
    if not curves:
        print("No usable curves found in", DATA)
        print(json.dumps(json.loads(DATA.read_text()), indent=1)[:800])
        sys.exit(1)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))

    style_map = {
        "56m": dict(color=PALETTE["blue_main"], marker="o", lw=2.6),
        "355m": dict(color=PALETTE["red_strong"], marker="s", lw=2.6),
    }

    # Panel A: val loss vs epoch
    ax = axes[0]
    for key, (ep, vl) in sorted(curves.items()):
        kw = next((v for k, v in style_map.items() if k in key.lower()),
                  dict(color=PALETTE["teal"], marker="^", lw=2.2))
        label = key.replace("_", " ")
        ax.plot(ep, vl, ms=6, alpha=0.95, label=label, **kw)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Validation loss (nats/codon)")
    ax.set_title("A  Pretraining convergence", loc="left", fontweight="bold")
    ax.legend(fontsize=11)

    # Panel B: 容量-数据汇总（各曲线最优 val loss vs 参数量/语料）
    ax = axes[1]
    rows = []
    for key, (ep, vl) in curves.items():
        best = min(vl)
        n_par = 355 if "355" in key else 56
        corpus = 862 if key.lower().startswith("v3") or "v3" in key else 215
        rows.append((key, n_par, corpus, best))
    if rows:
        xs = np.arange(len(rows))
        colors = [PALETTE["red_strong"] if r[1] == 355 else PALETTE["blue_main"] for r in rows]
        bars = ax.bar(xs, [r[3] for r in rows], width=0.62, color=colors,
                      edgecolor="black", linewidth=1.2)
        for x, r in zip(xs, rows):
            ax.text(x, r[3] + 0.004, f"{r[3]:.4f}", ha="center", fontsize=12, fontweight="bold")
        labels = [f"{r[1]}M\n@{r[2]}k" for r in rows]
        ax.set_xticks(xs, labels, fontsize=12)
        ax.set_ylim(min(r[3] for r in rows) - 0.015, max(r[3] for r in rows) + 0.015)
        ax.set_ylabel("Best validation loss")
        ax.set_title("B  Capacity × corpus", loc="left", fontweight="bold")

    fig.tight_layout(pad=1.2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(f"{OUT}.{ext}", dpi=300, bbox_inches="tight")
    print("saved:", OUT.with_suffix(".pdf"), OUT.with_suffix(".png"))


if __name__ == "__main__":
    main()
