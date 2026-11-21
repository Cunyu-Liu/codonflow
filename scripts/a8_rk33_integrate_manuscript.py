#!/usr/bin/env python3
"""Insert the accepted RK33 section without changing any pre-existing manuscript byte outside the insertion."""
from pathlib import Path
import argparse
import hashlib
import json


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--section", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    original = args.original.read_text()
    section = args.section.read_text().strip() + "\n\n"
    marker = "## 7. Discussion\n"
    if original.count(marker) != 1:
        raise ValueError("Expected exactly one Discussion marker")
    if "### 6.44 " in original:
        raise ValueError("RK33 section already present")
    prefix, suffix = original.split(marker)
    if not prefix.endswith("\n\n"):
        prefix += "\n"
    updated = prefix + section + marker + suffix
    # Removing exactly the inserted span must recover the source manuscript exactly.
    recovered = updated[:len(prefix)] + updated[len(prefix) + len(section):]
    if recovered != original:
        raise AssertionError("Non-insertion manuscript content changed")
    if updated.count("### 6.44 ") != 1 or updated.count("Table 21.") != 1 or updated.count("Table 22.") != 1:
        raise AssertionError("Section/table insertion count mismatch")
    args.output.write_text(updated)
    report = {
        "status": "PASS",
        "original_sha256": hashlib.sha256(args.original.read_bytes()).hexdigest(),
        "section_sha256": hashlib.sha256(args.section.read_bytes()).hexdigest(),
        "updated_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "original_bytes": args.original.stat().st_size,
        "section_bytes": len(section.encode()),
        "updated_bytes": args.output.stat().st_size,
        "non_insertion_content_preserved_exactly": True,
        "discussion_marker_preserved": True,
        "section_count": updated.count("### 6.44 "),
        "table_21_count": updated.count("Table 21."),
        "table_22_count": updated.count("Table 22."),
        "manuscript_status": "non_submittable_working_draft",
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
