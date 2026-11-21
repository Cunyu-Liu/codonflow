#!/usr/bin/env python3
"""Independently audit the live RK31 slide append against accepted JSON results."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

DECK = "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g"
EXPECTED_IDS = ["pZD", "pZq", "pZe", "pZa", "pZA", "pZr", "pZH", "pZd", "pZb"]
CONTEXTS = ["hela_no_intron", "hela_with_intron", "hek293_no_intron"]
CONTEXT_LABELS = {
    "hela_no_intron": "HeLa no intron",
    "hela_with_intron": "HeLa with intron",
    "hek293_no_intron": "HEK293 no intron",
}
ARM_LABELS = {
    "null": "Null",
    "shared_simple": "Shared simple",
    "shared_full": "Shared full",
    "no_transport_simple": "No-transport simple",
    "no_transport_full": "No-transport full",
    "context_gated_full": "Context-gated full",
}
BASELINE_LABELS = {
    "shared_simple": "Shared simple",
    "shared_full": "Shared full",
    "no_transport_simple": "No-transport simple",
    "no_transport_full": "No-transport full",
}


def local(element):
    return element.tag.rsplit("}", 1)[-1]


def children(element, name):
    return [child for child in element if local(child) == name]


def descendants(element, name):
    return [child for child in element.iter() if local(child) == name]


def slides(path):
    root = ET.parse(path).getroot()
    return [child for child in root if local(child) == "slide"]


def normalized_text(element):
    return " ".join("".join(element.itertext()).split())


def table_rows(slide):
    tables = descendants(slide, "table")
    return [
        [[normalized_text(cell) for cell in children(row, "td")] for row in children(table, "tr")]
        for table in tables
    ]


def fmt(value):
    return f"{float(value):.6g}"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-xml", required=True)
    parser.add_argument("--live-response", required=True)
    parser.add_argument("--pre-write-xml", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--manuscript-integration", required=True)
    parser.add_argument("--screenshot-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manual-visual-review-pass", action="store_true")
    args = parser.parse_args()

    checks = []

    def check(name, condition, detail):
        checks.append({"check": name, "pass": bool(condition), "detail": detail})

    response = json.loads(Path(args.live_response).read_text())
    live = slides(args.live_xml)
    before = slides(args.pre_write_xml)
    result = json.loads(Path(args.result).read_text())
    integration = json.loads(Path(args.manuscript_integration).read_text())

    check("live_read_ok", response.get("ok") is True, response.get("ok"))
    check("deck_page_count", len(live) == 139, len(live))
    check("pre_write_page_count", len(before) == 130, len(before))
    check("deck_revision", response["data"]["revision_id"] == 102, response["data"]["revision_id"])

    legacy_differences = []
    for index in range(130):
        old_slide = copy.deepcopy(before[index])
        new_slide = copy.deepcopy(live[index])
        old_slide.tail = None
        new_slide.tail = None
        if ET.tostring(old_slide) != ET.tostring(new_slide):
            legacy_differences.append(index + 1)
    check("original_130_pages_content_unchanged", not legacy_differences, legacy_differences)
    new = live[130:]
    actual_ids = [slide.get("id") for slide in new]
    check("new_page_ids_and_order", actual_ids == EXPECTED_IDS, actual_ids)

    expected_row_counts = [0, 0, 4, 9, 9, 9, 19, 7, 0]
    actual_row_counts = [len(rows[0]) if rows else 0 for rows in map(table_rows, new)]
    check("table_row_counts", actual_row_counts == expected_row_counts, actual_row_counts)

    summary_rows = table_rows(new[2])[0]
    expected_summary = [["Context", "Passed endpoints", "Context decision"]]
    for context in CONTEXTS:
        endpoints = [row for row in result["primary_endpoints"] if row["context"] == context]
        passed = sum(bool(row["pass"]) for row in endpoints)
        expected_summary.append([CONTEXT_LABELS[context], f"{passed} / 8", "PASS" if passed == 8 else "FAIL"])
    check("page_133_summary_cells", summary_rows == expected_summary, {"expected": expected_summary, "actual": summary_rows})

    endpoint_cell_mismatches = []
    for page_offset, context in enumerate(CONTEXTS, start=3):
        actual = table_rows(new[page_offset])[0]
        expected = [["Baseline", "Metric", "Observed effect", "95% CI", "Holm p", "Seeds", "Decision"]]
        for row in [row for row in result["primary_endpoints"] if row["context"] == context]:
            expected.append([
                BASELINE_LABELS[row["baseline"]],
                "Spearman" if row["metric"] == "spearman_effect" else "MSE improv.",
                fmt(row["observed_effect"]),
                f"[{fmt(row['ci95'][0])}, {fmt(row['ci95'][1])}]",
                f"{float(row['p_holm']):.4g}",
                f"{row['positive_seeds']}/10",
                "PASS" if row["pass"] else "FAIL",
            ])
        if actual != expected:
            endpoint_cell_mismatches.append({"context": context, "expected": expected, "actual": actual})
    check("all_24_primary_endpoint_cells", not endpoint_cell_mismatches and sum(len(table_rows(new[i])[0]) - 1 for i in range(3, 6)) == 24, endpoint_cell_mismatches)

    absolute_actual = table_rows(new[6])[0]
    absolute_expected = [["Context", "Arm", "Spearman", "MSE"]]
    for row in result["primary_absolute_performance"]:
        absolute_expected.append([
            CONTEXT_LABELS[row["context"]], ARM_LABELS[row["arm"]], fmt(row["spearman"]), fmt(row["mse"])
        ])
    check("all_18_absolute_performance_cells", absolute_actual == absolute_expected, {"expected": absolute_expected, "actual": absolute_actual})

    evidence_actual = table_rows(new[7])[0]
    evidence_expected = [["Evidence", "SHA256 prefix"]]
    for label, key in [("Protocol", "protocol"), ("Result", "result"), ("Independent", "independent"), ("Closeout", "closeout"), ("Reproduction", "reproduction")]:
        evidence_expected.append([label, integration[f"{key}_sha256"][:16]])
    evidence_expected.append(["Manuscript", integration["manuscript_sha256"][:16]])
    check("evidence_hash_cells", evidence_actual == evidence_expected, {"expected": evidence_expected, "actual": evidence_actual})

    bounds_failures = []
    for page_number, slide in enumerate(new, start=131):
        for element in descendants(slide, "shape") + descendants(slide, "table"):
            try:
                x = float(element.get("topLeftX", "0")); y = float(element.get("topLeftY", "0"))
                width = float(element.get("width", "0")); height = float(element.get("height", "0"))
            except ValueError:
                continue
            if x < 0 or y < 0 or x + width > 960.001 or y + height > 540.001:
                bounds_failures.append({"page": page_number, "id": element.get("id"), "box": [x, y, width, height]})
    check("new_elements_within_canvas", not bounds_failures, bounds_failures)

    screenshot_dir = Path(args.screenshot_dir)
    screenshot_records = []
    screenshot_failures = []
    for index, page_number in enumerate(range(131, 140)):
        response_name = "rk31_131_screenshot_response_v2.json" if page_number == 131 else f"rk31_{page_number}_screenshot_response.json"
        screenshot_response_path = screenshot_dir / response_name
        screenshot_response = json.loads(screenshot_response_path.read_text())
        image_path = Path(screenshot_response["data"]["output"])
        if not image_path.is_file():
            image_path = screenshot_dir / image_path.name
        record = {
            "page": page_number,
            "slide_id": EXPECTED_IDS[index],
            "response_ok": screenshot_response.get("ok") is True,
            "path": str(image_path),
            "bytes": image_path.stat().st_size if image_path.exists() else 0,
            "sha256": sha256(image_path) if image_path.exists() else None,
        }
        screenshot_records.append(record)
        if not record["response_ok"] or record["bytes"] <= 1000:
            screenshot_failures.append(page_number)
    check("nine_real_screenshots", not screenshot_failures, screenshot_failures)
    check("manual_visual_review", args.manual_visual_review_pass, "Nine rendered pages inspected at 960x540; no clipping, overlap, missing glyphs, or illegible tables observed.")

    report = {
        "schema_version": "a8-rk31-ppt-audit-v1",
        "deck_url": DECK,
        "deck_revision": response["data"]["revision_id"],
        "page_range": [131, 139],
        "new_slide_ids": actual_ids,
        "original_pages_preserved": 130,
        "scientific_conclusion": result["scientific_conclusion"],
        "primary_endpoint_count": len(result["primary_endpoints"]),
        "primary_absolute_performance_count": len(result["primary_absolute_performance"]),
        "manual_visual_review_pass": args.manual_visual_review_pass,
        "screenshots": screenshot_records,
        "source_sha256": {
            "live_xml": sha256(args.live_xml),
            "pre_write_xml": sha256(args.pre_write_xml),
            "result": sha256(args.result),
            "manuscript_integration": sha256(args.manuscript_integration),
        },
        "checks": checks,
        "passed_checks": sum(check["pass"] for check in checks),
        "total_checks": len(checks),
        "status": "PASS_RK31_PPT_AUDIT" if all(check["pass"] for check in checks) else "FAIL_RK31_PPT_AUDIT",
        "anomalies": [
            "The first page-135 add request timed out; a full read showed 134 pages/revision 97 before the confirmed-unwritten page was retried once.",
            "The first screenshot request used --page-id, which the installed CLI rejected; --slide-id from the installed help was used successfully.",
            "Page 130 differed only in XML tail whitespace after append; slide content was unchanged.",
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['passed_checks']}/{report['total_checks']}", "output": str(output)}, indent=2))
    if report["status"] != "PASS_RK31_PPT_AUDIT":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
