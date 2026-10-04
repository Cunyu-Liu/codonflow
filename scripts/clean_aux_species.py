"""Clean auxiliary species CDS (Ensembl) with the same rules as GENCODE."""
from __future__ import annotations

import sys

sys.path.insert(0, "/home/cunyuliu/codonflow/src")
from codonflow.data.pipeline import clean_fasta

if __name__ == "__main__":
    for name in [
        "caenorhabditis_elegans_cds",
        "drosophila_melanogaster_cds",
        "mus_musculus_cds",
        "danio_rerio_cds",
    ]:
        src = f"/mnt/cunyuliu/codonflow/corpora/{name}.fa"
        dst = f"/mnt/cunyuliu/codonflow/corpora/{name}_cleaned.fasta"
        counts = clean_fasta(src, dst)
        print(name, counts, flush=True)
