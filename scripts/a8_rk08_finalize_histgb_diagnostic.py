#!/usr/bin/env python3
"""Finalize the independently verified retrospective HistGB diagnostic."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import time
from pathlib import Path


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-dir", required=True)
    parser.add_argument("--verification", required=True)
    parser.add_argument("--original-summary", required=True)
    parser.add_argument("--original-finalization", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--analysis-script", required=True)
    parser.add_argument("--verification-script", required=True)
    parser.add_argument("--audit-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    started = time.time()
    analysis_dir = Path(args.analysis_dir)
    audit_dir = Path(args.audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    summary = json.loads((analysis_dir / "comparison_summary.json").read_text())
    verification = json.loads(Path(args.verification).read_text())
    original = json.loads(Path(args.original_summary).read_text())
    original_final = json.loads(Path(args.original_finalization).read_text())
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    check("analysis_status", summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION", summary["status"])
    check("independent_status", verification["status"] == "PASS", verification["status"])
    check("independent_counts", verification["checks_passed"] == verification["checks_total"] == 84 and not verification["failures"], f"{verification['checks_passed']}/{verification['checks_total']}")
    check("original_gate", original["rk_g1_pass"] is False and original_final["rk_g1_pass"] is False and summary["original_rk_g1_pass"] is False, False)
    check("original_finalization", original_final["status"] == "PASS" and original_final["checks_passed"] == original_final["checks_total"] == 48 and not original_final["failures"], f"{original_final['status']} {original_final['checks_passed']}/{original_final['checks_total']}")
    check("diagnostic_negative_or_uncertain", summary["diagnostic_favors_ribokinetic_all"] is False, summary["diagnostic_favors_ribokinetic_all"])
    check("retrospective_not_preregistered", summary["analysis_status"] == "retrospective_after_unpaired_metric_readout_not_preregistered", summary["analysis_status"])
    check("no_fitting_or_selection", summary["model_fitting_performed"] is False and summary["model_selection_performed"] is False, True)
    check("generator_remains_blocked", summary["expensive_generation_authorized"] is False and verification["expensive_generation_authorized"] is False, False)
    check("no_sota_or_fixed_protein_claim", summary["sota_claimed"] is False and summary["fixed_protein_synonymous_mechanism_supported"] is False, True)
    check("summary_verification_hash", verification["analysis_summary_sha256"] == sha256(analysis_dir / "comparison_summary.json"), verification["analysis_summary_sha256"])
    check("bootstrap_recomputation", verification["max_bootstrap_abs_delta"] < 1e-12, verification["max_bootstrap_abs_delta"])
    check("all_bootstrap_valid", all(row["bootstrap_valid"] == 2000 for row in summary["comparisons"]), True)
    check("four_comparisons", len(summary["comparisons"]) == 4, len(summary["comparisons"]))
    sequence = {row["metric"]: row for row in summary["comparisons"] if row["partition"] == "sequence_ood"}
    check("sequence_spearman_interval", sequence["spearman"]["ci95_low"] < 0 < sequence["spearman"]["ci95_high"], sequence["spearman"])
    check("sequence_mse_interval", sequence["cluster_balanced_mse"]["ci95_low"] < 0 < sequence["cluster_balanced_mse"]["ci95_high"], sequence["cluster_balanced_mse"])
    check("sequence_direction_not_mechanism_win", sequence["spearman"]["point_delta"] < 0 and sequence["cluster_balanced_mse"]["point_delta"] > 0, {key: row["point_delta"] for key, row in sequence.items()})
    check("sequence_metrics_finite", all(math.isfinite(summary["metrics"]["sequence_ood"][model][metric]) for model in ["ribokinetic_all", "histgb_all"] for metric in ["row_spearman", "cluster_balanced_mse"]), True)
    check("sequence_row_and_cluster_counts", all(summary["metrics"]["sequence_ood"][model]["n_rows"] == 1336 and summary["metrics"]["sequence_ood"][model]["n_clusters"] == 1110 for model in ["ribokinetic_all", "histgb_all"]), True)
    check("original_metrics_preserved", all(summary["metrics"][partition][model][metric] == original["metrics"][partition][model][metric] for partition in ["dev", "test", "sequence_ood"] for model in ["ribokinetic_all", "histgb_all"] for metric in ["row_spearman", "cluster_balanced_mse"]), True)

    artifacts = {}
    for label, path in [
        ("comparison_summary", analysis_dir / "comparison_summary.json"),
        ("paired_comparisons", analysis_dir / "paired_comparisons.csv"),
        ("metrics", analysis_dir / "metrics.csv"),
        ("bootstrap_deltas", analysis_dir / "bootstrap_deltas.csv.gz"),
        ("independent_verification", Path(args.verification)),
        ("original_summary", Path(args.original_summary)),
        ("original_finalization", Path(args.original_finalization)),
        ("protocol", Path(args.protocol)),
        ("analysis_script", Path(args.analysis_script)),
        ("verification_script", Path(args.verification_script)),
        ("finalization_script", Path(__file__)),
    ]:
        exists = Path(path).is_file() and Path(path).stat().st_size > 0
        check(f"artifact:{label}", exists, str(path))
        if exists:
            artifacts[label] = {"path": str(Path(path).resolve()), "sha256": sha256(path), "bytes": Path(path).stat().st_size}

    summary_copy = audit_dir / "full_function_histgb_diagnostic_summary_v1.json"
    verification_copy = audit_dir / "full_function_histgb_diagnostic_verification_v1.json"
    shutil.copy2(analysis_dir / "comparison_summary.json", summary_copy)
    shutil.copy2(args.verification, verification_copy)
    check("audit_summary_copy", sha256(summary_copy) == artifacts["comparison_summary"]["sha256"], sha256(summary_copy))
    check("audit_verification_copy", sha256(verification_copy) == artifacts["independent_verification"]["sha256"], sha256(verification_copy))
    failures = [row for row in checks if not row["pass"]]
    report = {
        "protocol": "a8_rk08_histgb_diagnostic_finalization_v1",
        "status": "PASS_COMPLETE_RETROSPECTIVE_HISTGB_DIAGNOSTIC" if not failures else "FAIL",
        "checks": checks,
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
        "conclusion": "The mechanism model does not outperform the frozen HistGB feature baseline on sequence-OOD; both paired confidence intervals include zero, and the original RK-G1 remains false.",
        "original_rk_g1_pass": False,
        "diagnostic_favors_ribokinetic_all": False,
        "expensive_generation_authorized": False,
        "sota_claimed": False,
        "fixed_protein_synonymous_mechanism_supported": False,
        "functional_untouched_accessed": False,
        "artifacts": artifacts,
        "audit_copies": {"summary": str(summary_copy), "verification": str(verification_copy)},
        "limitations": summary["limitations"],
        "next_action": "Retain HistGB as a required internal feature baseline in future preregistered comparisons and continue mechanism/data diagnosis before any generator training.",
        "elapsed_seconds": time.time() - started,
    }
    Path(args.output).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "output": args.output}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
