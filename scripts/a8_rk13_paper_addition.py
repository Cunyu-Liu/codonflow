#!/usr/bin/env python3
"""Append the finalized RK-13 EnsembleDesign seven-method evidence to A8 v22."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

BASE_PAPER_SHA256 = "0c38ea11bb5f73d470c456aa2332353f211412e2ae6658ad09154d61f972db9e"
BASE_AUDIT_SHA256 = "b4584c6715f02d3502da760efe5787cf2a78e615c17ac43afe26ee69c3fd0863"
A7_SHA256 = "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423"
HEADING = "### 6.18 RK-13 EnsembleDesign and seven-method actual-set comparison"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def fmt(value: float) -> str:
    return f"{value:.6f}"


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
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--update-report", type=Path, required=True)
    args = parser.parse_args()
    if args.update_report.exists():
        raise FileExistsError(args.update_report)
    if sha256(args.paper) != BASE_PAPER_SHA256 or sha256(args.audit) != BASE_AUDIT_SHA256 or sha256(args.a7) != A7_SHA256:
        raise ValueError("A8 v21 or A7 base hash mismatch")
    final = json.loads(args.finalization.read_text())
    ensemble = json.loads(args.ensemble.read_text())
    ensemble_independent = json.loads(args.ensemble_independent.read_text())
    matrix = json.loads(args.matrix.read_text())
    matrix_independent = json.loads(args.matrix_independent.read_text())
    if not final["status"].startswith("PASS_") or final["checks_passed"] != final["checks_total"]:
        raise ValueError("RK-13 finalization is not passing")
    if final["ensemble_sha256"] != sha256(args.ensemble) or final["matrix_sha256"] != sha256(args.matrix):
        raise ValueError("finalization evidence hash mismatch")
    text = args.paper.read_text()
    if HEADING in text:
        raise ValueError("RK-13 section already exists")
    args.snapshot_dir.mkdir(parents=True, exist_ok=False)
    snapshot_paper = args.snapshot_dir / "CodonFlow_preprint_A8_v21.md"
    snapshot_audit = args.snapshot_dir / "a8_rk_paper_sync_audit_v21.json"
    snapshot_a7 = args.snapshot_dir / "CodonFlow_preprint_A7.md"
    snapshot_paper.write_bytes(args.paper.read_bytes())
    snapshot_audit.write_bytes(args.audit.read_bytes())
    snapshot_a7.write_bytes(args.a7.read_bytes())
    summary = matrix["method_summary"]
    method_order = ["lineardesign_lambda11", "ensembledesign_11run", "gemorna", "codongpt", "cai_greedy", "uniform_synonymous", "lineardesign_scan"]
    rows = []
    for name in method_order:
        item = summary[name]
        rows.append(f"| {name} | {item['total_actual_outputs']} | {fmt(item['mean_hypervolume_normalized'])} | {fmt(item['mean_ned'])} | {item['min_identity_rate']:.3f} |")
    comparison_rows = []
    for key, item in matrix["primary_comparisons"].items():
        comparison_rows.append(f"| {item['comparator']} | {item['metric']} | {fmt(item['mean_effect'])} | [{fmt(item['ci95'][0])}, {fmt(item['ci95'][1])}] | {item['holm_p_twelve_primary']:.6g} |")
    direct_key = "lineardesign_lambda11_minus_ensembledesign_11run:hypervolume_normalized"
    direct = matrix["primary_comparisons"][direct_key]
    record_pairs = sum(record["unique_output_sequences"] for record in ensemble["records"])
    ensemble_cost = matrix["generation_cost_descriptive_not_time_matched"]["ensembledesign_11run"]["total_seconds"]
    ld_cost = matrix["generation_cost_descriptive_not_time_matched"]["lineardesign_lambda11"]["total_seconds"]
    section = f"""{HEADING}

I added the fixed-source EnsembleDesign baseline to the same unique18 development panel. The frozen protocol used 18 per-record official CPU processes and **198 generator runs** (11 per protein), with four internal threads per process, beam size 100, learning rate 0.03, epsilon 0.5 and three iterations. The raw runs yielded {record_pairs} unique record-sequence pairs after within-record deduplication and required {ensemble['total_generation_elapsed_s']:.3f} s of summed official-process wall clock. Every official CDS was protein-identical before the disclosed terminal TAA used only for shared evaluation. The independent raw-file verifier passed with a maximum official-versus-ViennaRNA EFE discrepancy of {ensemble_independent['max_efe_abs_delta_from_rounded_official']:.6g} kcal/mol.

The first verification attempt was stopped when unscaled ViennaRNA `pf()` returned its `100000.0` failure sentinel for `C41G7.2.1`; the failed report and all raw files were preserved unchanged. A separately frozen recovery applied MFE-based fold-compound rescaling consistently to every selected output and reexecuted `C41G7.2.1` plus the six not-yet-run records in a new output root. The selected evidence therefore contains 18 official processes and 198 generator runs, while 25 official processes and 209 generator runs were executed across the failed and recovery attempts. The EFE tolerance was not changed.

The seven-method matrix preserves all six RK-12 method fields exactly, binds their prior 139/139 independent PASS by hash, and recomputes only the new EnsembleDesign objectives from raw CDS using the same RSCU, per-record calibration and four objectives. The reference, six comparators, two metrics and Holm family of 12 paired tests were frozen before EnsembleDesign generation. Mean values remain descriptive over 18 development records. For NED, a positive LinearDesign-minus-comparator effect means greater sequence diversity, not better functional performance.

