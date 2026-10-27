"""Distribution and exact CDS/protein leakage audits.

The original distribution plots remain available. ``--splits`` adds a
standard-library-only deterministic audit without CAI/MFE/plot dependencies.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def summarize_lengths(values):
    if not values:
        return {"mean": None, "min": None, "q50": None, "max": None}
    ordered = sorted(values)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {
        "mean": sum(ordered) / len(ordered),
        "min": ordered[0],
        "q50": median,
        "q05": quantile(ordered, 0.05),
        "q25": quantile(ordered, 0.25),
        "q75": quantile(ordered, 0.75),
        "q95": quantile(ordered, 0.95),
        "max": ordered[-1],
    }


def quantile(ordered, probability):
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def histogram(values, edges):
    counts = [0] * (len(edges) - 1)
    for value in values:
        if value < edges[0] or value > edges[-1]:
            raise ValueError(f"distribution value {value} outside [{edges[0]}, {edges[-1]}]")
        index = bisect.bisect_right(edges, value) - 1
        counts[min(index, len(counts) - 1)] += 1
    return {"edges": edges, "counts": counts}


def overlap_audit(split_fastas: Dict[str, str], benchmark_fasta: str):
    """Count exact CDS and translated-protein duplicates within/across splits."""
    try:
        from .gemorna_arm import cds_protein, read_fasta_records
    except ImportError:
        from gemorna_arm import cds_protein, read_fasta_records

    split_fastas = dict(split_fastas)
    if benchmark_fasta is not None:
        split_fastas["benchmark"] = benchmark_fasta
    summaries, memberships, input_counts = {}, {}, {}
    for split, fasta in split_fastas.items():
        cds_values, protein_values = [], []
        cds_counts, protein_counts = {}, {}
        invalid = 0
        for header, cds in read_fasta_records(fasta):
            cds = cds.strip().upper().replace("U", "T")
            protein = cds_protein(cds)
            cds_values.append(cds)
            cds_counts[cds] = cds_counts.get(cds, 0) + 1
            memberships.setdefault(("cds", cds), set()).add(split)
            if protein is None:
                invalid += 1
            else:
                protein_values.append(protein)
                protein_counts[protein] = protein_counts.get(protein, 0) + 1
                memberships.setdefault(("protein", protein), set()).add(split)
        input_counts[split] = {"cds": cds_counts, "protein": protein_counts}
        length_values = [len(s) for s in cds_values]
        gc_values = [(s.count("G") + s.count("C")) / len(s) if s else 0.0 for s in cds_values]
        summaries[split] = {
            "n": len(cds_values),
            "length_nt": summarize_lengths(length_values),
            "gc": summarize_lengths(gc_values),
            "histograms": {
                "length_nt": histogram(length_values, [0] + list(range(300, 6001, 300))),
                "gc": histogram(gc_values, [i / 50 for i in range(51)]),
            },
            "n_unique_cds": len(cds_counts),
            "n_duplicate_cds_inputs": sum(n - 1 for n in cds_counts.values()),
            "n_cds_sequences_in_duplicate_groups": sum(n for n in cds_counts.values() if n > 1),
            "n_unique_proteins": len(protein_counts),
            "n_duplicate_protein_inputs": sum(n - 1 for n in protein_counts.values()),
            "n_protein_sequences_in_duplicate_groups": sum(n for n in protein_counts.values() if n > 1),
            "n_invalid_translation": invalid,
        }

    memberships = {key: splits for key, splits in memberships.items() if len(splits) > 1}
    overlaps = {}
    names = list(summaries)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            row = {}
            for kind in ("cds", "protein"):
                shared = sorted(key for (k, key), splits in memberships.items()
                                if k == kind and left in splits and right in splits)
                row[f"n_shared_{kind}"] = len(shared)
                row[f"n_{left}_inputs_with_shared_{kind}"] = sum(
                    input_counts[left][kind].get(key, 0) for key in shared
                )
                row[f"n_{right}_inputs_with_shared_{kind}"] = sum(
                    input_counts[right][kind].get(key, 0) for key in shared
                )
                row[f"shared_{kind}_examples"] = shared[:10]
            overlaps[f"{left}__{right}"] = row
    return {
        "scope": "exact normalized CDS and standard-table translated protein only; not family-disjoint proof",
        "splits": summaries,
        "overlaps": overlaps,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fasta")
    ap.add_argument("--rscu-json")
    ap.add_argument("--tag")
    ap.add_argument("--out-dir", default="docs/data_audit")
    ap.add_argument("--splits", nargs=3, metavar=("TRAIN", "VAL", "TEST"))
    ap.add_argument("--benchmark-fasta")
    ap.add_argument("--overlap-out", help="defaults to <out-dir>/overlap_audit.json")
    args = ap.parse_args()
    if args.benchmark_fasta and not args.splits:
        ap.error("--benchmark-fasta requires --splits TRAIN VAL TEST")
    if args.splits:
        result = overlap_audit(dict(zip(("train", "val", "test"), args.splits)),
                               args.benchmark_fasta)
        input_paths = dict(zip(("train", "val", "test"), args.splits))
        if args.benchmark_fasta:
            input_paths["benchmark"] = args.benchmark_fasta
        result["input_sha256"] = {
            name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for name, path in input_paths.items()
        }
        out_path = Path(args.overlap_out or Path(args.out_dir) / "overlap_audit.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        if not args.fasta:
            return
    if not (args.fasta and args.rscu_json and args.tag):
        ap.error("--fasta, --rscu-json and --tag are required for distribution audit")
    from codonflow.eval.metrics import cai_weights_from_rscu

    rscu = json.loads(Path(args.rscu_json).read_text())
    weights = cai_weights_from_rscu(rscu)
    s = audit(args.fasta, weights, args.tag, args.out_dir)
    print(json.dumps(s, indent=2))


def audit(fasta: str, cai_weights, tag: str, out_dir: str, n_mfe: int = 400) -> Dict:
    import numpy as np
    from codonflow.core.codon import gc_fraction
    from codonflow.data.dataset import read_fasta
    from codonflow.eval.metrics import cai, compute_rscu, mfe_batch

    lens, gcs, cais = [], [], []
    rscu_seqs = []
    for i, (h, s) in enumerate(read_fasta(fasta)):
        lens.append(len(s))
        gcs.append(gc_fraction(s))
        if i < 50000:
            cais.append(cai(s, cai_weights))
            rscu_seqs.append(s)
    rscu = compute_rscu(rscu_seqs)
    rng = np.random.default_rng(0)
    mfe_sample_idx = rng.choice(len(rscu_seqs), size=min(n_mfe, len(rscu_seqs)), replace=False)
    mfes = mfe_batch([rscu_seqs[i] for i in mfe_sample_idx])
    summary = {
        "tag": tag,
        "n": len(lens),
        "length": {
            "mean": float(np.mean(lens)),
            "std": float(np.std(lens)),
            "q5": float(np.percentile(lens, 5)),
            "q50": float(np.percentile(lens, 50)),
            "q95": float(np.percentile(lens, 95)),
        },
        "gc": {
            "mean": float(np.mean(gcs)),
            "std": float(np.std(gcs)),
            "q5": float(np.percentile(gcs, 5)),
            "q95": float(np.percentile(gcs, 95)),
        },
        "cai": {
            "mean": float(np.mean(cais)),
            "std": float(np.std(cais)),
            "q5": float(np.percentile(cais, 5)),
            "q95": float(np.percentile(cais, 95)),
        },
        "mfe_sample": {
            "mean": float(np.mean(mfes)),
            "q5": float(np.percentile(mfes, 5)),
            "q95": float(np.percentile(mfes, 95)),
        },
        "rscu_top": dict(sorted(rscu.items(), key=lambda kv: -kv[1])[:10]),
        "rscu_bottom": dict(sorted(rscu.items(), key=lambda kv: kv[1])[:10]),
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(11, 8))
        axes[0, 0].hist(lens, bins=80, color="#3b7dd8")
        axes[0, 0].set_title(f"{tag} length (nt)")
        axes[0, 1].hist(gcs, bins=60, color="#d86f3b")
        axes[0, 1].set_title(f"{tag} GC")
        axes[1, 0].hist(cais, bins=60, color="#3bd87a")
        axes[1, 0].set_title(f"{tag} CAI")
        axes[1, 1].hist(mfes, bins=40, color="#8a3bd8")
        axes[1, 1].set_title(f"{tag} MFE (sample {len(mfes)})")
        for ax in axes.flat:
            ax.set_yscale("log")
        fig.tight_layout()
        fig.savefig(out / f"audit_{tag}.png", dpi=120)
        plt.close(fig)
    except Exception as e:
        summary["plot_error"] = str(e)
    (out / f"audit_{tag}.json").write_text(json.dumps(summary, indent=2))
    return summary

if __name__ == "__main__":
    main()
