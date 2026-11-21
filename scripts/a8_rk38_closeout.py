#!/usr/bin/env python3
"""Compare primary and clean RK38 inventories and close the evidence scope."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

SCHEMA = "a8-rk38-clean-reproduction-closeout-v1"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--primary-summary", required=True)
    p.add_argument("--clean-summary", required=True)
    p.add_argument("--primary-independent", required=True)
    p.add_argument("--clean-independent", required=True)
    p.add_argument("--primary-details", required=True)
    p.add_argument("--clean-details", required=True)
    p.add_argument("--primary-cells", required=True)
    p.add_argument("--clean-cells", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    primary = json.loads(Path(args.primary_summary).read_text())
    clean = json.loads(Path(args.clean_summary).read_text())
    p_ind = json.loads(Path(args.primary_independent).read_text())
    c_ind = json.loads(Path(args.clean_independent).read_text())
    p_core, c_core = copy.deepcopy(primary), copy.deepcopy(clean)
    for core in (p_core, c_core):
        core.pop("artifacts", None)
        core.pop("created_at", None)
    checks = {
        "primary_independent_1851_pass": p_ind["status"] == "PASS" and p_ind["n_pass"] == 1851 and p_ind["n_fail"] == 0,
        "clean_independent_1851_pass": c_ind["status"] == "PASS" and c_ind["n_pass"] == 1851 and c_ind["n_fail"] == 0,
        "summary_core_exact": p_core == c_core,
        "details_csv_byte_exact": Path(args.primary_details).read_bytes() == Path(args.clean_details).read_bytes(),
        "external_cells_csv_byte_exact": Path(args.primary_cells).read_bytes() == Path(args.clean_cells).read_bytes(),
        "primary_complete": primary["status"] == "PASS_INVENTORY_ONLY_SCIENTIFIC_GATES_UNRESOLVED",
        "clean_complete": clean["status"] == "PASS_INVENTORY_ONLY_SCIENTIFIC_GATES_UNRESOLVED",
        "untouched_not_evaluated": primary["functional_untouched"]["functional_untouched_evaluated"] is False and primary["functional_untouched"]["new_label_or_outcome_read"] is False,
        "scientific_gates_not_promoted": all(primary[flag] is False for flag in [
            "scientific_gate_passed", "codonflow_external_sota_evaluated", "time_matched_comparison",
            "functional_untouched_evaluated", "new_functional_labels_read", "sota_claim", "rk_g1_pass",
            "expensive_generator_training_authorized", "manuscript_submittable",
        ]),
    }
    report = {
        "schema": SCHEMA,
        "status": "PASS_INVENTORY_CLOSEOUT_ONLY" if all(checks.values()) else "FAIL",
        "checks": checks,
        "n_checks": len(checks), "n_pass": sum(checks.values()), "n_fail": len(checks) - sum(checks.values()),
        "primary_summary_sha256": sha256(args.primary_summary), "clean_summary_sha256": sha256(args.clean_summary),
        "primary_independent_sha256": sha256(args.primary_independent), "clean_independent_sha256": sha256(args.clean_independent),
        "details_csv_sha256": sha256(args.primary_details), "external_cells_csv_sha256": sha256(args.primary_cells),
        "scientific_conclusion": {
            "verified_existing_real_asset_inventory": True,
            "new_model_training_or_generation": False,
            "new_external_baseline_execution": False,
            "functional_untouched_evaluation": False,
            "dense_auc_for_actual_set_methods": None,
            "sota_claim": False, "rk_g1_pass": False,
            "next_scientific_gate": "Do not treat this inventory as a performance win; any new comparison requires a separately frozen executable and input-matched protocol.",
        },
    }
    out = Path(args.output)
    if out.exists():
        raise FileExistsError(str(out))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "n_pass": report["n_pass"], "n_checks": report["n_checks"], "output_sha256": sha256(out)}, indent=2))
    raise SystemExit(0 if report["status"] == "PASS_INVENTORY_CLOSEOUT_ONLY" else 1)


if __name__ == "__main__":
    main()
