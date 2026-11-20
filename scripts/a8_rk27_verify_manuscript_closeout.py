#!/usr/bin/env python3
"""Bind the RK27 manuscript, science, slide, and pushed commits without mutable-head fields."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

SCIENCE_COMMIT = "8a62836bb73b34bcae529bae6a21f6e3eefc85d1"
SCIENCE_CLOSEOUT_COMMIT = "95257f290062d0f7d1ad2ab7bab21eef0b485437"
PPT_COMMIT = "f827a549e988698448d5601f3fd869050633215e"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(repo, *args, bytes_output=False):
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return result.stdout if bytes_output else result.stdout.decode().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manuscript-commit", required=True)
    for name in ["closeout", "manuscript-verification", "postpush-report", "update-report", "status", "result", "independent", "science-closeout", "slide-online", "slide-binding", "slide-response", "output"]:
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
    slide_binding = json.loads(args.slide_binding.read_text())
    slide_response = json.loads(args.slide_response.read_text())
    checks = []

    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})

    check("manuscript commit is full hash", len(args.manuscript_commit) == 40 and git(args.repo, "cat-file", "-t", args.manuscript_commit) == "commit")
    for label, commit in [("manuscript", args.manuscript_commit), ("science", SCIENCE_COMMIT), ("science closeout", SCIENCE_CLOSEOUT_COMMIT), ("PPT", PPT_COMMIT)]:
        check(label + " commit ancestor of HEAD", subprocess.run(["git", "-C", str(args.repo), "merge-base", "--is-ancestor", commit, "HEAD"]).returncode == 0)
        check(label + " commit present on origin/a8-rk", subprocess.run(["git", "-C", str(args.repo), "merge-base", "--is-ancestor", commit, "origin/a8-rk"]).returncode == 0)
    check("manuscript verification 83/83", verification["status"] == "PASS" and verification["checks_total"] == verification["checks_passed"] == 83 and all(item["pass"] for item in verification["checks"]))
    check("postpush verification 83/83", postpush["status"] == "PASS" and postpush["checks_total"] == postpush["checks_passed"] == 83)
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
    check("science independent 47/47", independent["status"] == "PASS" and independent["n_checks"] == independent["n_passed"] == 47)
    check("science closeout 97/97", science_closeout["status"] == "PASS" and science_closeout["n_checks"] == science_closeout["n_passed"] == 97)
    check("slide online 57/57", slide_online["status"] == "PASS" and slide_online["n_checks"] == slide_online["n_passed"] == 57)
    check("slide binding 21/21", slide_binding["status"] == "PASS" and slide_binding["n_checks"] == slide_binding["n_passed"] == 21)
    check("slide pZy", slide_online["slide_id"] == slide_binding["slide_id"] == slide_response["data"]["slide_id"] == "pZy")
    check("slide revision 82", slide_response["ok"] is True and slide_response["data"]["revision_id"] == 82)
    check("science scope remains retrospective", result["analysis_type"] == "retrospective_fixed_protein_sequence_cluster_transport_validation")
    check("science conclusion remains supported", result["scientific_conclusion"] == "FIXED_PROTEIN_SEQUENCE_CLUSTER_OOD_MFE_INCREMENT_SUPPORTED_RETROSPECTIVELY")
    check("no RK-G1 or generator authorization", result["scientific_flags"]["RK_G1_complete"] is False and result["scientific_flags"]["generator_training_authorized"] is False and result["scientific_flags"]["functional_untouched_read"] is False)
    expected_files = {
        "paper/CodonFlow_preprint_A8.md",
        "scripts/a8_rk27_update_manuscript.py",
        "scripts/a8_rk27_verify_manuscript.py",
        *{"audits/20261121/RK27/" + name for name in [
            "rk27_manuscript_before_v1.md", "rk27_manuscript_console_v1.log", "rk27_manuscript_deliver_console_v1.log",
            "rk27_manuscript_draft_check_v1.json", "rk27_manuscript_final_v1.md", "rk27_manuscript_meta_v1.json",
            "rk27_manuscript_prepare_check_v1.json", "rk27_manuscript_prepare_console_v1.log", "rk27_manuscript_section_v1.md",
            "rk27_manuscript_status_v1.json", "rk27_manuscript_update_v1.json", "rk27_manuscript_verification_v1.json",
            "rk27_manuscript_write_console_v1.log", "rk27_manuscript_write_retry_console_v1.log"
        ]},
    }
    commit_files = set(git(args.repo, "diff-tree", "--no-commit-id", "--name-only", "-r", args.manuscript_commit).splitlines())
    check("manuscript commit contains exactly 17 scoped files", commit_files == expected_files and len(commit_files) == 17)
    check("no pre-existing handover modifications committed", "docs/handover/tasks.md" not in commit_files and "docs/handover/A8_RK_tasks.md" not in commit_files)
    committed_manuscript = git(args.repo, "show", args.manuscript_commit + ":paper/CodonFlow_preprint_A8.md", bytes_output=True)
    check("committed manuscript hash", hashlib.sha256(committed_manuscript).hexdigest() == verification["manuscript_sha256"])
    current_manuscript = (args.repo / "paper/CodonFlow_preprint_A8.md").read_bytes()
    check("current manuscript hash unchanged", hashlib.sha256(current_manuscript).hexdigest() == verification["manuscript_sha256"])
    required_tokens = [
        args.manuscript_commit, SCIENCE_COMMIT, SCIENCE_CLOSEOUT_COMMIT, PPT_COMMIT,
        verification["manuscript_sha256"], verification["section_sha256"], verification["update_report_sha256"],
        sha(args.manuscript_verification), sha(args.status), result["scientific_conclusion"],
        "83/83 PASS", "47/47 PASS", "97/97 PASS", "57/57 PASS", "21/21 PASS", "519 词",
        "post-push 复验", "字节一致", "pZy", "revision 82", "12 条 RK27 证据行",
        "逐字节恢复原 RK26 稿件", "finish_with_status", "ModuleNotFoundError: revision_guard",
        "不证明整篇可提交", "RK-G1 仍为 false", "昂贵生成训练未授权", "functional untouched 未评价",
        "不是独立 untouched 或 protein OOD 确认", "不测量 velocity、decay 或完整空间耦合",
        "non-submittable working manuscript", str(args.postpush_report),
    ]
    for token in required_tokens:
        check("closeout contains " + token, token in closeout)
    failed = [item["name"] for item in checks if not item["pass"]]
    report = {
        "schema": "a8-rk27-manuscript-closeout-verification-v1",
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
        "slide_binding_report_sha256": sha(args.slide_binding),
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
