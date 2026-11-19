#!/usr/bin/env python3
"""Exact v23->v24 increment for the independently verified Mordstein structure no-go."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

EXPECTED_V23 = "a5ef4a157a3e60b91a5087c24ae71ea0c0c01ab21260057298a98426edfed0e2"
EXPECTED_AUDIT_V23 = "5f546a314961b87470cb81ae073eec45023d28542741a04be87b91ff271bb143"
A7_SHA256 = "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423"

SECTION = """### 6.20 Fixed-GFP observed-R1 structure increment: development no-go

I next tested whether ViennaRNA folding features add predictive signal beyond sequencing depth and simple sequence features on the same 152 fixed-GFP observed-R1 variants. This was a retrospective, development-only analysis of a new feature set, not an independent confirmatory test. The frozen v2 protocol used five deterministic variant folds and ridge regression with alpha=1 and no hyperparameter search. The simple model contained log1p(total assigned reads), GC3, GC, CpG density and CAI. The treatment model added full observed 300-nt R1 MFE and the minimum and mean MFE over all contiguous 48-nt windows. Every feature and outcome scaler was fitted within the corresponding training fold.

| OOF model | Spearman | Pearson | MSE | RMSE |
|---|---:|---:|---:|---:|
| depth only | 0.197284700 | 0.162829956 | 2.167833454 | 1.472356429 |
| depth + simple sequence | 0.413234098 | 0.373938420 | 1.915420664 | 1.383987234 |
| depth + simple sequence + observed-R1 structure | 0.408983112 | 0.378327283 | 1.909992037 | 1.382024615 |

The two frozen primary endpoints compared structure-augmented with simple out-of-fold predictions using 20,000 paired-variant bootstraps and 20,000 paired sign-flip permutations, with Holm correction across exactly two hypotheses.

| Treatment-minus-simple effect | Observed | Paired-bootstrap 95% CI | Sign-flip p | Holm p |
|---|---:|---:|---:|---:|
| delta Spearman | -0.004250986 | [-0.055205392, 0.046335849] | 0.857457127 | 1.000 |
| delta MSE | -0.005428627 | [-0.089603707, 0.076765849] | 0.900154992 | 1.000 |

Neither endpoint met its prespecified direction and multiplicity gate. The small MSE decrease is uncertain, and the Spearman estimate is slightly negative; the scientific result is therefore **FIXED_GFP_OBSERVED_R1_STRUCTURE_INCREMENT_NO_GO_DEVELOPMENT_ONLY**. This does not show that RNA structure is universally uninformative. It shows no validated incremental value for these particular observed-R1 MFE features in this fixed-GFP development setup.

The CAI feature used the nine raw `def_refs` strings hard-coded in the frozen CAGFN wrapper and CAI==1.0.2 raw three-character chunking. The first raw reference contains embedded whitespace between two sequence-like segments; this was retained to reproduce the external package behavior and is a reference-quality limitation, not a validated clean human reference set. A v1 preflight stopped before structure calculation or model fitting when this raw encoding was encountered. The v2 implementation reproduced all 61 sense-codon weights from the external package with maximum absolute difference 1.11e-16 and passed 12 unit tests.

Independent verification retranslated every raw R1 sequence, recomputed every external CAI and ViennaRNA feature, regenerated all out-of-fold predictions with a separate penalized-matrix solver, and repeated both resampling analyses. It passed 12/12 checks, with maximum feature and prediction discrepancies of 2.78e-16 and 1.07e-14, respectively; finalization passed 21/21 checks. These results remain restricted to observed CDS 4-303 from one fixed-GFP library. They do not use functional untouched data, impute the central unobserved CDS, establish protein/study OOD transfer or causality, close RK-G1, authorize generator training or support a SOTA claim.

"""

ANCHORS = """| RK02 structure-increment frozen protocol v2 | `f3e1911b4c72f34257c998b736b70ca76734c1586f04e40dd48c03f265d9bdb6` |
| RK02 structure-increment retained v1 preflight failure | `7f14453b47f1baf0f6f7f91653b663d3016e03b24cb0a56ebf1a9a9d1aff4a29` |
| RK02 structure-increment production | `eead79375e43f11b22c968a31d41010f8509f03289b8c5c833ecb571bcb4acc3` |
| RK02 structure-increment independent verification | `5d3868ba037877b5952376c7a4db85fa33df5ed3014abc141b728acc50296170` |
| RK02 structure-increment finalization | `c8fca9ae49706dfa7ef1d026cefde922ef461eb1fcfb5a7dab742b370637a1fc` |
| RK02 structure-increment unit tests and CAI cross-check | `5960def1db264c6ce8fe9161ae6505e4b274d0c67903f3953f12c91e692aa603` |

