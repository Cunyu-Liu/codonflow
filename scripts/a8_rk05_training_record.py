#!/usr/bin/env python3
"""Create a compact, auditable RiboMIMO study-OOD training record."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolve_run_path(report: dict, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (Path(report["artifacts"]["driver"]["path"]).resolve().parent / "src" / path).resolve()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--production", type=Path, required=True)
    ap.add_argument("--independent", type=Path, required=True)
    ap.add_argument("--finalization", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-md", type=Path, required=True)
    args = ap.parse_args()
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    final = json.loads(args.finalization.read_text())
    independent_run = json.loads(Path(independent["independent_report"]["path"]).read_text())
    independent_by_seed = {r["seed"]: r for r in independent_run["runs"]}
    rows = []
    for run in production["runs"]:
        seed = run["seed"]
        other = independent_by_seed[seed]
        rows.append({
            "seed": seed,
            "split_seed": run["split_seed"],
            "source_train_records": run["source_train_records"],
            "source_validation_records": run["source_validation_records"],
            "target_records": run["target_records"],
            "best_epoch": run["best_epoch"],
            "epochs_completed": run["epochs_completed"],
            "best_source_validation_global_r2": run["best_validation_r2"],
            "ridge_alpha": run["ridge_selected_alpha"],
            "training_seconds": run["training_seconds"],
            "ridge_selection_seconds": run["ridge_selection_seconds"],
            "target_evaluation_seconds": run["target_evaluation_seconds"],
            "target_after_training_and_ridge_selection": run["target_evaluated_after_training_and_ridge_selection"],
            "independent_best_epoch": other["best_epoch"],
            "independent_epochs_completed": other["epochs_completed"],
            "independent_training_seconds": other["training_seconds"],
            "independent_ridge_alpha": other["ridge_selected_alpha"],
            "official_log": str(resolve_run_path(production, run["official_log"])),
            "official_log_sha256": run["official_log_sha256"],
            "checkpoint": str(resolve_run_path(production, run["checkpoint"])),
            "checkpoint_sha256": run["checkpoint_sha256"],
            "checkpoint_tensor_sha256": run["checkpoint_tensor_sha256"],
            "target_predictions": str(resolve_run_path(production, run["target_predictions"])),
            "target_predictions_sha256": run["target_predictions_file_sha256"],
            "target_prediction_arrays_sha256": run["target_predictions_arrays_sha256"],
        })
    report = {
        "schema": "a8.rk05.ribomimo_study_ood_training_record.v1",
        "status": "PASS_COMPLETE" if final["status"] == "PASS_RK05_RIBOMIMO_STUDY_OOD" else "INCOMPLETE",
        "scientific_result": final["scientific_outcome"],
        "production_sha256": sha256(args.production),
        "independent_sha256": sha256(args.independent),
        "finalization_sha256": sha256(args.finalization),
        "protocol_sha256": production["protocol_sha256"],
        "driver_sha256": production["prepare"]["driver_sha256"],
        "shared_gpu_timing_not_time_matched": True,
        "rows": rows,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    lines = [
        "# RiboMIMO Mohammad16 → Subtelny14 training record",
        "",
        f"- Status: `{report['status']}`; scientific result: `{report['scientific_result']}`.",
        "- Official architecture/loss/optimizer and source-validation global-R2 checkpoint selection retained.",
        "- Target evaluation occurred only after source training, early stopping and source-only ridge selection.",
        "- Wall times are observed on a shared GPU and are not time-matched cost evidence.",
        "",
        "| Seed | Split seed | Train/valid/target | Best/last epoch | Best source val. R2 | Ridge alpha | Train s | Ridge s | Target eval s | Independent best/last | Independent train s |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['seed']} | {r['split_seed']} | {r['source_train_records']}/{r['source_validation_records']}/{r['target_records']} "
            f"| {r['best_epoch']}/{r['epochs_completed']} | {r['best_source_validation_global_r2']:.9f} | {r['ridge_alpha']:g} "
            f"| {r['training_seconds']:.3f} | {r['ridge_selection_seconds']:.3f} | {r['target_evaluation_seconds']:.3f} "
            f"| {r['independent_best_epoch']}/{r['independent_epochs_completed']} | {r['independent_training_seconds']:.3f} |"
        )
    lines += [
        "",
        "## Evidence files",
        "",
        f"- Production: `{args.production}` (SHA256 `{report['production_sha256']}`)",
        f"- Independent verification: `{args.independent}` (SHA256 `{report['independent_sha256']}`)",
        f"- Finalization: `{args.finalization}` (SHA256 `{report['finalization_sha256']}`)",
        "",
        "Full per-epoch source-validation histories, official logs, checkpoints and target prediction hashes are retained in the production and independent reports.",
        "",
    ]
    args.output_md.write_text("\n".join(lines))
    print(json.dumps({"status": report["status"], "rows": len(rows), "json": str(args.output_json), "markdown": str(args.output_md)}))


if __name__ == "__main__":
    main()
