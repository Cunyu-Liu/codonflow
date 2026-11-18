#!/usr/bin/env python3
"""Verify the live ROSE append and protection of all pre-existing slides."""
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(os.environ.get("ROSE_PPT_WORK_DIR", Path(__file__).resolve().parent))


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def sha(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def slides(name):
    root = ET.parse(ROOT / name).getroot()
    ns = root.tag.split("}")[0] + "}"
    return root, ns, root.findall(ns + "slide")


def c14n(element):
    return ET.canonicalize(ET.tostring(element, encoding="unicode"))


def texts(element):
    return [value.strip() for value in element.itertext() if value.strip()]


baseline_response = load("rose_baseline_response_v1.json")
readback_response = load("rose_readback_response_v1.json")
add_response = load("rose_add_response_v1.json")
preflight = load("rose_ppt_candidate_preflight_v1.json")
production = load("rose_production_frozen.json")
independent = load("rose_independent_frozen.json")
finalization = load("rose_finalization_frozen.json")
a8 = load("a8_v10_verification_frozen.json")
base_root, base_ns, base = slides("rose_baseline_v1.xml")
current_root, current_ns, current = slides("rose_readback_v1.xml")
candidate_root = ET.parse(ROOT / "rose_candidate_v1.xml").getroot()
new_slide = current[-1]
new_text = texts(new_slide)
visible = "\n".join(new_text)
checks = {}


def check(name, condition, details=None):
    checks[name] = {"passed": bool(condition), "details": details}


check("candidate_preflight", preflight["status"] == "PASS" and preflight["passed_count"] == preflight["check_count"] == 14 and preflight["candidate_sha256"] == sha("rose_candidate_v1.xml"))
check("successful_single_add_response", add_response["ok"] is True and add_response["data"]["slide_id"] == "pgc" and add_response["data"]["revision_id"] == 40)
check("baseline_identity", baseline_response["ok"] is True and baseline_response["data"]["revision_id"] == 39 and len(base) == 77 and base[-1].attrib.get("id") == "pgW")
check("readback_identity", readback_response["ok"] is True and readback_response["data"]["revision_id"] == 40 and len(current) == 78 and current_root.attrib.get("width") == "960" and current_root.attrib.get("height") == "540")
check("old_slide_order_and_ids", [s.attrib.get("id") for s in current[:77]] == [s.attrib.get("id") for s in base])
old_differences = [index + 1 for index, (before, after) in enumerate(zip(base, current[:77])) if c14n(before) != c14n(after)]
check("all_77_old_slides_xml_identical", not old_differences, old_differences)
check("one_new_last_slide", current[-1].attrib.get("id") == "pgc" and [s.attrib.get("id") for s in current].count("pgc") == 1)
check("no_duplicate_rose_result_page", "ROSE Released-Test Inference Verified" not in "\n".join(texts(base_root)) and "\n".join(texts(current_root)).count("ROSE Released-Test Inference Verified") == 1)
check("new_slide_text_matches_candidate", new_text == texts(candidate_root), {"candidate_text_items": len(texts(candidate_root)), "readback_text_items": len(new_text)})
expected_metrics = []
for name in ("Pop14", "Battle15"):
    study = production["studies"][name]
    metrics = study["metrics"]
    expected_metrics.extend([f"{study['records']:,} ({study['positive']:,}/{study['negative']:,})", f"{metrics['roc_auc']:.6f}", f"{metrics['average_precision']:.6f}", f"{metrics['accuracy_at_0.5']:.6f}", f"{metrics['log_loss']:.6f}"])
check("metrics_and_sample_counts", all(value in visible for value in expected_metrics))
check("independent_finalization_and_a8", independent["status"] == "PASS" and independent["passed_count"] == independent["check_count"] == 34 and finalization["status"] == "PASS" and finalization["passed_count"] == finalization["check_count"] == 60 and a8["status"] == "PASS" and a8["passed_checks"] == a8["check_count"] == 21 and all(value in visible for value in ("34/34", "60/60", "tests 12/12", "21/21")))
check("scientific_scope_and_failures", all(value in visible for value in ("binary stalling is not velocity regression", "no training, 64-model ensemble, velocity regression, OOD or SOTA", "stable float64 is secondary", "verifier v1–v3 precision failures retained", "raw-read 或 P-site 重映射")))
check("speaker_notes_and_evidence", len(new_slide.findall(".//" + current_ns + "note//" + current_ns + "p")) == 4 and all(value in visible for value in ("3a284efe", "f17f432e", "8b86d69")))
geometry_ok = True
for element in new_slide.iter():
    if all(key in element.attrib for key in ("topLeftX", "topLeftY", "width", "height")):
        x, y = float(element.attrib["topLeftX"]), float(element.attrib["topLeftY"])
        w, h = float(element.attrib["width"]), float(element.attrib["height"])
        geometry_ok = geometry_ok and x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 960 and y + h <= 540
check("new_slide_geometry_and_supported_elements", geometry_ok and not new_slide.findall(".//" + current_ns + "undefined") and not new_slide.findall(".//" + current_ns + "img") and "Rz33" not in visible and "ASKPASS" not in visible)

passed = sum(item["passed"] for item in checks.values())
report = {
    "schema_version": "rose-ppt-live-independent-verification-v1",
    "status": "PASS" if passed == len(checks) else "FAIL",
    "check_count": len(checks),
    "passed_count": passed,
    "presentation": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
    "baseline_revision": 39,
    "final_revision": 40,
    "baseline_slide_count": len(base),
    "final_slide_count": len(current),
    "new_slide_id": "pgc",
    "old_slide_xml_differences": old_differences,
    "candidate_sha256": sha("rose_candidate_v1.xml"),
    "baseline_xml_sha256": sha("rose_baseline_v1.xml"),
    "readback_xml_sha256": sha("rose_readback_v1.xml"),
    "add_response_sha256": sha("rose_add_response_v1.json"),
    "readback_response_sha256": sha("rose_readback_response_v1.json"),
    "checks": checks,
}
(ROOT / "rose_ppt_final_verification_v1.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "slides": len(current), "new_slide_id": "pgc", "old_slide_differences": old_differences}, indent=2))
if report["status"] != "PASS":
    print(json.dumps({name: value for name, value in checks.items() if not value["passed"]}, indent=2, ensure_ascii=False))
    raise SystemExit(1)
