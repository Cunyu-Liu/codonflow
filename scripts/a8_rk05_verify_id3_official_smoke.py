#!/usr/bin/env python3
"""Independently verify ID3 quick-test artifacts, source contracts and real scores."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import sys
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path

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
EXPECTED_QUICK = {
    "proteins": ["O15263"],
    "constraints": ["lagrangian", "ams", "cpc"],
    "variants": ["00", "01", "10", "11"],
    "iterations": 2,
    "seeds": 1,
    "enable_cai": False,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def translate_rna(seq: str) -> str:
    if not seq or len(seq) % 3 or re.fullmatch(r"[ACGU]+", seq) is None:
        raise ValueError("invalid RNA")
    return "".join(CODONS[seq[i:i+3]] for i in range(0, len(seq), 3))


def read_fasta(path: Path) -> str:
    return "".join(x.strip() for x in path.read_text().splitlines() if x.strip() and not x.startswith(">"))


def extract_preset(path: Path, function_name: str) -> dict:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
                    answer = {}
                    for kw in stmt.value.keywords:
                        if kw.arg:
                            try:
                                answer[kw.arg] = ast.literal_eval(kw.value)
                            except (ValueError, TypeError):
                                answer[kw.arg] = ast.unparse(kw.value)
                    return answer
    raise ValueError(function_name)


def detect_cpc_beta_omission(source_text: str) -> dict:
    """Detect CPC forward calling CodonPsiFunction.forward without its beta argument."""
    tree = ast.parse(source_text)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "CodonProfileConstraint"):
            continue
        for method in node.body:
            if not (isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name == "forward"):
                continue
            has_beta_parameter = any(arg.arg == "beta" for arg in method.args.args)
            for call in ast.walk(method):
                if not isinstance(call, ast.Call):
                    continue
                func = call.func
                is_psi = (
                    isinstance(func, ast.Attribute) and func.attr == "forward"
                    and isinstance(func.value, ast.Name) and func.value.id == "CodonPsiFunction"
                )
                if is_psi:
                    beta_passed = any(keyword.arg == "beta" for keyword in call.keywords)
                    return {
                        "detected": has_beta_parameter and not beta_passed,
                        "class": node.name,
                        "method": method.name,
                        "call_lineno": call.lineno,
                        "positional_argument_count": len(call.args),
                        "beta_keyword_passed": beta_passed,
                        "forward_has_beta_parameter": has_beta_parameter,
                    }
    return {"detected": False}


def detect_runner_ste_assumption(source_text: str) -> dict:
    """Locate the runner branch that treats beta=1 soft-path output as discrete."""
    tree = ast.parse(source_text)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)):
            continue
        test = node.test
        is_beta_one = (
            isinstance(test.left, ast.Name) and test.left.id == "beta"
            and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == 1.0
        )
        if not is_beta_one:
            continue
        for child in ast.walk(node):
            if not (isinstance(child, ast.Assign) and len(child.targets) == 1):
                continue
            target = child.targets[0]
            value = child.value
            if not (isinstance(target, ast.Name) and target.id == "accessibility"):
                continue
            if (
                isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                and value.func.attr == "item" and isinstance(value.func.value, ast.Name)
                and value.func.value.id == "accessibility_loss"
            ):
                return {"detected": True, "if_lineno": node.lineno, "assignment_lineno": child.lineno}
    return {"detected": False}


def expected_experiment_keys(preset: dict, base_seed: int = 42) -> set[tuple]:
    return {
        (p, c, v, base_seed + seed)
        for p in preset["proteins"]
        for c in preset["constraints"]
        for v in preset["variants"]
        for seed in range(preset["seeds"])
    }


def select_result_files(output_dir: Path) -> list[Path]:
    return sorted(p for p in output_dir.glob("*.json") if p.name not in {"config.json", "summary.json", "progress.json"})


def validate_result_payload(result: dict, expected_protein: str) -> dict:
    """Recompute protein and trajectory/best invariants without importing producer."""
    issues = []
    final_seq = result.get("final_sequence", "")
    try:
        final_translation = translate_rna(final_seq)
        if final_translation != expected_protein:
            issues.append("final_translation_mismatch")
        if result.get("actual_amino_acids") != final_translation:
            issues.append("reported_actual_amino_acids_mismatch")
    except Exception:
        issues.append("invalid_final_rna")
    if result.get("amino_acids_match") is not True:
        issues.append("amino_acids_match_not_true")
    trajectory = result.get("trajectory", {})
    candidates = trajectory.get("discrete_sequences", [])
    scores = trajectory.get("accessibility", [])
    iterations = trajectory.get("iterations", [])
    if len(candidates) != len(scores) or len(candidates) != len(iterations):
        issues.append("trajectory_length_mismatch")
    if result.get("iterations") != len(iterations):
        issues.append("iteration_count_mismatch")
    valid_scores = []
    valid_candidates = 0
    for candidate, score in zip(candidates, scores):
        try:
            if translate_rna(candidate) == expected_protein:
                valid_candidates += 1
                if isinstance(score, (int, float)) and math.isfinite(score):
                    valid_scores.append(float(score))
        except Exception:
            pass
    initial = result.get("initial_accessibility")
    best_value = result.get("best_accessibility")
    reference_best = min(valid_scores) if valid_scores else None
    if reference_best is None or not isinstance(best_value, (int, float)) or abs(reference_best - float(best_value)) > 1e-9:
        issues.append("best_accessibility_not_independent_minimum")
    if not candidates or not isinstance(initial, (int, float)) or abs(float(initial) - float(scores[0])) > 1e-9:
        issues.append("initial_accessibility_not_first_trajectory_score")
    expected_improvement = float(initial) - float(result.get("final_accessibility")) if isinstance(initial, (int, float)) and isinstance(result.get("final_accessibility"), (int, float)) else None
    if expected_improvement is None or not isinstance(result.get("improvement"), (int, float)) or abs(expected_improvement - float(result["improvement"])) > 1e-9:
        issues.append("improvement_not_first_minus_final")
    best = result.get("best_seq_design")
    best_seq = None
    if best is not None:
        best_seq = best.get("discrete_sequence", "")
        try:
            if translate_rna(best_seq) != expected_protein:
                issues.append("best_translation_mismatch")
        except Exception:
            issues.append("invalid_best_rna")
        iteration = best.get("iteration")
        if not isinstance(iteration, int) or iteration < 0 or iteration >= len(candidates):
            issues.append("best_iteration_invalid")
        elif candidates[iteration] != best_seq:
            issues.append("best_sequence_not_at_recorded_iteration")
        if not isinstance(best.get("accessibility"), (int, float)) or abs(float(best["accessibility"]) - float(best_value)) > 1e-9:
            issues.append("best_design_score_mismatch")
    elif reference_best is not None:
        issues.append("missing_best_design_despite_valid_candidate")
    return {
        "issues": issues,
        "final_sequence": final_seq,
        "best_sequence": best_seq,
        "initial_sequence": candidates[0] if candidates else None,
        "discrete_sequences": candidates,
        "candidate_count": len(candidates),
        "valid_candidate_count": valid_candidates,
        "best_design_present": best is not None,
    }


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
    parser.add_argument("--production-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verification-output", type=Path, required=True)
    parser.add_argument("--skip-model-recompute", action="store_true")
    args = parser.parse_args()
    source = args.id3_source.resolve()
    output_dir = args.output_dir.resolve()
    report = {
        "schema_version": "a8-rk05-id3-independent-verification-v2",
        "status": "FAIL_INDEPENDENT_VERIFICATION",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "producer_module_imported": False,
        "checks": [],
        "science_flags": {
            "quick_test_smoke_only": True,
            "main_baseline_comparison": False,
            "sota_claim": False,
            "dense_budget_evaluation": False,
            "functional_expression_claim": False,
        },
    }

    def check(name: str, passed: bool, detail=None) -> None:
        report["checks"].append({"name": name, "pass": bool(passed), "detail": detail})

    try:
        production = json.loads(args.production_report.read_text())
        check("producer_reports_pass", production.get("status") == "PASS_OFFICIAL_QUICK_TEST_SMOKE", production.get("status"))
        check("producer_all_checks_pass", all(x.get("pass") for x in production.get("checks", [])), f"{production.get('checks_passed')}/{production.get('checks_total')}")
        check("producer_did_not_use_upstream_example", production.get("science_flags", {}).get("upstream_example_used_as_result") is False, None)
        check("producer_has_no_sota_or_main_comparison", not production.get("science_flags", {}).get("sota_claim") and not production.get("science_flags", {}).get("main_baseline_comparison"), None)
        force_used = "--force" in production.get("official_command", [])
        check("official_force_cpu_scoped", (not force_used) or (
            production.get("execution_contract", {}).get("official_force") is True
            and production.get("environment", {}).get("requested_device") == "cpu"
        ), production.get("execution_contract"))
        requested_device = production.get("environment", {}).get("requested_device")
        check("official_cpu_cuda_isolation", requested_device != "cpu" or production.get("environment", {}).get("official_cuda_visible_devices") == "",
              production.get("environment", {}).get("official_cuda_visible_devices"))

        for key in ["id3_zip", "deepraccess_zip", "structured_weight"]:
            path = Path(production["source"][key])
            expected = production["source"][key + "_sha256"]
            check(f"sha256_{key}", path.is_file() and sha256(path) == expected, {"path": str(path), "actual": sha256(path) if path.is_file() else None, "expected": expected})
        for rel, expected in production["source"]["required_file_sha256"].items():
            check(f"source_file_{rel}", sha256(source / rel) == expected, None)
        materialization_path = Path(production["source"]["deepraccess_materialization_audit"])
        check("deepraccess_materialization_audit_sha256",
              materialization_path.is_file()
              and sha256(materialization_path) == production["source"]["deepraccess_materialization_audit_sha256"], None)
        materialization = json.loads(materialization_path.read_text())
        materialization_source = materialization.get("source", {})
        check("deepraccess_materialization_contract",
              materialization.get("status") == "PASS_FIXED_SOURCE_AND_WEIGHT_MATERIALIZATION"
              and materialization_source.get("commit") == "1a37235e31e1d5a7d5e2bfb705e3a00f1cdcaa9c"
              and materialization_source.get("zip_sha256") == production["source"]["deepraccess_zip_sha256"]
              and Path(materialization_source.get("target", "")).resolve() == (source / "DeepRaccess").resolve(), None)
        deep_mismatches = []
        for rel, registered in sorted(materialization_source.get("files", {}).items()):
            path = source / "DeepRaccess" / rel
            if not path.is_file() or path.stat().st_size != registered["bytes"] or sha256(path) != registered["sha256"]:
                deep_mismatches.append(rel)
        check("deepraccess_every_source_and_weight_hash", not deep_mismatches,
              {"registered_files": len(materialization_source.get("files", {})), "mismatches": deep_mismatches})
        config_path = source / "id3/experiments/configs/unified_experiment_config.py"
        quick = extract_preset(config_path, "quick_test")
        full = extract_preset(config_path, "full_12x12")
        for key, value in EXPECTED_QUICK.items():
            check(f"source_quick_{key}", quick.get(key) == value, {"actual": quick.get(key), "expected": value})
        check("source_full_1000_iterations", full.get("iterations") == 1000, full.get("iterations"))
        check("source_full_one_seed", full.get("seeds") == 1, full.get("seeds"))
        check("source_full_12_proteins", len(full.get("proteins", [])) == 12, full.get("proteins"))
        check("source_full_12_configurations_per_protein", len(full.get("constraints", [])) * len(full.get("variants", [])) == 12, None)
        check("producer_preset_ast_matches_independent_ast", production.get("source_preset_contract") == {"quick_test": quick, "full_12x12": full}, None)
        readme = (source / "README.md").read_text()
        check("readme_quick_5_vs_source_2_retained", "5 iterations" in readme and quick.get("iterations") == 2, None)
        check("readme_full_12_seeds_vs_source_1_retained", "12 seeds" in readme and full.get("seeds") == 1, None)

        cpc_source_path = source / "id3/constraints/codon_profile.py"
        runner_source_path = source / "id3/experiments/core/unified_experiment_runner.py"
        with zipfile.ZipFile(production["source"]["id3_zip"]) as archive:
            cpc_members = [name for name in archive.namelist() if name.endswith("/id3/constraints/codon_profile.py")]
            cpc_zip_bytes = archive.read(cpc_members[0]) if len(cpc_members) == 1 else b""
        check(
            "cpc_source_matches_fixed_zip",
            len(cpc_members) == 1 and cpc_source_path.is_file()
            and hashlib.sha256(cpc_zip_bytes).hexdigest() == sha256(cpc_source_path),
            {"zip_members": cpc_members, "source_sha256": sha256(cpc_source_path) if cpc_source_path.is_file() else None},
        )
        cpc_defect = detect_cpc_beta_omission(cpc_source_path.read_text())
        runner_assumption = detect_runner_ste_assumption(runner_source_path.read_text())
        check("upstream_cpc_beta_forward_omission_detected", cpc_defect.get("detected") is True, cpc_defect)
        check("upstream_runner_beta1_discrete_assumption_detected", runner_assumption.get("detected") is True, runner_assumption)
        report["upstream_cpc_ste_defect"] = {
            "cpc_forward": cpc_defect,
            "runner": runner_assumption,
            "cpc_source_sha256": sha256(cpc_source_path),
            "runner_source_sha256": sha256(runner_source_path),
            "explanation": "CPC accepts beta but omits it in CodonPsiFunction.forward, whose default is beta=0. The runner nevertheless treats beta=1 accessibility_loss as the hard/discrete value. This can corrupt CPC-01/11 trajectory, initial and best metric fields without changing the independently recomputed final-sequence score.",
        }

        saved_config = json.loads((output_dir / "config.json").read_text())
        summary = json.loads((output_dir / "summary.json").read_text())
        for key, value in EXPECTED_QUICK.items():
            check(f"saved_quick_{key}", saved_config.get(key) == value, {"actual": saved_config.get(key), "expected": value})
        overview = summary.get("experiment_overview", {})
        check("overview_total_success_failure", overview.get("total_experiments") == 12 and overview.get("successful") == 12 and overview.get("failed") == 0, overview)
        files = select_result_files(output_dir)
        check("exactly_12_real_result_payloads", len(files) == 12, [p.name for p in files])
        results = [json.loads(p.read_text()) for p in files]
        expected_keys = expected_experiment_keys(quick, int(saved_config.get("base_seed", 42)))
        actual_keys = {(r.get("protein_name"), r.get("constraint_type"), r.get("variant"), r.get("seed")) for r in results}
        check("experiment_key_matrix", actual_keys == expected_keys, {"expected": sorted(expected_keys), "actual": sorted(actual_keys)})
        check("all_result_status_completed", all(r.get("status") == "completed" for r in results), None)
        check("progress_json_quirk_recorded", production.get("summary_quirks", {}).get("progress_json_listed_in_summary_experiment_files") is True, summary.get("experiment_files", []))

        protein = read_fasta(source / "data/proteins/O15263.fasta.txt")
        check("O15263_length_64", len(protein) == 64, len(protein))
        validations = []
        per_run = []
        for path, result in zip(files, results):
            validation = validate_result_payload(result, protein)
            validations.append(validation)
            per_run.append({"file": path.name, **{k: v for k, v in validation.items() if k not in {"final_sequence", "best_sequence", "initial_sequence", "discrete_sequences"}}})
            check(f"payload_invariants_{path.name}", not validation["issues"], validation["issues"])
        check("total_24_discrete_trajectory_records", sum(v["candidate_count"] for v in validations) == 24, sum(v["candidate_count"] for v in validations))
        check("all_final_protein_preserved", all("invalid_final_rna" not in v["issues"] and "final_translation_mismatch" not in v["issues"] for v in validations), None)
        report["per_run_independent"] = per_run
        report["best_design_present_count"] = sum(v["best_design_present"] for v in validations)
        report["discrete_candidate_count"] = sum(v["candidate_count"] for v in validations)
        report["amino_acid_preserving_candidate_count"] = sum(v["valid_candidate_count"] for v in validations)

        artifact_actual = {x["path"]: x for x in production.get("artifacts", [])}
        required_artifacts = [output_dir / "config.json", output_dir / "summary.json", output_dir / "progress.json", *files, args.production_report.parent / "id3_official_quick_test.log", materialization_path]
        for path in required_artifacts:
            item = artifact_actual.get(str(path))
            check(f"artifact_hash_{path.name}", item is not None and item["sha256"] == sha256(path) and item["bytes"] == path.stat().st_size, str(path))
        log_text = (args.production_report.parent / "id3_official_quick_test.log").read_text(errors="replace")
        check("log_explicit_pretrained_load", "DeepRaccess model loaded successfully" in log_text, None)
        check("log_no_random_initialization_fallback", "using random initialization" not in log_text, None)

        if not args.skip_model_recompute:
            import torch
            os.chdir(source)
            sys.path.insert(0, str(source))
            from id3.utils.deepraccess_wrapper import DeepRaccessID3Wrapper
            from id3.config.utr_loader import get_default_utrs
            device = production["environment"]["requested_device"]
            if device == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("CUDA unavailable for independent score recomputation")
            wrapper = DeepRaccessID3Wrapper(production["source"]["structured_weight"], device=device)
            raw_utrs = get_default_utrs()
            # Independent adapter for ID3's DNA-compatible UTR files; model one-hot is ACGU.
            utrs = {key: value.upper().replace("T", "U") for key, value in raw_utrs.items()}
            base_index = {"A": 0, "C": 1, "G": 2, "U": 3}

            def independent_score(cds: str) -> float:
                seq = utrs["utr5"] + cds + utrs["utr3"]
                if re.fullmatch(r"[ACGU]+", seq) is None:
                    raise ValueError("invalid sequence for score recomputation")
                probs = torch.zeros((1, len(seq), 4), dtype=torch.float32, device=wrapper.device)
                for j, base in enumerate(seq):
                    probs[0, j, base_index[base]] = 1.0
                with torch.no_grad():
                    value = wrapper.compute_atg_window_accessibility(probs, atg_position=len(utrs["utr5"]), discrete=True)
                return float(value.detach().cpu().item())

            deltas = []
            score_cache = {}
            score_rows = []
            mismatch_runs = set()

            def cached_score(sequence: str) -> float:
                if sequence not in score_cache:
                    score_cache[sequence] = independent_score(sequence)
                return score_cache[sequence]

            for path, result, validation in zip(files, results, validations):
                candidates = validation["discrete_sequences"]
                trajectory_scores = [cached_score(sequence) for sequence in candidates]
                recomputed_final = cached_score(validation["final_sequence"])
                final_delta = abs(recomputed_final - float(result["final_accessibility"]))
                initial_delta = None
                recomputed_initial = None
                if validation["initial_sequence"]:
                    recomputed_initial = trajectory_scores[0]
                    initial_delta = abs(recomputed_initial - float(result["initial_accessibility"]))
                    deltas.append(initial_delta)
                best_delta = None
                recomputed_best = None
                if validation["best_sequence"]:
                    recomputed_best = cached_score(validation["best_sequence"])
                    best_delta = abs(recomputed_best - float(result["best_accessibility"]))
                    deltas.append(best_delta)
                deltas.append(final_delta)
                check(f"final_score_recompute_{path.name}", final_delta <= 2e-5, {"recomputed": recomputed_final, "recorded": result["final_accessibility"], "abs_delta": final_delta})
                if initial_delta is not None:
                    check(f"initial_score_recompute_{path.name}", initial_delta <= 2e-5, {"recomputed": recomputed_initial, "recorded": result["initial_accessibility"], "abs_delta": initial_delta})
                if best_delta is not None:
                    check(f"best_score_recompute_{path.name}", best_delta <= 2e-5, {"recomputed": recomputed_best, "recorded": result["best_accessibility"], "abs_delta": best_delta})

                valid_indices = []
                for index, sequence in enumerate(candidates):
                    try:
                        if translate_rna(sequence) == protein:
                            valid_indices.append(index)
                    except ValueError:
                        pass
                corrected_best_iteration = min(valid_indices, key=lambda index: trajectory_scores[index]) if valid_indices else None
                corrected_best_score = trajectory_scores[corrected_best_iteration] if corrected_best_iteration is not None else None
                corrected_best_sequence = candidates[corrected_best_iteration] if corrected_best_iteration is not None else None
                metric_mismatch = (
                    (initial_delta is not None and initial_delta > 2e-5)
                    or (best_delta is not None and best_delta > 2e-5)
                )
                key = (result.get("protein_name"), result.get("constraint_type"), result.get("variant"), result.get("seed"))
                if metric_mismatch:
                    mismatch_runs.add(key)
                recorded_trajectory = result.get("trajectory", {}).get("accessibility", [])
                score_rows.append({
                    "file": path.name,
                    "experiment_key": list(key),
                    "recorded_initial_accessibility": result.get("initial_accessibility"),
                    "recomputed_initial_accessibility": recomputed_initial,
                    "initial_abs_delta": initial_delta,
                    "recorded_best_accessibility": result.get("best_accessibility"),
                    "recomputed_official_best_sequence_accessibility": recomputed_best,
                    "best_abs_delta": best_delta,
                    "recorded_final_accessibility": result.get("final_accessibility"),
                    "recomputed_final_accessibility": recomputed_final,
                    "final_abs_delta": final_delta,
                    "recorded_trajectory_accessibility": recorded_trajectory,
                    "recomputed_trajectory_accessibility": trajectory_scores,
                    "trajectory_abs_deltas": [abs(float(saved) - recomputed) for saved, recomputed in zip(recorded_trajectory, trajectory_scores)],
                    "recomputed_best_iteration": corrected_best_iteration,
                    "recomputed_best_accessibility": corrected_best_score,
                    "recomputed_best_sequence_sha256": hashlib.sha256(corrected_best_sequence.encode()).hexdigest() if corrected_best_sequence else None,
                    "official_best_sequence_matches_recomputed_best": corrected_best_sequence == validation["best_sequence"],
                    "recomputed_initial_minus_final": (recomputed_initial - recomputed_final) if recomputed_initial is not None else None,
                    "acceptance": "FINAL_SEQUENCE_SCORE_ONLY__EXCLUDE_INITIAL_BEST_IMPROVEMENT_AND_TRAJECTORY_ACCESSIBILITY" if metric_mismatch else "FULL_QUICK_TEST_PAYLOAD_SCORES_VERIFIED",
                })
            expected_defect_runs = {("O15263", "cpc", "01", 42), ("O15263", "cpc", "11", 42)}
            check(
                "cpc_ste_metric_defect_scope_exact_and_final_scores_intact",
                mismatch_runs == expected_defect_runs
                and all(row["final_abs_delta"] <= 2e-5 for row in score_rows)
                and all(row["official_best_sequence_matches_recomputed_best"] for row in score_rows)
                and cpc_defect.get("detected") is True and runner_assumption.get("detected") is True,
                {"actual_mismatch_runs": sorted(mismatch_runs), "expected_mismatch_runs": sorted(expected_defect_runs)},
            )
            report["per_run_score_recomputation"] = score_rows
            report["bounded_acceptance"] = {
                "official_execution_completed_runs": len(results),
                "final_sequence_score_accepted_runs": sum(row["final_abs_delta"] <= 2e-5 for row in score_rows),
                "full_metric_payload_accepted_runs": sum(row["acceptance"] == "FULL_QUICK_TEST_PAYLOAD_SCORES_VERIFIED" for row in score_rows),
                "final_only_runs": [row["file"] for row in score_rows if row["acceptance"] != "FULL_QUICK_TEST_PAYLOAD_SCORES_VERIFIED"],
                "excluded_fields_for_final_only_runs": ["initial_accessibility", "best_accessibility", "best_seq_design.accessibility", "improvement", "trajectory.accessibility", "summary accessibility aggregates containing those fields"],
                "final_accessibility_remains_quick_test_only": True,
                "official_best_sequences_match_recomputed_argmin_for_all_runs": all(row["official_best_sequence_matches_recomputed_best"] for row in score_rows),
            }
            report["score_recomputation"] = {
                "performed": True,
                "device": device,
                "unique_sequences_scored": len(score_cache),
                "discrete_trajectory_records_scored": sum(len(v["discrete_sequences"]) for v in validations),
                "recorded_initial_best_final_values_checked": len(deltas),
                "max_abs_delta": max(deltas) if deltas else None,
                "tolerance": 2e-5,
                "torch": torch.__version__,
            }
        else:
            report["score_recomputation"] = {"performed": False, "reason": "explicit skip flag; not valid for final acceptance"}
            check("model_recompute_not_skipped", False, None)
        report["production_report_sha256"] = sha256(args.production_report)
        report["production_orchestration_wall_time_s"] = production.get("orchestration_wall_time_s")
        report["cost_and_discrete_records_independent"] = {
            "recorded_discrete_candidates": sum(v["candidate_count"] for v in validations),
            "final_evaluation_records": len(results),
            "caution": "Not a complete instrumented model-call count and not a unified-cost main comparison.",
        }
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        check("unhandled_exception", False, report["error"])

    report["checks_passed"] = sum(x["pass"] for x in report["checks"])
    report["checks_total"] = len(report["checks"])
    failed_names = {x["name"] for x in report["checks"] if not x["pass"]}
    report["failed_check_names"] = sorted(failed_names)
    if report["checks"] and not failed_names:
        report["status"] = "PASS_OFFICIAL_QUICK_TEST_INDEPENDENT_VERIFICATION"
    else:
        bounded = report.get("bounded_acceptance", {})
        expected_metric_failures = {
            f"{kind}_score_recompute_{filename}"
            for filename in bounded.get("final_only_runs", [])
            for kind in ("initial", "best")
        }
        recognized_bounded_defect = (
            bounded.get("official_execution_completed_runs") == 12
            and bounded.get("final_sequence_score_accepted_runs") == 12
            and bounded.get("full_metric_payload_accepted_runs") == 10
            and bounded.get("official_best_sequences_match_recomputed_argmin_for_all_runs") is True
            and failed_names == expected_metric_failures
            and any(x["name"] == "cpc_ste_metric_defect_scope_exact_and_final_scores_intact" and x["pass"] for x in report["checks"])
        )
        if recognized_bounded_defect:
            report["status"] = "BOUNDED_OFFICIAL_EXECUTION_COMPLETE_WITH_CPC_STE_TRAJECTORY_DEFECT"
            report["science_flags"].update({
                "official_execution_completed": True,
                "all_final_sequence_scores_independently_verified": True,
                "all_payload_metrics_independently_verified": False,
                "cpc_01_11_initial_best_improvement_and_trajectory_metrics_usable": False,
                "final_scores_main_baseline_ready": False,
            })
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["scope_note"] = "Independent verification of one official 2-iteration quick-test only. A bounded status retains all failed checks and accepts only independently recomputed final-sequence scores for the two affected CPC STE runs; no full experiment, baseline ranking, SOTA, dense-budget or functional claim."
    write_json(args.verification_output, report)
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "failed_checks": report["failed_check_names"], "output": str(args.verification_output)}, indent=2))
    return 0 if report["status"].startswith(("PASS_", "BOUNDED_")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
