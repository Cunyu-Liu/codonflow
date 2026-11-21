#!/usr/bin/env python3
"""Prepare bounded RK35 slide corrections from a live full-deck snapshot."""
from pathlib import Path
import argparse
import hashlib
import json
import re
from xml.sax.saxutils import escape

CHANGES = {
    "pSw": [
        ("STRUCTURE ARMS", "EVALUATED ARMS", 1),
        ("Six structure arms share one 154-sequence panel; three arms are new and two are reused from RK32 to keep the comparison fair.",
         "Six evaluated arms, including the null intercept, share one 154-sequence panel; three arms are new and two are reused from RK32 to keep the comparison fair.", 1),
    ],
    "pSN": [
        ("Natural window retains the increment; coverage is not necessary", "Natural window retains the increment within Kudla", 1),
        ("Supported: natural RK33 window CDS[3:45] carries the Kudla increment without ATG/UTR; coverage loss cannot solely explain RK28/RK33 negatives.",
         "Supported: natural RK33 window CDS[3:45] retains a Kudla increment without ATG/UTR; cross-study mechanisms remain unidentified.", 1),
        ("C1 4 / 4 · C2 2 / 4 · HOST / ASSAY / STUDY-LEVEL FACTORS NOW PRIMARY CANDIDATES",
         "C1 4 / 4 · C2 2 / 4 · HOST / ASSAY / STUDY EFFECTS REMAIN UNIDENTIFIED", 1),
        ("Decision D1: coverage is not necessary within Kudla retrospectively; host, assay and study-level factors become the primary candidates.",
         "Decision D1 supports retained incremental signal for the truncated window within Kudla; host, assay and study-level factors remain candidates rather than identified causes.", 1),
        ("<p>—</p>", "<p>10/10</p>", 2),
    ],
    "pSt": [
        ("The CDS-start and dangles-0 arms sit between simple and exact, consistent with a coverage gradient rather than a single necessary element.",
         "The CDS-start and dangles-0 arms have descriptive intermediate scores; body and coverage shifts prevent a mechanistic gradient claim.", 1),
    ],
    "pSX": [
        ("Boundary: same-cohort Kudla-retrospective diagnostic, not independent confirmation. RK34 ends window ablation; independent-validation / pivot decision pending user. RK-G1=false.",
         "Boundary: within-Kudla retrospective; not independent confirmation. Next: independent complete-CDS validation or pivot; no more window ablation. RK-G1=false.", 1),
        ("This is a same-cohort retrospective diagnostic, not independent confirmation; the prompt makes RK34 the end of window ablation, so the independent-validation versus pivot decision is left to the user.",
         "This is a same-cohort retrospective diagnostic, not independent confirmation; the next gate is independent complete-CDS validation or a data-supported pivot, not another same-cohort window ablation.", 1),
    ],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    raw = args.source.read_text()
    namespace = re.search(r'<presentation\b[^>]*\bxmlns="([^"]+)"', raw).group(1)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for sid in ["pSw", "pSl", "pSN", "pSt", "pSX"]:
        match = re.search(r'<slide\b[^>]*\bid="' + re.escape(sid) + r'"[^>]*>.*?</slide>', raw, re.S)
        assert match, sid
        xml = match.group(0)
        original = xml
        if "xmlns=" not in xml.split(">", 1)[0]:
            xml = xml.replace("<slide ", '<slide xmlns="' + namespace + '" ', 1)
        applied = []
        for old, new, count in CHANGES.get(sid, []):
            old_xml = old if old.startswith("<p>") else escape(old)
            new_xml = new if new.startswith("<p>") else escape(new)
            actual = xml.count(old_xml)
            assert actual == count, (sid, old, actual, count)
            xml = xml.replace(old_xml, new_xml)
            applied.append({"old": old, "new": new, "count": count})
        path = args.output_dir / ("rk35_" + sid + ".xml")
        path.write_text(xml)
        records.append({"slide_id": sid, "path": str(path), "source_sha256": hashlib.sha256(original.encode()).hexdigest(),
                        "candidate_sha256": sha(path), "changed": xml != original, "changes": applied})
    manifest = {"status": "GENERATED_NOT_ONLINE", "source": str(args.source), "source_sha256": sha(args.source), "slides": records}
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"], "slides": [{"id": r["slide_id"], "changes": len(r["changes"])} for r in records]}, indent=2))


if __name__ == "__main__":
    main()
