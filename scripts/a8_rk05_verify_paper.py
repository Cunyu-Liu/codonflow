#!/usr/bin/env python3
"""Independently verify the append-only A8 RiboMIMO study-OOD increment."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def f(value: float, digits: int = 6) -> str:
    return f"{float(value):.{digits}f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--production", type=Path, required=True)
    ap.add_argument("--verification", type=Path, required=True)
    ap.add_argument("--finalization", type=Path, required=True)
    ap.add_argument("--training-record", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo.resolve()
    paper = repo / "paper/CodonFlow_preprint_A8.md"
    sync_path = repo / "paper/a8_rk_paper_sync_audit.json"
    update_path = repo / "paper/a8_rk05_ribomimo_study_ood_paper_update.json"
    snapshot = repo / "paper/snapshots/rk05_ribomimo_study_ood_v25/CodonFlow_preprint_A8_v24.md"
    original = snapshot.read_text()
    updated = paper.read_text()
    update = json.loads(update_path.read_text())
    sync = json.loads(sync_path.read_text())
    production = json.loads(args.production.read_text())
    verification = json.loads(args.verification.read_text())
    final = json.loads(args.finalization.read_text())
    training = json.loads(args.training_record.read_text())
    checks = []
    candidate_facts = []

    def check(name: str, condition: bool, evidence=None) -> None:
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    def fact(name: str, expected: str) -> None:
        ok = expected in updated
        candidate_facts.append({"name": name, "expected": expected, "pass": ok})
        check(f"fact_{name}", ok)

    check("input_v24_hash", sha256(snapshot) == "29c85c3721182acea31e22f9a03e4c0be973c4be46c7b0ed8756eea420b070e5")
    check("output_v25_hash", sha256(paper) == update["output_paper_sha256"] == sync["output_sha256"])
    check("sync_hash", sha256(sync_path) == update["output_sync_sha256"])
    check("version_v25", update["manuscript_version"] == sync["manuscript_version"] == "v25")
    check("non_submittable", update["submittable"] is False and sync["last_increment"]["submittable"] is False and sync["scientific_scope"]["submittable"] is False)
    check("working_manuscript_label", "**non-submittable working manuscript**" in updated)
    check("a7_unchanged", sync["pre_rk05_ribomimo_study_ood_snapshot"]["a7_sha256"] == "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423")
    start = updated.find("### 6.21 RiboMIMO cross-study transfer")
    end = updated.find("## 7. Discussion", start)
    check("single_new_section", start >= 0 and end > start and updated.count("### 6.21 RiboMIMO cross-study transfer") == 1)
    restored = updated[:start] + updated[end:] if start >= 0 and end > start else updated
    anchor_block = "".join(line + "\n" for line in update["anchor_lines"]) + "\n"
    check("anchor_block_present_once", restored.count(anchor_block) == 1)
    restored = restored.replace(anchor_block, "", 1)
    check("all_v24_bytes_preserved", restored == original, {"restored_sha256": hashlib.sha256(restored.encode()).hexdigest(), "original_sha256": hashlib.sha256(original.encode()).hexdigest()})
    section = updated[start:end] if start >= 0 and end > start else ""
    check("finalization_pass", final["status"] == "PASS_RK05_RIBOMIMO_STUDY_OOD" and final["n_checks"] == final["n_passed"])
    check("independent_verification_pass", verification["status"] == "PASS_RK05_RIBOMIMO_STUDY_OOD_INDEPENDENT" and verification["n_checks"] == verification["n_passed"])
    check("training_record_complete", training["status"] == "PASS_COMPLETE" and len(training["rows"]) == 3)
    check("primary_endpoints_bound", final["primary_endpoints"] == production["primary_comparisons"])
    check("scientific_outcome_bound", final["scientific_outcome"] in section and update["scientific_outcome"] == final["scientific_outcome"])
    check("both_intervals_favor_ridge", production["primary_comparisons"][0]["ci95_low"] > 0 and production["primary_comparisons"][1]["ci95_high"] < 0)
    check("both_holm_significant", all(p["holm_pvalue"] < 0.05 for p in production["primary_comparisons"]))
    for run in production["runs"]:
        m = run["target_metrics"]
        expected = f"| {run['seed']} | {f(m['ribomimo']['transcript_balanced_mse'])} | {f(m['ridge']['transcript_balanced_mse'])} | {f(m['constant']['transcript_balanced_mse'])} | {f(m['ribomimo']['mean_transcript_pearson'])} | {f(m['ridge']['mean_transcript_pearson'])} |"
        fact(f"seed_{run['seed']}_row", expected)
    for endpoint in production["primary_comparisons"]:
        label = "delta TB-MSE" if endpoint["metric"] == "transcript_balanced_mse" else "delta mean within-transcript Pearson"
        expected = f"| {label} | {f(endpoint['point_delta_ribomimo_minus_ridge'], 9)} | [{f(endpoint['ci95_low'], 9)}, {f(endpoint['ci95_high'], 9)}] | {f(endpoint['sign_flip_pvalue'], 9)} | {f(endpoint['holm_pvalue'], 9)} |"
        fact(f"primary_{endpoint['metric']}", expected)
    fact("source_target_sizes", "1,062 training and 117 validation transcripts")
    fact("target_size", "3,921 target transcripts")
    fact("source_eligible", "1,179 source")
    fact("exact_cds_disjoint", "Source-target exact CDS overlap was zero")
    fact("primary_seed", "Seed 1234 was primary")
    fact("sensitivity_seeds", "seeds 2345 and 3456 were sensitivity analyses")
    fact("ridge_alpha", "alpha=100 was selected for every seed")
    fact("constant_caution", "the source-train constant also had lower TB-MSE than both learned models for every seed")
    fact("resampling", "2,000 paired-transcript bootstraps, 2,000 paired sign-flip permutations")
    fact("not_globally_untouched", "not a globally untouched confirmatory test")
    fact("not_physical_velocity", "not a physical-velocity measurement")
    fact("not_time_matched", "are not time-matched cost evidence")
    fact("open_gates", "does not close homology/protein OOD, functional OOD, RK-G1, generator authorization or the full baseline program")
    fact("verification_checks", f"It passed {verification['n_passed']}/{verification['n_checks']} checks")
    fact("finalization_checks", f"Finalization passed {final['n_passed']}/{final['n_checks']} checks")
    for label, item in update["artifacts"].items():
        check(f"anchor_{label}", Path(item["path"]).is_file() and sha256(Path(item["path"])) == item["sha256"] and item["sha256"] in updated)
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema_version": "a8-rk05-ribomimo-study-ood-paper-verify-v1",
        "status": "PASS_RK05_RIBOMIMO_STUDY_OOD_PAPER" if passed == len(checks) else "FAIL",
        "n_checks": len(checks), "n_passed": passed,
        "candidate_fact_count": len(candidate_facts),
        "candidate_facts_passed": sum(item["pass"] for item in candidate_facts),
        "candidate_facts": candidate_facts, "checks": checks,
        "paper": str(paper), "paper_sha256": sha256(paper),
        "sync": str(sync_path), "sync_sha256": sha256(sync_path),
        "update": str(update_path), "update_sha256": sha256(update_path),
        "manuscript_version": "v25", "submittable": False,
        "scientific_outcome": final["scientific_outcome"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "candidate_facts": f"{report['candidate_facts_passed']}/{len(candidate_facts)}", "paper_sha256": report["paper_sha256"]}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
