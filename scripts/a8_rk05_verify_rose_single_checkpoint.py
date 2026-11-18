#!/usr/bin/env python3
"""Independently re-encode and rerun released ROSE checkpoints without production imports."""
import argparse
import hashlib
import itertools
import json
import os
import re
import time
from pathlib import Path

import caffe
import h5py
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dump_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, path)


def independent_encode(raw_sequences):
    if raw_sequences.ndim != 1:
        raise AssertionError("Expected one-dimensional sequence array")
    # itertools.product is intentionally independent of production's nested loops.
    alphabet = "ATCG"
    channel_by_codon = {
        "".join(letters): channel
        for channel, letters in enumerate(itertools.product(alphabet, repeat=3))
    }
    tensor = np.zeros((raw_sequences.shape[0], 64, 1, 61), dtype=np.float32)
    for row, value in enumerate(raw_sequences):
        sequence = value.decode("ascii") if isinstance(value, bytes) else str(value)
        if len(sequence) != 183:
            raise AssertionError("Unexpected sequence length")
        for codon_index in range(61):
            channel = channel_by_codon[sequence[3 * codon_index : 3 * codon_index + 3]]
            tensor[row, channel, 0, codon_index] = np.float32(1.0)
    return tensor


def independent_network_text(template, h5_list, old_batch, new_batch):
    lines = template.read_text(encoding="utf-8").splitlines()
    output = []
    source_count = 0
    batch_count = 0
    for line in lines:
        if line.lstrip().startswith("source:"):
            indent = line[: len(line) - len(line.lstrip())]
            output.append('%ssource: "%s"' % (indent, h5_list))
            source_count += 1
        elif line.strip() == "batch_size: %d" % old_batch:
            indent = line[: len(line) - len(line.lstrip())]
            output.append("%sbatch_size: %d" % (indent, new_batch))
            batch_count += 1
        else:
            output.append(line)
    if source_count != 2 or batch_count != 1:
        raise AssertionError("Unexpected backup network structure")
    return "\n".join(output) + "\n"


def only_expected_network_changes(original, adapted, old_batch, new_batch):
    original_normalized = re.sub(r'source: "[^"]+"', 'source: "<LIST>"', original)
    adapted_normalized = re.sub(r'source: "[^"]+"', 'source: "<LIST>"', adapted)
    adapted_normalized = adapted_normalized.replace(
        "batch_size: %d" % new_batch,
        "batch_size: %d" % old_batch,
        1,
    )
    return original_normalized == adapted_normalized


