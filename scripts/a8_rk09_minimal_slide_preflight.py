#!/usr/bin/env python3
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(tag):
    return tag.rsplit("}", 1)[-1]


def main():
    p = argparse.ArgumentParser()
    for name in ["candidate", "production", "independent", "finalization", "paper-verification", "source-response", "report"]:
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    root = ET.parse(args.candidate).getroot()
    text = " ".join("".join(root.itertext()).split())
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    finalization = json.loads(args.finalization.read_text())
    paper = json.loads(args.paper_verification.read_text())
    source = json.loads(args.source_response.read_text())
    checks = []

    def check(name, condition, detail):
        checks.append({"id": name, "pass": bool(condition), "detail": detail})

    check("single_slide", local(root.tag) == "slide", "one complete slide")
    check("candidate_namespace", root.tag.startswith("{https://www.larkoffice.com/sml/2.0}"), "SML 2.0 namespace")
    check("no_fabricated_ids", all("id" not in node.attrib for node in root.iter()), "server assigns all IDs")
    check("source_deck_baseline", source["ok"] and source["data"]["revision_id"] == 48, "live source deck revision 48")
    check("production_gate", production["all_pass"] and production["checks_passed"] == 22, "22/22 production")
    check("independent_gate", independent["all_pass"] and independent["checks_passed"] == 16, "16/16 independent")
    check("finalization_gate", finalization["all_pass"] and finalization["checks_passed"] == 14, "14/14 finalization")
    check("paper_gate", paper["all_pass"] and paper["checks_passed"] == 30 and paper["status"] == "PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE", "30/30 paper verification")
    check("title_scope", "最小 CodonFlow-RK 数学核通过精确小状态核验" in text, "title is a bounded mathematical-kernel claim")
    check("legal_state_count", f"{production['counts']['kernel_valid_states']:,}" in text, "226,981 legal states")
    check("reachable_count", f"{production['counts']['two_step_reachable_states']:,}" in text, "10,981 two-step reachable states")
    check("one_step_count", "181 one-step targets" in text and production["counts"]["one_step_targets"] == 181, "181 one-step targets")
    check("naive_tv", f"{production['metrics']['naive_two_step_total_variation_vs_uniform']:.6f}" in text, "TV rounded to 0.324196")
    check("path_count", f"{production['metrics']['telescope']['path_count']:,} paths" in text, "14,641 paths")
    check("endpoint_count", f"{production['metrics']['telescope']['endpoint_count']:,} ends" in text, "3,721 endpoints")
    errors = [production["metrics"]["telescope"][key] for key in ["max_backward_normalization_error", "max_telescope_error", "max_endpoint_reconstruction_error"]]
    check("error_bound_not_zero_claim", max(errors) < 1e-12 and "errors <1e-12" in text and "max error 0" not in text and "最大误差均为零" not in text, f"maximum path error={max(errors)}; displayed as bounded, not zero")
    check("budget_counts", "103 kept · 78 excluded" in text and production["counts"]["budget_retained"] == 103 and production["counts"]["budget_excluded"] == 78, "frozen budget counts")
    check("event_time", f"MC {production['metrics']['event_time_monte_carlo_mean']:.6f} · mean {production['metrics']['event_time_expected_mean']:.2f}" in text, "Monte Carlo and analytic event means")
    check("verification_badges", all(value in text for value in ["22/22", "16/16", "14/14", "10 unit tests", "paper 30/30"]), "all verification layers visible")
    check("failure_history", "19/22" in text and "15/16" in text and "failures retained" in text, "initial failures retained on slide")
    check("scientific_boundary", all(value in text for value in ["不是训练或功能性能结果", "RK-G1 未改", "生成器未授权", "SOTA 未支持"]), "training, function, generation, gate and SOTA boundaries explicit")
    check("false_flags", not finalization["model_training_executed"] and not finalization["functional_or_generation_performance_evaluated"] and not finalization["rk_g1_gate_modified"] and not finalization["expensive_generation_authorized"], "source report confirms bounded scope")
    notes = [node for node in root.iter() if local(node.tag) == "note"]
    note_paragraphs = [] if not notes else [node for node in notes[0].iter() if local(node.tag) == "p"]
    check("speaker_notes", len(notes) == 1 and 3 <= len(note_paragraphs) <= 5, f"{len(note_paragraphs)} note paragraphs")
    direct_data = next(node for node in root if local(node.tag) == "data")
    in_bounds = True
    for node in direct_data:
        if local(node.tag) in {"shape", "table", "img", "embed"}:
            x, y = float(node.get("topLeftX")), float(node.get("topLeftY"))
            w, h = float(node.get("width")), float(node.get("height"))
            in_bounds &= x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540
    check("canvas_bounds", in_bounds, "all primary elements within 960x540")
    check("font_unified", all(node.get("fontFamily", "思源黑体") == "思源黑体" for node in root.iter() if local(node.tag) == "content"), "Source Han Sans throughout")
    check("no_external_media", not any(local(node.tag) in {"img", "embed"} for node in root.iter()), "native editable elements only")
    check("github_reference", "6a15d042" in text, "verified manuscript commit visible")
    result = {"schema": "a8-rk09-minimal-slide-preflight-v1", "candidate_sha256": sha(args.candidate), "source_revision": source["data"]["revision_id"], "evidence_sha256": {"production": sha(args.production), "independent": sha(args.independent), "finalization": sha(args.finalization), "paper": sha(args.paper_verification)}, "checks": checks, "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "all_pass": all(c["pass"] for c in checks)}
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"all_pass": result["all_pass"], "checks": f"{result['checks_passed']}/{result['checks_total']}", "candidate_sha256": result["candidate_sha256"]}))
    if not result["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
