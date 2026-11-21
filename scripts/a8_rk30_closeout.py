#!/usr/bin/env python3
"""Release-gated RK30 result packaging; no refitting or threshold changes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fmt(value, digits=4):
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "NA"
    if isinstance(value, (bool, np.bool_)):
        return "PASS" if value else "FAIL"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return f"{float(value):.{digits}g}"


def split_test(name: str) -> tuple[str, str]:
    model = "histgb" if name.startswith("histgb_") else "ridge"
    endpoint = "mse_improvement" if name.endswith("mse_improvement") else "spearman"
    return model, endpoint


def normalize_primary(tests: list[dict], n_variants: int, n_clusters: int) -> list[dict]:
    rows = []
    for test in tests:
        model, endpoint = split_test(test["test"])
        rows.append({
            "direction": test["pair"], "model": model, "endpoint": endpoint,
            "effect": float(test["mean_seed_effect"]),
            "primary_seed_effect": float(test["observed_effect"]),
            "ci_low": float(test["ci95"][0]), "ci_high": float(test["ci95"][1]),
            "permutation_p": float(test["p_cluster_swap"]), "holm_p": float(test["p_holm"]),
            "positive_seed_fraction": float(test["positive_seeds"]) / 10.0,
            "n_variants": n_variants, "n_clusters": n_clusters, "pass": bool(test["pass"]),
        })
    return rows


def normalize_secondary(tests: list[dict], n_variants: int, n_clusters: int) -> list[dict]:
    rows = []
    for test in tests:
        model, endpoint = split_test(test["test"])
        rows.append({
            "direction": test["context"], "model": model, "endpoint": endpoint,
            "effect": float(test["mean_seed_effect"]),
            "primary_seed_effect": float(test["observed_effect"]),
            "ci_low": float(test["ci95"][0]), "ci_high": float(test["ci95"][1]),
            "permutation_p": float(test["p_cluster_swap"]), "holm_p": float(test["p_holm"]),
            "positive_seed_fraction": float(test["positive_seeds"]) / 10.0,
            "n_variants": n_variants, "n_clusters": n_clusters, "pass": bool(test["pass"]),
        })
    return rows


def performance_rows(tests: list[dict], absolute: list[dict], key: str) -> list[dict]:
    rows = []
    for test in tests:
        model, endpoint = split_test(test["test"])
        group = test[key]
        metric = "mse" if endpoint == "mse_improvement" else "spearman"
        matching = [x for x in absolute if x[key] == group]
        simple = next(x for x in matching if x["arm"] == model + "_simple")
        structure = next(x for x in matching if x["arm"] == model + "_structure")
        null = next((x for x in matching if x["arm"] == "null"), None)
        rows.append({
            "direction": group, "model": model, "endpoint": endpoint,
            "simple_mean": float(simple[metric]), "structure_mean": float(structure[metric]),
            "null_mean": None if null is None else float(null[metric]),
            "effect": float(test["mean_seed_effect"]),
        })
    return rows


def markdown_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines.extend("| " + " | ".join(str(x) for x in row) + " |" for row in rows)
    return "\n".join(lines)


def summarize_outcomes(path: Path, conditions: list[str]) -> dict:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for condition in conditions:
        values = [float(row["target__" + condition]) for row in rows]
        summary[condition] = {
            "n": len(values), "mean": statistics.fmean(values),
            "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
            "min": min(values), "max": max(values),
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--artifact-root", required=True)
    args = parser.parse_args()
    root = Path(args.artifact_root).resolve()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text())
    model_path = root / "RK30_MODEL_SUMMARY.json"
    raw_path = root / "RK30_RAW_VERIFICATION.json"
    independent_path = root / "RK30_MODEL_INDEPENDENT.json"
    counting_path = root / "RK30_COUNTING.json"
    missing = [str(p) for p in [protocol_path, model_path, raw_path, independent_path, counting_path] if not p.is_file()]
    if missing:
        raise SystemExit("Missing release inputs: " + ", ".join(missing))
    model = json.loads(model_path.read_text())
    raw = json.loads(raw_path.read_text())
    independent = json.loads(independent_path.read_text())
    counting = json.loads(counting_path.read_text())
    n_variants = int(model["n_common_variants"])
    n_clusters = int(model["n_common_clusters"])
    primary_records = normalize_primary(model["primary_transport_tests"], n_variants, n_clusters)
    secondary_records = normalize_secondary(model["secondary_within_context_tests"], n_variants, n_clusters)
    primary_perf = performance_rows(model["primary_transport_tests"], model["primary_transport_absolute_performance"], "pair")
    secondary_perf = performance_rows(model["secondary_within_context_tests"], model["secondary_within_context_absolute_performance"], "context")
    gates = {
        "production_complete": model["status"] == "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION",
        "raw_independent_pass": raw["status"] == "PASS_RK30_RAW_VERIFICATION",
        "model_independent_pass": independent["status"] == "PASS_INDEPENDENT_MODEL_VERIFICATION",
        "production_summary_binding": independent["production_summary_sha256"] == sha256(model_path),
        "protocol_binding": raw["protocol_sha256"] == model["protocol_sha256"] == sha256(protocol_path),
        "counting_binding": raw["counting_summary_sha256"] == model["counting_report_sha256"] == sha256(counting_path),
        "cohort": bool(counting["coverage_feasible"]) and n_variants >= 100 and n_clusters >= 50,
        "cohort_binding": counting["common_variants"] == n_variants and counting["common_clusters"] == n_clusters,
        "primary_finite": all(np.isfinite([r[k] for k in ["effect", "ci_low", "ci_high", "permutation_p", "holm_p"]]).all() for r in primary_records),
        "secondary_finite": all(np.isfinite([r[k] for k in ["effect", "ci_low", "ci_high", "permutation_p", "holm_p"]]).all() for r in secondary_records),
        "fit_count": model["total_model_fits"] == independent["transport_fits_recomputed"] + independent["within_fits_recomputed"] == 1700 and independent["fit_count_pass"],
        "independent_decision": independent["scientific_conclusion_pass"] and independent["independent_family_pass"] == model["context_transportable_mfe_increment_pass"],
        "endpoint_count": len(primary_records) == 16 and len(secondary_records) == 12,
    }
    if not all(gates.values()):
        raise SystemExit("Release gates failed: " + json.dumps(gates, indent=2))

    direction_rows = []
    for pair in dict.fromkeys(r["direction"] for r in primary_records):
        rows = [r for r in primary_records if r["direction"] == pair]
        direction_rows.append({"direction": pair, "all_four_endpoints_pass": all(r["pass"] for r in rows), "passed_endpoints": sum(r["pass"] for r in rows), "total_endpoints": len(rows)})
    condition_rows = []
    for condition in dict.fromkeys(r["direction"] for r in secondary_records):
        rows = [r for r in secondary_records if r["direction"] == condition]
        condition_rows.append({"condition": condition, "all_four_endpoints_pass": all(r["pass"] for r in rows), "passed_endpoints": sum(r["pass"] for r in rows), "total_endpoints": len(rows)})
    repo = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        commit = None
    code_hashes = {}
    for relative in [
        "scripts/a8_rk30_download_hela_r1.py", "scripts/a8_rk30_spool_transfer.py", "scripts/a8_rk30_fixed_reference_counts.py",
        "scripts/a8_rk30_run_matched_context.py", "scripts/a8_rk30_verify_raw_counts.py",
        "scripts/a8_rk30_verify_model.py", "scripts/a8_rk30_test_freeze.py",
        "scripts/a8_rk30_test_model.py", "scripts/a8_rk30_closeout.py", "scripts/a8_rk30_integrate_manuscript.py",
    ]:
        path = repo / relative
        if path.is_file():
            code_hashes[relative] = sha256(path)
    artifact_relative = [
        "fixed_reference_r1_counts.csv", "matched_context_outcomes.csv", "RK30_COUNTING.json",
        "model/analysis_matched_context.csv", "model/transport_oof_predictions.csv",
        "model/transport_seed_metrics.csv", "model/transport_seed_effects.csv",
        "model/within_context_oof_predictions.csv", "model/within_context_seed_metrics.csv",
        "model/within_context_seed_effects.csv", "RK30_MODEL_SUMMARY.json",
        "RK30_RAW_VERIFICATION.json", "RK30_MODEL_INDEPENDENT.json",
    ]
    artifact_hashes = {name: sha256(root / name) for name in artifact_relative if (root / name).is_file()}
    conditions = list(dict.fromkeys(r["direction"] for r in secondary_records))
    result = {
        "schema_version": "a8-rk30-closeout-v1",
        "status": "PASS_RK30_VERIFIED_RESULT_PACKAGING",
        "scientific_conclusion": model["scientific_conclusion"],
        "primary_family_supported": bool(model["context_transportable_mfe_increment_pass"]),
        "release_gates": gates,
        "git_commit_at_packaging": commit,
        "protocol_sha256": sha256(protocol_path),
        "coverage": {
            "variants": n_variants, "clusters": n_clusters, "conditions": conditions,
            "condition_score_summary": summarize_outcomes(root / "matched_context_outcomes.csv", conditions),
        },
        "primary_direction_summary": direction_rows,
        "secondary_condition_summary": condition_rows,
        "primary_endpoints": primary_records,
        "secondary_endpoints": secondary_records,
        "absolute_performance_seed": int(model["primary_seed"]),
        "primary_absolute_performance": primary_perf,
        "secondary_absolute_performance": secondary_perf,
        "scientific_flags": model["scientific_flags"],
        "cost": {
            "fit_count": model["total_model_fits"], "transport_fit_count": model["transport_model_fits"],
            "within_context_fit_count": model["within_context_model_fits"], "cpu_threads": 1,
            "production_cost_seconds": model["elapsed_seconds"],
            "independent_verification_cost_seconds": independent.get("cost_seconds"),
        },
        "code_sha256": code_hashes, "artifact_sha256": artifact_hashes,
        "limitations": [
            "Same 152 observed-R1 GFP references and 74 fixed sequence clusters; not full-CDS or protein OOD.",
            "HeLa and HEK293 cell-line comparisons cannot isolate every cell-line-specific mechanism.",
            "Predicted MFE is not measured structure; bin-weighted Flow-seq scores are not direct translation velocity or decay.",
            "No functional-untouched evaluation, prospective design-build-test, or generator training was authorized.",
            "No complete external SOTA or time-matched generator claim follows from these fixed-context ridge/HistGB experiments.",
        ],
    }
    result_path = root / "RK30_CLOSEOUT.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    closeout_digest = sha256(result_path)

    primary_table = markdown_table(
        ["Direction", "Model", "Endpoint", "Effect", "95% CI", "Holm p", "Positive seeds", "Pass"],
        [[r["direction"], r["model"], r["endpoint"], fmt(r["effect"]), f"[{fmt(r['ci_low'])}, {fmt(r['ci_high'])}]", fmt(r["holm_p"]), f"{r['positive_seed_fraction']:.1f}", fmt(r["pass"])] for r in primary_records],
    )
    absolute_table = markdown_table(
        ["Direction", "Model", "Endpoint", "Null (primary seed)", "Simple (primary seed)", "Structure (primary seed)", "Mean-seed delta"],
        [[r["direction"], r["model"], r["endpoint"], fmt(r["null_mean"]), fmt(r["simple_mean"]), fmt(r["structure_mean"]), fmt(r["effect"])] for r in primary_perf],
    )
    secondary_table = markdown_table(
        ["Condition", "Model", "Endpoint", "Effect", "95% CI", "Holm p", "Positive seeds", "Pass"],
        [[r["direction"], r["model"], r["endpoint"], fmt(r["effect"]), f"[{fmt(r['ci_low'])}, {fmt(r['ci_high'])}]", fmt(r["holm_p"]), f"{r['positive_seed_fraction']:.1f}", fmt(r["pass"])] for r in secondary_records],
    )
    direction_table = markdown_table(
        ["Transport direction", "Passed endpoints", "Family pass"],
        [[r["direction"], f"{r['passed_endpoints']}/{r['total_endpoints']}", fmt(r["all_four_endpoints_pass"])] for r in direction_rows],
    )
    closeout_md = f"""# A8-RK30 matched-context verified closeout

