#!/usr/bin/env python2
"""Independent re-processing/retraining verifier; never imports production drivers."""
from __future__ import print_function
import argparse
import hashlib
import json
import os
import pickle
import random
import sys
import time

import numpy as np
import scipy.stats
import theano
import iXnos.interface as inter
import iXnos.process as proc


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


def fastq_count(path):
    n = 0
    lengths = {}
    names = set()
    with open(path, "r") as handle:
        while True:
            name = handle.readline()
            if not name:
                break
            seq = handle.readline()
            plus = handle.readline()
            qual = handle.readline()
            if not seq or not plus or not qual or not name.startswith("@") or not plus.startswith("+"):
                raise ValueError("invalid FASTQ at record %d" % n)
            seq = seq.rstrip("\r\n")
            qual = qual.rstrip("\r\n")
            if len(seq) != len(qual):
                raise ValueError("FASTQ length mismatch at record %d" % n)
            lengths[len(seq)] = lengths.get(len(seq), 0) + 1
            names.add(name.split()[0])
            n += 1
    return n, len(names), lengths


def calc_metrics(y, yhat):
    y = np.asarray(y, dtype=np.float64).ravel()
    yhat = np.asarray(yhat, dtype=np.float64).ravel()
    sse = np.sum((y - yhat) ** 2)
    sst = np.sum((y - np.mean(y)) ** 2)
    return {
        "n": int(y.size), "mse": float(np.mean((y - yhat) ** 2)),
        "r2": float(1.0 - sse / sst),
        "pearson": float(scipy.stats.pearsonr(y, yhat)[0]),
        "spearman": float(scipy.stats.spearmanr(y, yhat)[0]),
        "sse": float(sse), "sst": float(sst),
    }


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-run", required=True)
    parser.add_argument("--verification-run", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--source-archive", required=True)
    args = parser.parse_args()
    prod = os.path.abspath(args.production_run)
    ver = os.path.abspath(args.verification_run)
    source = os.path.abspath(args.source_root)
    if os.path.exists(ver):
        raise IOError("verification run exists; choose a new versioned directory")
    os.makedirs(ver)
    checks = []
    def check(name, condition, details=None):
        checks.append({"name": name, "passed": bool(condition), "details": details})
        print(("PASS" if condition else "FAIL") + " " + name + " " + str(details))
    with open(os.path.join(prod, "ixnos_official_smoke_v1.json")) as handle:
        report = json.load(handle)
    with open(os.path.join(prod, "run_config.json")) as handle:
        config = json.load(handle)
    with open(os.path.join(prod, "training_result.json")) as handle:
        training = json.load(handle)
    check("production_pending_independent_verification",
          report["status"] == "BOUNDED_OFFICIAL_SMOKE_COMPLETE_PENDING_INDEPENDENT_VERIFICATION", report["status"])
    flags = report["scope_flags"]
    check("bounded_scope_flags",
          flags["real_ribosome_profiling_reads"] and flags["official_ixnos_source_used"]
          and flags["simple_mapping_weights_used"] and not flags["rsem_used"]
          and not flags["full_SRR1049521_used"] and not flags["paper_protocol_reproduced"]
          and not flags["best_test_epoch_selected"] and not flags["functional_ood"]
          and not flags["codonflow_comparison"] and not flags["sota_claim"], flags)
    check("source_archive_sha256", sha256(args.source_archive) == config["source_archive_sha256"],
          sha256(args.source_archive))
    for rel, expected in training["source_file_sha256"].items():
        check("source_hash_" + rel.replace("/", "_"), sha256(os.path.join(source, rel)) == expected,
              sha256(os.path.join(source, rel)))

    prefix = report["prefix_qc"]
    n, unique_n, lengths = fastq_count(prefix["path"])
    check("prefix_fastq_independent_qc",
          n == config["prefix_reads"] and unique_n == n and sum(lengths.values()) == n
          and sha256(prefix["path"]) == prefix["sha256"],
          {"records": n, "unique_names": unique_n, "lengths": lengths, "sha256": sha256(prefix["path"])})
    trimmed = report["trimmed_qc"]
    tn, tu, tl = fastq_count(trimmed["path"])
    check("trimmed_fastq_independent_qc", tn == trimmed["records"] and tu == tn
          and sha256(trimmed["path"]) == trimmed["sha256"],
          {"records": tn, "unique_names": tu, "lengths": tl})
    rrna_log = open(os.path.join(prod, "logs", "bowtie_rrna.log")).read()
    footprint_log = open(os.path.join(prod, "logs", "bowtie_footprints.log")).read()
    check("bowtie_logs_real_input_and_output",
          ("# reads processed: %d" % tn) in rrna_log
          and "# reads processed:" in footprint_log
          and "# reads with at least one reported alignment:" in footprint_log,
          {"rrna_log": rrna_log, "footprint_log": footprint_log})
    weighted_sam = training["weighted_sam"]
    weighted_rel = os.path.relpath(weighted_sam, prod)
    check("weighted_sam_frozen_hash", sha256(weighted_sam) == report["artifacts"][weighted_rel]["sha256"],
          sha256(weighted_sam))

    random.seed(config["seed"])
    np.random.seed(config["seed"])
    expt = os.path.join(ver, "weinberg")
    for sub in ("plots", "process", "lasagne_nn", "linreg"):
        ensure_dir(os.path.join(expt, sub))
    shift = {27: {0: False, 1: 14, 2: False}, 28: {0: 15, 1: False, 2: False},
             29: {0: 15, 1: False, 2: 16}, 30: {0: 15, 1: False, 2: 16},
             31: {0: 15, 1: False, 2: 16}}
    process_started = time.time()
    inter.process_sam_file(
        expt, weighted_sam, os.path.join(source, "genome_data", "scer.transcripts.13cds10.fa"),
        os.path.join(source, "genome_data", "scer.transcripts.13cds10.lengths.txt"), shift,
        20, 20, 27, 31, config["train_genes"], config["test_genes"],
        config["min_counts"], config["min_codons"],
        paralog_groups_fname=os.path.join(source, "genome_data", "scer_100_80.paralogs.id.txt"),
        overwrite=False)
    process_seconds = time.time() - process_started
    independent_outputs = os.path.join(expt, "process", "outputs.size.27.31.txt")
    independent_counts = os.path.join(expt, "process", "cts_by_codon.size.27.31.txt")
    suffix = "size.27.31.trunc.20.20.min_cts.%d.min_cod.%d.top.%d.txt" % (
        config["min_counts"], config["min_codons"], config["train_genes"] + config["test_genes"])
    independent_tr = os.path.join(expt, "process", "tr_set_bounds." + suffix)
    independent_te = os.path.join(expt, "process", "te_set_bounds." + suffix)
    for name, a, b in (("counts", training["counts_by_codon"], independent_counts),
                       ("outputs", training["outputs"], independent_outputs),
                       ("train_bounds", training["train_bounds"], independent_tr),
                       ("test_bounds", training["test_bounds"], independent_te)):
        check("independent_reprocess_" + name + "_byte_identity", sha256(a) == sha256(b),
              {"production": sha256(a), "independent": sha256(b)})
    tr_genes = sorted(proc.load_codon_set_bounds(independent_tr).keys())
    te_genes = sorted(proc.load_codon_set_bounds(independent_te).keys())
    check("gene_split_sizes_and_disjointness",
          len(tr_genes) == config["train_genes"] and len(te_genes) == config["test_genes"]
          and not set(tr_genes).intersection(te_genes)
          and tr_genes == training["train_genes"] and te_genes == training["test_genes"],
          {"train_genes": tr_genes, "test_genes": te_genes})

    random.seed(config["seed"])
    np.random.seed(config["seed"])
    name = "independent_cod_n5p4_nt_n15p14_seed%d" % config["seed"]
    train_started = time.time()
    nn = inter.make_lasagne_feedforward_nn(
        name, expt, os.path.join(source, "genome_data", "scer.transcripts.13cds10.fa"),
        os.path.join(source, "genome_data", "scer.transcripts.13cds10.lengths.txt"),
        independent_tr, independent_te, independent_outputs,
        rel_cod_idxs=range(-5, 5), rel_nt_idxs=range(-15, 15),
        lr_decay=16, nonlinearity="tanh", widths=[200], update_method="nesterov",
        learning_rate=0.01, momentum=0.9, batch_size=500, nonnegative=True)
    nn.run_epochs(config["epochs"])
    train_seconds = time.time() - train_started
    independent_pred_path = os.path.join(ver, "test_predictions.npz")
    np.savez(independent_pred_path, y_true=np.asarray(nn.y_te).ravel(),
             y_pred=np.asarray(nn.y_te_hat).ravel())
    prod_npz = np.load(training["predictions"])
    ind_npz = np.load(independent_pred_path)
    y = prod_npz["y_true"]
    yp = prod_npz["y_pred"]
    yi = ind_npz["y_true"]
    ypi = ind_npz["y_pred"]
    target_delta = float(np.max(np.abs(y - yi)))
    pred_delta = float(np.max(np.abs(yp - ypi)))
    check("independent_retrain_test_targets_exact", target_delta == 0.0, target_delta)
    check("independent_retrain_predictions_exact", pred_delta <= 1e-12, pred_delta)
    recomputed = calc_metrics(y, yp)
    independent_metrics = calc_metrics(yi, ypi)
    metric_delta = max(abs(recomputed[k] - training["test_metrics"][k])
                       for k in ("mse", "r2", "pearson", "spearman", "sse", "sst"))
    check("production_metrics_independently_recomputed", metric_delta <= 1e-10,
          {"max_abs_delta": metric_delta, "recomputed": recomputed})
    check("independent_metrics_match_production",
          max(abs(recomputed[k] - independent_metrics[k]) for k in recomputed) <= 1e-12,
          independent_metrics)
    check("official_final_loss_matches_mse",
          abs(float(nn.test_err_by_epoch[-1]) - independent_metrics["mse"]) <= 1e-10,
          {"official": float(nn.test_err_by_epoch[-1]), "independent_mse": independent_metrics["mse"]})
    check("epoch_protocol_final_only",
          nn.num_epochs == config["epochs"] and len(nn.test_err_by_epoch) == config["epochs"] + 1
          and training["selection_rule"] == "final epoch only; no best-test checkpoint selection",
          {"epochs": nn.num_epochs, "loss_entries": len(nn.test_err_by_epoch)})
    prod_weights = list(pickle.load(open(training["weights"], "rb")))
    ind_weights_path = os.path.join(expt, "lasagne_nn", name, "epoch%d" % config["epochs"], "weights.pkl")
    ind_weights = list(pickle.load(open(ind_weights_path, "rb")))
    weight_delta = 0.0
    same_structure = len(prod_weights) == len(ind_weights)
    if same_structure:
        for a, b in zip(prod_weights, ind_weights):
            if np.asarray(a).shape != np.asarray(b).shape:
                same_structure = False
                break
            weight_delta = max(weight_delta, float(np.max(np.abs(np.asarray(a) - np.asarray(b)))))
    else:
        weight_delta = None
    check("checkpoint_tensor_structure_and_values", same_structure and weight_delta == 0.0,
          {"tensor_count": len(ind_weights), "max_abs_delta": weight_delta})
    parameter_count = int(sum(param.get_value().size for param in nn.params))
    check("model_shapes_and_parameter_count",
          list(nn.X_tr.shape) == training["train_shape"] and list(nn.X_te.shape) == training["test_shape"]
          and parameter_count == training["parameter_count"],
          {"train_shape": list(nn.X_tr.shape), "test_shape": list(nn.X_te.shape),
           "parameter_count": parameter_count})
    env_ok = (str(theano.config.device) == "cpu" and os.environ.get("OPENBLAS_NUM_THREADS") == "1"
              and os.environ.get("OMP_NUM_THREADS") == "1" and os.environ.get("MKL_NUM_THREADS") == "1"
              and os.environ.get("CUDA_VISIBLE_DEVICES") == "")
    check("real_runtime_environment_cpu_single_thread", env_ok,
          {"device": str(theano.config.device), "openblas": os.environ.get("OPENBLAS_NUM_THREADS"),
           "omp": os.environ.get("OMP_NUM_THREADS"), "mkl": os.environ.get("MKL_NUM_THREADS"),
           "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")})
    artifact_failures = []
    for rel, item in report["artifacts"].items():
        path = os.path.join(prod, rel)
        if not os.path.isfile(path) or os.path.getsize(path) != item["bytes"] or sha256(path) != item["sha256"]:
            artifact_failures.append(rel)
    check("production_artifact_hashes_and_sizes", not artifact_failures, artifact_failures)
    passed = sum(1 for c in checks if c["passed"])
    final = {
        "schema_version": "ixnos-independent-verification-v1",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks_passed": passed, "checks_total": len(checks), "checks": checks,
        "production_run": prod, "verification_run": ver,
        "independent_predictions": independent_pred_path,
        "independent_weights": ind_weights_path,
        "independent_process_seconds": process_seconds,
        "independent_training_seconds_including_compile": train_seconds,
        "max_prediction_abs_delta": pred_delta, "max_target_abs_delta": target_delta,
        "max_checkpoint_abs_delta": weight_delta,
        "recomputed_metrics": recomputed,
        "mapping_reexecuted": False,
        "mapping_verification_boundary": "raw prefix, trimming, Bowtie logs, weighted SAM and all downstream processing/training verified; Bowtie mapping itself was not rerun",
        "scope": "bounded prefix official-workflow smoke verification only; no full-run, paper-performance, OOD, SOTA, or CodonFlow claim",
    }
    write_json(os.path.join(ver, "ixnos_independent_verification_v1.json"), final)
    print(json.dumps({"status": final["status"], "checks": "%d/%d" % (passed, len(checks)),
                      "prediction_delta": pred_delta, "checkpoint_delta": weight_delta}, indent=2))
    if final["status"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
