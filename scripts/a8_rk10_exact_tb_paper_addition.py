#!/usr/bin/env python3
"""Add only independently finalized RK10 mathematical optimization to A8 v16."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

EXPECTED_A7 = "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, text):
    if path.exists() and path.name.startswith("a8_rk10_exact_tb_paper_update"):
        raise FileExistsError(f"Refusing to overwrite update report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    for name in ("paper", "audit", "a7", "protocol", "production", "retrain", "independent", "finalization", "unit-test-log", "initial-failure", "snapshot-dir", "update-report"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text())
    if audit.get("schema_version") != "a8-rk-paper-sync-v15" or sha(args.a7) != EXPECTED_A7:
        raise SystemExit("A8 v15/A7 gate failed")
    production = json.loads(args.production.read_text())
    retrain = json.loads(args.retrain.read_text())
    independent = json.loads(args.independent.read_text())
    finalization = json.loads(args.finalization.read_text())
    if not (production["status"] == retrain["status"] == independent["status"] == "PASS" and production["checks_passed"] == production["checks_total"] and retrain["checks_passed"] == retrain["checks_total"] and independent["checks_passed"] == independent["checks_total"] and finalization["status"] == "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_ANALYTIC_ORACLE" and finalization["checks_passed"] == finalization["checks_total"]):
        raise SystemExit("RK10 evidence is incomplete")
    if finalization["production_report_sha256"] != sha(args.production) or finalization["retrain_report_sha256"] != sha(args.retrain) or finalization["independent_report_sha256"] != sha(args.independent) or independent["production_report_sha256"] != sha(args.production):
        raise SystemExit("RK10 evidence identity mismatch")
    if not (finalization["theta_bitwise_equal"] and finalization["backward_logits_bitwise_equal"]):
        raise SystemExit("RK10 retrain tensors differ")

    args.snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paper = args.snapshot_dir / "CodonFlow_preprint_A8_v15.md"
    snapshot_audit = args.snapshot_dir / "a8_rk_paper_sync_audit_v15.json"
    snapshot_a7 = args.snapshot_dir / "CodonFlow_preprint_A7.md"
    shutil.copyfile(args.paper, snapshot_paper)
    shutil.copyfile(args.audit, snapshot_audit)
    shutil.copyfile(args.a7, snapshot_a7)
    input_paper_hash = sha(args.paper)
    input_audit_hash = sha(args.audit)
    metrics = independent["metrics"]
    oracle = independent["analytic_oracle"]
    weight_error = max(abs(a - b) for a, b in zip(production["theta"], production["target_weights"]))
    section = f"""### 6.12 Exact preference-conditioned trajectory-balance optimization

We next tested optimization on the frozen synthetic two-step system with **{production['geometry']['states']:,} endpoint states**, **{production['geometry']['actions_per_state']} legal actions per state**, and **{production['geometry']['paths']:,} enumerated paths**. The target is the exact endpoint law induced by the frozen oracle energy-tilted conditional, not a naive random-walk endpoint approximation. The first reverse step deterministically returns to the unique fixed start; the second reverse step is normalized only over legal parents reachable from that start. This construction preserves all state-dependent forward normalizers and the true time support.

The fixed protocol used float64 CUDA, Adam for **4,000 steps without checkpoint selection**, and a linear learning-rate schedule from 0.05 to 0.01. The independently recomputed final path-residual loss was **{metrics['loss']:.3e}**, maximum absolute path residual **{metrics['max_abs_path_residual']:.3e}**, maximum forward–target endpoint error **{metrics['max_abs_forward_target_error']:.3e}**, forward–target KL **{metrics['forward_target_kl']:.3e}**, and maximum endpoint-reconstruction error **{metrics['max_abs_endpoint_reconstruction_error']:.3e}**. The learned four weights differed from the frozen oracle weights by at most **{weight_error:.3e}**. Production and a separately executed retraining had bitwise-identical weight and backward-logit tensors and identical optimization histories. A separate NumPy implementation passed **{independent['checks_passed']}/{independent['checks_total']} checks**, finalization passed **{finalization['checks_passed']}/{finalization['checks_total']}**, and **10 unit tests** passed. The analytic oracle independently gave maximum path residual **{oracle['max_abs_residual']:.3e}**, forward–target error **{oracle['max_abs_forward_target_error']:.3e}**, and backward-normalization error **{oracle['max_abs_backward_normalization_error']:.3e}**. The earlier incorrect target/shared-backward version failed 2 of 10 tests and is retained rather than hidden.

