#!/usr/bin/env python3
"""Finalize the independently verified RK08 channel-screen closeout."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    audit = root / "audits/20261118/RK08"
    protocol_path = root / "configs/a8_rk08_channel_screen_protocol_v1.json"
    preparation_path = audit / "channel_screen_preparation_v1.json"
    selection_path = audit / "channel_screen_selection_v1.json"
    evaluation_path = audit / "channel_screen_evaluation_v1.json"
    independent_path = audit / "channel_screen_independent_v1.json"
    protocol = json.loads(protocol_path.read_text())
    preparation = json.loads(preparation_path.read_text())
    selection = json.loads(selection_path.read_text())
    evaluation = json.loads(evaluation_path.read_text())
    independent = json.loads(independent_path.read_text())
    checks = []

    def check(name: str, condition: bool, detail=None) -> None:
        checks.append({"check_id": name, "passed": bool(condition), "detail": detail})

    check("protocol_frozen", protocol["status"] == "FROZEN_BEFORE_CHANNEL_TRAINING_AND_TEST_READOUT")
    check("preparation_pass", preparation["status"] == "PASS_CHANNEL_SCREEN_PREPARATION")
    check("selection_frozen", selection["status"] == "PASS_CHANNEL_SELECTION_FROZEN")
    check("evaluation_produced", evaluation["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("independent_pass", independent["status"] == "PASS_CHANNEL_SCREEN_INDEPENDENT" and independent["overall_pass"])
    check("independent_no_failures", independent["failures"] == [])
    check("independent_numeric_tolerance", independent["max_numeric_delta"] <= 1e-12, independent["max_numeric_delta"])
    check("ten_arms", len(selection["development_table"]) == 10)
    check("one_selected_arm", selection["selected_arm"] == evaluation["selected_arm"] == independent["selected_arm"])
    check("selection_matches_independent", selection["selected_dev_cluster_balanced_mse"] == independent["selected_dev_cluster_balanced_mse"])
    check("gate_matches_independent", evaluation["channel_screen_gate_pass"] == independent["channel_screen_gate_pass"])
    check("sequence_ood_comparisons", len([row for row in independent["independent_comparisons"] if row["partition"] == "sequence_ood"]) == 6)
    check("test_comparisons", len([row for row in independent["independent_comparisons"] if row["partition"] == "test"]) == 6)
    check("bootstrap_2000", all(row["bootstrap_valid"] == row["bootstrap_requested"] == 2000 for row in independent["independent_comparisons"]))
    check("all_prior_state_equal", selection["prior_checkpoint_equivalence"]["all"]["state_dict_bitwise_equal"])
    check("none_prior_state_equal", selection["prior_checkpoint_equivalence"]["none"]["state_dict_bitwise_equal"])
    check("screen_excluded_test_ood", selection["test_or_ood_used_for_selection"] is False)
    check("functional_untouched_not_evaluated", evaluation["functional_untouched_evaluated"] is False and independent["functional_untouched_evaluated"] is False)
    check("velocity_negative_retained", evaluation["velocity_mechanism_pass"] is False and independent["velocity_mechanism_pass"] is False)
    check("rk_g1_remains_false", evaluation["rk_g1_pass"] is False and independent["rk_g1_pass"] is False)
    check("generator_not_authorized", evaluation["expensive_generation_authorized"] is False and independent["expensive_generation_authorized"] is False)
    check("complete_sota_false", evaluation["complete_sota"] is False)
    check("wet_lab_false", evaluation["wet_lab_validation_complete"] is False)
    test_log = (audit / "channel_screen_unit_tests_v1.console.log").read_text()
    check("unit_tests_8_pass", "8 passed" in test_log)
    bootstrap = Path(protocol["output_root"]) / "evaluation/bootstrap_deltas.csv.gz"
    check("bootstrap_artifact_present", bootstrap.is_file() and bootstrap.stat().st_size > 1000)
    check("evaluation_summary_raw_copy", (Path(protocol["output_root"]) / "evaluation/comparison_summary.json").is_file())
    check("selection_hash_in_evaluation", evaluation["selection_sha256"] == sha256(selection_path))
    check("protocol_hash_chain", preparation["protocol_sha256"] == selection["protocol_sha256"] == evaluation["protocol_sha256"] == independent["hashes"]["protocol"] == sha256(protocol_path))
    check("evaluation_hash_chain", independent["hashes"]["evaluation"] == sha256(evaluation_path))
    tracked = [
        "configs/a8_rk08_channel_screen_protocol_v1.json",
        "scripts/a8_rk08_prepare_channel_screen.py",
        "scripts/a8_rk08_run_channel_screen.sh",
        "scripts/a8_rk08_select_channel_screen.py",
        "scripts/a8_rk08_eval_channel_screen.py",
        "scripts/a8_rk08_verify_channel_screen.py",
        "scripts/a8_rk08_finalize_channel_screen.py",
        "tests/test_a8_rk08_channel_screen.py",
        "audits/20261118/RK08/channel_screen_preparation_v1.json",
        "audits/20261118/RK08/channel_screen_selection_v1.json",
        "audits/20261118/RK08/channel_screen_evaluation_v1.json",
        "audits/20261118/RK08/channel_screen_independent_v1.json",
    ]
    for relative in tracked:
        result = subprocess.run(["git", "ls-files", "--error-unmatch", relative], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        check(f"tracked:{relative}", result.returncode == 0)
    prereg = subprocess.run(["git", "merge-base", "--is-ancestor", "669b2735c21bf9bda8fdac12fc0c9f69635a38b5", "HEAD"], cwd=root)
    check("preregistration_commit_is_ancestor", prereg.returncode == 0)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    failures = [row["check_id"] for row in checks if not row["passed"]]
    report = {
        "schema": "a8-rk08-channel-screen-finalization-v1",
        "status": "PASS_CHANNEL_SCREEN_CLOSEOUT" if not failures else "FAIL_CHANNEL_SCREEN_CLOSEOUT",
        "overall_pass": not failures,
        "check_counts": {"passed": len(checks) - len(failures), "total": len(checks)},
        "failures": failures,
        "git_head_at_finalization": head,
        "preregistration_commit": "669b2735c21bf9bda8fdac12fc0c9f69635a38b5",
        "selected_arm": selection["selected_arm"],
        "selected_dev_cluster_balanced_mse": selection["selected_dev_cluster_balanced_mse"],
        "channel_screen_gate_pass": evaluation["channel_screen_gate_pass"],
        "rk_g1_pass": False,
        "functional_untouched_evaluated": False,
        "velocity_mechanism_pass": False,
        "expensive_generation_authorized": False,
        "complete_sota": False,
        "full_project_pytest_run": False,
        "clean_environment_install_run": False,
        "hashes": {
            "protocol": sha256(protocol_path),
            "preparation": sha256(preparation_path),
            "selection": sha256(selection_path),
            "evaluation": sha256(evaluation_path),
            "independent": sha256(independent_path),
            "bootstrap_deltas": sha256(bootstrap),
        },
        "checks": checks,
    }
    output = audit / "channel_screen_finalization_v1.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "check_counts": report["check_counts"], "selected_arm": report["selected_arm"], "channel_screen_gate_pass": report["channel_screen_gate_pass"], "failures": failures}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
