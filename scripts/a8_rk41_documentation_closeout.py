#!/usr/bin/env python3
"""Independent documentation/evidence closeout for A8-RK41; stdlib only."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

ROOT = Path(os.environ.get("CODONFLOW_ROOT", "/home/codonflow-a8-rk"))
ARCHIVE = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk41")
OUT = ROOT / "audits/20261122/RK41/rk41_documentation_closeout_v1.json"
checks = []


def check(name, condition, detail=None):
    checks.append({"check": name, "passed": bool(condition), "detail": detail})


def load(rel):
    return json.loads((ROOT / rel).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    production_rel = "audits/20261122/RK41/rk41_internal_basin_initialization_v1.json"
    independent_rel = "audits/20261122/RK41/rk41_internal_basin_independent_v1.json"
    clean_rel = "audits/20261122/RK41/rk41_clean_reproduction_closeout_v1.json"
    manuscript_rel = "audits/20261122/RK41/rk41_manuscript_closeout_v1.json"
    ppt_rel = "audits/20261122/RK41/ppt_v1/rk41_research_deck_closeout_v1.json"
    p = load(production_rel)
    i = load(independent_rel)
    c = load(clean_rel)
    m = load(manuscript_rel)
    deck = load(ppt_rel)
    protocol = load("configs/a8_rk41_internal_basin_protocol_v1.json")
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    status = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).splitlines()
    allowed_exact = {
        "experiments/REGISTRY.md", "tasks.md", "docs/handover/HANDOFF_A8_RK41_20261122.md",
        "scripts/a8_rk41_documentation_closeout.py",
        "audits/20261122/RK41/rk41_documentation_closeout_v1.json",
    }
    changed = [line[3:] for line in status]
    check("expected_precloseout_head", head == "d8d1e40161246ca931f4dc8ca7007b678cba9782", head)
    check("only_documentation_changes", all(x in allowed_exact or x.startswith("audits/20261122/RK41/ppt_v1/") or x.startswith("audits/20261122/RK41/rk41_documentation_closeout") for x in changed), changed)
    check("protocol_identity", protocol["protocol_id"] == "RK41_INTERNAL_BASIN_INITIALIZATION_V1")
    check("protocol_sha", sha(ROOT / "configs/a8_rk41_internal_basin_protocol_v1.json") == "9ed2657dfe698bc096eb1e1fe853a723f26bd69dcd3b0bc768e4f946412dc83a")
    check("production_sha", sha(ROOT / production_rel) == "2e7ef6dd4ad079e2dea3f872116cd86dfdac3ffb9fb6163c78fffe9c531ccd58")
    check("production_coverage", (p["n_new_runs"], p["n_new_unique_scorer_calls"], p["n_accepted_rk40_runs"]) == (216, 2376, 108))
    check("production_decision", p["decision"] == "INTERNAL_MULTISTART_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED")
    check("production_gates", p["primary_gate_passed"] is False and p["common_input_actual_set_gate_passed"] is False and p["scientific_gate_passed"] is False)
    check("independent_sha", sha(ROOT / independent_rel) == "b402c4fd4899452173848ab823e442d778ea5257fae7b691a7725c73ee9abb7a")
    check("independent_all_pass", i["status"] == "PASS" and i["n_checks"] == i["n_pass"] == 5401)
    check("independent_full_trajectory", i["n_runs"] == 324 and i["n_raw_points"] == 3564 and i["n_new_runs_full_trajectory_reconstructed"] == 216)
    check("independent_rescoring", i["n_unique_sequences_independently_rescored"] == 1604 and i["max_objective_abs_error"] == 0.0)
    check("clean_closeout_sha", sha(ROOT / clean_rel) == "af5ad25801510d5c1fe42dbd442df8adccd8c487f1346cb579b46f8cee2845e9")
    check("clean_closeout_all_pass", c["status"] == "PASS" and c["n_checks"] == c["n_pass"] == 1114)
    check("clean_summary_binding", c["clean_sha256"] == "a03bbd660f6a5247e9a082050d7b5903ec3c81240621616cb08c461f8f8d5361")
    check("clean_summary_archived", sha(ARCHIVE / "internal_basin_clean_summary_v1.json") == c["clean_sha256"])
    test_log = ARCHIVE / "full_pytest_v1.log"
    test_text = test_log.read_text()
    check("full_project_tests", "494 passed, 1 skipped" in test_text and "5 subtests passed" in test_text)
    paper = ROOT / "paper/CodonFlow_preprint_A8.md"
    paper_text = paper.read_text()
    check("manuscript_sha", sha(paper) == "ed074226456026fa07ac82780cf1a0b235fba50572e6607931dfc4a12adf9ca6")
    check("manuscript_lines", len(paper_text.splitlines()) == 2228)
    check("manuscript_section", paper_text.count("### 6.52 Internal basin selection improves simple search but does not close the common-input actual-set gap") == 1)
    check("manuscript_tables", "**Table 36**" in paper_text and "**Table 37**" in paper_text)
    check("manuscript_closeout", m["status"] == "PASS" and m["n_checks"] == m["n_pass"] == 57)
    check("accepted_section", m["accepted_section_sha256"] == "b23ab94755546d67093d63924eef8aeae06ea21b8230a3d8b41d3e38f4144cca" and m["accepted_section_word_count"] == 599)
    check("ppt_closeout_all_pass", deck["status"] == "PASS" and deck["n_checks"] == deck["n_pass"] == 55)
    check("ppt_current", deck["current_slide_count"] == 204 and deck["current_revision"] == 176)
    check("ppt_prior_preservation", deck["prior_slides_exactly_preserved"] == 198)
    check("ppt_new_ids", [x["slide_id"] for x in deck["new_slides"]] == ["pSJ", "pSV", "pSs", "pST", "pSY", "pSv"])
    check("ppt_archive_current_sha", sha(ARCHIVE / "ppt_v1/rk41_current_v1.xml") == deck["current_xml_sha256"])
    check("ppt_archive_source_sha", sha(ARCHIVE / "ppt_v1/rk41_source_v1.xml") == deck["source_xml_sha256"])
    registry = (ROOT / "experiments/REGISTRY.md").read_text()
    tasks = (ROOT / "tasks.md").read_text()
    handoff = (ROOT / "docs/handover/HANDOFF_A8_RK41_20261122.md").read_text()
    check("registry_single_rk41", registry.count("| RK41 | 2026-11-22 |") == 1)
    check("registry_prior_rk40", registry.count("| RK40 | 2026-11-22 |") == 1)
    check("registry_decision_and_evidence", "done_rk41_internal_multistart_supported_common_input_task_unresolved" in registry and "independent5401/5401" in registry and "clean1114/1114" in registry)
    check("tasks_single_rk41", tasks.count("## RK41 · 内部盆地感知初始化与共同输入复核") == 1)
    check("tasks_scientific_boundary", "本轮只支持内部多起点盆地选择机制，未逆转 RK39 的共同输入 actual-set 失败" in tasks and "昂贵生成训练未授权，functional untouched 未读取，wet-lab 未执行" in tasks)
    check("handoff_identity", handoff.startswith("# HANDOFF · A8-RK41") and "INTERNAL_MULTISTART_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED" in handoff)
    check("handoff_results", "+0.0500296358" in handoff and "+0.7889522329" in handoff and "−29.2155200839" in handoff and "+0.1657640837" in handoff)
    check("handoff_reproduction", "5,401/5,401 PASS" in handoff and "1,114/1,114 PASS" in handoff and "494 passed / 1 skipped" in handoff)
    check("handoff_ppt", "204页/revision176" in handoff and "pSJ,pSV,pSs,pST,pSY,pSv" in handoff and "55/55 PASS" in handoff)
    check("handoff_open_gates", all(x in handoff for x in ["external SOTA", "time-matched", "functional/protein OOD", "RK-G1", "manuscript submittable"]))
    result = {
        "schema": "a8-rk41-documentation-closeout-v1", "precloseout_head": head,
        "decision": p["decision"], "primary_gate_passed": False,
        "common_input_actual_set_gate_passed": False, "scientific_gate_passed": False,
        "external_sota_authorized": False, "time_matched_comparison": False,
        "functional_untouched_evaluated": False, "rk_g1_pass": False,
        "manuscript_submittable": False,
        "manuscript_sha256": sha(paper), "ppt_current_xml_sha256": deck["current_xml_sha256"],
        "full_pytest_log_sha256": sha(test_log),
        "status": "PASS" if all(x["passed"] for x in checks) else "FAIL",
        "n_checks": len(checks), "n_pass": sum(x["passed"] for x in checks), "checks": checks,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({k: result[k] for k in ["status", "n_checks", "n_pass", "decision", "manuscript_sha256"]}, ensure_ascii=False))
    if result["status"] != "PASS":
        for item in checks:
            if not item["passed"]:
                print("FAIL", item)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
