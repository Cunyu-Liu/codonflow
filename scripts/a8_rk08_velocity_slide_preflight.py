#!/usr/bin/env python3
"""Independent evidence-to-slide preflight for the RK08 velocity result page."""
import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"s": "https://www.larkoffice.com/sml/2.0"}
MODEL = "ribokinetic_velocity"
RIDGE = "ridge_codon_position_length"


def load(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixed(value, digits=4, signed=False):
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--deck", required=True)
    parser.add_argument("--deck-response", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--data-audit", required=True)
    parser.add_argument("--retrain", required=True)
    parser.add_argument("--independent", required=True)
    parser.add_argument("--finalization", required=True)
    parser.add_argument("--paper-verification", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    candidate_path = Path(args.candidate)
    raw = candidate_path.read_text()
    root = ET.fromstring(raw)
    visible = " ".join("".join(p.itertext()) for p in root.findall(".//s:data//s:p", NS))
    notes = ["".join(p.itertext()).strip() for p in root.findall(".//s:note//s:p", NS)]
    run = load(args.run)
    data_audit = load(args.data_audit)
    retrain = load(args.retrain)
    independent = load(args.independent)
    finalization = load(args.finalization)
    paper = load(args.paper_verification)
    deck = ET.parse(args.deck).getroot()
    deck_response = load(args.deck_response)
    deck_slides = deck.findall("s:slide", NS)

    comparisons = {row["metric"]: row for row in run["primary_comparisons"]}
    mse = comparisons["transcript_balanced_mse"]
    pearson = comparisons["mean_transcript_pearson"]
    expected_primary = [
        fixed(mse["point_delta_model_minus_ridge"], signed=True),
        fixed(mse["ci95_low"], signed=True), fixed(mse["ci95_high"], signed=True),
        fixed(pearson["point_delta_model_minus_ridge"], signed=True),
        fixed(pearson["ci95_low"], signed=True), fixed(pearson["ci95_high"], signed=True),
    ]
    expected_rows = {}
    for partition in ["dev", "test", "study_ood:Mohammad19-1", "study_ood:Mohammad19-2", "study_ood:Subtelny14"]:
        metrics = run["metrics"][partition]
        expected_rows[partition] = [
            f"{fixed(metrics[MODEL]['transcript_balanced_mse'])} / {fixed(metrics[RIDGE]['transcript_balanced_mse'])}",
            f"{fixed(metrics[MODEL]['mean_transcript_pearson'])} / {fixed(metrics[RIDGE]['mean_transcript_pearson'])}",
        ]
    normalized_visible = visible.replace("-", "−")
    row_checks = {partition: all(value.replace("-", "−") in normalized_visible for value in values) for partition, values in expected_rows.items()}
    geometry_ok = True
    for element in root.findall(".//s:data/*", NS):
        if element.tag.rsplit("}", 1)[-1] in {"shape", "table", "img", "icon", "embed"}:
            x, y = float(element.attrib["topLeftX"]), float(element.attrib["topLeftY"])
            w, h = float(element.attrib["width"]), float(element.attrib["height"])
            geometry_ok = geometry_ok and x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540

    checks = {
        "deck_has_84_preexisting_slides": len(deck_slides) == 84,
        "deck_revision_recorded": deck_response.get("ok") is True and deck_response.get("data", {}).get("revision_id") == 46,
        "candidate_single_slide": root.tag == "{https://www.larkoffice.com/sml/2.0}slide",
        "candidate_geometry_within_canvas": geometry_ok,
        "four_note_sentences": len(notes) == 4 and all(notes),
        "record_count_exact": data_audit["counts"]["retained_records"] == 7788 and "7,788 records" in visible,
        "model_parameters_exact": run["training"]["parameter_count"] == 24933 and "24,933 parameters" in visible,
        "dev_only_epoch_exact": run["selected_epoch"] == 16 and "dev-only epoch 16" in visible,
        "bootstrap_count_exact": all(row["bootstrap_valid"] == 2000 for row in run["primary_comparisons"]) and "2,000 transcript bootstraps" in visible,
        "primary_point_estimates_exact": all(value.replace("-", "−") in normalized_visible for value in expected_primary),
        "all_partition_rows_exact": all(row_checks.values()),
        "independent_26_pass": independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] == 26 and not independent["failures"],
        "finalization_12_pass": finalization["status"] == "PASS" and finalization["checks_passed"] == finalization["checks_total"] == 12 and not finalization["failures"],
        "paper_30_pass": paper["status"] == "PASS" and paper["checks_passed"] == paper["checks_total"] == 30 and not paper["failures"],
        "retrain_checkpoint_identical": run["hashes"]["checkpoint_sha256"] == retrain["hashes"]["checkpoint_sha256"],
        "retrain_predictions_identical": run["hashes"]["predictions_sha256"] == retrain["hashes"]["predictions_sha256"],
        "negative_gate_preserved": run["velocity_mechanism_pass"] is False and run["rk_g1_pass"] is False and "VELOCITY GATE = FALSE" in visible and "RK-G1 未通过" in visible,
        "proxy_boundary_explicit": "仅占据衍生速度代理" in visible and "非物理速度" in visible and "homology OOD" in visible and "功能迁移" in visible,
        "no_overclaim": not re.search(r"VELOCITY GATE = TRUE|RK-G1 = TRUE|SOTA|物理速度实测通过|homology OOD = PASS|homology OOD 已通过|homology OOD 通过验证", visible, re.I),
    }
    failures = [name for name, passed in checks.items() if not passed]
    report = {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
        "candidate_sha256": sha256(candidate_path),
        "deck_sha256": sha256(args.deck),
        "deck_slide_count": len(deck_slides),
        "deck_revision": deck_response.get("data", {}).get("revision_id"),
        "run_sha256": sha256(args.run),
        "data_audit_sha256": sha256(args.data_audit),
        "independent_sha256": sha256(args.independent),
        "finalization_sha256": sha256(args.finalization),
        "paper_verification_sha256": sha256(args.paper_verification),
        "partition_row_checks": row_checks,
        "velocity_mechanism_pass": False,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
