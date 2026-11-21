#!/usr/bin/env python3
"""RK36 label-free independent-transport feasibility audit.
Reads schema/coverage/identity metadata from frozen inputs (no outcome-effect),
evaluates R1-R7 per dataset with evidence, and emits the branch decision."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

UTR_KEYS = ("utr", "untrans", "upstream", "context", "leader", "5prime", "five_prime")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def utr_cols(cols):
    return [c for c in cols if any(k in c.lower() for k in UTR_KEYS)]


def req(passed, evidence):
    return {"verdict": "PASS" if passed else "FAIL", "evidence": evidence}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    proto = json.loads(args.protocol.read_text())
    inp = {k: Path(v["path"]) for k, v in proto["inputs"].items()}
    long = pd.read_csv(inp["functional_long_csv"])
    kudla = pd.read_csv(inp["kudla154_source_csv"])
    boel = pd.read_csv(inp["boel_sequence_expression_csv"])
    mord = pd.read_csv(inp["mordstein_sequence_cluster_facts_csv"])
    mage = long[long["protein_id"] == "infA"]

    datasets = {}

    # Kudla 2009 GFP — training cohort reference
    k_utr = utr_cols(kudla.columns)
    datasets["kudla_2009_gfp"] = {
        "n_rows": int(len(kudla)), "host": "Escherichia coli (Kudla GFP cohort)",
        "requirements": {
            "R1_independent_study_host": req(False, "Kudla is the RK27/RK32/RK34/RK35 training cohort, not independent."),
            "R2_full_cds_per_variant": req("cds" in kudla.columns and kudla["cds"].notna().all(), f"cds column present; nonnull={int(kudla['cds'].notna().sum())}/{len(kudla)}."),
            "R3_native_variant_specific_5utr": req(bool(k_utr), f"UTR-like columns={k_utr}; utr_5prime 144 nt + sequenceWithUtr 864 nt available."),
            "R4_fixed_protein_synonymous_library": req(True, "Fixed GFP protein synonymous library."),
            "R5_protein_identity_family_map": req(True, "Single GFP protein identity; exact_cds_group present."),
            "R6_fresh_continuous_outcome": req("log10_expression" in kudla.columns, "Continuous log10_expression outcome."),
            "R7_isolation_and_provenance": req(True, "Whole-cluster OOD frozen (RK27); raw SHA documented."),
        },
    }

    # Boel 2016 — independent study, full CDS, but non-synonymous cross-protein, no UTR, ordinal
    b_utr = utr_cols(boel.columns)
    b_vc = sorted(boel["variant_class"].dropna().unique().tolist())
    b_et = sorted(boel["expression_type"].dropna().unique().tolist())
    b_fam = sorted(boel["protein_family"].dropna().unique().tolist())
    b_fam_absent = all(("not_provided" in f) or ("UNASSIGNED" in f) for f in b_fam)
    datasets["boel_2016_nesg6348"] = {
        "n_rows": int(len(boel)), "host": sorted(boel["host"].dropna().unique().tolist()),
        "requirements": {
            "R1_independent_study_host": req(True, "Independent Boel 2016 study (E. coli BL21(DE3) pMGK-argU), distinct from Kudla."),
            "R2_full_cds_per_variant": req(boel["cds"].notna().all(), f"cds nonnull={int(boel['cds'].notna().sum())}/{len(boel)}; sequence_status=full_cds_with_terminal_stop_and_c_terminal_tag."),
            "R3_native_variant_specific_5utr": req(bool(b_utr), f"UTR-like columns={b_utr}; vector='pET plasmid; T7 RNA polymerase; C-terminal LEHHHHHH' (fixed vector leader, not variant-specific native UTR; not captured)."),
            "R4_fixed_protein_synonymous_library": req(False, f"variant_class={b_vc}; cross-protein natural NON-synonymous pool, not a fixed-protein synonymous library."),
            "R5_protein_identity_family_map": req(not b_fam_absent, f"protein_id present but protein_family={b_fam[:2]}...; split_assignment=UNASSIGNED_FAMILY_MAP_REQUIRED; family map absent."),
            "R6_fresh_continuous_outcome": req(False, f"expression_type={b_et}; coarse ordinal 0-5 total protein expression score, not continuous."),
            "R7_isolation_and_provenance": req(False, "leakage_risk='not a fixed-protein synonymous library; family mapping absent'; protein/study isolation not feasible without family map."),
        },
    }

    # Mordstein 2020 HEK293 — cross-host synonymous, but observed-R1 truncated (no ATG/upstream)
    m_utr = utr_cols(mord.columns)
    datasets["mordstein_2020_hek293"] = {
        "n_rows": int(len(mord)), "host": "Homo sapiens HEK293 (cross-host)",
        "requirements": {
            "R1_independent_study_host": req(True, "Independent Mordstein 2020 HEK293 study, cross-host vs Kudla E. coli."),
            "R2_full_cds_per_variant": req(False, "observed-R1 recovered reads begin at CDS position 4; full CDS with start ATG not available (RK28/RK33 established)."),
            "R3_native_variant_specific_5utr": req(bool(m_utr), f"UTR-like columns={m_utr}; start ATG (CDS 1-3) and upstream 4 nt absent, cannot reconstruct UTR[-4:]+CDS[:38]."),
            "R4_fixed_protein_synonymous_library": req(True, "Synonymous variant library (RK28 observed-R1)."),
            "R5_protein_identity_family_map": req(True, "Protein identity + sequence-cluster facts frozen (RK28)."),
            "R6_fresh_continuous_outcome": req(True, "Continuous relative fitness outcome (RK28)."),
            "R7_isolation_and_provenance": req(True, "Whole-sequence-cluster OOD frozen (RK28); SRA accession PRJNA596086 documented."),
        },
    }

    # Kelsic 2016 MAGE infA — frozen functional untouched, no full construct
    mg_ss = sorted(mage["sequence_status"].dropna().unique().tolist())
    datasets["kelsic_2016_mage_infA"] = {
        "n_rows": int(len(mage)), "host": sorted(mage["host"].dropna().unique().tolist()),
        "requirements": {
            "R1_independent_study_host": req(True, "Independent Kelsic 2016 MAGE infA study (E. coli chromosomal infA)."),
            "R2_full_cds_per_variant": req(False, f"sequence_status={mg_ss}; cds nonnull={int(mage['cds'].notna().sum())}/{len(mage)}; full construct not in supplement."),
            "R3_native_variant_specific_5utr": req(False, "No full construct sequence, hence no native 5'UTR reconstructable."),
            "R4_fixed_protein_synonymous_library": req(True, "Fixed infA single-codon / codon-pair synonymous variants."),
            "R5_protein_identity_family_map": req(True, "Single infA protein identity."),
            "R6_fresh_continuous_outcome": req(True, "Continuous relative fitness (rich/minimal) outcome."),
            "R7_isolation_and_provenance": req(False, "FUNCTIONAL UNTOUCHED: 19072 rows / 13569 signature groups frozen; reading outcomes for positives is forbidden by project gate."),
        },
    }

    for name, d in datasets.items():
        d["qualifying"] = all(r["verdict"] == "PASS" for r in d["requirements"].values())
        d["failed_requirements"] = [k for k, r in d["requirements"].items() if r["verdict"] == "FAIL"]

    n_qual = sum(d["qualifying"] for d in datasets.values())
    if n_qual >= 1:
        branch = "branch_1_independent_transport_preregistration"
        decision = "At least one independent dataset qualifies; draft a strict transport preregistration."
    else:
        branch = "branch_3_no_qualifying_data_trigger_branch_2_pivot"
        decision = ("No available independent dataset can reconstruct the exact Kudla native start window "
                    "UTR[-4:]+CDS[:38] for a fixed-protein synonymous transport test with fresh continuous outcome. "
                    "Record missing dimensions and formally trigger the branch-2 pivot to data-supported functional "
                    "sequence models / translation dynamics; stop treating start-aware MFE as the core model innovation.")
    missing_dimensions = [
        "Fixed-protein synonymous library (Boel is cross-protein non-synonymous).",
        "Native variant-specific 5'UTR (>=4 nt upstream of ATG) captured per construct (no UTR column in any available source; Mordstein truncated; MAGE no full construct).",
        "Full CDS with start ATG in an independent cross-host study (Mordstein observed-R1 starts at CDS position 4).",
        "Fresh continuous expression/fitness outcome with adequate dynamic range (Boel is ordinal 0-5).",
        "Protein family map for protein/study OOD isolation (Boel family map absent).",
        "Documented license/accession/raw SHA for a qualifying construct-level dataset.",
    ]
    pivot_plan = {
        "trigger": "branch_2 (no qualifying independent transport data; RK23 Boel protein-OOD 0/4 and RK25 mechanism 0/2 already constitute cross-protein/cross-host transport failure).",
        "direction": "Data-supported functional sequence modeling / translation dynamics, not start-aware MFE as core innovation.",
        "candidate_next_task_RK37": "Preregistered translation-speed / functional prediction benchmark on available bounded clean data (e.g., RiboMIMO), with strong constant/ridge controls, CAI/GC and full-proxy MFE baselines, general sequence models, protein/study OOD Spearman/RMSE/top-k enrichment; SOTA requires paired 95% CI lower>0, multiplicity pass, 100% legality, full cost.",
        "gates": {"RK_G1": False, "generative_training_authorized": False, "functional_untouched_readable": False},
        "data_to_seek": "Public construct-level synonymous datasets with native full UTR-CDS and continuous fresh outcome in an independent host/study (e.g., cross-host synonymous fitness with full construct sequences, or measured-structure synonymous data); Cambray 2018 fixed-UTR constructs require raw construct verification before any transport claim.",
    }

    report = {
        "schema": "a8-rk36-independent-transport-feasibility-result-v1",
        "status": "FEASIBILITY_AUDIT_COMPLETE_LABEL_FREE",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": sha256(args.protocol),
        "label_free": True,
        "input_sha256": {k: sha256(p) for k, p in inp.items()},
        "datasets": datasets,
        "n_qualifying_datasets": n_qual,
        "branch_decision": branch,
        "decision": decision,
        "missing_dimensions": missing_dimensions,
        "pivot_plan": pivot_plan,
        "non_claims": "Feasibility/eligibility audit only; no transport effect, no SOTA, no mechanism claim; functional untouched not read for outcomes; no generative training.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.report.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tmp.replace(args.report)
    print(json.dumps({"status": report["status"], "n_qualifying": n_qual, "branch": branch,
                      "qualifying": {k: v["qualifying"] for k, v in datasets.items()},
                      "failed": {k: v["failed_requirements"] for k, v in datasets.items()}}, indent=2))


if __name__ == "__main__":
    main()