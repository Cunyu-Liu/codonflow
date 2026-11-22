#!/usr/bin/env python3
"""A9-RK42 protocol builder: freeze the independent-data acquisition audit
protocol (R1-R7 eligibility, candidate list, decision rules) BEFORE any outcome
association or model fit. Idempotent: raises FileExistsError if already frozen.

Run: /home/codonflow-clean-env-v1/bin/python scripts/a9_rk42_build_protocol.py
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "configs", "a9_rk42_independent_data_acquisition_protocol_v1.json")

R1_R7 = {
    "R1": "independent study/host (not the Kudla training cohort)",
    "R2": "full CDS per variant (not an N-terminal segment / reporter fusion only)",
    "R3": "variant-specific native 5'UTR (>=4nt upstream of ATG), reconstructable UTR[-4:]+CDS[:38]; fixed vector/synthetic leader does NOT count",
    "R4": "fixed-protein synonymous library (amino acids invariant; cross-protein natural non-synonymous pools and amino-acid-level design factors do NOT count)",
    "R5": "protein identity + family map enabling protein/study OOD",
    "R6": "fresh continuous outcome with sufficient dynamic range (coarse ordinal does NOT count)",
    "R7": "sequence-cluster/protein/study isolation feasible + license/accession/raw SHA documentable",
}

CANDIDATES = [
    "Cambray2018", "Kosuri2013", "Goodman2013", "Mutalik2013", "Rhodius2012",
    "Salis2011", "EspahBorujeni2014_2017", "deBoer2020", "Lind2020",
]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    if os.path.exists(OUT):
        raise FileExistsError(f"protocol already frozen: {OUT}")
    directive = os.path.join(ROOT, "configs", "a9_positive_core_directive_v1.json")
    prereg = os.path.join(ROOT, "docs", "handover", "A9_RK42_PREREGISTRATION.md")
    protocol = {
        "schema": "a9-rk42-independent-data-acquisition-protocol-v1",
        "status": "FROZEN_BEFORE_OUTCOME_ASSOCIATION",
        "created_date": "2026-11-22",
        "timezone": "Asia/Shanghai",
        "task": "A9-RK42 phase B independent-data acquisition audit (public-first, label-free)",
        "eligibility_requirements": R1_R7,
        "qualify_iff": "all R1-R7 PASS",
        "candidates": CANDIDATES,
        "decision_rules": {
            "ge1_qualifying": "phase B2 acquire/clean/SHA/preregistered OOD split/leakage audit -> phase C",
            "zero_qualifying": "phase B3 record missing dimensions + prospective DBTL/wet-lab design; wet-lab budget and timeline extension REQUIRE user approval; measurement protocol frozen before reading outcomes",
            "raw_inaccessible": "record real reason (paywall/Cloudflare/throttle/no accession); never guess from abstract; raw-unverified source cannot be PASS",
            "strategic_option_requires_user": "whether to authorize a relaxed R3 (fixed leader + N-terminal synonymous editing window) for the FUNCTIONAL benchmark only, keeping strict R3 for start-structure transport claims; do NOT unilaterally relax frozen R1-R7",
        },
        "boundaries": {
            "historical_MAGE_functional_untouched_frozen": True,
            "historical_frozen_artifacts_unchanged": True,
            "no_model_fit_no_outcome_association_no_generator_training_in_this_audit": True,
            "RK_G1_authorized_for_phase_C_only": True,
            "public_retrospective_vs_prospective_DBTL_strictly_separated": True,
        },
        "input_sha256": {
            "configs/a9_positive_core_directive_v1.json": sha(directive),
            "docs/handover/A9_RK42_PREREGISTRATION.md": sha(prereg),
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(protocol, f, indent=2, sort_keys=True)
    print("FROZEN", OUT)
    print("protocol_sha256", sha(OUT))


if __name__ == "__main__":
    main()