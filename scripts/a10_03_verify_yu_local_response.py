#!/usr/bin/env python3
import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def close(actual, expected):
    if actual is None or expected is None:
        return actual is expected
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(expected, (float, int)):
        return math.isclose(float(actual), float(expected), rel_tol=1e-10, abs_tol=1e-10)
    return actual == expected


def require_equal(actual, expected, label):
    if not close(actual, expected):
        raise ValueError(f"independent mismatch for {label}: {actual!r} != {expected!r}")


def load_wig(path, reporter, length):
    result = []
    previous_end = 0
    with gzip.open(path, "rt", encoding="ascii") as handle:
        for line in handle:
            fields = line.rstrip().split("\t")
            if len(fields) != 4 or fields[0] != reporter:
                continue
            start, end, value = int(fields[1]), int(fields[2]), float(fields[3])
            if start != previous_end or end <= start or not math.isfinite(value) or value < 0:
                raise ValueError("independent WIG parsing found a gap, overlap or invalid value")
            result.extend([value] * (end - start))
            previous_end = end
    if len(result) != length:
        raise ValueError("independent WIG parsing does not cover the reporter")
    return result


def read_fasta(path, reporter):
    sequences = {}
    with gzip.open(path, "rt", encoding="ascii") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                name = line[1:].split()[0]
                sequences[name] = []
            else:
                sequences[name].append(line)
    return "".join(sequences[reporter]).upper()


