#!/usr/bin/env python3
"""Add only the verified RK09 mathematical-kernel result to A8 v14."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

EXPECTED_V13_PAPER = "cd2c74ef1b093bb0ce5d3bfce5d0bb26939367c6d0fa5269361096c7f5aa8f0d"
EXPECTED_V13_AUDIT = "4b562b630bb0344a0b862fcdb03894f96ac4c533bf2aaa1cc1d5a259f0d911ef"
EXPECTED_A7 = "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--a7", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--initial-production-failure", type=Path, required=True)
    parser.add_argument("--initial-independent-failure", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--update-report", type=Path, required=True)
    args = parser.parse_args()
    if sha(args.paper) != EXPECTED_V13_PAPER or sha(args.audit) != EXPECTED_V13_AUDIT or sha(args.a7) != EXPECTED_A7:
        raise SystemExit("A8 v13/A7 hash gate failed")
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    finalization = json.loads(args.finalization.read_text())
    if not (production["all_pass"] and production["checks_passed"] == 22 and independent["all_pass"] and independent["checks_passed"] == 16 and finalization["all_pass"] and finalization["checks_passed"] == 14):
        raise SystemExit("RK09 evidence is not complete")
    if independent["production_sha256"] != sha(args.production) or finalization["evidence_sha256"]["independent"] != sha(args.independent):
        raise SystemExit("RK09 evidence identity mismatch")

    args.snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paper = args.snapshot_dir / "CodonFlow_preprint_A8_v13.md"
    snapshot_audit = args.snapshot_dir / "a8_rk_paper_sync_audit_v13.json"
    snapshot_a7 = args.snapshot_dir / "CodonFlow_preprint_A7.md"
    shutil.copyfile(args.paper, snapshot_paper)
    shutil.copyfile(args.audit, snapshot_audit)
    shutil.copyfile(args.a7, snapshot_a7)

    telescope = production["metrics"]["telescope"]
    tv = production["metrics"]["naive_two_step_total_variation_vs_uniform"]
    section = f"""### 6.11 Minimal CodonFlow-RK mathematical kernel: exact small-state verification

Before any model training, we froze and tested the legal codon simplex and conditional kernels. A state has 64 slots per position, index 63 is the terminal stop, and internal positions may use only the 61 sense-codon indices. A feasible transition is either a no-op or one internal sense-codon replacement. The base conditional is uniform over its feasible support; preference and remaining-budget terms only reweight or mask that support. On the frozen length-four example, exhaustive enumeration produced **{production['counts']['kernel_valid_states']:,} valid states**, **{production['counts']['one_step_targets']} one-step targets**, and **{production['counts']['two_step_reachable_states']:,} states reachable within two transitions**. Exhaustive rejection recovers the exactly uniform feasible-set distribution, whereas the naive two-step random walk has total-variation distance **{tv:.12f}** from that uniform endpoint reference.

For the length-three path example, all **{telescope['path_count']:,} paths** and **{telescope['endpoint_count']:,} endpoints** were enumerated. Including the target endpoint mass in the backward path law makes the forward/backward log-probability ratio telescope to `log U(end) - log q_T(end)`. Maximum backward-normalization, path-telescoping and endpoint-reconstruction errors were **{telescope['max_backward_normalization_error']:.3e}**, **{telescope['max_telescope_error']:.3e}**, and **{telescope['max_endpoint_reconstruction_error']:.3e}**, respectively. The event-time transform `t = 1 - u^(1/kappa)` was checked against its inverse CDF; its analytic mean is `1/(kappa+1)`, not `kappa/(kappa+1)`. Production checks passed **22/22**, an independent implementation that did not import the production module passed **16/16**, finalization passed **14/14**, and **10 unit tests** passed. The initial 19/22 production failure (missing endpoint mass and reversed event-mean formula) and the independent 15/16 mask failure are retained with the corrected reports.

This is a **mathematical-kernel verification only**. It is not trained CodonFlow-RK, functional or generation performance, a mechanistic increment, RK-G1 closure, SOTA, or authorization for expensive generation training.

"""
    text = args.paper.read_text()
    marker = "## 7. Discussion\n"
    if text.count(marker) != 1 or "### 6.11 Minimal CodonFlow-RK" in text:
        raise SystemExit("paper insertion marker failed")
    updated = text.replace(marker, section + marker)
    sources = {
        "rk09_protocol": args.protocol,
        "rk09_production": args.production,
        "rk09_independent": args.independent,
        "rk09_finalization": args.finalization,
        "rk09_initial_production_failure": args.initial_production_failure,
        "rk09_initial_independent_failure": args.initial_independent_failure,
    }
    labels = {
        "rk09_protocol": "RK09 minimal-kernel protocol",
        "rk09_production": "RK09 minimal-kernel production",
        "rk09_independent": "RK09 minimal-kernel independent verifier",
        "rk09_finalization": "RK09 minimal-kernel finalization",
        "rk09_initial_production_failure": "RK09 retained initial production failure",
        "rk09_initial_independent_failure": "RK09 retained initial independent failure",
    }
    rows = "".join(f"| {labels[key]} | `{sha(path)}` |\n" for key, path in sources.items())
    anchor = "\nA7 is retained as the prior manuscript snapshot."
    if updated.count(anchor) != 1:
        raise SystemExit("evidence insertion marker failed")
    updated = updated.replace(anchor, rows + anchor)
    atomic(args.paper, updated)

    audit = json.loads(args.audit.read_text())
    audit["generated_sections"].extend(["6.11 RK09 minimal CodonFlow-RK mathematical kernel", "8.1 RK09 mathematical-kernel evidence anchors"])
    audit["schema_version"] = "a8-rk-paper-sync-v14"
    audit["output_sha256"] = sha(args.paper)
    audit["scientific_scope"]["rk09_minimal_kernel"] = "Exact small-state legal-simplex, feasible-kernel, rejection/random-walk, path-telescoping and event-time verification only; no trained model, functional/generation performance, RK-G1 closure, SOTA or expensive-generation authorization."
    for key, path in sources.items():
        audit["source_paths"][key] = str(path)
        audit["source_sha256"][key] = sha(path)
    audit["base_v13_paper_sha256"] = EXPECTED_V13_PAPER
    audit["base_v13_audit_sha256"] = EXPECTED_V13_AUDIT
    audit["pre_rk09_snapshot"] = {
        "paper": str(snapshot_paper), "paper_sha256": sha(snapshot_paper),
        "audit": str(snapshot_audit), "audit_sha256": sha(snapshot_audit),
        "a7": str(snapshot_a7), "a7_sha256": sha(snapshot_a7),
    }
    atomic(args.audit, json.dumps(audit, indent=2, sort_keys=True) + "\n")
    report = {
        "schema": "a8-rk09-minimal-paper-update-v14",
        "input_paper_sha256": EXPECTED_V13_PAPER,
        "input_audit_sha256": EXPECTED_V13_AUDIT,
        "output_paper_sha256": sha(args.paper),
        "output_audit_sha256": sha(args.audit),
        "a7_sha256": sha(args.a7),
        "section": section,
        "evidence_rows": rows,
        "evidence_sha256": {key: sha(path) for key, path in sources.items()},
        "snapshot": audit["pre_rk09_snapshot"],
        "scientific_scope_unchanged": {"trained_model": False, "functional_or_generation_performance": False, "rk_g1_gate_modified": False, "sota_claimed": False, "expensive_generation_authorized": False},
    }
    atomic(args.update_report, json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"paper_sha256": report["output_paper_sha256"], "audit_sha256": report["output_audit_sha256"]}))


if __name__ == "__main__":
    main()
