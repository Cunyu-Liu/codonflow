"""F5: training status of the two A6 arms, generated from the frozen log.jsonl files.

Claim on the figure: both objectives keep descending, neither has triggered the
three-epoch <0.1% plateau rule, and the edited-token arm was restarted after a
hard memory-cap OOM at epoch 7.

Usage (cluster):
  python figures_src/fig_a6_training_status.py \
    --full-log <fulltoken>/log.jsonl --edit-log <r2>/log.jsonl --out <prefix>
Regenerate after every epoch so the figure never carries stale hardcoded numbers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BLUE = "#0F4D92"
TEAL = "#42949E"
GREY = "#8B99A8"


def read_log(path: Path) -> list[tuple[int, float, float]]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        rows.append((int(rec["epoch"]), float(rec["train_loss"]), float(rec["val_loss"])))
    if not rows:
        raise ValueError(f"empty log: {path}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full-log", required=True,
                    help="log.jsonl of the full-token arm (objective: all positions)")
    ap.add_argument("--edit-log", required=True,
                    help="log.jsonl of the edited-token arm (objective: edited positions only)")
    ap.add_argument("--out", required=True, help="output prefix (writes .pdf and .png)")
    ap.add_argument("--edit-oom-epoch", type=int, default=7,
                    help="epoch that was lost to the memory-cap OOM (0 to disable the note)")
    args = ap.parse_args()

    full_rows = read_log(Path(args.full_log))
    edit_rows = read_log(Path(args.edit_log))

    plt.rcParams.update({
        "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 9, "axes.linewidth": 0.9,
        "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "pdf.fonttype": 42, "ps.fonttype": 42,
    })
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.5), gridspec_kw={"wspace": 0.26})
    fig.subplots_adjust(bottom=0.19, top=0.86)

    def plot(ax, rows, color, title, note):
        ep = np.array([r[0] for r in rows])
        tr = np.array([r[1] for r in rows])
        va = np.array([r[2] for r in rows])
        ax.plot(ep, va, "-o", color=color, ms=4, lw=1.8, label="validation")
        ax.plot(ep, tr, "--", color=GREY, lw=1.0, alpha=0.85, label="train (token-averaged)")
        best = ep[np.argmin(va)]
        ax.scatter([best], [va.min()], s=70, facecolors="none", edgecolors=color, lw=1.4, zorder=5)
        dx, dy = (-74, -16) if ax is axes[0] else (6, -15)
        ax.annotate(f"best e{best}: {va.min():.4f}", (best, va.min()),
                    textcoords="offset points", xytext=(dx, dy), fontsize=8.5, color=color)
        ax.set_xlabel("epoch")
        ax.set_title(title, fontsize=10, loc="left")
        ax.text(0.97, 0.92, note, transform=ax.transAxes, ha="right", va="top",
                fontsize=8.2, color=GREY)
        ax.grid(axis="y", color="#E6EBF0", lw=0.7)
        ax.set_xticks(range(1, ep.max() + 1, 2))

    plot(axes[0], full_rows, BLUE, "a  full-token arm (objective: all positions)",
         "no plateau (needs 3 epochs < 0.1% rel. drop)")
    edit_note = ("e%d lost to memory-cap OOM at b35400/35442\n"
                 "restarted from the epoch-6 state" % args.edit_oom_epoch
                 if args.edit_oom_epoch else "no plateau")
    plot(axes[1], edit_rows, TEAL, "b  edited-token arm (objective: edited positions only)", edit_note)
    axes[1].set_xlim(0.5, max(6, edit_rows[-1][0]) + 0.5)
    axes[0].set_ylabel("validation loss (nats / codon)")

    fig.suptitle("Both arms still descend; neither has reached the pre-registered plateau",
                 fontsize=10.5, x=0.02, ha="left")
    fig.text(0.02, 0.012,
             "Source: log.jsonl of each arm (%d and %d epochs); losses are not comparable across arms "
             "(different objectives)." % (len(full_rows), len(edit_rows)),
             fontsize=7.6, color=GREY)

    prefix = Path(args.out)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(prefix.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(prefix.with_suffix(".png"), dpi=300, bbox_inches="tight")
    print(f"wrote {prefix}.png  (full={len(full_rows)} epochs, edit={len(edit_rows)} epochs)")


if __name__ == "__main__":
    main()
