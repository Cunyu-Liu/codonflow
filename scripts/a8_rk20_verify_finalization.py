#!/usr/bin/env python3
"""Independently bind the RK20 finalization to verified comparison artifacts."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default="/home/codonflow-a8-rk")
    parser.add_argument("--artifact-root", default="/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk20/functional_multiseed_v1")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    repo = Path(args.repo_root)
    root = Path(args.artifact_root)
    audit = repo / "audits/20261120/RK20"
    final = json.loads((audit / "rk20_finalization_v1.json").read_text())
    independent = json.loads((audit / "rk20_independent_verification_v1.json").read_text())
    summary_path = root / "comparison_v1/comparison_summary.json"
    summary = json.loads(summary_path.read_text())
    execution = json.loads((root / "execution_status.json").read_text())
    paired = pd.read_csv(root / "comparison_v1/paired_comparisons.csv")
    per_seed = pd.read_csv(root / "comparison_v1/per_seed_comparisons.csv")
    checks = []

    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})

    def close(left, right):
        return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)

    check("final_status", final["status"] == "PASS_RK20_COMPLETE_ROBUSTNESS_NOT_PASSED")
    check("independent_77", independent["status"] == "PASS_INDEPENDENT_VERIFICATION" and independent["checks_passed"] == independent["checks_total"] == 77)
    check("independent_hash", sha256(audit / "rk20_independent_verification_v1.json") == final["independent_verification"]["sha256"])
    check("summary_hash", sha256(summary_path) == final["comparison_artifacts"]["summary_sha256"])
    check("paired_hash", sha256(root / "comparison_v1/paired_comparisons.csv") == final["comparison_artifacts"]["paired_comparisons_sha256"])
    check("metrics_hash", sha256(root / "comparison_v1/metrics.csv") == final["comparison_artifacts"]["metrics_sha256"])
    check("per_seed_hash", sha256(root / "comparison_v1/per_seed_comparisons.csv") == final["comparison_artifacts"]["per_seed_comparisons_sha256"])
    check("bootstrap_hash", sha256(root / "comparison_v1/bootstrap_deltas.csv.gz") == final["comparison_artifacts"]["bootstrap_deltas_sha256"])
    check("execution_hash", sha256(root / "execution_status.json") == final["training"]["execution_sha256"])
    check("manifest_hash", sha256(root / "run_manifest.json") == final["training"]["manifest_sha256"])
    check("execution_complete", execution["status"] == "PASS_ALL_FROZEN_RUNS_COMPLETE_PENDING_COMPARISON")
    check("six_new_two_reused", sum(row["execution"] == "completed" for row in execution["runs"]) == 6 and sum(row["execution"] == "reused_frozen_output" for row in execution["runs"]) == 2)
    check("training_cost", abs(sum(row["training_seconds"] for row in execution["runs"] if row["execution"] == "completed") - final["training"]["total_new_training_seconds"]) < 1e-9)

    means = summary["metrics"]["sequence_ood"]["mean_across_seeds"]
    for model, expected in final["mean_sequence_ood_metrics"].items():
        for metric, value in expected.items():
            check(f"mean_{model}_{metric}", means[model][metric] == value)
    source_rows = {
        (row.left, row.right, row.metric): row
        for row in paired[paired["partition"] == "sequence_ood"].itertuples()
    }
    for expected in final["sequence_ood_primary_and_secondary_comparisons"]:
        row = source_rows[(expected["left"], expected["right"], expected["metric"])]
        key = f"{expected['right']}_{expected['metric']}"
        check(f"delta_{key}", close(row.point_delta_mean_per_seed, expected["delta"]))
        check(f"ci_{key}", close(row.ci95_low, expected["ci95"][0]) and close(row.ci95_high, expected["ci95"][1]))
        check(f"holm_{key}", row.holm_pvalue_within_partition == expected["holm_p"])
        passed = bool(row.direction_pass and row.holm_pvalue_within_partition < 0.05)
        check(f"pass_{key}", passed == expected["pass"])
    check("two_of_eight", sum(row["pass"] for row in final["sequence_ood_primary_and_secondary_comparisons"]) == 2)
    for metric in ("spearman", "cluster_balanced_mse"):
        rows = per_seed[(per_seed["partition"] == "sequence_ood") & (per_seed["left"] == "ribokinetic_all") & (per_seed["right"] == "ribokinetic_none") & (per_seed["metric"] == metric)].sort_values("seed")
        check(f"per_seed_{metric}", len(rows) == len(final["all_minus_none_per_seed"][metric]) and all(close(left, right) for left, right in zip(rows["delta"].tolist(), final["all_minus_none_per_seed"][metric])))
    check("robustness_false", summary["functional_robustness_pass"] is False and final["functional_robustness_pass"] is False)
    for flag in ("rk_g1_pass", "functional_untouched_evaluated", "expensive_generation_authorized", "external_sota_authorized", "sota_claimed", "velocity_mechanism_pass", "fixed_gfp_structure_mechanism_pass"):
        check(f"boundary_{flag}", final[flag] is False)
    check("no_added_seeds", final["training"]["seeds"] == [20261119, 20261120, 20261121, 20261122] and final["no_added_seeds_or_test_ood_tuning"] is True)

    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk20-finalization-verification-v1",
        "status": "PASS_RK20_FINALIZATION" if passed == len(checks) else "FAIL_RK20_FINALIZATION",
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "functional_robustness_pass": False,
        "rk_g1_pass": False,
        "functional_untouched_evaluated": False,
        "expensive_generation_authorized": False,
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}"}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
