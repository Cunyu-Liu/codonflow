#!/usr/bin/env python3
"""Independent multi-bin verification for observed-end Mordstein recovery.

This verifier does not import the production implementation. It recounts raw reads,
checks exact seed counts and ORF totals, reassigns the frozen audit sample, and
verifies all reported centroids and artifact hashes. It never treats N-filled
paired-end references as a fully observed CDS.
"""
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


def fastq_records(path):
    with gzip.open(path, "rt") as handle:
        while True:
            header = handle.readline()
            if not header:
                return
            seq = handle.readline().strip()
            plus = handle.readline()
            qual = handle.readline().strip()
            if not seq or not plus.startswith("+") or len(seq) != len(qual):
                raise ValueError(f"Malformed FASTQ record in {path} after {header.strip()}")
            yield header.strip(), seq


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


def hamming(first, second):
    return sum(a != b for a, b in zip(first, second)) + abs(len(first) - len(second))


class IndependentSeedAssigner:
    def __init__(self, centroids, max_error=8):
        self.centroids = centroids
        self.max_error = max_error
        self.length = len(centroids[0]) if centroids else 0
        self.bounds = [min(self.length, int(i * self.length / 9)) for i in range(10)]
        self.index = collections.defaultdict(list)
        for cid, seq in enumerate(centroids):
            for segment in range(9):
                start, end = self.bounds[segment], self.bounds[segment + 1]
                self.index[(segment, seq[start:end])].append(cid)

    def assign(self, seq):
        if not self.centroids or len(seq) != self.length:
            return None
        candidates = set()
        for segment in range(9):
            start, end = self.bounds[segment], self.bounds[segment + 1]
            candidates.update(self.index.get((segment, seq[start:end]), ()))
        if not candidates:
            return None
        distances = [(hamming(seq, self.centroids[cid]), cid) for cid in candidates]
        best = min(distance for distance, _ in distances)
        winners = [cid for distance, cid in distances if distance == best]
        return winners[0] if best <= self.max_error and len(winners) == 1 else None


