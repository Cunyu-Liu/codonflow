#!/usr/bin/env python3
"""Bind the RK28 manuscript, science, slide, and pushed commits without mutable-head fields."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

SCIENCE_COMMIT = "71d27dd7610559c2781849c2be7b2a26933c3d0e"
SCIENCE_CLOSEOUT_COMMIT = "868cdb1d47d71c1a266d783628e047d41ba007e0"
PPT_COMMIT = "fb2c907eb068da4417bdee85449c08afa7466186"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(repo, *args, bytes_output=False):
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return result.stdout if bytes_output else result.stdout.decode().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manuscript-commit", required=True)
    for name in ["closeout", "manuscript-verification", "postpush-report", "update-report", "status", "result", "independent", "science-closeout", "slide-online", "slide-candidate", "slide-response", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    closeout = args.closeout.read_text()
    verification = json.loads(args.manuscript_verification.read_text())
    postpush = json.loads(args.postpush_report.read_text())
    update = json.loads(args.update_report.read_text())
    writing_status = json.loads(args.status.read_text())
    result = json.loads(args.result.read_text())
    independent = json.loads(args.independent.read_text())
    science_closeout = json.loads(args.science_closeout.read_text())
    slide_online = json.loads(args.slide_online.read_text())
    slide_candidate = json.loads(args.slide_candidate.read_text())
    slide_response = json.loads(args.slide_response.read_text())
    checks = []

    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})

    check("manuscript commit is full hash", len(args.manuscript_commit) == 40 and git(args.repo, "cat-file", "-t", args.manuscript_commit) == "commit")
    for label, commit in [("manuscript", args.manuscript_commit), ("science", SCIENCE_COMMIT), ("science closeout", SCIENCE_CLOSEOUT_COMMIT), ("PPT", PPT_COMMIT)]:
        check(label + " commit ancestor of HEAD", subprocess.run(["git", "-C", str(args.repo), "merge-base", "--is-ancestor", commit, "HEAD"]).returncode == 0)
        check(label + " commit present on origin/a8-rk", subprocess.run(["git", "-C", str(args.repo), "merge-base", "--is-ancestor", commit, "origin/a8-rk"]).returncode == 0)
    check("manuscript verification 92/92", verification["status"] == "PASS" and verification["checks_total"] == verification["checks_passed"] == 92 and all(item["pass"] for item in verification["checks"]))
    check("postpush verification 92/92", postpush["status"] == "PASS" and postpush["checks_total"] == postpush["checks_passed"] == 92)
    check("postpush report byte identical", args.postpush_report.read_bytes() == args.manuscript_verification.read_bytes())
    check("postpush manuscript hash", postpush["manuscript_sha256"] == verification["manuscript_sha256"])
    check("old manuscript exact", verification["old_manuscript_preserved_exactly"] is True and update["old_manuscript_reconstruction_exact"] is True)
    check("insertion-only update", update["insertion_only"] is True and update["evidence_row_count"] == 12)
    check("Markdown-only workflow PASS", writing_status["status"] == "PASS" and writing_status["stage"] == "deliver")
    check("single-section not whole-paper claim", verification["mode"] == "draft" and verification["output_target"] == "markdown_only")
    check("verification binds status", verification["status_sha256"] == sha(args.status))
    check("verification binds update", verification["update_report_sha256"] == sha(args.update_report))
    check("verification binds science result", verification["result_sha256"] == sha(args.result))
    check("verification binds independent report", verification["independent_sha256"] == sha(args.independent))
    check("science independent 54/54", independent["status"] == "PASS" and independent["n_checks"] == independent["n_passed"] == 54)
    check("science closeout 101/101", science_closeout["status"] == "PASS" and science_closeout["n_checks"] == science_closeout["n_passed"] == 101)
    check("slide candidate 256/256", slide_candidate["status"] == "PASS" and slide_candidate["n_checks"] == slide_candidate["n_passed"] == 256 and all(item["pass"] for item in slide_candidate["checks"]))
    check("slide online 624/624", slide_online["status"] == "PASS" and slide_online["n_checks"] == slide_online["n_passed"] == 624 and all(item["pass"] for item in slide_online["checks"]))
    check("slide pZC", slide_online["new_slide_id"] == slide_response["data"]["slide_id"] == "pZC")
    check("slide revision 83", slide_response["ok"] is True and slide_response["data"]["revision_id"] == 83)
    check("slide old pages preserved", slide_online["old_pages_preserved"] is True)
    check("slide binds science and closeout", slide_online["science_commit"] == SCIENCE_COMMIT and slide_online["closeout_commit"] == SCIENCE_CLOSEOUT_COMMIT)
    check("slide binds result and independent", slide_online["result_sha256"] == sha(args.result) and slide_online["independent_report_sha256"] == sha(args.independent))
    check("candidate and online bind same XML", slide_candidate["candidate_sha256"] == slide_online["candidate_sha256"])
    check("science scope remains retrospective cross-study observed-R1", result["analysis_type"] == "retrospective_cross_study_fixed_gfp_observed_r1_structure_increment_sequence_cluster_transport_validation")
    check("science conclusion remains not supported", result["scientific_conclusion"] == "FIXED_GFP_HEK293_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED")
    check("no RK-G1 or generator authorization", result["scientific_flags"]["rk_g1_complete"] is False and result["scientific_flags"]["generator_training_authorized"] is False and result["scientific_flags"]["functional_untouched_read"] is False)
    expected_files = {
        "paper/CodonFlow_preprint_A8.md",
        "scripts/a8_rk28_update_manuscript.py",
        "scripts/a8_rk28_verify_manuscript.py",
        *{"audits/20261121/RK28/" + name for name in [
            "rk28_manuscript_before_v1.md", "rk28_manuscript_console_v1.log", "rk28_manuscript_deliver_console_v1.log",
            "rk28_manuscript_draft_check_v1.json", "rk28_manuscript_final_v1.md", "rk28_manuscript_meta_v1.json",
            "rk28_manuscript_prepare_check_v1.json", "rk28_manuscript_prepare_console_v1.log", "rk28_manuscript_section_v1.md",
            "rk28_manuscript_status_v1.json", "rk28_manuscript_update_v1.json", "rk28_manuscript_verification_v1.json",
            "rk28_manuscript_write_console_v1.log"
        ]},
    }
    commit_files = set(git(args.repo, "diff-tree", "--no-commit-id", "--name-only", "-r", args.manuscript_commit).splitlines())
    check("manuscript commit contains exactly 16 scoped files", commit_files == expected_files and len(commit_files) == 16)
    check("no pre-existing handover modifications committed", "docs/handover/tasks.md" not in commit_files and "docs/handover/A8_RK_tasks.md" not in commit_files)
    committed_manuscript = git(args.repo, "show", args.manuscript_commit + ":paper/CodonFlow_preprint_A8.md", bytes_output=True)
    check("committed manuscript hash", hashlib.sha256(committed_manuscript).hexdigest() == verification["manuscript_sha256"])
    current_manuscript = (args.repo / "paper/CodonFlow_preprint_A8.md").read_bytes()
    check("current manuscript hash unchanged", hashlib.sha256(current_manuscript).hexdigest() == verification["manuscript_sha256"])
    required_tokens = [
        args.manuscript_commit, SCIENCE_COMMIT, SCIENCE_CLOSEOUT_COMMIT, PPT_COMMIT,
        verification["manuscript_sha256"], verification["section_sha256"], verification["update_report_sha256"],
        sha(args.manuscript_verification), sha(args.status), result["scientific_conclusion"],
        "92/92 PASS", "54/54 PASS", "101/101 PASS", "256/256 PASS", "624/624 PASS", "603 词",
        "post-push 复验", "字节一致", "pZC", "revision 83", "12 条 RK28 证据行",
        "逐字节恢复原 RK27 稿件", "finish_with_status", "不证明整篇可提交",
        "RK-G1 仍为 false", "昂贵生成训练未授权", "functional untouched 未评价",
        "不是独立 untouched 或 protein OOD 确认", "未测量结构、velocity、decay 或完整空间耦合",
        "non-submittable working manuscript", "前 119 页", "只追加一次",
        "/home/codonflow-a8-rk/paper/CodonFlow_preprint_A8.md", "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk28/mordstein_observed_r1_sequence_cluster_ood_v1/",
    ]
    for token in required_tokens:
        check("closeout contains " + token, token in closeout)
    failed = [item["name"] for item in checks if not item["pass"]]
    report = {
        "schema": "a8-rk28-manuscript-closeout-verification-v1",
        "status": "PASS" if not failed else "FAIL",
        "manuscript_commit": args.manuscript_commit,
        "science_commit": SCIENCE_COMMIT,
        "science_closeout_commit": SCIENCE_CLOSEOUT_COMMIT,
        "ppt_commit": PPT_COMMIT,
        "manuscript_sha256": verification["manuscript_sha256"],
        "section_sha256": verification["section_sha256"],
        "manuscript_verification_sha256": sha(args.manuscript_verification),
        "postpush_verification_sha256": sha(args.postpush_report),
        "update_report_sha256": sha(args.update_report),
        "writing_status_sha256": sha(args.status),
        "science_result_sha256": sha(args.result),
        "independent_report_sha256": sha(args.independent),
        "science_closeout_report_sha256": sha(args.science_closeout),
        "slide_online_report_sha256": sha(args.slide_online),
        "slide_candidate_report_sha256": sha(args.slide_candidate),
        "slide_response_sha256": sha(args.slide_response),
        "closeout_sha256": sha(args.closeout),
        "postpush_byte_identical": args.postpush_report.read_bytes() == args.manuscript_verification.read_bytes(),
        "committed_file_count": len(commit_files),
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed),
        "failed_checks": failed,
        "checks": checks,
        "rk_g1": False,
        "generator_training_authorized": False,
        "functional_untouched_evaluated": False,
        "whole_manuscript_submittable": False,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: report[key] for key in ["status", "checks_total", "checks_passed", "failed_checks", "manuscript_commit", "closeout_sha256"]}, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
