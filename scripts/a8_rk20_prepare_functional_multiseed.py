#!/usr/bin/env python3
"""Freeze RK20 per-seed configs and verify every reused RK08 input."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def resolve(repo: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo / path


def assert_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label}: {path}")
    observed = sha256(path)
    if observed != expected:
        raise ValueError(f"{label} SHA256 mismatch: expected {expected}, observed {observed}")


def only_seed_changed(base: dict, generated: dict, seed: int) -> bool:
    left = json.loads(json.dumps(base))
    right = json.loads(json.dumps(generated))
    left_seed = left["training"].pop("seed")
    right_seed = right["training"].pop("seed")
    return left == right and right_seed == seed and left_seed != right_seed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--repo-root", default="/home/codonflow-a8-rk")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol["schema"] != "a8-rk20-functional-multiseed-protocol-v1":
        raise ValueError("unexpected protocol schema")
    if not protocol["frozen_before_new_seed_result_readout"]:
        raise ValueError("protocol was not frozen before new result readout")
    output_root = Path(protocol["output_root"])
    config_root = output_root / "configs"
    config_root.mkdir(parents=True, exist_ok=True)
    audit_root = resolve(repo, protocol["audit_root"])
    audit_root.mkdir(parents=True, exist_ok=True)

    data = protocol["data"]
    assert_hash(Path(data["functional_csv"]), data["functional_csv_sha256"], "functional data")
    assert_hash(Path(data["baseline_predictions"]), data["baseline_predictions_sha256"], "baseline predictions")
    training = protocol["training_contract"]
    train_script = resolve(repo, training["script"])
    assert_hash(train_script, training["script_sha256"], "training script")
    original = protocol["original_result"]
    assert_hash(resolve(repo, original["summary"]), original["summary_sha256"], "original summary")

    bases = protocol["base_configs"]
    base_configs = {}
    for arm in ("all", "none"):
        path = resolve(repo, bases[arm])
        assert_hash(path, bases[f"{arm}_sha256"], f"{arm} base config")
        base_configs[arm] = json.loads(path.read_text(encoding="utf-8"))

    existing = protocol["existing_outputs"]
    for arm in ("all", "none"):
        key = f"ribokinetic_{arm}"
        directory = Path(existing[key])
        assert_hash(directory / "predictions.csv", existing[f"{arm}_predictions_sha256"], f"existing {arm} predictions")
        run = json.loads((directory / "run_summary.json").read_text(encoding="utf-8"))
        if run["training"]["seed"] != protocol["existing_seed"]:
            raise ValueError(f"existing {arm} seed mismatch")
        if run["hashes"]["data_sha256"] != data["functional_csv_sha256"]:
            raise ValueError(f"existing {arm} data hash mismatch")
        if run["hashes"]["config_sha256"] != bases[f"{arm}_sha256"]:
            raise ValueError(f"existing {arm} config hash mismatch")
        if run["hashes"]["script_sha256"] != training["script_sha256"]:
            raise ValueError(f"existing {arm} training-script hash mismatch")

    entries = []
    for seed in protocol["seeds"]:
        for arm in ("all", "none"):
            model = f"ribokinetic_{arm}"
            if seed == protocol["existing_seed"]:
                directory = Path(existing[model])
                entries.append({
                    "seed": seed,
                    "arm": arm,
                    "model": model,
                    "status": "reuse_frozen",
                    "config": str(resolve(repo, bases[arm])),
                    "config_sha256": bases[f"{arm}_sha256"],
                    "output_dir": str(directory),
                    "predictions_sha256": existing[f"{arm}_predictions_sha256"],
                })
                continue
            generated = json.loads(json.dumps(base_configs[arm]))
            generated["training"]["seed"] = seed
            if not only_seed_changed(base_configs[arm], generated, seed):
                raise ValueError("generated config changed more than training.seed")
            config_path = config_root / f"{arm}_seed{seed}.json"
            serialized = json.dumps(generated, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
            if config_path.exists() and config_path.read_text(encoding="utf-8") != serialized:
                raise ValueError(f"refusing to overwrite different generated config: {config_path}")
            if not config_path.exists():
                config_path.write_text(serialized, encoding="utf-8")
            entries.append({
                "seed": seed,
                "arm": arm,
                "model": model,
                "status": "run_required",
                "config": str(config_path),
                "config_sha256": sha256(config_path),
                "output_dir": str(output_root / f"{arm}_seed{seed}"),
                "log": str(output_root / f"{arm}_seed{seed}.console.log"),
                "predictions_sha256": None,
            })

    manifest = {
        "schema": "a8-rk20-functional-multiseed-preparation-v1",
        "status": "PASS_PREPARATION_NEW_RESULTS_NOT_READ",
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "preparation_script_sha256": sha256(Path(__file__).resolve()),
        "training_script": str(train_script),
        "training_script_sha256": training["script_sha256"],
        "data_sha256": data["functional_csv_sha256"],
        "baseline_predictions_sha256": data["baseline_predictions_sha256"],
        "output_root": str(output_root),
        "entries": entries,
        "new_results_read": False,
        "functional_untouched_evaluated": False,
        "expensive_generation_authorized": False,
    }
    atomic_json(audit_root / "rk20_functional_multiseed_preparation_v1.json", manifest)
    atomic_json(output_root / "run_manifest.json", manifest)
    print(json.dumps({"status": manifest["status"], "new_runs": sum(e["status"] == "run_required" for e in entries), "entries": len(entries)}, indent=2))


if __name__ == "__main__":
    main()
