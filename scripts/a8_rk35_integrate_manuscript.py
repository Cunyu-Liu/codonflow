#!/usr/bin/env python3
"""Insert RK35 section 6.46 (Tables 25-26 + evidence anchor) before section 7.
Idempotent guard; preserves all prior content; self-audits the insertion."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SECTION = """### 6.46 The natural RK33 truncated window retains the Kudla structure increment, so coverage alone does not explain cross-study transport failure

RK32 localized the Kudla structural increment to a start-aware 42-nt window (last four 5′ UTR nucleotides + start ATG + CDS positions 4–38), RK33 found no increment for a truncated CDS4–45 window in Mordstein observed R1, and RK34 showed that the exact local context adds a joint increment within Kudla while a matched N-masked factorial ablation did not separably identify upstream or start-codon contributions. RK35 asked a complementary transport question on the same frozen cohort: does the *natural* RK33 slice CDS[3:45] (1-based CDS4–45, no start ATG and no upstream UTR) still carry the local-structure increment within Kudla, and does exact start-aware coverage beat it? If the truncated natural window retains the increment, then missing coverage cannot be the sole explanation of the RK28/RK33 cross-study negatives, and host/assay/study-level factors become the primary candidates. This was a retrospective, outcome-known, fixed-GFP analysis rather than an independent confirmation, biological perturbation, or cross-host transport test. The 154 measurement rows, 150 exact-CDS groups, 37 sequence clusters, seed–fold assignments, simple CAI/GC/GC3 features, Ridge and histogram gradient-boosting models, and whole-cluster inference remained fixed.

Five arms were compared. Simple (CAI/GC/GC3) and exact_local (UTR[-4:]+CDS[:38], dangles=2) were reused from accepted RK32 out-of-fold predictions after hash, fold-identity and null-baseline gates. Three natural unmasked windows were newly fitted: cds_start_local (CDS[0:42], includes ATG, no UTR), trunc_local (CDS[3:45], excludes ATG and UTR, dangles=2), and trunc_local_d0 (the same truncated window at dangles=0, the RK33 prediction definition, prespecified as a secondary sensitivity). ViennaRNA at 37 °C supplied each MFE. Three new arms × two models × 50 folds gave 300 new fits; with 200 reused fits this yielded 500 evaluated fits. Unlike RK34's equal-length N-masked design with a fixed CDS4–38 body, these natural windows shift the CDS body, so the component contrasts (cds_start_local versus trunc_local, exact_local versus cds_start_local) are body-confounded and were kept descriptive; clean upstream/start decomposition is deferred to RK34.

Two primary paired contrasts each contained two models × two metrics, giving eight confirmatory endpoints under a unified Holm correction across those eight tests: trunc_vs_simple (trunc_local minus simple) and exact_vs_trunc (exact_local minus trunc_local). A consistency gate required exact_vs_simple to reproduce the frozen RK32 vienna_local observed effect, confidence limits, raw permutation p and seed effects within 1e-12 and to pass its own four-test Holm family; failure would stop scientific interpretation. An endpoint passed only with a positive observed effect, a positive lower 95% whole-cluster bootstrap confidence limit, Holm-adjusted cluster-swap p < 0.05, and at least eight positive seeds; a contrast required all four endpoints. Inference used 20,000 whole-cluster bootstrap resamples (seed 20261321) and 20,000 cluster-sign-swap permutations (seed 20261322) on the primary-seed out-of-fold predictions. Twelve secondary endpoints (atg_vs_trunc, exact_vs_atg, trunc_d0_vs_simple) were computed with their own descriptive Holm family but carried no gate and did not enter the decision.

**The consistency gate reproduced RK32 exactly (maximum absolute delta 0), and the natural truncated window passed trunc_vs_simple 4/4 (Table 25).** Within Kudla, trunc_local improved Ridge Spearman by 0.735912 (95% CI [0.269426, 0.883119]) and HistGB Spearman by 0.365595 ([0.215323, 0.493275]) over simple, with MSE improvements of 0.112439 and 0.101934; all four endpoints had 10/10 positive seeds and Holm p ≤ 0.043398. The exact window beat the truncated window for Ridge (exact_vs_trunc Spearman 0.248771, MSE 0.044487, both passing) but not for HistGB (Spearman 0.037152, CI [-0.058908, 0.101375], Holm p 0.356982; MSE 0.002329, CI [-0.020657, 0.017988], Holm p 0.770161), so exact_vs_trunc passed only 2/4. Because trunc_vs_simple passed while exact_vs_trunc did not pass all four, the prespecified decision was D1: `RK33_COVERAGE_RETAINS_INCREMENT_WITHIN_KUDLA_RETROSPECTIVELY`. The natural RK33 coverage therefore retains the increment within Kudla; coverage is not necessary for the increment to exist, and the RK28/RK33 cross-study negatives cannot be attributed to coverage alone. Host, assay and study-level differences become the leading candidates for the transport failure.

**Table 25**

