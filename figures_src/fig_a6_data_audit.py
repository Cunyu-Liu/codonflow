"""Render the A6 data-integrity audit directly from two verified JSON reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


PALETTE = {"old": "#A9B2BA", "new": "#0F4D92", "text": "#252B31", "muted": "#64707A"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v3", type=Path, required=True)
    parser.add_argument("--v4", type=Path, required=True)
    parser.add_argument("--out-prefix", type=Path, required=True)
    args = parser.parse_args()
    v3 = json.loads(args.v3.read_text())
    v4 = json.loads(args.v4.read_text())
    split_names = ("train", "val", "test")
    n_v3 = sum(v3["splits"][s]["n"] for s in split_names)
    n_v4 = sum(v4["splits"][s]["n"] for s in split_names)
    for split in split_names + ("benchmark",):
        assert v4["splits"][split]["n_unique_cds"] == v4["splits"][split]["n_unique_proteins"]
    for overlap in v4["overlaps"].values():
        assert overlap["n_shared_cds"] == overlap["n_shared_protein"] == 0

    plt.rcParams.update({
        "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 10, "axes.linewidth": 1.0, "axes.spines.top": False,
        "axes.spines.right": False, "legend.frameon": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    })
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.5), gridspec_kw={"wspace": 0.34})
    fig.subplots_adjust(left=0.065, right=0.985, bottom=0.22, top=0.73)
    fig.text(0.065, 0.95, "Exact-protein deduplication closes an overlooked split-leakage channel",
             fontsize=16, fontweight="bold", color=PALETTE["text"])
    fig.text(0.065, 0.885,
             f"{n_v3:,} cleaned CDS records → {n_v4:,} unique proteins; all v4 exact cross-split overlaps are zero",
             fontsize=10.5, color=PALETTE["muted"])

    x = np.arange(3)
    old_duplicates = [v3["splits"][s]["n_duplicate_protein_inputs"] for s in split_names]
    new_duplicates = [v4["splits"][s]["n_duplicate_protein_inputs"] for s in split_names]
    axes[0].bar(x - 0.18, old_duplicates, width=0.36, color=PALETTE["old"], label="v3 legacy split")
    axes[0].bar(x + 0.18, new_duplicates, width=0.36, color=PALETTE["new"], label="v4 exact-protein split")
    axes[0].set_xticks(x, split_names)
    axes[0].set_ylabel("Repeated translated-protein records")
    axes[0].set_title("a  Duplicates within each split", loc="left", fontweight="bold")
    axes[0].legend(loc="upper right")
    for i, value in enumerate(old_duplicates):
        axes[0].text(i - 0.18, value * 1.025, f"{value:,}", ha="center", va="bottom", fontsize=9)
    axes[0].set_ylim(0, max(old_duplicates) * 1.19)

    pair_names = ("train__val", "train__test", "val__test")
    overlaps = [v3["overlaps"][p]["n_shared_protein"] for p in pair_names]
    axes[1].bar(x - 0.18, overlaps, width=0.36, color=PALETTE["old"])
    axes[1].bar(x + 0.18, [v4["overlaps"][p]["n_shared_protein"] for p in pair_names],
                width=0.36, color=PALETTE["new"])
    axes[1].set_xticks(x, ["train–val", "train–test", "val–test"])
    axes[1].set_ylabel("Shared exact proteins")
    axes[1].set_title("b  Cross-split leakage before and after", loc="left", fontweight="bold")
    for i, value in enumerate(overlaps):
        axes[1].text(i - 0.18, value + 5, f"{value}", ha="center", fontsize=9)
        axes[1].text(i + 0.18, 5, "0", ha="center", fontsize=9, color=PALETTE["new"])
    axes[1].set_ylim(0, max(overlaps) * 1.25)

    width = 0.36
    old_unique = [v3["splits"][s]["n_unique_proteins"] for s in split_names]
    new_unique = [v4["splits"][s]["n_unique_proteins"] for s in split_names]
    axes[2].bar(x - width / 2, old_unique, width, color=PALETTE["old"])
    axes[2].bar(x + width / 2, new_unique, width, color=PALETTE["new"])
    axes[2].set_xticks(x, split_names)
    axes[2].set_ylabel("Unique translated proteins")
    axes[2].set_title("c  Records retained for model development", loc="left", fontweight="bold")
    for i, (old, new) in enumerate(zip(old_unique, new_unique)):
        axes[2].text(i + width / 2, new + max(new_unique) * 0.018, f"{new:,}", ha="center", fontsize=8.5)
    axes[2].set_ylim(0, max(new_unique) * 1.16)
    for ax in axes:
        ax.tick_params(axis="both", length=3, color=PALETTE["muted"])
        ax.grid(False)
    fig.text(0.065, 0.075,
             "Scope: exact nucleotide/protein identity and nucleotide clusters, not family- or species-level homology.\n"
             "Sources: v3_exact_overlap.json and v4_exact_overlap.json; v4 benchmark has 23 unique CDS/proteins.",
             fontsize=9, color=PALETTE["muted"], linespacing=1.5)
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out_prefix.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(args.out_prefix.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps({"n_v3": n_v3, "n_v4": n_v4,
                      "out": [str(args.out_prefix.with_suffix(".pdf")), str(args.out_prefix.with_suffix(".png"))]}))


if __name__ == "__main__":
    main()
