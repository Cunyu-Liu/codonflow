#!/usr/bin/env python3
"""Append the verified RK-12 development actual-set matrix to A8 v18."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

BASE_PAPER_SHA256 = "b3816b8d9940917ef14c3d246c2ed45509ed465f7e33e95e92385c4e36c274ae"
BASE_AUDIT_SHA256 = "1799f411b124f177e9f7e04278b7c7a842ede1a01aed481a7ac42e1928c8279e"
A7_SHA256 = "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423"
HEADING = "### 6.14 RK-12 unique18 LinearDesign and external actual-set matrix"


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
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--update-report", type=Path, required=True)
    args = parser.parse_args()
    if args.update_report.exists():
        raise FileExistsError(args.update_report)
    if sha256(args.paper) != BASE_PAPER_SHA256 or sha256(args.audit) != BASE_AUDIT_SHA256 or sha256(args.a7) != A7_SHA256:
        raise ValueError("A8 v17 or A7 base hash mismatch")
    final = json.loads(args.finalization.read_text())
    matrix = json.loads(args.matrix.read_text())
    if not final["status"].startswith("PASS_") or final["checks_passed"] != final["checks_total"]:
        raise ValueError("RK-12 finalization is not passing")
    text = args.paper.read_text()
    if HEADING in text:
        raise ValueError("RK-12 section already exists")
    args.snapshot_dir.mkdir(parents=True, exist_ok=False)
    snapshot_paper = args.snapshot_dir / "CodonFlow_preprint_A8_v17.md"
    snapshot_audit = args.snapshot_dir / "a8_rk_paper_sync_audit_v17.json"
    snapshot_a7 = args.snapshot_dir / "CodonFlow_preprint_A7.md"
    snapshot_paper.write_bytes(args.paper.read_bytes())
    snapshot_audit.write_bytes(args.audit.read_bytes())
    snapshot_a7.write_bytes(args.a7.read_bytes())
    summary = matrix["method_summary"]
    method_order = ["lineardesign_lambda11", "gemorna", "codongpt", "cai_greedy", "uniform_synonymous", "lineardesign_scan"]
    rows = []
    for name in method_order:
        item = summary[name]
        rows.append(f"| {name} | {item['total_actual_outputs']} | {fmt(item['mean_hypervolume_normalized'])} | {fmt(item['mean_ned'])} | {item['min_identity_rate']:.3f} |")
    comparison_rows = []
    for key, item in matrix["primary_comparisons"].items():
        comparison_rows.append(
            f"| {item['comparator']} | {item['metric']} | {fmt(item['mean_effect'])} | [{fmt(item['ci95'][0])}, {fmt(item['ci95'][1])}] | {item['holm_p_four_primary']:.6g} |"
        )
    section = f"""{HEADING}

I expanded the fixed-source LinearDesign executable from the C01 smoke to the frozen unique18 development panel at lambda = 0.0, 0.1, ..., 1.0. The formal run comprised **{final['run_count']} official CPU processes** ({final['record_count']} records x 11 lambdas) with one worker and preserved raw stdout/stderr. It produced {final['unique_output_sequences_global']} distinct record-sequence pairs and required {final['lineardesign_generation_seconds']:.3f} s of summed official-process wall clock; independent scoring time is reported separately. All 198 outputs were protein-identical. The independent grid verifier passed {final['checks'][1]['evidence']}/{final['checks'][1]['evidence']} checks with zero CAI/MFE recomputation error, and the three overlapping C01 sequences were exactly identical to the earlier official smoke.

For cross-method comparison, all raw CDS outputs were rescored using the same v4-train RSCU, frozen per-record calibration and four objectives. LinearDesign outputs received the disclosed terminal TAA before evaluation. The actual-set matrix contains {len(matrix['records'])} development records and six method columns; the primary comparator set and four paired tests were frozen before full-panel scoring. Mean values below are descriptive over 18 records, not a dense-budget or SOTA ranking.

| Method | Actual outputs | Mean normalized HV | Mean pairwise NED | Minimum identity |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

| Comparator | Effect (LinearDesign - comparator) | Mean delta | Paired-bootstrap 95% CI | Holm p (4 tests) |
|---|---|---:|---:|---:|
{chr(10).join(comparison_rows)}

