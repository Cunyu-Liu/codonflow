#!/usr/bin/env python2
"""Python 2.7 driver that calls official iXnos interfaces without editing them."""
from __future__ import print_function
import argparse
import hashlib
import json
import os
import platform
import random
import sys
import time

import numpy as np
import scipy
import scipy.stats
import sklearn
import matplotlib
import theano
import lasagne
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


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def paths(args):
    expt = os.path.join(args.run_dir, "weinberg")
    process = os.path.join(expt, "process")
    suffix = "size.27.31.trunc.20.20.min_cts.%d.min_cod.%d.top.%d.txt" % (
        args.min_counts, args.min_codons, args.train_genes + args.test_genes)
    return {
        "expt": expt,
        "process": process,
        "sam": os.path.join(process, "weinberg.footprints.sam"),
        "counts": os.path.join(process, "cts_by_codon.size.27.31.txt"),
        "outputs": os.path.join(process, "outputs.size.27.31.txt"),
        "train_bounds": os.path.join(process, "tr_set_bounds." + suffix),
        "test_bounds": os.path.join(process, "te_set_bounds." + suffix),
        "gene_len": os.path.join(args.source_root, "genome_data", "scer.transcripts.13cds10.lengths.txt"),
        "gene_seq": os.path.join(args.source_root, "genome_data", "scer.transcripts.13cds10.fa"),
        "paralogs": os.path.join(args.source_root, "genome_data", "scer_100_80.paralogs.id.txt"),
    }


def environment(args):
    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "sklearn_version": sklearn.__version__,
        "matplotlib_version": matplotlib.__version__,
        "matplotlib_backend": str(matplotlib.get_backend()),
        "theano_version": theano.__version__,
        "lasagne_version": lasagne.__version__,
        "theano_device": str(theano.config.device),
        "theano_floatX": str(theano.config.floatX),
        "openblas_num_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "mkl_num_threads": os.environ.get("MKL_NUM_THREADS"),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "seed": args.seed,
    }


def process_stage(args):
    random.seed(args.seed)
    np.random.seed(args.seed)
    p = paths(args)
    for sub in ("plots", "process", "lasagne_nn", "linreg"):
        ensure_dir(os.path.join(p["expt"], sub))
    started = time.time()
    weighted = inter.edit_sam_file(
        p["expt"], p["sam"], filter_unmapped=True,
        sam_add_simple_map_wts=True, RSEM_add_map_wts=False)
    shift_dict = {
        27: {0: False, 1: 14, 2: False}, 28: {0: 15, 1: False, 2: False},
        29: {0: 15, 1: False, 2: 16}, 30: {0: 15, 1: False, 2: 16},
        31: {0: 15, 1: False, 2: 16}}
    inter.process_sam_file(
        p["expt"], weighted, p["gene_seq"], p["gene_len"], shift_dict,
        20, 20, 27, 31, args.train_genes, args.test_genes,
        args.min_counts, args.min_codons, paralog_groups_fname=p["paralogs"],
        overwrite=False)
    for key in ("counts", "outputs", "train_bounds", "test_bounds"):
        if not os.path.isfile(p[key]):
            raise IOError("missing official output %s: %s" % (key, p[key]))
    train_genes = sorted(proc.load_codon_set_bounds(p["train_bounds"]).keys())
    test_genes = sorted(proc.load_codon_set_bounds(p["test_bounds"]).keys())
    if len(train_genes) != args.train_genes or len(test_genes) != args.test_genes:
        raise ValueError("official split size mismatch")
    if set(train_genes).intersection(test_genes):
        raise ValueError("train/test gene overlap")
    manifest = {
        "weighted_sam": weighted,
        "counts_by_codon": p["counts"], "outputs": p["outputs"],
        "train_bounds": p["train_bounds"], "test_bounds": p["test_bounds"],
        "train_genes": train_genes, "test_genes": test_genes,
        "train_test_gene_overlap": [],
        "process_wall_seconds": time.time() - started,
        "environment": environment(args),
    }
    write_json(os.path.join(args.run_dir, "process_manifest.json"), manifest)
    print(json.dumps({"status": "PROCESS_COMPLETE", "train_genes": len(train_genes),
                      "test_genes": len(test_genes), "weighted_sam": weighted}))


def metrics(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=np.float64).ravel()
    y_pred = np.asarray(y_pred, dtype=np.float64).ravel()
    if y_true.shape != y_pred.shape or y_true.size < 2:
        raise ValueError("invalid metric shapes")
    if not np.all(np.isfinite(y_true)) or not np.all(np.isfinite(y_pred)):
        raise ValueError("nonfinite metric inputs")
    sse = float(np.sum((y_true - y_pred) ** 2))
    sst = float(np.sum((y_true - np.mean(y_true)) ** 2))
    return {
        "n": int(y_true.size),
        "mse": float(np.mean((y_true - y_pred) ** 2)),
        "r2": float(1.0 - sse / sst),
        "pearson": float(scipy.stats.pearsonr(y_true, y_pred)[0]),
        "spearman": float(scipy.stats.spearmanr(y_true, y_pred)[0]),
        "sse": sse,
        "sst": sst,
    }


