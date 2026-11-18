#!/usr/bin/env python3
"""Run a bounded, fixed-source ID3 quick-test with provenance and validity gates."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ID3_COMMIT = "ed23037e5a74ca10953954c425ac736fb89578a8"
DEEPRACCESS_COMMIT = "1a37235e31e1d5a7d5e2bfb705e3a00f1cdcaa9c"
ID3_ZIP_SHA256 = "9566b8cc1492ed6870e792e4b8ffed00c1b08debfb1719b41de872b7107f066f"
EXPECTED_QUICK = {
    "proteins": ["O15263"],
    "constraints": ["lagrangian", "ams", "cpc"],
    "variants": ["00", "01", "10", "11"],
    "iterations": 2,
    "seeds": 1,
    "enable_cai": False,
}
EXPECTED_FULL = {
    "proteins": ["O15263", "P00004", "P01308", "P01825", "P04637", "P0CG48", "P0DTC2", "P0DTC9", "P31417", "P42212", "P61626", "P99999"],
    "constraints": ["lagrangian", "ams", "cpc"],
    "variants": ["00", "01", "10", "11"],
    "iterations": 1000,
    "seeds": 1,
    "enable_cai": False,
}
CODONS = {
    "UUU":"F","UUC":"F","UUA":"L","UUG":"L","UCU":"S","UCC":"S","UCA":"S","UCG":"S",
    "UAU":"Y","UAC":"Y","UAA":"*","UAG":"*","UGU":"C","UGC":"C","UGA":"*","UGG":"W",
    "CUU":"L","CUC":"L","CUA":"L","CUG":"L","CCU":"P","CCC":"P","CCA":"P","CCG":"P",
    "CAU":"H","CAC":"H","CAA":"Q","CAG":"Q","CGU":"R","CGC":"R","CGA":"R","CGG":"R",
    "AUU":"I","AUC":"I","AUA":"I","AUG":"M","ACU":"T","ACC":"T","ACA":"T","ACG":"T",
    "AAU":"N","AAC":"N","AAA":"K","AAG":"K","AGU":"S","AGC":"S","AGA":"R","AGG":"R",
    "GUU":"V","GUC":"V","GUA":"V","GUG":"V","GCU":"A","GCC":"A","GCA":"A","GCG":"A",
    "GAU":"D","GAC":"D","GAA":"E","GAG":"E","GGU":"G","GGC":"G","GGA":"G","GGG":"G",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def translate(seq: str) -> str:
    if len(seq) % 3 or not seq or re.fullmatch(r"[ACGU]+", seq) is None:
        raise ValueError("RNA sequence must be non-empty ACGU with length divisible by three")
    return "".join(CODONS[seq[i:i+3]] for i in range(0, len(seq), 3))


def read_fasta_sequence(path: Path) -> str:
    return "".join(line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith(">"))


def normalize_id3_rna(sequence: str) -> str:
    """Map ID3's DNA-compatible UTR alphabet to its ACGU model alphabet."""
    return sequence.upper().replace("T", "U")


def preset_from_source(path: Path, function_name: str) -> dict:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
                    values = {}
                    for kw in stmt.value.keywords:
                        if kw.arg:
                            try:
                                values[kw.arg] = ast.literal_eval(kw.value)
                            except (ValueError, TypeError):
                                values[kw.arg] = ast.unparse(kw.value)
                    return values
    raise ValueError(f"Preset not found: {function_name}")


