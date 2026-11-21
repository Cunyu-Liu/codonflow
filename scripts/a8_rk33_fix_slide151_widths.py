#!/usr/bin/env python3
"""Widen the live slide-151 comparison column while preserving every assigned element ID."""
from pathlib import Path
import argparse
import re

parser = argparse.ArgumentParser()
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
text = args.input.read_text()
widths = [130, 76, 82, 104, 206, 74, 84, 108]
replacement = "<colgroup>" + "".join(f'<col span="1" width="{w}"/>' for w in widths) + "</colgroup>"
updated, count = re.subn(r"<colgroup>.*?</colgroup>", replacement, text, count=1, flags=re.DOTALL)
if count != 1:
    raise SystemExit(f"Expected exactly one table colgroup, found {count}")
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(updated)
print({"input": str(args.input), "output": str(args.output), "columns": widths, "total_width": sum(widths)})