def pairwise_separated(sequences, threshold=8):
    sequences = sorted(set(sequences))
    for index, first in enumerate(sequences):
        for second in sequences[index+1:]:
            if hamming(first, second) <= threshold:
                return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--scope", choices=["smoke", "full"], required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    summary_path = args.artifacts / "summary.json"
    counts_path = args.artifacts / "variant_counts.csv"
    audit_path = args.artifacts / "read_assignment_audit_sample.csv"
    summary = json.loads(summary_path.read_text())
    with counts_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    with audit_path.open(newline="") as handle:
        audit_rows = list(csv.DictReader(handle))
    checks = []

    def check(name, condition, details=None):
        checks.append({"name": name, "status": "PASS" if condition else "FAIL", "details": details})

    full = args.scope == "full"
    check("production_pending_independent", summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("scope_matches", len(summary["runs"]) == (8 if full else 1) and
          ({row["bin"] for row in summary["runs"]} == set(range(1, 9)) if full else True))
    check("recovery_status_declared", summary["library_recovery_status"] in {
        "SMOKE_PARTIAL_LIBRARY", "EXACT_217_CANDIDATES", "REVIEW_REQUIRED_COUNT_NOT_217"})
    check("smoke_not_complete_library", not full and summary["library_recovery_status"] == "SMOKE_PARTIAL_LIBRARY" or
          full and summary["library_recovery_status"] != "SMOKE_PARTIAL_LIBRARY")
    check("central_gap_138", summary["checks"]["gap_is_138nt"] and all(int(row["central_gap_nt"]) == 138 for row in rows))
    check("row_count_matches_summary", len(rows) == summary["variants_retained"], len(rows))
    check("mutual_count_matches_summary", sum(row["mutual_best_r2"] == "True" for row in rows) == summary["mutual_best_links"])
    check("reconstructed_ids_only", all(row["variant_id"].startswith("CF_MORD_") for row in rows))
    check("support_threshold", all(int(row["r1_assigned_reads"]) >= summary["parameters"]["min_variant_support"] for row in rows))
    count_columns = [key for key in rows[0] if key.startswith("counts_")]
    check("eight_count_columns_when_full", not full or len(count_columns) == 8, count_columns)
    check("counts_sum_to_assigned_total", all(sum(int(row[key]) for key in count_columns) == int(row["r1_assigned_reads"]) for row in rows))
    check("pair_purity_bounds", all(row["r1_pair_purity"] in {"", "None"} or 0 <= float(row["r1_pair_purity"]) <= 1 for row in rows))

    r1_fasta = read_fasta(args.artifacts / "references_r1.fasta")
    paired_fasta = read_fasta(args.artifacts / "references_paired_ends.fasta")
    all_r1_fasta = read_fasta(args.artifacts / "all_r1_centroids.fasta")
    all_r2_fasta = read_fasta(args.artifacts / "all_r2_centroids.fasta")
    r1_centroids = [all_r1_fasta.get(f"r1_centroid_{index:04d}", "") for index in range(len(all_r1_fasta))]
    r2_centroids = [all_r2_fasta.get(f"r2_centroid_{index:04d}", "") for index in range(len(all_r2_fasta))]
    check("all_r1_centroids_count", len(all_r1_fasta) == summary["r1_centroids"] and all(r1_centroids))
    check("all_r2_centroids_count", len(all_r2_fasta) == summary["r2_centroids"] and all(r2_centroids))
    check("all_r1_centroids_translation", all(translate(seq) == summary["r1_protein_reference"] for seq in r1_centroids))
    check("all_r2_centroids_translation", all(translate(seq) == summary["r2_protein_reference"] for seq in r2_centroids))
    check("all_r1_centroids_separated", pairwise_separated(r1_centroids))
    check("all_r2_centroids_separated", pairwise_separated(r2_centroids))
    check("selected_r1_matches_all_centroids", all(r1_centroids[int(row["r1_centroid_index"])] == row["sequence_5prime_300nt"] for row in rows))
    linked = [row for row in rows if row["sequence_3prime_279nt"]]
    check("selected_r2_matches_all_centroids", all(r2_centroids[int(row["r2_centroid_index"])] == row["sequence_3prime_279nt"] for row in linked))
    check("r1_fasta_complete", len(r1_fasta) == len(rows))
    check("r1_fasta_matches_table", all(r1_fasta.get(row["variant_id"]) == row["sequence_5prime_300nt"] for row in rows))
    check("r1_translation", all(translate(row["sequence_5prime_300nt"]) == summary["r1_protein_reference"] for row in rows))
    check("paired_fasta_complete", len(paired_fasta) == len(linked))
    check("r2_translation", all(translate(row["sequence_3prime_279nt"]) == summary["r2_protein_reference"] for row in linked))
    gap_ok = True
    for row in linked:
        seq = paired_fasta.get(row["variant_id"], "")
        expected = "ATG" + row["sequence_5prime_300nt"] + "N" * 138 + row["sequence_3prime_279nt"]
        gap_ok = gap_ok and seq == expected and len(seq) == 720 and seq[303:441] == "N" * 138
    check("paired_fasta_gap_and_lengths", gap_ok)

    input_hashes = []
    inputs_ok = True
    for item in summary["input_files"]:
        path = Path(item["path"])
        actual = sha256(path) if path.exists() else None
        match = actual == item["sha256"] and path.stat().st_size == item["bytes"]
        inputs_ok = inputs_ok and match
        input_hashes.append({"path": str(path), "expected_sha256": item["sha256"], "actual_sha256": actual, "match": match})
    check("frozen_input_hashes", inputs_ok)
    cache_hashes = []
    caches_ok = True
    for item in summary.get("exact_cache_files", []):
        path = Path(item["path"])
        actual = sha256(path) if path.exists() else None
        match = actual == item["sha256"] and path.stat().st_size == item["bytes"]
        caches_ok = caches_ok and match
        cache_hashes.append({"path": str(path), "expected_sha256": item["sha256"], "actual_sha256": actual, "match": match})
    check("exact_cache_hashes", caches_ok)
    check("external_exact_mode", summary.get("exact_collection_mode") == "per_run_disk_cache_exact_merge")

    r1_targets = {row["sequence_5prime_300nt"]: row for row in rows}
    r2_targets = {row["sequence_3prime_279nt"]: row for row in linked}
    exact_r1 = collections.Counter()
    exact_r2 = collections.Counter()
    audit_by_run = collections.defaultdict(dict)
    for row in audit_rows:
        audit_by_run[row["run"]][int(row["read_index"])] = row
    audit_raw_mismatches = []
    raw_run_metrics = []
    for run_index, run in enumerate(summary["runs"]):
        total = 0
        orf_r1 = 0
        orf_r2 = 0
        seen_audit = 0
        first = iter(fastq_records(Path(run["r1"])))
        second = iter(fastq_records(Path(run["r2"])))
        pending = audit_by_run[run["run"]]
        while True:
            try:
                h1, seq1 = next(first)
                h2, seq2 = next(second)
            except StopIteration:
                break
            if h1.split()[0] != h2.split()[0]:
                raise ValueError(f"Mate order mismatch in {run['run']} at pair {total + 1}")
            total += 1
            coding2 = r2_coding(seq2)
            if seq1 in r1_targets:
                exact_r1[seq1] += 1
            if coding2 in r2_targets:
                exact_r2[coding2] += 1
            orf_r1 += int(len(seq1) == 300 and translate(seq1) == summary["r1_protein_reference"])
            orf_r2 += int(len(seq2) == 300 and translate(coding2) == summary["r2_protein_reference"])
            sampled = pending.get(total)
            if sampled is not None:
                seen_audit += 1
                if (sampled["read_id"] != h1.split()[0] or sampled["r1_sequence"] != seq1 or
                        sampled["r2_coding_sequence"] != coding2):
                    audit_raw_mismatches.append({"run": run["run"], "read_index": total})
        raw_run_metrics.append({"run": run["run"], "pairs": total, "orf_r1": orf_r1, "orf_r2": orf_r2,
                                "audit_rows_seen": seen_audit, "audit_rows_expected": len(pending)})
        check(f"audit_rows_seen_{run['run']}", seen_audit == len(pending),
              {"seen": seen_audit, "expected": len(pending)})
        expected_pairs = summary["run_metrics"][run_index]["pairs_scanned"]
        expected_exact = summary["exact_collection"][run_index]
        check(f"raw_pairs_{run['run']}", total == expected_pairs, total)
        check(f"raw_orf_{run['run']}", orf_r1 == expected_exact["r1_orf_valid_reads"] and
              orf_r2 == expected_exact["r2_orf_valid_reads"], {"r1": orf_r1, "r2": orf_r2})
    check("audit_sample_size", len(audit_rows) == summary["read_assignment_audit_rows"] ==
          summary["parameters"]["audit_sample_per_run"] * len(summary["runs"]), len(audit_rows))
    check("audit_sample_unique", len({(row["run"], row["read_index"]) for row in audit_rows}) == len(audit_rows))
    check("audit_rows_match_raw_reads", not audit_raw_mismatches, audit_raw_mismatches[:10])

    r1_assigner = IndependentSeedAssigner(r1_centroids)
    r2_assigner = IndependentSeedAssigner(r2_centroids)
    reassignment_mismatches = []
    distance_mismatches = []
    for row in audit_rows:
        id1_text = row["r1_centroid_index"]
        id2_text = row["r2_centroid_index"]
        expected1 = int(id1_text) if id1_text not in {"", "None"} else None
        expected2 = int(id2_text) if id2_text not in {"", "None"} else None
        observed1 = r1_assigner.assign(row["r1_sequence"])
        observed2 = r2_assigner.assign(row["r2_coding_sequence"])
        if observed1 != expected1 or observed2 != expected2:
            reassignment_mismatches.append({"run": row["run"], "read_index": row["read_index"],
                                            "expected": [expected1, expected2], "observed": [observed1, observed2]})
        distance1 = hamming(row["r1_sequence"], r1_centroids[expected1]) if expected1 is not None else None
        distance2 = hamming(row["r2_coding_sequence"], r2_centroids[expected2]) if expected2 is not None else None
        recorded1 = int(row["r1_distance_nt"]) if row["r1_distance_nt"] not in {"", "None"} else None
        recorded2 = int(row["r2_distance_nt"]) if row["r2_distance_nt"] not in {"", "None"} else None
        if distance1 != recorded1 or distance2 != recorded2:
            distance_mismatches.append({"run": row["run"], "read_index": row["read_index"]})
    check("independent_audit_reassignment", not reassignment_mismatches, reassignment_mismatches[:10])
    check("audit_distances", not distance_mismatches, distance_mismatches[:10])

    bad_r1 = [{"id": row["variant_id"], "expected": int(row["r1_seed_exact_reads"]),
               "observed": exact_r1[row["sequence_5prime_300nt"]]}
              for row in rows if int(row["r1_seed_exact_reads"]) != exact_r1[row["sequence_5prime_300nt"]]]
    bad_r2 = [{"id": row["variant_id"], "expected": int(row["r2_seed_exact_reads"]),
               "observed": exact_r2[row["sequence_3prime_279nt"]]}
              for row in linked if int(row["r2_seed_exact_reads"]) != exact_r2[row["sequence_3prime_279nt"]]]
    check("independent_r1_exact_seed_counts", not bad_r1, bad_r1[:10])
    check("independent_r2_exact_seed_counts", not bad_r2, bad_r2[:10])

    artifact_paths = [summary_path, counts_path, args.artifacts / "references_r1.fasta",
                      args.artifacts / "references_paired_ends.fasta", args.artifacts / "all_r1_centroids.fasta",
                      args.artifacts / "all_r2_centroids.fasta", audit_path]
    status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    report = {
        "schema": "a8.rk02.mordstein_recovery_independent.v2",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": status, "scope": args.scope,
        "scientific_library_gate": "NOT_217_REVIEW_REQUIRED" if full and len(rows) != 217 else
                                   "217_CANDIDATES_RECOVERED" if full else "SMOKE_ONLY",
        "prohibited_claims": ["complete CDS recovered", "author GFP_### identity recovered", "SOTA", "generator ready"],
        "artifacts": {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)} for path in artifact_paths},
        "input_hashes": input_hashes, "exact_cache_hashes": cache_hashes,
        "raw_run_metrics": raw_run_metrics, "raw_pairs_recounted": sum(row["pairs"] for row in raw_run_metrics),
        "variants": len(rows), "linked_variants": len(linked),
        "audit_rows_reassigned": len(audit_rows),
        "checks": checks, "passed": sum(item["status"] == "PASS" for item in checks), "total": len(checks),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": status, "passed": report["passed"], "total": report["total"],
                      "scientific_library_gate": report["scientific_library_gate"], "report": str(args.report)}))
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
