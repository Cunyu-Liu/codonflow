#!/usr/bin/env python3
"""Insert RK34 before RK35 when present, preserving every pre-existing byte."""
from pathlib import Path
import argparse
import hashlib
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--section", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    original = args.original.read_text()
    section = args.section.read_text().strip() + "\n\n"
    if "### 6.45 " in original:
        raise ValueError("RK34 section already present")
    markers = [marker for marker in ("### 6.46 ", "## 7. Discussion\n") if marker in original]
    if len(markers) != 1:
        raise ValueError("Expected either RK35 section or Discussion marker")
    marker = markers[0]
    marker_index = original.index(marker)
    prefix, suffix = original[:marker_index], original[marker_index:]
    if not prefix.endswith("\n\n"):
        prefix += "\n"
    updated = prefix + section + suffix
    recovered = updated[:len(prefix)] + updated[len(prefix) + len(section):]
    if recovered != original:
        raise AssertionError("Non-insertion manuscript content changed")
    if updated.count("### 6.45 ") != 1 or updated.count("**Table 23**") != 1 or updated.count("**Table 24**") != 1:
        raise AssertionError("Section/table insertion count mismatch")
    args.output.write_text(updated)
    report = {"status": "PASS", "original_sha256": hashlib.sha256(args.original.read_bytes()).hexdigest(), "section_sha256": hashlib.sha256(args.section.read_bytes()).hexdigest(), "updated_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), "original_bytes": args.original.stat().st_size, "section_bytes": len(section.encode()), "updated_bytes": args.output.stat().st_size, "non_insertion_content_preserved_exactly": True, "inserted_before": "RK35" if marker.startswith("### 6.46") else "Discussion", "rk35_preserved": original.count("### 6.46 ") == updated.count("### 6.46 "), "manuscript_status": "non_submittable_working_draft"}
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
