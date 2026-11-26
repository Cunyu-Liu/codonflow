import json
import time
from pathlib import Path

import numpy as np
import pytest
import torch

from codonflow.models import kinetic_mean_field
from scripts import a10_03_e2_kinetic as kinetic
from scripts import a10_03_e2_kinetic_parallel as parallel
from tests.test_a10_03_e2_kinetic import synthetic_protocol, write_raw


def synthetic_worker(task):
    value = task["value"]
    if value < 0:
        raise RuntimeError(f"injected shard failure {value}")
    time.sleep(0.002 * (3 - value % 3))
    spec = task["spec"]
    return {
        "spec": spec,
        "value": value,
        "array": np.asarray([value, value + 0.25], dtype=np.float64),
        "state": torch.tensor([value, -value], dtype=torch.float64),
        "curves": [{"epochs": [{"epoch": 1, "elapsed_seconds": time.perf_counter()}]}],
        "fit_costs": [{"continuation_wall_clock_seconds": time.perf_counter()}],
        "shard_cost": {"wall_clock_seconds": 0.001 + value / 1000},
    }


def failing_worker(task):
    raise RuntimeError("cache miss must fail")


def synthetic_tasks(protocol, failing=False):
    tasks = []
    for index, spec in enumerate(parallel.kinetic_first(parallel.shard_specs(protocol))):
        tasks.append({"spec": spec, "value": -1 if failing and index == 0 else index})
    return tasks