## Release and scientific decision

- Packaging: `PASS_RK30_VERIFIED_RESULT_PACKAGING`; all raw/model independent gates passed.
- Scientific conclusion: `{model['scientific_conclusion']}`.
- Common complete cohort: {n_variants} variants / {n_clusters} fixed clusters.
- Actual fits: {model['total_model_fits']} (800 transport + 900 within-context), single-thread CPU.
- Production seconds: {model['elapsed_seconds']:.6f}; independent model verification seconds: {fmt(independent.get('cost_seconds'))}.

## Primary ordered transport

{direction_table}

{primary_table}

## Absolute null/simple/structure performance

Values are absolute performance at the frozen primary seed ({model['primary_seed']}); the delta column remains the mean effect over 10 seeds. They prevent a positive increment from being mistaken for a useful absolute model.

{absolute_table}

## Secondary within-context analysis

These 12 endpoints have a separate Holm family and cannot rescue a failed transport family.

{secondary_table}

## Interpretation boundary

- This experiment holds study, vector family, variant references, observed 300-nt coverage and predicted-structure definitions constant while varying host/intron context.
- It does not establish full-CDS/protein OOD, measured-structure effects, translation velocity, decay, clinical expression, or complete external SOTA.
- A negative transport result is not evidence that RNA structure is universally irrelevant; it is specific to these endpoints, references, conditions and models.
- Functional untouched remains frozen; no generator training or prospective experimental claim is authorized.

