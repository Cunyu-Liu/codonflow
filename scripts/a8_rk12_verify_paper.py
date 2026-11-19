#!/usr/bin/env python3
"""Independently verify the A8 v18 RK-12 increment against finalized evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

HEADING = "### 6.14 RK-12 unique18 LinearDesign and external actual-set matrix"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--a7", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--update-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    text = args.paper.read_text()
    audit = json.loads(args.audit.read_text())
    matrix = json.loads(args.matrix.read_text())
    final = json.loads(args.finalization.read_text())
    update = json.loads(args.update_report.read_text())
    checks = []

    def record(name, passed, evidence=None):
        checks.append({"check": name, "pass": bool(passed), "evidence": evidence})

    snapshot = audit["pre_rk12_snapshot"]
    record("snapshot_paper", sha256(Path(snapshot["paper"])) == snapshot["paper_sha256"] == audit["base_v17_paper_sha256"])
    record("snapshot_audit", sha256(Path(snapshot["audit"])) == snapshot["audit_sha256"] == audit["base_v17_audit_sha256"])
    record("snapshot_a7", sha256(Path(snapshot["a7"])) == snapshot["a7_sha256"] == sha256(args.a7))
    record("current_output_hash", audit["output_sha256"] == sha256(args.paper))
    record("update_hashes", update["paper_sha256"] == sha256(args.paper) and update["audit_sha256"] == sha256(args.audit) and update["matrix_sha256"] == sha256(args.matrix) and update["finalization_sha256"] == sha256(args.finalization))
    record("section_once", text.count(HEADING) == 1)
    record("section_before_discussion", text.index(HEADING) < text.index("## 7. Discussion"))
    record("generated_sections", "6.14 RK-12 unique18 LinearDesign and external actual-set matrix" in audit["generated_sections"] and "8.1 RK-12 evidence anchors" in audit["generated_sections"])
    record("finalization_pass", final["status"].startswith("PASS_") and final["checks_passed"] == final["checks_total"] == 15)
    record("run_count_text", f"**{final['run_count']} official CPU processes**" in text and f"{final['record_count']} records x 11 lambdas" in text)
    record("unique_sequence_text", f"produced {final['unique_output_sequences_global']} distinct record-sequence pairs" in text)
    record("generation_cost_text", f"{final['lineardesign_generation_seconds']:.3f} s of summed official-process wall clock" in text)
    record("grid_verifier_text", "35/35 checks with zero CAI/MFE recomputation error" in text)
    record("matrix_verifier_text", f"{final['checks'][6]['evidence']}/{final['checks'][6]['evidence']} PASS" in text)
    record("finalizer_and_tests_text", f"{final['checks_passed']}/{final['checks_total']} checks and the contract tests passed 10/10" in text)
    for name, item in matrix["method_summary"].items():
        expected = f"| {name} | {item['total_actual_outputs']} | {item['mean_hypervolume_normalized']:.6f} | {item['mean_ned']:.6f} | {item['min_identity_rate']:.3f} |"
        record(f"method_row:{name}", expected in text)
    for key, item in matrix["primary_comparisons"].items():
        expected = f"| {item['comparator']} | {item['metric']} | {item['mean_effect']:.6f} | [{item['ci95'][0]:.6f}, {item['ci95'][1]:.6f}] | {item['holm_p_four_primary']:.6g} |"
        record(f"comparison_row:{key}", expected in text)
    for label, value in [
        ("RK-12 official unique18 grid", final["grid_sha256"]),
        ("RK-12 independent grid verification", final["grid_independent_sha256"]),
        ("RK-12 full actual-set matrix", final["matrix_sha256"]),
        ("RK-12 independent actual-set matrix verification", final["matrix_independent_sha256"]),
        ("RK-12 finalization", sha256(args.finalization)),
    ]:
        record(f"anchor:{label}", f"| {label} | `{value}` |" in text)
    record("audit_rk12_hashes", audit["rk12"]["matrix_sha256"] == sha256(args.matrix) and audit["rk12"]["finalization_sha256"] == sha256(args.finalization) and audit["rk12"]["run_count"] == 198)
    record("pending_main_model_preserved", "main CodonFlow-RK model baseline matrix and dense/time-matched comparison" in audit["pending_preserved"])
    record("pending_ood_and_wetlab_preserved", "OOD" in audit["pending_preserved"] and "wet-lab validation" in audit["pending_preserved"])
    record("non_submittable", "non-submittable working manuscript" in text and update["non_submittable_preserved"] is True)
    section = text.split(HEADING, 1)[1].split("## 7. Discussion", 1)[0]
    record("scientific_boundaries", "`dense_budget_step_auc_v2` remains null" in section and "not time-matched" in section and "no CodonFlow-RK generator result" in section and "SOTA claim" in section and audit["rk12"]["sota_claim"] is False)
    record("a7_unchanged", sha256(args.a7) == "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423")
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk12-paper-independent-verification-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks": checks,
        "checks_passed": passed,
        "checks_total": len(checks),
        "paper_sha256": sha256(args.paper),
        "audit_sha256": sha256(args.audit),
        "matrix_sha256": sha256(args.matrix),
        "finalization_sha256": sha256(args.finalization),
        "production_paper_script_imported": False,
        "scope": "exact RK-12 increment, provenance and scientific boundaries; not a full manuscript review",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