def test_schedule_has_27_shards_kinetic_first_and_canonical_merge_order():
    protocol = kinetic.load_protocol(Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json")
    canonical = parallel.shard_specs(protocol)
    scheduled = parallel.kinetic_first(canonical)
    assert len(canonical) == len(scheduled) == 27
    assert [spec["arm"] for spec in scheduled[:9]] == ["kinetic"] * 9
    assert scheduled[9:] == [spec for spec in canonical if spec["arm"] != "kinetic"]
    assert sorted(scheduled, key=parallel.canonical_spec_key) == canonical


def test_spawn_1_2_4_workers_are_bitwise_equivalent_and_cache_reuses_results(tmp_path):
    protocol = kinetic.load_protocol(Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json")
    tasks = synthetic_tasks(protocol)
    identity = {"synthetic": "same-science"}
    fingerprints = []
    canonical_results = None
    for workers in (1, 2, 4):
        results, ledger = parallel.execute_shard_tasks(
            tasks, tmp_path / f"workers_{workers}", identity, workers, synthetic_worker,
        )
        assert ledger["max_workers"] == workers
        assert ledger["start_method"] == "spawn"
        assert ledger["cache_hits"] == 0 and ledger["cache_misses"] == 27
        assert len(results) == 27
        fingerprints.append([parallel.shard_science_sha256(result) for result in results])
        if canonical_results is None:
            canonical_results = results
        else:
            for before, after in zip(canonical_results, results):
                np.testing.assert_array_equal(before["array"], after["array"])
                np.testing.assert_array_equal(before["state"].numpy(), after["state"].numpy())
                assert before["value"] == after["value"]
    assert fingerprints[0] == fingerprints[1] == fingerprints[2]
    cached, ledger = parallel.execute_shard_tasks(tasks, tmp_path / "workers_4", identity, 4, failing_worker)
    assert [parallel.shard_science_sha256(result) for result in cached] == fingerprints[0]
    assert ledger["cache_hits"] == 27 and ledger["cache_misses"] == 0


def test_spawn_failure_is_fail_closed_and_preserves_prior_complete_cache(tmp_path):
    protocol = kinetic.load_protocol(Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json")
    cache = tmp_path / "failure_cache"
    with pytest.raises(parallel.ShardExecutionError, match="injected shard failure"):
        parallel.execute_shard_tasks(synthetic_tasks(protocol, failing=True), cache, {"case": "failure"}, 4, synthetic_worker)
    assert not (cache / "summary.json").exists()
    assert not (cache / "complete.json").exists()
    assert len(list(cache.glob("*.npz"))) < 27
    for path in cache.glob("*.npz"):
        assert path.with_suffix(path.suffix + ".sha256").is_file()


def test_cache_rejects_identity_mismatch_and_tampering(tmp_path):
    spec = {"seed": 11, "seed_index": 0, "outer_fold": 0, "arm": "kinetic"}
    result = {
        "spec": spec, "array": np.asarray([1.0]), "selection": {"score": 0.25},
        "selected_state": {"state": torch.tensor([2.0])},
    }
    path = tmp_path / "shard.npz"
    parallel.save_shard(path, result, {"protocol": "a"})
    loaded = parallel.load_shard(path, {"protocol": "a"}, spec)
    np.testing.assert_array_equal(loaded["array"], result["array"])
    np.testing.assert_array_equal(loaded["selected_state"]["state"].numpy(), [2.0])
    with pytest.raises(RuntimeError, match="identity mismatch"):
        parallel.load_shard(path, {"protocol": "b"}, spec)
    with path.open("ab") as handle:
        handle.write(b"corruption")
    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        parallel.load_shard(path, {"protocol": "a"}, spec)


def test_backward_failure_snapshot_has_exact_reconstruction_state_and_refinement(tmp_path, monkeypatch):
    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    protocol = kinetic.load_protocol(Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json")
    protocol["training"]["batch_transcripts"] = 3
    protocol["training"]["successive_halving"]["rung_epochs"] = 1
    original = kinetic_mean_field._solve_adjoint_system

    def inject_backward_failure(*args, **kwargs):
        error = RuntimeError("injected precise backward failure")
        error.backward_failures = ({
            "batch_index": 1,
            "jacobian_transpose": torch.eye(4, dtype=torch.float64),
            "output_gradient": torch.arange(4, dtype=torch.float64),
            "multiplier": torch.arange(4, dtype=torch.float64),
            "recovery_extended": np.full(4, 1e-8, dtype=np.longdouble),
            "denominator_extended": np.ones(4, dtype=np.longdouble),
            "relative_recovery_extended": np.full(4, 1e-8, dtype=np.longdouble),
            "jacobian_condition_number": 12.5,
            "refinement_steps": 8,
            "qr_fallback": True,
            "qr_error": None,
        },)
        error.backward_snapshot_fields = tuple(error.backward_failures[0])
        raise error

    monkeypatch.setattr(kinetic_mean_field, "_solve_adjoint_system", inject_backward_failure)
    metadata = {
        "seed": 11, "outer_fold": 0, "arm": "kinetic", "grid_index": 2,
        "learning_rate": 1e-3, "weight_decay": 0.0, "inner_fold": 1, "fit_seed": 17,
    }
    with pytest.raises(RuntimeError, match="injected precise backward failure") as caught:
        kinetic.fit_candidate(
            "kinetic", records[:5], records[5:8], 1e-3, 0.0, 17, protocol, torch.device("cpu"),
            metadata, tmp_path / "snapshots",
        )
    path = Path(caught.value.codonflow_snapshot_path)
    assert path.is_file()
    with np.load(path, allow_pickle=False) as archive:
        saved = json.loads(archive["metadata"].item())
        assert saved["schema"] == parallel.FAILURE_SCHEMA
        assert saved["stage"] == "fixed_rung"
        assert (saved["seed"], saved["outer_fold"], saved["inner_fold"], saved["grid_index"]) == (11, 0, 1, 2)
        assert saved["epoch"] == 1 and saved["batch_index"] == 0
        assert set(saved["record_indices"]) <= {record.index for record in records[:5]}
        assert set(saved["record_ids"]) <= {record.transcript_id for record in records[:5]}
        assert len(saved["record_indices"]) == len(saved["record_ids"]) == 3
        assert saved["output_gradient_source"] == "autograd_output_hook"
        assert "native v9 backward_failures telemetry" in saved["refinement_trace_source"]
        assert saved["native_backward_failures"] == [{
            "failure_index": 0, "batch_sample": 1,
            "record_index": saved["record_indices"][1], "record_id": saved["record_ids"][1],
            "jacobian_condition_number": 12.5, "refinement_steps": 8,
            "qr_fallback": True, "qr_error": None, "array_prefix": "native_backward/0",
        }]
        for name in ("alpha", "k", "beta", "rho", "J", "output_gradient", "A", "jacobian"):
            assert name in archive.files and archive[name].size
        np.testing.assert_array_equal(archive["A"], archive["jacobian"])
        assert archive["A"].shape[0] == 3
        assert saved["refinement_trajectory"]
        assert any(key.startswith("refinement/0/0/") for key in archive.files)
        assert any(key.startswith("state/") for key in archive.files)
        assert archive["output_gradient"].shape[0] == 3
        for name in (
            "jacobian_transpose", "output_gradient", "multiplier", "recovery_extended",
            "denominator_extended", "relative_recovery_extended",
        ):
            assert archive[f"native_backward/0/{name}"].shape == ((4, 4) if name == "jacobian_transpose" else (4,))
        np.testing.assert_array_equal(archive["native_backward/0/jacobian_transpose"], np.eye(4))
        assert archive["native_backward/0/recovery_extended"].dtype == np.longdouble
    monkeypatch.setattr(kinetic_mean_field, "_solve_adjoint_system", original)


def test_parallel_failure_writes_failure_record_but_never_completion_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(kinetic, "resolve_cuda_device", lambda name: torch.device("cpu"))
    raw = write_raw(tmp_path / "synthetic.txt")
    protocol = synthetic_protocol(tmp_path, raw)
    output = tmp_path / "failed_output"

    def inject_failure(*args, **kwargs):
        raise parallel.ShardExecutionError({"seed": 11, "outer_fold": 0, "arm": "kinetic"}, RuntimeError("injected"))

    monkeypatch.setattr(parallel, "execute_shard_tasks", inject_failure)
    with pytest.raises(parallel.ShardExecutionError, match="injected"):
        kinetic.run_experiment(protocol, raw, output, max_workers=2)
    failure = json.loads((output / "failure.json").read_text())
    assert failure["status"] == "failed_no_completion_summary"
    assert failure["scientific_gate_claimed"] is False
    assert not (output / "summary.json").exists()
    assert not (output / "parallel.json").exists()
    assert not (output / "curves.jsonl").exists()
