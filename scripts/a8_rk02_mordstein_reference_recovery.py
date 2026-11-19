#!/usr/bin/env python3
"""Recover observed-end GFP haplotypes and Flow-seq counts from public reads.

The central 138 nt are not observed by the 2x300 reads and are never imputed.
Reconstructed variant IDs are not asserted to equal the authors' GFP_### IDs.
"""
import argparse
import collections
import csv
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re

import numpy as np

TITLE = "Illumina MiSeq sequencing: Flow-Seq of GFP library without intron in HEK293 cells"
BASES = "TCAG"
AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODON_TABLE = {a+b+c: AAS[i] for i, (a, b, c) in enumerate(
    (a, b, c) for a in BASES for b in BASES for c in BASES)}
COMP = str.maketrans("ACGTN", "TGCAN")
EGFP_PROTEIN = (
    "MVSKGEELFTGVVPILVELDGDVNGHKFSVSGEGEGDATYGKLTLKFICTTGKLPVPWPTLVTTLTYGVQCFSRYP"
    "DHMKQHDFFKSAMPEGYVQERTIFFKDDGNYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNYNSHNVY"
    "IMADKQKNGIKVNFKIRHNIEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSTQSALSKDPNEKRDHMVLLEFVTAA"
    "GITHGMDELYK"
)
R1_PROTEIN = EGFP_PROTEIN[1:101]
R2_SEED_PROTEIN = EGFP_PROTEIN[147:] + "*"
R1_LENGTH = 300
R2_LENGTH = 279
GAP_LENGTH = 720 - 3 - R1_LENGTH - R2_LENGTH


def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def translate(seq):
    return "".join(CODON_TABLE.get(seq[i:i+3], "X") for i in range(0, len(seq) - 2, 3))


def r2_coding(seq):
    # Raw R2 has a 20-nt right primer and one terminal boundary base.
    # RC[1:280] is 279 nt / 93 codons: amino acids 148..239 plus stop.
    return seq.translate(COMP)[::-1][1:1 + R2_LENGTH]


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


def paired_records(r1_path, r2_path=None, allow_truncated=False):
    try:
        if r2_path is None:
            for header, seq in fastq_records(r1_path):
                yield header, seq, None
        else:
            first = iter(fastq_records(r1_path))
            second = iter(fastq_records(r2_path))
            while True:
                try:
                    h1, s1 = next(first)
                    h2, s2 = next(second)
                except StopIteration:
                    return
                id1 = h1.split()[0]
                id2 = h2.split()[0]
                if id1 != id2:
                    raise ValueError(f"Mate order mismatch: {id1} != {id2}")
                yield h1, s1, s2
    except (EOFError, gzip.BadGzipFile):
        if not allow_truncated:
            raise


