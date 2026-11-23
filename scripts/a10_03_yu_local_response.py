#!/usr/bin/env python3
import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

PROTOCOL = "a10_03_yu_local_response_v1"
SCHEMA = "a10-03-yu-local-response-summary-v1"
CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L", "TCT": "S", "TCC": "S",
    "TCA": "S", "TCG": "S", "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W", "CTT": "L", "CTC": "L",
    "CTA": "L", "CTG": "L", "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q", "CGT": "R", "CGC": "R",
    "CGA": "R", "CGG": "R", "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T", "AAT": "N", "AAC": "N",
    "AAA": "K", "AAG": "K", "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V", "GCT": "A", "GCC": "A",
    "GCA": "A", "GCG": "A", "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}
FIELDS = [
    "codon_one_based", "region", "opt_codon", "cwt_opt_codon", "same_codon",
    "opt_rpm", "cwt_opt_rpm", "cwt_opt_minus_opt_rpm", "cwt_opt_over_opt_rpm",
    "opt_upstream_normalized", "cwt_opt_upstream_normalized",
    "cwt_opt_minus_opt_upstream_normalized", "cwt_opt_over_opt_upstream_normalized",
]


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, payload):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def load_protocol(path):
    with Path(path).open(encoding="utf-8") as handle:
        protocol = json.load(handle)
    if protocol.get("schema") != "a10-03-yu-local-response-protocol-v1" or protocol.get("protocol") != PROTOCOL:
        raise ValueError("Yu local-response protocol identity mismatch")
    scope = protocol["scope"]
    if not all((scope["development_only"], scope["descriptive_only"], scope["one_run_per_construct"])):
        raise ValueError("Yu analysis must remain descriptive development evidence")
    if any((scope["causal_claim"], scope["gate_pass_by_this_analysis_alone"], scope["untouched"])):
        raise ValueError("Yu analysis cannot make causal, Gate or untouched claims")
    if scope["independent_biological_replicates"] != 0:
        raise ValueError("Yu has no independent biological replicate in this construct pair")
    processing = protocol["processing"]
    if processing["pseudocount"] is not None or processing["statistical_tests"] is not None:
        raise ValueError("no pseudocount or inferential test was frozen")
    if processing["p_values"] is not None or processing["confidence_intervals"] is not None:
        raise ValueError("one run per construct cannot support the forbidden inference")
    return protocol


def read_reporter_fasta(path, reporter, expected_length):
    records = {}
    name = None
    with gzip.open(path, "rt", encoding="ascii", errors="strict") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                name = line[1:].split()[0]
                if name in records:
                    raise ValueError(f"duplicate FASTA identifier: {name}")
                records[name] = []
            elif name is None:
                raise ValueError("FASTA sequence precedes its header")
            else:
                records[name].append(line.upper())
    if reporter not in records:
        raise ValueError(f"missing reporter {reporter}")
    sequence = "".join(records[reporter])
    if len(sequence) != expected_length or set(sequence) - set("ACGT"):
        raise ValueError("reporter length or alphabet mismatch")
    return sequence


def read_reporter_wig(path, reporter, expected_length):
    values = [None] * expected_length
    intervals = 0
    with gzip.open(path, "rt", encoding="ascii", errors="strict") as handle:
        for line_number, line in enumerate(handle, 1):
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 4 or fields[0] != reporter:
                continue
            start, end = int(fields[1]), int(fields[2])
            value = float(fields[3])
            if start < 0 or end <= start or end > expected_length or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid reporter WIG interval at line {line_number}")
            if any(item is not None for item in values[start:end]):
                raise ValueError(f"overlapping reporter WIG interval at line {line_number}")
            values[start:end] = [value] * (end - start)
            intervals += 1
    if not intervals or any(item is None for item in values):
        raise ValueError("reporter WIG does not continuously cover the full construct")
    return values, intervals


def translate(cds):
    if len(cds) % 3:
        raise ValueError("CDS length is not divisible by three")
    amino_acids = []
    for offset in range(0, len(cds), 3):
        codon = cds[offset:offset + 3]
        if codon not in CODON_TABLE:
            raise ValueError("invalid CDS codon")
        amino_acids.append(CODON_TABLE[codon])
    if amino_acids[-1] != "*" or "*" in amino_acids[:-1]:
        raise ValueError("CDS must have exactly one terminal stop")
    return "".join(amino_acids[:-1])


def ratio(numerator, denominator):
    return numerator / denominator if numerator > 0 and denominator > 0 else None


def mean(values):
    return sum(values) / len(values) if values else None


