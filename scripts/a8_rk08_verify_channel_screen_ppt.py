#!/usr/bin/env python3
"""Verify the RK08 result-slide candidate and its appended online rendering."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def text(element) -> str:
    return "".join(element.itertext())


def signature(element):
    # Inter-element indentation is not presentation content. In particular,
    # appending a slide changes the former last slide's closing tail from one
    # newline to a newline plus two spaces. Preserve every non-whitespace tail.
    tail = element.tail if element.tail and element.tail.strip() else None
    return (element.tag, tuple(sorted(element.attrib.items())), element.text, tail, tuple(signature(child) for child in element))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["candidate", "final"], required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--candidate", default="rk08_slide_v01.xml")
    ap.add_argument("--output", required=True)
    ap.add_argument("--visual-reviewed", action="store_true")
    args = ap.parse_args()
    work = Path(args.work_dir)
    candidate_path = work / args.candidate
    selection = load(work / "channel_screen_selection_v1.json")
    evaluation = load(work / "channel_screen_evaluation_v1.json")
    independent = load(work / "channel_screen_independent_v1.json")
    final = load(work / "channel_screen_finalization_v1.json")
    root = ET.parse(candidate_path).getroot()
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    data = root.find(ns + "data")
    note = root.find(ns + "note")
    visible = text(data)
    notes = text(note)
    checks = []

    def ck(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    ck("single_slide_root", root.tag == ns + "slide")
    ck("namespace_read_from_root", ns == "{https://www.larkoffice.com/sml/2.0}")
    ck("candidate_has_no_self_assigned_id", root.get("id") is None)
    ck("one_data_and_note", data is not None and note is not None)
    ck("no_external_media", "http://" not in candidate_path.read_text() and "https://" not in candidate_path.read_text().replace("https://www.larkoffice.com/sml/2.0", ""))
    ck("no_undefined", root.find(".//" + ns + "undefined") is None)
    ck("no_embed", root.find(".//" + ns + "embed") is None)
    ck("no_emoji", not re.search(r"[\U0001F300-\U0001FAFF]", visible + notes))
    for index, element in enumerate(root.findall(".//*[@topLeftX]")):
        x, y = float(element.get("topLeftX")), float(element.get("topLeftY"))
        w, h = float(element.get("width")), float(element.get("height"))
        ck(f"canvas_bounds_{index}", 0 <= x <= 960 and 0 <= y <= 540 and x + w <= 960 and y + h <= 540, [x, y, w, h])
    ck("footer_above_canvas", "A8-RK · 107" in visible)
    ck("title_negative_boundary", "full-proxy increment is not established" in visible)
    ck("ten_arm_subtitle", "10 matched arms" in visible and "4,997 parameters/arm" in visible)
    ck("train_dev_only", "train/dev-only selection" in visible and selection["test_or_ood_used_for_selection"] is False)
    ck("selected_all", selection["selected_arm"] == "all" and "all" in visible)
    ck("selected_dev_value", selection["selected_dev_cluster_balanced_mse"] == 3.761769367012553 and "3.761769" in visible and repr(selection["selected_dev_cluster_balanced_mse"]) in notes)
    ck("dev_partition", selection["screen_rows"] == {"train": 4019, "dev": 503} and "503 rows and 447 clusters" in notes)
    ck("ten_development_rows", len(selection["development_table"]) == 10 and all(row["parameters"] == 4997 for row in selection["development_table"]))
    ck("sequence_ood_counts", evaluation["metrics"]["sequence_ood"]["ribokinetic_selected"]["n_rows"] == 1336 and evaluation["metrics"]["sequence_ood"]["ribokinetic_selected"]["n_clusters"] == 1110 and "1,336" in visible and "1,110" in visible)
    ck("bootstrap", evaluation["bootstrap"] == {"method": "operational_protein_cluster_resampling", "replicates": 2000, "seed": 20261120} and "2,000 cluster bootstraps" in visible and "2,000 cluster bootstrap replicates" in notes)
    ck("independent_320", independent["check_counts"] == {"passed": 320, "total": 320} and "320 / 320" in visible and "320/320" in notes)
    ck("independent_delta", independent["max_numeric_delta"] == 1.9095836023552692e-14 and "1.91e-14" in visible and repr(independent["max_numeric_delta"]) in notes)
    ck("finalization_42", final["check_counts"] == {"passed": 42, "total": 42} and final["status"] == "PASS_CHANNEL_SCREEN_CLOSEOUT" and "42 / 42" in visible and "42/42" in notes)
    ck("targeted_8", "TARGETED 8/8" in visible and "8/8" in notes)
    ck("channel_gate_false", evaluation["channel_screen_gate_pass"] is False and "Channel gate = false" in visible)
    ck("rk_g1_false", evaluation["rk_g1_pass"] is False and "RK-G1 = false" in visible)
    ck("generator_unauthorized", evaluation["expensive_generation_authorized"] is False and "generator unauthorized" in visible)
    ck("functional_untouched", evaluation["functional_untouched_evaluated"] is False and "19,072" in visible and "not evaluated" in visible)
    ck("velocity_boundary", evaluation["velocity_mechanism_pass"] is False and "velocity endpoint remains failed" in notes)
    ck("manuscript_anchor", "manuscript v31 §6.27" in visible and "7d5e51a1" in visible and "7d5e51a17f93218e831bc22b845c030065362a35" in notes)

    table = root.find(".//" + ns + "table")
    ck("single_native_table", table is not None)
    rows = table.findall(ns + "tr")
    ck("table_four_rows", len(rows) == 4)
    ck("table_five_columns", len(table.find(ns + "colgroup").findall(ns + "col")) == 5 and all(len(row.findall(ns + "td")) == 5 for row in rows))
    sequence_rows = [row for row in evaluation["comparisons"] if row["partition"] == "sequence_ood"]
    ck("six_frozen_comparisons", len(sequence_rows) == 6)
    pivot = {}
    for source in sequence_rows:
        key = source["right"]
        item = pivot.setdefault(key, {})
        item[source["metric"]] = source
    ck("three_comparators", set(pivot) == {"ribokinetic_none", "ridge_all", "ridge_gc"})

    def signed3(value):
        return f"{value:+.3f}".replace("-", "−")

    expected_display = {}
    for right, row in pivot.items():
        spearman, mse = row["spearman"], row["cluster_balanced_mse"]
        expected_display[right] = {
            "spearman": f"{signed3(spearman['point_delta'])} [{signed3(spearman['ci95_low'])}, {signed3(spearman['ci95_high'])}]",
            "mse": f"{signed3(mse['point_delta'])} [{signed3(mse['ci95_low'])}, {signed3(mse['ci95_high'])}]",
            "spearman_p": str(spearman["holm_pvalue_within_partition"]),
            "mse_p": str(mse["holm_pvalue_within_partition"]),
        }
        for metric in [spearman, mse]:
            ck(f"note_delta_{right}_{metric['metric']}", repr(metric["point_delta"]) in notes)
            ck(f"note_ci_low_{right}_{metric['metric']}", repr(metric["ci95_low"]) in notes)
            ck(f"note_ci_high_{right}_{metric['metric']}", repr(metric["ci95_high"]) in notes)
            if metric["holm_pvalue_within_partition"]:
                ck(f"note_p_{right}_{metric['metric']}", repr(metric["holm_pvalue_within_partition"]) in notes)
            ck(f"bootstrap_valid_{right}_{metric['metric']}", metric["bootstrap_valid"] == metric["bootstrap_requested"] == 2000)
    ck("display_none_spearman", expected_display["ribokinetic_none"]["spearman"] in visible, expected_display["ribokinetic_none"]["spearman"])
    ck("display_none_mse", expected_display["ribokinetic_none"]["mse"] in visible, expected_display["ribokinetic_none"]["mse"])
    ck("display_full_spearman", expected_display["ridge_all"]["spearman"] in visible, expected_display["ridge_all"]["spearman"])
    ck("display_full_mse", expected_display["ridge_all"]["mse"] in visible, expected_display["ridge_all"]["mse"])
    ck("display_gc_spearman", expected_display["ridge_gc"]["spearman"] in visible, expected_display["ridge_gc"]["spearman"])
    ck("display_gc_mse", expected_display["ridge_gc"]["mse"] in visible, expected_display["ridge_gc"]["mse"])
    ck("full_p_values", "0.532" in visible and "0.636" in visible)
    ck("zero_holm_display", visible.count("<0.001") == 4 and len(re.findall(r"Holm p=0(?!\.\d)", notes)) == 4)
    for right in ["ribokinetic_none", "ridge_gc"]:
        spearman, mse = pivot[right]["spearman"], pivot[right]["cluster_balanced_mse"]
        ck(f"supported_{right}", spearman["ci95_low"] > 0 and mse["ci95_high"] < 0 and spearman["holm_pvalue_within_partition"] < 0.05 and mse["holm_pvalue_within_partition"] < 0.05)
    full_s, full_m = pivot["ridge_all"]["spearman"], pivot["ridge_all"]["cluster_balanced_mse"]
    ck("full_ci_cross_zero", full_s["ci95_low"] < 0 < full_s["ci95_high"] and full_m["ci95_low"] < 0 < full_m["ci95_high"])
    ck("full_not_significant", full_s["holm_pvalue_within_partition"] == 0.532 and full_m["holm_pvalue_within_partition"] == 0.636)
    ck("supported_card", "2/2 endpoints vs none · 2/2 vs ridge_gc" in visible)
    ck("gate_card", "No significant increment over ridge_all" in visible and "both CIs cross zero" in visible)

    if args.mode == "final":
        before_path = work / "rk08_source_v02.xml"
        after_path = work / "rk08_after_v01.xml"
        before_root = ET.parse(before_path).getroot()
        after_root = ET.parse(after_path).getroot()
        before_ns = before_root.tag.split("}")[0] + "}"
        after_ns = after_root.tag.split("}")[0] + "}"
        before_slides = before_root.findall(before_ns + "slide")
        after_slides = after_root.findall(after_ns + "slide")
        add_response = load(work / "rk08_add_response_v01.json")
        after_response = load(work / "rk08_after_response_v01.json")
        ck("add_ok", add_response.get("ok") is True)
        new_id = add_response.get("data", {}).get("slide_id")
        ck("new_id_present", bool(new_id))
        ck("add_revision_69", add_response.get("data", {}).get("revision_id") == 69)
        ck("after_ok", after_response.get("ok") is True and after_response.get("data", {}).get("revision_id") == 69)
        ck("before_106_after_107", len(before_slides) == 106 and len(after_slides) == 107)
        ck("new_last_id", after_slides[-1].get("id") == new_id)
        ck("old_slide_ids_preserved", [s.get("id") for s in before_slides] == [s.get("id") for s in after_slides[:106]])
        for index, (old, new) in enumerate(zip(before_slides, after_slides[:106]), start=1):
            ck(f"old_page_semantics_{index}", signature(old) == signature(new))
        ck("new_page_scientific_text", "full-proxy increment is not established" in text(after_slides[-1]) and "Channel gate = false" in text(after_slides[-1]))
        ck("new_page_note", "320/320" in text(after_slides[-1]) and "7d5e51a17f93218e831bc22b845c030065362a35" in text(after_slides[-1]))
        screenshot = load(work / "rk08_screenshot_response_v01.json")
        ck("screenshot_ok", screenshot.get("ok") is True)
        shots = screenshot.get("data", {}).get("screenshots", [])
        ck("one_screenshot", len(shots) == 1 and shots[0].get("slide_id") == new_id)
        if shots:
            path = Path(shots[0]["path"])
            if not path.is_file():
                path = work / "rk08_screenshots_v01" / path.name
            ck("screenshot_file", path.is_file() and path.stat().st_size > 10000, str(path))
            ck("screenshot_sha", bool(sha(path)))
        ck("visual_reviewed", args.visual_reviewed)

    passed = sum(row["pass"] for row in checks)
    result = {
        "schema": "a8-rk08-channel-screen-ppt-verification-v1",
        "mode": args.mode,
        "status": "PASS_RK08_CHANNEL_SCREEN_PPT" if passed == len(checks) else "FAIL",
        "overall_pass": passed == len(checks),
        "check_counts": {"passed": passed, "total": len(checks)},
        "candidate_sha256": sha(candidate_path),
        "selection_sha256": sha(work / "channel_screen_selection_v1.json"),
        "evaluation_sha256": sha(work / "channel_screen_evaluation_v1.json"),
        "independent_sha256": sha(work / "channel_screen_independent_v1.json"),
        "finalization_sha256": sha(work / "channel_screen_finalization_v1.json"),
        "channel_screen_gate_pass": False,
        "rk_g1_pass": False,
        "functional_untouched_evaluated": False,
        "generator_training_authorized": False,
        "checks": checks,
    }
    if args.mode == "final":
        result["slide_id"] = new_id
        result["revision_id"] = 69
        result["source_sha256"] = sha(before_path)
        result["after_sha256"] = sha(after_path)
    out = Path(args.output)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "check_counts": result["check_counts"]}, indent=2))
    if passed != len(checks):
        for row in checks:
            if not row["pass"]:
                print("FAIL", row)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
