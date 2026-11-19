#!/usr/bin/env python3
"""Append the verified MAGE nested-development result to A8 as v26."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

OLD_PAPER_SHA = "f399fceead66b231b998e073fa02aab0d4bd830aa7a6d4dffd0bb2bec836c15b"
A7_SHA = "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def ci(values):
    return f"[{values[0]:.9f}, {values[1]:.9f}]"


def build_section(final):
    models = final["primary_models"]
    comp = final["primary_comparisons"]
    a = comp["full_mechanism_minus_intrinsic"]
    b = comp["full_mechanism_minus_local_mfe"]
    sens = final["sensitivity_comparisons"]
    rows = []
    for name in ["intrinsic", "local_mfe", "rcs_only", "full_mechanism"]:
        rows.append(f"| {name} | {models[name]['rmse']:.9f} | {models[name]['spearman']:.9f} |")
    comparison_rows = []
    for label, key, values in [
        ("intrinsic", "Spearman", a), ("intrinsic", "RMSE", a),
        ("local-MFE", "Spearman", b), ("local-MFE", "RMSE", b),
    ]:
        if key == "Spearman":
            comparison_rows.append(f"| full minus {label} | delta Spearman | {values['delta_spearman']:.9f} | {ci(values['delta_spearman_ci95'])} | {values['holm_p_spearman']:.6f} |")
        else:
            comparison_rows.append(f"| full minus {label} | delta RMSE | {values['delta_rmse']:.9f} | {ci(values['delta_rmse_ci95'])} | {values['holm_p_rmse']:.6f} |")
    sensitivity_rows = []
    for seed in ["40261120", "40261121"]:
        for reference in ["intrinsic", "local_mfe"]:
            values = sens[seed][f"full_mechanism_minus_{reference}"]
            sensitivity_rows.append(f"| {seed} | full minus {reference} | {values['delta_spearman']:.9f} | {values['delta_rmse']:.9f} |")
    return f"""### 6.22 MAGE nested development CV: mechanism increments were small and unstable

We asked whether the original single-split MAGE development NO-GO was sensitive to the particular 33-construct development assignment. The new diagnostic used only the 131 constructs already assigned to train or development in v1 (98 train and 33 development). The 33 test constructs were excluded before constructing any development record table, fold, feature matrix, prediction or metric. Thus v1 remains **DEV_NO_GO_TEST_UNTOUCHED**, and the present analysis is a development-only diagnostic rather than an independent confirmation.

The four original feature sets and alpha grid were unchanged. Five-fold outer cross-validation produced one out-of-fold prediction per construct; four-fold inner cross-validation selected ridge alpha separately within each outer-training partition and feature set. All scaling and categorical encoding were fitted within the corresponding training partition. The primary outer seed was 40261119, with seeds 40261120 and 40261121 used only for sensitivity. Primary inference used 20,000 construct bootstraps, 20,000 paired sign-flip permutations and Holm correction across four tests (two references and two metrics).

| Feature set | Development OOF RMSE | Development OOF Spearman |
|---|---:|---:|
{chr(10).join(rows)}

| Contrast | Metric | Observed | Paired-bootstrap 95% CI | Holm p |
|---|---|---:|---:|---:|
{chr(10).join(comparison_rows)}

The full-mechanism model did not improve RMSE relative to intrinsic features: the observed difference was +0.000094928, and its interval crossed zero. Its small RMSE decrease relative to local-MFE was also uncertain, with a 95% CI of [-0.000999395, 0.000600285]. Both Spearman point differences were positive, but both intervals crossed zero and all four Holm-adjusted p values were 1.0. No primary comparison met the frozen direction and multiplicity requirements.

| Sensitivity seed | Contrast | Delta Spearman | Delta RMSE |
|---:|---|---:|---:|
{chr(10).join(sensitivity_rows)}

The sensitivity analyses did not resolve the result in favor of the mechanism model. In particular, full-minus-local-MFE Spearman was negative in both sensitivity repeats, and the RMSE direction changed across references and repeats. The prespecified sensitivity sign-consistency requirement therefore failed in addition to the primary inferential gate. These results do not show that RNA structure is universally uninformative; they show that the current full-mechanism feature set did not yield a stable increment over intrinsic or local-MFE baselines in this fixed-infA development design. RCS remains a published supervised structure score, not an unsupervised physical ground truth.

