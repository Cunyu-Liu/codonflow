"""Download Ensembl/RefSeq CDS corpora (Task 1.1.1).

Primary: Ensembl BioMart REST (human + vertebrates CDS, transcript type).
Fallback: NCBI Datasets RefSeq umps.
Output: /mnt/cunyuliu/codonflow/corpora/<name>.fasta
"""
from __future__ import annotations

import argparse
import os
import time
import urllib.request
from pathlib import Path
from typing import List

BIOMART_URL = (
    "https://www.ensembl.org/biomart/martservice?query={xml}"
)

BIOMART_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Query>
<Query virtualSchemaName="{schema}" formatter="FASTA" header="0"
       uniqueRows="1" datasetConfigVersion="0.6">
  <Dataset name="{dataset}" interface="default">
    <Filter name="transcript_biotype" value="protein_coding"/>
    <Attribute name="cdna"/>
    <Attribute name="coding_sequence"/>
  </Dataset>
</Query>"""


def fetch(url: str, out_path: Path, retries: int = 5) -> int:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "codonflow/0.1"})
            with urllib.request.urlopen(req, timeout=600) as resp, open(out_path, "wb") as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            return out_path.stat().st_size
        except Exception as e:
            print(f"attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(10 * (attempt + 1))
    return -1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="/mnt/cunyuliu/codonflow/corpora")
    ap.add_argument("--dataset", default="hsapiens_gene_ensembl")
    ap.add_argument("--schema", default="ensembl")
    ap.add_argument("--tag", default="ensembl_human")
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    import urllib.parse

    xml = BIOMART_XML.format(schema=args.schema, dataset=args.dataset)
    url = BIOMART_URL.format(xml=urllib.parse.quote(xml))
    out = out_dir / f"{args.tag}.fasta"
    if out.exists() and out.stat().st_size > 1000:
        print(f"exists: {out}")
        return
    size = fetch(url, out)
    print(f"downloaded {size} bytes -> {out}")


if __name__ == "__main__":
    main()
