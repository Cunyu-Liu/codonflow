#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import numpy as np

from codonflow.models import kinetic_mean_field
import a10_03_e2_kinetic as experiment


def install_case_recorder(output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    original = kinetic_mean_field._solve_state_numpy
    state = {"calls": 0}

    def recording_solver(alpha, rates, beta, root_tolerance, residual_tolerance, maxfev):
        state["calls"] += 1
        np.savez(
            output_dir / "current_case.npz",
            alpha=np.float64(alpha), rates=np.asarray(rates, dtype=np.float64),
            beta=np.float64(beta), call=state["calls"],
            root_tolerance=root_tolerance, residual_tolerance=residual_tolerance,
            maxfev=maxfev,
        )
        return original(alpha, rates, beta, root_tolerance, residual_tolerance, maxfev)

    kinetic_mean_field._solve_state_numpy = recording_solver
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--raw", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    protocol = experiment.load_protocol(args.protocol)
    device = experiment.resolve_cuda_device(args.device)
    records, _ = experiment.parse_raw_matrix(args.raw, protocol["inputs"]["sha256"])
    splits = experiment.make_nested_splits(records, protocol["split"]["seed"])
    inner = splits[0]["inner"][0]
    train = [records[int(index)] for index in inner["train"]]
    validation = [records[int(index)] for index in inner["validation"]]
    state = install_case_recorder(args.output_dir)
    fit_seed = int(np.random.SeedSequence([1234, 0, 0]).generate_state(1)[0])
    rung = experiment.start_candidate_rung(
        "kinetic", train, validation, 0.0001, 0.0, fit_seed, protocol, device,
    )
    with (Path(args.output_dir) / "completed.json").open("x") as handle:
        json.dump({"calls": state["calls"], "rung": rung["rung"]}, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
