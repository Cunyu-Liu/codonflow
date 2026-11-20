#!/usr/bin/env python3
"""Verify the RK21 slide candidate and its non-destructive online append."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
import xml.etree.ElementTree as ET

NS = "https://www.larkoffice.com/sml/2.0"
Q = "{" + NS + "}"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

def signature(node: ET.Element, note_text_only: bool = False):
    attrs = tuple(sorted((local(k), " ".join(v.split())) for k, v in node.attrib.items() if local(k) != "id"))
    if note_text_only and local(node.tag) == "content":
        attrs = ()
    text = " ".join((node.text or "").split())
    return (local(node.tag), attrs, text, tuple(signature(child, note_text_only) for child in node))

def texts(root: ET.Element):
    return [" ".join("".join(node.itertext()).split()) for node in root.iter() if local(node.tag) == "p"]

def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["candidate", "online"], required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--before")
    parser.add_argument("--after")
    parser.add_argument("--response")
    parser.add_argument("--slide-id")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    candidate_path = Path(args.candidate)
    candidate = ET.parse(candidate_path).getroot()
    checks = []
    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})
    visible = texts(candidate)
    joined = "\n".join(visible)
    check("single_slide_root", candidate.tag == Q + "slide")
    check("candidate_has_no_server_id", "id" not in candidate.attrib)
    check("no_hand_authored_element_ids", all("id" not in node.attrib for node in candidate.iter()))
    check("no_undefined_or_external_media", all(local(node.tag) not in {"undefined", "img", "embed"} for node in candidate.iter()))
    bounds = []
    for node in candidate.iter():
        if local(node.tag) not in {"shape", "table", "line", "img", "icon", "embed"}:
            continue
        try:
            x, y = float(node.attrib["topLeftX"]), float(node.attrib["topLeftY"])
            w, h = float(node.attrib["width"]), float(node.attrib["height"])
            bounds.append(x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540)
        except (KeyError, ValueError):
            bounds.append(False)
    check("all_elements_inside_960x540", all(bounds), len(bounds))
    check("title_exact", "Kudla recovery yields 154 measurements, 150 exact CDS" in visible)
    for token in ["154", "150", "72", "69 / 69"]:
        check(f"kpi_{token.replace(' ', '_')}", token in visible)
    for token in [
        "154 rows · 71 columns · 864 nt",
        "150 exact CDS · 4 duplicate pairs",
        "72 paired IDs · 62 source columns",
        "One 239-aa protein · expression 43–10606",
        "MFE + expression; no tagged sequence",
        "Sequence, expression and 5′ MFE exact",
    ]:
        check("fact_" + hashlib.sha256(token.encode()).hexdigest()[:8], token in visible, token)
    check("split_grouping_boundary", "Group identical CDS before every split" in visible)
    check("scientific_boundary", "No mechanism, OOD, untouched or SOTA result." in visible and "RK-G1 = false; generator training unauthorized." in visible)
    check("untouched_unread", "154 rows retained · 150 CDS groups mandatory · no tagged sequence imputed · functional untouched unread" in visible)
    check("source_and_commit", "Source: RK21 recovery audit 69/69 · Supek File S2 + PLOS S1 · commit 82c45436" in visible)
    check("page_label", "113 · RK21" in visible)
    table = candidate.find(".//" + Q + "table")
    check("table_5x3", table is not None and len(table.findall(Q + "tr")) == 5 and all(len(row.findall(Q + "td")) == 3 for row in table.findall(Q + "tr")))
    notes = candidate.findall(".//" + Q + "note//" + Q + "p")
    note_text = "\n".join(" ".join("".join(p.itertext()).split()) for p in notes)
    check("five_speaker_note_paragraphs", len(notes) == 5)
    for token in ["154 measurement rows", "150 unique exact CDS", "72 tagged pairs", "69 of 69 checks", "RK-G1 remains false"]:
        check("note_" + hashlib.sha256(token.encode()).hexdigest()[:8], token in note_text, token)
    visible_contents = candidate.findall(".//" + Q + "data//" + Q + "content")
    check("visible_font_sizes_explicit", all("fontSize" in node.attrib for node in visible_contents))
    check("font_family_consistent", all(node.attrib.get("fontFamily") == "Inter" for node in visible_contents))
    check("no_emoji", not any(ord(char) > 0xFFFF for char in joined + note_text))
    if args.phase == "online":
        before_path, after_path, response_path = Path(args.before), Path(args.after), Path(args.response)
        before_root = ET.parse(before_path).getroot()
        after_root = ET.parse(after_path).getroot()
        response = json.loads(response_path.read_text())
        before_slides = before_root.findall(Q + "slide")
        after_slides = after_root.findall(Q + "slide")
        check("online_response_ok", response.get("ok") is True)
        check("before_112_after_113", len(before_slides) == 112 and len(after_slides) == 113, [len(before_slides), len(after_slides)])
        check("new_slide_id_matches", after_slides[-1].get("id") == args.slide_id, after_slides[-1].get("id"))
        check("only_one_new_slide_id", sum(slide.get("id") == args.slide_id for slide in after_slides) == 1)
        check("revision_advanced", int(response.get("data", {}).get("revision_id", 0)) > 75, response.get("data", {}).get("revision_id"))
        old_equal = [signature(left, True) == signature(right, True) for left, right in zip(before_slides, after_slides[:112])]
        check("all_previous_112_pages_semantically_unchanged", all(old_equal), [index + 1 for index, value in enumerate(old_equal) if not value])
        check("online_new_page_matches_candidate", signature(after_slides[-1], True) == signature(candidate, True))
        online_text = texts(after_slides[-1])
        check("online_required_facts_present", all(token in online_text for token in ["154", "150", "72", "69 / 69", "MFE + expression; no tagged sequence"]))
        check("online_source_and_page_label", "113 · RK21" in online_text and any("commit 82c45436" in text for text in online_text))
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk21-ppt-verification-v1",
        "phase": args.phase,
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "candidate_sha256": sha(candidate_path),
        "before_sha256": sha(Path(args.before)) if args.before else None,
        "after_sha256": sha(Path(args.after)) if args.after else None,
        "slide_id": args.slide_id,
        "scientific_flags": {"mechanism_evaluated": False, "functional_ood_evaluated": False, "functional_untouched_evaluated": False, "rk_g1_pass": False, "sota_claimed": False},
    }
    write_json(Path(args.output), report)
    print(json.dumps({"status": report["status"], "checks_passed": passed, "checks_total": len(checks)}, indent=2))
    if passed != len(checks):
        for item in checks:
            if not item["pass"]:
                print("FAILED", item)
        raise SystemExit(1)

if __name__ == "__main__":
    main()