def train_stage(args):
    random.seed(args.seed)
    np.random.seed(args.seed)
    p = paths(args)
    with open(os.path.join(args.run_dir, "process_manifest.json")) as handle:
        manifest = json.load(handle)
    name = "bounded_cod_n5p4_nt_n15p14_seed%d" % args.seed
    started = time.time()
    nn = inter.make_lasagne_feedforward_nn(
        name, p["expt"], p["gene_seq"], p["gene_len"],
        p["train_bounds"], p["test_bounds"], p["outputs"],
        rel_cod_idxs=range(-5, 5), rel_nt_idxs=range(-15, 15),
        lr_decay=16, nonlinearity="tanh", widths=[200],
        update_method="nesterov", learning_rate=0.01, momentum=0.9,
        batch_size=500, nonnegative=True)
    compile_seconds = time.time() - started
    epoch_started = time.time()
    nn.run_epochs(args.epochs)
    epoch_seconds = time.time() - epoch_started
    if nn.num_epochs != args.epochs:
        raise ValueError("epoch count mismatch")
    y_true = np.asarray(nn.y_te).ravel()
    y_pred = np.asarray(nn.y_te_hat).ravel()
    test_metrics = metrics(y_true, y_pred)
    train_mean = float(np.mean(nn.y_tr))
    baseline_pred = np.repeat(train_mean, y_true.size)
    baseline_metrics = metrics(y_true, baseline_pred)
    baseline_metrics["pearson"] = None
    baseline_metrics["spearman"] = None
    predictions_path = os.path.join(args.run_dir, "test_predictions.npz")
    np.savez(predictions_path, y_true=y_true, y_pred=y_pred,
             train_mean=np.array([train_mean], dtype=np.float64))
    weights_path = os.path.join(p["expt"], "lasagne_nn", name,
                                "epoch%d" % args.epochs, "weights.pkl")
    source_files = {}
    for rel in ("iXnos/interface.py", "iXnos/process.py", "iXnos/lasagnenn.py",
                "reproduce_scripts/process_data.py", "reproduce_scripts/feat_neighborhood_nn_series.py"):
        source_files[rel] = sha256(os.path.join(args.source_root, rel))
    result = {
        "status": "TRAIN_COMPLETE",
        "model_name": name,
        "model_source": "official iXnos FeedforwardMLP via interface.make_lasagne_feedforward_nn",
        "train_shape": list(nn.X_tr.shape), "test_shape": list(nn.X_te.shape),
        "train_target_shape": list(nn.y_tr.shape), "test_target_shape": list(nn.y_te.shape),
        "parameter_count": int(sum(param.get_value().size for param in nn.params)),
        "parameter_tensors": [list(param.get_value().shape) for param in nn.params],
        "test_metrics": test_metrics,
        "train_mean_baseline_metrics": baseline_metrics,
        "train_mean": train_mean,
        "official_train_loss_including_initial": [float(x) for x in nn.train_err_by_epoch],
        "official_test_loss_including_initial": [float(x) for x in nn.test_err_by_epoch],
        "official_final_test_loss": float(nn.test_err_by_epoch[-1]),
        "compile_and_initial_prediction_seconds": compile_seconds,
        "run_epochs_wall_seconds": epoch_seconds,
        "weighted_sam": manifest["weighted_sam"],
        "counts_by_codon": p["counts"], "outputs": p["outputs"],
        "train_bounds": p["train_bounds"], "test_bounds": p["test_bounds"],
        "train_genes": manifest["train_genes"], "test_genes": manifest["test_genes"],
        "weights": weights_path, "predictions": predictions_path,
        "source_file_sha256": source_files,
        "environment": environment(args),
        "process_wall_seconds": manifest["process_wall_seconds"],
        "selection_rule": "final epoch only; no best-test checkpoint selection",
        "test_set_use_limitation": "official implementation reports test loss after every epoch; bounded run uses last epoch and does not select on test",
    }
    write_json(os.path.join(args.run_dir, "training_result.json"), result)
    print(json.dumps({"status": result["status"], "test_metrics": test_metrics,
                      "parameter_count": result["parameter_count"],
                      "train_shape": result["train_shape"], "test_shape": result["test_shape"]}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--stage", choices=("process", "train"), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--train-genes", type=int, required=True)
    parser.add_argument("--test-genes", type=int, required=True)
    parser.add_argument("--min-counts", type=int, required=True)
    parser.add_argument("--min-codons", type=int, required=True)
    args = parser.parse_args()
    args.run_dir = os.path.abspath(args.run_dir)
    args.source_root = os.path.abspath(args.source_root)
    if args.stage == "process":
        process_stage(args)
    else:
        train_stage(args)


if __name__ == "__main__":
    main()
