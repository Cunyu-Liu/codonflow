"""Bind formal G2 execution to the matching convergence and G1 evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.dataset import read_fasta
from codonflow.eval.anytime import FrozenReference
from codonflow.train.run_pretrain import file_sha256, git_commit


def verify_gate_pair(convergence_path, g1_path, benchmark_fasta, calibration_dir, min_genes=18):
    convergence = json.loads(Path(convergence_path).read_text())
    behavior = json.loads(Path(g1_path).read_text())
    if convergence.get("protocol") != "a7_convergence_audit_v1" or convergence.get("passed") is not True:
        raise ValueError("convergence audit has not passed")
    if behavior.get("protocol") != "a7_g1_behavior_v1" or behavior.get("passed") is not True:
        raise ValueError("G1 has not passed")
    if behavior["device"] != "cuda:0" or convergence["device"] != "cuda:0":
        raise ValueError("G1 and convergence evidence must use CUDA")
    checkpoint = convergence["checkpoint_paths"]["converged.pt"]
    digest = convergence["checkpoint_sha256"]["converged.pt"]
    if behavior["checkpoint_path"] != checkpoint or behavior["checkpoint_sha256"] != digest:
        raise ValueError("G1 checkpoint does not match convergence audit")
    if not checkpoint.startswith("/teams/") or file_sha256(checkpoint) != digest:
        raise ValueError("frozen checkpoint hash mismatch")
    if behavior["benchmark_sha256"] != file_sha256(benchmark_fasta):
        raise ValueError("G1 benchmark mismatch")
    if len(behavior["records"]) < 3 or behavior["n_samples"] < 100 or not all(
            row["passed"] for row in behavior["records"]):
        raise ValueError("incomplete G1 behavior evidence")
    records = {header.split()[0]: sequence for header, sequence in read_fasta(benchmark_fasta)}
    if len(records) < min_genes:
        raise ValueError(f"G2 requires at least {min_genes} development genes")
    for record_id, source in records.items():
        calibration_path = Path(calibration_dir) / f"{record_id}.json"
        calibration = json.loads(calibration_path.read_text())
        if calibration["source_role"] != "independent_calibration_not_test":
            raise ValueError(f"invalid calibration role: {record_id}")
        if calibration["source_sha256"] != hashlib.sha256(source.encode()).hexdigest():
            raise ValueError(f"calibration source mismatch: {record_id}")
        if calibration["rscu_sha256"] != behavior["rscu_sha256"]:
            raise ValueError(f"calibration RSCU mismatch: {record_id}")
        FrozenReference.from_dict(calibration)
    return {"convergence": convergence, "behavior": behavior, "records": records,
            "checkpoint": checkpoint, "checkpoint_sha256": digest}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--convergence-audit", required=True)
    parser.add_argument("--g1-gate", required=True)
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--calibration-dir", required=True)
    parser.add_argument("--arm", choices=("FULL", "EDIT"), required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-genes", type=int, default=18)
    args = parser.parse_args()
    verified = verify_gate_pair(args.convergence_audit, args.g1_gate,
                                args.benchmark_fasta, args.calibration_dir, args.min_genes)
    current_commit = git_commit()
    subprocess.run(["git", "merge-base", "--is-ancestor",
                    verified["behavior"]["code_commit"], current_commit], check=True)
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("formal G2 requires a clean source tree")
    out_dir = Path(args.out_dir)
    if not str(out_dir.resolve()).startswith("/teams/"):
        raise ValueError("G2 artifacts must remain on /teams")
    if out_dir.exists() and any(out_dir.rglob("*.json")):
        raise ValueError("formal G2 output directory must not contain prior results")
    result = {
        "protocol": "a7_g2_preflight_v1", "ready_for_g2": True,
        "scientific_gate_passed": False, "arm": args.arm,
        "convergence_audit_path": args.convergence_audit,
        "convergence_audit_sha256": file_sha256(args.convergence_audit),
        "g1_gate_path": args.g1_gate, "g1_gate_sha256": file_sha256(args.g1_gate),
        "benchmark_fasta": args.benchmark_fasta,
        "benchmark_sha256": file_sha256(args.benchmark_fasta),
        "calibration_dir": args.calibration_dir,
        "rscu_sha256": verified["behavior"]["rscu_sha256"],
        "checkpoint_path": verified["checkpoint"],
        "checkpoint_sha256": verified["checkpoint_sha256"],
        "record_ids": sorted(verified["records"]), "seeds": [0, 1, 2],
        "budget": 500, "terminal_step": 4, "path_batch_size": 32,
        "out_dir": str(out_dir), "code_commit": current_commit, "code_dirty": False,
    }
    out = Path(args.out)
    if not str(out.resolve()).startswith("/teams/"):
        raise ValueError("G2 preflight artifact must remain on /teams")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({"out": str(out), "ready_for_g2": True,
                      "scientific_gate_passed": False, "n_genes": len(verified["records"])}))


if __name__ == "__main__":
    main()
