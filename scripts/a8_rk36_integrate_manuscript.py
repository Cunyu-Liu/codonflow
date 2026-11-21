#!/usr/bin/env python3
"""Insert RK36 section 6.47 (Table 27 feasibility matrix + evidence anchor) before section 7.
Table 27 and counts are rendered from the frozen feasibility result. Idempotent guard;
preserves all prior content; self-audits the insertion."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

REQ_ORDER = ["R1_independent_study_host", "R2_full_cds_per_variant", "R3_native_variant_specific_5utr",
             "R4_fixed_protein_synonymous_library", "R5_protein_identity_family_map",
             "R6_fresh_continuous_outcome", "R7_isolation_and_provenance"]
REQ_SHORT = ["R1 indep.", "R2 full CDS", "R3 native UTR", "R4 synonymous", "R5 family map", "R6 continuous", "R7 isolation"]
DS_ORDER = ["kudla_2009_gfp", "boel_2016_nesg6348", "mordstein_2020_hek293", "kelsic_2016_mage_infA"]
DS_LABEL = {"kudla_2009_gfp": "Kudla 2009 GFP (E. coli)", "boel_2016_nesg6348": "Boel 2016 (E. coli BL21)",
            "mordstein_2020_hek293": "Mordstein 2020 (HEK293)", "kelsic_2016_mage_infA": "Kelsic 2016 MAGE infA"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_section(res: dict, proto_sha: str, result_sha: str, indep_sha: str,
                  freeze_commit: str, science_commit: str) -> str:
    rows = []
    for ds in DS_ORDER:
        d = res["datasets"][ds]
        cells = ["Pass" if d["requirements"][r]["verdict"] == "PASS" else "Fail" for r in REQ_ORDER]
        qual = "Yes" if d["qualifying"] else "No"
        rows.append("| " + DS_LABEL[ds] + " | " + " | ".join(cells) + " | " + qual + " |")
    matrix = "\n".join(rows)
    failed_lines = "\n".join(
        f"- **{DS_LABEL[ds]}**: fails " + ", ".join(res["datasets"][ds]["failed_requirements"]) + "."
        for ds in DS_ORDER)
    missing = "\n".join(f"- {m}" for m in res["missing_dimensions"])
    n_qual = res["n_qualifying_datasets"]
    return f"""### 6.47 No available independent dataset can reconstruct the exact start window, triggering a pivot away from start-aware MFE as the core innovation

The handover protocol (§3–§4) designates RK34 as the terminal same-cohort window ablation and requires that subsequent work either pursue a genuinely independent transport confirmation or pivot. RK34 established a joint exact-context increment within Kudla without separable upstream or start-codon contributions, and RK35 showed that the natural truncated RK33 window still carries the increment within Kudla, so coverage alone does not explain the cross-study transport failure. Together these trigger §4 branch 1: seek an independent, full-CDS, protein-identified functional dataset on which the same exact start window can be preregistered for transport. RK36 executes the mandated first step of that branch — a label-free feasibility audit, frozen before any outcome association, asking whether any available public dataset can support a strict independent transport experiment. The audit reads only schema, sequence-coverage and identity metadata; it computes no outcome-effect correlation and reads no functional-untouched outcome.

Seven eligibility requirements were frozen in `configs/a8_rk36_independent_transport_feasibility_protocol_v1.json`: R1 an independent study/host from the Kudla training cohort; R2 full CDS per variant; R3 a native variant-specific 5′ UTR (at least four nucleotides upstream of the ATG) so that `UTR[-4:]+CDS[:38]` can be reconstructed with the same construct geometry as Kudla (a fixed vector leader substitution does not qualify); R4 a fixed-protein synonymous library (a cross-protein natural non-synonymous pool cannot test the synonymous initiation-structure mechanism); R5 clear protein identity plus a family map for protein/study out-of-distribution isolation; R6 a fresh continuous expression/fitness outcome with adequate dynamic range (a coarse ordinal score does not qualify); and R7 feasible sequence-cluster/protein/study isolation with documentable license, accession and raw SHA. A dataset qualifies only if all seven pass. Four datasets were audited against the unified functional long table (25,420 rows, 31 columns) and the raw sources: the Kudla 2009 GFP recovery, Boel 2016 NESG6348, Mordstein 2020 HEK293 observed R1, and Kelsic 2016 MAGE infA.

**No dataset qualified (0/4); the prespecified branch-3 decision was triggered (Table 27).** The unified long table contains no 5′ UTR column at all. Kudla has the full native UTR and CDS but is the training cohort (R1 fails). Boel 2016 is an independent study with full CDS and many protein identities, yet it is a cross-protein natural *non-synonymous* pool with an absent family map, an ordinal 0–5 total-protein expression score, a C-terminal tag and a fixed pET/T7 vector leader rather than a captured variant-specific native UTR (R3–R7 fail). Mordstein 2020 is cross-host and synonymous with a continuous fitness outcome, but its observed R1 reads begin at CDS position 4, lacking the start ATG and upstream four nucleotides, so the exact window cannot be reconstructed (R2–R3 fail; consistent with the RK28/RK33 0/12 negatives). Kelsic 2016 MAGE infA has no full construct sequence in the supplement and is frozen functional-untouched (R2–R3, R7 fail).

**Table 27**

*Independent-Transport Eligibility Matrix (label-free; Pass/Fail against frozen R1–R7)*

| Dataset | { " | ".join(REQ_SHORT) } | Qualifies |
|---|---|---|---|---|---|---|---|---|
{matrix}

