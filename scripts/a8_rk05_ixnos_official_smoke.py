#!/usr/bin/env python3
"""Bounded, real-data iXnos official-workflow smoke; not a paper reproduction."""
import argparse
import datetime
import gzip
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request

SOURCE_SHA = "523e6105acdf52d792d96c272594655b2765a9c369892f78bac9452f7d20c1c8"
SOURCE_COMMIT = "1ea2337dd24d1e6fa3859f08573e99f02512810f"
ENA_API = ("https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRR1049521"
           "&result=read_run&fields=run_accession,fastq_ftp,fastq_bytes,fastq_md5,"
           "read_count,base_count&format=json")
FASTQ_URL = "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR104/001/SRR1049521/SRR1049521.fastq.gz"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, obj):
    with open(path, "w") as handle:
        json.dump(obj, handle, indent=2, sort_keys=True)
        handle.write("\n")


def run_logged(command, log_path, env=None):
    with open(log_path, "wb") as log:
        log.write(("COMMAND " + " ".join(command) + "\n").encode())
        log.flush()
        proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
        code = proc.wait()
    if code != 0:
        raise RuntimeError("command failed (%d): %s; see %s" % (code, " ".join(command), log_path))


def fastq_qc(path):
    lengths = {}
    records = 0
    ids = set()
    with open(path, "r") as handle:
        while True:
            name = handle.readline()
            if not name:
                break
            seq = handle.readline()
            plus = handle.readline()
            qual = handle.readline()
            if not (seq and plus and qual) or not name.startswith("@") or not plus.startswith("+"):
                raise ValueError("invalid or truncated FASTQ record %d in %s" % (records, path))
            seq = seq.rstrip("\r\n")
            qual = qual.rstrip("\r\n")
            if len(seq) != len(qual):
                raise ValueError("sequence/quality length mismatch at record %d" % records)
            lengths[len(seq)] = lengths.get(len(seq), 0) + 1
            ids.add(name.split()[0])
            records += 1
    return {"records": records, "unique_read_names": len(ids),
            "read_length_counts": {str(k): lengths[k] for k in sorted(lengths)}}