Independent raw-source verification reconstructed all 131 development records, all nested folds and alpha selections, all OOF predictions, the primary intervals and permutations, and both sensitivity repeats. It passed **96/96 checks**, with zero maximum discrepancy for predictions, metrics, inference and inner RMSE. Finalization passed **30/30 checks**. No test prediction, test metric, minimal-medium transport, N-terminal transport or generator authorization was generated. The original v1 NO-GO and all previous negative results remain unchanged; RK-G1 remains open and the manuscript remains non-submittable.
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", required=True)
    parser.add_argument("--a7", required=True)
    parser.add_argument("--sync-audit", required=True)
    parser.add_argument("--production", required=True)
    parser.add_argument("--independent", required=True)
    parser.add_argument("--finalization", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--unit-test-log", required=True)
    parser.add_argument("--update-record", required=True)
    args = parser.parse_args()
    paper_path = Path(args.paper)
    if sha256(paper_path) != OLD_PAPER_SHA:
        raise AssertionError("A8 is not the frozen v25 input")
    if sha256(args.a7) != A7_SHA:
        raise AssertionError("A7 hash mismatch")
    production = json.loads(Path(args.production).read_text())
    independent = json.loads(Path(args.independent).read_text())
    final = json.loads(Path(args.finalization).read_text())
    if production["status"] != "DEV_NO_GO_TEST_UNTOUCHED" or independent["status"] != "PASS" or final["status"] != "PASS":
        raise AssertionError("scientific evidence is not a verified NO-GO")
    if independent["checks_passed"] != 96 or final["checks_passed"] != 30:
        raise AssertionError("unexpected verification counts")
    section = build_section(final)
    old = paper_path.read_text()
    if "### 6.22 MAGE nested development CV" in old:
        raise AssertionError("section already exists")
    marker = "## 7. Discussion"
    if old.count(marker) != 1:
        raise AssertionError("Discussion marker missing")
    updated = old.replace(marker, section + "\n" + marker, 1)
    anchors = (
        f"| RK03 MAGE nested-development frozen protocol v2 | `{sha256(args.protocol)}` |\n"
        f"| RK03 MAGE nested-development production | `{sha256(args.production)}` |\n"
        f"| RK03 MAGE nested-development independent verification | `{sha256(args.independent)}` |\n"
        f"| RK03 MAGE nested-development finalization | `{sha256(args.finalization)}` |\n"
        f"| RK03 MAGE nested-development unit tests | `{sha256(args.unit_test_log)}` |\n\n"
    )
    anchor_marker = "A7 is retained as the prior manuscript snapshot."
    if updated.count(anchor_marker) != 1:
        raise AssertionError("evidence anchor insertion point missing")
    updated = updated.replace(anchor_marker, anchors + anchor_marker, 1)
    snapshot_dir = paper_path.parent / "snapshots" / "rk03_mage_development_nested_cv_v26"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paper = snapshot_dir / "CodonFlow_preprint_A8_v25.md"
    snapshot_audit = snapshot_dir / "a8_rk_paper_sync_audit_v25.json"
    snapshot_a7 = snapshot_dir / "CodonFlow_preprint_A7.md"
    snapshot_paper.write_text(old)
    snapshot_audit.write_text(Path(args.sync_audit).read_text())
    snapshot_a7.write_text(Path(args.a7).read_text())
    paper_path.write_text(updated)
    sync = json.loads(Path(args.sync_audit).read_text())
    sync["base_v25_paper_sha256"] = OLD_PAPER_SHA
    sync["base_v25_audit_sha256"] = sha256(args.sync_audit)
    sync["generated_sections"] = sync.get("generated_sections", []) + ["6.22 MAGE nested development CV", "8.1 RK03 MAGE nested-development evidence anchors"]
    sync["last_increment"] = {
        "section": "6.22 MAGE nested development CV: mechanism increments were small and unstable",
        "protocol_sha256": sha256(args.protocol),
        "production_sha256": sha256(args.production),
        "independent_sha256": sha256(args.independent),
        "finalization_sha256": sha256(args.finalization),
        "paper_sha256": sha256(paper_path),
        "scientific_scope": "fixed-infA synonymous development nested-CV NO-GO; test untouched; no RK-G1, generator or SOTA claim",
        "submittable": False,
    }
    sync["output_sha256"] = sha256(paper_path)
    sync["pre_rk03_mage_development_snapshot"] = {
        "paper": str(snapshot_paper), "paper_sha256": sha256(snapshot_paper),
        "audit": str(snapshot_audit), "audit_sha256": sha256(snapshot_audit),
        "a7": str(snapshot_a7), "a7_sha256": sha256(snapshot_a7),
    }
    sync["rk03_mage_development_nested_cv"] = {
        "status": "DEV_NO_GO_TEST_UNTOUCHED", "development_n": 131, "test_n_untouched": 33,
        "independent_checks": "96/96", "finalization_checks": "30/30", "max_numeric_delta": 0.0,
        "rk_g1_pass": False, "generator_training_authorized": False, "sota_claim": False,
    }
    dump(args.sync_audit, sync)
    record = {
        "schema": "a8-rk03-mage-development-nested-cv-paper-update-v26",
        "old_paper_sha256": OLD_PAPER_SHA,
        "new_paper_sha256": sha256(paper_path),
        "old_sync_audit_sha256": sha256(snapshot_audit),
        "new_sync_audit_sha256": sha256(args.sync_audit),
        "a7_sha256": A7_SHA,
        "section": section,
        "evidence_anchors": anchors,
        "snapshot_paper": str(snapshot_paper),
        "snapshot_audit": str(snapshot_audit),
        "snapshot_a7": str(snapshot_a7),
        "source_hashes": {"protocol": sha256(args.protocol), "production": sha256(args.production), "independent": sha256(args.independent), "finalization": sha256(args.finalization), "unit_tests": sha256(args.unit_test_log)},
        "submittable": False,
    }
    dump(args.update_record, record)
    print(json.dumps({"old_paper_sha256": OLD_PAPER_SHA, "new_paper_sha256": record["new_paper_sha256"], "section": "6.22", "submittable": False}, indent=2))


if __name__ == "__main__":
    main()
