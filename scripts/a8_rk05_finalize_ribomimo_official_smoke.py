#!/usr/bin/env python3
"""Finalize only the bounded RiboMIMO official-training smoke."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path


def sha(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-report", required=True)
    parser.add_argument("--independent-report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    production_path = Path(args.production_report).resolve()
    independent_path = Path(args.independent_report).resolve()
    prod = json.loads(production_path.read_text())
    ind = json.loads(independent_path.read_text())
    checks = []
    def check(name: str, passed: bool, detail: object = "") -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})
    required = {"status", "source", "matrix", "subset", "protocol", "runs", "compatibility", "official_result", "environment", "artifacts", "full_official_10fold_100epoch_reproduced", "homology_aware_split", "protein_ood", "study_ood", "functional_ood", "main_baseline_comparison", "publication_metrics_reproduced", "sota_claim"}
    check("production_schema_and_required_fields", prod["schema_version"] == "a8-rk05-ribomimo-official-smoke-v2" and required <= prod.keys() and prod["status"] == "BOUNDED_OFFICIAL_TRAINING_COMPLETE")
    check("fixed_source_matrix_and_subset", prod["source"]["commit"] == "094c693d4df45f4b29f5a3209b31c452a39092a5" and len(prod["subset"]["records"]) == 20 and Path(prod["subset"]["path"]).is_file() and sha(prod["subset"]["path"]) == prod["subset"]["sha256"] and sha(prod["matrix"]["path"]) == prod["matrix"]["sha256"])
    check("unmodified_and_staged_failures_retained", all(prod["runs"][name]["returncode"] != 0 and Path(prod["runs"][name]["log"]).is_file() for name in ("official_unmodified", "ragged_only")), {name: prod["runs"][name]["returncode"] for name in ("official_unmodified", "ragged_only")})
    check("six_item_compatibility_patch", prod["compatibility"]["replacement_count"] == 6 and len(json.loads(Path(prod["compatibility"]["replacements_path"]).read_text())) == 6 and sha(prod["compatibility"]["diff_path"]) == prod["compatibility"]["diff_sha256"] and prod["compatibility"]["algorithm_changed"] is False)
    metrics = prod["official_result"]["metrics"]
    check("bounded_protocol_and_finite_metrics", prod["protocol"]["num_fold"] == 2 and prod["protocol"]["max_epoch"] == 2 and prod["protocol"]["batch_size"] == 4 and prod["protocol"]["input_dims"] == 97 and all(math.isfinite(value) for key, value in metrics.items() if key != "aggregation"), metrics)
    checkpoint_ok = len(prod["official_result"]["checkpoints"]) == 2 and all(Path(row["path"]).is_file() and sha(row["path"]) == row["sha256"] for row in prod["official_result"]["checkpoints"].values())
    check("two_best_validation_checkpoints", checkpoint_ok and prod["official_result"]["checkpoint_parameter_count"] > 0, prod["official_result"]["checkpoint_parameter_count"])
    check("independent_verification_fully_passed", ind["status"] == "PASS" and ind["passed_checks"] == ind["check_count"] == 17 and ind["production_module_imported"] is False, f"{ind['passed_checks']}/{ind['check_count']}")
    independent = ind["independent_training"]
    independent_ok = independent["returncode"] == 0 and Path(independent["log"]).is_file() and sha(independent["log"]) == independent["log_sha256"] and len(independent["checkpoints"]) == 2 and all(Path(row["path"]).is_file() and sha(row["path"]) == row["sha256"] for row in independent["checkpoints"].values())
    check("independent_raw_artifacts", independent_ok and Path(ind["checkpoint_metrics_path"]).is_file())
    check("numeric_recompute_delta", ind["max_numeric_delta"] <= 2e-5, ind["max_numeric_delta"])
    check("cpu_deterministic_environment", prod["environment"]["device"] == "cpu" and prod["environment"]["torch_num_threads"] == 1 and prod["environment"]["deterministic_algorithms_in_driver"] is True and prod["environment"]["gpu_visible_to_training"] is False)
    artifact_failures = [name for name, row in prod["artifacts"].items() if not Path(row["path"]).is_file() or sha(row["path"]) != row["sha256"]]
    check("production_artifact_hashes", not artifact_failures, artifact_failures)
    forbidden = ("full_official_10fold_100epoch_reproduced", "homology_aware_split", "protein_ood", "study_ood", "functional_ood", "main_baseline_comparison", "publication_metrics_reproduced", "sota_claim")
    check("bounded_scope_gate_and_no_overclaim", all(prod[key] is False for key in forbidden) and prod["published_prediction_pickles_used"] is False)
    check("bounded_ready_not_full_rk05_or_rkg0", prod["status"] == "BOUNDED_OFFICIAL_TRAINING_COMPLETE" and not prod["main_baseline_comparison"] and not prod["study_ood"], {"RK05": "not closed", "RK-G0": "not closed"})
    passed = sum(row["pass"] for row in checks)
    report = {
        "schema_version": "a8-rk05-ribomimo-finalization-v1",
        "task": "RK-05",
        "status": "CLOSED_BOUNDED_OFFICIAL_SMOKE" if passed == len(checks) else "FINALIZATION_FAILED",
        "check_count": len(checks), "passed_checks": passed, "checks": checks,
        "production_report": str(production_path), "production_report_sha256": sha(production_path),
        "independent_report": str(independent_path), "independent_report_sha256": sha(independent_path),
        "scope": "Only the bounded official RiboMIMO training smoke is closed. Full CV, homology/study OOD, functional OOD, main baseline matrix and SOTA remain open.",
    }
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "output": str(output)}, indent=2))
    if report["status"] != "CLOSED_BOUNDED_OFFICIAL_SMOKE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
