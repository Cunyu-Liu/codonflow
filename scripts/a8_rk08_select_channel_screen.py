#!/usr/bin/env python3
"""Independently select one RK08 channel arm from train/dev-only artifacts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import torch


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def active_map(arm: str) -> dict[str, bool]:
    names = ("initiation", "velocity", "decay", "pair")
    if arm == "all":
        return {name: True for name in names}
    if arm == "none":
        return {name: False for name in names}
    if arm.endswith("_only") and arm[:-5] in names:
        target = arm[:-5]
        return {name: name == target for name in names}
    if arm.startswith("no_") and arm[3:] in names:
        target = arm[3:]
        return {name: name != target for name in names}
    raise ValueError(arm)


def recompute_partition_metrics(path: Path, partition: str) -> dict:
    errors: dict[str, list[float]] = {}
    seen_splits = set()
    count = 0
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            split = row["split"]
            seen_splits.add(split)
            assert split in {"train", "dev"}, split
            if split != partition:
                continue
            target = float(row["target"])
            prediction = float(row["prediction"])
            assert math.isfinite(target) and math.isfinite(prediction)
            cluster = row["cluster_id"]
            assert cluster
            errors.setdefault(cluster, []).append((prediction - target) ** 2)
            count += 1
    assert count > 0
    cluster_mse = [sum(values) / len(values) for _, values in sorted(errors.items())]
    return {
        "n_rows": count,
        "n_clusters": len(cluster_mse),
        "cluster_balanced_mse": sum(cluster_mse) / len(cluster_mse),
        "seen_splits": sorted(seen_splits),
    }


def state_equal(left: dict, right: dict) -> bool:
    return left.keys() == right.keys() and all(torch.equal(left[key], right[key]) for key in left)


def choose_arm(dev_values: dict[str, float], arms: list[str]) -> str:
    """Frozen minimum-dev rule with deterministic protocol-order tie breaking."""
    return min(arms, key=lambda arm: (dev_values[arm], arms.index(arm)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    protocol_path = args.protocol.resolve()
    preparation_path = args.preparation.resolve()
    protocol = json.loads(protocol_path.read_text())
    preparation = json.loads(preparation_path.read_text())
    assert protocol["status"] == "FROZEN_BEFORE_CHANNEL_TRAINING_AND_TEST_READOUT"
    assert preparation["status"] == "PASS_CHANNEL_SCREEN_PREPARATION"
    assert preparation["protocol_sha256"] == sha256(protocol_path)
    arms = protocol["arms_in_tie_break_order"]
    assert arms == preparation["arms_in_tie_break_order"]
    output_root = Path(protocol["output_root"]) / "screen"

    table = []
    artifact_hashes = {}
    checkpoints = {}
    for order, arm in enumerate(arms):
        config_item = preparation["config_hashes"][arm]
        config_path = root / config_item["path"]
        config = json.loads(config_path.read_text())
        assert sha256(config_path) == config_item["sha256"]
        assert config["ablation"] == arm
        assert config["include_splits"] == ["train", "dev"]
        run_dir = output_root / arm
        run_path = run_dir / "run_summary.json"
        predictions_path = run_dir / "predictions.csv"
        checkpoint_path = run_dir / "best.pt"
        history_path = run_dir / "history.json"
        resolved_path = run_dir / "resolved_config.json"
        for path in (run_path, predictions_path, checkpoint_path, history_path, resolved_path):
            assert path.is_file(), path
        run = json.loads(run_path.read_text())
        assert run["ablation"] == arm
        assert run["active_mechanisms"] == active_map(arm) == preparation["active_mechanisms"][arm]
        assert run["rows"] == protocol["screen"]["expected_rows"]
        assert set(run["metrics"]) == {"train", "dev"}
        assert run["hashes"]["data_sha256"] == protocol["data"]["sha256"]
        assert run["hashes"]["config_sha256"] == config_item["sha256"]
        assert run["hashes"]["script_sha256"] == protocol["train_script"]["sha256"]
        assert run["hashes"]["checkpoint_sha256"] == sha256(checkpoint_path)
        resolved = json.loads(resolved_path.read_text())
        assert resolved["include_splits"] == ["train", "dev"]
        assert resolved["active_mechanisms"] == active_map(arm)
        dev = recompute_partition_metrics(predictions_path, "dev")
        train = recompute_partition_metrics(predictions_path, "train")
        assert dev["seen_splits"] == train["seen_splits"] == ["dev", "train"]
        assert dev["n_rows"] == protocol["screen"]["expected_rows"]["dev"]
        assert dev["n_clusters"] == protocol["screen"]["expected_dev_clusters"]
        assert train["n_rows"] == protocol["screen"]["expected_rows"]["train"]
        assert math.isclose(dev["cluster_balanced_mse"], run["metrics"]["dev"]["cluster_balanced_mse"], rel_tol=0.0, abs_tol=1e-12)
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        assert checkpoint["active_mechanisms"] == active_map(arm)
        assert checkpoint["scope"] == "SUPERVISED_RK08_NOT_GENERATOR"
        assert checkpoint["normalizer"] is None
        assert sum(tensor.numel() for tensor in checkpoint["state_dict"].values()) == protocol["required_parameters_per_arm"]
        assert math.isclose(float(checkpoint["selected_dev_value"]), dev["cluster_balanced_mse"], rel_tol=0.0, abs_tol=1e-10)
        checkpoints[arm] = checkpoint
        table.append({
            "arm": arm,
            "tie_break_order": order,
            "dev_cluster_balanced_mse": dev["cluster_balanced_mse"],
            "dev_n_rows": dev["n_rows"],
            "dev_n_clusters": dev["n_clusters"],
            "selected_epoch": run["selected_epoch"],
            "parameters": protocol["required_parameters_per_arm"],
            "elapsed_seconds": run["training"]["elapsed_seconds"],
            "checkpoint_sha256": run["hashes"]["checkpoint_sha256"],
        })
        artifact_hashes[arm] = {
            "run_summary": sha256(run_path),
            "predictions": sha256(predictions_path),
            "checkpoint": sha256(checkpoint_path),
            "history": sha256(history_path),
            "resolved_config": sha256(resolved_path),
            "console_log": sha256(output_root / f"{arm}.console.log"),
        }

    equivalence = {}
    for arm in ("all", "none"):
        item = protocol["prior_checkpoint_equivalence"][arm]
        prior_path = Path(item["path"])
        assert sha256(prior_path) == item["sha256"]
        prior = torch.load(prior_path, map_location="cpu", weights_only=False)
        same = state_equal(checkpoints[arm]["state_dict"], prior["state_dict"])
        assert same, f"train/dev-only {arm} differs from prior full-load run"
        equivalence[arm] = {
            "state_dict_bitwise_equal": same,
            "selected_epoch_equal": checkpoints[arm]["selected_epoch"] == prior["selected_epoch"],
            "prior_checkpoint_sha256": item["sha256"],
            "screen_checkpoint_sha256": sha256(output_root / arm / "best.pt"),
        }

    selected_arm = choose_arm({row["arm"]: row["dev_cluster_balanced_mse"] for row in table}, arms)
    selected = next(row for row in table if row["arm"] == selected_arm)
    report_path = root / protocol["audit_root"] / "channel_screen_selection_v1.json"
    if report_path.exists():
        raise FileExistsError(report_path)
    report = {
        "schema": "a8-rk08-channel-selection-v1",
        "status": "PASS_CHANNEL_SELECTION_FROZEN",
        "protocol_sha256": sha256(protocol_path),
        "preparation_sha256": sha256(preparation_path),
        "selection_rule": protocol["screen"]["selection_rule"],
        "arms_in_tie_break_order": arms,
        "development_table": table,
        "selected_arm": selected_arm,
        "selected_dev_cluster_balanced_mse": selected["dev_cluster_balanced_mse"],
        "selected_checkpoint": {
            "path": str(output_root / selected_arm / "best.pt"),
            "sha256": selected["checkpoint_sha256"],
        },
        "none_checkpoint": {
            "path": str(output_root / "none" / "best.pt"),
            "sha256": artifact_hashes["none"]["checkpoint"],
        },
        "prior_checkpoint_equivalence": equivalence,
        "artifact_hashes": artifact_hashes,
        "screen_rows": protocol["screen"]["expected_rows"],
        "test_or_ood_used_for_selection": False,
        "functional_untouched_evaluated": False,
        "channel_screen_gate_pass": None,
        "velocity_mechanism_pass": False,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "complete_sota": False,
    }
    dump(report_path, report)
    print(json.dumps({"status": report["status"], "selected_arm": selected_arm, "selected_dev_cluster_balanced_mse": selected["dev_cluster_balanced_mse"], "report": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()