This is an **exact synthetic trajectory-balance optimization check**, not biological reward learning, a trained neural CodonFlow-RK generator, functional or generation performance, physical mechanism validation, RK-G1 closure, SOTA, or authorization for expensive generation training.

"""
    text = args.paper.read_text()
    marker = "## 7. Discussion\n"
    if text.count(marker) != 1 or "### 6.12 Exact preference-conditioned trajectory-balance optimization" in text:
        raise SystemExit("paper insertion marker failed")
    updated = text.replace(marker, section + marker)
    sources = {
        "rk10_protocol": args.protocol,
        "rk10_production": args.production,
        "rk10_retrain": args.retrain,
        "rk10_independent": args.independent,
        "rk10_finalization": args.finalization,
        "rk10_unit_tests": args.unit_test_log,
        "rk10_initial_failure": args.initial_failure,
    }
    labels = {
        "rk10_protocol": "RK10 exact trajectory-balance protocol",
        "rk10_production": "RK10 exact trajectory-balance production",
        "rk10_retrain": "RK10 exact trajectory-balance retrain",
        "rk10_independent": "RK10 independent NumPy and analytic-oracle verification",
        "rk10_finalization": "RK10 exact trajectory-balance finalization",
        "rk10_unit_tests": "RK10 final unit-test log",
        "rk10_initial_failure": "RK10 retained initial failed unit-test log",
    }
    rows = "".join(f"| {labels[key]} | `{sha(path)}` |\n" for key, path in sources.items())
    anchor = "\nA7 is retained as the prior manuscript snapshot."
    if updated.count(anchor) != 1:
        raise SystemExit("evidence insertion marker failed")
    updated = updated.replace(anchor, rows + anchor)
    atomic(args.paper, updated)

    audit["generated_sections"].extend(["6.12 RK10 exact preference-conditioned trajectory-balance optimization", "8.1 RK10 exact trajectory-balance evidence anchors"])
    audit["schema_version"] = "a8-rk-paper-sync-v16"
    audit["output_sha256"] = sha(args.paper)
    audit["scientific_scope"]["rk10_exact_trajectory_balance"] = "Synthetic two-step exact trajectory-balance optimization only; no biological reward, trained neural generator, functional/generation performance, RK-G1 closure, SOTA or expensive-generation authorization."
    for key, path in sources.items():
        audit["source_paths"][key] = str(path)
        audit["source_sha256"][key] = sha(path)
    audit["base_v15_paper_sha256"] = input_paper_hash
    audit["base_v15_audit_sha256"] = input_audit_hash
    audit["pre_rk10_snapshot"] = {"paper": str(snapshot_paper), "paper_sha256": sha(snapshot_paper), "audit": str(snapshot_audit), "audit_sha256": sha(snapshot_audit), "a7": str(snapshot_a7), "a7_sha256": sha(snapshot_a7)}
    atomic(args.audit, json.dumps(audit, indent=2, sort_keys=True) + "\n")
    report = {
        "schema": "a8-rk10-exact-tb-paper-update-v16",
        "input_paper_sha256": input_paper_hash, "input_audit_sha256": input_audit_hash,
        "output_paper_sha256": sha(args.paper), "output_audit_sha256": sha(args.audit),
        "a7_sha256": sha(args.a7), "section": section, "evidence_rows": rows,
        "evidence_sha256": {key: sha(path) for key, path in sources.items()},
        "snapshot": audit["pre_rk10_snapshot"],
        "scientific_scope_unchanged": {"biological_reward_measured": False, "full_neural_model_trained": False, "functional_or_generation_performance_evaluated": False, "rk_g1_gate_modified": False, "sota_claimed": False, "expensive_generation_authorized": False},
    }
    atomic(args.update_report, json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"paper_sha256": report["output_paper_sha256"], "audit_sha256": report["output_audit_sha256"]}))


if __name__ == "__main__":
    main()
