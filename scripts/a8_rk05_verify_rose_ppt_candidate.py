#!/usr/bin/env python3
"""Independently validate the ROSE slide candidate against frozen JSON evidence."""
import hashlib
import json
import math
import os
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(os.environ.get("ROSE_PPT_WORK_DIR", Path(__file__).resolve().parent))
CANDIDATE = ROOT / "rose_candidate_v1.xml"
production = json.loads((ROOT / "rose_production_frozen.json").read_text())
independent = json.loads((ROOT / "rose_independent_frozen.json").read_text())
finalization = json.loads((ROOT / "rose_finalization_frozen.json").read_text())
a8 = json.loads((ROOT / "a8_v10_verification_frozen.json").read_text())
raw = CANDIDATE.read_bytes()
text = raw.decode("utf-8")
root = ET.fromstring(raw)
ns = root.tag.split("}")[0] + "}"
visible = "\n".join(t.strip() for t in root.itertext() if t.strip())
checks = {}


def check(name, condition, details=None):
    checks[name] = {"passed": bool(condition), "details": details}


check("production_and_a8_status", production["status"] == "PASS_COMPLETE_RELEASED_TEST_SINGLE_CHECKPOINT_INFERENCE" and a8["status"] == "PASS" and a8["passed_checks"] == a8["check_count"] == 21)
check("fixed_source", production["source"]["commit"].startswith("8b86d69") and "Fixed 8b86d69" in visible)
expected_rows = []
for name in ("Pop14", "Battle15"):
    study = production["studies"][name]
    metrics = study["metrics"]
    expected_rows.extend([
        f"{study['records']:,} ({study['positive']:,}/{study['negative']:,})",
        f"{metrics['roc_auc']:.6f}", f"{metrics['average_precision']:.6f}",
        f"{metrics['accuracy_at_0.5']:.6f}", f"{metrics['log_loss']:.6f}",
    ])
    check(name + "_complete_single_checkpoint", study["training"] is False and study["checkpoint_count"] == 1 and study["forward_passes"] == 1 and study["input_nt_per_record"] == 183 and study["input_codons_per_record"] == 61, {"records": study["records"], "parameters": study["parameter_count"]})
check("all_metric_strings_from_frozen_json", all(value in visible for value in expected_rows), expected_rows)
check("parameter_and_input_protocol", "128,834 / 265,858 parameters" in visible and "183 nt / 61 codons" in visible and production["studies"]["Pop14"]["parameter_count"] == 128834 and production["studies"]["Battle15"]["parameter_count"] == 265858)
check("independent_exact_reproduction", independent["status"] == "PASS" and independent["passed_count"] == independent["check_count"] == 34 and not independent["production_driver_imported"] and "34/34" in visible and all(independent["studies"][name]["logit_max_abs_delta"] == 0.0 and independent["studies"][name]["production_float32_formula_max_abs_delta"] == 0.0 and all(v == 0.0 for v in independent["studies"][name]["metric_abs_deltas"].values()) for name in ("Pop14", "Battle15")))
check("finalization", finalization["status"] == "PASS" and finalization["passed_count"] == finalization["check_count"] == 60 and "60/60" in visible and "tests 12/12" in visible)
baselines = [production["studies"][name]["metrics"]["constant_prevalence_baseline"] for name in ("Pop14", "Battle15")]
check("constant_baseline", all(b["roc_auc"] == b["average_precision"] == 0.5 and math.isclose(b["log_loss"], math.log(2), abs_tol=5e-7) for b in baselines) and all(production["studies"][name]["positive"] == production["studies"][name]["negative"] for name in ("Pop14", "Battle15")) and all(s in visible for s in ("0.500000", "0.693147", "Constant prevalence")))
check("precision_failures_retained", "stable float64 is secondary" in visible and "verifier v1–v3 precision failures retained" in visible)
check("scientific_boundaries", all(production["scientific_scope"][key] for key in ("not_continuous_velocity_regression", "not_training", "not_64_checkpoint_ensemble", "not_protein_or_study_or_functional_ood", "not_matched_cost_or_sota", "not_raw_read_or_psite_remapping", "not_codonflow_rk")) and all(s in visible for s in ("Binary stalling only", "no training, 64-model ensemble, velocity regression, OOD or SOTA", "binary stalling is not velocity regression")))
check("github_evidence_links", "3a284efe" in visible and "f17f432e" in visible)
geometry_ok = True
for element in root.iter():
    if all(key in element.attrib for key in ("topLeftX", "topLeftY", "width", "height")):
        x, y = float(element.attrib["topLeftX"]), float(element.attrib["topLeftY"])
        w, h = float(element.attrib["width"]), float(element.attrib["height"])
        geometry_ok = geometry_ok and x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 960 and y + h <= 540
check("canvas_and_notes", geometry_ok and len(root.findall(".//" + ns + "note//" + ns + "p")) == 4 and not any(element.attrib.get("id") for element in root.iter()))
check("single_page_number", ">78<" in text and ">77<" not in text and root.tag.endswith("slide"))

passed = sum(item["passed"] for item in checks.values())
report = {
    "schema_version": "rose-ppt-candidate-independent-preflight-v1",
    "status": "PASS" if passed == len(checks) else "FAIL",
    "check_count": len(checks),
    "passed_count": passed,
    "candidate": CANDIDATE.name,
    "candidate_sha256": hashlib.sha256(raw).hexdigest(),
    "production_report_sha256": hashlib.sha256((ROOT / "rose_production_frozen.json").read_bytes()).hexdigest(),
    "independent_report_sha256": hashlib.sha256((ROOT / "rose_independent_frozen.json").read_bytes()).hexdigest(),
    "finalization_report_sha256": hashlib.sha256((ROOT / "rose_finalization_frozen.json").read_bytes()).hexdigest(),
    "a8_verification_sha256": hashlib.sha256((ROOT / "a8_v10_verification_frozen.json").read_bytes()).hexdigest(),
    "checks": checks,
}
(ROOT / "rose_ppt_candidate_preflight_v1.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "candidate_sha256": report["candidate_sha256"]}, indent=2))
if report["status"] != "PASS":
    print(json.dumps({k: v for k, v in checks.items() if not v["passed"]}, indent=2, ensure_ascii=False))
    raise SystemExit(1)
