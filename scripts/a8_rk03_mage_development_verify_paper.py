#!/usr/bin/env python3
"""Independent manuscript and candidate-fact verifier for MAGE v26."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", required=True)
    parser.add_argument("--a7", required=True)
    parser.add_argument("--sync-audit", required=True)
    parser.add_argument("--update-record", required=True)
    parser.add_argument("--production", required=True)
    parser.add_argument("--independent", required=True)
    parser.add_argument("--finalization", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    paper = Path(args.paper).read_text()
    record = json.loads(Path(args.update_record).read_text())
    production = json.loads(Path(args.production).read_text())
    independent = json.loads(Path(args.independent).read_text())
    final = json.loads(Path(args.finalization).read_text())
    sync = json.loads(Path(args.sync_audit).read_text())
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    def has(label, text):
        check(f"paper_fact_{label}", text in paper, text)

    check("paper_hash_record", sha256(args.paper) == record["new_paper_sha256"])
    check("sync_hash_record", sha256(args.sync_audit) == record["new_sync_audit_sha256"])
    check("snapshot_paper_hash", sha256(record["snapshot_paper"]) == record["old_paper_sha256"])
    check("snapshot_audit_hash", sha256(record["snapshot_audit"]) == record["old_sync_audit_sha256"])
    check("a7_unchanged", sha256(args.a7) == record["a7_sha256"] and sha256(record["snapshot_a7"]) == record["a7_sha256"])
    recovered = paper.replace(record["section"] + "\n", "", 1).replace(record["evidence_anchors"], "", 1)
    check("v25_exactly_recoverable", hashlib.sha256(recovered.encode()).hexdigest() == record["old_paper_sha256"])
    check("v25_snapshot_byte_exact", recovered == Path(record["snapshot_paper"]).read_text())
    check("section_present_once", paper.count("### 6.22 MAGE nested development CV: mechanism increments were small and unstable") == 1)
    check("previous_section_preserved", paper.count("### 6.21 RiboMIMO cross-study transfer") == 1)
    check("section_before_discussion", paper.index("### 6.22 MAGE") < paper.index("## 7. Discussion"))
    check("production_no_go", production["status"] == "DEV_NO_GO_TEST_UNTOUCHED" and not production["development_go"])
    check("independent_96_pass", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] == 96)
    check("finalization_30_pass", final["status"] == "PASS" and final["checks_passed"] == final["checks_total"] == 30)
    check("zero_independent_deltas", all(v == 0.0 for v in independent["max_numeric_deltas"].values()))
    check("test_still_untouched", not production["test_predictions_generated"] and not production["test_metrics_generated"] and final["test_n_untouched"] == 33)
    check("generator_not_authorized", not final["expensive_generation_authorized"] and not final["rk_g1_pass"])
    check("non_submittable", "non-submittable working manuscript" in paper and not record["submittable"] and not sync["last_increment"]["submittable"])
    check("sync_output_hash", sync["output_sha256"] == record["new_paper_sha256"])
    check("sync_increment_hashes", all(sync["last_increment"][k] == record["source_hashes"][source] for k, source in [("protocol_sha256", "protocol"), ("production_sha256", "production"), ("independent_sha256", "independent"), ("finalization_sha256", "finalization")]))
    check("sync_scope", sync["rk03_mage_development_nested_cv"]["status"] == "DEV_NO_GO_TEST_UNTOUCHED" and sync["rk03_mage_development_nested_cv"]["test_n_untouched"] == 33)

    has("development_n", "131 constructs")
    has("original_train_dev", "98 train and 33 development")
    has("test_n", "33 test constructs")
    has("outer_inner", "Five-fold outer cross-validation")
    has("inner_folds", "four-fold inner cross-validation")
    has("resampling", "20,000 construct bootstraps")
    has("permutation", "20,000 paired sign-flip permutations")
    has("primary_seed", "40261119")
    has("sensitivity_seeds", "40261120 and 40261121")
    m = final["primary_models"]
    for name in ["intrinsic", "local_mfe", "rcs_only", "full_mechanism"]:
        has(f"model_{name}_rmse", f"{m[name]['rmse']:.9f}")
        has(f"model_{name}_spearman", f"{m[name]['spearman']:.9f}")
    a = final["primary_comparisons"]["full_mechanism_minus_intrinsic"]
    b = final["primary_comparisons"]["full_mechanism_minus_local_mfe"]
    has("intrinsic_delta_rmse", f"{a['delta_rmse']:.9f}")
    has("intrinsic_delta_spearman", f"{a['delta_spearman']:.9f}")
    has("local_delta_rmse", f"{b['delta_rmse']:.9f}")
    has("local_delta_spearman", f"{b['delta_spearman']:.9f}")
    has("intrinsic_rmse_ci", f"[{a['delta_rmse_ci95'][0]:.9f}, {a['delta_rmse_ci95'][1]:.9f}]")
    has("local_rmse_ci", f"[{b['delta_rmse_ci95'][0]:.9f}, {b['delta_rmse_ci95'][1]:.9f}]")
    has("holm_all_one", "all four Holm-adjusted p values were 1.0")
    has("sensitivity_negative", "full-minus-local-MFE Spearman was negative in both sensitivity repeats")
    has("no_universal_structure_claim", "do not show that RNA structure is universally uninformative")
    has("independent_count", "96/96 checks")
    has("finalization_count", "30/30 checks")
    has("no_test_readout", "No test prediction, test metric, minimal-medium transport, N-terminal transport or generator authorization was generated")
    for label, value in record["source_hashes"].items():
        check(f"evidence_anchor_{label}", f"`{value}`" in paper)
    result = {
        "schema": "a8-rk03-mage-development-nested-cv-paper-verification-v26",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "checks": checks,
        "checks_passed": sum(c["pass"] for c in checks),
        "checks_total": len(checks),
        "candidate_facts_passed": sum(c["pass"] for c in checks if c["name"].startswith("paper_fact_")),
        "candidate_facts_total": sum(c["name"].startswith("paper_fact_") for c in checks),
        "paper_sha256": sha256(args.paper),
        "sync_audit_sha256": sha256(args.sync_audit),
        "v25_recovery_verified": recovered == Path(record["snapshot_paper"]).read_text(),
        "submittable": False,
    }
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"status": result["status"], "checks": f"{result['checks_passed']}/{result['checks_total']}", "candidate_facts": f"{result['candidate_facts_passed']}/{result['candidate_facts_total']}", "paper_sha256": result["paper_sha256"]}, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
