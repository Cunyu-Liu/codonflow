#!/usr/bin/env python3
"""Idempotently insert or refresh the independently validated RK39 section."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RK39 = ROOT / "audits/20261122/RK39"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    production_path = RK39 / "rk39_common_input_actual_set_v1.json"
    independent_path = RK39 / "rk39_common_input_actual_set_independent_v1.json"
    clean_path = RK39 / "rk39_common_input_actual_set_clean_v1.json"
    closeout_path = RK39 / "rk39_clean_reproduction_closeout_v1.json"
    protocol_path = ROOT / "configs/a8_rk39_common_input_actual_set_protocol_v1.json"
    manuscript_source = RK39 / "manuscript_workflow_v1/paper_final.md"
    draft_check = load(RK39 / "manuscript_workflow_v1/draft_check.json")
    assert draft_check["status"] == "pass"
    word_count = int(draft_check["result"]["word_count"])

    production = load(production_path)
    independent = load(independent_path)
    clean = load(clean_path)
    closeout = load(closeout_path)
    assert production["decision"] == clean["decision"] == "COMMON_INPUT_ACTUAL_SET_TASK_UNRESOLVED"
    assert independent["status"] == "PASS"
    assert independent["n_pass"] == independent["n_checks"] == 1216
    assert closeout["status"] == "PASS"
    assert closeout["n_pass"] == closeout["n_checks"] == 830

    source = manuscript_source.read_text().strip()
    lines = source.splitlines()
    assert lines[0] == "# Common-Input Actual-Set Evaluation"
    body = "\n".join(lines[1:]).strip()
    heading = (
        "### 6.50 Matched-cardinality simple search remained far behind "
        "LinearDesign-11 under common protein input"
    )
    anchor = f"""::: {{.evidence-anchor #sec-6-50}}
| Field | Evidence |
|---|---|
| Code commit | `b3f89b948b707a56e9ae9ab8e9726a5fa0acaa41` |
| Protocol | `configs/a8_rk39_common_input_actual_set_protocol_v1.json`; SHA256 `{sha(protocol_path)}` |
| Production | `audits/20261122/RK39/rk39_common_input_actual_set_v1.json`; 162 runs and 1,782 calls; SHA256 `{sha(production_path)}` |
| Independent | `rk39_common_input_actual_set_independent_v1.json`; 1216/1216 PASS; maximum objective error 0.0; SHA256 `{sha(independent_path)}` |
| Clean reproduction | `rk39_common_input_actual_set_clean_v1.json`; SHA256 `{sha(clean_path)}`; pointwise closeout 830/830 PASS, SHA256 `{sha(closeout_path)}` |
| Manuscript workflow | {word_count}-word isolated section; prepare/write/deliver PASS; source SHA256 `{sha(manuscript_source)}` |
| Artifacts | `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk39/common_input_actual_set_v1/` and `common_input_actual_set_clean_v1/` |
| Tests | 477 passed, 1 skipped, 5 subtests passed |
| Scope | Common-protein, fixed-TAA, actual-cardinality proxy evaluation; unresolved task; no superiority, external SOTA, time-matched, functional, protein-OOD, untouched, generator, wet-lab, RK-G1, or submittable-manuscript claim |
:::"""
    section = heading + "\n\n" + body + "\n\n" + anchor

    paper = ROOT / "paper/CodonFlow_preprint_A8.md"
    text = paper.read_text()
    marker = "## 7. Discussion"
    assert text.count(marker) == 1
    references = text[text.index("## 9. References") :]
    if "### 6.50 " in text:
        assert text.count("### 6.50 ") == 1
        start = text.index("### 6.50 ")
        end = text.index(marker, start)
        updated = text[:start] + section + "\n\n" + text[end:]
    else:
        updated = text.replace(marker, section + "\n\n" + marker)
    assert updated[updated.index("## 9. References") :] == references
    for token in (
        "-29.714618",
        "[-41.925699, -19.552535]",
        "-0.066598",
        "0.169577",
        "1216",
        "830",
        "COMMON_INPUT_ACTUAL_SET_V1",
        "Positive records are counted from record-level effects after seed averaging.",
    ):
        assert token in section, token
    paper.write_text(updated)
    print(
        json.dumps(
            {
                "status": "PASS",
                "manuscript_lines": len(updated.splitlines()),
                "manuscript_sha256": hashlib.sha256(updated.encode()).hexdigest(),
                "section_sha256": hashlib.sha256(section.encode()).hexdigest(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
