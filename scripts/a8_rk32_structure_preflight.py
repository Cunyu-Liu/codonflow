"""Label-free RK32 provenance preflight for source-reported Kudla energies."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import RNA

REPO = Path(__file__).resolve().parents[1]
COLUMNS = [
    "source_row", "seqId", "sequenceWithUtr", "utr_5prime", "cds",
    "mfe_5prime_kcal_mol", "rna_energy_entire_prot_kcal_mol",
    "cds_sha256", "exact_cds_group",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def energy(sequence: str, dangles: int) -> float:
    md = RNA.md()
    md.dangles = dangles
    md.temperature = 37.0
    value = float(RNA.fold_compound(sequence.replace("T", "U"), md).mfe()[1])
    if not math.isfinite(value) or abs(value) >= 100000:
        raise ValueError("non-finite ViennaRNA energy")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output_json, args.output_csv):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")

    source = args.source.resolve()
    frame = pd.read_csv(source, usecols=COLUMNS)
    if len(frame) != 154 or frame["exact_cds_group"].nunique() != 150:
        raise ValueError("expected 154 source rows and 150 exact-CDS groups")
    if frame[["seqId", "exact_cds_group"]].isna().any().any():
        raise ValueError("missing construct or group keys")

    rows = []
    seen = set()
    for record in frame.to_dict("records"):
        group = record["exact_cds_group"]
        if group in seen:
            continue
        seen.add(group)
        utr = str(record["utr_5prime"]).upper()
        cds = str(record["cds"]).upper()
        full = str(record["sequenceWithUtr"]).upper()
        if len(utr) != 144 or len(cds) != 720 or len(full) != 864:
            raise ValueError(f"unexpected sequence coverage for {record['seqId']}")
        if full != utr + cds or set(full) - set("ACGT"):
            raise ValueError(f"UTR/CDS concatenation failure for {record['seqId']}")
        if hashlib.sha256(cds.encode()).hexdigest() != record["cds_sha256"]:
            raise ValueError(f"CDS hash mismatch for {record['seqId']}")
        definitions = {
            "local_utr_minus4_cds38": utr[-4:] + cds[:38],
            "local_utr_minus4_cds37": utr[-4:] + cds[:37],
            "local_cds42": cds[:42],
            "local_cds41": cds[:41],
            "full_cds": cds,
            "full_cds_no_stop": cds[:-3],
            "full_mrna": full,
            "full_mrna_no_stop": full[:-3],
        }
        row = {
            "source_row": int(record["source_row"]),
            "seqId": record["seqId"],
            "exact_cds_group": group,
            "source_mfe_5prime_kcal_mol": float(record["mfe_5prime_kcal_mol"]),
            "source_mfe_full_kcal_mol": float(record["rna_energy_entire_prot_kcal_mol"]),
        }
        for name, sequence in definitions.items():
            for dangles in (0, 2):
                row[f"{name}__dangles{dangles}"] = energy(sequence, dangles)
        rows.append(row)
    if len(rows) != 150:
        raise ValueError("unique preflight row count mismatch")

    fields = list(rows[0])
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.with_suffix(args.output_csv.suffix + ".tmp").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    if args.output_csv.exists():
        raise FileExistsError(f"refusing to overwrite {args.output_csv}")
    args.output_csv.with_suffix(args.output_csv.suffix + ".tmp").replace(args.output_csv)

    comparisons = {}
    for name in fields:
        if "__dangles" not in name:
            continue
        target = "source_mfe_5prime_kcal_mol" if name.startswith("local_") else "source_mfe_full_kcal_mol"
        observed = np.asarray([row[target] for row in rows], dtype=float)
        predicted = np.asarray([row[name] for row in rows], dtype=float)
        delta = predicted - observed
        comparisons[name] = {
            "target": target,
            "n": len(rows),
            "pearson": float(np.corrcoef(observed, predicted)[0, 1]),
            "bias": float(delta.mean()),
            "mae": float(np.abs(delta).mean()),
            "rmse": float(np.sqrt(np.mean(delta ** 2))),
            "max_abs_delta": float(np.abs(delta).max()),
            "exact_within_1e-6": int(np.sum(np.abs(delta) <= 1e-6)),
            "within_0.05_kcal": int(np.sum(np.abs(delta) <= 0.05)),
            "within_0.5_kcal": int(np.sum(np.abs(delta) <= 0.5)),
        }
    best = {
        "local": min((key for key in comparisons if key.startswith("local_")), key=lambda key: comparisons[key]["rmse"]),
        "full": min((key for key in comparisons if key.startswith("full_")), key=lambda key: comparisons[key]["rmse"]),
    }
    payload = {
        "schema": "a8-rk32-structure-source-preflight-v1",
        "status": "PASS_LABEL_FREE_STRUCTURE_PREFLIGHT",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "source": str(source),
        "source_sha256": sha256(source),
        "columns_read": COLUMNS,
        "expression_columns_read": False,
        "model_fit_performed": False,
        "unique_exact_cds_groups": len(rows),
        "vienna_settings": "RNA.md(); temperature=37 C; dangles=0 or 2 as encoded in each candidate",
        "candidate_comparisons": comparisons,
        "lowest_rmse_candidate_by_provenance_only": best,
        "candidate_csv": str(args.output_csv),
        "candidate_csv_sha256": sha256(args.output_csv),
        "selection_boundary": "Candidates are compared only with source-reported structure fields; expression outcomes were not read or used. The lowest-RMSE candidate is provenance evidence, not an outcome-selected model arm.",
        "functional_untouched_read": False,
    }
    atomic_text(args.output_json, json.dumps(payload, indent=2) + "\n")
    print(json.dumps({
        "status": payload["status"],
        "rows": len(rows),
        "best": {key: {"candidate": value, **comparisons[value]} for key, value in best.items()},
        "output_json_sha256": sha256(args.output_json),
        "output_csv_sha256": payload["candidate_csv_sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
