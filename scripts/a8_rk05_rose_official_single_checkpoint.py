#!/usr/bin/env python3
"""Run the released ROSE networks on their complete released test arrays.

This is a Python-3/path compatibility driver for the official Caffe demo path,
not a new ROSE architecture, training algorithm, or 64-model ensemble.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import caffe
import h5py
import numpy as np
import sklearn
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    roc_auc_score,
)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, path)


def encode_sequences(sequences):
    """Reproduce official demo_test.py codon order and all-zero fallback."""
    if sequences.ndim != 1 or len(sequences) == 0:
        raise ValueError("Expected a non-empty one-dimensional sequence array")
    lengths = {len(value) for value in sequences}
    if lengths != {183}:
        raise ValueError("ROSE released inputs must all contain 183 nucleotides")
    codons = [a + b + c for a in "ATCG" for b in "ATCG" for c in "ATCG"]
    lookup = {codon: index for index, codon in enumerate(codons)}
    encoded = np.zeros((len(sequences), 64, 1, 61), dtype=np.float32)
    unknown = 0
    for row, raw_sequence in enumerate(sequences):
        sequence = raw_sequence.decode("ascii") if isinstance(raw_sequence, bytes) else str(raw_sequence)
        for offset in range(0, 183, 3):
            codon = sequence[offset : offset + 3]
            index = lookup.get(codon)
            if index is None:
                unknown += 1
            else:
                encoded[row, index, 0, offset // 3] = 1.0
    if unknown:
        raise ValueError("Unknown codons would change the released input semantics: %d" % unknown)
    return encoded


def official_probabilities(logits):
    """Use the exact two-exp probability expression in official ribo_convnet.py."""
    logits = np.asarray(logits, dtype=np.float32)
    probabilities = np.divide(
        np.exp(logits[:, 1]),
        np.exp(logits[:, 0]) + np.exp(logits[:, 1]),
    )
    if probabilities.shape != (len(logits),) or not np.all(np.isfinite(probabilities)):
        raise ValueError("Invalid ROSE probabilities")
    return probabilities.astype(np.float64)


def classification_metrics(labels, probabilities):
    labels = np.asarray(labels, dtype=np.int64)
    probabilities = np.asarray(probabilities, dtype=np.float64)
    predicted = (probabilities >= 0.5).astype(np.int64)
    tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
    prevalence = float(np.mean(labels))
    constant = np.full(len(labels), prevalence, dtype=np.float64)
    return {
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "average_precision": float(average_precision_score(labels, probabilities)),
        "accuracy_at_0.5": float(accuracy_score(labels, predicted)),
        "balanced_accuracy_at_0.5": float(balanced_accuracy_score(labels, predicted)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "confusion_matrix_at_0.5": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "constant_prevalence_baseline": {
            "probability": prevalence,
            "roc_auc": 0.5,
            "average_precision": prevalence,
            "log_loss": float(log_loss(labels, constant, labels=[0, 1])),
            "brier_score": float(brier_score_loss(labels, constant)),
        },
    }


def adapt_network(template, hdf5_list, original_test_batch, record_count):
    source = template.read_text(encoding="utf-8")
    batch_token = "batch_size: %d" % original_test_batch
    if source.count(batch_token) != 1:
        raise ValueError("Could not uniquely identify official TEST batch size")
    adapted, replacements = re.subn(r'source: "[^"]+"', 'source: "%s"' % hdf5_list, source)
    if replacements != 2:
        raise ValueError("Expected TRAIN and TEST HDF5 source declarations in backup network")
    adapted = adapted.replace(batch_token, "batch_size: %d" % record_count, 1)
    return source, adapted, replacements


def environment_record():
    try:
        caffe_package = subprocess.check_output(
            ["dpkg-query", "-W", "-f=${Version}", "python3-caffe-cpu"],
            text=True,
        ).strip()
    except Exception:
        caffe_package = "unknown"
    cpu_model = None
    with open("/proc/cpuinfo", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "cpu_model": cpu_model,
        "caffe_module": caffe.__file__,
        "caffe_package": caffe_package,
        "numpy": np.__version__,
        "h5py": h5py.__version__,
        "sklearn": sklearn.__version__,
        "solver_mode": "CPU",
        "gpu_used": False,
        "thread_environment": {
            key: os.environ.get(key)
            for key in ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"]
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol["status"] != "FROZEN_BEFORE_FULL_INFERENCE":
        raise ValueError("Protocol is not the frozen full-inference protocol")
    if protocol["training"] or protocol["ensemble"] or protocol["checkpoint_count_per_study"] != 1:
        raise ValueError("Only single-checkpoint inference is authorized")
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    unexpected = [p.name for p in output_root.iterdir() if p.name != "execution.log"]
    if unexpected:
        raise FileExistsError("Output root is not empty: %s" % unexpected)
    shutil.copyfile(protocol_path, output_root / "protocol.json")
    source = protocol["source"]
    source_root = Path(source["restored_root"])
    if sha256(source["archive"]) != source["archive_sha256"]:
        raise ValueError("ROSE archive hash mismatch")
    if sha256(source_root / "script/demo_test.py") != source["official_demo_sha256"]:
        raise ValueError("Official demo hash mismatch")
    environment = environment_record()
    if environment["thread_environment"]["OPENBLAS_NUM_THREADS"] != "1":
        raise ValueError("Set OPENBLAS_NUM_THREADS=1 before running")
    if environment["thread_environment"]["OMP_NUM_THREADS"] != "1":
        raise ValueError("Set OMP_NUM_THREADS=1 before running")
    write_json(output_root / "environment.json", environment)
    caffe.set_mode_cpu()
    studies = {}
    for name, specification in protocol["studies"].items():
        study_started = time.perf_counter()
        data_dir = source_root / "data" / name
        model_dir = source_root / specification["relative_model_dir"]
        x_path = data_dir / "X_test.npy"
        y_path = data_dir / "y_test.npy"
        weights_path = model_dir / protocol["checkpoint_name"]
        template_path = model_dir / protocol["network_template"]
        for key, path in [
            ("x_sha256", x_path),
            ("y_sha256", y_path),
            ("weights_sha256", weights_path),
            ("network_sha256", template_path),
        ]:
            if sha256(path) != specification[key]:
                raise ValueError("Hash mismatch for %s %s" % (name, key))
        raw_x = np.load(x_path, allow_pickle=False)
        labels = np.load(y_path, allow_pickle=False).astype(np.int64)
        if len(raw_x) != specification["expected_records"] or len(labels) != len(raw_x):
            raise ValueError("Released test-array size mismatch for " + name)
        positive = int(np.sum(labels == 1))
        negative = int(np.sum(labels == 0))
        if positive != specification["expected_positive"] or negative != specification["expected_negative"]:
            raise ValueError("Released label counts mismatch for " + name)
        if positive + negative != len(labels):
            raise ValueError("Non-binary labels in " + name)
        encode_started = time.perf_counter()
        encoded = encode_sequences(raw_x)
        encoding_seconds = time.perf_counter() - encode_started
        study_dir = output_root / name
        study_dir.mkdir()
        hdf5_path = study_dir / "test.h5"
        hdf5_list = study_dir / "test.txt"
        network_path = study_dir / "train_test.prototxt"
        h5_started = time.perf_counter()
        with h5py.File(hdf5_path, "w") as handle:
            handle["data"] = encoded
            handle["label"] = labels
        hdf5_list.write_text(str(hdf5_path) + "\n", encoding="utf-8")
        hdf5_seconds = time.perf_counter() - h5_started
        original_network, adapted_network, source_replacements = adapt_network(
            template_path,
            hdf5_list,
            specification["original_test_batch_size"],
            len(raw_x),
        )
        network_path.write_text(adapted_network, encoding="utf-8")
        (study_dir / "train_test_backup.official.prototxt").write_text(original_network, encoding="utf-8")
        load_started = time.perf_counter()
        network = caffe.Net(str(network_path), str(weights_path), caffe.TEST)
        load_seconds = time.perf_counter() - load_started
        parameter_count = int(
            sum(np.prod(blob.data.shape) for blobs in network.params.values() for blob in blobs)
        )
        if parameter_count != specification["expected_parameters"]:
            raise ValueError("Network parameter mismatch for " + name)
        forward_started = time.perf_counter()
        network.forward()
        forward_seconds = time.perf_counter() - forward_started
        logits = np.array(network.blobs["ip2"].data, dtype=np.float32, copy=True)
        caffe_labels = np.array(network.blobs["label"].data, dtype=np.int64, copy=True).reshape(-1)
        if logits.shape != (len(labels), 2) or not np.array_equal(caffe_labels, labels):
            raise ValueError("Caffe output/label shape mismatch for " + name)
        probabilities = official_probabilities(logits)
        metrics = classification_metrics(labels, probabilities)
        predictions_path = study_dir / "predictions.npz"
        np.savez_compressed(
            predictions_path,
            labels=labels,
            logits=logits,
            probabilities=probabilities,
        )
        artifact_paths = {
            "hdf5": hdf5_path,
            "hdf5_list": hdf5_list,
            "adapted_network": network_path,
            "official_network_copy": study_dir / "train_test_backup.official.prototxt",
            "weights": weights_path,
            "predictions": predictions_path,
        }
        studies[name] = {
            "records": int(len(labels)),
            "positive": positive,
            "negative": negative,
            "input_nt_per_record": 183,
            "input_codons_per_record": 61,
            "encoded_shape": list(encoded.shape),
            "encoded_dtype": str(encoded.dtype),
            "checkpoint_count": 1,
            "forward_passes": 1,
            "training": False,
            "parameter_count": parameter_count,
            "parameter_shapes": {
                layer: [list(blob.data.shape) for blob in blobs]
                for layer, blobs in network.params.items()
            },
            "metrics": metrics,
            "timing_seconds": {
                "encoding": encoding_seconds,
                "hdf5_write": hdf5_seconds,
                "network_load": load_seconds,
                "single_full_forward": forward_seconds,
                "study_total": time.perf_counter() - study_started,
            },
            "network_adaptation": {
                "source_path_replacements": source_replacements,
                "original_test_batch_size": specification["original_test_batch_size"],
                "actual_test_batch_size": int(len(labels)),
                "algorithm_or_weights_changed": False,
            },
            "artifacts": {
                key: {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
                for key, path in artifact_paths.items()
            },
            "source_artifacts": {
                key: {"path": str(path), "sha256": sha256(path)}
                for key, path in [("X_test", x_path), ("y_test", y_path)]
            },
        }
        print(name, json.dumps(metrics, sort_keys=True), flush=True)
    report = {
        "schema_version": 1,
        "protocol_version": protocol["protocol_version"],
        "protocol_sha256": sha256(protocol_path),
        "status": "PASS_COMPLETE_RELEASED_TEST_SINGLE_CHECKPOINT_INFERENCE",
        "source": source,
        "execution": {
            "command": [sys.executable] + sys.argv,
            "output_root": str(output_root),
            "environment_sha256": sha256(output_root / "environment.json"),
            "total_seconds": time.perf_counter() - started,
        },
        "studies": studies,
        "scientific_scope": {
            "task": "binary ribosome-stalling classification on author-processed released test arrays",
            "not_continuous_velocity_regression": True,
            "not_training": True,
            "not_64_checkpoint_ensemble": True,
            "not_protein_or_study_or_functional_ood": True,
            "not_matched_cost_or_sota": True,
            "not_raw_read_or_psite_remapping": True,
            "not_codonflow_rk": True,
        },
        "explicit_nonclaims": protocol["explicit_nonclaims"],
    }
    write_json(args.report, report)
    write_json(output_root / "production_report.copy.json", report)
    print(json.dumps({"status": report["status"], "studies": list(studies), "report": args.report}, indent=2))


if __name__ == "__main__":
    main()
