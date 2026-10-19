"""Clean auxiliary species CDS (Ensembl) with the same rules as GENCODE."""
from __future__ import annotations

import sys

sys.path.insert(0, "/home/codonflow/src")
from codonflow.data.pipeline import clean_fasta

if __name__ == "__main__":
    for name in [
        "caenorhabditis_elegans_cds",
        "drosophila_melanogaster_cds",
        "mus_musculus_cds",
        "danio_rerio_cds",
    ]:
        src = f"/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/{name}.fa"
        dst = f"/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/{name}_cleaned.fasta"
        counts = clean_fasta(src, dst)
        print(name, counts, flush=True)