The independent matrix verifier recomputed every raw objective, NED, Pareto/HV value and paired interval without importing the production matrix module ({final['checks'][6]['evidence']}/{final['checks'][6]['evidence']} PASS); finalization passed {final['checks_passed']}/{final['checks_total']} checks and the contract tests passed 10/10. Lambda is an objective weight, not a real scorer budget, so `dense_budget_step_auc_v2` remains null. Legacy baseline cost fields are not time-matched to the new single-worker measurements. This section contains no CodonFlow-RK generator result, untouched evaluation, functional OOD, wet-lab result or SOTA claim.

"""
    marker = "## 7. Discussion"
    if text.count(marker) != 1:
        raise ValueError("Discussion insertion marker missing")
    text = text.replace(marker, section + marker, 1)
    anchors = f"""| RK-12 frozen LinearDesign grid protocol | `{sha256(Path('/home/codonflow-a8-rk/configs/a8_rk12_lineardesign_unique18_protocol_v1.json'))}` |
| RK-12 official unique18 grid | `{final['grid_sha256']}` |
| RK-12 independent grid verification | `{final['grid_independent_sha256']}` |
| RK-12 frozen actual-set matrix protocol | `{sha256(Path('/home/codonflow-a8-rk/configs/a8_rk12_actual_set_matrix_protocol_v1.json'))}` |
| RK-12 full actual-set matrix | `{final['matrix_sha256']}` |
| RK-12 independent actual-set matrix verification | `{final['matrix_independent_sha256']}` |
| RK-12 finalization | `{sha256(args.finalization)}` |
"""
    anchor_marker = "\nA7 is retained as the prior manuscript snapshot."
    if text.count(anchor_marker) != 1:
        raise ValueError("evidence anchor marker missing")
    text = text.replace(anchor_marker, "\n" + anchors + anchor_marker, 1)
    audit = json.loads(args.audit.read_text())
    audit["base_v17_audit_sha256"] = BASE_AUDIT_SHA256
    audit["base_v17_paper_sha256"] = BASE_PAPER_SHA256
    audit["generated_sections"].extend(["6.14 RK-12 unique18 LinearDesign and external actual-set matrix", "8.1 RK-12 evidence anchors"])
    audit["pending_preserved"] = [
        "main CodonFlow-RK model baseline matrix and dense/time-matched comparison" if item == "main baseline matrix" else item
        for item in audit["pending_preserved"]
    ]
    audit["pre_rk12_snapshot"] = {
        "paper": str(snapshot_paper),
        "paper_sha256": sha256(snapshot_paper),
        "audit": str(snapshot_audit),
        "audit_sha256": sha256(snapshot_audit),
        "a7": str(snapshot_a7),
        "a7_sha256": sha256(snapshot_a7),
    }
    audit["rk12"] = {
        "grid_sha256": final["grid_sha256"],
        "grid_independent_sha256": final["grid_independent_sha256"],
        "matrix_sha256": final["matrix_sha256"],
        "matrix_independent_sha256": final["matrix_independent_sha256"],
        "finalization_sha256": sha256(args.finalization),
        "run_count": final["run_count"],
        "record_count": final["record_count"],
        "generation_seconds": final["lineardesign_generation_seconds"],
        "scope": "development actual-set external-method matrix only",
        "sota_claim": False,
    }
    atomic(args.paper, text)
    audit["output_sha256"] = sha256(args.paper)
    atomic(args.audit, json.dumps(audit, indent=2) + "\n")
    report = {
        "schema": "a8-rk12-paper-update-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS",
        "base_paper_sha256": BASE_PAPER_SHA256,
        "base_audit_sha256": BASE_AUDIT_SHA256,
        "paper_sha256": sha256(args.paper),
        "audit_sha256": sha256(args.audit),
        "section": HEADING,
        "snapshot": audit["pre_rk12_snapshot"],
        "matrix_sha256": final["matrix_sha256"],
        "finalization_sha256": sha256(args.finalization),
        "non_submittable_preserved": True,
        "sota_claim": False,
    }
    args.update_report.parent.mkdir(parents=True, exist_ok=True)
    args.update_report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