def protein(sequence, start, end):
    code = "FFLLSSSSYY**CC*W" + "LLLLPPPPHHQQRRRR" + "IIIMTTTTNNKKSSRR" + "VVVVAAAADDEEGGGG"
    mapping = {a + b + c: code[index] for index, (a, b, c) in enumerate(
        (a, b, c) for a in "TCAG" for b in "TCAG" for c in "TCAG"
    )}
    translated = "".join(mapping[sequence[index:index + 3]] for index in range(start, end, 3))
    if translated[-1] != "*" or "*" in translated[:-1]:
        raise ValueError("independent FASTA translation found invalid stop geometry")
    return translated[:-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--opt-fasta", required=True)
    parser.add_argument("--cwt-opt-fasta", required=True)
    parser.add_argument("--opt-wig", required=True)
    parser.add_argument("--cwt-opt-wig", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with Path(args.protocol).open(encoding="utf-8") as handle:
        protocol = json.load(handle)
    output_dir = Path(args.output_dir)
    with (output_dir / "summary.json").open(encoding="utf-8") as handle:
        summary = json.load(handle)
    if summary["protocol"] != protocol["protocol"] or summary["schema"] != "a10-03-yu-local-response-summary-v1":
        raise ValueError("summary/protocol identity mismatch")
    if summary["scope"] != protocol["scope"] or summary["processing"] != protocol["processing"]:
        raise ValueError("scope or processing contract was altered")
    paths = {
        "opt": {"fasta": args.opt_fasta, "wig": args.opt_wig},
        "cwt_opt": {"fasta": args.cwt_opt_fasta, "wig": args.cwt_opt_wig},
    }
    values = {}
    sequences = {}
    for arm, config in protocol["constructs"].items():
        require_equal(sha256(paths[arm]["fasta"]), config["fasta_sha256"], f"{arm} FASTA SHA")
        require_equal(sha256(paths[arm]["wig"]), config["wig_sha256"], f"{arm} WIG SHA")
        sequences[arm] = read_fasta(paths[arm]["fasta"], config["reporter"])
        values[arm] = load_wig(
            paths[arm]["wig"], config["reporter"], protocol["geometry"]["reporter_length_nt"],
        )
    geometry = protocol["geometry"]
    cds_start = geometry["cds_start_zero_based"]
    cds_end = geometry["cds_end_zero_based_exclusive"]
    edit_start = cds_start + 3 * (geometry["edited_sense_codon_first_one_based"] - 1)
    edit_end = cds_start + 3 * geometry["edited_sense_codon_last_one_based"]
    opt_protein = protein(sequences["opt"], cds_start, cds_end)
    cwt_protein = protein(sequences["cwt_opt"], cds_start, cds_end)
    require_equal(opt_protein, cwt_protein, "independent protein identity")
    require_equal(len(opt_protein), summary["qc"]["protein_length_aa"], "protein length")
    differences = [i for i, pair in enumerate(zip(sequences["opt"], sequences["cwt_opt"])) if pair[0] != pair[1]]
    if any(i < edit_start or i >= cds_end for i in differences):
        raise ValueError("independent sequence audit found differences outside edit/stop")
    require_equal(len(differences), summary["qc"]["different_nucleotides"], "different nucleotide count")
    require_equal(sequences["opt"][edit_end:cds_end], "TGA", "OPT stop")
    require_equal(sequences["cwt_opt"][edit_end:cds_end], "TAA", "Cwt-Opt stop")
    upstream = {arm: sum(x[cds_start:edit_start]) / (edit_start - cds_start) for arm, x in values.items()}
    for arm in upstream:
        require_equal(upstream[arm], summary["qc"]["upstream_normalization_mean_rpm"][arm], f"{arm} upstream mean")
    with (output_dir / "codon_response.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    require_equal(len(rows), (cds_end - cds_start) // 3, "codon row count")
    recomputed = []
    for index, row in enumerate(rows):
        start = cds_start + index * 3
        end = start + 3
        region = "unchanged_upstream" if start < edit_start else "edited_sense" if start < edit_end else "terminal_stop"
        opt = sum(values["opt"][start:end]) / 3
        cwt = sum(values["cwt_opt"][start:end]) / 3
        opt_normalized = opt / upstream["opt"]
        cwt_normalized = cwt / upstream["cwt_opt"]
        require_equal(row["region"], region, f"row {index + 1} region")
        require_equal(int(row["codon_one_based"]), index + 1, f"row {index + 1} number")
        for field, expected in {
            "opt_rpm": opt,
            "cwt_opt_rpm": cwt,
            "cwt_opt_minus_opt_rpm": cwt - opt,
            "cwt_opt_over_opt_rpm": cwt / opt if opt > 0 and cwt > 0 else None,
            "opt_upstream_normalized": opt_normalized,
            "cwt_opt_upstream_normalized": cwt_normalized,
            "cwt_opt_minus_opt_upstream_normalized": cwt_normalized - opt_normalized,
            "cwt_opt_over_opt_upstream_normalized": cwt_normalized / opt_normalized if opt > 0 and cwt > 0 else None,
        }.items():
            actual = None if row[field] == "" else float(row[field])
            require_equal(actual, expected, f"row {index + 1} {field}")
        recomputed.append({"region": region, "rpm_difference": cwt - opt, "normalized_difference": cwt_normalized - opt_normalized})
    for region, reported in summary["regions"].items():
        selected = [row for row in recomputed if row["region"] == region]
        require_equal(len(selected), reported["codons"], f"{region} codons")
        require_equal(sum(x["rpm_difference"] for x in selected) / len(selected), reported["mean_cwt_opt_minus_opt_rpm"], f"{region} RPM effect")
        require_equal(sum(x["normalized_difference"] for x in selected) / len(selected), reported["mean_cwt_opt_minus_opt_upstream_normalized"], f"{region} normalized effect")
    require_equal(summary["statistical_inference"]["biological_replicates_per_construct"], 0, "replicate boundary")
    require_equal(summary["statistical_inference"]["p_values"], None, "P-value boundary")
    require_equal(summary["statistical_inference"]["confidence_intervals"], None, "CI boundary")
    require_equal(sha256(output_dir / "codon_response.csv"), summary["artifact_sha256"]["codon_response.csv"], "CSV SHA")
    report = {
        "schema": "a10-03-yu-local-response-independent-verification-v1",
        "protocol": protocol["protocol"],
        "passed": True,
        "checks": {
            "raw_sha256": 4,
            "wig_reconstruction": 2,
            "protein_and_edit_geometry_recomputed": True,
            "codon_rows_recomputed": len(rows),
            "region_summaries_recomputed": len(summary["regions"]),
            "replicate_and_inference_boundaries": True,
        },
        "sha256": {
            "summary.json": sha256(output_dir / "summary.json"),
            "codon_response.csv": sha256(output_dir / "codon_response.csv"),
        },
        "claim_boundary": summary["claim_boundary"],
    }
    with Path(args.output).open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


if __name__ == "__main__":
    main()
