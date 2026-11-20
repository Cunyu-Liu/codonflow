#!/usr/bin/env python3
"""Verify the RK28 frozen protocol and label-free coverage before any fit."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

REPO = Path("/home/codonflow-a8-rk")
AUDIT = REPO / "audits/20261121/RK28"
PROTOCOL = AUDIT / "a8_rk28_mordstein_sequence_cluster_ood_protocol_v1.json"
REPORT = AUDIT / "rk28_sequence_coverage_v1.json"
FACTS = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk28/mordstein_observed_r1_sequence_cluster_ood_v1/sequence_cluster_facts.csv")
OUTPUT = AUDIT / "rk28_freeze_verification_v1.json"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    protocol = json.loads(PROTOCOL.read_text())
    report = json.loads(REPORT.read_text())
    facts = pd.read_csv(FACTS)
    checks = []

    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})
        if not condition:
            raise AssertionError(name)

    check("protocol frozen before outcome/feature read", protocol["created_before_RK28_outcome_or_model_feature_read"] is True)
    check("protocol frozen before fit", protocol["created_before_RK28_model_fit"] is True)
    check("only two coverage columns", protocol["label_free_coverage_audit"]["columns_permitted"] == ["variant_id", "sequence_5prime_300nt"])
    check("90 percent threshold frozen", protocol["label_free_coverage_audit"]["min_identity"] == 0.90)
    check("300 fits frozen", protocol["models"]["expected_model_fits_if_feasible"] == 300)
    check("four tests", len(protocol["primary_inference"]["tests"]) == 4)
    check("20k bootstrap", protocol["primary_inference"]["cluster_bootstrap"]["resamples"] == 20000)
    check("20k permutation", protocol["primary_inference"]["cluster_swap_permutation"]["permutations"] == 20000)
    check("10 seeds", len(protocol["outer_evaluation"]["sensitivity_seeds"]) == 10)
    check("CPU only", protocol["models"]["device"] == "CPU_ONLY")
    check("no untouched", protocol["scientific_boundaries"]["independent_untouched_confirmation"] is False)
    check("no full CDS", protocol["scientific_boundaries"]["complete_cds_observed"] is False)
    check("no measured structure", protocol["scientific_boundaries"]["measured_structure"] is False)
    check("no generator authorization", protocol["scientific_boundaries"]["generator_training_authorized"] is False)
    check("source hash bound", report["source_sha256"] == protocol["inputs"]["main_csv"]["sha256"])
    check("protocol hash bound", report["protocol_sha256"] == sha256(PROTOCOL))
    check("coverage script hash bound", report["coverage_script_sha256"] == sha256(REPO / "scripts/a8_rk28_audit_sequence_coverage.py"))
    check("facts hash bound", report["facts_sha256"] == sha256(FACTS))
    check("coverage feasible", report["coverage_feasible"] is True and report["model_fit_authorized"] is True)
    check("all coverage checks pass", len(report["checks"]) == 9 and all(x["pass"] for x in report["checks"]))
    check("no outcomes read", report["outcome_or_model_feature_read"] is False and report["expression_or_model_fit_performed"] is False)
    check("74 clusters", report["selected_coverage"]["clusters"] == 74)
    check("35 singleton clusters", report["selected_coverage"]["singleton_clusters"] == 35)
    check("largest cluster 12", report["selected_coverage"]["largest_cluster"] == 12)
    check("primary fold sizes", report["selected_coverage"]["primary_seed_fold_sizes"] == [30, 31, 31, 30, 30])
    check("primary fold cluster counts", report["selected_coverage"]["primary_seed_fold_cluster_counts"] == [15, 15, 16, 15, 13])
    check("facts 152 rows", len(facts) == 152)
    check("facts unique IDs", facts["variant_id"].is_unique)
    check("facts unique sequences", facts["sequence_sha256"].is_unique)
    check("facts clusters", facts["sequence_cluster_id"].nunique() == 74)
    check("facts cluster sizes", facts.groupby("sequence_cluster_id").size().max() == 12)
    check("primary fold sizes recomputed", facts.groupby("primary_seed_fold").size().sort_index().tolist() == [30, 31, 31, 30, 30])
    check("cluster wholly within fold", facts.groupby("sequence_cluster_id")["primary_seed_fold"].nunique().max() == 1)

    spec = importlib.util.spec_from_file_location("rk28_coverage", REPO / "scripts/a8_rk28_audit_sequence_coverage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    synthetic_labels = np.array([1, 1, 1, 2, 2, 3, 3, 4, 5, 6, 7, 8])
    assignment, loads, cluster_loads = module.balanced_folds(synthetic_labels, 20261222)
    check("synthetic fold sizes sum", sum(loads) == len(synthetic_labels))
    check("synthetic five folds", len(loads) == 5 and len(cluster_loads) == 5)
    synthetic_folds = np.array([assignment[int(c)] for c in synthetic_labels])
    check("synthetic whole clusters", all(np.unique(synthetic_folds[synthetic_labels == label]).size == 1 for label in np.unique(synthetic_labels)))
    check("synthetic nonempty folds", min(loads) > 0 and min(cluster_loads) > 0)
    seqs = ["AAAAAAAAAA", "AAAAATAAAA", "CCCCCCCCCC", "CCCCCTCCCC", "GGGGGGGGGG", "GGGGGTGGGG"]
    encoded = np.array([[ord(c) for c in seq] for seq in seqs], dtype=np.uint8)
    identity = (encoded[:, None, :] == encoded[None, :, :]).mean(axis=2)
    labels = fcluster(linkage(squareform(1 - identity, checks=False), method="complete"), t=0.1, criterion="distance")
    check("synthetic three clusters", len(np.unique(labels)) == 3)
    check("synthetic paired clusters", labels[0] == labels[1] and labels[2] == labels[3] and labels[4] == labels[5])
    check("synthetic distinct clusters", len({labels[0], labels[2], labels[4]}) == 3)

    payload = {
        "schema": "a8-rk28-freeze-verification-v1",
        "status": "PASS",
        "checks": checks,
        "passed": len(checks),
        "failed": 0,
        "protocol_sha256": sha256(PROTOCOL),
        "coverage_report_sha256": sha256(REPORT),
        "coverage_script_sha256": sha256(REPO / "scripts/a8_rk28_audit_sequence_coverage.py"),
        "facts_sha256": sha256(FACTS),
        "outcome_or_model_feature_read": False,
        "model_fit_performed": False,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "checks": len(checks), "model_fit_performed": False}, indent=2))


if __name__ == "__main__":
    main()
