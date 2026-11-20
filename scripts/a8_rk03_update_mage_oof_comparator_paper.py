#!/usr/bin/env python3
"""Append the verified MAGE OOF comparator audit to a frozen manuscript base."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

MARKER = "Development-only MAGE OOF comparator closure"


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text())
def signs(values): return "/".join("+" if v > 0 else "−" if v < 0 else "0" for v in values)


def build_section(prod, independent, unit_log, section_number):
    comparisons = prod["exploratory_comparisons"]
    labels = [
        ("full_mechanism_minus_rcs_only", "delta_spearman", "full − RCS", "ΔSpearman"),
        ("full_mechanism_minus_rcs_only", "delta_rmse", "full − RCS", "ΔRMSE"),
        ("rcs_only_minus_intrinsic", "delta_spearman", "RCS − intrinsic", "ΔSpearman"),
        ("rcs_only_minus_intrinsic", "delta_rmse", "RCS − intrinsic", "ΔRMSE"),
        ("full_mechanism_minus_outer_train_mean", "delta_rmse", "full − outer-train mean", "ΔRMSE"),
    ]
    lines = [
        f"### 6.{section_number} {MARKER}", "",
        "To close a comparator gap in the existing MAGE nested-development diagnostic without fitting another model, we froze a post-hoc exploratory analysis of the existing 131-construct OOF predictions for all three outer seeds. The four original arms were unchanged. The arm named `rcs_only` contains intrinsic features plus RCS additions and is not a pure external-pretrained-model replacement. The outer-train-mean prediction for each fold was computed only from development labels outside that fold. No mechanism-test construct or new sequence/label was accessed.", "",
        "For the two feature contrasts, paired inference covered both ΔSpearman and ΔRMSE. The outer-train-mean comparison used RMSE only: fold-specific training means are not a globally constant prediction vector, so their OOF Spearman is descriptive and excluded from paired inference. Five tests shared one Holm family. The primary outer seed used 20,000 construct bootstraps and 20,000 paired permutations; the other two seeds contributed point estimates only. The earlier v1 protocol failed its technical gate because it incorrectly required a null Spearman for fold-varying means; no v1 production report was written, and the correction and all failed logs are retained.", "",
        "| Comparison | Metric | Effect | 95% paired CI | Holm p |",
        "|---|---:|---:|---:|---:|",
    ]
    for cid, metric, label, metric_label in labels:
        row = comparisons[cid]
        ci = row[metric + "_ci95"]
        hp = row["holm_p_" + metric.split("delta_", 1)[1]]
        lines.append(f"| {label} | {metric_label} | {row[metric]!r} | [{ci[0]!r}, {ci[1]!r}] | {hp!r} |")
    mean_row = comparisons["full_mechanism_minus_outer_train_mean"]
    full = prod["primary_models"]["full_mechanism"]
    mean = prod["primary_models"]["outer_train_mean"]
    seeds = list(prod["sensitivity"])
    def values(cid, metric):
        return [prod["sensitivity"][s]["comparisons"][cid][metric] for s in seeds]
    lines += [
        "",
        f"The full model and outer-train mean had primary RMSE values of {full['rmse']!r} and {mean['rmse']!r}, respectively. The full−mean ΔRMSE was {mean_row['delta_rmse']!r}, with raw permutation p={mean_row['permutation_p_rmse']!r} and Holm p={mean_row['holm_p_rmse']!r}; its three-seed ΔRMSE signs were {signs(values('full_mechanism_minus_outer_train_mean', 'delta_rmse'))}. This establishes an improvement over the fold-specific training-mean baseline on already-used development predictions, not a mechanism increment or independent confirmation.", "",
        f"Across seeds {', '.join(seeds)}, full−RCS ΔSpearman signs were {signs(values('full_mechanism_minus_rcs_only', 'delta_spearman'))} and ΔRMSE signs were {signs(values('full_mechanism_minus_rcs_only', 'delta_rmse'))}; RCS−intrinsic ΔSpearman signs were {signs(values('rcs_only_minus_intrinsic', 'delta_spearman'))} and ΔRMSE signs were {signs(values('rcs_only_minus_intrinsic', 'delta_rmse'))}. All four feature-comparison Holm p values were 1.0 and every confidence interval crossed zero; the sensitivity directions were not stable. A separately fitted constant-speed arm, a mature external-model replacement, functional-untouched evaluation, transport analysis, and generator authorization remain open.", "",
        f"Independent recomputation passed **{independent['check_counts']['passed']}/{independent['check_counts']['total']} checks** with maximum absolute tolerance 1e-12, and the unit suite passed **9/9 tests** (`{Path(unit_log).name}`). The audit performed zero new fits and zero new scorer calls; its 120,000 primary resample replicates took {prod['cost']['wall_seconds']!r} s. It remains development-only and post-hoc: `DEV_NO_GO_TEST_UNTOUCHED`, RK-G1=false, and the non-submittable working-manuscript status are unchanged.", "",
    ]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--expected-base-sha", required=True)
    ap.add_argument("--base-version", required=True)
    ap.add_argument("--new-version", required=True)
    ap.add_argument("--section-number", default=None)
    a = ap.parse_args()
    root = Path(a.root)
    if not re.fullmatch(r"[0-9a-f]{64}", a.expected_base_sha): raise SystemExit("invalid base SHA")
    if not re.fullmatch(r"v[0-9]+", a.base_version) or not re.fullmatch(r"v[0-9]+", a.new_version): raise SystemExit("versions must be vN")
    paper = root / "paper/CodonFlow_preprint_A8.md"
    audit = root / "audits/20261120/RK03"
    prod_path = audit / "mage_oof_comparator_closure_v2.json"
    ind_path = audit / "mage_oof_comparator_closure_independent_v2.json"
    correction_path = audit / "mage_oof_comparator_closure_correction_v1.json"
    protocol_path = root / "configs/a8_rk03_mage_oof_comparator_closure_protocol_v2.json"
    unit_path = audit / "mage_oof_comparator_closure_unit_tests_v4_python3.console.log"
    base = paper.read_text()
    if sha(paper) != a.expected_base_sha: raise SystemExit("manuscript base SHA mismatch")
    if MARKER in base: raise SystemExit("MAGE comparator section already exists")
    anchor_marker = "\n\nA7 is retained as the prior manuscript snapshot."
    if base.count("\n## 7. Discussion") != 1 or base.count(anchor_marker) != 1: raise SystemExit("unexpected manuscript structure")
    prod, ind, correction = load(prod_path), load(ind_path), load(correction_path)
    if not prod.get("overall_pass") or not ind.get("overall_pass"): raise SystemExit("science reports do not pass")
    if not all(c.get("pass") is True for c in prod["technical_checks"] + ind["checks"]): raise SystemExit("science check failure")
    if ind["production_report_sha256"] != sha(prod_path): raise SystemExit("independent report does not bind production")
    if prod["protocol_sha256"] != sha(protocol_path): raise SystemExit("protocol hash mismatch")
    if prod["scientific_gate"] != "UNCHANGED_DEV_NO_GO_TEST_UNTOUCHED" or prod["scientific_gate_pass"] or prod["test_authorized"]: raise SystemExit("scientific boundary changed")
    if prod["new_model_fits"] != 0 or prod["cost"]["new_scorer_calls"] != 0: raise SystemExit("unexpected fits or scorer calls")
    if correction["protocol_v2"]["production_report_sha256"] != sha(prod_path) or correction["protocol_v2"]["independent_report_sha256"] != sha(ind_path): raise SystemExit("correction does not bind final reports")
    if correction["protocol_v2"]["unit_test_log_sha256"] != sha(unit_path): raise SystemExit("unit-log hash mismatch")
    unit_text = unit_path.read_text()
    if "Ran 9 tests" not in unit_text or "OK" not in unit_text: raise SystemExit("unit tests do not pass")
    numbers = [int(x) for x in re.findall(r"^### 6\.(\d+) ", base, re.M)]
    section_number = a.section_number or str(max(numbers) + 1)
    if not re.fullmatch(r"[0-9]+", section_number) or f"### 6.{section_number} " in base: raise SystemExit("invalid section number")
    section = build_section(prod, ind, unit_path, section_number)
    evidence = [
        ("RK03 MAGE OOF comparator protocol v2", protocol_path),
        ("RK03 MAGE OOF comparator production", prod_path),
        ("RK03 MAGE OOF comparator independent verification", ind_path),
        ("RK03 MAGE OOF comparator correction record", correction_path),
        ("RK03 MAGE OOF comparator 9-test log", unit_path),
    ]
    anchor_rows = [f"| {label} | `{sha(path)}` |" for label, path in evidence]
    anchors = "\n" + "\n".join(anchor_rows)
    updated = base.replace("\n## 7. Discussion", "\n" + section + "## 7. Discussion", 1)
    updated = updated.replace(anchor_marker, anchors + anchor_marker, 1)
    if updated.count(MARKER) != 1: raise SystemExit("section insertion count mismatch")
    restored = updated.replace(section, "", 1).replace(anchors, "", 1)
    if restored != base: raise SystemExit("internal exact-restoration check failed")
    snapshot = root / f"paper/snapshots/rk03_mage_oof_comparator_{a.new_version}"
    if snapshot.exists(): raise SystemExit("snapshot directory already exists")
    snapshot.mkdir(parents=True)
    shutil.copy2(paper, snapshot / f"CodonFlow_preprint_A8_{a.base_version}.md")
    for _, path in evidence: shutil.copy2(path, snapshot / Path(path).name)
    a7 = root / "paper/CodonFlow_preprint_A7.md"
    update = {
        "schema": "a8-rk03-mage-oof-comparator-paper-update-v1",
        "base_version": a.base_version, "new_version": a.new_version,
        "base_sha256": a.expected_base_sha, "new_sha256": hashlib.sha256(updated.encode()).hexdigest(),
        "section_heading": f"### 6.{section_number} {MARKER}",
        "section_number": section_number, "section_sha256": hashlib.sha256(section.encode()).hexdigest(),
        "section_markdown": section, "anchor_markdown": anchors,
        "snapshot_directory": str(snapshot),
        "base_snapshot": str(snapshot / f"CodonFlow_preprint_A8_{a.base_version}.md"),
        "evidence": {label: {"path": str(path), "sha256": sha(path)} for label, path in evidence},
        "production_sha256": sha(prod_path), "independent_sha256": sha(ind_path),
        "correction_sha256": sha(correction_path), "protocol_sha256": sha(protocol_path), "unit_test_log_sha256": sha(unit_path),
        "a7_sha256": sha(a7) if a7.exists() else None,
        "scientific_gate": prod["scientific_gate"], "manuscript_submittable": False,
    }
    record = root / "paper/a8_rk03_mage_oof_comparator_paper_update.json"
    if record.exists(): raise SystemExit("paper update record already exists")
    paper.write_text(updated)
    record.write_text(json.dumps(update, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"new_version": a.new_version, "new_sha256": update["new_sha256"], "section": update["section_heading"]}))


if __name__ == "__main__": main()
