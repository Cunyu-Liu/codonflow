#!/usr/bin/env python3
"""RK34 label-free matched start/upstream context preflight."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from a8_rk34_run_start_context import ARMS, CONTEXTS, context_sequences, mfe

SOURCE_COLUMNS = [
    "source_row", "seqId", "sequenceWithUtr", "utr_5prime", "cds",
    "cds_sha256", "exact_cds_group",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--rk32-preflight", type=Path, required=True)
    parser.add_argument("--rk32-preflight-sha256", required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output_csv, args.output_json):
        if path.exists():
            raise FileExistsError(path)

    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, details: object = None) -> None:
        checks.append({"name": name, "pass": bool(ok), "details": details})

    check("source_sha256", sha256(args.source) == args.source_sha256, sha256(args.source))
    check("rk32_preflight_sha256", sha256(args.rk32_preflight) == args.rk32_preflight_sha256, sha256(args.rk32_preflight))
    source = pd.read_csv(args.source, usecols=SOURCE_COLUMNS)
    check("source_rows_and_groups", len(source) == 154 and source["exact_cds_group"].nunique() == 150,
          {"rows": len(source), "groups": source["exact_cds_group"].nunique()})
    constant = source.groupby("exact_cds_group")[["cds", "utr_5prime", "sequenceWithUtr", "cds_sha256"]].nunique()
    check("within_group_sequence_identity", bool((constant == 1).all().all()), constant.max().to_dict())

    rows: list[dict[str, object]] = []
    identity_ok = True
    atg_ok = True
    for group, frame in source.groupby("exact_cds_group", sort=False):
        record = frame.sort_values("source_row").iloc[0]
        utr = str(record["utr_5prime"]).upper()
        cds = str(record["cds"]).upper()
        full = str(record["sequenceWithUtr"]).upper()
        valid = (
            len(utr) == 144 and len(cds) == 720 and len(full) == 864
            and full == utr + cds and not set(full) - set("ACGT")
            and hashlib.sha256(cds.encode()).hexdigest() == str(record["cds_sha256"])
        )
        identity_ok = identity_ok and valid
        atg_ok = atg_ok and cds[:3] == "ATG"
        contexts = context_sequences(utr, cds)
        row: dict[str, object] = {
            "source_row": int(record["source_row"]), "seqId": str(record["seqId"]),
            "exact_cds_group": str(group), "cds_sha256": str(record["cds_sha256"]),
        }
        for name, sequence in contexts.items():
            row[f"sequence__{name}"] = sequence
        for dangles in (2, 0):
            for name, sequence in contexts.items():
                row[f"{name}_d{dangles}"] = mfe(sequence, dangles)
        rows.append(row)
    check("full_mrna_and_cds_identity", identity_ok)
    check("native_start_atg_all_groups", atg_ok)
    candidate = pd.DataFrame(rows).sort_values("source_row").reset_index(drop=True)
    check("candidate_rows", len(candidate) == 150 and candidate["exact_cds_group"].nunique() == 150)
    check("matched_42nt", all(len(row[f"sequence__{context}"]) == 42 for row in rows for context in CONTEXTS))
    check("factorial_mask_identities", all(
        row["sequence__exact_real"][4:] == row["sequence__start_only"][4:]
        and row["sequence__exact_real"][:4] == row["sequence__upstream_only"][:4]
        and row["sequence__exact_real"][7:] == row["sequence__upstream_only"][7:]
        and row["sequence__start_only"][:4] == row["sequence__neither"][:4]
        and row["sequence__start_only"][7:] == row["sequence__neither"][7:]
        and row["sequence__upstream_only"][4:] == row["sequence__neither"][4:]
        for row in rows
    ))
    energies = candidate[ARMS].to_numpy(float)
    check("finite_nonconstant_energies", bool(np.isfinite(energies).all() and (candidate[ARMS].nunique() > 1).all()),
          {arm: int(candidate[arm].nunique()) for arm in ARMS})

    rk32 = pd.read_csv(args.rk32_preflight)
    merged = candidate.merge(rk32[["exact_cds_group", "local_utr_minus4_cds38__dangles0", "local_utr_minus4_cds38__dangles2"]],
                             on="exact_cds_group", how="left", validate="one_to_one")
    deltas = {}
    for dangles in (0, 2):
        delta = np.abs(merged[f"exact_real_d{dangles}"].to_numpy(float) - merged[f"local_utr_minus4_cds38__dangles{dangles}"].to_numpy(float))
        deltas[f"dangles{dangles}"] = float(np.max(delta))
        check(f"exact_matches_rk32_d{dangles}", bool(np.isfinite(delta).all() and np.max(delta) <= 1e-12), float(np.max(delta)))

    sequence_uniqueness = {context: int(candidate[f"sequence__{context}"].nunique()) for context in CONTEXTS}
    mfe_uniqueness = {arm: int(candidate[arm].nunique()) for arm in ARMS}
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    temporary_csv = args.output_csv.with_suffix(args.output_csv.suffix + ".tmp")
    candidate.to_csv(temporary_csv, index=False)
    temporary_csv.replace(args.output_csv)
    status = "PASS_LABEL_FREE_START_CONTEXT_PREFLIGHT" if all(row["pass"] for row in checks) else "FAIL"
    payload = {
        "schema": "a8-rk34-start-context-preflight-v1",
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source": str(args.source), "source_sha256": sha256(args.source),
        "rk32_preflight": str(args.rk32_preflight), "rk32_preflight_sha256": sha256(args.rk32_preflight),
        "columns_read": SOURCE_COLUMNS, "expression_columns_read": False, "model_fit_performed": False,
        "rows": len(candidate), "contexts": CONTEXTS, "arms": ARMS,
        "vienna_settings": "RNA.md(); temperature=37 C; isolated 42 nt; dangles=2 or 0",
        "sequence_uniqueness": sequence_uniqueness, "mfe_uniqueness": mfe_uniqueness,
        "exact_vs_rk32_max_abs_delta": deltas,
        "candidate_csv": str(args.output_csv), "candidate_csv_sha256": sha256(args.output_csv),
        "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks),
        "functional_untouched_read": False,
    }
    atomic_text(args.output_json, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": status, "checks_passed": payload["checks_passed"], "checks_total": len(checks),
                      "sequence_uniqueness": sequence_uniqueness, "mfe_uniqueness": mfe_uniqueness,
                      "candidate_csv_sha256": payload["candidate_csv_sha256"],
                      "report": str(args.output_json)}, indent=2))
    if status != "PASS_LABEL_FREE_START_CONTEXT_PREFLIGHT":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
