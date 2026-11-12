"""Freeze an HV reference exclusively from independent calibration objectives."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from codonflow.eval.anytime import FrozenReference


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--objectives-json", required=True,
                        help="JSON list of objective vectors or {'objectives': [...]}; never test outputs")
    parser.add_argument("--out", required=True)
    parser.add_argument("--margin", type=float, default=0.05)
    parser.add_argument("--upper-quantile", type=float, default=0.95)
    args = parser.parse_args()
    source = Path(args.objectives_json)
    payload = json.loads(source.read_text())
    points = payload.get("objectives") if isinstance(payload, dict) else payload
    frozen = FrozenReference.from_calibration(points, args.margin, args.upper_quantile)
    result = {
        "protocol": "a7_independent_calibration_v1",
        "source_role": "independent_calibration_not_test",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "n_calibration_points": len(points),
        **frozen.to_dict(),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({"out": str(out), "n_calibration_points": len(points)}))


if __name__ == "__main__":
    main()