*Confirmatory Paired Endpoints for the Natural-Window Coverage Transport Test*

| Comparison | Model | Metric | Effect | 95% CI | Raw *p* | Holm *p* | Positive seeds | Pass |
|---|---|---|---:|---|---:|---:|---:|---|
| trunc−simple | Ridge | Spearman | 0.735912 | [0.269426, 0.883119] | 0.001850 | 0.011099 | 10/10 | Yes |
| trunc−simple | Ridge | MSE improvement | 0.112439 | [0.037299, 0.157190] | 0.010849 | 0.043398 | 10/10 | Yes |
| exact−trunc | Ridge | Spearman | 0.248771 | [0.096534, 0.433405] | 0.001850 | 0.011099 | 10/10 | Yes |
| exact−trunc | Ridge | MSE improvement | 0.044487 | [0.020955, 0.073430] | 0.012349 | 0.043398 | 10/10 | Yes |
| trunc−simple | HistGB | Spearman | 0.365595 | [0.215323, 0.493275] | 0.000250 | 0.001750 | 10/10 | Yes |
| trunc−simple | HistGB | MSE improvement | 0.101934 | [0.048890, 0.135677] | 0.000100 | 0.000800 | 10/10 | Yes |
| exact−trunc | HistGB | Spearman | 0.037152 | [-0.058908, 0.101375] | 0.178491 | 0.356982 | 10/10 | No |
| exact−trunc | HistGB | MSE improvement | 0.002329 | [-0.020657, 0.017988] | 0.770161 | 0.770161 | 10/10 | No |

*Note.* Effects are the first arm minus the comparator; MSE improvement is comparator MSE minus arm MSE. CI is the 95% whole-cluster bootstrap interval. Raw and Holm-adjusted *p*-values use 20,000 cluster-swap permutations; Holm is across the eight primary tests. The gate contrast exact_vs_simple reproduced RK32 vienna_local within 1e-12 (Ridge Spearman 0.984683, HistGB Spearman 0.402747) and passed 4/4.

Primary-seed absolute performance gives context (Table 26). Ridge simple features alone gave Spearman −0.318413; adding the truncated natural window raised this to 0.417499 and the exact window to 0.666270. HistGB rose from 0.302424 (simple) to 0.668019 (truncated) and 0.705171 (exact). The truncated dangles=0 arm also carried signal (Ridge 0.314038; HistGB 0.538153), consistent with the RK33 prediction definition retaining within-Kudla information. The negative Ridge simple Spearman again warns that a large paired increment does not imply that either the backbone or the resulting predictor is universally strong.

**Table 26**

*Absolute Held-Out Performance for Primary Seed 20261221*

| Model | Arm | Spearman | MSE |
|---|---|---:|---:|
| Intercept | null | -0.367234 | 0.194471 |
| Ridge | simple | -0.318413 | 0.257149 |
| Ridge | exact local d2 | 0.666270 | 0.100223 |
| Ridge | CDS-start d2 | 0.307810 | 0.156892 |
| Ridge | trunc CDS4-45 d2 | 0.417499 | 0.144710 |
| Ridge | trunc CDS4-45 d0 | 0.314038 | 0.163578 |
| HistGB | simple | 0.302424 | 0.198658 |
| HistGB | exact local d2 | 0.705171 | 0.094394 |
| HistGB | CDS-start d2 | 0.602022 | 0.117825 |
| HistGB | trunc CDS4-45 d2 | 0.668019 | 0.096724 |
| HistGB | trunc CDS4-45 d0 | 0.538153 | 0.133087 |

*Note.* The truncated dangles=0 arm is a prespecified sensitivity analysis shown for completeness, not a replacement for the confirmatory dangles=2 comparisons.

The secondary descriptive contrasts illustrate why natural-window component comparisons cannot substitute for the matched RK34 decomposition. atg_vs_trunc was negative for both models (Ridge Spearman −0.109689, HistGB −0.065997, 0/10 positive seeds): shifting the body to CDS1–42 while adding ATG did not help relative to CDS4–45, a body-position effect rather than evidence about ATG itself. exact_vs_atg was positive for Ridge (Spearman 0.358460, Holm p 0.002400) but not HistGB, and trunc_d0_vs_simple passed for Ridge Spearman (0.632451) with mixed HistGB results. These twelve endpoints are body-confounded, carry no gate, and are reported only descriptively; the clean upstream/start separation remains the RK34 matched N-mask result.

An independently written raw-source implementation reconstructed the windows, energies, clusters, folds, all 500 fits, seed statistics, 24 contrast tests and 48 inference arrays. Verifier v2 passed 39/39 checks; the maximum absolute prediction difference was 1.33e-15, the maximum inference-array difference 1.80e-16, and the consistency-gate delta 0. Two verifier-only corrections were made after freezing, without changing any scientific value or tolerance: the null-baseline arm label that pandas parses as NaN on CSV readback was canonicalized (mirroring the RK32 verifier), and the training-log check was matched to the per-fit 300-row logging design. The initial verifier v1 failure (37/39) is retained. A no-hardlinks clean checkout of `9c26dcabeb82147ea12d9b58a5c0549d46c5a10d` then repeated production and independent verification; the comparison passed 12/12 checks with all six production CSV files byte-identical, all 50 inference arrays exact, and all result scientific fields equal. The full project suite at the frozen worktree reported 453 passed, one skipped and zero failed; the RK35 unit suite passed 15/15. Production and independent wall times were 166.54 s and 185.09 s.

