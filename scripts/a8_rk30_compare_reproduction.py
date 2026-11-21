#!/usr/bin/env python3
"""Compare an independent RK30 rerun with production without comparing timings."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--reproduction-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    production = args.production_root.resolve()
    reproduction = args.reproduction_root.resolve()
    if production == reproduction:
        raise RuntimeError("Production and reproduction artifact roots must differ")

    csv_names = ["fixed_reference_r1_counts.csv", "matched_context_outcomes.csv"]
    csv_names += sorted(path.name for path in (production / "model").glob("*.csv"))
    csv_checks = []
    for name in csv_names:
        left, right = production / ("model/" + name if name not in csv_names[:2] else name), reproduction / ("model/" + name if name not in csv_names[:2] else name)
        if not right.is_file():
            raise FileNotFoundError(right)
        left_sha, right_sha = sha256(left), sha256(right)
        csv_checks.append({"name": name, "production_sha256": left_sha,
                           "reproduction_sha256": right_sha, "byte_equal": left_sha == right_sha})

    npz_names = sorted(path.name for path in (production / "model").glob("*.npz"))
    npz_checks = []
    for name in npz_names:
        left_path, right_path = production / "model" / name, reproduction / "model" / name
        with np.load(left_path, allow_pickle=False) as left, np.load(right_path, allow_pickle=False) as right:
            if set(left.files) != set(right.files):
                raise RuntimeError(f"Inference array names differ: {name}")
            arrays = []
            for key in sorted(left.files):
                a, b = left[key], right[key]
                equal = a.shape == b.shape and a.dtype == b.dtype and np.array_equal(a, b, equal_nan=True)
                arrays.append({"array": key, "shape": list(a.shape), "dtype": str(a.dtype), "exact_equal": bool(equal)})
            npz_checks.append({"name": name, "arrays": arrays, "all_exact": all(row["exact_equal"] for row in arrays)})

    ignored = {"started_utc", "completed_utc", "elapsed_seconds", "outputs", "counting_report_sha256"}
    left_summary = load(production / "RK30_MODEL_SUMMARY.json")
    right_summary = load(reproduction / "RK30_MODEL_SUMMARY.json")
    left_scientific = {k: v for k, v in left_summary.items() if k not in ignored}
    right_scientific = {k: v for k, v in right_summary.items() if k not in ignored}
    scientific_summary_equal = left_scientific == right_scientific

    reports = {}
    for name in ["RK30_RAW_VERIFICATION.json", "RK30_MODEL_INDEPENDENT.json", "RK30_CLOSEOUT.json"]:
        left, right = load(production / name), load(reproduction / name)
        reports[name] = {"production_status": left.get("status"), "reproduction_status": right.get("status"),
                         "status_equal": left.get("status") == right.get("status")}
    passed = (all(row["byte_equal"] for row in csv_checks) and
              all(row["all_exact"] for row in npz_checks) and scientific_summary_equal and
              reports["RK30_RAW_VERIFICATION.json"]["reproduction_status"] == "PASS_INDEPENDENT_RAW_COUNT_VERIFICATION" and
              reports["RK30_MODEL_INDEPENDENT.json"]["reproduction_status"] == "PASS_INDEPENDENT_MODEL_VERIFICATION" and
              reports["RK30_CLOSEOUT.json"]["reproduction_status"] == "PASS_RK30_VERIFIED_RESULT_PACKAGING")
    result = {
        "schema": "a8-rk30-production-reproduction-equivalence-v1",
        "status": "PASS_RK30_PRODUCTION_REPRODUCTION_EQUIVALENCE" if passed else "FAIL_RK30_PRODUCTION_REPRODUCTION_EQUIVALENCE",
        "production_root": str(production), "reproduction_root": str(reproduction),
        "n_csv_files": len(csv_checks), "n_npz_files": len(npz_checks),
        "n_npz_arrays": sum(len(row["arrays"]) for row in npz_checks),
        "scientific_summary_equal_ignoring_timing_paths_and_output_inventory": scientific_summary_equal,
        "ignored_summary_fields": sorted(ignored), "csv_checks": csv_checks,
        "npz_checks": npz_checks, "report_status_checks": reports,
        "comparison_script_sha256": sha256(Path(__file__).resolve()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "n_csv_files": len(csv_checks),
                      "n_npz_files": len(npz_checks), "scientific_summary_equal": scientific_summary_equal}, indent=2))
    if not passed:
        raise RuntimeError("Production/reproduction equivalence failed")


if __name__ == "__main__":
    main()
