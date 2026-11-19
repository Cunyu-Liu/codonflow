import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument("--work-dir", default=str(Path(__file__).resolve().parent))
args = parser.parse_args()
ROOT = Path(args.work_dir).resolve()
checks = []

def add(name, passed, detail=None):
    checks.append({"name": name, "pass": bool(passed), "detail": detail})

def load_json(name):
    return json.loads((ROOT / name).read_text())

def slides(path):
    root = ET.parse(ROOT / path).getroot()
    return root, [e for e in root if e.tag.split("}")[-1] == "slide"]

def semantic(element, exclude_ids=False):
    text = element.text if element.text and element.text.strip() else None
    attrs = tuple(sorted((k, v) for k, v in element.attrib.items() if not (exclude_ids and k == "id")))
    return element.tag, attrs, text, tuple(semantic(c, exclude_ids) for c in element)

def sha(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()

baseline_response = load_json("baseline99-response.json")
add_response = load_json("add-response-v1.json")
readback_response = load_json("readback100-response.json")
fact_check = load_json("candidate-fact-check.json")
production = load_json("evidence/production.json")
independent = load_json("evidence/independent.json")
finalization = load_json("evidence/finalization.json")
paper = load_json("evidence/paper-verification.json")
_, before = slides("baseline99.xml")
_, after = slides("readback100.xml")
candidate = ET.parse(ROOT / "candidate-v1.xml").getroot()
new_slide = after[-1]

add("baseline_read_ok", baseline_response.get("ok") is True)
add("baseline_revision_61", baseline_response.get("data", {}).get("revision_id") == 61)
add("baseline_page_count_99", len(before) == 99)
add("add_ok", add_response.get("ok") is True)
add("add_revision_62", add_response.get("data", {}).get("revision_id") == 62)
add("add_slide_id_pgv", add_response.get("data", {}).get("slide_id") == "pgv")
add("readback_ok", readback_response.get("ok") is True)
add("readback_revision_62", readback_response.get("data", {}).get("revision_id") == 62)
add("readback_page_count_100", len(after) == 100)
add("new_slide_is_last", new_slide.get("id") == "pgv")
add("existing_cagfn_slide_kept_at_99", after[98].get("id") == "pgY")
add("existing_rk13_slides_kept_at_96_98", [s.get("id") for s in after[95:98]] == ["pgV", "pgs", "pgT"])
add("slide_ids_unique", len({s.get("id") for s in after}) == 100)
add("candidate_fact_check_19_of_19", fact_check["status"] == "PASS" and fact_check["checks_passed"] == fact_check["checks_total"] == 19)
add("candidate_hash_matches_fact_check", fact_check["candidate_sha256"] == sha("candidate-v1.xml"))
add("scientific_production_no_go", production["status"] == "DEV_STRUCTURE_INCREMENT_NO_GO_PENDING_INDEPENDENT" and not production["structure_increment_pass"])
add("scientific_independent_pass", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] == 12)
add("scientific_finalization_pass", finalization["status"] == "PASS_RK02_MORDSTEIN_STRUCTURE_INCREMENT_DEV" and finalization["checks_passed"] == finalization["checks_total"] == 21)
add("paper_verification_pass", paper["status"] == "PASS_RK02_STRUCTURE_PAPER_UPDATE" and paper["checks_passed"] == paper["checks_total"] == 38)

for index, (old, new) in enumerate(zip(before, after[:99]), start=1):
    add(f"prior_slide_{index:02d}_{old.get('id')}_semantic_xml_unchanged", old.get("id") == new.get("id") and semantic(old) == semantic(new))

add("candidate_online_semantic_xml_equal_excluding_server_ids", semantic(candidate, True) == semantic(new_slide, True))

visible_text = "\n".join(t.strip() for t in new_slide.itertext() if t.strip())
required_texts = [
    "12/12 + 21/21 · VERIFIED",
    "RK02 · FIXED-GFP OBSERVED-R1 STRUCTURE",
    "观测 R1 MFE 未显示已验证的开发集增量",
    "152 R1 variants · 5-fold OOF · ridge alpha = 1 · 300 nt full / 48 nt-window MFE",
    "20,000 paired bootstrap + 20,000 sign flips · Holm across 2 primary endpoints",
    "+0.413234", "+0.408983", "RMSE 1.383987 · MSE 1.915421", "RMSE 1.382025 · MSE 1.909992",
    "NO-GO", "development only · both CIs cross zero", "−0.004251", "−0.005429",
    "[−0.055205, +0.046336]", "[−0.089604, +0.076766]",
    "simple = log depth + GC + GC3 + CpG + CAI", "+structure = full MFE + 48 nt min / mean",
    "feature max abs diff = 2.78e-16", "prediction max abs diff = 1.07e-14",
    "结论 · 两个主终点均未通过方向门禁", "区间跨零 · 微小 MSE 下降不确定",
    "边界 · 仅限固定 GFP observed-R1 development", "非完整 CDS · 非蛋白 OOD · 非普遍结构证伪",
    "Evidence: independent 12/12 · finalization 21/21 · paper 38/38 · GitHub 1388ac627f23",
]
for i, value in enumerate(required_texts, start=1):
    add(f"new_slide_required_text_{i:02d}", value in visible_text, value)
