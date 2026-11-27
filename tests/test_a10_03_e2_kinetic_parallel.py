import json
import multiprocessing
import os
import queue
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


def tracked_worker(task):
    active, peak, lock = task["active"], task["peak"], task["lock"]
    arm = task["spec"]["arm"]
    with lock:
        active[arm] += 1
        peak[arm] = max(peak[arm], active[arm])
    try:
        time.sleep(0.05)
        return synthetic_worker(task)
    finally:
        with lock:
            active[arm] -= 1


def blocking_failure_worker(task):
    task["started"].put({"value": task["value"], "pid": os.getpid()})
    task["barrier"].wait(timeout=30)
    if task["value"] < 0:
        snapshot_dir = Path(task["snapshot_dir"])
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        kinetic.write_json_exclusive(snapshot_dir / "injected_worker_failure.json", {
            "spec": task["spec"], "pid": os.getpid(), "status": "complete_before_raise",
        })
        raise RuntimeError("injected blocking shard failure")
    task["never_release"].wait(60)
    raise RuntimeError("blocking worker escaped scheduler termination")


def synthetic_cuda_worker(task):
    device = torch.device("cuda:0")
    spec = task["spec"]
    length = 96
    positions = np.arange(length)
    codons = (positions * 3 + spec["seed_index"]) % len(kinetic.CODONS)
    density = 1.0 + ((positions * 5 + spec["outer_fold"]) % 11)
    record = kinetic.Transcript(
        index=0, transcript_id="synthetic_cuda_long", codons=codons,
        counts=density.copy(), density=density,
        mask=(positions >= 5) & (positions < length - 4),
        coverage=1.0, positive_mean=float(density.mean()),
    )
    model = kinetic._new_model(device, spec["seed"], spec["arm"])
    packed = kinetic._pack([record], device)
    output = kinetic.forward_arm(model, spec["arm"], packed, task["model_config"])
    kinetic._transcript_losses(output, packed).mean().backward()
    torch.cuda.synchronize(device)
    gradient = torch.cat([parameter.grad.detach().reshape(-1) for parameter in model.parameters()])
    return {
        "spec": spec, "value": task["value"], "array": output["rho"].detach().cpu(),
        "state": gradient.cpu(),
        "residual": None if output["residual"] is None else output["residual"].detach().cpu(),
        "shard_cost": {"wall_clock_seconds": 0.0},
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


def test_banded_cuda_backend_identity_is_hashed_and_invalidates_cache(tmp_path, monkeypatch):
    protocol_path = Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json"
    protocol = kinetic.load_protocol(protocol_path)
    identity = parallel.source_identity(protocol_path)
    assert identity["banded_cuda_backend"] == kinetic.sha256_file(parallel.kinetic_banded_cuda.__file__)
    assert set(identity) == {
        "protocol", "implementation", "mean_field_operator", "banded_cuda_backend", "parallel_implementation",
    }

    tasks = synthetic_tasks(protocol)
    cache = tmp_path / "backend_identity_cache"
    parallel.execute_shard_tasks(tasks, cache, identity, 2, synthetic_worker)
    changed_backend = tmp_path / "kinetic_banded_cuda.py"
    changed_backend.write_text("# changed backend identity\n", encoding="utf-8")
    monkeypatch.setattr(parallel.kinetic_banded_cuda, "__file__", str(changed_backend))
    changed_identity = parallel.source_identity(protocol_path)
    assert changed_identity["banded_cuda_backend"] != identity["banded_cuda_backend"]
    assert {key: value for key, value in changed_identity.items() if key != "banded_cuda_backend"} == {
        key: value for key, value in identity.items() if key != "banded_cuda_backend"
    }
    with pytest.raises(RuntimeError, match="shard cache identity mismatch"):
        parallel.execute_shard_tasks(tasks, cache, changed_identity, 2, failing_worker)


def test_worker_rejects_backend_only_identity_change_before_training(tmp_path, monkeypatch):
    protocol_path = Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json"
    identity = parallel.source_identity(protocol_path)
    changed_backend = tmp_path / "kinetic_banded_cuda.py"
    changed_backend.write_text("# worker-observed backend change\n", encoding="utf-8")
    monkeypatch.setattr(parallel.kinetic_banded_cuda, "__file__", str(changed_backend))
    changed_identity = parallel.source_identity(protocol_path)
    assert {key: value for key, value in changed_identity.items() if key != "banded_cuda_backend"} == {
        key: value for key, value in identity.items() if key != "banded_cuda_backend"
    }
    monkeypatch.setattr(
        parallel, "_run_single_shard", lambda task: pytest.fail("training ran despite worker identity mismatch"),
    )
    task = {
        "spec": {"seed": 1234, "seed_index": 0, "outer_fold": 0, "arm": "kinetic"},
        "protocol_path": str(protocol_path), "identity": identity, "snapshot_dir": str(tmp_path / "failures"),
    }
    with pytest.raises(RuntimeError, match="worker source identity differs"):
        parallel._run_shard_task(task)
    failures = list((tmp_path / "failures").glob("*.json"))
    assert len(failures) == 1
    failure = json.loads(failures[0].read_text())
    assert failure["error_type"] == "RuntimeError"
    assert "worker source identity differs" in failure["error"]


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


@pytest.mark.integration
@pytest.mark.skipif(not torch.cuda.is_available(), reason="synthetic CUDA equivalence requires CUDA")
def test_spawn_1_2_4_workers_real_cuda_forward_backward_are_bitwise_equivalent(tmp_path):
    protocol = kinetic.load_protocol(Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json")
    tasks = synthetic_tasks(protocol)
    for task in tasks:
        task["model_config"] = protocol["model"]
    fingerprints = []
    for workers in (1, 2, 4):
        results, ledger = parallel.execute_shard_tasks(
            tasks, tmp_path / f"cuda_workers_{workers}", {"case": "real_cuda"}, workers, synthetic_cuda_worker,
        )
        assert len(results) == 27
        assert ledger["cache_misses"] == 27
        fingerprints.append([parallel.shard_science_sha256(result) for result in results])
    assert fingerprints[0] == fingerprints[1] == fingerprints[2]


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


def test_arm_worker_limits_are_enforced_without_changing_canonical_results(tmp_path):
    protocol = kinetic.load_protocol(Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json")
    tasks = synthetic_tasks(protocol)
    with multiprocessing.get_context("spawn").Manager() as manager:
        active, peak, lock = manager.dict(), manager.dict(), manager.Lock()
        limits = {"kinetic": 1, "independent": 2, "position": 3}
        for arm in kinetic.ARMS:
            active[arm], peak[arm] = 0, 0
        for task in tasks:
            task.update({"active": active, "peak": peak, "lock": lock})
        results, ledger = parallel.execute_shard_tasks(
            tasks, tmp_path / "arm_limits", {"case": "arm_limits"}, 21, tracked_worker, limits,
        )
        assert all(1 <= peak[arm] <= limits[arm] for arm in kinetic.ARMS)
        assert dict(active) == {arm: 0 for arm in kinetic.ARMS}
    assert ledger["configured_arm_max_workers"] == limits
    assert ledger["arm_max_workers"] == limits
    assert [result["spec"] for result in results] == parallel.shard_specs(protocol)
    assert ledger["cache_hits"] == 0 and ledger["cache_misses"] == 27


def test_first_failure_cancels_pending_terminates_pids_and_preserves_snapshot(tmp_path):
    protocol = kinetic.load_protocol(Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json")
    tasks = synthetic_tasks(protocol, failing=True)
    cache = tmp_path / "terminated_cache"
    snapshot_dir = tmp_path / "failure_snapshots"
    with multiprocessing.get_context("spawn").Manager() as manager:
        started, barrier, never_release = manager.Queue(), manager.Barrier(4), manager.Event()
        for task in tasks:
            task.update({
                "started": started, "barrier": barrier, "never_release": never_release,
                "snapshot_dir": str(snapshot_dir),
            })
        started_clock = time.perf_counter()
        with pytest.raises(parallel.ShardExecutionError, match="injected blocking shard failure") as caught:
            parallel.execute_shard_tasks(tasks, cache, {"case": "terminate"}, 4, blocking_failure_worker)
        assert time.perf_counter() - started_clock < 30
        observed = [started.get(timeout=1) for _ in range(4)]
        with pytest.raises(queue.Empty):
            started.get_nowait()
    cancellation = caught.value.scheduler_cancellation
    assert cancellation["all_workers_reaped"] is True
    assert len(cancellation["terminated_worker_pids"]) == 4
    assert cancellation["cancelled_pending_futures"] == 0
    assert len(cancellation["unsubmitted_shard_specs"]) == 23
    assert {entry["value"] for entry in observed} == {-1, 1, 2, 3}
    assert {entry["pid"] for entry in observed} == set(cancellation["terminated_worker_pids"])
    assert set(cancellation["worker_exit_codes"]) == {str(entry["pid"]) for entry in observed}
    for entry in observed:
        with pytest.raises(ProcessLookupError):
            os.kill(entry["pid"], 0)
    assert json.loads((snapshot_dir / "injected_worker_failure.json").read_text())["status"] == "complete_before_raise"
    assert not list(cache.glob("*.npz"))


def test_arm_worker_limit_validation_rejects_unknown_and_nonpositive_values():
    assert parallel.resolve_arm_max_workers(21)[1] == parallel.DEFAULT_ARM_MAX_WORKERS
    assert parallel.resolve_arm_max_workers(2)[1] == {arm: 2 for arm in kinetic.ARMS}
    with pytest.raises(ValueError, match="unknown arm"):
        parallel.resolve_arm_max_workers(4, {"unknown": 1})
    with pytest.raises(ValueError, match="positive integer"):
        parallel.resolve_arm_max_workers(4, {"kinetic": 0})


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


def test_pre_backward_snapshot_is_readable_after_injected_ima_without_later_cpu_conversion(tmp_path, monkeypatch):
    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    protocol = kinetic.load_protocol(Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json")
    protocol["training"]["batch_transcripts"] = 3
    protocol["training"]["successive_halving"]["rung_epochs"] = 1
    poisoned = {"value": False}
    original_cpu = torch.Tensor.cpu

    def guarded_cpu(self, *args, **kwargs):
        if poisoned["value"]:
            raise AssertionError("post-IMA tensor conversion attempted")
        return original_cpu(self, *args, **kwargs)

    def inject_ima(*args, **kwargs):
        poisoned["value"] = True
        raise RuntimeError("injected CUDA illegal memory access")

    monkeypatch.setattr(torch.Tensor, "cpu", guarded_cpu)
    monkeypatch.setattr(kinetic_mean_field, "_solve_adjoint_system", inject_ima)
    metadata = {
        "seed": 11, "outer_fold": 0, "arm": "kinetic", "grid_index": 2,
        "learning_rate": 1e-3, "weight_decay": 0.0, "inner_fold": 1, "fit_seed": 17,
    }
    with pytest.raises(RuntimeError, match="injected CUDA illegal memory access") as caught:
        kinetic.fit_candidate(
            "kinetic", records[:5], records[5:8], 1e-3, 0.0, 17, protocol, torch.device("cpu"),
            metadata, tmp_path / "snapshots",
        )
    latest = tmp_path / "snapshots" / "pre_backward_latest.npz"
    historical = Path(caught.value.codonflow_snapshot_path)
    assert latest.is_file() and historical.is_file() and latest != historical
    for path, schema in ((latest, parallel.PRE_BACKWARD_SCHEMA), (historical, parallel.FAILURE_SCHEMA)):
        with np.load(path, allow_pickle=False) as archive:
            saved = json.loads(archive["metadata"].item())
            assert saved["schema"] == schema
            assert saved["snapshot_timing"] == "post_forward_pre_backward"
            assert (saved["grid_index"], saved["inner_fold"], saved["epoch"], saved["batch_index"]) == (2, 1, 1, 0)
            assert len(saved["record_indices"]) == len(saved["record_ids"]) == 3
            assert set(saved["record_indices"]) <= {record.index for record in records[:5]}
            assert set(saved["record_ids"]) <= {record.transcript_id for record in records[:5]}
            assert saved["current_rng_state"] is not None
            assert set(saved["states"]) == {
                "epoch_start_model_state", "epoch_start_optimizer_state",
                "current_model_state", "current_optimizer_state",
            }
            for name in ("alpha", "k", "beta", "batch/target", "batch/mask", "packed/codons", "output_gradient"):
                assert name in archive.files and archive[name].size
            assert any(key.startswith("state/") for key in archive.files)
    with np.load(latest, allow_pickle=False) as archive:
        assert "A" not in archive.files and "jacobian" not in archive.files
    with np.load(historical, allow_pickle=False) as archive:
        assert json.loads(archive["metadata"].item())["error"] == "injected CUDA illegal memory access"
        assert "A" in archive.files and "jacobian" in archive.files


@pytest.mark.integration
@pytest.mark.skipif(not torch.cuda.is_available(), reason="requires CUDA")
def test_real_cuda_pre_backward_snapshot_survives_injected_ima(tmp_path, monkeypatch):
    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    protocol = kinetic.load_protocol(Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json")
    protocol["training"]["batch_transcripts"] = 2
    protocol["training"]["successive_halving"]["rung_epochs"] = 1
    device = kinetic.resolve_cuda_device("cuda:0")
    poisoned = {"value": False}
    original_cpu = torch.Tensor.cpu

    def guarded_cpu(self, *args, **kwargs):
        if poisoned["value"] and self.device.type == "cuda":
            raise AssertionError("post-IMA CUDA tensor conversion attempted")
        return original_cpu(self, *args, **kwargs)

    def inject_ima(*args, **kwargs):
        poisoned["value"] = True
        raise RuntimeError("injected CUDA illegal memory access")

    monkeypatch.setattr(torch.Tensor, "cpu", guarded_cpu)
    monkeypatch.setattr(kinetic_mean_field, "_solve_adjoint_system", inject_ima)
    metadata = {
        "seed": 11, "outer_fold": 0, "arm": "kinetic", "grid_index": 0,
        "learning_rate": 1e-3, "weight_decay": 0.0, "inner_fold": 0, "fit_seed": 17,
    }
    with pytest.raises(RuntimeError, match="injected CUDA illegal memory access") as caught:
        kinetic.fit_candidate(
            "kinetic", records[:3], records[3:5], 1e-3, 0.0, 17, protocol, device,
            metadata, tmp_path / "snapshots",
        )
    latest = tmp_path / "snapshots" / "pre_backward_latest.npz"
    historical = Path(caught.value.codonflow_snapshot_path)
    assert latest.is_file() and historical.is_file()
    assert historical.with_suffix(historical.suffix + ".sha256").is_file()
    for path, schema in ((latest, parallel.PRE_BACKWARD_SCHEMA), (historical, parallel.FAILURE_SCHEMA)):
        with np.load(path, allow_pickle=False) as archive:
            saved = json.loads(archive["metadata"].item())
            assert saved["schema"] == schema
            assert (saved["epoch"], saved["batch_index"]) == (1, 0)
            assert len(saved["record_indices"]) == len(saved["record_ids"]) == 2
            for name in ("alpha", "k", "beta", "batch/target", "batch/mask", "output_gradient"):
                assert archive[name].size
            assert any(key.startswith("state/") for key in archive.files)


def test_snapshot_disk_failure_does_not_replace_original_cuda_exception(tmp_path, monkeypatch):
    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    protocol = kinetic.load_protocol(Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json")
    protocol["training"]["batch_transcripts"] = 3
    protocol["training"]["successive_halving"]["rung_epochs"] = 1
    injected = RuntimeError("original CUDA illegal memory access")

    def disk_failure(*args, **kwargs):
        raise OSError(122, "injected disk quota exhaustion")

    def inject_ima(*args, **kwargs):
        raise injected

    monkeypatch.setattr(parallel, "_atomic_savez", disk_failure)
    monkeypatch.setattr(kinetic_mean_field, "_solve_adjoint_system", inject_ima)
    with pytest.raises(RuntimeError, match="original CUDA illegal memory access") as caught:
        kinetic.fit_candidate(
            "kinetic", records[:5], records[5:8], 1e-3, 0.0, 17, protocol, torch.device("cpu"),
            {"arm": "kinetic"}, tmp_path / "snapshots",
        )
    assert caught.value is injected
    assert not hasattr(caught.value, "codonflow_snapshot_path")
    assert any("failure snapshot could not be saved" in note for note in caught.value.__notes__)


def test_pre_backward_capture_does_not_change_normal_training_numerics(tmp_path):
    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    protocol = kinetic.load_protocol(Path(__file__).parents[1] / "configs" / "a10_03_e2_kinetic_protocol_v1.json")
    protocol["training"]["batch_transcripts"] = 2
    protocol["training"]["successive_halving"]["rung_epochs"] = 2
    arguments = (
        "independent", records[:4], records[4:6], 1e-3, 0.0, 17, protocol, torch.device("cpu"),
        {"seed": 11, "outer_fold": 0, "arm": "independent", "grid_index": 0, "inner_fold": 0},
    )
    baseline = kinetic.start_candidate_rung(*arguments)
    captured = kinetic.start_candidate_rung(*arguments, tmp_path / "snapshots")
    for name in ("model_state", "optimizer_state", "best_state"):
        assert kinetic.state_dict_sha256(baseline[name]) == kinetic.state_dict_sha256(captured[name])
    assert baseline["rng_state"] == captured["rng_state"]
    assert baseline["rung_validation_transcript_mse"] == captured["rung_validation_transcript_mse"]
    assert baseline["rung"]["last_state_sha256"] == captured["rung"]["last_state_sha256"]
    assert baseline["rung"]["last_optimizer_state_sha256"] == captured["rung"]["last_optimizer_state_sha256"]
    assert [
        {key: value for key, value in epoch.items() if key != "elapsed_seconds"} for epoch in baseline["curves"]
    ] == [
        {key: value for key, value in epoch.items() if key != "elapsed_seconds"} for epoch in captured["curves"]
    ]
    with np.load(tmp_path / "snapshots" / "pre_backward_latest.npz", allow_pickle=False) as archive:
        saved = json.loads(archive["metadata"].item())
        assert (saved["epoch"], saved["batch_index"]) == (2, 1)
        assert len(saved["record_ids"]) == 2


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
