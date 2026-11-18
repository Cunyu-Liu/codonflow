#!/usr/bin/env python3
"""Finalize iXnos bounded smoke only after independent scientific verification."""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import numpy as np


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sam(path, run_dir):
    """Compare Bowtie output independent of thread order and run-specific paths."""
    headers, records, pg = [], [], []
    with open(path, "rb") as handle:
        for line in handle:
            if line.startswith(b"@PG"):
                pg.append(line.replace(str(run_dir).encode(), b"<RUN_DIR>"))
            elif line.startswith(b"@"):
                headers.append(line)
            else:
                records.append(line)
    records.sort()
    content = hashlib.sha256()
    for line in headers + records:
        content.update(line)
    command = hashlib.sha256()
    for line in pg:
        command.update(line)
    return {
        "raw_sha256": sha256(path),
        "canonical_sorted_alignment_sha256": content.hexdigest(),
        "normalized_pg_sha256": command.hexdigest(),
        "non_pg_headers": len(headers),
        "alignment_records": len(records),
        "pg_records": len(pg),
    }


def write_json(path, obj):
    with open(path, "w") as handle:
        json.dump(obj, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-run", required=True)
    parser.add_argument("--verification-run", required=True)
    parser.add_argument("--failed-run", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    prod = os.path.abspath(args.production_run)
    ver = os.path.abspath(args.verification_run)
    failed = os.path.abspath(args.failed_run)
    out = os.path.abspath(args.output_dir)
    os.makedirs(out, exist_ok=True)
    final_path = os.path.join(out, "ixnos_finalization_v1.json")
    if os.path.exists(final_path):
        raise FileExistsError(final_path)
    with open(os.path.join(prod, "ixnos_official_smoke_v1.json")) as handle:
        production = json.load(handle)
    with open(os.path.join(prod, "training_result.json")) as handle:
        training = json.load(handle)
    with open(os.path.join(ver, "ixnos_independent_verification_v1.json")) as handle:
        independent = json.load(handle)
    checks = []
    def check(name, condition, details=None):
        checks.append({"name": name, "passed": bool(condition), "details": details})

    check("independent_verification_all_pass", independent["status"] == "PASS"
          and independent["checks_passed"] == independent["checks_total"]
          and all(c["passed"] for c in independent["checks"]),
          "%s/%s" % (independent["checks_passed"], independent["checks_total"]))
    flags = production["scope_flags"]
    check("strict_bounded_scope", flags["real_ribosome_profiling_reads"] and flags["official_ixnos_source_used"]
          and flags["simple_mapping_weights_used"] and not flags["rsem_used"]
          and not flags["full_SRR1049521_used"] and not flags["paper_protocol_reproduced"]
          and not flags["best_test_epoch_selected"] and not flags["functional_ood"]
          and not flags["codonflow_comparison"] and not flags["sota_claim"], flags)
    artifact_failures = []
    for rel, item in production["artifacts"].items():
        path = os.path.join(prod, rel)
        if not os.path.isfile(path) or os.path.getsize(path) != item["bytes"] or sha256(path) != item["sha256"]:
            artifact_failures.append(rel)
    check("production_artifacts_intact", not artifact_failures, artifact_failures)
    for key in ("independent_predictions", "independent_weights"):
        check("independent_artifact_" + key, os.path.isfile(independent[key]), independent[key])
    data = np.load(training["predictions"])
    y = np.asarray(data["y_true"], dtype=np.float64).ravel()
    yp = np.asarray(data["y_pred"], dtype=np.float64).ravel()
    mse = float(np.mean((y - yp) ** 2))
    r2 = float(1.0 - np.sum((y - yp) ** 2) / np.sum((y - y.mean()) ** 2))
    pearson = float(np.corrcoef(y, yp)[0, 1])
    metric_delta = max(abs(mse - training["test_metrics"]["mse"]),
                       abs(r2 - training["test_metrics"]["r2"]),
                       abs(pearson - training["test_metrics"]["pearson"]))
    check("final_metric_recalculation", metric_delta <= 1e-10,
          {"max_abs_delta": metric_delta, "mse": mse, "r2": r2, "pearson": pearson})
    check("independent_retrain_exact", independent["max_prediction_abs_delta"] <= 1e-12
          and independent["max_target_abs_delta"] == 0.0
          and independent["max_checkpoint_abs_delta"] == 0.0,
          {"prediction": independent["max_prediction_abs_delta"],
           "target": independent["max_target_abs_delta"],
           "checkpoint": independent["max_checkpoint_abs_delta"]})
    check("gene_split_contract", len(training["train_genes"]) == production["config"]["train_genes"]
          and len(training["test_genes"]) == production["config"]["test_genes"]
          and not set(training["train_genes"]).intersection(training["test_genes"]),
          {"train": len(training["train_genes"]), "test": len(training["test_genes"])})
    check("final_epoch_not_test_selected", training["selection_rule"] == "final epoch only; no best-test checkpoint selection"
          and len(training["official_test_loss_including_initial"]) == production["config"]["epochs"] + 1,
          training["official_test_loss_including_initial"])
    env = training["environment"]
    check("runtime_cpu_single_thread_headless", env["theano_device"] == "cpu"
          and env["openblas_num_threads"] == "1" and env["omp_num_threads"] == "1"
          and env["mkl_num_threads"] == "1" and env["cuda_visible_devices"] == ""
          and env["matplotlib_backend"].lower() == "agg", env)
    check("model_and_data_nonempty", training["parameter_count"] > 0
          and training["train_shape"][0] > 0 and training["test_shape"][0] == training["test_metrics"]["n"]
          and training["train_shape"][1] == training["test_shape"][1],
          {"train_shape": training["train_shape"], "test_shape": training["test_shape"],
           "parameter_count": training["parameter_count"]})
    prefix = production["prefix_qc"]
    check("real_prefix_integrity", prefix["records"] == production["config"]["prefix_reads"]
          and prefix["unique_read_names"] == prefix["records"]
          and prefix["read_length_counts"] == {"40": prefix["records"]}
          and sha256(prefix["path"]) == prefix["sha256"],
          {"records": prefix["records"], "sha256": prefix["sha256"]})
    trimmed = production["trimmed_qc"]
    check("real_trimming_integrity", 0 < trimmed["records"] <= prefix["records"]
          and trimmed["unique_read_names"] == trimmed["records"]
          and sha256(trimmed["path"]) == trimmed["sha256"],
          {"records": trimmed["records"], "lengths": trimmed["read_length_counts"]})
    failed_process = os.path.join(failed, "logs", "process.log")
    failure_text = open(failed_process, "r", errors="replace").read() if os.path.isfile(failed_process) else ""
    check("first_failure_preserved", "ImportError: No module named _tkinter" in failure_text
          and os.path.isfile(os.path.join(failed, "weinberg", "process", "weinberg.footprints.sam")),
          {"process_log_sha256": sha256(failed_process) if os.path.isfile(failed_process) else None})
    repeated = {}
    repeat_ok = True
    for label, rel in (("prefix", "raw/SRR1049521.first_1000000.fastq"),
                       ("trimmed", "weinberg/process/SRR1049521.trimmed.fastq")):
        a = os.path.join(failed, rel)
        b = os.path.join(prod, rel)
        same = os.path.isfile(a) and os.path.isfile(b) and sha256(a) == sha256(b)
        repeated[label] = {"failed_run_sha256": sha256(a) if os.path.isfile(a) else None,
                           "production_sha256": sha256(b) if os.path.isfile(b) else None,
                           "byte_identical": same}
        repeat_ok = repeat_ok and same
    sam_rel = "weinberg/process/weinberg.footprints.sam"
    failed_sam = canonical_sam(os.path.join(failed, sam_rel), failed)
    prod_sam = canonical_sam(os.path.join(prod, sam_rel), prod)
    sam_keys = ("canonical_sorted_alignment_sha256", "normalized_pg_sha256", "non_pg_headers", "alignment_records", "pg_records")
    sam_same = all(failed_sam[k] == prod_sam[k] for k in sam_keys)
    repeated["footprints_sam"] = {
        "failed_run": failed_sam, "production_run": prod_sam,
        "raw_byte_identical": failed_sam["raw_sha256"] == prod_sam["raw_sha256"],
        "canonical_content_identical": sam_same,
        "normalization": "non-PG headers plus lexicographically sorted complete alignment records; PG command hashed after replacing run-specific directory paths",
    }
    repeat_ok = repeat_ok and sam_same
    check("independent_pipeline_rerun_content_identity_before_training", repeat_ok, repeated)
    check("mapping_verification_boundary_explicit", independent["mapping_reexecuted"] is False
          and "not rerun" in independent["mapping_verification_boundary"],
          independent["mapping_verification_boundary"])
    passed = sum(c["passed"] for c in checks)
    status = "CLOSED_BOUNDED_OFFICIAL_SMOKE" if passed == len(checks) else "FINALIZATION_FAILED"
    prod_copy = os.path.join(out, "ixnos_official_smoke_v1.json")
    ind_copy = os.path.join(out, "ixnos_independent_verification_v1.json")
    shutil.copyfile(os.path.join(prod, "ixnos_official_smoke_v1.json"), prod_copy)
    shutil.copyfile(os.path.join(ver, "ixnos_independent_verification_v1.json"), ind_copy)
    final = {
        "schema_version": "ixnos-finalization-v1",
        "created_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "status": status, "checks_passed": passed, "checks_total": len(checks), "checks": checks,
        "source_repository": production["config"]["source_repository"],
        "source_commit": production["config"]["source_commit"],
        "source_archive_sha256": production["config"]["source_archive_sha256"],
        "production_run": prod, "verification_run": ver, "failed_run_retained": failed,
        "production_report_sha256": sha256(prod_copy),
        "independent_report_sha256": sha256(ind_copy),
        "prefix_sha256": prefix["sha256"], "trimmed_sha256": trimmed["sha256"],
        "weighted_sam": training["weighted_sam"], "weights": training["weights"],
        "test_metrics": training["test_metrics"],
        "train_mean_baseline_metrics": training["train_mean_baseline_metrics"],
        "train_shape": training["train_shape"], "test_shape": training["test_shape"],
        "parameter_count": training["parameter_count"],
        "scope": "Closed only as a bounded, real-prefix, official iXnos workflow smoke. Not full SRR1049521, not RSEM, not the full 333/167 60-epoch paper protocol, not functional OOD, not a CodonFlow comparison, and not SOTA.",
    }
    write_json(final_path, final)
    print(json.dumps({"status": status, "checks": "%d/%d" % (passed, len(checks)),
                      "finalization": final_path, "test_metrics": training["test_metrics"]}, indent=2))
    if status != "CLOSED_BOUNDED_OFFICIAL_SMOKE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
