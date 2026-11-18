#!/usr/bin/env python3
"""Finalize bounded VeloHARMO E. coli data acceptance after independent checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

EXPECTED = {
    "archive_sha256": "68b029b667029827d9c7213249eebcac32e6152d80ef7c0e24e53d8437d5a0ef",
    "matrix_sha256": "71008f948597daff282ccb3e124dd7e4c5b35aa92e2dbe4af43d5725d6fa740f",
    "raw_records": 1170,
    "clean_records": 1170,
    "unique_gene_ids": 1170,
    "duplicate_gene_ids": 0,
    "modal_feature_numeric_dim": 6,
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--payload-dir", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    args = parser.parse_args()
    qc = json.loads((args.audit_dir / "veloharmo_ecoli_qc.json").read_text())
    independent = json.loads((args.audit_dir / "veloharmo_ecoli_independent_verification.json").read_text())
    material = json.loads((args.audit_dir / "veloharmo_materialization.json").read_text())
    loader = json.loads((args.audit_dir / "veloharmo_official_loader_smoke.json").read_text())
    matrix = args.payload_dir / "shared/E.coli.summary.add.pro.SS.txt"
    checks = []
    def add(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})
    add("fixed_archive", sha(args.archive) == EXPECTED["archive_sha256"] and material["commit"] == "38b48079856aeb9d33a1b10844d77aa8f6640032")
    add("matrix_identity", sha(matrix) == EXPECTED["matrix_sha256"] == qc["matrix_sha256"] == loader["matrix_sha256"])
    add("qc_counts", all(qc.get(k) == v for k, v in EXPECTED.items() if k not in ("archive_sha256", "matrix_sha256")) and qc["excluded_records"] == 0, {k: qc.get(k) for k in EXPECTED if k not in ("archive_sha256", "matrix_sha256")})
    add("independent_recompute", independent["status"] == "PASS" and independent["passed_checks"] == independent["check_count"] == 7 and independent["max_numeric_delta"] == 0.0)
    add("official_loader", loader["status"] == "PASS_OFFICIAL_LOADER_ONLY" and loader["pass"] and loader["x_shape"] == [1170, 1520, 111] and loader["density_shape"] == [1170, 1520, 1] and loader["x_all_finite"] and loader["density_all_finite"], {"x_shape": loader["x_shape"], "density_shape": loader["density_shape"]})
    outputs_ok = True
    manifest = json.loads((args.payload_dir / "qc_v1/artifact_manifest.json").read_text())
    for name, record in manifest["outputs"].items():
        path = args.payload_dir / "qc_v1" / name
        outputs_ok &= path.stat().st_size == record["bytes"] and sha(path) == record["sha256"]
    add("artifact_manifest", outputs_ok)
    layout_ok = str(args.source_dir).startswith("/home/") and str(args.payload_dir).startswith("/teams/HoulabData_1788502323/liucunyu/")
    for rel in ("VeloBERT/E.coli.summary.add.pro.SS.txt", "VeloGRU/E.coli.summary.add.pro.SS.txt", "Genetic_algorithm/E.coli.fold_0_best_network.pth", "Genetic_algorithm/yeast.fold_0_best_network.pth"):
        layout_ok &= (args.source_dir / rel).is_symlink() and (args.source_dir / rel).resolve().is_file()
    add("home_code_teams_payload_layout", layout_ok)
    scope_ok = not qc["five_species_processed_matrices_complete"] and not qc["model_training_authorized"] and not qc["functional_ood_or_sota_claim_authorized"] and not loader["training_performed"] and not loader["publication_metrics_reproduced"] and not loader["sota_claim"]
    add("bounded_scope_retained", scope_ok)
    passed = sum(c["pass"] for c in checks)
    result = {
        "schema_version": "a8-rk03-veloharmo-finalization-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ECOLI_QC_VERIFIED_FIVE_SPECIES_NOT_AVAILABLE" if passed == len(checks) else "FAIL",
        "checks": checks, "passed_checks": passed, "check_count": len(checks),
        "repository": "https://github.com/BianBian2021/VeloHARMO",
        "commit": material["commit"],
        "archive_sha256": EXPECTED["archive_sha256"], "matrix_sha256": EXPECTED["matrix_sha256"],
        "raw_records": qc["raw_records"], "clean_records": qc["clean_records"], "excluded_records": qc["excluded_records"],
        "unique_gene_ids": qc["unique_gene_ids"], "duplicate_gene_ids": qc["duplicate_gene_ids"], "modal_feature_numeric_dim": qc["modal_feature_numeric_dim"],
        "clean_length_distribution": qc["clean_length_distribution"], "clean_coverage_distribution": qc["clean_coverage_distribution"],
        "loader": {"x_shape": loader["x_shape"], "density_shape": loader["density_shape"], "length_shape": loader["length_shape"], "length_min": loader["length_min"], "length_max": loader["length_max"], "all_finite": loader["x_all_finite"] and loader["density_all_finite"]},
        "independent_checks": f"{independent['passed_checks']}/{independent['check_count']}",
        "max_numeric_delta": independent["max_numeric_delta"],
        "available_processed_matrices": ["Escherichia_coli"],
        "unavailable_processed_matrices": ["Pseudomonas_aeruginosa", "Drosophila_melanogaster", "Homo_sapiens", "Saccharomyces_cerevisiae"],
        "weights_available": ["E.coli.fold_0_best_network.pth", "yeast.fold_0_best_network.pth"],
        "science_flags": {"ppt_record_ready": passed == len(checks), "ecoli_matrix_ready": passed == len(checks), "five_species_data_closed": False, "official_cross_validation_reproduced": False, "model_training_complete": False, "main_baseline_comparison": False, "functional_ood": False, "sota_claim": False},
        "scope": "Verified E. coli processed matrix and official loader only. Four other processed matrices are not present in the fixed public snapshot; no model training, publication metric, OOD or SOTA claim.",
        "artifacts": {path.name: sha(path) for path in [args.audit_dir / "veloharmo_materialization.json", args.audit_dir / "veloharmo_ecoli_qc.json", args.audit_dir / "veloharmo_ecoli_independent_verification.json", args.audit_dir / "veloharmo_official_loader_smoke.json"]},
    }
    output = args.audit_dir / "veloharmo_finalization.json"
    if output.exists(): raise RuntimeError(f"refusing to overwrite {output}")
    part = output.with_name(output.name + f".part-{os.getpid()}")
    part.write_text(json.dumps(result, indent=2) + "\n")
    os.replace(part, output)
    print(json.dumps({"status": result["status"], "checks": f"{passed}/{len(checks)}", "science_flags": result["science_flags"]}, indent=2))
    if result["status"] == "FAIL": raise SystemExit(1)


if __name__ == "__main__":
    main()
