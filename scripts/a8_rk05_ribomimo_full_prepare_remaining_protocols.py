#!/usr/bin/env python3
"""Freeze parameterized full-CV protocols for the three remaining RiboMIMO matrices."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite frozen protocol: {path}")
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    repo = Path("/home/codonflow-a8-rk")
    audit_dir = repo / "audits/20261118/RK05"
    template_path = audit_dir / "ribomimo_full_mohammad16_protocol_v2.json"
    preflight_path = audit_dir / "ribomimo_full_loader_preflight_v1.json"
    template = json.loads(template_path.read_text())
    preflight = json.loads(preflight_path.read_text())
    root = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_full_094c_v1")
    created = []
    for dataset in ("Subtelny14", "Mohammad19-1", "Mohammad19-2"):
        slug = dataset.lower().replace("-", "_")
        protocol = copy.deepcopy(template)
        row = preflight["datasets"][dataset]
        protocol["dataset"] = dataset
        protocol["attempt"] = "full-official-first-attempt-with-seven-runtime-compatibility-fixes"
        protocol["matrix"] = {
            "path": row["matrix_path"], "sha256": row["matrix_sha256"],
            "raw_records": row["raw_records"],
            "official_loader_eligible_records": row["eligible_official_coverage_gt_0.6"],
        }
        protocol["output_root"] = str(root / f"{slug}_v1")
        protocol["previous_attempt"] = None
        protocol["protocol_lineage"] = {
            "mohammad16_v2_protocol": str(template_path), "mohammad16_v2_protocol_sha256": sha256(template_path),
            "four_matrix_preflight": str(preflight_path), "four_matrix_preflight_sha256": sha256(preflight_path),
            "reason": "Reuse the validated seven runtime-only replacements; do not repeat the known CUDA-length failure.",
        }
        protocol["scope"] = {
            "complete_official_random_gene_cv": True,
            "homology_aware_split": False, "protein_ood": False, "study_ood": False, "functional_ood": False,
            "publication_metrics_reproduced": False, "sota_claim": False,
            "all_four_datasets_reproduced_by_this_protocol": False,
        }
        output = audit_dir / f"ribomimo_full_{slug}_protocol_v1.json"
        atomic_json(output, protocol)
        created.append({"dataset": dataset, "protocol": str(output), "sha256": sha256(output), "output_root": protocol["output_root"]})
    print(json.dumps({"status": "PASS", "created": created}, indent=2))


if __name__ == "__main__":
    main()
