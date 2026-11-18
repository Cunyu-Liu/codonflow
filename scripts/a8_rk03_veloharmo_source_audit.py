#!/usr/bin/env python3
"""Audit VeloHARMO source-tree availability without lazy-fetching missing blobs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

EXPECTED_ARCHIVES = {
    "VeloGRU/E.coli.summary.add.pro.SS.txt.zip",
    "VeloBERT/E.coli.summary.add.pro.SS.txt.zip",
}


def git(repository, arguments):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_NO_LAZY_FETCH": "1"}
    return subprocess.check_output(["git", "-C", str(repository), *arguments], text=True, env=env).strip()


def audit(repository, commit):
    head = git(repository, ["rev-parse", "HEAD"])
    if head != commit: raise RuntimeError(f"HEAD mismatch: {head} != {commit}")
    tree_hash = git(repository, ["rev-parse", f"{commit}^{{tree}}"])
    lines = git(repository, ["ls-tree", "-r", commit]).splitlines()
    entries = []
    for line in lines:
        metadata, path = line.split("\t", 1)
        mode, kind, blob = metadata.split()
        if kind != "blob": continue
        entries.append({"path": path, "mode": mode, "blob_id": blob})
    paths = {item["path"] for item in entries}
    archives = sorted(path for path in paths if path.endswith("summary.add.pro.SS.txt.zip"))
    if set(archives) != EXPECTED_ARCHIVES:
        raise RuntimeError(f"unexpected fixed-tree archive set: {archives}")
    availability = {
        "E_coli": "two_same_named_archives_listed_content_not_materialized_or_qc_verified",
        "Saccharomyces_cerevisiae": "no_processed_matrix_archive_in_fixed_tree",
        "Pseudomonas_aeruginosa": "no_processed_matrix_archive_in_fixed_tree",
        "Drosophila_melanogaster": "no_processed_matrix_archive_in_fixed_tree",
        "Human": "no_processed_matrix_archive_in_fixed_tree",
    }
    return {
        "schema_version": "a8-rk03-veloharmo-source-tree-audit-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_SOURCE_TREE_AUDIT_ONLY",
        "repository": "https://github.com/BianBian2021/VeloHARMO",
        "paper": "https://academic.oup.com/bib/article/27/5/bbag558/8885519",
        "commit": commit, "tree_hash": tree_hash, "head_matches": True,
        "git_lazy_fetch_disabled": True, "tree_entry_count": len(entries),
        "listed_matrix_archives": [item for item in entries if item["path"] in EXPECTED_ARCHIVES],
        "organism_matrix_availability": availability,
        "archive_bytes_and_content_verified": False,
        "five_species_processed_matrices_complete": False,
        "paper_metrics_independently_reproduced": False,
        "model_training_or_sota_claim_authorized": False,
        "all_tree_entries": entries,
        "scope": "Fixed-commit tree and blob-ID audit only; the listed E. coli ZIP payloads were not represented as downloaded, decompressed, or biologically QC-verified.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    if args.audit.exists(): raise RuntimeError(f"refusing to overwrite: {args.audit}")
    report = audit(args.repository, args.commit)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    part = args.audit.with_name(args.audit.name + f".part.{os.getpid()}")
    part.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(part, args.audit)
    print(json.dumps({"status": report["status"], "tree_entries": report["tree_entry_count"],
                      "listed_archives": len(report["listed_matrix_archives"]),
                      "five_species_complete": False, "content_verified": False}))


if __name__ == "__main__": main()
