#!/usr/bin/env python3
"""Materialize the frozen RK08 train/dev-only channel-screen configs."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


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
    if arm.endswith("_only"):
        target = arm[:-5]
        assert target in names
        return {name: name == target for name in names}
    if arm.startswith("no_"):
        target = arm[3:]
        assert target in names
        return {name: name != target for name in names}
    raise ValueError(arm)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    protocol_path = args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    assert protocol["status"] == "FROZEN_BEFORE_CHANNEL_TRAINING_AND_TEST_READOUT"
    assert protocol["screen"]["include_splits"] == ["train", "dev"]
    assert protocol["functional_untouched_evaluated"] is False
    assert protocol["rk_g1_pass"] is False
    assert protocol["expensive_generation_authorized"] is False

    resolved = []
    for key in ("base_config", "train_script"):
        item = protocol[key]
        path = root / item["path"]
        assert path.is_file(), path
        assert sha256(path) == item["sha256"], key
        resolved.append(str(path))
    for key in ("data", "baseline_predictions"):
        item = protocol[key]
        path = Path(item["path"])
        assert path.is_file(), path
        assert sha256(path) == item["sha256"], key
    for item in protocol["prior_checkpoint_equivalence"].values():
        if isinstance(item, dict) and "path" in item:
            path = Path(item["path"])
            assert path.is_file(), path
            assert sha256(path) == item["sha256"], path

    base_path = root / protocol["base_config"]["path"]
    base = json.loads(base_path.read_text())
    assert base["include_splits"] == ["train", "dev", "test", "sequence_ood"]
    assert base["training"]["selection_metric"] == "cluster_balanced_mse"
    arms = protocol["arms_in_tie_break_order"]
    assert len(arms) == len(set(arms)) == 10
    config_hashes = {}
    active_mechanisms = {}
    for arm in arms:
        config = copy.deepcopy(base)
        config["ablation"] = arm
        config["include_splits"] = ["train", "dev"]
        assert config["max_rows_per_split"] is None
        assert not ({"test", "sequence_ood", "functional_untouched"} & set(config["include_splits"]))
        path = root / "configs" / f"a8_rk08_channel_screen_{arm}_config.json"
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing screen config: {path}")
        dump(path, config)
        config_hashes[arm] = {"path": str(path.relative_to(root)), "sha256": sha256(path)}
        active_mechanisms[arm] = active_map(arm)

    report_path = root / protocol["audit_root"] / "channel_screen_preparation_v1.json"
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite preparation report: {report_path}")
    report = {
        "schema": "a8-rk08-channel-screen-preparation-v1",
        "status": "PASS_CHANNEL_SCREEN_PREPARATION",
        "protocol_path": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "arms_in_tie_break_order": arms,
        "config_hashes": config_hashes,
        "active_mechanisms": active_mechanisms,
        "screen_include_splits": ["train", "dev"],
        "expected_rows": protocol["screen"]["expected_rows"],
        "test_or_ood_loaded": False,
        "functional_untouched_evaluated": False,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "output_root": protocol["output_root"],
    }
    dump(report_path, report)
    print(json.dumps({"status": report["status"], "arms": len(arms), "report": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()
