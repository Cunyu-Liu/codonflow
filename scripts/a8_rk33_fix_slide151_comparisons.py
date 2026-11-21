#!/usr/bin/env python3
"""Expand the twelve comparison labels on slide 151 without altering IDs or numerical results."""
from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
text = args.input.read_text()
counts = {}
for old, new in [("−simple", "local42−simple"), ("−full1", "local42−full1"), ("−full3", "local42−full3")]:
    needle = f"<p>{old}</p>"
    counts[old] = text.count(needle)
    if counts[old] != 4:
        raise SystemExit(f"Expected four cells for {old}, found {counts[old]}")
    text = text.replace(needle, f"<p>{new}</p>")
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(text)
print({"replacements": counts, "output": str(args.output)})