def independent_metrics(labels, probabilities):
    predicted = (probabilities >= 0.5).astype(np.int64)
    return {
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "average_precision": float(average_precision_score(labels, probabilities)),
        "accuracy_at_0.5": float(accuracy_score(labels, predicted)),
        "balanced_accuracy_at_0.5": float(balanced_accuracy_score(labels, predicted)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "brier_score": float(brier_score_loss(labels, probabilities)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--production-report", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    protocol_path = Path(args.protocol).resolve()
    production_path = Path(args.production_report).resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    if production["protocol_sha256"] != sha256(protocol_path):
        raise AssertionError("Production protocol identity mismatch")
    if production["status"] != "PASS_COMPLETE_RELEASED_TEST_SINGLE_CHECKPOINT_INFERENCE":
        raise AssertionError("Production run did not pass")
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    unexpected = [p.name for p in output_root.iterdir() if p.name != "execution.log"]
    if unexpected:
        raise FileExistsError("Independent output root is not empty: %s" % unexpected)
    source_root = Path(protocol["source"]["restored_root"])
    caffe.set_mode_cpu()
    checks = []

    def check(name, condition, details=None):
        checks.append({"name": name, "passed": bool(condition), "details": details})
        if not condition:
            raise AssertionError(name + (": " + str(details) if details is not None else ""))

    check("official_archive_identity", sha256(protocol["source"]["archive"]) == protocol["source"]["archive_sha256"])
    check("official_demo_identity", sha256(source_root / "script/demo_test.py") == protocol["source"]["official_demo_sha256"])
    studies = {}
    for name, specification in protocol["studies"].items():
        data_dir = source_root / "data" / name
        model_dir = source_root / specification["relative_model_dir"]
        x_path = data_dir / "X_test.npy"
        y_path = data_dir / "y_test.npy"
        weights_path = model_dir / protocol["checkpoint_name"]
        template_path = model_dir / protocol["network_template"]
        check(name + "_source_hashes", all([
            sha256(x_path) == specification["x_sha256"],
            sha256(y_path) == specification["y_sha256"],
            sha256(weights_path) == specification["weights_sha256"],
            sha256(template_path) == specification["network_sha256"],
        ]))
        checkpoints = sorted(model_dir.glob("*.caffemodel"))
        check(name + "_only_one_released_checkpoint", checkpoints == [weights_path], [str(p) for p in checkpoints])
        raw_sequences = np.load(x_path, allow_pickle=False)
        labels = np.load(y_path, allow_pickle=False).astype(np.int64)
        check(name + "_complete_arrays", len(raw_sequences) == len(labels) == specification["expected_records"], len(labels))
        check(name + "_balanced_binary_labels", {
            "positive": int(np.sum(labels == 1)),
            "negative": int(np.sum(labels == 0)),
        } == {"positive": specification["expected_positive"], "negative": specification["expected_negative"]})
        encoded = independent_encode(raw_sequences)
        production_study = production["studies"][name]
        production_h5 = Path(production_study["artifacts"]["hdf5"]["path"])
        with h5py.File(production_h5, "r") as handle:
            production_encoded = np.array(handle["data"])
            production_h5_labels = np.array(handle["label"]).astype(np.int64)
        check(name + "_independent_encoding_exact", np.array_equal(encoded, production_encoded), {
            "shape": list(encoded.shape),
            "nonzero": int(np.count_nonzero(encoded)),
            "expected_nonzero": int(len(labels) * 61),
        })
        check(name + "_production_h5_labels_exact", np.array_equal(labels, production_h5_labels))
        study_dir = output_root / name
        study_dir.mkdir()
        h5_path = study_dir / "test.h5"
        h5_list = study_dir / "test.txt"
        with h5py.File(h5_path, "w") as handle:
            handle.create_dataset("data", data=encoded)
            handle.create_dataset("label", data=labels)
        h5_list.write_text(str(h5_path) + "\n", encoding="utf-8")
        network_path = study_dir / "train_test.prototxt"
        network_path.write_text(
            independent_network_text(
                template_path,
                h5_list,
                specification["original_test_batch_size"],
                len(labels),
            ),
            encoding="utf-8",
        )
        original_network = template_path.read_text(encoding="utf-8")
        production_network = Path(production_study["artifacts"]["adapted_network"]["path"]).read_text(encoding="utf-8")
        check(name + "_production_only_path_and_batch_changes", only_expected_network_changes(
            original_network,
            production_network,
            specification["original_test_batch_size"],
            len(labels),
        ))
        check(name + "_independent_only_path_and_batch_changes", only_expected_network_changes(
            original_network,
            network_path.read_text(encoding="utf-8"),
            specification["original_test_batch_size"],
            len(labels),
        ))
        network = caffe.Net(str(network_path), str(weights_path), caffe.TEST)
        parameter_count = int(sum(np.prod(blob.data.shape) for blobs in network.params.values() for blob in blobs))
        check(name + "_parameter_count", parameter_count == specification["expected_parameters"], parameter_count)
        forward_started = time.perf_counter()
        network.forward()
        forward_seconds = time.perf_counter() - forward_started
        logits = np.array(network.blobs["ip2"].data, dtype=np.float32, copy=True)
        network_labels = np.array(network.blobs["label"].data, dtype=np.int64).reshape(-1)
        check(name + "_independent_forward_shape_and_labels", logits.shape == (len(labels), 2) and np.array_equal(network_labels, labels))
        # Stable logistic form is independent of production's exact two-exp expression.
        probabilities = 1.0 / (1.0 + np.exp(logits[:, 0].astype(np.float64) - logits[:, 1].astype(np.float64)))
        with np.load(production_study["artifacts"]["predictions"]["path"], allow_pickle=False) as previous:
            production_labels = np.array(previous["labels"])
            production_logits = np.array(previous["logits"])
            production_probabilities = np.array(previous["probabilities"])
        logit_delta = float(np.max(np.abs(logits.astype(np.float64) - production_logits.astype(np.float64))))
        probability_delta = float(np.max(np.abs(probabilities - production_probabilities)))
        # Production follows the official float32 two-exp expression before casting
        # to float64. Reproduce that expression independently and compare it exactly;
        # separately bound the stable-float64 difference at float32 rounding scale.
        official_float32_probabilities = np.divide(
            np.exp(production_logits[:, 1]),
            np.exp(production_logits[:, 0]) + np.exp(production_logits[:, 1]),
        ).astype(np.float64)
        production_formula_delta = float(np.max(np.abs(
            official_float32_probabilities - production_probabilities
        )))
        check(name + "_labels_exact", np.array_equal(labels, production_labels))
        check(name + "_logits_bitwise_exact", logit_delta == 0.0, logit_delta)
        check(name + "_production_float32_formula_exact", production_formula_delta == 0.0, production_formula_delta)
        check(name + "_stable_float64_probability_rounding_only", probability_delta <= 2e-7, {
            "max_abs_delta": probability_delta,
            "tolerance": 2e-7,
        })
        # Primary verification uses the independently recomputed official float32
        # probabilities, which must reproduce every production metric exactly.
        # Stable-float64 metrics are retained as a secondary numerical robustness check.
        metrics = independent_metrics(labels, official_float32_probabilities)
        stable_metrics = independent_metrics(labels, probabilities)
        production_metrics = production_study["metrics"]
        metric_deltas = {key: abs(value - production_metrics[key]) for key, value in metrics.items()}
        check(name + "_official_formula_metrics_exact", max(metric_deltas.values()) == 0.0, metric_deltas)
        stable_metric_deltas = {key: abs(value - production_metrics[key]) for key, value in stable_metrics.items()}
        stable_metric_tolerances = {
            "roc_auc": 1e-7,
            "average_precision": 1e-6,
            "accuracy_at_0.5": 1e-12,
            "balanced_accuracy_at_0.5": 1e-12,
            "log_loss": 1e-7,
            "brier_score": 1e-8,
        }
        check(name + "_stable_float64_metrics_rounding_only", all(
            stable_metric_deltas[key] <= tolerance for key, tolerance in stable_metric_tolerances.items()
        ), {"abs_deltas": stable_metric_deltas, "tolerances": stable_metric_tolerances})
        predictions_path = study_dir / "predictions.npz"
        np.savez_compressed(
            predictions_path,
            labels=labels,
            logits=logits,
            probabilities=probabilities,
            official_float32_probabilities=official_float32_probabilities,
        )
        studies[name] = {
            "records": int(len(labels)),
            "single_full_forward_seconds": forward_seconds,
            "logit_max_abs_delta": logit_delta,
            "probability_max_abs_delta": probability_delta,
            "production_float32_formula_max_abs_delta": production_formula_delta,
            "metric_abs_deltas": metric_deltas,
            "stable_float64_metric_abs_deltas": stable_metric_deltas,
            "metrics": metrics,
            "stable_float64_metrics": stable_metrics,
            "independent_predictions": {
                "path": str(predictions_path),
                "bytes": predictions_path.stat().st_size,
                "sha256": sha256(predictions_path),
            },
            "independent_hdf5": {"path": str(h5_path), "sha256": sha256(h5_path)},
            "independent_network": {"path": str(network_path), "sha256": sha256(network_path)},
        }
    report = {
        "schema_version": 1,
        "protocol_version": protocol["protocol_version"],
        "status": "PASS" if all(item["passed"] for item in checks) else "FAIL",
        "production_report": str(production_path),
        "production_report_sha256": sha256(production_path),
        "production_driver_imported": False,
        "independent_output_root": str(output_root),
        "check_count": len(checks),
        "passed_count": sum(item["passed"] for item in checks),
        "checks": checks,
        "studies": studies,
        "total_seconds": time.perf_counter() - started,
        "scope": "Independent re-encoding and single-checkpoint inference only; no training, ensemble, OOD, matched-cost or SOTA claim.",
    }
    dump_json(args.report, report)
    dump_json(output_root / "independent_report.copy.json", report)
    print(json.dumps({"status": report["status"], "checks": "%d/%d" % (report["passed_count"], report["check_count"]), "studies": studies}, indent=2))


if __name__ == "__main__":
    main()