def analyze(protocol, paths):
    geometry = protocol["geometry"]
    length = geometry["reporter_length_nt"]
    cds_start = geometry["cds_start_zero_based"]
    cds_end = geometry["cds_end_zero_based_exclusive"]
    edit_start = cds_start + 3 * (geometry["edited_sense_codon_first_one_based"] - 1)
    edit_end = cds_start + 3 * geometry["edited_sense_codon_last_one_based"]
    sequences, wig_values, interval_counts = {}, {}, {}
    for arm, config in protocol["constructs"].items():
        if sha256_file(paths[arm]["fasta"]) != config["fasta_sha256"]:
            raise ValueError(f"{arm} FASTA SHA256 mismatch")
        if sha256_file(paths[arm]["wig"]) != config["wig_sha256"]:
            raise ValueError(f"{arm} WIG SHA256 mismatch")
        sequences[arm] = read_reporter_fasta(paths[arm]["fasta"], config["reporter"], length)
        wig_values[arm], interval_counts[arm] = read_reporter_wig(
            paths[arm]["wig"], config["reporter"], length,
        )
    opt, cwt = sequences["opt"], sequences["cwt_opt"]
    if translate(opt[cds_start:cds_end]) != translate(cwt[cds_start:cds_end]):
        raise ValueError("construct proteins differ")
    differences = [index for index, (a, b) in enumerate(zip(opt, cwt)) if a != b]
    if any(index < edit_start or index >= cds_end for index in differences):
        raise ValueError("sequence differences extend beyond the frozen C-terminal edit/stop")
    if any(opt[index:index + 3] != cwt[index:index + 3] for index in range(cds_start, edit_start, 3)):
        raise ValueError("upstream normalization region is not sequence-identical")
    upstream_rpm = {
        arm: mean(values[cds_start:edit_start]) for arm, values in wig_values.items()
    }
    if any(value <= 0 for value in upstream_rpm.values()):
        raise ValueError("upstream normalization mean must be positive")
    rows = []
    for codon_index, start in enumerate(range(cds_start, cds_end, 3), 1):
        end = start + 3
        if start < edit_start:
            region = "unchanged_upstream"
        elif start < edit_end:
            region = "edited_sense"
        else:
            region = "terminal_stop"
        opt_rpm = mean(wig_values["opt"][start:end])
        cwt_rpm = mean(wig_values["cwt_opt"][start:end])
        opt_normalized = opt_rpm / upstream_rpm["opt"]
        cwt_normalized = cwt_rpm / upstream_rpm["cwt_opt"]
        rows.append({
            "codon_one_based": codon_index,
            "region": region,
            "opt_codon": opt[start:end],
            "cwt_opt_codon": cwt[start:end],
            "same_codon": opt[start:end] == cwt[start:end],
            "opt_rpm": opt_rpm,
            "cwt_opt_rpm": cwt_rpm,
            "cwt_opt_minus_opt_rpm": cwt_rpm - opt_rpm,
            "cwt_opt_over_opt_rpm": ratio(cwt_rpm, opt_rpm),
            "opt_upstream_normalized": opt_normalized,
            "cwt_opt_upstream_normalized": cwt_normalized,
            "cwt_opt_minus_opt_upstream_normalized": cwt_normalized - opt_normalized,
            "cwt_opt_over_opt_upstream_normalized": ratio(cwt_normalized, opt_normalized),
        })
    region_summary = {}
    for region in ("unchanged_upstream", "edited_sense", "terminal_stop"):
        selected = [row for row in rows if row["region"] == region]
        region_summary[region] = {
            "codons": len(selected),
            "sequence_different_codons": sum(not row["same_codon"] for row in selected),
            "mean_opt_rpm": mean([row["opt_rpm"] for row in selected]),
            "mean_cwt_opt_rpm": mean([row["cwt_opt_rpm"] for row in selected]),
            "mean_cwt_opt_minus_opt_rpm": mean([row["cwt_opt_minus_opt_rpm"] for row in selected]),
            "mean_cwt_opt_minus_opt_upstream_normalized": mean([
                row["cwt_opt_minus_opt_upstream_normalized"] for row in selected
            ]),
            "positive_rpm_pairs": sum(row["cwt_opt_over_opt_rpm"] is not None for row in selected),
        }
    summary = {
        "schema": SCHEMA,
        "protocol": PROTOCOL,
        "scope": protocol["scope"],
        "source": protocol["source"],
        "constructs": protocol["constructs"],
        "geometry": protocol["geometry"],
        "processing": protocol["processing"],
        "input_sha256": {
            arm: {kind: sha256_file(path) for kind, path in inputs.items()}
            for arm, inputs in paths.items()
        },
        "qc": {
            "reporter_length_nt": length,
            "protein_length_aa": len(translate(opt[cds_start:cds_end])),
            "protein_identical": True,
            "different_nucleotides": len(differences),
            "first_difference_zero_based": min(differences),
            "last_difference_zero_based": max(differences),
            "opt_terminal_stop": opt[edit_end:cds_end],
            "cwt_opt_terminal_stop": cwt[edit_end:cds_end],
            "wig_intervals": interval_counts,
            "wig_complete_contiguous_coverage": True,
            "upstream_normalization_mean_rpm": upstream_rpm,
            "downstream_coding_region_available": False,
        },
        "regions": region_summary,
        "statistical_inference": {
            "biological_replicates_per_construct": 0,
            "runs_per_construct": 1,
            "p_values": None,
            "confidence_intervals": None,
            "reason": "One run per construct; descriptive paired contrast only",
        },
        "claim_boundary": "Descriptive local synonymous occupancy contrast; not causal evidence, final research OOD, SOTA or an independent G1 pass",
    }
    return rows, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--opt-fasta", required=True)
    parser.add_argument("--cwt-opt-fasta", required=True)
    parser.add_argument("--opt-wig", required=True)
    parser.add_argument("--cwt-opt-wig", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    paths = {
        "opt": {"fasta": args.opt_fasta, "wig": args.opt_wig},
        "cwt_opt": {"fasta": args.cwt_opt_fasta, "wig": args.cwt_opt_wig},
    }
    rows, summary = analyze(protocol, paths)
    with (output / "codon_response.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary["artifact_sha256"] = {
        "codon_response.csv": sha256_file(output / "codon_response.csv")
    }
    write_json(output / "summary.json", summary)


if __name__ == "__main__":
    main()
