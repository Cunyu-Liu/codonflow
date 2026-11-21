#!/usr/bin/env python3
"""Verify RK40 evidence, reporting, documentation, and explicit open boundaries."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

EXPECTED = {
    "production": "fedfa32097232106e33e1107d7c2244b0b57939697899d828b40dda72c622187",
    "independent": "ae5b90d0ac3c5890194834f2c8c9bf8ffdb221ce1b7c86ec98ff9d52656897df",
    "clean_closeout": "7ddf1dab2bfaa92e603f0743b0ee0d06a6372f9a972c6985abe24ead957a11f4",
    "manuscript": "7a0a6dee54ff7e6c04199fb9b96671cecb8f4b3e8c762586a756bded44f6b1c2",
}
COMMITS = [
    "1c3dfc77d5b18e637852b1d3c57a7bf10a880e29",
    "71cbf8cf900c83810260c144e970710223524c5c",
    "aec5051f4cd3af374f3936fa5067e1dbe11f4458",
    "9b2eef793c639ce348a91f37f73e60612149c926",
    "339cf23ef71cd7f4952b7102fdca79665baf1c27",
    "20d7001e60fdc18d53dbcc42beef2be6331a7268",
]
FALSE_BOUNDARIES = [
    "scientific_gate_passed", "external_sota_authorized", "time_matched_comparison",
    "functional_untouched_evaluated", "rk_g1_pass", "manuscript_submittable",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    audit = root / "audits/20261122/RK40"
    paths = {
        "production": audit / "rk40_budget_initialization_v1.json",
        "independent": audit / "rk40_budget_initialization_independent_v1.json",
        "clean_closeout": audit / "rk40_clean_reproduction_closeout_v1.json",
        "manuscript": root / "paper/CodonFlow_preprint_A8.md",
    }
    docs = {
        "registry": root / "experiments/REGISTRY.md",
        "tasks": root / "tasks.md",
        "handoff": root / "docs/handover/HANDOFF_A8_RK40_20261122.md",
    }
    loaded = {key: json.loads(path.read_text()) for key, path in paths.items() if path.suffix == ".json"}
    manuscript_closeout = json.loads((audit / "rk40_manuscript_closeout_v1.json").read_text())
    ppt_closeout = json.loads((audit / "rk40_ppt_closeout.json").read_text())
    checks = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"check": name, "pass": bool(condition), "detail": detail})

    for key, path in paths.items():
        actual = sha256(path)
        check(f"sha256_{key}", actual == EXPECTED[key], {"expected": EXPECTED[key], "actual": actual})
    check("production_status", loaded["production"]["status"] == "PASS_COMPLETE_MECHANISM_EVALUATION" and loaded["production"]["decision"] == "NORMALIZATION_AND_SHORT_BUDGET_BOTH_CONTRIBUTE", {"status": loaded["production"]["status"], "decision": loaded["production"]["decision"]})
    check("independent_5031", loaded["independent"]["n_pass"] == loaded["independent"]["n_checks"] == 5031, {"n_pass": loaded["independent"]["n_pass"], "n_checks": loaded["independent"]["n_checks"]})
    check("clean_948", loaded["clean_closeout"]["n_pass"] == loaded["clean_closeout"]["n_checks"] == 948, {"n_pass": loaded["clean_closeout"]["n_pass"], "n_checks": loaded["clean_closeout"]["n_checks"]})
    check("primary_families", all(loaded["production"]["primary_family_pass"].values()) and len(loaded["production"]["primary_family_pass"]) == 2, loaded["production"]["primary_family_pass"])
    for source_name, report in [("production", loaded["production"]), ("independent", loaded["independent"]), ("clean", loaded["clean_closeout"]), ("ppt", ppt_closeout)]:
        check(f"{source_name}_open_boundaries", all(report.get(key) is False for key in FALSE_BOUNDARIES), {key: report.get(key) for key in FALSE_BOUNDARIES})
    check("manuscript_closeout", manuscript_closeout["status"] == "PASS" and len(manuscript_closeout["checks"]) == 7 and all(manuscript_closeout["checks"].values()), {"status": manuscript_closeout["status"], "n_checks": len(manuscript_closeout["checks"])})
    check("ppt_revision_and_ids", ppt_closeout["status"] == "PASS" and ppt_closeout["final_revision"] == 170 and ppt_closeout["appended_slide_ids"] == ["pSQ", "pSu", "pSk", "pSE", "pSK", "pSm"], {"status": ppt_closeout["status"], "final_revision": ppt_closeout["final_revision"], "slide_ids": ppt_closeout["appended_slide_ids"]})
    check("ppt_old_pages_protected", ppt_closeout["preexisting_192_slides_semantically_unchanged"] is True, ppt_closeout["preexisting_192_slides_semantically_unchanged"])
    check("ppt_visual_review", len(ppt_closeout["pages"]) == 6 and all(item["online_visual_status"] == "PASS" and all(item["online_visual_checks"].values()) for item in ppt_closeout["pages"]), {"n_reviews": len(ppt_closeout["pages"])})

    registry = docs["registry"].read_text()
    rk40_rows = [line for line in registry.splitlines() if line.startswith("| RK40 |")]
    check("registry_single_rk40", len(rk40_rows) == 1, {"n_rows": len(rk40_rows)})
    row = rk40_rows[0] if rk40_rows else ""
    for token_name, token in [
        ("registry_decision", "NORMALIZATION_AND_SHORT_BUDGET_BOTH_CONTRIBUTE"),
        ("registry_independent", "independent5031/5031"),
        ("registry_clean", "clean948/948"),
        ("registry_paper_sha", EXPECTED["manuscript"]),
        ("registry_ppt", "PPT193-198"),
        ("registry_open_gate", "common-input/external SOTA/time-matched/functional untouched/protein OOD/RK-G1/manuscript submittable remain false"),
    ]:
        check(token_name, token in row, token)
    tasks = docs["tasks"].read_text()
    task_section = tasks.split("## RK40 ·", 1)[1] if "## RK40 ·" in tasks else ""
    check("tasks_completion_counts", task_section.count("- [x]") == 7 and task_section.count("- [ ]") == 2, {"checked": task_section.count("- [x]"), "open": task_section.count("- [ ]")})
    check("tasks_next_is_not_claimed_closed", "下一项必须产生新判别证据" in task_section and "尚未" not in task_section.split("下一项必须产生新判别证据", 1)[-1].split("不得", 1)[0], "next task remains open")
    handoff = docs["handoff"].read_text()
    for token_name, token in [
        ("handoff_decision", "NORMALIZATION_AND_SHORT_BUDGET_BOTH_CONTRIBUTE"),
        ("handoff_not_reversed", "RK39 的共同输入 actual-set 失败没有被逆转"),
        ("handoff_cli", "--production-independent"),
        ("handoff_external_boundary", "不能算作独立 CodonFlow 设计"),
        ("handoff_next_not_frozen", "该方向尚未冻结"),
    ]:
        check(token_name, token in handoff, token)
    for commit in COMMITS:
        result = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", commit, "HEAD"], capture_output=True)
        check(f"ancestor_{commit[:8]}", result.returncode == 0, {"commit": commit, "returncode": result.returncode})
    for relative in [
        "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk40/budget_initialization_v1",
        "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk40/budget_initialization_clean_v1",
        "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk40/ppt_v1",
        "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk40/full_pytest_v1.log",
    ]:
        check(f"asset_{Path(relative).name}", Path(relative).exists(), relative)

    n_pass = sum(item["pass"] for item in checks)
    report = {
        "protocol_id": "RK40_BUDGET_INITIALIZATION_V1",
        "status": "PASS" if n_pass == len(checks) else "FAIL",
        "n_checks": len(checks), "n_pass": n_pass,
        "checks": checks,
        "documentation_commit": "current_commit_containing_this_report",
        "head_before_documentation_commit": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
        "scientific_gate_passed": False,
        "external_sota_authorized": False,
        "time_matched_comparison": False,
        "functional_untouched_evaluated": False,
        "rk_g1_pass": False,
        "manuscript_submittable": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "n_pass": n_pass, "n_checks": len(checks), "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
