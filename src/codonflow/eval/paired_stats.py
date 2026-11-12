"""Gene-level paired statistics for learned-versus-simple comparisons."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, Sequence

import numpy as np
from scipy.stats import wilcoxon


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    values = np.asarray(p_values, dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError("p-values must be a nonempty finite vector")
    if np.any((values < 0) | (values > 1)):
        raise ValueError("p-values must lie in [0, 1]")
    order = np.argsort(values)
    adjusted = np.empty(len(values), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(values) - rank) * values[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def paired_gene_effects(
    rows: Iterable[Mapping],
    simple_methods: Sequence[str],
    learned_method: str = "learned",
    n_bootstrap: int = 10000,
    seed: int = 0,
) -> dict:
    grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for row in rows:
        value = float(row["auc"])
        if not np.isfinite(value):
            raise ValueError("AUC values must be finite")
        grouped[row["gene"]][int(row["seed"])][row["method"]].append(value)
    if not grouped:
        raise ValueError("no paired observations")
    per_gene = []
    for gene in sorted(grouped):
        method_values = defaultdict(list)
        for seed_values in grouped[gene].values():
            for method, values in seed_values.items():
                if len(values) != 1:
                    raise ValueError("each gene/seed/method must have one AUC")
                method_values[method].append(values[0])
        if learned_method not in method_values:
            raise ValueError(f"missing learned method for {gene}")
        available_simple = [m for m in simple_methods if m in method_values]
        if not available_simple:
            raise ValueError(f"missing simple methods for {gene}")
        learned = float(np.mean(method_values[learned_method]))
        simple_means = {method: float(np.mean(method_values[method])) for method in available_simple}
        strongest_simple_method = max(available_simple, key=lambda method: simple_means[method])
        simple = simple_means[strongest_simple_method]
        if simple <= 0:
            raise ValueError(f"relative effect requires positive simple AUC for {gene}")
        per_gene.append({
            "gene": gene,
            "learned_auc": learned,
            "strongest_simple_auc": simple,
            "strongest_simple_method": strongest_simple_method,
            "absolute_improvement": learned - simple,
            "relative_improvement": (learned - simple) / abs(simple),
            "n_seeds": len(grouped[gene]),
        })
    absolute = np.asarray([row["absolute_improvement"] for row in per_gene])
    relative = np.asarray([row["relative_improvement"] for row in per_gene])
    if n_bootstrap < 1:
        raise ValueError("n_bootstrap must be positive")
    rng = np.random.default_rng(seed)
    samples = rng.choice(relative, size=(n_bootstrap, len(relative)), replace=True)
    medians = np.median(samples, axis=1)
    if np.allclose(absolute, 0):
        p_value = 1.0
    else:
        p_value = float(wilcoxon(absolute, alternative="greater", zero_method="wilcox").pvalue)
    return {
        "n_genes": len(per_gene),
        "median_relative_improvement": float(np.median(relative)),
        "median_absolute_improvement": float(np.median(absolute)),
        "paired_bootstrap_95ci": [float(np.quantile(medians, 0.025)),
                                  float(np.quantile(medians, 0.975))],
        "wilcoxon_greater_p": p_value,
        "per_gene": per_gene,
        "bootstrap_seed": seed,
        "n_bootstrap": n_bootstrap,
    }
