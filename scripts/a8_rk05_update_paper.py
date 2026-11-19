#!/usr/bin/env python3
"""Append only independently finalized RiboMIMO study-OOD evidence to A8."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

EXPECTED_V24 = "29c85c3721182acea31e22f9a03e4c0be973c4be46c7b0ed8756eea420b070e5"
A7_SHA = "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def f(value: float, digits: int = 6) -> str:
    text = f"{float(value):.{digits}f}"
    return "0." + text.split(".", 1)[1] if text.startswith("-0.") and float(value) == 0 else text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--production", type=Path, required=True)
    ap.add_argument("--independent-retrain", type=Path, required=True)
    ap.add_argument("--verification", type=Path, required=True)
    ap.add_argument("--finalization", type=Path, required=True)
    ap.add_argument("--training-record", type=Path, required=True)
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--unit-tests", type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo.resolve()
    paper = repo / "paper/CodonFlow_preprint_A8.md"
    sync_path = repo / "paper/a8_rk_paper_sync_audit.json"
    original = paper.read_text()
    if sha256(paper) != EXPECTED_V24:
        raise SystemExit("A8 is not the expected v24 input")
    production = json.loads(args.production.read_text())
    independent_retrain = json.loads(args.independent_retrain.read_text())
    verification = json.loads(args.verification.read_text())
    final = json.loads(args.finalization.read_text())
    training = json.loads(args.training_record.read_text())
    if final["status"] != "PASS_RK05_RIBOMIMO_STUDY_OOD" or final["n_checks"] != final["n_passed"]:
        raise SystemExit("Finalization has not passed")
    if verification["status"] != "PASS_RK05_RIBOMIMO_STUDY_OOD_INDEPENDENT" or verification["n_checks"] != verification["n_passed"]:
        raise SystemExit("Independent verification has not passed")
    if training["status"] != "PASS_COMPLETE":
        raise SystemExit("Training record is incomplete")
    if "### 6.21 RiboMIMO cross-study transfer" in original:
        raise SystemExit("Section already exists")

    snapshot = repo / "paper/snapshots/rk05_ribomimo_study_ood_v25"
    snapshot.mkdir(parents=True, exist_ok=True)
    old_paper_snapshot = snapshot / "CodonFlow_preprint_A8_v24.md"
    old_audit_snapshot = snapshot / "a8_rk_paper_sync_audit_v24.json"
    for source, target in ((paper, old_paper_snapshot), (sync_path, old_audit_snapshot)):
        if target.exists():
            if sha256(target) != sha256(source):
                raise SystemExit(f"Snapshot collision: {target}")
        else:
            shutil.copyfile(source, target)
    prior_a7 = Path(json.loads(sync_path.read_text())["pre_rk02_structure_snapshot"]["a7"])
    if not prior_a7.is_absolute():
        prior_a7 = repo / prior_a7
    if sha256(prior_a7) != A7_SHA:
        raise SystemExit("A7 hash mismatch")
    a7_snapshot = snapshot / "CodonFlow_preprint_A7.md"
    if not a7_snapshot.exists():
        shutil.copyfile(prior_a7, a7_snapshot)
    if sha256(a7_snapshot) != A7_SHA:
        raise SystemExit("A7 snapshot mismatch")

    rows = []
    for run in production["runs"]:
        m = run["target_metrics"]
        rows.append(
            f"| {run['seed']} | {f(m['ribomimo']['transcript_balanced_mse'])} | {f(m['ridge']['transcript_balanced_mse'])} "
            f"| {f(m['constant']['transcript_balanced_mse'])} | {f(m['ribomimo']['mean_transcript_pearson'])} | {f(m['ridge']['mean_transcript_pearson'])} |"
        )
    primary_rows = []
    for endpoint in production["primary_comparisons"]:
        label = "delta TB-MSE" if endpoint["metric"] == "transcript_balanced_mse" else "delta mean within-transcript Pearson"
        primary_rows.append(
            f"| {label} | {f(endpoint['point_delta_ribomimo_minus_ridge'], 9)} | "
            f"[{f(endpoint['ci95_low'], 9)}, {f(endpoint['ci95_high'], 9)}] | {f(endpoint['sign_flip_pvalue'], 9)} | {f(endpoint['holm_pvalue'], 9)} |"
        )
    ribo_mse = [r["target_metrics"]["ribomimo"]["transcript_balanced_mse"] for r in production["runs"]]
    ridge_mse = [r["target_metrics"]["ridge"]["transcript_balanced_mse"] for r in production["runs"]]
    constant_mse = [r["target_metrics"]["constant"]["transcript_balanced_mse"] for r in production["runs"]]
    ribo_r = [r["target_metrics"]["ribomimo"]["mean_transcript_pearson"] for r in production["runs"]]
    ridge_r = [r["target_metrics"]["ridge"]["mean_transcript_pearson"] for r in production["runs"]]
    max_diff = verification["details"]["max_differences"]
    section = f"""### 6.21 RiboMIMO cross-study transfer: ridge was stronger on both frozen endpoints

