#!/usr/bin/env python3
"""Append only independently verified RK06 claims to manuscript v27, producing v28."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper/CodonFlow_preprint_A8.md"
AUDIT = ROOT / "audits/20261120/RK06"
EXPECTED_BASE_SHA = "c745b3e73b7d9f380f7c0ce326cc5fba2cfae769273b2e58f606a73dba9e0952"
SECTION_HEADING = "### 6.24 Real dense-budget simple-search trajectories on unique18"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fmt(value):
    return f"{float(value):.9f}"


def pfmt(value):
    return f"{float(value):.8f}"


def build_section(claims, independent, finalization):
    lines = [
        SECTION_HEADING,
        "",
        "We measured real anytime behavior for four non-learned simple searches on the 18 unique18 development records. The frozen panel comprised three seeds, four methods and 500 successive unique proxy-scorer evaluations per run, giving 216 runs and 108,000 scored sequences. Every sequence remained synonymous with its source. The initial state consumed budget B=1. The primary dense endpoint was sum(HV_b for b=1,...,499)/499; B=500 was retained as an endpoint and was excluded from the AUC. Normalized HV used each record's frozen calibration reference and scale and was not clipped to [0,1]. No synthetic origin, trapezoidal integration, zero-filled missing budget or conversion of unordered external actual sets was used.",
        "",
        "| Method | Mean dense AUC | Mean HV B50 | Mean HV B100 | Mean HV B500 | Total wall time (s) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in claims["method_summary"]:
        lines.append(f"| {row['method']} | {fmt(row['mean_dense_auc'])} | {fmt(row['mean_hv_B50'])} | {fmt(row['mean_hv_B100'])} | {fmt(row['mean_hv_B500'])} | {fmt(row['sum_wall_clock_seconds'])} |")
    lines.extend([
        "",
        "The record was the statistical unit. For each record and method, values were first averaged arithmetically over seeds 0, 1 and 2. Paired record bootstrap used 20,000 resamples, paired sign-flip permutation used 20,000 draws, and Holm correction covered the six primary tests. A supported advantage required a positive effect, a 95% CI lower bound above zero and Holm-adjusted p<0.05.",
        "",
        "| Method minus uniform | Endpoint | Effect | 95% CI | Holm p | Supported advantage |",
        "|---|---|---:|---|---:|---|",
    ])
    for row in claims["primary_tests"]:
        endpoint = "dense AUC" if row["endpoint"] == "dense_budget_step_auc_v2" else "B500 normalized HV"
        ci = f"[{fmt(row['ci95'][0])}, {fmt(row['ci95'][1])}]"
        lines.append(f"| {row['method']} | {endpoint} | {fmt(row['effect'])} | {ci} | {pfmt(row['holm_p'])} | {'yes' if row['supported_advantage'] else 'no'} |")
    supported = [row for row in claims["primary_tests"] if row["supported_advantage"]]
    if supported:
        labels = ", ".join(f"{row['method']} ({'dense AUC' if row['endpoint'] == 'dense_budget_step_auc_v2' else 'B500 HV'})" for row in supported)
        interpretation = f"The frozen rule supported {len(supported)} of six comparisons: {labels}. The remaining comparisons, including negative and interval-crossing effects, are retained in the table."
    else:
        interpretation = "No comparison met the frozen positive-effect, interval and multiplicity requirements. All positive, negative and interval-crossing effects are retained in the table."
    lines.extend([
        "",
        interpretation + " These are development proxy-search comparisons, not functional or external SOTA results.",
        "",
        "Secondary bidirectional strict-dominance fractions at B=500 were computed from each run's Pareto points. They describe proxy-output sets only.",
        "",
        "| Method A | Method B | Fraction of A dominated by B | Fraction of B dominated by A |",
        "|---|---|---:|---:|",
    ])
    for row in claims["bidirectional_strict_dominance_B500"]:
        lines.append(f"| {row['method_a']} | {row['method_b']} | {fmt(row['mean_fraction_a_strictly_dominated_by_b'])} | {fmt(row['mean_fraction_b_strictly_dominated_by_a'])} |")
    lines.extend([
        "",
        f"Independent verification recomputed every CAI, ViennaRNA MFE, GC and motif objective from sequence, all 500-point normalized-HV curves, secondary budgets, NED, Pareto counts, strict dominance and paired inference. It passed **{independent['check_counts']['passed']}/{independent['check_counts']['total']} checks**; the maximum absolute discrepancy was {independent['maximum_differences']['objectives']:.3g} for objectives, {independent['maximum_differences']['dense_curve']:.3g} for dense HV and {independent['maximum_differences']['paired_inference']:.3g} for paired inference. Finalization passed **{finalization['check_counts']['passed']}/{finalization['check_counts']['total']} checks**. Wall times are internal one-worker-per-run costs and are not time-matched to LinearDesign, EnsembleDesign or another external implementation. External independent-lambda outputs remain unordered actual sets, so their dense AUC remains null.",
        "",
        "This section closes only the real dense-budget simple-search evidence gap on unique18 development proxies. It used no untouched24 record, functional-untouched assay row, MAGE mechanism-test construct or functional label; it trained no generator. It does not establish functional effectiveness, CodonFlow-RK improvement, external SOTA, RK-G1 closure or generator-training readiness. The manuscript remains non-submittable.",
        "",
    ])
    return "\n".join(lines)


def main():
    claims_path = AUDIT / "simple_search_dense_claims_v1.json"
    finalization_path = AUDIT / "simple_search_dense_finalization_v1.json"
    production_path = AUDIT / "simple_search_dense_unique18_v1.json"
    independent_path = AUDIT / "simple_search_dense_independent_v2.json"
    protocol_path = ROOT / "configs/a8_rk06_simple_search_dense_unique18_protocol_v1.json"
    claims = json.loads(claims_path.read_text())
    finalization = json.loads(finalization_path.read_text())
    independent = json.loads(independent_path.read_text())
    if not claims["finalization_overall_pass"] or not finalization["overall_pass"] or not independent["overall_pass"]:
        raise RuntimeError("refusing paper update without passing finalization and independent verification")
    if claims["finalization_sha256"] != sha256(finalization_path):
        raise RuntimeError("claims do not reference the current finalization artifact")
    base = PAPER.read_text()
    if hashlib.sha256(base.encode()).hexdigest() != EXPECTED_BASE_SHA:
        raise RuntimeError("manuscript is not frozen v27")
    if SECTION_HEADING in base or "### 6.24 " in base:
        raise RuntimeError("section 6.24 already exists; refusing duplicate insertion")
    section = build_section(claims, independent, finalization)
    anchor_rows = "\n".join([
        "",
        f"| RK06 simple-search dense frozen protocol | `{sha256(protocol_path)}` |",
        f"| RK06 simple-search dense production | `{sha256(production_path)}` |",
        f"| RK06 simple-search dense independent verification | `{sha256(independent_path)}` |",
        f"| RK06 simple-search dense finalization | `{sha256(finalization_path)}` |",
        f"| RK06 simple-search dense claims | `{sha256(claims_path)}` |",
        "",
    ])
    updated = base.replace("\n## 7. Discussion", "\n" + section + "## 7. Discussion", 1)
    marker = "\nA7 is retained as the prior manuscript snapshot."
    if marker not in updated:
        raise RuntimeError("evidence-anchor insertion marker missing")
    updated = updated.replace(marker, anchor_rows + "A7 is retained as the prior manuscript snapshot.", 1)
    if updated == base or updated.count(SECTION_HEADING) != 1:
        raise RuntimeError("paper update did not produce exactly one new section")
    snapshot = ROOT / "paper/snapshots/rk06_simple_search_dense_v28"
    snapshot.mkdir(parents=True, exist_ok=False)
    shutil.copy2(PAPER, snapshot / "CodonFlow_preprint_A8_v27.md")
    for path in [claims_path, finalization_path, production_path, independent_path, protocol_path]:
        shutil.copy2(path, snapshot / path.name)
    temporary = PAPER.with_suffix(".md.tmp")
    temporary.write_text(updated)
    os.replace(temporary, PAPER)
    update = {
        "schema": "a8-rk06-simple-search-dense-paper-update-v1",
        "base_version": "v27",
        "new_version": "v28",
        "base_sha256": EXPECTED_BASE_SHA,
        "new_sha256": sha256(PAPER),
        "section_heading": SECTION_HEADING,
        "section_sha256": hashlib.sha256(section.encode()).hexdigest(),
        "anchor_rows": anchor_rows,
        "claims_sha256": sha256(claims_path),
        "finalization_sha256": sha256(finalization_path),
        "independent_sha256": sha256(independent_path),
        "snapshot": str(snapshot),
        "manuscript_submittable": False,
        "scientific_gate_passed": False,
        "rk_g1_closed": False,
    }
    (ROOT / "paper/a8_rk06_simple_search_dense_paper_update.json").write_text(json.dumps(update, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"new_version": "v28", "new_sha256": update["new_sha256"], "section": SECTION_HEADING}))


if __name__ == "__main__":
    main()
