#!/usr/bin/env python3
"""Independent raw-read and artifact verification for Mordstein recovery."""
import argparse
import collections
import csv
import datetime
import gzip
import hashlib
import json
from pathlib import Path

BASES = "TCAG"
AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
TABLE = {a+b+c: AAS[i] for i, (a, b, c) in enumerate(
    (a, b, c) for a in BASES for b in BASES for c in BASES)}
COMP = str.maketrans("ACGTN", "TGCAN")


def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def translate(seq):
    return "".join(TABLE.get(seq[i:i+3], "X") for i in range(0, len(seq) - 2, 3))


def r2_coding(seq):
    return seq.translate(COMP)[::-1][1:280]


def read_fasta(path):
    records = {}
    name = None
    chunks = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                if name is not None:
                    records[name] = "".join(chunks)
                name = line[1:].split()[0]
                chunks = []
            else:
                chunks.append(line)
    if name is not None:
        records[name] = "".join(chunks)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    summary_path = args.artifacts / "summary.json"
    counts_path = args.artifacts / "variant_counts.csv"
    summary = json.loads(summary_path.read_text())
    with counts_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    checks = []
    def check(name, condition, details=None):
        checks.append({"name": name, "status": "PASS" if condition else "FAIL", "details": details})

    check("production_pending_independent", summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("smoke_scope_not_complete_library", summary["library_recovery_status"] == "SMOKE_PARTIAL_LIBRARY")
    check("central_gap_138", summary["checks"]["gap_is_138nt"] and all(int(row["central_gap_nt"]) == 138 for row in rows))
    check("row_count_matches_summary", len(rows) == summary["variants_retained"], len(rows))
    check("mutual_count_matches_summary", sum(row["mutual_best_r2"] == "True" for row in rows) == summary["mutual_best_links"])
    check("reconstructed_ids_only", all(row["variant_id"].startswith("CF_MORD_") for row in rows))
    check("support_threshold", all(int(row["r1_assigned_reads"]) >= summary["parameters"]["min_variant_support"] for row in rows))
    count_columns = [key for key in rows[0] if key.startswith("counts_")]
    check("counts_sum_to_assigned_total", all(sum(int(row[key]) for key in count_columns) == int(row["r1_assigned_reads"]) for row in rows))
    check("pair_purity_bounds", all(row["r1_pair_purity"] in {"", "None"} or 0 <= float(row["r1_pair_purity"]) <= 1 for row in rows))

    r1_fasta = read_fasta(args.artifacts / "references_r1.fasta")
    paired_fasta = read_fasta(args.artifacts / "references_paired_ends.fasta")
    check("r1_fasta_complete", len(r1_fasta) == len(rows))
    check("r1_fasta_matches_table", all(r1_fasta.get(row["variant_id"]) == row["sequence_5prime_300nt"] for row in rows))
    check("r1_translation", all(translate(row["sequence_5prime_300nt"]) == summary["r1_protein_reference"] for row in rows))
    linked = [row for row in rows if row["sequence_3prime_279nt"]]
    check("paired_fasta_complete", len(paired_fasta) == len(linked))
    check("r2_translation", all(translate(row["sequence_3prime_279nt"]) == summary["r2_protein_reference"] for row in linked))
    gap_ok = True
    for row in linked:
        seq = paired_fasta.get(row["variant_id"], "")
        expected = "ATG" + row["sequence_5prime_300nt"] + "N" * 138 + row["sequence_3prime_279nt"]
        gap_ok = gap_ok and seq == expected and len(seq) == 720 and seq[303:441] == "N" * 138
    check("paired_fasta_gap_and_lengths", gap_ok)

    def pairwise_above(rows, key, threshold):
        # Multiple distinct R1 haplotypes may legitimately share one R2 end.
        sequences = sorted({row[key] for row in rows if row[key]})
        for i, first in enumerate(sequences):
            for second in sequences[i+1:]:
                if sum(a != b for a, b in zip(first, second)) <= threshold:
                    return False
        return True
    check("selected_r1_centroids_separated", pairwise_above(rows, "sequence_5prime_300nt", 8))
    check("selected_r2_centroids_separated", pairwise_above(rows, "sequence_3prime_279nt", 8))

    input_hashes = []
    inputs_ok = True
    for item in summary["input_files"]:
        path = Path(item["path"])
        actual = sha256(path) if path.exists() else None
        match = actual == item["sha256"] and path.stat().st_size == item["bytes"]
        inputs_ok = inputs_ok and match
        input_hashes.append({"path": str(path), "expected_sha256": item["sha256"], "actual_sha256": actual, "match": match})
    check("frozen_input_hashes", inputs_ok)

    r1_targets = {row["sequence_5prime_300nt"]: row for row in rows}
    r2_targets = {row["sequence_3prime_279nt"]: row for row in linked}
    exact_r1 = collections.Counter()
    exact_r2 = collections.Counter()
    total = 0
    orf_r1 = 0
    orf_r2 = 0
    first_path = Path(summary["runs"][0]["r1"])
    second_path = Path(summary["runs"][0]["r2"])
    with gzip.open(first_path, "rt") as first, gzip.open(second_path, "rt") as second:
        while True:
            h1 = [first.readline() for _ in range(4)]
            h2 = [second.readline() for _ in range(4)]
            if not h1[0] and not h2[0]:
                break
            if len(h1) != 4 or len(h2) != 4 or not all(h1 + h2):
                raise ValueError("Unexpected truncated frozen input")
            seq1 = h1[1].strip()
            seq2 = h2[1].strip()
            coding2 = r2_coding(seq2)
            if seq1 in r1_targets:
                exact_r1[seq1] += 1
            if coding2 in r2_targets:
                exact_r2[coding2] += 1
            orf_r1 += int(translate(seq1) == summary["r1_protein_reference"])
            orf_r2 += int(translate(coding2) == summary["r2_protein_reference"])
            total += 1
    check("raw_read_pair_count", total == summary["run_metrics"][0]["pairs_scanned"], total)
    check("raw_r1_orf_count", orf_r1 == summary["exact_collection"][0]["r1_orf_valid_reads"], orf_r1)
    check("raw_r2_orf_count", orf_r2 == summary["exact_collection"][0]["r2_orf_valid_reads"], orf_r2)
    bad_r1 = [{"id": row["variant_id"], "expected": int(row["r1_seed_exact_reads"]), "observed": exact_r1[row["sequence_5prime_300nt"]]}
              for row in rows if int(row["r1_seed_exact_reads"]) != exact_r1[row["sequence_5prime_300nt"]]]
    bad_r2 = [{"id": row["variant_id"], "expected": int(row["r2_seed_exact_reads"]), "observed": exact_r2[row["sequence_3prime_279nt"]]}
              for row in linked if int(row["r2_seed_exact_reads"]) != exact_r2[row["sequence_3prime_279nt"]]]
    check("independent_r1_exact_seed_counts", not bad_r1, bad_r1[:10])
    check("independent_r2_exact_seed_counts", not bad_r2, bad_r2[:10])

    status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    report = {
        "schema": "a8.rk02.mordstein_recovery_independent.v1",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": status, "scope": "single-bin smoke; not complete 217-library recovery",
        "artifacts": {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
                      for path in [summary_path, counts_path, args.artifacts / "references_r1.fasta", args.artifacts / "references_paired_ends.fasta"]},
        "input_hashes": input_hashes, "raw_pairs_recounted": total,
        "variants": len(rows), "linked_variants": len(linked),
        "checks": checks, "passed": sum(item["status"] == "PASS" for item in checks),
        "total": len(checks),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": status, "passed": report["passed"], "total": report["total"], "report": str(args.report)}))
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