"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    os.replace(temporary, path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo.resolve()
    paper = repo / "paper/CodonFlow_preprint_A8.md"
    audit_path = repo / "paper/a8_rk_paper_sync_audit.json"
    a7 = repo / "paper/CodonFlow_preprint_A7.md"
    assert sha256(paper) == EXPECTED_V23
    assert sha256(audit_path) == EXPECTED_AUDIT_V23
    assert sha256(a7) == A7_SHA256
    old = paper.read_text()
    assert "### 6.20 Fixed-GFP" not in old and old.count("\n## 7. Discussion\n") == 1
    snapshot = repo / "paper/snapshots/rk02_structure_v24"
    snapshot.mkdir(parents=True, exist_ok=False)
    shutil.copy2(paper, snapshot / "CodonFlow_preprint_A8_v23.md")
    shutil.copy2(audit_path, snapshot / "a8_rk_paper_sync_audit_v23.json")
    shutil.copy2(a7, snapshot / "CodonFlow_preprint_A7.md")
    new = old.replace("\n## 7. Discussion\n", "\n" + SECTION + "## 7. Discussion\n", 1)
    marker = "\nA7 is retained as the prior manuscript snapshot."
    assert new.count(marker) == 1 and "RK02 structure-increment frozen protocol v2" not in new
    new = new.replace(marker, "\n" + ANCHORS + "A7 is retained as the prior manuscript snapshot.", 1)
    atomic_write(paper, new)
    paper_hash = sha256(paper)
    audit = json.loads(audit_path.read_text())
    audit["base_v23_paper_sha256"] = EXPECTED_V23
    audit["base_v23_audit_sha256"] = EXPECTED_AUDIT_V23
    audit["generated_sections"].extend(["6.20 Fixed-GFP observed-R1 structure increment: development no-go", "8.1 RK02 structure-increment evidence anchors"])
    audit["last_increment"] = {
        "section": "6.20 Fixed-GFP observed-R1 structure increment: development no-go",
        "protocol_sha256": "f3e1911b4c72f34257c998b736b70ca76734c1586f04e40dd48c03f265d9bdb6",
        "production_sha256": "eead79375e43f11b22c968a31d41010f8509f03289b8c5c833ecb571bcb4acc3",
        "independent_sha256": "5d3868ba037877b5952376c7a4db85fa33df5ed3014abc141b728acc50296170",
        "finalization_sha256": "c8fca9ae49706dfa7ef1d026cefde922ef461eb1fcfb5a7dab742b370637a1fc",
        "paper_sha256": paper_hash,
        "scientific_scope": "fixed-GFP observed-R1 structure increment development no-go; no untouched, complete-CDS, OOD, RK-G1, generator or SOTA claim",
        "submittable": False,
    }
    audit["output_sha256"] = paper_hash
    audit["pre_rk02_structure_snapshot"] = {
        "paper": str(snapshot / "CodonFlow_preprint_A8_v23.md"), "paper_sha256": EXPECTED_V23,
        "audit": str(snapshot / "a8_rk_paper_sync_audit_v23.json"), "audit_sha256": EXPECTED_AUDIT_V23,
        "a7": str(snapshot / "CodonFlow_preprint_A7.md"), "a7_sha256": A7_SHA256,
    }
    audit["rk02_mordstein_structure_increment"] = {
        "analysis_status": "DEVELOPMENT_ONLY_NOT_CONFIRMATORY_INDEPENDENT_TEST",
        "scientific_result": "FIXED_GFP_OBSERVED_R1_STRUCTURE_INCREMENT_NO_GO_DEVELOPMENT_ONLY",
        "n_variants": 152, "structure_increment_pass": False,
        "functional_untouched_used": False, "complete_cds_closed": False,
        "full_rk_g1_gate": False, "generator_training_authorized": False, "sota_claim": False,
    }
    atomic_write(audit_path, json.dumps(audit, indent=2, sort_keys=True) + "\n")
    report = {
        "schema": "a8.rk02.structure_paper_update.v1", "status": "UPDATED_PENDING_INDEPENDENT_VERIFICATION",
        "section": "6.20 Fixed-GFP observed-R1 structure increment: development no-go",
        "base_paper_sha256": EXPECTED_V23, "base_audit_sha256": EXPECTED_AUDIT_V23,
        "paper_sha256": paper_hash, "audit_sha256": sha256(audit_path), "a7_sha256": sha256(a7),
        "snapshot_directory": str(snapshot), "submittable": False,
    }
    report_path = repo / "paper/a8_rk02_structure_paper_update.json"
    atomic_write(report_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
