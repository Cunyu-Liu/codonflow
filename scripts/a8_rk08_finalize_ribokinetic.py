#!/usr/bin/env python3
"""Finalize the RK-08 smoke only after independent and CUDA checks pass."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from codonflow.data.ribokinetic import file_sha256


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--retrain-dir", required=True)
    p.add_argument("--cuda-dir", required=True)
    p.add_argument("--independent-report", required=True)
    p.add_argument("--unit-test-report", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--repo", default="/home/codonflow-a8-rk")
    args = p.parse_args()
    independent = json.loads(Path(args.independent_report).read_text())
    tests = json.loads(Path(args.unit_test_report).read_text())
    checks = []

    def check(name, condition, detail):
        checks.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})

    check("independent_verification", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"], {"passed": independent["checks_passed"], "total": independent["checks_total"]})
    check("unit_tests", tests["status"] == "PASS" and tests["passed"] == tests["total"], tests)
    check("cpu_retrain_bitwise", independent["retrain"]["state_tensors_bitwise_equal"], independent["retrain"])
    check("real_cuda_execution", independent["cuda"]["device"] == "cuda" and bool(independent["cuda"]["gpu"]), independent["cuda"])
    summaries = {}
    for name, directory in (("cpu", args.run_dir), ("retrain", args.retrain_dir), ("cuda", args.cuda_dir)):
        root = Path(directory)
        summary = json.loads((root / "run_summary.json").read_text())
        summaries[name] = summary
        check(f"{name}_pending_preserved", summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION", summary["status"])
        check(f"{name}_large_artifacts_on_teams", str(root).startswith("/teams/HoulabData_1788502323/liucunyu/"), str(root))
        check(f"{name}_scope_not_mechanism_validation", summary["scope"] == "REAL_DATA_SMOKE_NOT_MECHANISM_VALIDATION", summary["scope"])
        check(f"{name}_checkpoint_hash", file_sha256(str(root / "best.pt")) == summary["hashes"]["checkpoint_sha256"], summary["hashes"]["checkpoint_sha256"])
        for artifact in ("metrics.json", "history.json", "predictions.csv", "resolved_config.json"):
            check(f"{name}_{artifact}_exists", (root / artifact).is_file(), str(root / artifact))
    check("no_untouched_evaluation", all("functional_untouched" not in s["rows"] for s in summaries.values()), {k: v["rows"] for k, v in summaries.items()})
    check("no_generator_claim", all("generator" in " ".join(s["forbidden_claims"]).lower() for s in summaries.values()), "generator claims remain forbidden")
    repo = Path(args.repo)
    code_files = [
        "src/codonflow/models/ribokinetic.py",
        "src/codonflow/data/ribokinetic.py",
        "scripts/a8_rk08_train_ribokinetic.py",
        "scripts/a8_rk08_verify_ribokinetic.py",
        "scripts/a8_rk08_finalize_ribokinetic.py",
        "tests/test_a8_rk08_ribokinetic.py",
        "configs/a8_rk08_smoke_config.json",
    ]
    hashes = {}
    for relative in code_files:
        path = repo / relative
        check(f"code_exists_{relative}", path.is_file(), relative)
        if path.is_file():
            hashes[relative] = file_sha256(str(path))
    failed = [c for c in checks if c["status"] != "PASS"]
    report = {
        "status": "PASS" if not failed else "FAIL",
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "checks": checks,
        "code_sha256": hashes,
        "artifact_roots": {"cpu": args.run_dir, "retrain": args.retrain_dir, "cuda": args.cuda_dir},
        "conclusion": "Real-data CPU/CUDA training smoke is reproducible and independently checked; mechanism efficacy, OOD gains, generator readiness and SOTA remain unvalidated.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "passed": report["checks_passed"], "total": report["checks_total"], "output": str(output)}))


if __name__ == "__main__":
    main()