def read_runs(metadata, raw_root, selected):
    runs = []
    with metadata.open(newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if selected and row["run_accession"] not in selected:
                continue
            if not selected and row["experiment_title"] != TITLE:
                continue
            run = row["run_accession"]
            match = re.search(r"Bin(\d+)", row["library_name"])
            bin_number = int(match.group(1)) if match else None
            r1 = raw_root / run / f"{run}_1.fastq.gz"
            r2 = raw_root / run / f"{run}_2.fastq.gz"
            runs.append({
                "run": run, "library_name": row["library_name"], "bin": bin_number,
                "experiment_title": row["experiment_title"], "r1": r1,
                "r2": r2 if r2.exists() else None,
                "urls": row["fastq_ftp"].split(";"), "md5s": row["fastq_md5"].split(";"),
            })
    if selected and {row["run"] for row in runs} != set(selected):
        raise ValueError("Not all requested runs are present in metadata")
    if not selected:
        if len(runs) != 8 or {row["bin"] for row in runs} != set(range(1, 9)):
            raise ValueError("The full protocol requires exactly HEK293 bins 1..8")
        runs.sort(key=lambda row: row["bin"])
    else:
        runs.sort(key=lambda row: row["run"])
    for row in runs:
        if not row["r1"].exists():
            raise FileNotFoundError(row["r1"])
    return runs


def derive_r2_protein(run, max_reads, allow_truncated):
    counts = [collections.Counter() for _ in range(len(R2_SEED_PROTEIN))]
    used = 0
    if run["r2"] is None:
        return None, {"status": "NO_R2"}
    for _, _, seq in paired_records(run["r1"], run["r2"], allow_truncated):
        if len(seq) == 300:
            coding = r2_coding(seq)
            protein = translate(coding)
            distance = sum(a != b for a, b in zip(protein, R2_SEED_PROTEIN))
            if len(protein) == len(R2_SEED_PROTEIN) and distance <= 1:
                for index, aa in enumerate(protein):
                    counts[index][aa] += 1
                used += 1
        if used >= max_reads:
            break
    if used < 100:
        raise ValueError(f"Insufficient reads to derive R2 protein consensus: {used}")
    consensus = "".join(counter.most_common(1)[0][0] for counter in counts)
    return consensus, {
        "status": "PASS", "source_run": run["run"], "reads_used": used,
        "seed_protein": R2_SEED_PROTEIN, "consensus_protein": consensus,
        "differences_from_seed": [
            {"codon_1based": 148 + i, "seed": a, "observed": b}
            for i, (a, b) in enumerate(zip(R2_SEED_PROTEIN, consensus)) if a != b
        ],
    }


def collect_exact(runs, max_reads, allow_truncated, r2_protein):
    r1_exact = collections.Counter()
    r2_exact = collections.Counter()
    per_run = []
    for run in runs:
        first = collections.Counter()
        second = collections.Counter()
        total = 0
        for _, seq1, seq2 in paired_records(run["r1"], run["r2"], allow_truncated):
            if len(seq1) == R1_LENGTH and translate(seq1) == R1_PROTEIN:
                first[seq1] += 1
            if seq2 is not None and len(seq2) == 300:
                coding = r2_coding(seq2)
                if translate(coding) == r2_protein:
                    second[coding] += 1
            total += 1
            if max_reads and total >= max_reads:
                break
        r1_exact.update(first)
        r2_exact.update(second)
        per_run.append({"run": run["run"], "reads_scanned": total,
                        "r1_orf_valid_reads": sum(first.values()),
                        "r2_orf_valid_reads": sum(second.values())})
        print(json.dumps({"phase": "exact", **per_run[-1]}), flush=True)
    return r1_exact, r2_exact, per_run


def choose_centroids(exact, length, top_n, min_seed, max_error):
    items = sorted(exact.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    centroids = []
    seed_counts = []
    matrix = np.empty((max(1, len(items)), length), dtype=np.uint8)
    for seq, count in items:
        if count < min_seed:
            break
        query = np.frombuffer(seq.encode(), dtype=np.uint8)
        if centroids:
            distances = (matrix[:len(centroids)] != query).sum(axis=1)
            if int(distances.min()) <= max_error:
                continue
        matrix[len(centroids)] = query
        centroids.append(seq)
        seed_counts.append(count)
    return centroids, seed_counts


class SeedAssigner:
    def __init__(self, centroids, max_error):
        self.centroids = centroids
        self.max_error = max_error
        self.length = len(centroids[0]) if centroids else 0
        self.matrix = (np.frombuffer("".join(centroids).encode(), dtype=np.uint8)
                       .reshape(len(centroids), self.length)) if centroids else None
        self.bounds = np.linspace(0, self.length, 10, dtype=int) if centroids else []
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
        ids = sorted(candidates)
        query = np.frombuffer(seq.encode(), dtype=np.uint8)
        distances = (self.matrix[ids] != query).sum(axis=1)
        best = int(distances.min())
        if best > self.max_error or int((distances == best).sum()) != 1:
            return None
        return ids[int(distances.argmin())]


def assign_reads(runs, max_reads, allow_truncated, r1_assigner, r2_assigner):
    n_runs = len(runs)
    r1_counts = np.zeros((len(r1_assigner.centroids), n_runs), dtype=np.int64)
    r2_counts = np.zeros((len(r2_assigner.centroids), n_runs), dtype=np.int64)
    pair_counts = collections.Counter()
    caches = [{"r1": {}, "r2": {}} for _ in runs]
    metrics = []
    for run_index, run in enumerate(runs):
        total = 0
        a1 = a2 = both = 0
        for _, seq1, seq2 in paired_records(run["r1"], run["r2"], allow_truncated):
            cache = caches[run_index]
            if seq1 not in cache["r1"]:
                cache["r1"][seq1] = r1_assigner.assign(seq1)
            id1 = cache["r1"][seq1]
            id2 = None
            if id1 is not None:
                r1_counts[id1, run_index] += 1
                a1 += 1
            if seq2 is not None:
                coding = r2_coding(seq2) if len(seq2) == 300 else ""
                if coding not in cache["r2"]:
                    cache["r2"][coding] = r2_assigner.assign(coding)
                id2 = cache["r2"][coding]
                if id2 is not None:
                    r2_counts[id2, run_index] += 1
                    a2 += 1
            if id1 is not None and id2 is not None:
                pair_counts[(id1, id2)] += 1
                both += 1
            total += 1
            if max_reads and total >= max_reads:
                break
        metrics.append({"run": run["run"], "library_name": run["library_name"], "bin": run["bin"],
                        "pairs_scanned": total, "r1_assigned": a1, "r2_assigned": a2,
                        "both_assigned": both,
                        "r1_assignment_fraction": a1 / total if total else None,
                        "r2_assignment_fraction": a2 / total if total else None})
        print(json.dumps({"phase": "assign", **metrics[-1]}), flush=True)
    return r1_counts, r2_counts, pair_counts, metrics


def write_outputs(args, runs, r1_centroids, r2_centroids, r1_seed_counts, r2_seed_counts,
                  r1_counts, r2_counts, pair_counts, metrics, exact_metrics,
                  r2_protein, r2_provenance, input_files):
    r1_totals = r1_counts.sum(axis=1)
    r2_totals = r2_counts.sum(axis=1)
    selected = [cid for cid, total in enumerate(r1_totals) if total >= args.min_variant_support]
    selected.sort(key=lambda cid: (-int(r1_totals[cid]), r1_centroids[cid]))
    best_r2 = {}
    pair_support = collections.Counter()
    for (id1, id2), count in pair_counts.items():
        pair_support[id1] += count
        if id1 not in best_r2 or (count, -id2) > (best_r2[id1][1], -best_r2[id1][0]):
            best_r2[id1] = (id2, count)
    mutual = 0
    rows = []
    for new_id, cid in enumerate(selected, 1):
        link = best_r2.get(cid)
        r2_id, linked_count = link if link else (None, 0)
        reverse_best = None
        if r2_id is not None:
            candidates = [(count, id1) for (id1, id2), count in pair_counts.items() if id2 == r2_id]
            reverse_best = max(candidates)[1] if candidates else None
        is_mutual = reverse_best == cid
        mutual += int(is_mutual)
        counts = r1_counts[cid].astype(int).tolist()
        score = None
        if len(runs) == 8 and {row["bin"] for row in runs} == set(range(1, 9)):
            score = sum((i + 1) * count for i, count in enumerate(counts)) / sum(counts)
        row = {
            "variant_id": f"CF_MORD_{new_id:04d}", "r1_centroid_index": cid,
            "r1_seed_exact_reads": r1_seed_counts[cid], "r1_assigned_reads": int(r1_totals[cid]),
            "r2_centroid_index": r2_id if r2_id is not None else "",
            "r2_seed_exact_reads": r2_seed_counts[r2_id] if r2_id is not None else "",
            "paired_reads": linked_count,
            "r1_pair_purity": linked_count / pair_support[cid] if pair_support[cid] else None,
            "mutual_best_r2": is_mutual,
            "central_gap_nt": GAP_LENGTH, "sequence_5prime_300nt": r1_centroids[cid],
            "sequence_3prime_279nt": r2_centroids[r2_id] if r2_id is not None else "",
            "flowseq_score_r1_only": score,
        }
        for index, run in enumerate(runs):
            label = f"bin{run['bin']}" if run["bin"] is not None else run["run"]
            row[f"counts_{label}"] = counts[index]
        rows.append(row)
    args.output.mkdir(parents=True, exist_ok=False)
    count_columns = [key for key in rows[0] if key.startswith("counts_")] if rows else []
    fieldnames = (["variant_id", "r1_centroid_index", "r1_seed_exact_reads", "r1_assigned_reads",
                   "r2_centroid_index", "r2_seed_exact_reads", "paired_reads", "r1_pair_purity",
                   "mutual_best_r2", "central_gap_nt", "flowseq_score_r1_only"] + count_columns +
                  ["sequence_5prime_300nt", "sequence_3prime_279nt"])
    with (args.output / "variant_counts.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with (args.output / "references_r1.fasta").open("w") as handle:
        for row in rows:
            handle.write(f">{row['variant_id']} observed=CDS_4_303\n{row['sequence_5prime_300nt']}\n")
    with (args.output / "references_paired_ends.fasta").open("w") as handle:
        for row in rows:
            if row["sequence_3prime_279nt"]:
                seq = "ATG" + row["sequence_5prime_300nt"] + "N" * GAP_LENGTH + row["sequence_3prime_279nt"]
                handle.write(f">{row['variant_id']} observed=CDS_4_303,CDS_442_720 gap_nt=138\n{seq}\n")
    sensitivity = {str(threshold): int((r1_totals >= threshold).sum())
                   for threshold in [20, 50, 100, 200, 500, 1000, 2000, 5000]}
    full = len(runs) == 8 and {row["bin"] for row in runs} == set(range(1, 9))
    checks = {
        "gap_is_138nt": GAP_LENGTH == 138,
        "r1_length_is_300": all(len(row["sequence_5prime_300nt"]) == 300 for row in rows),
        "r2_length_is_279_when_linked": all(not row["sequence_3prime_279nt"] or len(row["sequence_3prime_279nt"]) == 279 for row in rows),
        "support_threshold_respected": all(row["r1_assigned_reads"] >= args.min_variant_support for row in rows),
        "scores_in_1_to_8": all(row["flowseq_score_r1_only"] is None or 1 <= row["flowseq_score_r1_only"] <= 8 for row in rows),
        "reconstructed_ids_not_author_ids": all(row["variant_id"].startswith("CF_MORD_") for row in rows),
        "r1_centroids_nonempty": bool(r1_centroids),
    }
    if full:
        completeness = "EXACT_217_CANDIDATES" if len(rows) == 217 else "REVIEW_REQUIRED_COUNT_NOT_217"
    else:
        completeness = "SMOKE_PARTIAL_LIBRARY"
    status = "PASS_PENDING_INDEPENDENT_VERIFICATION" if all(checks.values()) else "FAIL"
    summary = {
        "schema": "a8.rk02.mordstein_observed_end_recovery.v1",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": status, "library_recovery_status": completeness,
        "scope": "Observed 5'/3' GFP ends and R1-based Flow-seq counts; central 138 nt unobserved",
        "prohibited_claims": ["complete CDS recovered", "author GFP_### identity recovered", "SOTA", "generator ready"],
        "runs": [{key: (str(value) if isinstance(value, Path) else value) for key, value in run.items()
                  if key not in {"urls", "md5s"}} for run in runs],
        "input_files": input_files, "exact_collection": exact_metrics, "run_metrics": metrics,
        "r1_protein_reference": R1_PROTEIN, "r2_protein_reference": r2_protein,
        "r2_protein_provenance": r2_provenance,
        "parameters": {"max_error_nt": args.max_error, "top_exact": args.top_exact,
                       "min_centroid_seed_reads": args.min_seed,
                       "min_variant_support": args.min_variant_support,
                       "max_reads_per_run": args.max_reads},
        "r1_centroids": len(r1_centroids), "r2_centroids": len(r2_centroids),
        "variants_retained": len(rows), "mutual_best_links": mutual,
        "support_threshold_sensitivity": sensitivity,
        "selected_r1_assigned_reads": int(sum(row["r1_assigned_reads"] for row in rows)),
        "checks": checks,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": status, "library_recovery_status": completeness,
                      "variants_retained": len(rows), "mutual_best_links": mutual,
                      "output": str(args.output)}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", default="")
    parser.add_argument("--max-reads", type=int, default=0)
    parser.add_argument("--allow-truncated", action="store_true")
    parser.add_argument("--top-exact", type=int, default=20000)
    parser.add_argument("--min-seed", type=int, default=20)
    parser.add_argument("--min-variant-support", type=int, default=1000)
    parser.add_argument("--max-error", type=int, default=8)
    args = parser.parse_args()
    if args.max_error != 8:
        raise ValueError("The nine-segment exact-seed proof is frozen at max_error=8")
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {args.output}")
    selected = {value for value in args.runs.split(",") if value}
    runs = read_runs(args.metadata, args.raw_root, selected)
    input_files = []
    for run in runs:
        for key in ["r1", "r2"]:
            path = run[key]
            if path is not None:
                input_files.append({"run": run["run"], "mate": key, "path": str(path),
                                    "bytes": path.stat().st_size, "sha256": sha256(path)})
    r2_run = next((run for run in runs if run["r2"] is not None), None)
    if r2_run is not None:
        r2_protein, r2_provenance = derive_r2_protein(r2_run, min(args.max_reads or 50000, 50000), args.allow_truncated)
    else:
        r2_protein, r2_provenance = None, {"status": "NO_R2"}
    r1_exact, r2_exact, exact_metrics = collect_exact(
        runs, args.max_reads, args.allow_truncated, r2_protein)
    r1_centroids, r1_seed_counts = choose_centroids(r1_exact, R1_LENGTH, args.top_exact, args.min_seed, args.max_error)
    r2_centroids, r2_seed_counts = choose_centroids(r2_exact, R2_LENGTH, args.top_exact, args.min_seed, args.max_error)
    if not r1_centroids:
        raise ValueError("No R1 centroids passed the frozen seed threshold")
    if not r2_centroids:
        r2_centroids, r2_seed_counts = [], []
    print(json.dumps({"phase": "centroids", "r1": len(r1_centroids), "r2": len(r2_centroids)}), flush=True)
    r1_assigner = SeedAssigner(r1_centroids, args.max_error)
    r2_assigner = SeedAssigner(r2_centroids, args.max_error)
    r1_counts, r2_counts, pair_counts, metrics = assign_reads(
        runs, args.max_reads, args.allow_truncated, r1_assigner, r2_assigner)
    write_outputs(args, runs, r1_centroids, r2_centroids, r1_seed_counts, r2_seed_counts,
                  r1_counts, r2_counts, pair_counts, metrics, exact_metrics,
                  r2_protein, r2_provenance, input_files)


if __name__ == "__main__":
    main()
