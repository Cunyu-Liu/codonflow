#!/usr/bin/env python3
"""Run the pinned official VeloGRU processed-matrix loader without training."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

COMMIT = "38b48079856aeb9d33a1b10844d77aa8f6640032"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_dir / "VeloGRU"))
    import torch
    import VeloGRU_data
    matrix = args.source_dir / "VeloGRU/E.coli.summary.add.pro.SS.txt"
    x, density, length = VeloGRU_data.load_data(str(matrix))
    report = {
        "schema_version": "a8-rk03-veloharmo-official-loader-smoke-v1",
        "created_at": datetime.now(timezone.utc).isoformat(), "status": "PASS_OFFICIAL_LOADER_ONLY",
        "commit": COMMIT, "entrypoint": "VeloGRU/VeloGRU_data.py::load_data",
        "python": sys.executable, "torch_version": torch.__version__, "matrix_path": str(matrix),
        "matrix_sha256": hashlib.sha256(matrix.read_bytes()).hexdigest(),
        "x_shape": list(x.shape), "density_shape": list(density.shape), "length_shape": list(length.shape),
        "x_dtype": str(x.dtype), "density_dtype": str(density.dtype),
        "x_all_finite": bool(torch.isfinite(x).all()), "density_all_finite": bool(torch.isfinite(density).all()),
        "density_min": float(density.min()), "density_max": float(density.max()),
        "length_min": int(length.min()), "length_max": int(length.max()), "records": int(x.shape[0]),
        "training_performed": False, "publication_metrics_reproduced": False, "sota_claim": False,
        "scope": "Official processed-matrix loader smoke only; no training or performance comparison.",
    }
    report["pass"] = report["records"] == 1170 and report["x_all_finite"] and report["density_all_finite"] and len(report["x_shape"]) == 3 and report["x_shape"][0] == report["density_shape"][0] == report["length_shape"][0]
    report["status"] = "PASS_OFFICIAL_LOADER_ONLY" if report["pass"] else "FAIL_OFFICIAL_LOADER"
    if args.output.exists(): raise RuntimeError(f"refusing to overwrite {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    part = args.output.with_name(args.output.name + f".part-{os.getpid()}")
    part.write_text(json.dumps(report, indent=2) + "\n")
    os.replace(part, args.output)
    print(json.dumps(report, indent=2))
    if not report["pass"]: raise SystemExit(1)


if __name__ == "__main__":
    main()
