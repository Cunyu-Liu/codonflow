#!/usr/bin/env python3
"""Add only independently finalized RK-11 synthetic neural contracts to A8 v17."""
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
    if path.exists() and path.name.startswith("minimal_neural_paper_update"):
        raise FileExistsError(f"Refusing to overwrite update report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def main():
    names = ("paper", "audit", "a7", "protocol", "production", "retrain", "independent", "finalization", "unit-test-log", "initial-failure", "second-failure", "independent-initial-failure", "independent-second-failure", "development", "snapshot-dir", "update-report")
    parser = argparse.ArgumentParser()
    for name in names:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text())
    if audit.get("schema_version") != "a8-rk-paper-sync-v16" or sha(args.a7) != EXPECTED_A7:
        raise SystemExit("A8 v16/A7 gate failed")
    production = json.loads(args.production.read_text())
    retrain = json.loads(args.retrain.read_text())
    independent = json.loads(args.independent.read_text())
    finalization = json.loads(args.finalization.read_text())
    if not (production["status"] == retrain["status"] == "PASS_MINIMAL_NEURAL_SYNTHETIC_CUDA_CONTRACT" and production["checks_passed"] == production["checks_total"] == 14 and retrain["checks_passed"] == retrain["checks_total"] == 14 and independent["status"] == "PASS_INDEPENDENT_MINIMAL_NEURAL" and independent["checks_passed"] == independent["checks_total"] == 27 and finalization["status"] == "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_CUDA_CONTRACT" and finalization["checks_passed"] == finalization["checks_total"] == 25):
        raise SystemExit("RK-11 evidence is incomplete")
    if not (independent["tensor_bitwise_equal"] and independent["array_bitwise_equal"] and independent["history_numeric_equal"]):
        raise SystemExit("RK-11 retrain tensors or numeric history differ")
    if any(value != 0.0 for value in independent["array_abs_errors"].values()):
        raise SystemExit("RK-11 independent numerical errors are nonzero")

    args.snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paper = args.snapshot_dir / "CodonFlow_preprint_A8_v16.md"
    snapshot_audit = args.snapshot_dir / "a8_rk_paper_sync_audit_v16.json"
    snapshot_a7 = args.snapshot_dir / "CodonFlow_preprint_A7.md"
    shutil.copyfile(args.paper, snapshot_paper)
    shutil.copyfile(args.audit, snapshot_audit)
    shutil.copyfile(args.a7, snapshot_a7)
    input_paper_hash = sha(args.paper)
    input_audit_hash = sha(args.audit)
    section = f"""### 6.13 Minimal neural legal-kernel synthetic CUDA contract

We implemented a **{production['parameter_count']:,}-parameter** minimal neural potential model by reusing the unchanged RK-08 initiation/velocity/decay/pair backbone and adding explicit codon-to-three-nucleotide expansion, multi-fidelity potential supervision, and an exact no-op/synonymous-single-edit conditional kernel. For the frozen `ATG–CTT–GCT–TGA` state, the core genetic-code table gives **{production['candidate_count']} unique legal candidates**, including no-op; internal stops are forbidden and terminal TGA is fixed. The remaining-budget rule admits **{production['budget_allowed']} candidates and hard-masks {production['budget_masked']}**, rather than merely adding a soft cost penalty. UTR–CDS pair tensors and all candidate potentials are auditable.

The fixed smoke used float64 CUDA, Adam for **40 steps without checkpoint selection**, and a synthetic teacher only. The heteroscedastic multi-fidelity objective changed from **{production['initial_eval_loss']:.9f} to {production['final_eval_loss']:.9f}**, while unmasked teacher MSE decreased from **{production['initial_unmasked_mse']:.9f} to {production['final_unmasked_mse']:.9f}**. The conditional probabilities summed to **{production['probability_sum']:.1f}**, total probability on masked states was **{production['masked_probability']:.1f}**, and the maximum absolute kernel-gradient entry was **{production['kernel_gradient_max_abs']:.6e}**. Production and a separate retrain each passed **14/14 checks**; independent recomputation passed **{independent['checks_passed']}/{independent['checks_total']}**, with zero error for candidates, potentials, cost, deltas, and log-probabilities, and finalization passed **{finalization['checks_passed']}/{finalization['checks_total']}**. Checkpoint bytes, all state tensors, kernel arrays, and deterministic numeric history matched between runs; measured elapsed times were retained rather than forced to match. The initial codon-index implementation failed 6 tests, a subsequent test setup failed 1 test, and two independent verifiers stopped at 24/27 and 25/27 before the exact history and teacher-dtype semantics were corrected; all failures are preserved.

This is a **synthetic neural contract and CUDA backward smoke**, not biological mechanism validation, functional or velocity performance, full-generator training, generation quality, RK-G1 passage, OOD, SOTA, or authorization for expensive generation training.

"""
    text = args.paper.read_text()
    marker = "## 7. Discussion\n"
    if text.count(marker) != 1 or "### 6.13 Minimal neural legal-kernel synthetic CUDA contract" in text:
        raise SystemExit("paper insertion marker failed")
    updated = text.replace(marker, section + marker)
    sources = {
        "rk11_protocol": args.protocol,
        "rk11_production": args.production,
        "rk11_retrain": args.retrain,
        "rk11_independent": args.independent,
        "rk11_finalization": args.finalization,
        "rk11_unit_tests": args.unit_test_log,
        "rk11_initial_failure": args.initial_failure,
        "rk11_second_failure": args.second_failure,
        "rk11_independent_initial_failure": args.independent_initial_failure,
        "rk11_independent_second_failure": args.independent_second_failure,
        "rk11_development": args.development,
    }
    labels = {
        "rk11_protocol": "RK-11 frozen synthetic neural protocol",
        "rk11_production": "RK-11 production CUDA contract",
        "rk11_retrain": "RK-11 independent retrain",
        "rk11_independent": "RK-11 independent numerical verification",
        "rk11_finalization": "RK-11 finalization",
        "rk11_unit_tests": "RK-11 final unit tests",
        "rk11_initial_failure": "RK-11 initial codon-mapping failure",
        "rk11_second_failure": "RK-11 second test-setup failure",
        "rk11_independent_initial_failure": "RK-11 first independent failure",
        "rk11_independent_second_failure": "RK-11 second independent failure",
        "rk11_development": "RK-11 development CUDA smoke",
    }
    rows = "".join(f"| {labels[key]} | `{sha(path)}` |\n" for key, path in sources.items())
    anchor = "\nA7 is retained as the prior manuscript snapshot."
    if updated.count(anchor) != 1:
        raise SystemExit("evidence insertion marker failed")
    updated = updated.replace(anchor, rows + anchor)
    atomic(args.paper, updated)
    audit["generated_sections"].extend(["6.13 RK-11 minimal neural legal-kernel synthetic CUDA contract", "8.1 RK-11 synthetic neural evidence anchors"])
    audit["schema_version"] = "a8-rk-paper-sync-v17"
    audit["output_sha256"] = sha(args.paper)
    audit["scientific_scope"]["rk11_minimal_neural"] = "Synthetic teacher and exact finite-state neural CUDA contracts only; no biological mechanism, functional/generation performance, full-generator training, RK-G1 closure, OOD, SOTA or expensive-generation authorization."
    for key, path in sources.items():
        audit["source_paths"][key] = str(path)
        audit["source_sha256"][key] = sha(path)
    audit["base_v16_paper_sha256"] = input_paper_hash
    audit["base_v16_audit_sha256"] = input_audit_hash
    audit["pre_rk11_snapshot"] = {"paper": str(snapshot_paper), "paper_sha256": sha(snapshot_paper), "audit": str(snapshot_audit), "audit_sha256": sha(snapshot_audit), "a7": str(snapshot_a7), "a7_sha256": sha(snapshot_a7)}
    atomic(args.audit, json.dumps(audit, indent=2, sort_keys=True) + "\n")
    report = {
        "schema": "a8-rk11-minimal-neural-paper-update-v17",
        "input_paper_sha256": input_paper_hash, "input_audit_sha256": input_audit_hash,
        "output_paper_sha256": sha(args.paper), "output_audit_sha256": sha(args.audit),
        "a7_sha256": sha(args.a7), "section": section, "evidence_rows": rows,
        "evidence_sha256": {key: sha(path) for key, path in sources.items()},
        "snapshot": audit["pre_rk11_snapshot"],
        "scientific_scope_unchanged": {"biological_mechanism_validated": False, "functional_or_generation_performance_evaluated": False, "full_generator_trained": False, "rk_g1_gate_modified": False, "sota_claimed": False, "expensive_generation_authorized": False},
    }
    atomic(args.update_report, json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"paper_sha256": report["output_paper_sha256"], "audit_sha256": report["output_audit_sha256"]}))


if __name__ == "__main__":
    main()
