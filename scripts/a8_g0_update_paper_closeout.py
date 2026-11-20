#!/usr/bin/env python3
"""Append the independently verified RK-G0 closeout to an exact manuscript base."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

MARKER = "Bounded RK-G0 readiness and unified cost ledger"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def fmt(value):
    return "—" if value is None else repr(value)


def build_section(prod, ind, final, correction, section_number):
    rows = prod["cost_matrix"]
    measured = [row for row in rows if row["metrics"].get("wall_clock_s") is not None]
    lines = [
        f"### 6.{section_number} {MARKER}", "",
        f"We froze {len(prod['gate_results'])} source/gate facts and {len(rows)} explicit cost rows from {prod['summary']['source_count']} hashed reports. The bounded RK-G0 gate required usable real functional data with reliable splits, reproducible key baselines, and independently tested dense/actual-set evaluators. Boël sequence-OOD, MAGE development OOF, the Mordstein 16-file/eight-bin recovery, the 21-file RNARL pair-table QC, LinearDesign, EnsembleDesign, CodonTransformer, CAGFN, RiboMIMO study-OOD, and both evaluator families met their frozen technical criteria. This is a bounded readiness result, not a claim that every dataset, official model, or external dense trajectory is complete.", "",
        "Costs are reported only within their original task, hardware, and execution scopes. A dash is an explicit null with a machine-readable reason in the frozen JSON; it is never zero. Training, generation/inference, scoring, unique scorer calls, and total wall time are not summed or ranked across mixed or overlapping scopes. No time-matched or complete-SOTA interpretation is authorized.", "",
        "| Method | Scope | Wall (s) | Train (s) | Generation/inference (s) | Scoring/selection (s) | Calls / outputs |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in measured:
        m = row["metrics"]
        if m.get("unique_scorer_calls") is not None:
            extra = f"{m['unique_scorer_calls']} unique scorer calls"
        elif m.get("actual_outputs") is not None:
            extra = f"{m['actual_outputs']} outputs"
        elif m.get("runs") is not None:
            extra = f"{m['runs']} runs/seeds"
        else:
            extra = "—"
        scope = {
            "lineardesign_unique18": "unique18, 198 runs, actual-set",
            "ensembledesign_unique18": "unique18, 198 runs, actual-set",
            "cagfn_official_smoke": "bounded official toy smoke",
            "id3_official_quick_test": "one protein, 2 iterations, 1 seed",
            "codontransformer_official_smoke": "4 released-weight GPU inferences",
            "veloharmo_official_smoke": "released test + bounded GA",
            "ixnos_real_prefix": "1M-read prefix, 2 epochs",
            "rose_released_checkpoint": "2 studies, released checkpoint",
            "ribomimo_study_ood": "study-OOD, 3 independent seeds",
            "rk06_dense_uniform": "unique18 dense, 54 runs",
            "rk06_dense_hill_climbing": "unique18 dense, 54 runs",
            "rk06_dense_mh_annealing": "unique18 dense, 54 runs",
            "rk06_dense_areuredi_style": "unique18 dense, 54 runs",
        }[row["row_id"]]
        lines.append(
            f"| {row['method']} | {scope} | {fmt(m.get('wall_clock_s'))} | {fmt(m.get('training_s'))} | "
            f"{fmt(m.get('generation_or_inference_s'))} | {fmt(m.get('scoring_s'))} | {extra} |"
        )
    inherited = {row["row_id"]: row for row in rows}
    lines += [
        "",
        "The five inherited external actual-set groups remain cost-null rather than cost-zero: "
        f"codonGPT={inherited['inherited_codongpt']['metrics']['actual_outputs']} outputs, "
        f"GEMORNA={inherited['inherited_gemorna']['metrics']['actual_outputs']}, "
        f"CAI greedy={inherited['inherited_cai_greedy']['metrics']['actual_outputs']}, "
        f"uniform synonymous={inherited['inherited_uniform_synonymous']['metrics']['actual_outputs']}, and "
        f"LinearDesignScan={inherited['inherited_lineardesign_scan']['metrics']['actual_outputs']}. "
        f"RNARL contributes {inherited['rnarl_availability']['metrics']['qc_pairs']} clean LinearDesign-like QC pairs, not valid official-model generations. CDGB source identity remains unresolved; COformer and CHARMING remain explicitly NOT_RUN. These states are not evidence that the corresponding methods are ineffective.", "",
        "The source-feasibility task is closed only as a feasibility report: iXnos executed a real 1,000,000-read prefix with independent P-site offset re-derivation, while the later source audit recovered metadata-level UTR/Ribo/VeloHARMO scope. It did not complete a full UTR–CDS remap, full SRR1049521 processing, natural-CDS eligibility, or five-species VeloHARMO matrices. The frozen status is therefore `FEASIBILITY_CLOSED_NOT_FULL_REMAP`.", "",
        f"Production passed **{prod['technical_passed_checks']}/{prod['technical_check_count']} checks**. The independent standard-library verifier recomputed every extraction and gate fact and passed **{ind['passed_checks']}/{ind['check_count']} checks**, with maximum numeric discrepancy {ind['max_numeric_delta']!r}; targeted tests passed **9/9**, and finalization passed **{final['passed_checks']}/{final['check_count']} checks**. The first protocol failed on `lineardesign_unique_sequences`; a full preflight then found ten invalid pointers. The v1 protocol/log and correction record are retained. The closeout reran no baseline, added zero scorer calls, and started no generator training.", "",
        "The resulting status is `PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY`. External dense coverage, time-matched evaluation, complete SOTA, full UTR–CDS remapping, RNARL official-model reproduction, functional-untouched evaluation, wet-lab validation, and RK-G1 remain unclosed. Expensive CodonFlow-RK generator training remains unauthorized, and this manuscript remains non-submittable.", "",
    ]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--expected-base-sha", required=True)
    ap.add_argument("--base-version", required=True)
    ap.add_argument("--new-version", required=True)
    ap.add_argument("--section-number")
    args = ap.parse_args()
    root = Path(args.root)
    if not re.fullmatch(r"[0-9a-f]{64}", args.expected_base_sha):
        raise SystemExit("invalid base SHA")
    if not re.fullmatch(r"v[0-9]+", args.base_version) or not re.fullmatch(r"v[0-9]+", args.new_version):
        raise SystemExit("versions must be vN")
    paper = root / "paper/CodonFlow_preprint_A8.md"
    audit = root / "audits/20261120/RK06"
    protocol_path = root / "configs/a8_g0_closeout_protocol_v2.json"
    prod_path = audit / "g0_unified_cost_closeout_v2.json"
    ind_path = audit / "g0_unified_cost_closeout_independent_v1.json"
    final_path = audit / "g0_unified_cost_closeout_finalization_v1.json"
    correction_path = audit / "g0_closeout_correction_v1.json"
    unit_path = audit / "g0_closeout_targeted_tests_v1.console.log"
    base = paper.read_text()
    if sha(paper) != args.expected_base_sha:
        raise SystemExit("manuscript base SHA mismatch")
    if MARKER in base:
        raise SystemExit("G0 section already exists")
    anchor_marker = "\n\nA7 is retained as the prior manuscript snapshot."
    if base.count("\n## 7. Discussion") != 1 or base.count(anchor_marker) != 1:
        raise SystemExit("unexpected manuscript structure")
    prod, ind, final, correction = map(load, [prod_path, ind_path, final_path, correction_path])
    if not prod["overall_pass"] or not ind["all_pass"] or final["status"] != "PASS_BOUNDED_G0_CLOSEOUT":
        raise SystemExit("science reports do not pass")
    if prod["technical_passed_checks"] != prod["technical_check_count"]:
        raise SystemExit("production check failure")
    if ind["passed_checks"] != ind["check_count"] or ind["max_numeric_delta"] != 0.0:
        raise SystemExit("independent check failure")
    if ind["production_sha256"] != sha(prod_path) or prod["protocol_sha256"] != sha(protocol_path):
        raise SystemExit("evidence hash mismatch")
    if correction["artifacts"]["v2_production"]["sha256"] != sha(prod_path):
        raise SystemExit("correction does not bind production")
    if correction["artifacts"]["v2_protocol"]["sha256"] != sha(protocol_path):
        raise SystemExit("correction does not bind protocol")
    if correction["artifacts"]["independent"]["sha256"] != sha(ind_path):
        raise SystemExit("correction does not bind independent report")
    if correction["artifacts"]["tests"]["sha256"] != sha(unit_path):
        raise SystemExit("correction does not bind test log")
    if "9 passed" not in unit_path.read_text():
        raise SystemExit("targeted tests do not pass")
    if prod["boundaries"]["rk_g1_passed"] or prod["boundaries"]["generator_training_authorized"]:
        raise SystemExit("scientific boundary changed")
    numbers = [int(x) for x in re.findall(r"^### 6\.(\d+) ", base, re.M)]
    section_number = args.section_number or str(max(numbers) + 1)
    if not re.fullmatch(r"[0-9]+", section_number) or f"### 6.{section_number} " in base:
        raise SystemExit("invalid section number")
    section = build_section(prod, ind, final, correction, section_number)
    evidence = [
        ("G0 closeout protocol v2", protocol_path),
        ("G0 unified cost production", prod_path),
        ("G0 independent verification", ind_path),
        ("G0 finalization", final_path),
        ("G0 correction record", correction_path),
        ("G0 retained v1 protocol", root / "configs/a8_g0_closeout_protocol_v1.json"),
        ("G0 retained v1 failure log", audit / "g0_unified_cost_closeout_v1.console.log"),
        ("G0 targeted 9-test log", unit_path),
    ]
    anchors = "\n" + "\n".join(f"| {label} | `{sha(path)}` |" for label, path in evidence)
    updated = base.replace("\n## 7. Discussion", "\n" + section + "## 7. Discussion", 1)
    updated = updated.replace(anchor_marker, anchors + anchor_marker, 1)
    if updated.count(MARKER) != 1:
        raise SystemExit("section insertion count mismatch")
    restored = updated.replace(section, "", 1).replace(anchors, "", 1)
    if restored != base:
        raise SystemExit("internal exact-restoration check failed")
    snapshot = root / f"paper/snapshots/g0_closeout_{args.new_version}"
    if snapshot.exists():
        raise SystemExit("snapshot directory already exists")
    snapshot.mkdir(parents=True)
    base_snapshot = snapshot / f"CodonFlow_preprint_A8_{args.base_version}.md"
    shutil.copy2(paper, base_snapshot)
    for _, path in evidence:
        shutil.copy2(path, snapshot / Path(path).name)
    a7 = root / "paper/CodonFlow_preprint_A7.md"
    record = root / f"paper/a8_g0_closeout_paper_update_{args.new_version}.json"
    if record.exists():
        raise SystemExit("paper update record already exists")
    update = {
        "schema": "a8-g0-closeout-paper-update-v1",
        "base_version": args.base_version,
        "new_version": args.new_version,
        "base_sha256": args.expected_base_sha,
        "new_sha256": hashlib.sha256(updated.encode()).hexdigest(),
        "section_heading": f"### 6.{section_number} {MARKER}",
        "section_number": section_number,
        "section_sha256": hashlib.sha256(section.encode()).hexdigest(),
        "section_markdown": section,
        "anchor_markdown": anchors,
        "snapshot_directory": str(snapshot),
        "base_snapshot": str(base_snapshot),
        "evidence": {label: {"path": str(path), "sha256": sha(path)} for label, path in evidence},
        "production_sha256": sha(prod_path),
        "independent_sha256": sha(ind_path),
        "finalization_sha256": sha(final_path),
        "correction_sha256": sha(correction_path),
        "protocol_sha256": sha(protocol_path),
        "unit_test_log_sha256": sha(unit_path),
        "a7_sha256": sha(a7) if a7.exists() else None,
        "g0_status": prod["g0_status"],
        "rk_g1_passed": False,
        "generator_training_authorized": False,
        "manuscript_submittable": False,
    }
    paper.write_text(updated)
    record.write_text(json.dumps(update, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"new_version": args.new_version, "new_sha256": update["new_sha256"],
                      "section": update["section_heading"]}, indent=2))


if __name__ == "__main__":
    main()
