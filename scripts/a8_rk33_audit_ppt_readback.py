#!/usr/bin/env python3
"""Closed-loop audit for one RK33 slide: add response, live readback, text, tables, notes and bounds."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def paragraphs(root, container):
    nodes = []
    for data in root.findall(f".//{{*}}{container}"):
        for p in data.findall(".//{*}p"):
            nodes.append("".join(p.itertext()))
    return nodes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--readback", type=Path, required=True)
    p.add_argument("--add-response", type=Path, required=True)
    p.add_argument("--read-response", type=Path, required=True)
    p.add_argument("--page", type=int, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    source = ET.parse(args.source).getroot()
    live = ET.parse(args.readback).getroot()
    add = json.loads(args.add_response.read_text())
    read = json.loads(args.read_response.read_text())
    checks = []

    def check(name, ok, details):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    sid = add.get("data", {}).get("slide_id")
    check("add_business_success", add.get("ok") is True and bool(sid), {"ok": add.get("ok"), "slide_id": sid, "revision_id": add.get("data", {}).get("revision_id")})
    check("read_business_success", read.get("ok") is True and read.get("data", {}).get("slide_id") == sid, {"ok": read.get("ok"), "slide_id": read.get("data", {}).get("slide_id"), "revision_id": read.get("data", {}).get("revision_id")})
    check("single_slide", live.tag.endswith("slide"), live.tag)
    check("no_undefined", not live.findall(".//{*}undefined"), len(live.findall(".//{*}undefined")))
    source_text, live_text = paragraphs(source, "data"), paragraphs(live, "data")
    check("visible_text_exact", source_text == live_text, {"source_paragraphs": len(source_text), "live_paragraphs": len(live_text), "source": source_text, "live": live_text})
    source_notes, live_notes = paragraphs(source, "note"), paragraphs(live, "note")
    check("speaker_notes_exact", source_notes == live_notes and 3 <= len(live_notes) <= 5, {"source": source_notes, "live": live_notes})
    source_tables = [{"rows": len(t.findall("{*}tr")), "cols": sum(int(c.attrib.get("span", "1")) for c in t.findall("{*}colgroup/{*}col"))} for t in source.findall(".//{*}table")]
    live_tables = [{"rows": len(t.findall("{*}tr")), "cols": sum(int(c.attrib.get("span", "1")) for c in t.findall("{*}colgroup/{*}col"))} for t in live.findall(".//{*}table")]
    check("table_shapes_exact", source_tables == live_tables, {"source": source_tables, "live": live_tables})
    bounds = []
    data = live.find(".//{*}data")
    if data is not None:
        for element in list(data):
            try:
                x, y = float(element.attrib["topLeftX"]), float(element.attrib["topLeftY"])
                w, h = float(element.attrib["width"]), float(element.attrib["height"])
            except (KeyError, ValueError):
                continue
            bounds.append({"tag": element.tag, "id": element.attrib.get("id"), "x": x, "y": y, "width": w, "height": h, "inside": x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540})
    check("all_positioned_elements_inside_canvas", bool(bounds) and all(b["inside"] for b in bounds), bounds)
    check("page_number_visible", str(args.page) in live_text, {"page": args.page})
    report = {
        "schema": "a8-rk33-slide-readback-audit-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "page": args.page,
        "slide_id": sid,
        "add_revision_id": add.get("data", {}).get("revision_id"),
        "read_revision_id": read.get("data", {}).get("revision_id"),
        "checks": checks,
        "checks_passed": sum(c["pass"] for c in checks),
        "checks_total": len(checks),
        "failed_checks": [c["name"] for c in checks if not c["pass"]],
        "source_sha256": digest(args.source),
        "readback_sha256": digest(args.readback),
        "add_response_sha256": digest(args.add_response),
        "read_response_sha256": digest(args.read_response),
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "page": args.page, "slide_id": sid, "checks": f'{report["checks_passed"]}/{report["checks_total"]}', "failed": report["failed_checks"]}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