for i, value in enumerate(["18/18 + 8/8", "GC3 rho range", "简单序列代理并非无信号", "FIXED_GFP_OBSERVED_R1_STRUCTURE_INCREMENT_NO_GO_DEVELOPMENT_ONLY"], start=1):
    add(f"new_slide_avoids_stale_or_internal_text_{i:02d}", value not in visible_text, value)

tables = [e for e in new_slide.iter() if e.tag.split("}")[-1] == "table"]
add("new_slide_has_one_native_table", len(tables) == 1)
if tables:
    rows = [e for e in tables[0] if e.tag.split("}")[-1] == "tr"]
    add("new_slide_table_has_six_rows", len(rows) == 6)
    for i, row in enumerate(rows, start=1):
        cells = [e for e in row if e.tag.split("}")[-1] == "td"]
        add(f"new_slide_table_row_{i}_has_five_cells", len(cells) == 5)

notes = [e for e in new_slide if e.tag.split("}")[-1] == "note"]
add("new_slide_has_speaker_notes", len(notes) == 1)
if notes:
    paragraphs = [e for e in notes[0].iter() if e.tag.split("}")[-1] == "p"]
    note_text = "\n".join("".join(p.itertext()) for p in paragraphs)
    add("new_slide_notes_have_four_paragraphs", len(paragraphs) == 4)
    for key, value in {
        "full_spearman_effect": "-0.00425098585966277",
        "full_mse_effect": "-0.005428627465626112",
        "full_spearman_ci": "[-0.05520539205719149, 0.04633584918114156]",
        "full_mse_ci": "[-0.08960370674454726, 0.07676584869175301]",
        "rk_g1_remains_false": "RK-G1 仍为 false",
        "not_universal_structure_falsification": "普遍 RNA 结构证伪",
    }.items():
        add(f"new_slide_notes_{key}", value in note_text)

add("new_slide_has_no_undefined_objects", not any(e.tag.split("}")[-1] == "undefined" for e in new_slide.iter()))
for element in new_slide.iter():
    if element.tag.split("}")[-1] in {"shape", "table", "img", "icon", "embed"}:
        x = float(element.get("topLeftX", "0")); y = float(element.get("topLeftY", "0"))
        w = float(element.get("width", "0")); h = float(element.get("height", "0"))
        add(f"new_slide_{element.get('id')}_within_canvas", x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540, [x, y, w, h])

status = "PASS_RK02_STRUCTURE_PPT_ONLINE_READBACK" if all(c["pass"] for c in checks) else "FAIL_RK02_STRUCTURE_PPT_ONLINE_READBACK"
report = {
    "schema": "a8.rk02.structure_ppt_online_readback.v1",
    "status": status,
    "checks_passed": sum(c["pass"] for c in checks),
    "checks_total": len(checks),
    "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
    "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
    "baseline_revision": 61,
    "final_revision": readback_response.get("data", {}).get("revision_id"),
    "baseline_pages": len(before),
    "final_pages": len(after),
    "new_slide_id": new_slide.get("id"),
    "new_slide_number": 100,
    "prior_slides_semantic_xml_unchanged": 99,
    "candidate_sha256": sha("candidate-v1.xml"),
    "baseline_xml_sha256": sha("baseline99.xml"),
    "readback_xml_sha256": sha("readback100.xml"),
    "add_response_sha256": sha("add-response-v1.json"),
    "readback_response_sha256": sha("readback100-response.json"),
    "candidate_fact_check_sha256": sha("candidate-fact-check.json"),
    "production_sha256": sha("evidence/production.json"),
    "independent_sha256": sha("evidence/independent.json"),
    "finalization_sha256": sha("evidence/finalization.json"),
    "paper_verification_sha256": sha("evidence/paper-verification.json"),
    "scientific_result": finalization["scientific_result"],
    "scope": "One online page appended after live baseline and candidate fact verification; no prior slide changed.",
    "checks": checks,
}
(ROOT / "ppt-online-readback-v1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: report[k] for k in ("status", "checks_passed", "checks_total", "final_pages", "final_revision", "new_slide_id", "prior_slides_semantic_xml_unchanged")}, ensure_ascii=False, indent=2))
if not status.startswith("PASS"):
    for c in checks:
        if not c["pass"]:
            print("FAILED", c)
    raise SystemExit(1)