We next tested whether the complete official RiboMIMO recipe transferred from Mohammad16 to Subtelny14 under a protocol frozen before target readout. Official-loader eligibility yielded 1,179 source and 3,921 target transcripts. The source was divided into 1,062 training and 117 validation transcripts by the official NumPy random-split logic; all target transcripts were excluded from fitting, checkpoint selection and ridge-alpha selection. Source-target exact CDS overlap was zero. Subtelny14 had already been used in the RiboKinetic/ridge analysis, so this is not a globally untouched confirmatory test.

The official architecture, normalized ribosome-density target, mask, loss, optimizer and source-validation global-R2 checkpoint rule were retained. Seed 1234 was primary; seeds 2345 and 3456 were sensitivity analyses and were not selected by target performance. The ridge baseline used 64 codon one-hot features, 20 relative-position bins, relative position and log(length)/7. Its alpha was selected only by source-validation transcript-balanced MSE; alpha=100 was selected for every seed. Target predictions were evaluated only after source training and baseline selection.

| Seed | RiboMIMO TB-MSE | Ridge TB-MSE | Constant TB-MSE | RiboMIMO mean within-transcript r | Ridge mean within-transcript r |
|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

Across seeds, RiboMIMO TB-MSE ranged from {f(min(ribo_mse))} to {f(max(ribo_mse))}, compared with {f(min(ridge_mse))} to {f(max(ridge_mse))} for ridge and {f(min(constant_mse))} to {f(max(constant_mse))} for the source-train constant. Mean within-transcript Pearson ranged from {f(min(ribo_r))} to {f(max(ribo_r))} for RiboMIMO and from {f(min(ridge_r))} to {f(max(ridge_r))} for ridge. The ridge advantage over RiboMIMO therefore does not imply strong absolute transfer: the source-train constant also had lower TB-MSE than both learned models for every seed. The constant has undefined within-transcript Pearson and is therefore not a complete ranking baseline.

The two frozen primary contrasts used the primary seed, 2,000 paired-transcript bootstraps, 2,000 paired sign-flip permutations and Holm correction across exactly two hypotheses. Positive delta TB-MSE and negative delta Pearson favor ridge.

| Primary effect: RiboMIMO minus ridge | Observed | Paired-bootstrap 95% CI | Sign-flip p | Holm p |
|---|---:|---:|---:|---:|
{chr(10).join(primary_rows)}

Both intervals excluded zero in the direction favoring ridge, with Holm p={f(production['primary_comparisons'][0]['holm_pvalue'], 9)} for each endpoint. The finalized result is **{final['scientific_outcome']}**; more directly, ridge significantly outperformed RiboMIMO on both prespecified primary endpoints in this Mohammad16-to-Subtelny14 setup. This is a bounded negative transfer result for an occupancy-derived target, not a physical-velocity measurement, universal assessment of RiboMIMO, functional OOD result or SOTA claim.

Independent verification reparsed both raw three-line matrices, recomputed eligibility, normalization, masks, source splits, ridge fitting, target metrics and paired inference, and retrained all three seeds in separate output directories. It passed {verification['n_passed']}/{verification['n_checks']} checks; maximum absolute production-versus-independent differences were {max_diff['model_independent_retrain']:.3g} for model predictions and {max_diff['ridge_independent_retrain']:.3g} for ridge predictions. Finalization passed {final['n_passed']}/{final['n_checks']} checks. The shared-GPU wall times are retained in the training record but are not time-matched cost evidence. This experiment does not close homology/protein OOD, functional OOD, RK-G1, generator authorization or the full baseline program.

