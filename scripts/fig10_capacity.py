"""fig10: capacity/data-scaling curves for CodonFlow pretraining (offset small-multiples).

Borrowed parts (plot-is-all-you-need gallery `plos-cc0-offset-series`):
  structure layout  <- offset rows sharing one x-axis; grey reference band = converged v2 loss plateau
  color             <- black curves + light-grey band; one red accent marker for the parity point
  text & annotation <- series name written at line start/end; direct value labels, no legend box
  decoration        <- thin ticks, no outer frame, no color legend
Data: data/capacity_curves.json (cluster log.jsonl / converged.json, 3x cross-checked).
Output: fig10_capacity.png (300 dpi) + fig10_capacity.pdf
"""
import json
from pathlib import Path
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
D = json.load(open(HERE / "data" / "capacity_curves.json"))

v1 = D["v1_mask_56M_215k"]
v2 = D["v2_corrupt_56M_215k"]
v3_56 = D["v3_56M_862k"]
v3_355 = D["v3_355M_862k"]

V2_PLATEAU = 2.814  # converged value of v2 (18 epochs)
BAND = 0.010        # +- band width around plateau

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "Noto Serif CJK SC"],
    "font.size": 8.4, "pdf.fonttype": 42, "axes.linewidth": 0.9,
    "axes.edgecolor": "#3a3a3a", "xtick.color": "#3a3a3a", "ytick.color": "#3a3a3a",
})

series = [
    ("v1 masking · 56M · 215k", v1, "#8a8a8a", 1.15),
    ("v2 corruption · 56M · 215k", v2, "#1b2a5c", 0.30),
    ("v3 corruption · 56M · 862k", v3_56, "#2a7f62", 0.12),
    ("v3 corruption · 355M · 862k", v3_355, "#d1242f", 0.0),
]

fig, ax = plt.subplots(figsize=(7.0, 4.4))

# shared reference band: v2 converged plateau
ax.axhspan(V2_PLATEAU - BAND, V2_PLATEAU + BAND, color="#d9d9d9", alpha=0.55, zorder=0)
ax.text(18.6, V2_PLATEAU, "v2 converged plateau 2.814", fontsize=7.2, color="#595959",
        va="center", ha="right", style="italic")

for name, ys, color, off in series:
    xs = list(range(1, len(ys) + 1))
    ax.plot(xs, [y + off for y in ys], color=color, lw=1.4, zorder=3,
            marker="o", ms=2.6, mfc=color, mec="white", mew=0.5)
    # series label at end of line, direct labeling (no legend)
    ax.text(xs[-1] + 0.35, ys[-1] + off, name, fontsize=7.6, color=color,
            va="center", ha="left", fontweight="bold" if "v3" in name else "normal")
    # last value label
    ax.text(xs[-1], ys[-1] + off + 0.16, f"{ys[-1]:.3f}", fontsize=6.6,
            color=color, ha="center", va="bottom")

# parity point: v3-56M epoch5 reaches v2 plateau
ax.plot([5], [v3_56[-1] + 0.12], marker="*", ms=11, color="#e8a917", mec="#3a3a3a", mew=0.6, zorder=5)
ax.annotate("4x data, 13 fewer epochs\n(matches v2 converged loss)",
            xy=(5, v3_56[-1] + 0.12), xytext=(7.4, v3_56[-1] + 0.52),
            fontsize=7.2, color="#3a3a3a",
            arrowprops=dict(arrowstyle="-", color="#8a8a8a", lw=0.7))

# epoch-1 horizontal guides (dotted) showing start-gap of 355M vs 56M
ax.plot([1, 1], [v3_355[0], v3_56[0]], color="#b0b0b0", lw=0.6, ls=":")
ax.text(0.92, (v3_355[0] + v3_56[0]) / 2, "0.10", fontsize=6.4, color="#8a8a8a",
        ha="right", va="center")

ax.set_xlabel("epoch", fontsize=8.6)
ax.set_ylabel("validation loss  (offset per series for readability)", fontsize=8.6)
ax.set_xlim(0.5, 21.5)
ax.set_ylim(2.55, 5.35)
ax.set_xticks([1, 3, 5, 10, 15, 18])
ax.spines[["top", "right"]].set_visible(False)
ax.tick_params(length=2.4)
ax.grid(axis="x", color="#dcdcdc", lw=0.4, ls=(0, (1, 2)))
ax.set_axisbelow(True)

ax.set_title("Pretraining capacity curves: objective choice dominates, then data size, then model size",
             fontsize=9.8, fontweight="bold", color="#1b2a5c", pad=8, loc="left")
fig.text(0.06, 0.012, "Rows are vertically offset; absolute values printed at each line end. "
         "v1 masking saturates at marginal codon entropy 4.03 (dead objective); "
         "v2 corruption (215k) needs 18 epochs; v3 4x data reaches the same loss in 5 epochs; 355M in progress.",
         fontsize=6.8, color="#595959")

fig.subplots_adjust(left=0.10, right=0.68, top=0.90, bottom=0.16)
OUT = HERE / "fig10_capacity"
fig.savefig(OUT.with_suffix(".png"), dpi=300)
fig.savefig(OUT.with_suffix(".pdf"))
print("saved", OUT.with_suffix(".png"))
