#!/usr/bin/env python3
"""Freeze the RK36 label-free independent-transport feasibility audit protocol.
Writes requirements R1-R7, input paths + SHA256, and the branch decision rule.
Status FROZEN_BEFORE_OUTCOME_ASSOCIATION: no outcome-effect is read by the audit."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/codonflow-a8-rk")
TEAMS = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031")
INPUTS = {
    "functional_long_csv": TEAMS / "rk_functional/clean/functional_long.csv",
    "kudla154_source_csv": TEAMS / "rk21/kudla_recovery_v1/derived/kudla154_source.csv",
    "boel_sequence_expression_csv": TEAMS / "rk_functional/clean/boel_2016_nesg6348/sequence_expression.csv",
    "mordstein_sequence_cluster_facts_csv": TEAMS / "rk28/mordstein_observed_r1_sequence_cluster_ood_v1/sequence_cluster_facts.csv",
}
REQUIREMENTS = {
    "R1_independent_study_host": "Study/host independent of the Kudla training cohort (not the same GFP cohort).",
    "R2_full_cds_per_variant": "Full CDS available for every variant.",
    "R3_native_variant_specific_5utr": "Native variant-specific 5'UTR (>=4 nt upstream of ATG) available to reconstruct UTR[-4:]+CDS[:38] with the same construct geometry as Kudla; a fixed vector leader substitution does not qualify.",
    "R4_fixed_protein_synonymous_library": "Fixed-protein synonymous codon library; a cross-protein natural non-synonymous pool cannot test the synonymous initiation-structure mechanism.",
    "R5_protein_identity_family_map": "Clear protein identity plus family map enabling protein/study OOD isolation.",
    "R6_fresh_continuous_outcome": "Fresh continuous expression/fitness outcome with adequate dynamic range; a coarse ordinal score does not qualify.",
    "R7_isolation_and_provenance": "Sequence-cluster/protein/study isolation feasible; license/accession/raw SHA documentable.",
}
DECISION_RULE = {
    "qualifying": "A dataset qualifies iff R1-R7 all PASS.",
    "branch_1": "If >=1 dataset qualifies: draft a strict transport preregistration (data, full CDS/UTR, host/assay/batch, structure definition, cleaning, dynamic range, isolation, simple/full-proxy/strongest-external baseline, primary endpoint, whole-cluster stats, Holm, power, three conclusions).",
    "branch_3": "If 0 datasets qualify: record each dataset's failed requirements and missing dimensions; formally trigger branch 2 pivot.",
    "branch_2_pivot": "Stop treating start-aware MFE as the core model innovation; pivot to data-supported functional sequence models / translation dynamics with strong baselines, OOD and SOTA criteria.",
    "forbidden": "No faking transport with a host/assay/coverage-mismatched dataset; no reading functional untouched (MAGE 19072 frozen) for positives; no generative training (RK-G1=false).",
}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    out = ROOT / "configs/a8_rk36_independent_transport_feasibility_protocol_v1.json"
    if out.exists():
        raise FileExistsError(out)
    inputs = {}
    for k, p in INPUTS.items():
        inputs[k] = {"path": str(p), "sha256": sha256(p), "exists": p.exists()}
    protocol = {
        "schema": "a8-rk36-independent-transport-feasibility-protocol-v1",
        "status": "FROZEN_BEFORE_OUTCOME_ASSOCIATION",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "label_free": True,
        "audit_reads": "schema/coverage/identity metadata only; no outcome-effect correlation",
        "requirements": REQUIREMENTS,
        "decision_rule": DECISION_RULE,
        "datasets_audited": ["kudla_2009_gfp", "boel_2016_nesg6348", "mordstein_2020_hek293", "kelsic_2016_mage_infA"],
        "inputs": inputs,
        "exact_start_window": "UTR[-4:]+CDS[:38] (42 nt, dangles=2, 37C)",
        "gates": {"RK_G1": False, "functional_untouched_readable": False, "generative_training_authorized": False},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n")
    tmp.replace(out)
    print(json.dumps({"protocol": str(out), "sha256": sha256(out), "status": protocol["status"],
                      "inputs": {k: v["sha256"][:12] for k, v in inputs.items()}}, indent=2))


if __name__ == "__main__":
    main()