"""
    marker = "## 7. Discussion"
    if original.count(marker) != 1:
        raise SystemExit("Discussion marker is not unique")
    updated = original.replace(marker, section + marker)

    artifacts = {
        "RK05 RiboMIMO study-OOD frozen protocol": args.protocol,
        "RK05 RiboMIMO study-OOD unit tests": args.unit_tests,
        "RK05 RiboMIMO study-OOD production": args.production,
        "RK05 RiboMIMO study-OOD independent retrain": args.independent_retrain,
        "RK05 RiboMIMO study-OOD independent verification": args.verification,
        "RK05 RiboMIMO study-OOD finalization": args.finalization,
        "RK05 RiboMIMO study-OOD training record": args.training_record,
    }
    anchor_lines = "".join(f"| {label} | `{sha256(path)}` |\n" for label, path in artifacts.items())
    anchor_marker = "A7 is retained as the prior manuscript snapshot."
    if original.count(anchor_marker) != 1:
        raise SystemExit("Anchor marker is not unique")
    updated = updated.replace(anchor_marker, anchor_lines + "\n" + anchor_marker)
    paper.write_text(updated)

    sync = json.loads(sync_path.read_text())
    old_sync_sha = sha256(sync_path)
    sync["base_v24_audit_sha256"] = old_sync_sha
    sync["base_v24_paper_sha256"] = EXPECTED_V24
    sync["generated_sections"] += [
        "6.21 RiboMIMO cross-study transfer: ridge was stronger on both frozen endpoints",
        "8.1 RK05 RiboMIMO study-OOD evidence anchors",
    ]
    sync["last_increment"] = {
        "section": "6.21 RiboMIMO cross-study transfer: ridge was stronger on both frozen endpoints",
        "protocol_sha256": sha256(args.protocol),
        "production_sha256": sha256(args.production),
        "independent_retrain_sha256": sha256(args.independent_retrain),
        "independent_sha256": sha256(args.verification),
        "finalization_sha256": sha256(args.finalization),
        "training_record_sha256": sha256(args.training_record),
        "paper_sha256": sha256(paper),
        "scientific_scope": "Mohammad16-to-Subtelny14 occupancy-derived study-OOD baseline; ridge significantly better on both frozen primary endpoints; not globally untouched, physical velocity, functional/homology OOD, RK-G1 closure, generator authorization or SOTA",
        "submittable": False,
    }
    sync["manuscript_version"] = "v25"
    sync["output_sha256"] = sha256(paper)
    sync["pre_rk05_ribomimo_study_ood_snapshot"] = {
        "paper": str(old_paper_snapshot), "paper_sha256": sha256(old_paper_snapshot),
        "audit": str(old_audit_snapshot), "audit_sha256": sha256(old_audit_snapshot),
        "a7": str(a7_snapshot), "a7_sha256": sha256(a7_snapshot),
    }
    sync["rk05_ribomimo_study_ood_v25"] = {
        "protocol_sha256": sha256(args.protocol), "production_sha256": sha256(args.production),
        "independent_retrain_sha256": sha256(args.independent_retrain), "independent_sha256": sha256(args.verification),
        "finalization_sha256": sha256(args.finalization), "training_record_sha256": sha256(args.training_record),
        "paper_sha256": sha256(paper), "scientific_outcome": final["scientific_outcome"],
        "ridge_better_on_both_primary_endpoints": True, "globally_untouched": False,
        "physical_velocity": False, "functional_ood": False, "homology_protein_ood": False,
        "rk_g1_changed": False, "generator_training_authorized": False, "sota_claim": False,
    }
    sync["scientific_scope"]["ribomimo_study_ood"] = sync["last_increment"]["scientific_scope"]
    for label, path in artifacts.items():
        key = label.lower().replace(" ", "_").replace("-", "_")
        sync["source_paths"][key] = str(path)
    sync_path.write_text(json.dumps(sync, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    update = {
        "schema_version": "a8-rk05-ribomimo-study-ood-paper-update-v1",
        "status": "PASS_PENDING_INDEPENDENT_PAPER_VERIFY",
        "manuscript_version": "v25", "submittable": False,
        "input_paper_sha256": EXPECTED_V24, "output_paper_sha256": sha256(paper),
        "input_sync_sha256": old_sync_sha, "output_sync_sha256": sha256(sync_path),
        "section": sync["last_increment"]["section"],
        "scientific_outcome": final["scientific_outcome"],
        "anchor_lines": anchor_lines.splitlines(),
        "artifacts": {label: {"path": str(path), "sha256": sha256(path)} for label, path in artifacts.items()},
    }
    update_path = repo / "paper/a8_rk05_ribomimo_study_ood_paper_update.json"
    update_path.write_text(json.dumps(update, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"status": update["status"], "paper_sha256": update["output_paper_sha256"], "sync_sha256": update["output_sync_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