## Reproduction

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
/home/codonflow-clean-env-v1/bin/python scripts/a8_rk30_test_freeze.py
/home/codonflow-clean-env-v1/bin/python scripts/a8_rk30_test_model.py
/home/codonflow-clean-env-v1/bin/python scripts/a8_rk30_verify_raw_counts.py --protocol configs/a8-rk30-mordstein-matched-context-v1.json --artifact-root <RK30_ROOT>
/home/codonflow-clean-env-v1/bin/python scripts/a8_rk30_verify_model.py --protocol configs/a8-rk30-mordstein-matched-context-v1.json --artifact-root <RK30_ROOT> --production-summary <RK30_ROOT>/RK30_MODEL_SUMMARY.json --report <RK30_ROOT>/RK30_MODEL_INDEPENDENT.json
/home/codonflow-clean-env-v1/bin/python scripts/a8_rk30_closeout.py --protocol configs/a8-rk30-mordstein-matched-context-v1.json --artifact-root <RK30_ROOT>
```

Machine-readable hashes, all 16 primary and 12 secondary endpoints, absolute performance, costs and limitations are in `RK30_CLOSEOUT.json`.
"""
    (root / "RK30_CLOSEOUT.md").write_text(closeout_md)
    manuscript_md = f"""## Matched host and 5′UTR-intron transport in the Mordstein GFP library

We held the GFP reference set, observed 300-nt read coverage, sequence clusters, feature definitions and models constant across HeLa without intron, HeLa with intron, and HEK293 without intron. The complete eight-experiment cohort contained {n_variants} variants in {n_clusters} sequence clusters. Four ordered transport directions were tested with two models and two endpoints each (16 confirmatory endpoints, one Holm family). The primary family decision was `{model['scientific_conclusion']}`.

{direction_table}

The table reports the number of passed endpoints among four per direction; a pass required a positive mean seed effect, a cluster-bootstrap 95% CI lower bound above zero, Holm-adjusted sign-swap permutation p<0.05, and at least 8/10 positive seeds. Full endpoint-level effects, CIs, adjusted p values, absolute null/simple/structure performance and secondary within-context results are reported in Supplementary Table RK30. These are predicted-MFE increments for bin-weighted Flow-seq outcomes, not direct measurements of translation velocity or RNA decay.
"""
    (root / "RK30_MANUSCRIPT_RESULTS.md").write_text(manuscript_md)
    ppt = {
        "title": "RK30 | Matched-context MFE transport", "conclusion": model["scientific_conclusion"],
        "cohort": f"{n_variants} variants / {n_clusters} clusters / 3 conditions",
        "verification": "Raw counts + 1,700 fits independently verified", "directions": direction_rows,
        "primary_endpoints": primary_records, "primary_absolute_performance": primary_perf,
        "absolute_performance_seed": int(model["primary_seed"]),
        "secondary_conditions": condition_rows, "cost_seconds": model["elapsed_seconds"],
        "closeout_sha256": closeout_digest,
        "interpretation_boundary": "Same GFP observed-R1 library; predicted MFE; no protein-OOD, velocity, decay or SOTA claim.",
    }
    (root / "RK30_RESULTS_FOR_PPT.json").write_text(json.dumps(ppt, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": result["status"], "scientific_conclusion": model["scientific_conclusion"], "closeout_sha256": closeout_digest, "ppt_json": str(root / "RK30_RESULTS_FOR_PPT.json")}, indent=2))


if __name__ == "__main__":
    main()
