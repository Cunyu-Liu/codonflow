#!/usr/bin/env python3
"""Independent post-write verification for the MAGE nested-development slide."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audits/20261119/RK03"
ART = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/ppt_mage_development_nested_cv_v1")
OUT = AUDIT / "mage_development_nested_cv_ppt_verification.json"
URL = "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g"


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


final = load(AUDIT / "mage_development_nested_cv_finalization_v2.json")
production = load(AUDIT / "mage_development_nested_cv_v2.json")
ind = load(AUDIT / "mage_development_nested_cv_independent_v2.json")
paper = load(AUDIT / "mage_development_nested_cv_paper_verification_v2.json")
preflight = load(AUDIT / "mage_development_nested_cv_ppt_candidate_verification.json")
add = load(ART / "mage-v26-add-response.json")
baseline_response = load(ART / "mage-v26-baseline-response.json")
precommit_response = load(ART / "mage-v26-precommit-response.json")
post_response = load(ART / "mage-v26-post-response.json")
old = ET.parse(ART / "mage-v26-precommit.xml").getroot()
new = ET.parse(ART / "mage-v26-post.xml").getroot()
candidate = ET.parse(ART / "mage-v26-candidate.xml").getroot()
uri = new.tag[1:].split("}")[0]
q = lambda tag: f"{{{uri}}}{tag}"
old_slides = old.findall(q("slide"))
new_slides = new.findall(q("slide"))
last = new_slides[-1]
text = "\n".join(last.itertext())
checks = []


def check(name, condition, detail=None):
    checks.append({"name": name, "pass": bool(condition), "detail": detail})


def sem(element):
    return (
        element.tag,
        tuple(sorted((k, v) for k, v in element.attrib.items() if k != "id")),
        (element.text or "").strip(),
        tuple(sem(child) for child in list(element)),
    )


check("scientific_finalization_30_pass", final["status"] == "PASS" and final["checks_passed"] == final["checks_total"] == 30)
check("scientific_independent_96_pass", ind["status"] == "PASS" and ind["checks_passed"] == ind["checks_total"] == 96)
check("paper_54_pass", paper["status"] == "PASS" and paper["checks_passed"] == paper["checks_total"] == 54)
check("paper_candidate_facts_29_pass", paper["candidate_facts_passed"] == paper["candidate_facts_total"] == 29)
check("paper_non_submittable", paper["submittable"] is False and final["manuscript_submittable"] is False)
check("development_no_go", final["development_go"] is False and production["status"] == "DEV_NO_GO_TEST_UNTOUCHED")
check("rk_g1_remains_open", final["rk_g1_pass"] is False)
check("generator_not_authorized", final["expensive_generation_authorized"] is False)
check("functional_untouched_not_evaluated", final["functional_untouched_evaluated"] is False)
check("mechanism_test_33_untouched", final["test_n_untouched"] == 33)
check("candidate_preflight_52_pass", preflight["status"] == "PASS" and preflight["checks_passed"] == preflight["checks_total"] == 52)
check("candidate_preflight_hash", preflight["candidate_sha256"] == sha(ART / "mage-v26-candidate.xml"))
check("baseline_response_ok", baseline_response["ok"] is True)
check("baseline_101_revision_63", baseline_response["data"]["revision_id"] == 63 and len(old_slides) == 101)
check("precommit_response_ok", precommit_response["ok"] is True and precommit_response["data"]["revision_id"] == 63)
check("precommit_byte_identical_to_baseline", sha(ART / "mage-v26-baseline.xml") == sha(ART / "mage-v26-precommit.xml"))
check("add_response_ok", add["ok"] is True)
check("add_response_page_and_revision", add["data"]["slide_id"] == "pgj" and add["data"]["revision_id"] == 64, add["data"])
check("post_response_ok", post_response["ok"] is True and post_response["data"]["revision_id"] == 64)
check("post_slide_count_102", len(new_slides) == 102)
check("new_page_102_pgJ", last.attrib.get("id") == "pgj")
prefix_differences = [i + 1 for i, (a, b) in enumerate(zip(old_slides, new_slides[:101])) if sem(a) != sem(b)]
check("first_101_pages_semantically_unchanged", not prefix_differences, prefix_differences)
check("ribomimo_page_101_preserved", new_slides[100].attrib.get("id") == "pgI" and "RiboMIMO" in " ".join(new_slides[100].itertext()))
check("candidate_online_semantic_equal", sem(candidate) == sem(last))
check("candidate_has_no_ids", all("id" not in e.attrib for e in candidate.iter()))
check("online_new_page_has_server_id", last.attrib.get("id") == "pgj")

data = last.find(q("data"))
text_shapes = [e for e in data.findall(q("shape")) if e.attrib.get("type") == "text"]
table = data.find(q("table"))
rows = table.findall(q("tr"))
notes = last.find(q("note")).find(q("content")).findall(q("p"))
check("new_page_20_text_shapes", len(text_shapes) == 20)
check("new_page_table_6_by_5", len(rows) == 6 and all(len(row.findall(q("td"))) == 5 for row in rows))
check("new_page_5_note_paragraphs", len(notes) == 5)
bbox_failures = []
for element in data:
    if all(k in element.attrib for k in ("topLeftX", "topLeftY", "width", "height")):
        x, y, w, h = (float(element.attrib[k]) for k in ("topLeftX", "topLeftY", "width", "height"))
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 960 or y + h > 540:
            bbox_failures.append([x, y, w, h])
check("new_page_elements_inside_canvas", not bbox_failures, bbox_failures)
badge = data.findall(q("shape"))[0]
title = text_shapes[2]
check("title_badge_overlap_fixed", float(title.attrib["topLeftY"]) >= float(badge.attrib["topLeftY"]) + float(badge.attrib["height"]))

models = final["primary_models"]
for model, values in models.items():
    for metric in ("rmse", "spearman"):
        needles = (f"{values[metric]:.9f}", f"{values[metric]:.6f}")
        check(f"online_{model}_{metric}", any(n in text for n in needles), values[metric])
comparisons = final["primary_comparisons"]
for name, values in comparisons.items():
    for key in ("delta_spearman", "delta_rmse"):
        value = values[key]
        check(f"online_{name}_{key}", f"{value:+.6f}".replace("-", "−") in text, value)
    for key in ("delta_spearman_ci95", "delta_rmse_ci95"):
        values_ci = values[key]
        expected = "[" + ", ".join(f"{v:+.6f}".replace("-", "−") for v in values_ci) + "]"
        check(f"online_{name}_{key}", expected in text, expected)
    check(f"online_{name}_both_holm_one", values["holm_p_spearman"] == values["holm_p_rmse"] == 1.0)

required = {
    "title": "MAGE 同义机制增量：nested CV 仍未通过开发门禁",
    "verification_badge": "96/96 + 30/30 · VERIFIED",
    "development_design": "131 development = 98 train + 33 dev",
    "test_excluded": "33 test excluded",
    "nested_folds": "5-fold outer / 4-fold inner",
    "resamples": "20,000 bootstrap + 20,000 sign flips",
    "holm_scope": "Holm across 4",
    "frozen_decision": "NO-GO",
    "all_cis_cross_zero": "四个区间均跨零",
    "sensitivity_failed": "敏感性方向不一致",
    "intrinsic_rmse_worse": "intrinsic RMSE 反而更高",
    "development_only": "development-only",
    "test_untouched": "33 test untouched",
    "not_protein_ood": "非蛋白 OOD",
    "not_universal_structure_falsification": "非普遍结构证伪",
    "rcs_supervised": "RCS is supervised",
    "frozen_status": "DEV_NO_GO_TEST_UNTOUCHED",
    "independent_count": "independent 96/96",
    "finalization_count": "finalization 30/30",
    "paper_count": "paper 54/54",
    "paper_facts_count": "候选事实 29/29",
    "github_short": "85feef400ec1",
    "github_full": "85feef400ec1bd477c817416cfe5928108eef8da",
    "sensitivity_seed_120": "40261120",
    "sensitivity_seed_121": "40261121",
    "rcs_not_physical_truth": "不是无监督物理真值",
    "rk_g1_not_closed": "不关闭 RK-G1 或授权生成器训练",
}
for name, needle in required.items():
    check(f"required_text_{name}", needle in text, needle)
check("no_old_fixed_gfp_text", "FIXED-GFP" not in text and "observed R1" not in text)
check("no_old_ribomimo_text", "RiboMIMO" not in text and "Subtelny" not in text)
check("no_test_predictions_or_metrics_claim", "test predictions" not in text.lower() and "test metrics" not in text.lower())

report = {
    "schema": "a8-rk03-mage-development-ppt-verification-v1",
    "presentation": URL,
    "presentation_revision_id": post_response["data"]["revision_id"],
    "slide_count": len(new_slides),
    "new_slide_number": 102,
    "new_slide_id": last.attrib["id"],
    "previous_slide_count": len(old_slides),
    "previous_last_slide_id": old_slides[-1].attrib["id"],
    "first_101_pages_semantically_unchanged": not prefix_differences,
    "candidate_online_semantic_equal_ignoring_ids": sem(candidate) == sem(last),
    "scientific_status": production["status"],
    "scientific_conclusion": final["conclusion"],
    "test_n_untouched": final["test_n_untouched"],
    "rk_g1_pass": final["rk_g1_pass"],
    "generator_training_authorized": final["expensive_generation_authorized"],
    "manuscript_submittable": final["manuscript_submittable"],
    "paper_sha256": paper["paper_sha256"],
    "source_sha256": {
        name: sha(ART / name)
        for name in (
            "mage-v26-baseline.xml",
            "mage-v26-precommit.xml",
            "mage-v26-candidate.xml",
            "mage-v26-add-response.json",
            "mage-v26-post.xml",
            "mage-v26-post-response.json",
        )
    },
    "checks": checks,
    "checks_passed": sum(c["pass"] for c in checks),
    "checks_total": len(checks),
    "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
(ART / OUT.name).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: report[k] for k in ("status", "checks_passed", "checks_total", "slide_count", "new_slide_id", "presentation_revision_id", "first_101_pages_semantically_unchanged", "candidate_online_semantic_equal_ignoring_ids")}, ensure_ascii=False, indent=2))
if report["status"] != "PASS":
    for item in checks:
        if not item["pass"]:
            print("FAIL", json.dumps(item, ensure_ascii=False))
    raise SystemExit(1)