def download_prefix(run_dir, reads, log_path):
    raw_dir = os.path.join(run_dir, "raw")
    metadata_path = os.path.join(raw_dir, "ena_SRR1049521.json")
    with urllib.request.urlopen(ENA_API, timeout=90) as response:
        metadata = json.loads(response.read().decode("utf-8"))
    if len(metadata) != 1 or metadata[0].get("run_accession") != "SRR1049521":
        raise ValueError("unexpected ENA metadata")
    write_json(metadata_path, metadata)
    out_path = os.path.join(raw_dir, "SRR1049521.first_%d.fastq" % reads)
    started = time.time()
    bytes_compressed = 0
    with urllib.request.urlopen(FASTQ_URL, timeout=120) as response:
        compressed_length = response.headers.get("Content-Length")
        with gzip.GzipFile(fileobj=response, mode="rb") as source, open(out_path, "wb") as out:
            remaining = reads * 4
            for line in source:
                out.write(line)
                remaining -= 1
                if remaining == 0:
                    break
            if remaining != 0:
                raise ValueError("ENA stream ended before requested prefix")
        # Accessing the underlying stream is intentionally avoided after prefix completion.
    elapsed = time.time() - started
    qc = fastq_qc(out_path)
    if qc["records"] != reads or qc["unique_read_names"] != reads:
        raise ValueError("prefix FASTQ QC failed")
    qc.update({
        "run_accession": "SRR1049521",
        "source_url": FASTQ_URL,
        "source_full_fastq_bytes_from_ena": metadata[0].get("fastq_bytes"),
        "source_full_fastq_md5_from_ena_not_computed_here": metadata[0].get("fastq_md5"),
        "source_full_read_count_from_ena": metadata[0].get("read_count"),
        "http_content_length_header": compressed_length,
        "prefix_strategy": "first N complete FASTQ records from the ENA gzip stream; no random sampling claim",
        "download_wall_seconds": elapsed,
        "path": out_path,
        "bytes": os.path.getsize(out_path),
        "sha256": sha256(out_path),
    })
    write_json(os.path.join(raw_dir, "prefix_qc.json"), qc)
    with open(log_path, "w") as log:
        log.write(json.dumps(qc, indent=2, sort_keys=True) + "\n")
    return qc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--source-archive", required=True)
    parser.add_argument("--py27-site-packages", required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--prefix-reads", type=int, default=1000000)
    parser.add_argument("--seed", type=int, default=20261118)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--bowtie-threads", type=int, default=4)
    parser.add_argument("--train-genes", type=int, default=20)
    parser.add_argument("--test-genes", type=int, default=10)
    parser.add_argument("--min-counts", type=int, default=50)
    parser.add_argument("--min-codons", type=int, default=20)
    args = parser.parse_args()
    if args.prefix_reads <= 0 or args.epochs <= 0 or min(args.train_genes, args.test_genes) <= 0:
        raise ValueError("reads, epochs, and gene-set sizes must be positive")
    run_dir = os.path.abspath(args.run_dir)
    source_root = os.path.abspath(args.source_root)
    if os.path.exists(run_dir):
        raise FileExistsError("run directory already exists; use a new versioned directory: " + run_dir)
    if sha256(args.source_archive) != SOURCE_SHA:
        raise ValueError("iXnos source archive SHA256 mismatch")
    if not os.path.isfile(args.driver):
        raise FileNotFoundError(args.driver)
    started = time.time()
    for sub in ("raw", "logs", "genome", os.path.join("weinberg", "process")):
        os.makedirs(os.path.join(run_dir, sub))
    config = vars(args).copy()
    config.update({
        "task": "RK05 iXnos bounded official prefix-read training smoke",
        "source_repository": "https://github.com/lareaulab/iXnos",
        "source_commit": SOURCE_COMMIT,
        "source_archive_sha256": SOURCE_SHA,
        "scientific_scope": "bounded real-data prefix smoke only; not full-run, not paper-performance reproduction, not OOD, not CodonFlow comparison",
        "mapping_weights": "official simple uniform multimapping weights; RSEM not used",
        "feature_window": "codons -5..4 and nucleotides -15..14",
        "model": "official FeedforwardMLP tanh [200], Nesterov, nonnegative output",
        "final_epoch_rule": "last epoch only; official test loss is logged each epoch but no best-test checkpoint is selected",
    })
    write_json(os.path.join(run_dir, "run_config.json"), config)
    prefix = download_prefix(run_dir, args.prefix_reads, os.path.join(run_dir, "logs", "download.log"))
    process_dir = os.path.join(run_dir, "weinberg", "process")
    trimmer = os.path.join(source_root, "expts", "weinberg", "process", "trim_linker_weinberg.pl")
    raw_fastq = prefix["path"]
    trimmed = os.path.join(process_dir, "SRR1049521.trimmed.fastq")
    with open(raw_fastq, "rb") as source, open(trimmed, "wb") as out, open(os.path.join(run_dir, "logs", "trimmer.log"), "wb") as log:
        proc = subprocess.Popen(["perl", trimmer], stdin=source, stdout=out, stderr=log)
        if proc.wait() != 0:
            raise RuntimeError("official Weinberg linker trimmer failed")
    trim_qc = fastq_qc(trimmed)
    trim_qc.update({"path": trimmed, "bytes": os.path.getsize(trimmed), "sha256": sha256(trimmed)})
    write_json(os.path.join(process_dir, "trimmed_qc.json"), trim_qc)

    genome = os.path.join(source_root, "genome_data")
    transcript_fa = os.path.join(genome, "scer.transcripts.13cds10.fa")
    transcript_index = os.path.join(run_dir, "genome", "scer.transcripts.13cds10")
    run_logged(["bowtie-build", transcript_fa, transcript_index], os.path.join(run_dir, "logs", "bowtie_build.log"))
    not_rrna = os.path.join(process_dir, "weinberg.not_rrna.fastq")
    rrna_sam = os.path.join(process_dir, "weinberg.rrna.sam")
    with open(rrna_sam, "wb") as out, open(os.path.join(run_dir, "logs", "bowtie_rrna.log"), "wb") as log:
        proc = subprocess.Popen(["bowtie", "-v", "2", "-p", str(args.bowtie_threads), "-S", "--un", not_rrna,
                                 os.path.join(genome, "ScerRRNA"), trimmed], stdout=out, stderr=log)
        if proc.wait() != 0:
            raise RuntimeError("rRNA Bowtie filtering failed")
    not_ncrna = os.path.join(process_dir, "weinberg.not_ncrna.fastq")
    ncrna_sam = os.path.join(process_dir, "weinberg.ncrna.sam")
    with open(ncrna_sam, "wb") as out, open(os.path.join(run_dir, "logs", "bowtie_ncrna.log"), "wb") as log:
        proc = subprocess.Popen(["bowtie", "-v", "2", "-p", str(args.bowtie_threads), "-S", "--un", not_ncrna,
                                 os.path.join(genome, "rna_coding"), not_rrna], stdout=out, stderr=log)
        if proc.wait() != 0:
            raise RuntimeError("noncoding-RNA Bowtie filtering failed")
    footprints = os.path.join(process_dir, "weinberg.footprints.sam")
    unmapped = os.path.join(process_dir, "weinberg.unmapped.fastq")
    with open(footprints, "wb") as out, open(os.path.join(run_dir, "logs", "bowtie_footprints.log"), "wb") as log:
        proc = subprocess.Popen(["bowtie", "-a", "--norc", "-v", "2", "-p", str(args.bowtie_threads), "-S",
                                 "--un", unmapped, transcript_index, not_ncrna], stdout=out, stderr=log)
        if proc.wait() != 0:
            raise RuntimeError("transcriptome Bowtie mapping failed")

    env = os.environ.copy()
    env.update({
        "PYTHONPATH": os.path.abspath(args.py27_site_packages) + os.pathsep + source_root,
        "THEANO_FLAGS": "device=cpu,floatX=float64,optimizer=fast_run",
        "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1", "CUDA_VISIBLE_DEVICES": "", "PYTHONHASHSEED": "0", "LC_ALL": "C",
        "MPLBACKEND": "Agg",
    })
    with open(os.path.join(run_dir, "logs", "pip-freeze.txt"), "wb") as out:
        proc = subprocess.Popen(["/usr/bin/python2", "-m", "pip", "freeze"], stdout=out, stderr=subprocess.STDOUT, env=env)
        if proc.wait() != 0:
            raise RuntimeError("pip freeze failed")
    driver_common = ["/usr/bin/python2", args.driver, "--run-dir", run_dir, "--source-root", source_root,
                     "--seed", str(args.seed), "--train-genes", str(args.train_genes),
                     "--test-genes", str(args.test_genes), "--min-counts", str(args.min_counts),
                     "--min-codons", str(args.min_codons)]
    run_logged(driver_common + ["--stage", "process"], os.path.join(run_dir, "logs", "process.log"), env=env)
    run_logged(driver_common + ["--stage", "train", "--epochs", str(args.epochs)],
               os.path.join(run_dir, "logs", "train.log"), env=env)
    with open(os.path.join(run_dir, "training_result.json")) as handle:
        training = json.load(handle)
    artifact_paths = [raw_fastq, trimmed, footprints, training["weighted_sam"], training["counts_by_codon"],
                      training["outputs"], training["train_bounds"], training["test_bounds"],
                      training["weights"], training["predictions"]]
    artifacts = {os.path.relpath(p, run_dir): {"bytes": os.path.getsize(p), "sha256": sha256(p)} for p in artifact_paths}
    report = {
        "schema_version": "ixnos-bounded-official-smoke-v1",
        "created_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "status": "BOUNDED_OFFICIAL_SMOKE_COMPLETE_PENDING_INDEPENDENT_VERIFICATION",
        "config": config,
        "prefix_qc": prefix,
        "trimmed_qc": trim_qc,
        "training": training,
        "artifacts": artifacts,
        "pipeline_wall_seconds_including_download_mapping_training": time.time() - started,
        "host_platform": platform.platform(),
        "scope_flags": {
            "real_ribosome_profiling_reads": True,
            "official_ixnos_source_used": True,
            "rsem_used": False,
            "simple_mapping_weights_used": True,
            "full_SRR1049521_used": False,
            "paper_protocol_reproduced": False,
            "full_60_epoch_training_reproduced": False,
            "best_test_epoch_selected": False,
            "functional_ood": False,
            "codonflow_comparison": False,
            "sota_claim": False,
        },
    }
    write_json(os.path.join(run_dir, "ixnos_official_smoke_v1.json"), report)
    print(json.dumps({"status": report["status"], "run_dir": run_dir,
                      "test_metrics": training["test_metrics"], "train_shape": training["train_shape"],
                      "test_shape": training["test_shape"], "parameter_count": training["parameter_count"]}, indent=2))


if __name__ == "__main__":
    main()
