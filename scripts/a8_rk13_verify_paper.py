#!/usr/bin/env python3
"""Independently verify the exact A8 v22 RK-13 manuscript increment."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

HEADING = "### 6.18 RK-13 EnsembleDesign and seven-method actual-set comparison"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--a7", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--ensemble", type=Path, required=True)
    parser.add_argument("--ensemble-independent", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--matrix-independent", type=Path, required=True)
    parser.add_argument("--update-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    text = args.paper.read_text()
    audit = json.loads(args.audit.read_text())
    final = json.loads(args.finalization.read_text())
    ensemble = json.loads(args.ensemble.read_text())
    ensemble_independent = json.loads(args.ensemble_independent.read_text())
    matrix = json.loads(args.matrix.read_text())
    matrix_independent = json.loads(args.matrix_independent.read_text())
    update = json.loads(args.update_report.read_text())
    checks = []

    def record(name, passed, evidence=None):
        checks.append({"check": name, "pass": bool(passed), "evidence": evidence})

    snapshot = audit["pre_rk13_snapshot"]
    record("snapshot_paper", sha256(Path(snapshot["paper"])) == snapshot["paper_sha256"] == audit["base_v21_paper_sha256"])
    record("snapshot_audit", sha256(Path(snapshot["audit"])) == snapshot["audit_sha256"] == audit["base_v21_audit_sha256"])
    record("snapshot_a7", sha256(Path(snapshot["a7"])) == snapshot["a7_sha256"] == sha256(args.a7))
    record("current_output_hash", audit["output_sha256"] == sha256(args.paper))
    record("update_hashes", update["paper_sha256"] == sha256(args.paper) and update["audit_sha256"] == sha256(args.audit) and update["matrix_sha256"] == sha256(args.matrix) and update["ensemble_sha256"] == sha256(args.ensemble) and update["finalization_sha256"] == sha256(args.finalization))
    record("section_once", text.count(HEADING) == 1)
    record("section_before_discussion", text.index(HEADING) < text.index("## 7. Discussion"))
    record("generated_sections", "6.18 RK-13 EnsembleDesign and seven-method actual-set comparison" in audit["generated_sections"] and "8.1 RK-13 evidence anchors" in audit["generated_sections"])
    record("finalization_pass", final["status"].startswith("PASS_") and final["checks_passed"] == final["checks_total"])
    record("official_run_text", "18 per-record official CPU processes and **198 generator runs**" in text and "11 per protein" in text)
    record_pairs = sum(r["unique_output_sequences"] for r in ensemble["records"])
    record("unique_sequence_text", f"yielded {record_pairs} unique record-sequence pairs" in text)
    record("generation_cost_text", f"{ensemble['total_generation_elapsed_s']:.3f} s of summed official-process wall clock" in text)
    record("ensemble_verifier_text", f"{ensemble_independent['max_efe_abs_delta_from_rounded_official']:.6g} kcal/mol" in text)
    record("recovery_disclosure_text", "100000.0` failure sentinel" in text and "25 official processes and 209 generator runs" in text and "EFE tolerance was not changed" in text and "MFE-based fold-compound rescaling" in text)
    record("matrix_verifier_text", f"{matrix_independent['checks_passed']}/{matrix_independent['checks_total']} checks" in text)
    for name, item in matrix["method_summary"].items():
        expected = f"| {name} | {item['total_actual_outputs']} | {item['mean_hypervolume_normalized']:.6f} | {item['mean_ned']:.6f} | {item['min_identity_rate']:.3f} |"
        record(f"method_row:{name}", expected in text)
    for key, item in matrix["primary_comparisons"].items():
        expected = f"| {item['comparator']} | {item['metric']} | {item['mean_effect']:.6f} | [{item['ci95'][0]:.6f}, {item['ci95'][1]:.6f}] | {item['holm_p_twelve_primary']:.6g} |"
        record(f"comparison_row:{key}", expected in text)
    direct = matrix["primary_comparisons"]["lineardesign_lambda11_minus_ensembledesign_11run:hypervolume_normalized"]
    record("direct_effect_text", f"was {direct['mean_effect']:.6f} (95% CI [{direct['ci95'][0]:.6f}, {direct['ci95'][1]:.6f}], Holm p={direct['holm_p_twelve_primary']:.6g})" in text)
    for label, value in [
        ("RK-13 frozen recovery protocol", ensemble["recovery"]["recovery_protocol_sha256"]),
        ("RK-13 preserved failed v1 report", ensemble["recovery"]["failed_report_sha256"]),
        ("RK-13 official EnsembleDesign unique18 report", sha256(args.ensemble)),
        ("RK-13 independent EnsembleDesign verification", sha256(args.ensemble_independent)),
        ("RK-13 seven-method actual-set matrix", sha256(args.matrix)),
        ("RK-13 independent seven-method matrix verification", sha256(args.matrix_independent)),
        ("RK-13 finalization", sha256(args.finalization)),
    ]:
        record(f"anchor:{label}", f"| {label} | `{value}` |" in text)
    record("audit_rk13_hashes", audit["rk13"]["matrix_sha256"] == sha256(args.matrix) and audit["rk13"]["ensemble_sha256"] == sha256(args.ensemble) and audit["rk13"]["finalization_sha256"] == sha256(args.finalization) and audit["rk13"]["run_count"] == 198)
    record("audit_recovery_hashes", audit["rk13"]["recovery_protocol_sha256"] == ensemble["recovery"]["recovery_protocol_sha256"] and audit["rk13"]["failed_v1_report_sha256"] == ensemble["recovery"]["failed_report_sha256"] and audit["rk13"]["total_official_processes_across_attempts"] == 25 and audit["rk13"]["total_generator_runs_across_attempts"] == 209)
    record("pending_main_model_preserved", "main CodonFlow-RK model baseline matrix and dense/time-matched comparison" in audit["pending_preserved"])
    record("pending_ood_and_wetlab_preserved", "OOD" in audit["pending_preserved"] and "wet-lab validation" in audit["pending_preserved"])
    record("non_submittable", "non-submittable working manuscript" in text and update["non_submittable_preserved"] is True)
    section = text.split(HEADING, 1)[1].split("## 7. Discussion", 1)[0]
    record("scientific_boundaries", "`dense_budget_step_auc_v2` remains null" in section and "not unified or time-matched" in section and "no CodonFlow-RK main-generator result" in section and "SOTA claim" in section and audit["rk13"]["sota_claim"] is False)
    record("ned_interpretation", "greater sequence diversity, not better functional performance" in section)
    record("a7_unchanged", sha256(args.a7) == "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423")
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk13-paper-independent-verification-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks": checks, "checks_passed": passed, "checks_total": len(checks),
        "paper_sha256": sha256(args.paper), "audit_sha256": sha256(args.audit),
        "ensemble_sha256": sha256(args.ensemble), "matrix_sha256": sha256(args.matrix),
        "finalization_sha256": sha256(args.finalization),
        "production_paper_script_imported": False,
        "scope": "exact RK-13 increment, provenance and scientific boundaries; not a full manuscript review",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
