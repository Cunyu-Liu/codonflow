"""Plot Fig-6 (EXP-6): budget-quality-time curves from E6_budget_curves.json.

Frozen spec: HV vs scoring-calls curve family (one line per steps setting,
marker per C); per-solution time on secondary annotation; LinearDesign x5
cost reference line; inflection annotated.
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
    ap.add_argument("--json", default="/mnt/cunyuliu/codonflow/eval_outputs/E6_budget_curves.json")
    args = ap.parse_args()
    r = json.loads(Path(args.json).read_text())
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.6))

    styles = {10: ("#1f77b4", "o"), 20: ("#2ca02c", "s"), 30: ("#d62728", "^")}
    for steps in (10, 20, 30):
        rows = sorted([x for x in r if x["n_steps"] == steps], key=lambda z: z["scoring_calls"])
        for c in (10, 30):
            pts = [x for x in rows if x["n_candidates"] == c]
            if not pts:
                continue
            color, marker = styles[steps]
            label = f"steps={steps}, C={c}"
            ax.plot(
                [p["scoring_calls"] for p in pts], [p["hv"] for p in pts],
                marker=marker, color=color, linestyle="-" if c == 10 else "--",
                label=label, markersize=6,
            )
            ax2.plot(
                [p["scoring_calls"] for p in pts], [p["per_sol_s"] for p in pts],
                marker=marker, color=color, linestyle="-" if c == 10 else "--",
                label=label, markersize=6,
            )
    ax.set_xlabel("total scoring calls (budget)")
    ax.set_ylabel("hypervolume")
    ax.set_title("budget -> quality (knee at steps=30, C=10)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    ax2.set_xlabel("total scoring calls (budget)")
    ax2.set_ylabel("time per solution (s)")
    ax2.set_title("budget -> cost")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)

    best = max(r, key=lambda z: z["hv"])
    ax.annotate(
        f"knee: steps={best['n_steps']},C={best['n_candidates']}\n"
        f"{best['scoring_calls']} calls, HV {best['hv']:.2f}, {best['per_sol_s']}s/sol",
        xy=(best["scoring_calls"], best["hv"]),
        xytext=(best["scoring_calls"] * 0.55, best["hv"] * 0.9),
        arrowprops=dict(arrowstyle="->", color="k"),
        fontsize=8,
    )
    fig.suptitle("EXP-6: budget-quality-time grid (RLOO-v4, beta=8, apply_k=4, eGFP)")
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "fig6_exp6_budget_curves.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
