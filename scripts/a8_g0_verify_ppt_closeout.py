#!/usr/bin/env python3
"""Verify live G0 slide append against frozen evidence and the exact pre-write deck."""
from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

D = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm_text(value):
    return " ".join((value or "").split())


def semantic(element):
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        norm_text(element.text),
        tuple(semantic(child) for child in element),
    )


def text_nodes(element):
    ordered = []

    def visit(node):
        if norm_text(node.text):
            ordered.append(norm_text(node.text))
        for child in node:
            visit(child)
            if norm_text(child.tail):
                ordered.append(norm_text(child.tail))

    visit(element)
    return ordered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=str(Path(__file__).resolve().parent))
    args = ap.parse_args()
    D = Path(args.workdir).resolve()
    before_response = json.loads((D / "g0_before_response_v01.json").read_text())
    after_response = json.loads((D / "g0_after_response_v01.json").read_text())
    add_response = json.loads((D / "g0_add_response_v01.json").read_text())
    before = ET.parse(D / "g0_before_v01.xml").getroot()
    after = ET.parse(D / "g0_after_v01.xml").getroot()
    submitted = ET.parse(D / "g0_slide_v01.xml").getroot()
    prod = json.loads((D / "g0_unified_cost_closeout_v2.json").read_text())
    ind = json.loads((D / "g0_unified_cost_closeout_independent_v1.json").read_text())
    final = json.loads((D / "g0_unified_cost_closeout_finalization_v1.json").read_text())
    paper_verification = json.loads((D / "a8_g0_closeout_paper_verification_v30.json").read_text())
    paper = (D / "CodonFlow_preprint_A8_v30.md").read_text()
    ns = before.tag.split("}")[0] + "}"
    old = before.findall(ns + "slide")
    new = after.findall(ns + "slide")
    current = new[-1]
    visible = " ".join(text_nodes(current.find(ns + "data")))
    notes = " ".join(text_nodes(current.find(ns + "note")))
    checks = []

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    check("before_response", before_response["ok"] and before_response["data"]["revision_id"] == 67)
    check("after_response", after_response["ok"] and after_response["data"]["revision_id"] == 68)
    check("add_response", add_response["ok"] and add_response["data"]["slide_id"] == "pZg"
          and add_response["data"]["revision_id"] == 68)
    check("page_count", len(old) == 105 and len(new) == 106)
    check("old_ids_unchanged", [s.get("id") for s in old] == [s.get("id") for s in new[:105]])
    check("new_page_id", current.get("id") == "pZg")
    changed = [i + 1 for i, (a, b) in enumerate(zip(old, new[:105])) if semantic(a) != semantic(b)]
    check("all_105_old_pages_semantically_identical", not changed, changed)
    check("submitted_text_preserved", text_nodes(submitted) == text_nodes(current))
    check("no_undefined_or_external_image", not current.findall(".//" + ns + "undefined")
          and all((img.get("src") or "").startswith("http") is False for img in current.findall(".//" + ns + "img")))
    shapes = current.findall(".//" + ns + "shape")
    check("all_shapes_in_canvas", all(0 <= float(s.get("topLeftX")) and float(s.get("topLeftX")) + float(s.get("width")) <= 960
          and 0 <= float(s.get("topLeftY")) and float(s.get("topLeftY")) + float(s.get("height")) <= 540 for s in shapes))
    check("shape_count_preserved", len(shapes) == len(submitted.findall(".//" + ns + "shape")) == 60)
    check("explicit_font_sizes", all(s.find(ns + "content") is None or s.find(ns + "content").get("fontSize") for s in shapes))
    check("production_hash", sha(D / "g0_unified_cost_closeout_v2.json") ==
          "c0510f528615af6ef505aed83dd1c0ec5d1fa75eb900c46f6a363521c2cdd583")
    check("independent_hash", sha(D / "g0_unified_cost_closeout_independent_v1.json") ==
          "1bf177c3ad170d3bd0385efce488402fd8e2e74611a0dc3590499e47acd93a40")
    check("finalization_hash", sha(D / "g0_unified_cost_closeout_finalization_v1.json") ==
          "9775981553bc830b9ac27aa19bf4eab5106a09901fb3863ba8e6ea8df66e4db2")
    check("paper_verified", paper_verification["overall_pass"] and paper_verification["check_counts"] == {"passed": 127, "total": 127})
    check("source_and_gate_counts", prod["summary"]["source_count"] == 22 and prod["summary"]["row_count"] == 22
          and len(prod["gate_results"]) == 20 and all(x in visible for x in ["22 hashed source reports", "22 cost rows", "20 gate facts"]))
    check("acceptance_counts", prod["technical_passed_checks"] == 179 and ind["passed_checks"] == 357
          and ind["max_numeric_delta"] == 0 and final["passed_checks"] == 6
          and all(x in visible for x in ["179 / 179", "357 / 357", "9 / 9", "6 / 6", "Δ = 0"]))
    check("bounded_gate", prod["g0_status"] == "PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY"
          and prod["g0_status"] in visible)
    check("measured_and_null_counts", prod["summary"]["measured_wall_clock_scopes"] == 13
          and prod["summary"]["explicit_null_wall_clock_scopes"] == 9 and "13 measured scopes · 9 explicit nulls" in visible)

    rows = {r["row_id"]: r for r in prod["cost_matrix"]}
    expected_costs = {
        "lineardesign_unique18": "5,459.87 s",
        "ensembledesign_unique18": "6,001.06 s",
        "cagfn_official_smoke": "47.56 s",
        "id3_official_quick_test": "417.59 s",
        "codontransformer_official_smoke": "6.47 s",
        "ribomimo_study_ood": "949.74 s",
        "rose_released_checkpoint": "112.83 s",
        "ixnos_real_prefix": "10.54 s",
        "veloharmo_official_smoke": "5.95 s",
    }
    for row_id, rendered in expected_costs.items():
        value = rows[row_id]["metrics"]["wall_clock_s"]
        check("cost_" + row_id, f"{value:,.2f} s" == rendered and rendered in visible, rendered)
    check("linear_outputs_and_runs", rows["lineardesign_unique18"]["metrics"]["actual_outputs"] == 131
          and "198 runs · 131 actual-set outputs" in visible and "18 records x 11" in rows["lineardesign_unique18"]["scope"])
    check("ensemble_outputs_and_runs", rows["ensembledesign_unique18"]["metrics"]["actual_outputs"] == 192
          and "198 runs · 192 actual-set outputs" in visible and "18 records x 11" in rows["ensembledesign_unique18"]["scope"])
    check("cagfn_components", f"{rows['cagfn_official_smoke']['metrics']['training_s']:.2f}" == "11.01"
          and f"{rows['cagfn_official_smoke']['metrics']['generation_or_inference_s']:.2f}" == "6.68"
          and "11.01 s train · 6.68 s inference" in visible)
    check("id3_scope", rows["id3_official_quick_test"]["metrics"]["runs"] == 12
          and "1 protein · 2 iterations · 1 seed · 12 runs" in visible)
    check("ct_scope", rows["codontransformer_official_smoke"]["metrics"]["runs"] == 4
          and rows["codontransformer_official_smoke"]["metrics"]["actual_outputs"] == 2
          and "model load + 4 inferences · 2 unique outputs" in visible)
    check("ribomimo_scope", rows["ribomimo_study_ood"]["metrics"]["runs"] == 3
          and "3 independent training seeds" in visible)
    check("negative_transfer_retained", "ridge was stronger on both frozen endpoints" in paper
          and "negative transfer retained" in visible)
    check("rose_components", f"{rows['rose_released_checkpoint']['metrics']['generation_or_inference_s']:.2f}" == "105.96"
          and "2 studies · 105.96 s inference" in visible)
    check("ixnos_scope", "1,000,000-read" in rows["ixnos_real_prefix"]["scope"]
          and "two epochs" in rows["ixnos_real_prefix"]["scope"] and "1M reads · 2 epochs" in visible)
    check("veloharmo_boundary", "no five-species matrix" in rows["veloharmo_official_smoke"]["scope"]
          and "not five-species coverage" in visible)
    check("rnarl_not_generation", rows["rnarl_availability"]["metrics"]["qc_pairs"] == 128289
          and rows["rnarl_availability"]["metrics"]["wall_clock_s"] is None
          and "128,289 clean QC pairs · not official generations" in visible and "cost null" in visible)
    rk06 = [rows[k] for k in ["rk06_dense_uniform", "rk06_dense_hill_climbing", "rk06_dense_mh_annealing", "rk06_dense_areuredi_style"]]
    check("rk06_calls", all(r["metrics"]["unique_scorer_calls"] == 27000 for r in rk06)
          and "4 × 27,000 unique scorer calls" in visible)
    expected_range = f"{min(r['metrics']['wall_clock_s'] for r in rk06):,.0f}–{max(r['metrics']['wall_clock_s'] for r in rk06):,.0f} s per method"
    check("rk06_wall_range", expected_range == "20,939–21,078 s per method" and expected_range in visible, expected_range)
    check("null_and_cost_boundaries", all(x in visible for x in ["null ≠ 0", "no global cost sum", "time-matched ranking"])
          and prod["summary"]["global_wall_clock_sum"] is None)
    check("research_boundaries", all(x in visible for x in ["Bounded pass only", "external dense / time-matched / SOTA incomplete",
          "RK-G1 = false", "generator unauthorized"]) and not prod["boundaries"]["rk_g1_passed"]
          and not prod["boundaries"]["generator_training_authorized"])
    check("notes_hashes", all(x in notes for x in [sha(D / "g0_unified_cost_closeout_v2.json"),
          sha(D / "g0_unified_cost_closeout_independent_v1.json"), sha(D / "g0_unified_cost_closeout_finalization_v1.json")]))
    check("notes_feasibility_and_open_gates", all(x in notes for x in ["FEASIBILITY_CLOSED_NOT_FULL_REMAP",
          "functional-untouched", "wet-lab validation remain open", "RK-G1=false", "generator training is unauthorized"]))
    check("paper_anchor", "manuscript v30 §6.26" in visible and "e8bf9d37" in visible
          and "### 6.26 Bounded RK-G0 readiness and unified cost ledger" in paper)
    report = {
        "schema": "a8-g0-ppt-verification-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "overall_pass": all(c["pass"] for c in checks),
        "presentation": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "slide_id": current.get("id"),
        "slide_number": len(new),
        "before_revision": before_response["data"]["revision_id"],
        "after_revision": after_response["data"]["revision_id"],
        "old_pages_semantically_unchanged": not changed,
        "old_page_differences": changed,
        "check_counts": {"passed": sum(c["pass"] for c in checks), "total": len(checks)},
        "checks": checks,
        "hashes": {name: sha(D / name) for name in ["g0_before_v01.xml", "g0_after_v01.xml", "g0_slide_v01.xml",
                   "g0_unified_cost_closeout_v2.json", "g0_unified_cost_closeout_independent_v1.json",
                   "g0_unified_cost_closeout_finalization_v1.json", "CodonFlow_preprint_A8_v30.md"]},
    }
    output = D / "g0_ppt_verification_v01.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "check_counts": report["check_counts"],
                      "slide_id": report["slide_id"], "slide_number": report["slide_number"],
                      "old_pages_semantically_unchanged": report["old_pages_semantically_unchanged"]}, indent=2))
    if not report["overall_pass"]:
        for c in checks:
            if not c["pass"]:
                print("FAIL", c)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
