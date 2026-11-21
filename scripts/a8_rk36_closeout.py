#!/usr/bin/env python3
"""RK36 closeout: verify the full feasibility-audit + pivot chain is consistent
and complete (protocol/result/independent/manuscript/PPT/tests + commits + gates)."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git_exists(commit: str) -> bool:
    r = subprocess.run(["git", "cat-file", "-t", commit], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "commit"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    A = Path("audits/20261122/RK36")
    proto = Path("configs/a8_rk36_independent_transport_feasibility_protocol_v1.json")
    result = A / "rk36_feasibility_result_v1.json"
    indep = A / "rk36_feasibility_independent_v1.json"
    integ = A / "rk36_manuscript_integration_v1.json"
    review = A / "rk36_manuscript_review_v1.json"
    ppt = A / "ppt_v1/rk36_ppt_audit_v1.json"
    tests = A / "rk36_final_project_tests_cb528983.json"
    manuscript = Path("paper/CodonFlow_preprint_A8.md")
    res = json.loads(result.read_text())
    ind = json.loads(indep.read_text())
    itg = json.loads(integ.read_text())
    rvw = json.loads(review.read_text())
    pp = json.loads(ppt.read_text())
    ts = json.loads(tests.read_text())
    tsum = ts.get("summary", ts)
    mtext = manuscript.read_text()
    checks = []

    def ck(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    files = {"protocol": proto, "result": result, "independent": indep, "integration": integ,
             "review": review, "ppt_audit": ppt, "tests": tests}
    shas = {}
    for k, p in files.items():
        ck(f"file_exists_{k}", p.exists())
        if p.exists():
            shas[k] = sha256(p)
    ck("result_n_qualifying_zero", res["n_qualifying_datasets"] == 0)
    ck("result_branch_3_pivot", res["branch_decision"] == "branch_3_no_qualifying_data_trigger_branch_2_pivot")
    ck("result_label_free", res["label_free"] is True)
    ck("result_four_datasets", len(res["datasets"]) == 4)
    ck("result_missing_dims", len(res["missing_dimensions"]) == 6)
    ck("result_pivot_rk37", "candidate_next_task_RK37" in res["pivot_plan"] and "RiboMIMO" in res["pivot_plan"]["candidate_next_task_RK37"])
    ck("result_gates", res["pivot_plan"]["gates"] == {"RK_G1": False, "generative_training_authorized": False, "functional_untouched_readable": False})
    ck("independent_pass_24_24", ind["status"] == "PASS" and ind["checks_passed"] == 24 == ind["checks_total"])
    ck("integration_pass_12_12", itg["status"] == "PASS" and itg["checks_passed"] == 12 == itg["checks_total"])
    ck("review_pass_32_32", rvw["status"] == "PASS" and rvw["checks_passed"] == 32 == rvw["checks_total"])
    ck("ppt_pass_23_23", pp["status"] == "PASS" and pp["checks_passed"] == 23 == pp["checks_total"])
    ck("tests_455_1_0", tsum.get("passed") == 455 and tsum.get("failed") == 0 and tsum.get("skipped") == 1)
    ck("manuscript_sec_6_47", "### 6.47" in mtext and "#sec-6-47" in mtext and "**Table 27**" in mtext)
    ck("manuscript_sha_match_review", sha256(manuscript) == rvw["manuscript_sha256"])
    ck("result_sha_match_independent", sha256(result) == ind["result_sha256"])
    for name, c in [("freeze", "7942d6a93b0df5fbb6e33a1bc8c8426e70a2353d"),
                    ("science", "eca9171d2f28e30a62a6052ff30450eaccdee051"),
                    ("manuscript", "cb528983b400b6a5aa780ae4fe8ee58cb1874b98")]:
        ck(f"commit_exists_{name}", git_exists(c))
    ck("ppt_pages_170_173", pp["pages"] == {"pSL": 170, "pSy": 171, "pSC": 172, "pSx": 173})

    report = {
        "schema": "a8-rk36-closeout-v1",
        "status": "PASS_BOUNDED_FEASIBILITY_PIVOT_CLOSEOUT" if all(c["pass"] for c in checks) else "FAIL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Label-free independent-transport feasibility audit + branch-3 record + branch-2 pivot trigger; no transport effect, SOTA, mechanism, functional/protein OOD, generator or wet-lab claim.",
        "artifact_sha256": shas,
        "manuscript_sha256": sha256(manuscript),
        "commits": {"freeze": "7942d6a93b0df5fbb6e33a1bc8c8426e70a2353d",
                    "science": "eca9171d2f28e30a62a6052ff30450eaccdee051",
                    "manuscript": "cb528983b400b6a5aa780ae4fe8ee58cb1874b98"},
        "ppt": {"presentation_id": "WB1KsYGualerMUddEzMcCw1En0g", "pages": pp["pages"], "revision": 145, "total_pages": 173},
        "gates": {"RK_G1": False, "generative_training_authorized": False, "functional_untouched_readable": False},
        "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "checks": checks,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.report.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tmp.replace(args.report)
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if not all(c["pass"] for c in checks):
        print(json.dumps([c for c in checks if not c["pass"]], indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()