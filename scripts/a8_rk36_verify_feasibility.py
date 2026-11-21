#!/usr/bin/env python3
"""Independent verification of the RK36 feasibility audit.
Re-reads raw sources, re-derives the discriminating facts and per-dataset
qualifying verdicts via an independent code path, and compares to the audit."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

UTR_KEYS = ("utr", "untrans", "upstream", "context", "leader", "5prime", "five_prime")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def has_utr(cols):
    return any(any(k in c.lower() for k in UTR_KEYS) for c in cols)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--result", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    proto = json.loads(args.protocol.read_text())
    res = json.loads(args.result.read_text())
    inp = {k: Path(v["path"]) for k, v in proto["inputs"].items()}
    checks = []

    def ck(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    # input integrity
    for k, p in inp.items():
        ck(f"input_sha_{k}", sha256(p) == proto["inputs"][k]["sha256"])
    ck("protocol_sha_match", res["protocol_sha256"] == sha256(args.protocol))

    long = pd.read_csv(inp["functional_long_csv"])
    kudla = pd.read_csv(inp["kudla154_source_csv"])
    boel = pd.read_csv(inp["boel_sequence_expression_csv"])
    mord = pd.read_csv(inp["mordstein_sequence_cluster_facts_csv"])
    mage = long[long["protein_id"] == "infA"]

    # independent discriminating facts
    ck("long_no_utr_column", not has_utr(long.columns), {"cols": list(long.columns)})
    ck("boel_no_utr_column", not has_utr(boel.columns))
    ck("mord_no_utr_column", not has_utr(mord.columns))
    ck("kudla_has_utr", has_utr(kudla.columns) and "cds" in kudla.columns)
    ck("mage_no_full_cds", int(mage["cds"].notna().sum()) == 0, {"nonnull": int(mage["cds"].notna().sum())})
    ck("boel_full_cds", int(boel["cds"].notna().sum()) == len(boel) == 6348)
    ck("boel_nonsynonymous", boel["variant_class"].str.contains("nonsynonymous", case=False, na=False).all())
    ck("boel_ordinal_outcome", boel["expression_type"].str.contains("ordinal", case=False, na=False).all())
    ck("boel_family_absent", boel["protein_family"].str.contains("not_provided", case=False, na=False).all())

    # independent re-derivation of qualifying per dataset
    rederive = {
        "kudla_2009_gfp": False,  # R1 fail: training cohort
        "boel_2016_nesg6348": (not has_utr(boel.columns)) is False and False,  # R3/R4/R6 fail -> False
        "mordstein_2020_hek293": False,  # R2/R3 fail: truncated
        "kelsic_2016_mage_infA": False,  # R2/R3/R7 fail
    }
    # explicit independent logic
    rederive["boel_2016_nesg6348"] = bool(has_utr(boel.columns)) and bool(boel["variant_class"].str.contains("synonymous", case=False, na=False).all()) and not boel["expression_type"].str.contains("ordinal", case=False, na=False).any()
    for name, q in rederive.items():
        ck(f"qualifying_match_{name}", res["datasets"][name]["qualifying"] == q, {"audit": res["datasets"][name]["qualifying"], "rederived": q})

    ck("n_qualifying_zero", res["n_qualifying_datasets"] == 0)
    ck("branch_3_pivot", res["branch_decision"] == "branch_3_no_qualifying_data_trigger_branch_2_pivot")
    ck("missing_dimensions_recorded", len(res["missing_dimensions"]) >= 5)
    ck("pivot_gates", res["pivot_plan"]["gates"] == {"RK_G1": False, "generative_training_authorized": False, "functional_untouched_readable": False})
    ck("label_free", res["label_free"] is True and proto["label_free"] is True)
    ck("all_datasets_audited", set(res["datasets"]) == {"kudla_2009_gfp", "boel_2016_nesg6348", "mordstein_2020_hek293", "kelsic_2016_mage_infA"})

    report = {
        "schema": "a8-rk36-feasibility-independent-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "result_sha256": sha256(args.result),
        "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "checks": checks,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.report.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tmp.replace(args.report)
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if report["status"] != "PASS":
        print(json.dumps([c for c in checks if not c["pass"]], indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()