#!/usr/bin/env python3
"""Verify the RK03 source-feasibility documentation closeout without network or writes to science evidence."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "audits/20261120/RK03"
OUT = A / "source_feasibility_closeout_verification_v1.json"


def load(name):
    return json.loads((A / name).read_text())


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    production = load("source_feasibility_v1.json")
    independent = load("source_feasibility_independent_v1.json")
    finalization = load("source_feasibility_finalization_v1.json")
    paper = load("source_feasibility_paper_verification_v27.json")
    candidate = load("source_feasibility_ppt_candidate_verification_v1.json")
    postwrite = load("source_feasibility_ppt_postwrite_verification_v1.json")
    write_response = load("source_feasibility_ppt_write_response_v1.json")

    docs = {
        "README.md": ROOT / "README.md",
        "docs/handover/tasks.md": ROOT / "docs/handover/tasks.md",
        "docs/handover/HANDOFF_A8_RK_20261118.md": ROOT / "docs/handover/HANDOFF_A8_RK_20261118.md",
        "experiments/REGISTRY.md": ROOT / "experiments/REGISTRY.md",
    }
    text = {name: path.read_text() for name, path in docs.items()}
    checks = []

    def check(name, condition, evidence=None):
        checks.append({"check": name, "pass": bool(condition), "evidence": evidence})

    check("production_74_of_74", production["check_counts"] == {"total": 74, "passed": 74, "failed": 0})
    check("independent_169_of_169", independent["check_counts"] == {"total": 169, "passed": 169, "failed": 0})
    check("independent_exact", independent["production_independent_max_numeric_delta"] == 0)
    check("finalization_47_of_47", finalization["check_counts"] == {"total": 47, "passed": 47, "failed": 0})
    check("bounded_only_closed", finalization["bounded_source_feasibility_closed"] is True)
    check("rk_g1_remains_open", finalization["rk_g1_closed"] is False)
    check("generator_remains_unauthorized", finalization["expensive_generator_training_authorized"] is False)
    check("manuscript_remains_unsubmittable", finalization["manuscript_submittable"] is False)
    check("no_read_download", production["large_read_files_downloaded"] == [])
    check("no_utr_cds", production["boundaries"]["utr_cds_mapping_completed"] is False)
    check("no_raw_remap", production["boundaries"]["raw_read_remapping_completed"] is False)
    check("terminal_scope", production["status"] == "SOURCE_METADATA_RECOVERABLE_REMAP_NOT_PERFORMED")
    check("scientific_outcome", finalization["scientific_outcome"] == "PUBLIC_SOURCE_RECOVERY_FEASIBLE_BUT_NOT_REMAPPED")

    velo = production["veloharmo_organism_feasibility"]
    ribo_extra = [row for row in production["ribomimo_raw_feasibility"] if row["label"] != "Mohammad16"]
    runinfo = production["runinfo_evidence"]
    velo_runs = sum(row["raw_source"]["run_count"] for row in velo)
    velo_mb = sum(row["raw_source"]["size_mb"] for row in velo)
    extra_runs = sum(row["raw_source"]["run_count"] for row in ribo_extra)
    extra_mb = sum(row["raw_source"]["size_mb"] for row in ribo_extra)
    unique_runs = sum(row["run_count"] for row in runinfo.values())
    unique_mb = sum(row["size_mb"] for row in runinfo.values())
    check("veloharmo_totals", (velo_runs, velo_mb) == (125, 143663), {"runs": velo_runs, "size_MB": velo_mb})
    check("ribomimo_extra_totals", (extra_runs, extra_mb) == (13, 9236), {"runs": extra_runs, "size_MB": extra_mb})
    check("distinct_runinfo_totals", (len(runinfo), unique_runs, unique_mb) == (7, 138, 152899), {"accessions": len(runinfo), "runs": unique_runs, "size_MB": unique_mb})
    check("only_ecoli_matrix", sum(row["released_harmonized_matrix_in_pinned_repo"] for row in velo) == 1)
    check("four_matrices_absent", sum(not row["released_harmonized_matrix_in_pinned_repo"] for row in velo) == 4)
    check("fourteen_pinned_files", len(production["pinned_repository"]["files"]) == 14)
    mapping = {row["label"]: (row["organism"], row["source_accession"]) for row in velo}
    check("dunn13_corrected", mapping["Dunn13"] == ("Drosophila melanogaster", "GSE49197"))
    check("pop14_corrected", mapping["Pop14"] == ("Saccharomyces cerevisiae", "GSE63789"))

    paper_path = ROOT / "paper/CodonFlow_preprint_A8.md"
    check("paper_61_of_61", paper["checks_passed"] == 61 and paper["checks_total"] == 61)
    check("paper_facts_30_of_30", paper["candidate_facts_passed"] == 30 and paper["candidate_facts_total"] == 30)
    check("paper_v26_recovery", paper["v26_recovery_verified"] is True)
    check("paper_hash_current", sha256(paper_path) == paper["paper_sha256"] == "c745b3e73b7d9f380f7c0ce326cc5fba2cfae769273b2e58f606a73dba9e0952")
    check("paper_not_submittable", paper["submittable"] is False)
    check("ppt_candidate_35_of_35", candidate["check_counts"] == {"total": 35, "passed": 35, "failed": 0})
    check("ppt_postwrite_47_of_47", postwrite["check_counts"] == {"total": 47, "passed": 47, "failed": 0})
    check("ppt_page_identity", postwrite["postwrite"] == {"new_slide_id": "pgM", "new_page_number": 103, "revision_id": 65})
    check("ppt_write_succeeded", write_response["ok"] is True)
    check("ppt_initial_failure_retained", load("source_feasibility_ppt_postwrite_initial_failed_v1.json")["check_counts"]["failed"] == 1)
    check("ppt_normalization_bounded", postwrite["xml_normalization"] == "Only schema-default col@span=1 and server-assigned IDs are normalized in the new-page semantic comparison; text, table values, geometry and all other attributes remain strict.")

    required = {
        "README.md": [
            "74/74 PASS", "169/169 PASS", "47/47 PASS", "61/61 PASS", "35/35 PASS",
            "pgM", "revision 65", "138 runs、152,899 MB", "不是本轮下载量",
            "SOURCE_METADATA_RECOVERABLE_REMAP_NOT_PERFORMED", "不关闭四物种 harmonization",
            "a8_rk03_verify_source_feasibility_closeout.py",
        ],
        "docs/handover/tasks.md": [
            "2026-11-20 RK03 Ribo/VeloHARMO source-feasibility increment",
            "125 runs、143,663 MB", "13 runs、9,236 MB", "138 runs、152,899 MB",
            "dc567587aa9b3a1db67be0fcebcd26fdf450e16a", "不构建 UTR–CDS",
        ],
        "docs/handover/HANDOFF_A8_RK_20261118.md": [
            "## 30. Ribo/VeloHARMO metadata-only 来源可行性与 A8 v27",
            "## 31. Source-feasibility 在线 PPT 第 103 页与写后验收",
            "103 页、revision 65、末页 `pgM`", "不得重复追加本页",
            "c0fd2b32a4919734747214ae06336efb67e03dcd", "c5046b9c25a700f6231f0411b95f4d881dcda5d8",
            "dc567587aa9b3a1db67be0fcebcd26fdf450e16a",
        ],
        "experiments/REGISTRY.md": [
            "CF-A8-RK03-SOURCE-FEASIBILITY", "CF-A8-RK18-WORKING-MANUSCRIPT-V27",
            "CF-A8-RK03-SOURCE-FEASIBILITY-PPT", "done_metadata_only_not_remapped_not_rk_g1",
        ],
    }
    for name, needles in required.items():
        for needle in needles:
            check(f"documentation_{name}_{needle}", needle in text[name])

    check("tasks_increment_unique", text["docs/handover/tasks.md"].count("2026-11-20 RK03 Ribo/VeloHARMO source-feasibility increment") == 1)
    check("handoff_science_section_unique", text["docs/handover/HANDOFF_A8_RK_20261118.md"].count("## 30. Ribo/VeloHARMO metadata-only 来源可行性与 A8 v27") == 1)
    check("handoff_ppt_section_unique", text["docs/handover/HANDOFF_A8_RK_20261118.md"].count("## 31. Source-feasibility 在线 PPT 第 103 页与写后验收") == 1)
    for run_id in ["CF-A8-RK03-SOURCE-FEASIBILITY", "CF-A8-RK18-WORKING-MANUSCRIPT-V27", "CF-A8-RK03-SOURCE-FEASIBILITY-PPT"]:
        check(f"registry_unique_{run_id}", text["experiments/REGISTRY.md"].count(f"| {run_id} |") == 1)
    check("mage_handoff_retained", "## 29. MAGE nested-development 在线 PPT 记录与写后验收" in text["docs/handover/HANDOFF_A8_RK_20261118.md"])
    check("ribomimo_tasks_retained", "2026-11-19 RK05 RiboMIMO cross-study OOD increment" in text["docs/handover/tasks.md"])
    check("mage_readme_retained", "第 102 页（`pgj`，revision 64）" in text["README.md"])

    for commit in [
        "c0fd2b32a4919734747214ae06336efb67e03dcd",
        "c5046b9c25a700f6231f0411b95f4d881dcda5d8",
        "dc567587aa9b3a1db67be0fcebcd26fdf450e16a",
    ]:
        result = subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=ROOT, check=False)
        check(f"evidence_commit_ancestor_{commit}", result.returncode == 0)

    ok = all(row["pass"] for row in checks)
    report = {
        "schema": "a8_rk03_source_feasibility_closeout_verification_v1",
        "status": "PASS" if ok else "FAIL",
        "overall_pass": ok,
        "network_used": False,
        "online_ppt_modified": False,
        "check_counts": {"total": len(checks), "passed": sum(row["pass"] for row in checks), "failed": sum(not row["pass"] for row in checks)},
        "recomputed_totals": {
            "veloharmo": {"runs": velo_runs, "size_MB": velo_mb},
            "ribomimo_extra": {"runs": extra_runs, "size_MB": extra_mb},
            "distinct_runinfo": {"accessions": len(runinfo), "runs": unique_runs, "size_MB": unique_mb},
        },
        "document_sha256": {name: sha256(path) for name, path in docs.items()},
        "paper_sha256": sha256(paper_path),
        "ppt": postwrite["postwrite"],
        "scope": "Documentation/registry closeout only; metadata-level source feasibility remains bounded and is not raw-read/P-site remapping, mechanism validation, RK-G1 closure, generator authorization, or a submittable manuscript.",
        "checks": checks,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "check_counts": report["check_counts"], "ppt": report["ppt"]}, indent=2))
    if not ok:
        for row in checks:
            if not row["pass"]:
                print("FAILED", row["check"], row.get("evidence"))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
