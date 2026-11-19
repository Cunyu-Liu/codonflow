#!/usr/bin/env python3
"""Independently verify one appended RK06 slide and preservation of every old page."""
import argparse, hashlib, json
from pathlib import Path
import xml.etree.ElementTree as ET

MARKER = "RK06 · UNIQUE18 REAL DENSE-BUDGET SEARCH"
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text())
def slides(root): return [e for e in list(root) if e.tag.rsplit("}", 1)[-1] == "slide"]
def text(root): return "\n".join("".join(p.itertext()) for p in root.iter() if p.tag.rsplit("}", 1)[-1] == "p")
def semantic(e):
    attrs = dict(e.attrib)
    attrs.pop("id", None)
    # Slides service materializes col/row span=1; this default has no semantic effect.
    if attrs.get("span") == "1": attrs.pop("span")
    return (e.tag, tuple(sorted(attrs.items())), (e.text or "").strip(), (e.tail or "").strip(),
            tuple(semantic(c) for c in list(e)))

def main():
    ap = argparse.ArgumentParser()
    for name in ["baseline-xml", "baseline-response", "candidate-xml", "candidate-report", "add-response", "postwrite-xml", "postwrite-response", "output"]:
        ap.add_argument("--" + name, required=True)
    a = ap.parse_args()
    baseline = ET.parse(a.baseline_xml).getroot()
    candidate = ET.parse(a.candidate_xml).getroot()
    current = ET.parse(a.postwrite_xml).getroot()
    base_pages, new_pages = slides(baseline), slides(current)
    base_resp, add_resp, post_resp = load(a.baseline_response), load(a.add_response), load(a.postwrite_response)
    preflight = load(a.candidate_report)
    checks = []
    def check(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
    check("baseline_response_ok", base_resp.get("ok") is True)
    check("add_response_ok", add_resp.get("ok") is True)
    check("postwrite_response_ok", post_resp.get("ok") is True)
    check("candidate_preflight_pass", preflight.get("status") == "PASS" and all(c.get("passed") for c in preflight.get("checks", [])))
    check("candidate_unchanged_since_preflight", sha(a.candidate_xml) == preflight.get("candidate_sha256"), sha(a.candidate_xml))
    check("exactly_one_page_appended", len(new_pages) == len(base_pages) + 1, {"before": len(base_pages), "after": len(new_pages)})
    mismatches = []
    for i, (before, after) in enumerate(zip(base_pages, new_pages), 1):
        if semantic(before) != semantic(after): mismatches.append(i)
    check("all_preexisting_pages_semantically_preserved", not mismatches, mismatches)
    new_id = add_resp.get("data", {}).get("slide_id")
    check("new_slide_id_matches_response", bool(new_id) and new_pages[-1].attrib.get("id") == new_id,
          {"response": new_id, "readback": new_pages[-1].attrib.get("id") if new_pages else None})
    check("new_slide_is_last", text(new_pages[-1]).count(MARKER) == 1 if new_pages else False)
    check("marker_occurs_exactly_once_in_deck", text(current).count(MARKER) == 1)
    check("new_page_semantically_matches_candidate", bool(new_pages) and semantic(candidate) == semantic(new_pages[-1]))
    check("candidate_visible_text_preserved", bool(new_pages) and text(candidate) == text(new_pages[-1]))
    check("candidate_note_preserved", bool(new_pages) and "108,000" in text(new_pages[-1]) and "不使 manuscript 可提交" in text(new_pages[-1]))
    base_rev = base_resp.get("data", {}).get("revision_id")
    add_rev = add_resp.get("data", {}).get("revision_id")
    post_rev = post_resp.get("data", {}).get("revision_id")
    check("revision_advanced", isinstance(base_rev, int) and isinstance(add_rev, int) and isinstance(post_rev, int) and add_rev > base_rev and post_rev >= add_rev,
          {"baseline": base_rev, "add": add_rev, "postwrite": post_rev})
    check("postwrite_scope_is_presentation", post_resp.get("data", {}).get("scope") == "presentation")
    forbidden = ["ssh -p ", "mailto:root@", "ControlPath="]
    joined = text(current)
    check("no_connection_or_credential_material", not any(s in joined for s in forbidden))
    report = {"status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
              "baseline_slide_count": len(base_pages), "postwrite_slide_count": len(new_pages), "new_slide_id": new_id,
              "baseline_revision_id": base_rev, "add_revision_id": add_rev, "postwrite_revision_id": post_rev,
              "baseline_xml_sha256": sha(a.baseline_xml), "candidate_xml_sha256": sha(a.candidate_xml),
              "postwrite_xml_sha256": sha(a.postwrite_xml), "preexisting_page_mismatches": mismatches, "checks": checks}
    Path(a.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": len(checks), "slides": [len(base_pages), len(new_pages)],
                      "new_slide_id": new_id, "revision": [base_rev, add_rev, post_rev], "mismatches": mismatches}, indent=2))
    if report["status"] != "PASS": raise SystemExit(1)
if __name__ == "__main__": main()
