#!/usr/bin/env python3
"""Finalize only the CodonTransformer official bounded-smoke task boundary."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--materialization", type=Path, required=True)
    p.add_argument("--production", type=Path, required=True)
    p.add_argument("--verification", type=Path, required=True)
    p.add_argument("--unit-log", type=Path, required=True)
    p.add_argument("--env-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    materialization = json.loads(args.materialization.read_text())
    production = json.loads(args.production.read_text())
    verification = json.loads(args.verification.read_text())
    unit = args.unit_log.read_text()
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    model_files = materialization["model"]["files"]
    model_ok = materialization["status"] == "COMPLETE"
    for item in model_files:
        path = Path(materialization["model"]["model_dir"]) / item["name"]
        model_ok &= path.stat().st_size == item["bytes"] and sha(path) == item["sha256"]
    weight = next(x for x in model_files if x["name"] == "model.safetensors")
    model_ok &= (weight["bytes"] == 358342232
                 and weight["sha256"] == "23994e1e7324e78c9d9da71040e8677c0a635287cf1c7c9ea5096b7eadc44dfd")
    check("official_source_and_model_materialized", model_ok,
          {"source_commit": materialization["source"]["commit"],
           "model_commit": materialization["model"]["commit"], "model_files": len(model_files)})

    check("official_bounded_execution_complete",
          production["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE"
          and len(production["runs"]) == 4
          and production["official_example_readme_exact_match"] is True,
          {"status": production["status"], "runs": len(production["runs"])})

    raw_ok = True
    for run in production["runs"]:
        path = Path(run["raw_output"])
        raw_ok &= path.exists() and sha(path) == run["raw_output_sha256"]
    fasta = Path(production["outputs_fasta"])
    raw_ok &= fasta.exists() and sha(fasta) == production["outputs_fasta_sha256"]
    check("raw_outputs_and_fasta_immutable_identity", raw_ok,
          {"raw_count": len(production["runs"]), "fasta_sha256": production["outputs_fasta_sha256"]})

    check("independent_reexecution_and_verification_pass",
          verification["status"] == "PASS"
          and verification["passed_checks"] == verification["check_count"]
          and verification["production_report_sha256"] == sha(args.production),
          {"checks": f"{verification['passed_checks']}/{verification['check_count']}"})

    check("eight_helper_contract_tests_pass",
          "Ran 8 tests" in unit and unit.rstrip().endswith("OK"),
          {"log": str(args.unit_log), "sha256": sha(args.unit_log)})

    check("match_protein_translation_contract_closed",
          production["constrained_legal_count"] == production["constrained_run_count"] == 2
          and verification["constrained_legal_count"] == verification["constrained_run_count"] == 2,
          {"legal": 2, "total": 2})

    check("official_default_behavior_preserved",
          production["default_run_count"] == verification["default_run_count"] == 2
          and production["default_legal_count"] == verification["default_legal_count"],
          {"default_legal_count": production["default_legal_count"], "default_run_count": 2})

    freeze = args.env_dir / "pip_freeze.txt"
    install_logs = [args.env_dir / "pip_install_inference_v2.log",
                    args.env_dir / "pip_install_sklearn_v3.log"]
    import_log = args.env_dir / "environment_import_v2.txt"
    frozen = freeze.read_text() if freeze.exists() else ""
    env_ok = (freeze.exists() and all(x.exists() for x in install_logs) and import_log.exists()
              and "OFFICIAL_IMPORT_PASS" in import_log.read_text()
              and "transformers==4.40.2" in frozen and "numpy==1.26.4" in frozen
              and "scikit-learn==1.4.2" in frozen
              and production["transformers"] == "4.40.2")
    check("isolated_inference_environment_frozen", env_ok,
          {"freeze": str(freeze), "freeze_sha256": sha(freeze) if freeze.exists() else None,
           "torch": production["torch"], "transformers": production["transformers"],
           "gpu": production["gpu_name"]})

    scope_names = ["main_baseline_comparison", "dense_budget_complete",
                   "matched_lineardesign_or_ensembledesign_comparison", "functional_ood", "sota_claim"]
    check("bounded_scope_not_promoted", all(production[x] is False for x in scope_names),
          {x: production[x] for x in scope_names})

    scripts = [Path(__file__),
               Path(__file__).with_name("a8_rk05_codontransformer_official_smoke.py"),
               Path(__file__).with_name("a8_rk05_verify_codontransformer_official_smoke.py"),
               Path(__file__).parents[1] / "tests" / "test_a8_rk05_codontransformer_official_smoke.py"]
    script_records = [{"path": str(x), "sha256": sha(x)} for x in scripts]
    check("reproduction_scripts_present_and_hashed",
          all(x.exists() and x.stat().st_size > 0 for x in scripts), script_records)

    passed = sum(x["pass"] for x in checks)
    report = {
        "schema_version": "a8-rk05-codontransformer-finalization-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "CLOSED_BOUNDED_OFFICIAL_SMOKE" if passed == len(checks) else "NOT_CLOSED",
        "check_count": len(checks), "passed_checks": passed, "checks": checks,
        "production": str(args.production), "production_sha256": sha(args.production),
        "verification": str(args.verification), "verification_sha256": sha(args.verification),
        "materialization": str(args.materialization), "materialization_sha256": sha(args.materialization),
        "unit_log": str(args.unit_log), "unit_log_sha256": sha(args.unit_log),
        "official_example_exact": production["official_example_readme_exact_match"],
        "default_legal": f"{production['default_legal_count']}/{production['default_run_count']}",
        "constrained_legal": f"{production['constrained_legal_count']}/{production['constrained_run_count']}",
        "main_baseline_comparison": False, "dense_budget_complete": False,
        "functional_ood": False, "sota_claim": False,
        "next_gate": "Do not interpret this bounded official-example/C01 smoke as a main baseline result; full baseline, dense-budget and functional-OOD tasks remain open.",
    }
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}",
                      "output": str(args.output)}))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
