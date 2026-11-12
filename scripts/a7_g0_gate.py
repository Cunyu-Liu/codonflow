"""Evaluate the complete A7 G0 contract from frozen evidence artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.train.run_pretrain import file_sha256, git_commit


def evaluate_g0(full_audit_path, frozen_path, source_manifest_paths, unique_paths,
                cuda_path, registry_path):
    full = json.loads(Path(full_audit_path).read_text())
    frozen = json.loads(Path(frozen_path).read_text())
    registry = json.loads(Path(registry_path).read_text())
    expected = {row["species"]: row.get("release", registry["release"]) for row in registry["records"]}
    source_records = {}
    source_failures = []
    for path in source_manifest_paths:
        manifest = json.loads(Path(path).read_text())
        source_failures.extend(row for row in manifest.get("records", []) if row.get("status") != "done")
        for row in manifest.get("records", []):
            if row.get("status") == "done" and expected.get(row.get("species")) == row.get("release"):
                source_records[row["species"]] = row
    source_checks = {}
    for species, release in expected.items():
        row = source_records.get(species)
        if not row:
            source_checks[species] = False
            continue
        counts = row.get("cleaning_counts", {})
        source_checks[species] = bool(
            row.get("n_input") == sum(counts.values())
            and row.get("n_retained") == counts.get("kept")
            and len(row.get("raw_sha256", "")) == 64
            and len(row.get("cleaned_sha256", "")) == 64
            and Path(row["raw_path"]).exists() and Path(row["cleaned_path"]).exists()
        )
    unique = {}
    for path in unique_paths:
        payload = json.loads(Path(path).read_text())
        for seed in payload.get("seeds", []):
            unique[seed] = payload
    unique_checks = {
        seed: bool(seed in unique and unique[seed].get("complete_all_requested_seeds")
                   and unique[seed].get("mfe_ned_independently_recomputed")
                   and unique[seed].get("n_records") == 18
                   and len(unique[seed].get("records", [])) == 18
                   and all(row.get("matches") for row in unique[seed]["records"]))
        for seed in (0, 1, 2)
    }
    cuda = json.loads(Path(cuda_path).read_text())
    checks = {
        "full_distribution": bool(full.get("passed") and full.get("v3_all", {}).get("passed")
                                  and full.get("species_distribution", {}).get("passed")),
        "frozen_assets": bool(frozen.get("passed") and all(frozen.get("checks", {}).values())),
        "source_recovery": len(source_records) == 25 and all(source_checks.values()) and not source_failures,
        "unique18_all_seeds": all(unique_checks.values()),
        "cuda_matmul": bool(cuda.get("passed") and cuda.get("device") == "cuda"
                              and cuda.get("matmul_synchronized")),
    }
    return {
        "protocol": "a7_g0_gate_v1",
        "code_commit": git_commit(),
        "passed": all(checks.values()),
        "checks": checks,
        "source_species_checks": source_checks,
        "source_failures": source_failures,
        "unique_seed_checks": unique_checks,
        "evidence": {
            "full_audit": {"path": str(full_audit_path), "sha256": file_sha256(full_audit_path)},
            "frozen_assets": {"path": str(frozen_path), "sha256": file_sha256(frozen_path)},
            "source_manifests": [{"path": str(path), "sha256": file_sha256(path)} for path in source_manifest_paths],
            "unique18": [{"path": str(path), "sha256": file_sha256(path)} for path in unique_paths],
            "cuda": {"path": str(cuda_path), "sha256": file_sha256(cuda_path)},
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-audit", required=True)
    parser.add_argument("--frozen-assets", required=True)
    parser.add_argument("--source-manifest", action="append", required=True)
    parser.add_argument("--unique-audit", action="append", required=True)
    parser.add_argument("--cuda-evidence", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = evaluate_g0(args.full_audit, args.frozen_assets, args.source_manifest,
                         args.unique_audit, args.cuda_evidence, args.registry)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(out.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(out)
    print(json.dumps({"out": str(out), "passed": result["passed"], "checks": result["checks"]}))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