*Note.* R1 independent study/host; R2 full CDS per variant; R3 native variant-specific 5′ UTR (≥4 nt upstream of ATG); R4 fixed-protein synonymous library; R5 protein identity + family map; R6 fresh continuous outcome; R7 isolation + provenance. A dataset qualifies only if all seven pass. The unified functional long table has no 5′ UTR column.

Per-dataset failed requirements:

{failed_lines}

Because no independent dataset can reconstruct the exact Kudla native start window for a fixed-protein synonymous transport test with a fresh continuous outcome, §4 branch 3 applies: the missing dimensions are recorded rather than papered over with a host/assay/coverage-mismatched dataset. The missing dimensions are:

{missing}

This formally triggers the §4 branch-2 pivot. The cross-protein and cross-host transport failures already observed (RK23 Boel protein-OOD 0/4 at Holm p = 1; RK25 mechanism 0/2) corroborate that start-aware MFE is not a portable core innovation on the available data. The project therefore stops treating start-aware MFE as the core model innovation and pivots to data-supported functional sequence modeling and translation dynamics. The concrete next preregistered task (RK37) is a translation-speed / functional prediction benchmark on available bounded clean data (for example RiboMIMO), with strong constant and Ridge controls, CAI/GC and full-proxy MFE baselines, and general sequence models, evaluated under protein/study out-of-distribution Spearman, RMSE and top-k enrichment; a SOTA claim will require a paired 95% confidence-interval lower bound above zero, multiplicity control, 100% legality and full cost accounting. Construct-level synonymous datasets with native full UTR–CDS and continuous fresh outcomes in an independent host/study remain the data to seek before any future transport claim; Cambray 2018 fixed-UTR constructs require raw construct verification first.

An independently written verification re-read the raw sources, re-derived the discriminating facts (no UTR column in the long table, Boel or Mordstein; Kudla UTR present; MAGE zero full CDS; Boel full CDS, non-synonymous, ordinal, family absent) and re-derived each dataset's qualifying verdict through a separate code path; it passed 24/24 checks and confirmed 0 qualifying datasets and the branch-3 pivot decision. This is a feasibility/eligibility audit only: it makes no transport-effect, SOTA or mechanism claim, reads no functional-untouched outcome for positives, and authorizes no generative training (RK-G1 remains false).

::: {{.evidence-anchor #sec-6-47}}
| Field | Evidence |
|---|---|
| Code commits | `{freeze_commit}` (protocol freeze + label-free audit scripts); `{science_commit}` (feasibility result + independent verification) |
| Code | `scripts/a8_rk36_build_protocol.py`; `scripts/a8_rk36_feasibility_audit.py`; independent `scripts/a8_rk36_verify_feasibility.py` |
| Protocol | `configs/a8_rk36_independent_transport_feasibility_protocol_v1.json` |
| Results | `audits/20261122/RK36/rk36_feasibility_result_v1.json`; `rk36_feasibility_independent_v1.json` |
| SHA256 | protocol `{proto_sha}`; result `{result_sha}`; independent `{indep_sha}` |
| Analysis | Label-free audit of 4 datasets against frozen R1–R7; unified long table 25,420 rows / 31 columns; {n_qual} qualifying datasets; independent verification 24/24 |
| Scope | Feasibility/eligibility only; branch-3 record + branch-2 pivot trigger; no transport effect, SOTA, mechanism, functional/protein OOD, generator or wet-lab claim; functional untouched not read; RK-G1 false |
:::

"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", type=Path, required=True)
    ap.add_argument("--result", type=Path, required=True)
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--independent", type=Path, required=True)
    ap.add_argument("--freeze-commit", required=True)
    ap.add_argument("--science-commit", required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    res = json.loads(args.result.read_text())
    section = build_section(res, sha256(args.protocol), sha256(args.result), sha256(args.independent),
                            args.freeze_commit, args.science_commit)
    original = args.manuscript.read_text()
    if "### 6.47" in original or "#sec-6-47" in original:
        raise ValueError("RK36 section already present; refusing duplicate insertion")
    marker = "## 7. Discussion"
    if marker not in original:
        raise ValueError("section 7 marker not found")
    before, after = original.split(marker, 1)
    if "### 6.46" not in before:
        raise ValueError("RK35 section 6.46 not present before insertion point")
    new = before + section + marker + after
    assert new.replace(section, "", 1) == original
    args.manuscript.write_text(new)
    checks = []

    def check(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    reread = args.manuscript.read_text()
    check("section_6_47_present", "### 6.47" in reread)
    check("table_27_present", "**Table 27**" in reread)
    check("evidence_anchor_present", "#sec-6-47" in reread)
    check("section_6_46_intact", "### 6.46" in reread and "#sec-6-46" in reread)
    check("section_7_intact", "## 7. Discussion" in reread)
    check("prior_content_preserved", reread.replace(section, "", 1) == original)
    check("branch_decision_present", "branch-3" in reread and "branch-2 pivot" in reread)
    check("zero_qualifying_present", "0/4" in reread)
    check("pivot_task_present", "RK37" in reread)
    check("result_sha_present", sha256(args.result) in reread)
    check("section_order", reread.index("### 6.46") < reread.index("### 6.47") < reread.index("## 7. Discussion"))
    check("no_chinese", not any("\u4e00" <= ch <= "\u9fff" for ch in section))
    report = {
        "schema": "a8-rk36-manuscript-integration-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "manuscript": str(args.manuscript),
        "lines_before": len(original.splitlines()), "lines_after": len(reread.splitlines()),
        "sha256_before": hashlib.sha256(original.encode()).hexdigest(),
        "sha256_after": sha256(args.manuscript),
        "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "checks": checks,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.report.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tmp.replace(args.report)
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()