def select_result_files(output_dir: Path) -> list[Path]:
    excluded = {"config.json", "summary.json", "progress.json"}
    return sorted(p for p in output_dir.glob("*.json") if p.name not in excluded)


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True, allow_nan=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id3-source", type=Path, default=Path("/home/codonflow-a8-rk-external/ID3"))
    parser.add_argument("--id3-zip", type=Path, default=Path("/home/id3_ed23037_fixed.zip"))
    parser.add_argument("--deepraccess-zip", type=Path, default=Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/sources/deepraccess_1a37235_fixed.zip"))
    parser.add_argument("--deepraccess-zip-sha256", required=True)
    parser.add_argument("--deepraccess-materialization-audit", type=Path,
                        default=Path("/home/codonflow-a8-rk/audits/20261118/RK05/deepraccess_materialization.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    parser.add_argument("--official-force", action="store_true",
                        help="CPU-only bypass of ID3's global GPU-process gate; does not alter experiment config")
    args = parser.parse_args()
    if args.official_force and args.device != "cpu":
        parser.error("--official-force is restricted to --device cpu")

    started = time.time()
    source = args.id3_source.resolve()
    output_dir = args.output_dir.resolve()
    audit_output = args.audit_output.resolve()
    log_path = audit_output.parent / "id3_official_quick_test.log"
    report = {
        "schema_version": "a8-rk05-id3-official-smoke-v1",
        "status": "FAIL_OFFICIAL_ID3_SMOKE",
        "started_utc": utcnow(),
        "source": {
            "id3_commit": ID3_COMMIT,
            "id3_zip": str(args.id3_zip),
            "id3_zip_sha256": ID3_ZIP_SHA256,
            "deepraccess_commit": DEEPRACCESS_COMMIT,
            "deepraccess_zip": str(args.deepraccess_zip),
            "deepraccess_zip_sha256": args.deepraccess_zip_sha256,
            "source_dir": str(source),
        },
        "science_flags": {
            "official_quick_test_executed": False,
            "upstream_example_used_as_result": False,
            "pretrained_deepraccess_verified": False,
            "main_baseline_comparison": False,
            "sota_claim": False,
            "dense_budget_evaluation": False,
            "natural_cds_claim": False,
            "functional_expression_claim": False,
        },
        "execution_contract": {
            "official_force": args.official_force,
            "official_force_scope": "CPU-only skip of upstream global GPU-process gate; no GPU allocation or experiment-config change" if args.official_force else None,
        },
        "checks": [],
    }

    def check(name: str, passed: bool, detail) -> None:
        report["checks"].append({"name": name, "pass": bool(passed), "detail": detail})

    try:
        if output_dir.exists() and any(output_dir.iterdir()):
            raise FileExistsError(f"Refusing non-empty output directory: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        audit_output.parent.mkdir(parents=True, exist_ok=True)

        required = [
            "run_unified_experiment.py",
            "id3/experiments/configs/unified_experiment_config.py",
            "id3/experiments/core/unified_experiment_runner.py",
            "id3/utils/deepraccess_wrapper.py",
            "data/proteins/O15263.fasta.txt",
            "README.md",
        ]
        check("fixed_source_files", all((source / p).is_file() for p in required), required)
        if not all((source / p).is_file() for p in required):
            raise FileNotFoundError("Incomplete ID3 fixed source")
        check("id3_zip_sha256", sha256(args.id3_zip) == ID3_ZIP_SHA256, sha256(args.id3_zip))
        check("deepraccess_zip_sha256", sha256(args.deepraccess_zip) == args.deepraccess_zip_sha256, sha256(args.deepraccess_zip))

        config_path = source / "id3/experiments/configs/unified_experiment_config.py"
        quick = preset_from_source(config_path, "quick_test")
        full = preset_from_source(config_path, "full_12x12")
        for key, value in EXPECTED_QUICK.items():
            check(f"quick_preset_{key}", quick.get(key) == value, {"actual": quick.get(key), "expected": value})
        for key, value in EXPECTED_FULL.items():
            check(f"full_preset_{key}", full.get(key) == value, {"actual": full.get(key), "expected": value})
        report["source_preset_contract"] = {"quick_test": quick, "full_12x12": full}
        readme_lines = (source / "README.md").read_text().splitlines()
        report["readme_contract_lines"] = [
            {"line": i + 1, "text": line.strip()}
            for i, line in enumerate(readme_lines)
            if "Quick test" in line or "full-12x12" in line or "12 seeds" in line or "5 iterations" in line
        ]
        readme_text = "\n".join(readme_lines)
        report["readme_source_discrepancies"] = {
            "quick_readme_5_iterations": "5 iterations" in readme_text,
            "quick_source_iterations": quick.get("iterations"),
            "full_readme_12_seeds": "12 seeds" in readme_text,
            "full_source_seeds": full.get("seeds"),
            "full_12x12_interpretation": "12 proteins x (3 constraints x 4 variants); source seeds=1",
        }
        check("readme_quick_mismatch_retained", "5 iterations" in readme_text and quick.get("iterations") == 2, report["readme_source_discrepancies"])
        check("readme_full_mismatch_retained", "12 seeds" in readme_text and full.get("seeds") == 1, report["readme_source_discrepancies"])

        weight = source / "DeepRaccess/path/FCN_structured.pth"
        check("structured_weight_present", weight.is_file(), str(weight))
        if not weight.is_file():
            raise FileNotFoundError(f"Missing pretrained weight: {weight}")
        report["source"]["structured_weight"] = str(weight)
        report["source"]["structured_weight_bytes"] = weight.stat().st_size
        report["source"]["structured_weight_sha256"] = sha256(weight)
        report["source"]["required_file_sha256"] = {p: sha256(source / p) for p in required}
        materialization_path = args.deepraccess_materialization_audit.resolve()
        materialization = json.loads(materialization_path.read_text())
        materialization_source = materialization.get("source", {})
        check("deepraccess_materialization_status",
              materialization.get("status") == "PASS_FIXED_SOURCE_AND_WEIGHT_MATERIALIZATION",
              materialization.get("status"))
        check("deepraccess_materialization_identity",
              materialization_source.get("commit") == DEEPRACCESS_COMMIT
              and materialization_source.get("zip_sha256") == args.deepraccess_zip_sha256
              and Path(materialization_source.get("target", "")).resolve() == (source / "DeepRaccess").resolve(),
              {"commit": materialization_source.get("commit"), "target": materialization_source.get("target")})
        materialized_files = materialization_source.get("files", {})
        deep_source_deltas = []
        for relative, registered in sorted(materialized_files.items()):
            path = source / "DeepRaccess" / relative
            if not path.is_file() or path.stat().st_size != registered["bytes"] or sha256(path) != registered["sha256"]:
                deep_source_deltas.append(relative)
        check("deepraccess_all_materialized_file_hashes", not deep_source_deltas,
              {"registered_files": len(materialized_files), "mismatches": deep_source_deltas})
        structured_registration = materialization.get("pretrained_weights", {}).get("path/FCN_structured.pth", {})
        check("materialized_structured_weight_matches_audit",
              structured_registration.get("bytes") == weight.stat().st_size
              and structured_registration.get("sha256") == sha256(weight), structured_registration)
        report["source"]["deepraccess_materialization_audit"] = str(materialization_path)
        report["source"]["deepraccess_materialization_audit_sha256"] = sha256(materialization_path)
        report["source"]["deepraccess_file_count"] = len(materialized_files)

        import torch
        import numpy
        import pandas
        import yaml
        import Bio
        import seaborn
        if args.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but unavailable; no silent fallback permitted")
        os.chdir(source)
        sys.path.insert(0, str(source))
        from id3.utils.deepraccess_wrapper import DeepRaccessID3Wrapper
        from id3.config.utr_loader import get_default_utrs

        wrapper = DeepRaccessID3Wrapper(str(weight), device=args.device)
        protein = read_fasta_sequence(source / "data/proteins/O15263.fasta.txt")
        raw_utrs = get_default_utrs()
        utrs = {key: normalize_id3_rna(value) for key, value in raw_utrs.items()}
        preflight_cds = "AUG" + "GCU" * (len(protein) - 1)
        full_rna = utrs["utr5"] + preflight_cds + utrs["utr3"]
        index = {"A": 0, "C": 1, "G": 2, "U": 3}
        probs = torch.zeros((1, len(full_rna), 4), dtype=torch.float32, device=wrapper.device)
        for j, base in enumerate(full_rna):
            probs[0, j, index[base]] = 1.0
        with torch.no_grad():
            preflight_score = wrapper.compute_atg_window_accessibility(probs, atg_position=len(utrs["utr5"]), discrete=True)
        score_value = float(preflight_score.detach().cpu().item())
        check("pretrained_wrapper_finite_forward", math.isfinite(score_value), score_value)
        report["preflight"] = {
            "protein_id": "O15263",
            "protein_length": len(protein),
            "utr5_length": len(utrs["utr5"]),
            "utr3_length": len(utrs["utr3"]),
            "full_rna_length": len(full_rna),
            "utr_t_to_u_normalization": {key: "T" in raw_utrs.get(key, "") for key in ("utr5", "utr3")},
            "finite_accessibility": score_value,
            "note": "Shape/finite forward gate only; not a predictive validity or benchmark result.",
        }
        report["environment"] = {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_name": torch.cuda.get_device_name(0) if args.device == "cuda" else None,
            "numpy": numpy.__version__,
            "pandas": pandas.__version__,
            "pyyaml": yaml.__version__,
            "biopython": Bio.__version__,
            "seaborn": seaborn.__version__,
            "pythonpath": os.environ.get("PYTHONPATH"),
            "requested_device": args.device,
        }
        report["science_flags"]["pretrained_deepraccess_verified"] = True
        del wrapper, probs, preflight_score
        if args.device == "cuda":
            torch.cuda.empty_cache()

        cmd = [
            sys.executable,
            "run_unified_experiment.py",
            "--preset", "quick-test",
            "--device", args.device,
            "--output-dir", str(output_dir),
            "--disable-inner-tqdm",
        ]
        if args.official_force:
            cmd.append("--force")
        official_env = os.environ.copy()
        if args.device == "cpu":
            # Fixed runner constructs DeepRaccessID3Wrapper() without propagating config device.
            # Hide CUDA in the child so its automatic device selection remains CPU; source is unchanged.
            official_env["CUDA_VISIBLE_DEVICES"] = ""
        report["environment"]["official_cuda_visible_devices"] = official_env.get("CUDA_VISIBLE_DEVICES")
        report["official_command"] = cmd
        with log_path.open("w") as log_handle:
            proc = subprocess.run(cmd, cwd=source, env=official_env, stdout=log_handle, stderr=subprocess.STDOUT, timeout=7200)
        report["official_returncode"] = proc.returncode
        report["science_flags"]["official_quick_test_executed"] = True
        check("official_process_returncode", proc.returncode == 0, proc.returncode)

        config = json.loads((output_dir / "config.json").read_text())
        summary = json.loads((output_dir / "summary.json").read_text())
        result_files = select_result_files(output_dir)
        results = [json.loads(p.read_text()) for p in result_files]
        overview = summary.get("experiment_overview", {})
        check("summary_12_total", overview.get("total_experiments") == 12, overview)
        check("summary_12_success", overview.get("successful") == 12, overview)
        check("summary_zero_failed", overview.get("failed") == 0, overview)
        check("actual_12_result_payloads", len(results) == 12, [p.name for p in result_files])
        for key, value in EXPECTED_QUICK.items():
            check(f"saved_config_{key}", config.get(key) == value, {"actual": config.get(key), "expected": value})

        expected_keys = {(c, v) for c in EXPECTED_QUICK["constraints"] for v in EXPECTED_QUICK["variants"]}
        actual_keys = {(r.get("constraint_type"), r.get("variant")) for r in results}
        check("unique_experiment_matrix", actual_keys == expected_keys and len(actual_keys) == 12, sorted(actual_keys))
        check("all_protein_and_seed", all(r.get("protein_name") == "O15263" and r.get("seed") == 42 for r in results), None)

        per_run = []
        all_sequences = set()
        final_ok = True
        best_ok = True
        trajectory_total = 0
        trajectory_valid = 0
        for path, result in zip(result_files, results):
            trajectory = result.get("trajectory", {})
            candidates = trajectory.get("discrete_sequences", [])
            iterations = trajectory.get("iterations", [])
            final_seq = result.get("final_sequence", "")
            best = result.get("best_seq_design") or {}
            best_seq = best.get("discrete_sequence", "")
            try:
                final_translate_ok = translate(final_seq) == protein and result.get("amino_acids_match") is True
            except Exception:
                final_translate_ok = False
            try:
                best_translate_ok = translate(best_seq) == protein
            except Exception:
                best_translate_ok = False
            final_ok &= final_translate_ok
            best_ok &= best_translate_ok
            trajectory_total += len(candidates)
            for candidate in candidates:
                all_sequences.add(candidate)
                try:
                    trajectory_valid += int(translate(candidate) == protein)
                except Exception:
                    pass
            per_run.append({
                "file": path.name,
                "constraint_type": result.get("constraint_type"),
                "variant": result.get("variant"),
                "seed": result.get("seed"),
                "status": result.get("status"),
                "iterations": result.get("iterations"),
                "trajectory_iterations": iterations,
                "recorded_discrete_candidates": len(candidates),
                "final_amino_acids_preserved": final_translate_ok,
                "best_amino_acids_preserved": best_translate_ok,
                "final_sequence_sha256": hashlib.sha256(final_seq.encode()).hexdigest(),
                "best_sequence_sha256": hashlib.sha256(best_seq.encode()).hexdigest(),
                "initial_accessibility": result.get("initial_accessibility"),
                "final_accessibility": result.get("final_accessibility"),
                "best_accessibility": result.get("best_accessibility"),
                "optimization_time_s": result.get("optimization_time"),
            })
        check("all_final_protein_preserved", final_ok, None)
        check("all_best_protein_preserved", best_ok, None)
        check("trajectory_24_records", trajectory_total == 24, trajectory_total)
        check("two_iterations_per_result", all(r["trajectory_iterations"] == [0, 1] for r in per_run), None)
        check("all_results_completed", all(r["status"] == "completed" for r in per_run), None)

        log_text = log_path.read_text(errors="replace")
        check("official_log_pretrained_load", "DeepRaccess model loaded successfully" in log_text, None)
        check("official_log_no_random_fallback", "using random initialization" not in log_text, None)
        report["summary_quirks"] = {
            "progress_json_listed_in_summary_experiment_files": "progress.json" in summary.get("experiment_files", []),
            "counting_rule": "Only JSON payloads other than config.json, summary.json and progress.json are counted as experiment results.",
        }
        report["per_run"] = per_run
        report["cost_and_discrete_records"] = {
            "official_total_wall_time_s": overview.get("total_time"),
            "sum_optimization_time_s": sum(float(r["optimization_time_s"]) for r in per_run),
            "recorded_discrete_candidates": trajectory_total,
            "unique_recorded_discrete_candidates": len(all_sequences),
            "trajectory_amino_acid_preserving_candidates": trajectory_valid,
            "final_evaluation_records": len(results),
            "caution": "Trajectory/final record counts are not a complete instrumented count of all DeepRaccess calls and are not yet a unified-cost comparison.",
        }
        artifacts = [output_dir / "config.json", output_dir / "summary.json", output_dir / "progress.json", *result_files, log_path, materialization_path]
        report["artifacts"] = [
            {"path": str(p), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in artifacts if p.is_file()
        ]
        report["scope_note"] = "Fixed-source official quick-test smoke only. No full-12x12 run, multi-seed statistics, main baseline ranking, dense-budget result, functional expression claim or SOTA claim."
        if all(item["pass"] for item in report["checks"]):
            report["status"] = "PASS_OFFICIAL_QUICK_TEST_SMOKE"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        check("unhandled_exception", False, report["error"])

    report["finished_utc"] = utcnow()
    report["orchestration_wall_time_s"] = time.time() - started
    report["checks_passed"] = sum(bool(x["pass"]) for x in report["checks"])
    report["checks_total"] = len(report["checks"])
    write_json(audit_output, report)
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "audit": str(audit_output)}, indent=2))
    return 0 if report["status"] == "PASS_OFFICIAL_QUICK_TEST_SMOKE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
