#!/usr/bin/env python3
"""Independently close RK39 scientific, manuscript, PPT, and documentation evidence."""
import argparse
import ast
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audits/20261122/RK39"
EXPECTED = {
    "production": "b9882da074040176b71eb86b37245b8bab438bb71ffe80ea796498f57916f2d1",
    "independent": "824b07b985efb98a7cfd3cf025f27472dfbc669c4de665674e51ff8dfaf4f185",
    "clean": "0f24145a78faf563ef8e45867d811b038a943983e526bc1a94c065c4c4dcef78",
    "clean_closeout": "a5695d6fffb2b3a37118c8b3e74c7705f9e44d0c5be5ef7fc8c17eed52065ca0",
    "manuscript": "611a0ceec7adb305fdfb47f6ac2566b37c2e500ffd8210a49835e3d0439230bf",
    "ppt_xml": "570ee5c6ec9ccbf709b860e0476e12a349ef217facd9016d8a567ce774ddea7a",
}


def load(name):
    return json.loads((AUDIT / name).read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--expected-head")
    args = parser.parse_args()
    checks = []

    def check(name, ok, detail=None):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    files = {
        "production": AUDIT / "rk39_common_input_actual_set_v1.json",
        "independent": AUDIT / "rk39_common_input_actual_set_independent_v1.json",
        "clean": AUDIT / "rk39_common_input_actual_set_clean_v1.json",
        "clean_closeout": AUDIT / "rk39_clean_reproduction_closeout_v1.json",
        "manuscript": ROOT / "paper/CodonFlow_preprint_A8.md",
    }
    reports = {k: json.loads(p.read_text()) for k, p in files.items() if k != "manuscript"}
    for key, path in files.items():
        check(f"sha256_{key}", sha(path) == EXPECTED[key], sha(path))
    prod = reports["production"]
    independent = reports["independent"]
    clean = reports["clean"]
    clean_close = reports["clean_closeout"]
    check("production_decision", prod["decision"] == "COMMON_INPUT_ACTUAL_SET_TASK_UNRESOLVED")
    for key in ("primary_gate_passed", "scientific_gate_passed"):
        check(f"production_{key}_false", prod[key] is False)
    check("clean_decision", clean["decision"] == prod["decision"])
    check("independent_1216", independent["n_pass"] == independent["n_checks"] == 1216 and independent["status"] == "PASS")
    check("independent_sequence_recompute", independent["n_unique_sequences_independently_rescored"] == 1594 and independent["max_objective_abs_error"] == 0.0)
    check("clean_closeout_830", clean_close["n_pass"] == clean_close["n_checks"] == 830 and clean_close["status"] == "PASS")
    tests = next(t for t in prod["tests"] if t["method"] == "hill_climbing" and t["endpoint"] == "hypervolume_normalized" and t["confirmatory"])
    check("production_162_runs", prod["n_runs"] == 162 and prod["n_unique_scorer_calls"] == 1782)
    check("production_primary_effect", math.isclose(tests["effect"], -29.71461778089193, rel_tol=0, abs_tol=1e-14))
    check("production_primary_ci", tests["ci95"] == [-41.92569883799738, -19.552535077886407])
    check("production_primary_holm", tests["holm_p"] == 9.99950002499875e-05)
    check("production_primary_direction", not any(x > 0 for x in tests["per_record_effects"]) and not any(x > 0 for x in tests["seed_mean_effects"]))
    records = prod["per_record"]
    external_hv = sum(x["external"]["hypervolume_normalized"] for x in records) / len(records)
    external_ned = sum(x["external"]["pairwise_ned"] for x in records) / len(records)
    check("linear_design_absolute", math.isclose(external_hv, 29.972887490261744, abs_tol=1e-14) and math.isclose(external_ned, 0.07128928032706872, abs_tol=1e-15))
    hill_values = [v for x in records for v in x["methods"]["hill_climbing"].values()]
    hill_hv = sum(x["hypervolume_normalized"] for x in hill_values) / len(hill_values)
    hill_ned = sum(x["pairwise_ned"] for x in hill_values) / len(hill_values)
    check("hill_absolute", math.isclose(hill_hv, 0.258269709369807, abs_tol=1e-15) and math.isclose(hill_ned, 0.004691579884140756, abs_tol=1e-16))
    log = (AUDIT / "rk39_full_pytest.log").read_text()
    check("full_pytest", "477 passed" in log and "1 skipped" in log and "5 subtests passed" in log and re.search(r"\b[1-9]\d* failed", log) is None)
    manuscript = files["manuscript"].read_text()
    check("manuscript_section_and_tables", len(manuscript.splitlines()) == 2154 and "6.50" in manuscript and "Table 32" in manuscript and "Table 33" in manuscript)
    for name in ("A8_RK39_PREREGISTRATION.md",):
        check(f"preregistration_{name}", (AUDIT / name).is_file())
    for name in ("a8_rk39_common_input_actual_set.py", "a8_rk39_verify_common_input.py", "a8_rk39_compare_clean.py", "a8_rk39_integrate_manuscript.py", "a8_rk39_build_ppt_page.py", "a8_rk39_audit_ppt_page.py"):
        path = ROOT / "scripts" / name
        try:
            ast.parse(path.read_text())
            ok = True
        except (OSError, SyntaxError):
            ok = False
        check(f"script_syntax_{name}", ok)
    registry = (ROOT / "experiments/REGISTRY.md").read_text()
    tasks = (ROOT / "tasks.md").read_text()
    handoff = ROOT / "docs/handover/HANDOFF_A8_RK39_20261122.md"
    check("registry_rk39", "| RK39 |" in registry and "done_rk39_common_input_actual_set_dual_negative" in registry)
    check("tasks_rk39", "RK39 共同输入、固定 TAA" in tasks and "科学任务仍未解决" in tasks)
    check("handoff_rk39", handoff.is_file() and "COMMON_INPUT_ACTUAL_SET_TASK_UNRESOLVED" in handoff.read_text())
    ppt = load("rk39_ppt_closeout.json")
    check("ppt_closeout_status", ppt["status"] == "PASS" and ppt["slide_count"] == 192 and ppt["revision_id"] == 164)
    check("ppt_page_identity", [p["page"] for p in ppt["pages"]] == [187, 188, 189, 190, 191, 192] and [p["slide_id"] for p in ppt["pages"]] == ["pSA", "pSr", "pSH", "pSd", "pSb", "pSF"])
    check("ppt_audit_total", ppt["audit_totals"] == {"n_pass": 421, "n_checks": 421} and sum(int(p["preupload_audit"].split("/")[0]) for p in ppt["pages"]) == 421)
    check("ppt_old_pages_protected", ppt["prior_186_slides_structure_attrs_text_exact_match"] is True and ppt["final_xml_sha256"] == EXPECTED["ppt_xml"])
    artifact_root = Path(ppt["artifact_root"])
    check("ppt_artifact_root", str(artifact_root) == "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk39/ppt_v1")
    check("ppt_final_xml_archived", (artifact_root / "rk39_final.xml").is_file() and sha(artifact_root / "rk39_final.xml") == EXPECTED["ppt_xml"])
    for page in ppt["pages"]:
        number = page["page"]
        check(f"ppt_{number}_screenshot_archived", Path(page["screenshot"]).is_file())
        check(f"ppt_{number}_online_xml_archived", (artifact_root / f"rk39_{number}_online.xml").is_file())
        response = json.loads((artifact_root / f"rk39_{number}_add_response.json").read_text())
        check(f"ppt_{number}_write_response", response.get("ok") is True)
    for name in ("rk39_common_input_actual_set_v1.json", "rk39_common_input_actual_set_independent_v1.json", "rk39_common_input_actual_set_clean_v1.json", "rk39_clean_reproduction_closeout_v1.json", "rk39_full_pytest.log"):
        check(f"ppt_evidence_{name}", (artifact_root / "evidence" / name).is_file())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    origin = subprocess.check_output(["git", "rev-parse", "origin/a8-rk"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    if args.expected_head:
        check("expected_head", head == args.expected_head, head)
    if args.require_clean:
        check("head_equals_origin", head == origin, {"head": head, "origin": origin})
        check("worktree_clean", not dirty, dirty)
    result = {
        "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
        "n_checks": len(checks),
        "n_pass": sum(c["passed"] for c in checks),
        "checks": checks,
        "head": head,
        "origin_a8_rk": origin,
        "require_clean": args.require_clean,
        "scientific_decision": prod["decision"],
        "scientific_gate_passed": False,
        "external_sota_authorized": False,
        "time_matched_comparison": False,
        "functional_untouched_evaluated": False,
        "rk_g1_pass": False,
        "manuscript_submittable": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({k: result[k] for k in ("status", "n_checks", "n_pass", "head", "origin_a8_rk", "scientific_decision")}))
    if result["status"] != "PASS":
        for item in checks:
            if not item["passed"]:
                print("FAIL", item)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