These findings support only a retrospective, fixed-Kudla, sequence-cluster-OOD conclusion: the natural truncated RK33 coverage retains the structure increment within Kudla, so coverage alone does not explain the cross-study transport failure. The experiment does not identify the host or assay responsible (it only rules out coverage as the sole explanation), establish a causal mechanism, validate measured structure, or demonstrate independent cross-host transport, functional or protein OOD, external SOTA, time-matched generation quality, or RK-G1. Because the natural windows shift the CDS body, no separable upstream or start-codon claim is made here. The next discriminating step is a cross-host, full-coverage public-data transport test rather than further Kudla window mining. Functional untouched data were not read, and expensive generator training was not authorized.

::: {.evidence-anchor #sec-6-46}
| Field | Evidence |
|---|---|
| Code commits | `291ccdbc8637156341e9c61c25c1d9434df08ae3` (protocol freeze + label-free preflight); `9c26dcabeb82147ea12d9b58a5c0549d46c5a10d` (accepted science + independent v2); `718b342df4632b60e73dee68726f4bb5812b9e50` (clean reproduction + closeout) |
| Code | `scripts/a8_rk35_preflight.py`; `scripts/a8_rk35_run_coverage_transport.py`; independent `scripts/a8_rk35_verify_coverage_transport.py`; `scripts/a8_rk35_compare_reproduction.py`; `scripts/a8_rk35_closeout.py` |
| Protocol | `configs/a8_rk35_coverage_transport_protocol_v1.json` |
| Results | `audits/20261122/RK35/rk35_coverage_transport_result_v1.json`; `rk35_coverage_transport_independent_v2.json`; `rk35_reproduction_comparison_v2.json`; `rk35_closeout_v1.json` |
| SHA256 | protocol `a26ec02a1f5a7fd8b83f9764ed98ac30c50a71a79d39bb4b27e082d2216b1f7b`; result `c811bb6e3481f8450b600687e9bb9f9fa849f8d8c3c3c71b55d44ed71f4d5651`; independent `d037542df5ee40e47e26f1c368acb5eb5070c6d23f18c168503b609487d820a6`; reproduction `f8faf2b693924a45d4d8222d5eab2c4ad50c8e7033a3d77e9ea7fa2c07f9989f`; closeout `99308d7fad5411f84e4a9c816622c0742e3899bc7a895118b53afc31d459f96b`; preflight `0847653d4060e8016cf39384951c055445ea68cb5a049fc57d25cf4ea0e6be5c` |
| Analysis | 154 retrospective measurement rows; 150 exact-CDS groups; 37 sequence clusters; 10 seeds × 5 folds; 300 new + 200 reused = 500 evaluated fits; 8 primary + 4 gate + 12 secondary descriptive tests |
| Scope | Fixed-Kudla natural-window coverage transport only; coverage not necessary within Kudla; no host/assay identification, separable component claim, independent transport, functional/protein OOD, generator, or wet-lab claim |
:::

"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    original = args.manuscript.read_text()
    if "### 6.46" in original or "#sec-6-46" in original:
        raise ValueError("RK35 section already present; refusing duplicate insertion")
    marker = "## 7. Discussion"
    if marker not in original:
        raise ValueError("section 7 marker not found")
    before, after = original.split(marker, 1)
    if "### 6.45" not in before:
        raise ValueError("RK34 section 6.45 not present before insertion point")
    new = before + SECTION + marker + after
    # prior content preserved exactly except the insertion
    assert new.replace(SECTION, "", 1) == original
    args.manuscript.write_text(new)
    checks = []

    def check(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    reread = args.manuscript.read_text()
    check("section_6_46_present", "### 6.46" in reread)
    check("table_25_present", "**Table 25**" in reread)
    check("table_26_present", "**Table 26**" in reread)
    check("evidence_anchor_present", "#sec-6-46" in reread)
    check("section_6_45_intact", "### 6.45" in reread and "#sec-6-45" in reread)
    check("section_7_intact", "## 7. Discussion" in reread)
    check("prior_content_preserved", reread.replace(SECTION, "", 1) == original)
    check("decision_string_present", "RK33_COVERAGE_RETAINS_INCREMENT_WITHIN_KUDLA_RETROSPECTIVELY" in reread)
    check("key_value_present", "0.735912" in reread and "0.365595" in reread)
    check("section_order", reread.index("### 6.45") < reread.index("### 6.46") < reread.index("## 7. Discussion"))
    report = {
        "schema": "a8-rk35-manuscript-integration-v1",
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