| Method | Actual outputs | Mean normalized HV | Mean pairwise NED | Minimum identity |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

| Comparator | Effect (LinearDesign - comparator) | Mean delta | Paired-bootstrap 95% CI | Holm p (12 tests) |
|---|---|---:|---:|---:|
{chr(10).join(comparison_rows)}

For the direct EnsembleDesign comparison, LinearDesign-minus-EnsembleDesign normalized HV was {direct['mean_effect']:.6f} (95% CI [{direct['ci95'][0]:.6f}, {direct['ci95'][1]:.6f}], Holm p={direct['holm_p_twelve_primary']:.6g}). The descriptive highest mean-HV method was `{matrix['descriptive_highest_mean_hv_method']}`; this is not a SOTA designation. The independent matrix verifier passed {matrix_independent['checks_passed']}/{matrix_independent['checks_total']} checks, recomputed all new raw objectives, HV, NED, Pareto counts and 12 paired intervals, and confirmed exact preservation of the six base-method fields. Measured generation time was {ld_cost:.3f} s for the single-worker LinearDesign grid and {ensemble_cost:.3f} s for EnsembleDesign with four internal threads; these costs are reported but are not unified or time-matched. Independent runs are not successive real-scorer budget checkpoints, so `dense_budget_step_auc_v2` remains null. This section contains no CodonFlow-RK main-generator result, functional OOD, wet-lab result or SOTA claim.

"""
    marker = "## 7. Discussion"
    if text.count(marker) != 1:
        raise ValueError("Discussion insertion marker missing")
    text = text.replace(marker, section + marker, 1)
    anchors = f"""| RK-13 frozen EnsembleDesign unique18 protocol | `{sha256(Path('/home/codonflow-a8-rk/configs/a8_rk13_ensembledesign_unique18_protocol_v1.json'))}` |
| RK-13 frozen recovery protocol | `{ensemble['recovery']['recovery_protocol_sha256']}` |
| RK-13 preserved failed v1 report | `{ensemble['recovery']['failed_report_sha256']}` |
| RK-13 official EnsembleDesign unique18 report | `{sha256(args.ensemble)}` |
| RK-13 independent EnsembleDesign verification | `{sha256(args.ensemble_independent)}` |
| RK-13 frozen seven-method matrix protocol | `{sha256(Path('/home/codonflow-a8-rk/configs/a8_rk13_seven_method_matrix_protocol_v1.json'))}` |
| RK-13 seven-method actual-set matrix | `{sha256(args.matrix)}` |
| RK-13 independent seven-method matrix verification | `{sha256(args.matrix_independent)}` |
| RK-13 finalization | `{sha256(args.finalization)}` |
"""
    anchor_marker = "\nA7 is retained as the prior manuscript snapshot."
    if text.count(anchor_marker) != 1:
        raise ValueError("evidence anchor marker missing")
    text = text.replace(anchor_marker, "\n" + anchors + anchor_marker, 1)
    audit = json.loads(args.audit.read_text())
    audit["base_v21_audit_sha256"] = BASE_AUDIT_SHA256
    audit["base_v21_paper_sha256"] = BASE_PAPER_SHA256
    audit["generated_sections"].extend(["6.18 RK-13 EnsembleDesign and seven-method actual-set comparison", "8.1 RK-13 evidence anchors"])
    audit["pre_rk13_snapshot"] = {
        "paper": str(snapshot_paper), "paper_sha256": sha256(snapshot_paper),
        "audit": str(snapshot_audit), "audit_sha256": sha256(snapshot_audit),
        "a7": str(snapshot_a7), "a7_sha256": sha256(snapshot_a7),
    }
    audit["rk13"] = {
        "ensemble_sha256": sha256(args.ensemble),
        "ensemble_independent_sha256": sha256(args.ensemble_independent),
        "recovery_protocol_sha256": ensemble["recovery"]["recovery_protocol_sha256"],
        "failed_v1_report_sha256": ensemble["recovery"]["failed_report_sha256"],
        "total_official_processes_across_attempts": 25,
        "total_generator_runs_across_attempts": 209,
        "matrix_sha256": sha256(args.matrix),
        "matrix_independent_sha256": sha256(args.matrix_independent),
        "finalization_sha256": sha256(args.finalization),
        "run_count": ensemble["run_count"], "record_count": ensemble["record_count"],
        "generation_seconds": ensemble["total_generation_elapsed_s"],
        "scope": "development seven-method actual-set matrix only",
        "sota_claim": False,
    }
    atomic(args.paper, text)
    audit["output_sha256"] = sha256(args.paper)
    atomic(args.audit, json.dumps(audit, indent=2) + "\n")
    report = {
        "schema": "a8-rk13-paper-update-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS",
        "base_paper_sha256": BASE_PAPER_SHA256, "base_audit_sha256": BASE_AUDIT_SHA256,
        "paper_sha256": sha256(args.paper), "audit_sha256": sha256(args.audit),
        "section": HEADING, "snapshot": audit["pre_rk13_snapshot"],
        "ensemble_sha256": sha256(args.ensemble), "matrix_sha256": sha256(args.matrix),
        "finalization_sha256": sha256(args.finalization),
        "non_submittable_preserved": True, "sota_claim": False,
    }
    args.update_report.parent.mkdir(parents=True, exist_ok=True)
    args.update_report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
