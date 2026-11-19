#!/usr/bin/env python3
"""Independently bind the RiboMIMO study-OOD slide candidate to frozen evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

NS = "https://www.larkoffice.com/sml/2.0"
OUTCOME = "RIBOMIMO_STUDY_OOD_NO_UNIFORM_SIGNIFICANT_ADVANTAGE_OVER_RIDGE"
COMMIT = "ee580a7f9bbc8104b37341b7749403338e9e6257"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def q(name: str) -> str:
    return "{%s}%s" % (NS, name)


def paragraphs(root):
    return ["".join(p.itertext()).strip() for p in root.iter(q("p"))]


def signed(value: float, digits: int = 6) -> str:
    return ("+" if value >= 0 else "−") + f"{abs(value):.{digits}f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--paper-verification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks = []

    def check(name, condition, evidence=None):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    raw = args.candidate.read_text()
    root = ET.fromstring(raw)
    production = load(args.production)
    independent = load(args.independent)
    final = load(args.finalization)
    paper = load(args.paper_verification)
    text = "\n".join(paragraphs(root))
    check("finalization_30_of_30", final["status"] == "PASS_RK05_RIBOMIMO_STUDY_OOD" and final["n_passed"] == final["n_checks"] == 30)
    check("independent_203_of_203", independent["status"] == "PASS_RK05_RIBOMIMO_STUDY_OOD_INDEPENDENT" and independent["n_passed"] == independent["n_checks"] == 203)
    check("paper_44_and_20", paper["status"] == "PASS_RK05_RIBOMIMO_STUDY_OOD_PAPER" and paper["n_passed"] == paper["n_checks"] == 44 and paper["candidate_facts_passed"] == paper["candidate_fact_count"] == 20 and all(row["pass"] for row in paper["candidate_facts"]))
    check("scientific_outcome", final["scientific_outcome"] == OUTCOME, OUTCOME)
    check("primary_seed", final["primary_seed"] == 1234 and "primary seed 1234" in text)
    check("sensitivity_seeds", [row["seed"] for row in final["seed_sensitivity"] if row["seed"] != 1234] == [2345, 3456] and "sensitivity 2345/3456" in text)
    check("direction_and_sizes", production["studies"]["source"] == "Mohammad16" and production["studies"]["target"] == "Subtelny14" and production["runs"][0]["source_train_records"] == 1062 and production["runs"][0]["source_validation_records"] == 117 and production["runs"][0]["target_records"] == 3921 and "source 1,062/117" in text and "target 3,921" in text)
    check("cds_disjoint", all(run["exact_cds_overlap_source_target"] == 0 for run in production["runs"]) and "exact CDS overlap = 0" in text)
    check("resampling_and_holm", all(row["bootstrap_requested"] == row["bootstrap_valid"] == 2000 for row in final["primary_endpoints"]) and len(final["primary_endpoints"]) == 2 and "2,000 bootstrap + 2,000 sign flips" in text and "Holm across 2" in text)
    check("frozen_decision_badge", "203/203 + 30/30 · VERIFIED" in text and "FROZEN PRIMARY READOUT" in text)
    check("no_element_ids_in_candidate", re.search(r'\bid="', raw) is None)
    check("native_table", len(root.findall(".//" + q("table"))) == 1 and len(root.findall(".//" + q("tr"))) == 6)
    check("candidate_geometry", all(0 <= int(el.attrib.get("topLeftX", 0)) and 0 <= int(el.attrib.get("topLeftY", 0)) and int(el.attrib.get("topLeftX", 0)) + int(el.attrib["width"]) <= 960 and int(el.attrib.get("topLeftY", 0)) + int(el.attrib["height"]) <= 540 for el in list(root.findall(".//" + q("shape"))) + root.findall(".//" + q("table"))))
    check("no_tiny_visible_type", all(int(el.attrib.get("fontSize", "12")) >= 8 for el in root.find(q("data")).iter(q("content"))))

    endpoints = {row["metric"]: row for row in final["primary_endpoints"]}
    mse = endpoints["transcript_balanced_mse"]
    cor = endpoints["mean_transcript_pearson"]
    check("primary_mse_effect", abs(mse["point_delta_ribomimo_minus_ridge"] - 1.179641679101714) < 1e-12 and "delta +1.179642" in text and "[+1.162687, +1.196288]" in text and "0.0009995" in text, mse)
    check("primary_correlation_effect", abs(cor["point_delta_ribomimo_minus_ridge"] + 0.03850771646224459) < 1e-12 and "delta −0.038508" in text and "[−0.041406, −0.035536]" in text, cor)
    check("direction_favors_ridge", mse["direction"] == "negative_favors_ribomimo" and mse["point_delta_ribomimo_minus_ridge"] > 0 and cor["direction"] == "positive_favors_ribomimo" and cor["point_delta_ribomimo_minus_ridge"] < 0 and text.count("favors ridge") == 2 and "RIDGE 2/2" in text)
    check("notes_full_precision_mse", str(mse["point_delta_ribomimo_minus_ridge"]) in text and str(mse["ci95_low"]) in text and str(mse["ci95_high"]) in text)
    check("notes_full_precision_correlation", str(cor["point_delta_ribomimo_minus_ridge"]) in text and str(cor["ci95_low"]) in text and str(cor["ci95_high"]) in text)
    check("notes_holm_precision", str(mse["holm_pvalue"]) in text and str(cor["holm_pvalue"]) in text)

    runs = {int(run["seed"]): run for run in production["runs"]}
    for seed, best, last in [(1234, 10, 15), (2345, 10, 15), (3456, 13, 18)]:
        run = runs[seed]
        ribo = run["target_metrics"]["ribomimo"]
        ridge = run["target_metrics"]["ridge"]
        const = run["target_metrics"]["constant"]
        expected = [f"Seed {seed}", f"{ribo['transcript_balanced_mse']:.6f}", f"{ridge['transcript_balanced_mse']:.6f}", f"constant {const['transcript_balanced_mse']:.6f}", f"{best}/{last}"]
        check(f"seed_{seed}_row", all(item in text for item in expected) and run["best_epoch"] == best and run["epochs_completed"] == last and run["ridge_selected_alpha"] == 100, expected)
    primary = runs[1234]
    check("primary_kpis", f"{primary['target_metrics']['ribomimo']['transcript_balanced_mse']:.6f}" in text and f"{primary['target_metrics']['ridge']['transcript_balanced_mse']:.6f}" in text and f"{primary['target_metrics']['constant']['transcript_balanced_mse']:.6f}" in text and signed(primary["target_metrics"]["ribomimo"]["mean_transcript_pearson"]) in text and signed(primary["target_metrics"]["ridge"]["mean_transcript_pearson"]) in text)
    r_ribo = [run["target_metrics"]["ribomimo"]["mean_transcript_pearson"] for run in runs.values()]
    r_ridge = [run["target_metrics"]["ridge"]["mean_transcript_pearson"] for run in runs.values()]
    check("seed_correlation_ranges", f"RiboMIMO r range {signed(min(r_ribo))}…{signed(max(r_ribo))}" in text and f"ridge r range {signed(min(r_ridge))}…{signed(max(r_ridge))}" in text)
    check("constant_baseline_caution", all(run["target_metrics"]["constant"]["transcript_balanced_mse"] < min(run["target_metrics"]["ribomimo"]["transcript_balanced_mse"], run["target_metrics"]["ridge"]["transcript_balanced_mse"]) for run in runs.values()) and "常数 MSE 更低" in text and "不能解释为强绝对迁移" in text)
    check("official_and_training_boundary", "official 094c693d" in text and "target readout last" in text and "source-only early stop" in text and "alpha = 100 all seeds" in text)
    max_ridge = independent["details"]["max_differences"]["ridge_independent_retrain"]
    check("independent_retrain_badge", len(independent["details"]["seeds"]) == 3 and independent["details"]["max_differences"]["model_independent_retrain"] == 0 and max_ridge <= 1e-6 and "model/checkpoint exact" in text and "ridge max 1.51e−7" in text and "3/3 retrains" in text)
    check("paper_badge", "paper 44/44 + facts 20/20" in text)
    check("commit_binding", COMMIT[:12] in text)
    check("bounded_claims", "occupancy-derived study-OOD" in text and "非全局 untouched" in text and "非物理速度/功能或蛋白 OOD" in text and "RK-G1 未关闭" in text and "不是全局 untouched、物理速度、功能或 homology/protein OOD" in text)
    check("negative_result_retained", "ridge 两项主终点均显著优于 RiboMIMO" in text and "常数 MSE 更低" in text and "不能解释为强绝对迁移" in text)
    check("no_empty_paragraphs", all(paragraphs(root)))
    status = "PASS_RK05_RIBOMIMO_STUDY_OOD_PPT_CANDIDATE" if all(row["pass"] for row in checks) else "FAIL"
    report = {
        "schema_version": "a8-rk05-ribomimo-study-ood-ppt-candidate-v1",
        "status": status,
        "n_checks": len(checks),
        "n_passed": sum(row["pass"] for row in checks),
        "checks": checks,
        "candidate_sha256": sha256(args.candidate),
        "commit": COMMIT,
        "inputs": {name: {"path": str(path), "sha256": sha256(path)} for name, path in {"production": args.production, "independent": args.independent, "finalization": args.finalization, "paper_verification": args.paper_verification}.items()},
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": status, "n_passed": report["n_passed"], "n_checks": len(checks), "output": str(args.output)}))
    if status != "PASS_RK05_RIBOMIMO_STUDY_OOD_PPT_CANDIDATE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
