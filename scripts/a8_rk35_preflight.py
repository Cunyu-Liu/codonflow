#!/usr/bin/env python3
"""RK35 label-free preflight: natural coverage-transport windows on the frozen Kudla cohort.

Reads NO expression outcome columns. Verifies cohort identity, window coordinates,
ViennaRNA energies (dangles 2 primary, dangles 0 sensitivity), RK32 reuse-input
integrity (hash/keys/folds only, never outcome or prediction values), and frozen
RK27 cluster-fold reproduction. Produces the trunc-window energy CSV consumed by
the frozen production protocol.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import RNA

LABEL_FREE_USECOLS = [
    "source_row", "seqId", "sequenceWithUtr", "utr_5prime", "cds",
    "protein_aa", "CAI", "cds_sha256", "exact_cds_group",
]
FORBIDDEN_OUTCOME_COLUMNS = [
    "log10_expression", "expression_value", "pGK8_normalizedFlourescence",
    "linearModel_Fig1E", "rankRnaEnergy-4..37", "rankCAI", "target",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def energy(sequence: str, dangles: int) -> float:
    md = RNA.md()
    md.dangles = dangles
    md.temperature = 37.0
    value = float(RNA.fold_compound(sequence.replace("T", "U"), md).mfe()[1])
    if not np.isfinite(value) or abs(value) >= 100000:
        raise ValueError("non-finite MFE")
    return value


def make_cluster_folds(labels: np.ndarray, seed: int) -> tuple[np.ndarray, list[int]]:
    labels = np.asarray(labels, dtype=int)
    ids = np.array(sorted(np.unique(labels)), dtype=int)
    rng = np.random.default_rng(seed)
    shuffled = ids[rng.permutation(len(ids))].tolist()
    sizes = {int(c): int(np.sum(labels == c)) for c in ids}
    ordered = sorted(shuffled, key=lambda c: -sizes[int(c)])
    loads = np.zeros(5, dtype=int)
    assignment = {}
    for cluster in ordered:
        candidates = np.flatnonzero(loads == loads.min())
        fold = int(rng.choice(candidates))
        assignment[int(cluster)] = fold
        loads[fold] += sizes[int(cluster)]
    return np.array([assignment[int(c)] for c in labels], dtype=int), loads.tolist()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-csv", type=Path, required=True)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--coverage-report", type=Path, required=True)
    parser.add_argument("--coverage-sha", required=True)
    parser.add_argument("--rk32-preflight-csv", type=Path, required=True)
    parser.add_argument("--rk32-preflight-sha", required=True)
    parser.add_argument("--rk32-result", type=Path, required=True)
    parser.add_argument("--rk32-result-sha", required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    checks: list[dict] = []

    def check(name: str, ok: bool, details: object = None) -> None:
        checks.append({"name": name, "pass": bool(ok), "details": details})
        if not ok:
            raise ValueError(f"preflight check failed: {name}: {details}")

    check("main_csv_sha", sha256(args.main_csv) == args.main_sha)
    check("coverage_report_sha", sha256(args.coverage_report) == args.coverage_sha)
    check("rk32_preflight_sha", sha256(args.rk32_preflight_csv) == args.rk32_preflight_sha)
    check("rk32_result_sha", sha256(args.rk32_result) == args.rk32_result_sha)

    source = pd.read_csv(args.main_csv, usecols=LABEL_FREE_USECOLS)
    check("no_outcome_columns_read", not any(c in source.columns for c in FORBIDDEN_OUTCOME_COLUMNS), list(source.columns))
    check("measurement_rows_154", len(source) == 154, len(source))

    groups = []
    for cds_sha, group in source.groupby("cds_sha256", sort=False):
        check_ok = (
            group["cds"].nunique() == 1
            and group["protein_aa"].nunique() == 1
            and group["exact_cds_group"].nunique() == 1
            and group["utr_5prime"].nunique() == 1
            and group["sequenceWithUtr"].nunique() == 1
            and np.isfinite(group["CAI"]).all()
            and group["CAI"].nunique(dropna=False) == 1
        )
        if not check_ok:
            raise ValueError(f"non-unique exact-CDS construct: {cds_sha}")
        utr = str(group["utr_5prime"].iloc[0]).upper()
        cds = str(group["cds"].iloc[0]).upper()
        full = str(group["sequenceWithUtr"].iloc[0]).upper()
        if len(utr) != 144 or len(cds) != 720 or len(full) != 864:
            raise ValueError("transcript length failure")
        if full != utr + cds or set(full) - set("ACGT"):
            raise ValueError("transcript concatenation/alphabet failure")
        if hashlib.sha256(cds.encode()).hexdigest() != cds_sha:
            raise ValueError("CDS identity failure")
        exact_window = utr[-4:] + cds[:38]
        atg_window = cds[:42]
        trunc_window = cds[3:45]
        if len(exact_window) != 42 or len(atg_window) != 42 or len(trunc_window) != 42:
            raise ValueError("window length failure")
        if trunc_window[0] != cds[3] or trunc_window == atg_window:
            raise ValueError("trunc window coordinate failure")
        if atg_window[:3] != "ATG":
            raise ValueError("CDS does not start with ATG")
        if trunc_window[:3] == "ATG" and cds[3:6] == "ATG":
            raise ValueError("ambiguous trunc start")
        groups.append({
            "cds_sha256": cds_sha,
            "exact_cds_group": str(group["exact_cds_group"].iloc[0]),
            "first_source_row": int(group["source_row"].min()),
            "n_measurements": len(group),
            "CAI": float(group["CAI"].iloc[0]),
            "exact_window": exact_window,
            "atg_window": atg_window,
            "trunc_window": trunc_window,
            "trunc_excludes_start_atg": trunc_window != atg_window and cds[:3] not in (trunc_window[:3],),
        })
    frame = pd.DataFrame(groups).sort_values("first_source_row").reset_index(drop=True)
    check("exact_cds_groups_150", len(frame) == 150, len(frame))
    check("multi_measurement_groups_4", int((frame["n_measurements"] > 1).sum()) == 4)
    check("all_cds_start_atg", all(str(c).upper().startswith("ATG") for c in source.groupby("cds_sha256", sort=False)["cds"].first()))

    energies = []
    for record in frame.to_dict("records"):
        energies.append({
            "exact_cds_group": record["exact_cds_group"],
            "cds_sha256": record["cds_sha256"],
            "recomputed_exact_local__dangles2": energy(record["exact_window"], 2),
            "recomputed_cds_start__dangles2": energy(record["atg_window"], 2),
            "trunc_cds4_45__dangles2": energy(record["trunc_window"], 2),
            "trunc_cds4_45__dangles0": energy(record["trunc_window"], 0),
        })
    energy_frame = pd.DataFrame(energies)
    numeric = energy_frame.select_dtypes(include=[np.number]).to_numpy(float)
    check("all_window_energies_finite", bool(np.isfinite(numeric).all()))

    rk32_preflight = pd.read_csv(args.rk32_preflight_csv)
    check("rk32_preflight_rows_150", len(rk32_preflight) == 150 and rk32_preflight["exact_cds_group"].nunique() == 150)
    merged = energy_frame.merge(
        rk32_preflight[["exact_cds_group", "local_utr_minus4_cds38__dangles2", "local_cds42__dangles2"]],
        on="exact_cds_group", how="left", validate="one_to_one",
    )
    exact_delta = float(np.max(np.abs(merged["recomputed_exact_local__dangles2"] - merged["local_utr_minus4_cds38__dangles2"])))
    atg_delta = float(np.max(np.abs(merged["recomputed_cds_start__dangles2"] - merged["local_cds42__dangles2"])))
    check("exact_window_matches_rk32_preflight", exact_delta <= 1e-9, exact_delta)
    check("atg_window_matches_rk32_preflight", atg_delta <= 1e-9, atg_delta)
    d0_d2_delta = float(np.max(np.abs(energy_frame["trunc_cds4_45__dangles2"] - energy_frame["trunc_cds4_45__dangles0"])))
    check("trunc_d0_d2_recorded_separately", d0_d2_delta > 0.0, d0_d2_delta)

    coverage = json.loads(args.coverage_report.read_text())
    check("coverage_status", coverage["status"] == "PASS_LABEL_FREE_COVERAGE_AUDIT")
    facts_path = Path(coverage["facts_csv"])
    check("cluster_facts_sha", sha256(facts_path) == coverage["facts_sha256"])
    facts = pd.read_csv(facts_path)
    cluster_frame = frame.merge(facts[["cds_sha256", "sequence_cluster_id"]], on="cds_sha256", how="left", validate="one_to_one")
    check("clusters_37_complete", cluster_frame["sequence_cluster_id"].nunique() == 37 and not cluster_frame["sequence_cluster_id"].isna().any())
    labels = cluster_frame["sequence_cluster_id"].to_numpy(int)
    seeds = [20261221 + i for i in range(10)]
    fold_ok = True
    for seed in seeds:
        folds, loads = make_cluster_folds(labels, seed)
        if seed == 20261221 and loads != coverage["selected_coverage"]["primary_seed_fold_sizes"]:
            fold_ok = False
        for fold in range(5):
            train_clusters = set(labels[folds != fold])
            test_clusters = set(labels[folds == fold])
            if not train_clusters.isdisjoint(test_clusters):
                fold_ok = False
    check("folds_reproduce_rk27_no_leakage", fold_ok)

    rk32_result = json.loads(args.rk32_result.read_text())
    reuse = {}
    for key in ("oof_predictions.csv", "fold_assignments.csv", "seed_effects.csv"):
        entry = rk32_result["outputs"][key]
        path = Path(entry["path"])
        reuse[key] = {"path": str(path), "sha256": sha256(path), "expected": entry["sha256"]}
        check(f"rk32_reuse_{key}_sha", reuse[key]["sha256"] == entry["sha256"])
    oof = pd.read_csv(reuse["oof_predictions.csv"]["path"], usecols=["seed", "group_id", "cds_sha256", "sequence_cluster_id", "fold"])
    check("rk32_oof_rows_1500", len(oof) == 1500, len(oof))
    assignments = pd.read_csv(reuse["fold_assignments.csv"]["path"])
    fold_match = True
    for seed in seeds:
        folds, _ = make_cluster_folds(labels, seed)
        expected = dict(zip(cluster_frame["cds_sha256"], folds))
        current = assignments[assignments["seed"] == seed]
        if len(current) != 150:
            fold_match = False
        for record in current.to_dict("records"):
            if int(record["fold"]) != int(expected[record["cds_sha256"]]):
                fold_match = False
        oof_current = oof[oof["seed"] == seed]
        for record in oof_current.to_dict("records"):
            if int(record["fold"]) != int(expected[record["cds_sha256"]]):
                fold_match = False
    check("rk32_folds_match_regenerated_all_seeds", fold_match)
    check("rk32_oof_keys_complete", set(zip(oof["seed"], oof["cds_sha256"])) == {(s, c) for s in seeds for c in frame["cds_sha256"]})

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    out = energy_frame.drop(columns=["cds_sha256"]).merge(
        frame[["exact_cds_group", "cds_sha256", "trunc_excludes_start_atg"]], on="exact_cds_group", validate="one_to_one",
    )
    if args.output_csv.exists():
        raise FileExistsError(args.output_csv)
    out.to_csv(args.output_csv, index=False)
    report = {
        "schema": "a8-rk35-label-free-preflight-v1",
        "status": "PASS_LABEL_FREE_PREFLIGHT",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "outcome_columns_read": False,
        "model_fits_performed": 0,
        "n_measurement_rows": 154, "n_exact_cds_groups": 150, "n_sequence_clusters": 37,
        "windows": {
            "exact_local": "UTR[-4:]+CDS[:38], 42 nt, dangles=2, 37 C (RK32 vienna_local definition)",
            "cds_start_local": "CDS[0:42], 42 nt, includes start ATG, no UTR, dangles=2, 37 C (RK32 preflight local_cds42)",
            "trunc_local": "CDS[3:45] (1-based CDS4-45), 42 nt, excludes start ATG and UTR, dangles=2, 37 C (RK33 coverage, Kudla-matched dangles)",
            "trunc_local_d0": "CDS[3:45], dangles=0, 37 C (RK33 prediction definition; secondary sensitivity only)",
        },
        "max_exact_delta_vs_rk32": exact_delta, "max_atg_delta_vs_rk32": atg_delta,
        "trunc_d0_d2_max_abs_delta": d0_d2_delta,
        "reuse_inputs": reuse,
        "output_csv": {"path": str(args.output_csv), "sha256": sha256(args.output_csv), "bytes": args.output_csv.stat().st_size},
        "checks_passed": len(checks), "checks_total": len(checks), "checks": checks,
    }
    atomic_json(args.report, report)
    print(json.dumps({"status": report["status"], "checks": f"{len(checks)}/{len(checks)}", "output_csv": str(args.output_csv)}, indent=2))


if __name__ == "__main__":
    main()