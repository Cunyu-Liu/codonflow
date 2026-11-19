#!/usr/bin/env python3
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    root_dir = Path(sys.argv[1]).resolve()
    summary_path = root_dir / "sequence_ood_model_summary.json"
    independent_path = root_dir / "sequence_ood_model_independent_verification.json"
    final_path = root_dir / "sequence_ood_model_finalization.json"
    before_path = root_dir / "rk04_model_before_v01.xml"
    candidate_path = root_dir / "rk04_sequence_ood_model_page81_v01.xml"
    output_path = root_dir / "rk04_model_ppt_candidate_verification.json"
    summary = json.loads(summary_path.read_text())
    independent = json.loads(independent_path.read_text())
    final = json.loads(final_path.read_text())
    checks = []

    def check(name, condition, detail):
        checks.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})

    check("independent_pass", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] == 40, independent["status"])
    check("finalization_pass", final["status"] == "PASS" and final["checks_passed"] == final["checks_total"] == 18, final["status"])
    before = ET.parse(before_path).getroot()
    before_ns = before.tag[1:].split("}")[0]
    old_slides = before.findall(f"{{{before_ns}}}slide")
    old_text = "\n".join(p.text or "" for s in old_slides for p in s.iter(f"{{{before_ns}}}p"))
    check("before_has_80_slides", len(old_slides) == 80, len(old_slides))
    check("result_page_not_duplicate", "sequence-OOD：组合代理特征优于 GC-only" not in old_text, "unique new title")

    candidate = ET.parse(candidate_path).getroot()
    ns = candidate.tag[1:].split("}")[0]
    text = "\n".join(p.text or "" for p in candidate.iter(f"{{{ns}}}p"))
    check("new_title", "sequence-OOD：组合代理特征优于 GC-only" in text, "title")
    primary = summary["primary_family"]
    selected = summary["selected"][primary]
    check("primary_identity", primary == "ridge_all" and selected["params"]["alpha"] == 100.0, primary)
    check("primary_dev_cbmse", f"ridge_all · {selected['dev_metrics']['cluster_balanced_mse']:.6f}" in text, selected["dev_metrics"]["cluster_balanced_mse"])
    comparison = summary["primary_comparison"]
    ood = comparison["bootstrap"]["sequence_ood"]["statistics"]
    check("ood_spearman_gain", f"+{comparison['observed']['sequence_ood']['row_spearman_delta']:.6f}" in text and "95% CI [" + ", ".join(f"{x:.6f}" for x in ood["row_spearman_delta"]["ci95"]) + "]" in text, ood["row_spearman_delta"])
    check("ood_cbmse_change", f"{comparison['observed']['sequence_ood']['cluster_balanced_mse_delta']:.6f}" in text and "95% CI [" + ", ".join(f"{x:.6f}" for x in ood["cluster_balanced_mse_delta"]["ci95"]) + "]" in text, ood["cluster_balanced_mse_delta"])
    check("ood_intervals_exclude_zero", ood["row_spearman_delta"]["ci95"][0] > 0 and ood["cluster_balanced_mse_delta"]["ci95"][1] < 0, "both OOD intervals exclude zero")
    test_stats = comparison["bootstrap"]["test"]["statistics"]
    check("test_intervals_cross_zero", test_stats["row_spearman_delta"]["ci95"][0] < 0 < test_stats["row_spearman_delta"]["ci95"][1] and test_stats["cluster_balanced_mse_delta"]["ci95"][0] < 0 < test_stats["cluster_balanced_mse_delta"]["ci95"][1], "both retained-test intervals cross zero")

    expected_rows = {
        "constant": ["null", f"{summary['test_metrics']['constant']['row_r2']:.6f}", "null", f"{summary['sequence_ood_metrics']['constant']['row_r2']:.6f}", f"{summary['sequence_ood_metrics']['constant']['cluster_balanced_mse']:.6f}"],
    }
    for family in ["ridge_gc", "ridge_basic", "ridge_all", "histgb_all"]:
        expected_rows[family] = [
            f"{summary['test_metrics'][family]['row_spearman']:.6f}",
            f"{summary['test_metrics'][family]['row_r2']:.6f}",
            f"{summary['sequence_ood_metrics'][family]['row_spearman']:.6f}",
            f"{summary['sequence_ood_metrics'][family]['row_r2']:.6f}",
            f"{summary['sequence_ood_metrics'][family]['cluster_balanced_mse']:.6f}",
        ]
    for family, values in expected_rows.items():
        check(f"metrics_{family}", all(value in text for value in values), values)
    check("all_families_visible", all(family in text for family in ["constant", "ridge_gc", "ridge_basic", "ridge_all (primary)", "histgb_all"]), "5/5")
    check("no_post_hoc_primary_switch", "HistGB 不后验替换 primary" in text and summary["test_metrics"]["histgb_all"]["row_spearman"] > summary["test_metrics"][primary]["row_spearman"], "HistGB retained-test result retained without switching primary")
    check("scientific_boundary", "OOD R2 仍低" in text and "不支持机制、生成器或 SOTA 声称" in text and summary["sequence_ood_metrics"][primary]["row_r2"] < 0.02, summary["sequence_ood_metrics"][primary]["row_r2"])
    notes = [p.text or "" for p in candidate.findall(f"{{{ns}}}note/{{{ns}}}content/{{{ns}}}p")]
    check("speaker_notes", len(notes) == 4 and all(len(note) > 20 for note in notes), len(notes))

    in_bounds = True
    for element in candidate.iter():
        attrs = element.attrib
        if all(key in attrs for key in ["topLeftX", "topLeftY", "width", "height"]):
            in_bounds &= float(attrs["topLeftX"]) >= 0 and float(attrs["topLeftY"]) >= 0
            in_bounds &= float(attrs["topLeftX"]) + float(attrs["width"]) <= 960
            in_bounds &= float(attrs["topLeftY"]) + float(attrs["height"]) <= 540
    check("elements_in_canvas", in_bounds, "960x540")
    failed = [c for c in checks if c["status"] == "FAIL"]
    report = {
        "protocol_id": "a8_rk04_model_ppt_candidate_verification_v1",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "summary": {"checks": f"{len(checks)-len(failed)}/{len(checks)}", "failed": [c["name"] for c in failed]},
        "evidence": {
            "model_summary": str(summary_path), "model_summary_sha256": sha(summary_path),
            "independent": str(independent_path), "independent_sha256": sha(independent_path),
            "finalization": str(final_path), "finalization_sha256": sha(final_path),
            "before_xml": str(before_path), "before_xml_sha256": sha(before_path),
            "candidate_xml": str(candidate_path), "candidate_xml_sha256": sha(candidate_path),
        },
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({**report["summary"], "status": report["status"]}, ensure_ascii=False))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
