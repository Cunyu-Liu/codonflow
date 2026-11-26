#!/usr/bin/env python3
"""Spawn-parallel execution and fail-closed shard artifacts for A10-03/E2."""
from __future__ import annotations

import concurrent.futures
import copy
import csv
import hashlib
import json
import multiprocessing
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from scripts import a10_03_e2_kinetic as kinetic

PARALLEL_SCHEMA = "a10-03-e2-kinetic-parallel-v1"
SHARD_SCHEMA = "a10-03-e2-kinetic-shard-v1"
FAILURE_SCHEMA = "a10-03-e2-kinetic-candidate-failure-v1"
DEFAULT_ARM_MAX_WORKERS = {"kinetic": 4, "independent": 8, "position": 8}
WORKER_TERMINATION_GRACE_SECONDS = 5.0


def shard_specs(protocol):
    return [
        {"seed": seed, "seed_index": seed_index, "outer_fold": outer, "arm": arm}
        for seed_index, seed in enumerate(protocol["training"]["model_seeds"])
        for outer in range(3) for arm in kinetic.ARMS
    ]


def kinetic_first(specs):
    return sorted(specs, key=lambda spec: (spec["arm"] != "kinetic", spec["seed_index"], spec["outer_fold"]))


def canonical_spec_key(spec):
    return spec["seed_index"], spec["outer_fold"], kinetic.ARMS.index(spec["arm"])


def shard_basename(spec):
    return f"seed_{spec['seed_index']:02d}_outer_{spec['outer_fold']:02d}_{spec['arm']}"


def _pack_tree(value, arrays):
    if isinstance(value, torch.Tensor):
        key = f"array_{len(arrays):06d}"
        arrays[key] = value.detach().cpu().numpy()
        return {"type": "tensor", "key": key}
    if isinstance(value, np.ndarray):
        key = f"array_{len(arrays):06d}"
        arrays[key] = value
        return {"type": "ndarray", "key": key}
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, (bool, int, float, str)):
        return {"type": "scalar", "value": value}
    if isinstance(value, list):
        return {"type": "list", "items": [_pack_tree(item, arrays) for item in value]}
    if isinstance(value, tuple):
        return {"type": "tuple", "items": [_pack_tree(item, arrays) for item in value]}
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            if isinstance(key, bool) or not isinstance(key, (str, int)):
                raise TypeError(f"unsupported shard dictionary key: {key!r}")
            items.append([key, _pack_tree(item, arrays)])
        return {"type": "dict", "items": items}
    raise TypeError(f"unsupported shard value: {type(value).__name__}")


def _unpack_tree(value, arrays):
    kind = value["type"]
    if kind == "scalar":
        return value["value"]
    if kind == "tensor":
        return torch.from_numpy(arrays[value["key"]].copy())
    if kind == "ndarray":
        return arrays[value["key"]].copy()
    if kind == "list":
        return [_unpack_tree(item, arrays) for item in value["items"]]
    if kind == "tuple":
        return tuple(_unpack_tree(item, arrays) for item in value["items"])
    if kind == "dict":
        return {key: _unpack_tree(item, arrays) for key, item in value["items"]}
    raise ValueError(f"unknown shard tree type {kind!r}")


def save_shard(path, result, identity):
    path = Path(path)
    digest_path = path.with_suffix(path.suffix + ".sha256")
    if path.exists() or digest_path.exists():
        raise FileExistsError(f"refusing to overwrite shard cache: {path}")
    arrays = {}
    metadata = {
        "schema": SHARD_SCHEMA, "identity": identity, "spec": result["spec"],
        "payload": _pack_tree(result, arrays),
    }
    arrays["metadata"] = np.asarray(json.dumps(metadata, ensure_ascii=False, allow_nan=False))
    with path.open("xb") as handle:
        np.savez_compressed(handle, **arrays)
    digest = kinetic.sha256_file(path)
    digest_path.write_text(digest + "\n", encoding="ascii")
    return digest


def load_shard(path, identity, spec):
    path = Path(path)
    digest_path = path.with_suffix(path.suffix + ".sha256")
    if not path.exists() and not digest_path.exists():
        raise FileNotFoundError(path)
    if not path.is_file() or not digest_path.is_file():
        raise RuntimeError(f"incomplete shard cache pair: {path}")
    expected_digest = digest_path.read_text(encoding="ascii").strip()
    if kinetic.sha256_file(path) != expected_digest:
        raise RuntimeError(f"shard cache SHA256 mismatch: {path}")
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(archive["metadata"].item())
        if metadata.get("schema") != SHARD_SCHEMA or metadata.get("identity") != identity:
            raise RuntimeError(f"shard cache identity mismatch: {path}")
        if metadata.get("spec") != spec:
            raise RuntimeError(f"shard cache spec mismatch: {path}")
        result = _unpack_tree(metadata["payload"], archive)
    if result.get("spec") != spec:
        raise RuntimeError(f"shard payload spec mismatch: {path}")
    return result


def _science_tree(value, key=None):
    if key in {"cost", "fit_costs", "shard_cost", "worker", "cache_hit", "wall_clock_seconds", "elapsed_seconds"}:
        return None
    if isinstance(value, dict):
        result = {}
        for item_key, item in value.items():
            normalized = _science_tree(item, item_key)
            if normalized is not None:
                result[item_key] = normalized
        return result
    if isinstance(value, list):
        return [_science_tree(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_science_tree(item) for item in value)
    return value


def shard_science_sha256(result):
    arrays = {}
    tree = _pack_tree(_science_tree(result), arrays)
    digest = hashlib.sha256()
    digest.update(json.dumps(tree, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    for key in sorted(arrays):
        digest.update(key.encode("ascii"))
        digest.update(str(arrays[key].dtype).encode("ascii"))
        digest.update(str(arrays[key].shape).encode("ascii"))
        digest.update(np.ascontiguousarray(arrays[key]).tobytes())
    return digest.hexdigest()


class ShardExecutionError(RuntimeError):
    def __init__(self, spec, original):
        self.spec = spec
        self.original = original
        super().__init__(f"shard {spec} failed: {type(original).__name__}: {original}")


def resolve_arm_max_workers(max_workers, arm_max_workers=None):
    kinetic._positive_int(max_workers, "max_workers")
    configured = dict(DEFAULT_ARM_MAX_WORKERS)
    if arm_max_workers is not None:
        unknown = set(arm_max_workers) - set(kinetic.ARMS)
        if unknown:
            raise ValueError(f"unknown arm worker limits: {sorted(unknown)}")
        configured.update(arm_max_workers)
    for arm, limit in configured.items():
        kinetic._positive_int(limit, f"arm_max_workers[{arm!r}]")
    effective = {arm: min(max_workers, limit) for arm, limit in configured.items()}
    return configured, effective


def _cancel_and_terminate(executor, futures, unsubmitted):
    cancelled = sum(future.cancel() for future in futures)
    processes = list(executor._processes.values())
    worker_pids = sorted(process.pid for process in processes if process.pid is not None)
    for process in processes:
        if process.is_alive():
            process.terminate()
    deadline = time.monotonic() + WORKER_TERMINATION_GRACE_SECONDS
    for process in processes:
        process.join(max(0.0, deadline - time.monotonic()))
    killed = []
    for process in processes:
        if process.is_alive():
            process.kill()
            killed.append(process.pid)
    kill_deadline = time.monotonic() + WORKER_TERMINATION_GRACE_SECONDS
    for process in processes:
        process.join(max(0.0, kill_deadline - time.monotonic()))
    executor.shutdown(wait=True, cancel_futures=True)
    return {
        "cancelled_pending_futures": int(cancelled),
        "unsubmitted_shard_specs": [task["spec"] for task, _ in unsubmitted],
        "terminated_worker_pids": worker_pids,
        "killed_worker_pids": sorted(killed),
        "worker_exit_codes": {str(process.pid): process.exitcode for process in processes},
        "all_workers_reaped": all(not process.is_alive() for process in processes),
    }


def execute_shard_tasks(tasks, cache_dir, identity, max_workers, worker, arm_max_workers=None):
    configured_arm_workers, effective_arm_workers = resolve_arm_max_workers(max_workers, arm_max_workers)
    cache_dir = Path(cache_dir).expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    ledger = []
    pending = []
    seen = set()
    for task in tasks:
        spec = task["spec"]
        key = canonical_spec_key(spec)
        if key in seen:
            raise ValueError(f"duplicate shard spec: {spec}")
        seen.add(key)
        path = cache_dir / f"{shard_basename(spec)}.npz"
        digest_path = path.with_suffix(path.suffix + ".sha256")
        if path.exists() or digest_path.exists():
            result = load_shard(path, identity, spec)
            results[key] = result
            ledger.append({
                "spec": spec, "cache_hit": True, "path": str(path),
                "sha256": digest_path.read_text(encoding="ascii").strip(),
                "shard_cost": result.get("shard_cost"),
            })
        else:
            pending.append((task, path))
    started = time.perf_counter()
    executor = None
    futures = {}
    active_by_arm = {arm: 0 for arm in kinetic.ARMS}
    try:
        if pending:
            executor = concurrent.futures.ProcessPoolExecutor(
                max_workers=min(max_workers, sum(effective_arm_workers.values())),
                mp_context=multiprocessing.get_context("spawn"),
            )

            def submit_ready():
                while len(futures) < max_workers:
                    ready_index = next((
                        index for index, (task, _) in enumerate(pending)
                        if active_by_arm[task["spec"]["arm"]] < effective_arm_workers[task["spec"]["arm"]]
                    ), None)
                    if ready_index is None:
                        return
                    task, path = pending.pop(ready_index)
                    arm = task["spec"]["arm"]
                    futures[executor.submit(worker, task)] = (task, path)
                    active_by_arm[arm] += 1

            submit_ready()
            while futures:
                done, _ = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    task, path = futures.pop(future)
                    spec = task["spec"]
                    active_by_arm[spec["arm"]] -= 1
                    try:
                        result = future.result()
                    except Exception as error:
                        raise ShardExecutionError(spec, error) from error
                    if result.get("spec") != spec:
                        raise RuntimeError(f"worker returned the wrong shard spec: expected {spec}")
                    result = kinetic._cpu_tree(result)
                    digest = save_shard(path, result, identity)
                    results[canonical_spec_key(spec)] = result
                    ledger.append({
                        "spec": spec, "cache_hit": False, "path": str(path), "sha256": digest,
                        "shard_cost": result.get("shard_cost"),
                    })
                submit_ready()
    except Exception as error:
        if executor is not None:
            error.scheduler_cancellation = _cancel_and_terminate(executor, futures, pending)
        raise
    else:
        if executor is not None:
            executor.shutdown(wait=True)
    execution_wall = time.perf_counter() - started
    ordered_results = [results[key] for key in sorted(results)]
    if len(ordered_results) != len(tasks):
        raise RuntimeError("not every requested shard returned exactly one result")
    ledger.sort(key=lambda entry: canonical_spec_key(entry["spec"]))
    return ordered_results, {
        "max_workers": max_workers, "start_method": "spawn",
        "configured_arm_max_workers": configured_arm_workers,
        "arm_max_workers": effective_arm_workers,
        "shard_execution_wall_clock_seconds": execution_wall,
        "shard_wall_clock_seconds_sum": sum((entry["shard_cost"] or {}).get("wall_clock_seconds", 0.0) for entry in ledger),
        "cache_hits": sum(entry["cache_hit"] for entry in ledger),
        "cache_misses": sum(not entry["cache_hit"] for entry in ledger), "shards": ledger,
    }


def _failure_metadata(task, seed, outer_fold, arm, grid_index, lr, wd, inner_fold, fit_seed):
    return {
        "seed": seed, "outer_fold": outer_fold, "arm": arm, "grid_index": grid_index,
        "learning_rate": lr, "weight_decay": wd, "inner_fold": inner_fold, "fit_seed": fit_seed,
        "protocol_sha256": task["identity"]["protocol"],
        "implementation_sha256": task["identity"]["implementation"],
        "mean_field_operator_sha256": task["identity"]["mean_field_operator"],
        "parallel_implementation_sha256": task["identity"]["parallel_implementation"],
        "solver_interface": "v9 native backward failure telemetry with captured batch reconstruction", "residual_tolerance": 1e-10,
    }


def _run_single_shard(task):
    protocol = kinetic.load_protocol(task["protocol_path"])
    device = kinetic.resolve_cuda_device(task["device"])
    records, _ = kinetic.parse_raw_matrix(task["raw_path"], protocol["inputs"]["sha256"])
    if len(records) != protocol["inputs"]["expected_eligible_transcripts"]:
        raise RuntimeError("worker eligible transcript count mismatch")
    splits = kinetic.make_nested_splits(records, protocol["split"]["seed"])
    spec = task["spec"]
    seed, outer_fold, arm, seed_index = spec["seed"], spec["outer_fold"], spec["arm"], spec["seed_index"]
    if seed != protocol["training"]["model_seeds"][seed_index] or arm not in kinetic.ARMS:
        raise RuntimeError("invalid shard specification")
    outer = splits[outer_fold]
    outer_test = [records[int(index)] for index in outer["test"]]
    rates = kinetic.learning_rate_grid(protocol["hyperparameters"]["learning_rate"])
    weight_decays = protocol["hyperparameters"]["weight_decays"]
    candidates, fit_costs, curves = [], [], []
    for grid_index, (learning_rate, weight_decay) in enumerate((lr, wd) for lr in rates for wd in weight_decays):
        candidate = {
            "grid_index": grid_index, "learning_rate": learning_rate, "weight_decay": weight_decay,
            "rung_selected": False, "rung_inner_oof_tb_mse": None, "rung_inner_oof_transcripts": 0,
            "inner_oof_tb_mse": None, "inner_oof_transcripts": 0, "folds": [],
        }
        rungs, rung_oof_mse = [], {}
        for inner in outer["inner"]:
            train_records = [records[int(index)] for index in inner["train"]]
            validation_records = [records[int(index)] for index in inner["validation"]]
            fit_seed = int(np.random.SeedSequence([seed, outer_fold, inner["inner_fold"]]).generate_state(1)[0])
            metadata = _failure_metadata(task, seed, outer_fold, arm, grid_index, learning_rate, weight_decay, inner["inner_fold"], fit_seed)
            rung = kinetic.start_candidate_rung(
                arm, train_records, validation_records, learning_rate, weight_decay,
                fit_seed, protocol, device, metadata, task["snapshot_dir"],
            )
            rungs.append({"rung": rung, "fit_seed": fit_seed})
            rung_oof_mse.update(rung["rung_validation_transcript_mse"])
        expected_oof = set(int(index) for outer_inner in outer["inner"] for index in outer_inner["validation"])
        if set(rung_oof_mse) != expected_oof or set(rung_oof_mse) & set(outer["test"].tolist()):
            raise RuntimeError("rung out-of-fold predictions are incomplete or touch outer test")
        candidate["rung_inner_oof_tb_mse"] = float(np.mean(list(rung_oof_mse.values())))
        candidate["rung_inner_oof_transcripts"] = len(rung_oof_mse)
        candidates.append({"report": candidate, "rungs": rungs, "states": []})
    retained = kinetic.successive_halving_indices(candidates)
    for candidate_index, candidate in enumerate(candidates):
        rung_selected = candidate_index in retained
        candidate["report"]["rung_selected"] = rung_selected
        oof_mse = {}
        for inner, rung_entry in zip(outer["inner"], candidate["rungs"]):
            inner_fold = inner["inner_fold"]
            train_records = [records[int(index)] for index in inner["train"]]
            validation_records = [records[int(index)] for index in inner["validation"]]
            rung, fit_seed = rung_entry["rung"], rung_entry["fit_seed"]
            learning_rate, weight_decay = candidate["report"]["learning_rate"], candidate["report"]["weight_decay"]
            metadata = _failure_metadata(task, seed, outer_fold, arm, candidate["report"]["grid_index"], learning_rate, weight_decay, inner_fold, fit_seed)
            if rung_selected:
                fitted = kinetic.resume_candidate(
                    rung, arm, train_records, validation_records, learning_rate, weight_decay,
                    fit_seed, protocol, device, metadata, task["snapshot_dir"],
                )
                candidate["states"].append({
                    "inner_fold": inner_fold, "fit_seed": fit_seed, "best_epoch": fitted["best_epoch"],
                    "best_validation_tb_mse": fitted["best_validation_tb_mse"], "state": fitted["best_state"],
                })
                oof_mse.update(fitted["validation_transcript_mse"])
            else:
                fitted = kinetic.reject_rung_candidate(rung)
            candidate["report"]["folds"].append({
                "inner_fold": inner_fold, "best_epoch": fitted["best_epoch"],
                "best_validation_tb_mse": fitted["best_validation_tb_mse"],
                "rung_last_validation_tb_mse": fitted["rung"]["last_validation_tb_mse"],
                "stop_reason": fitted["stop_reason"],
                "validation_plateau_converged": fitted["validation_plateau_converged"],
                "resumed_from_rung_last_state": rung_selected, "cost": fitted["cost"],
            })
            fit_costs.append(fitted["cost"])
            curves.append({
                "schema": kinetic.CURVE_SCHEMA, "seed": seed, "outer_fold": outer_fold,
                "inner_fold": inner_fold, "arm": arm, "grid_index": candidate["report"]["grid_index"],
                "learning_rate": learning_rate, "weight_decay": weight_decay,
                "rung_selected": rung_selected, "rung": fitted["rung"], "resume": fitted["resume"],
                "stop_reason": fitted["stop_reason"],
                "validation_plateau_converged": fitted["validation_plateau_converged"],
                "rung_rejection_is_not_convergence": True,
                "selected_candidates_have_no_final_epoch_cap": True, "epochs": fitted["curves"],
            })
        if rung_selected:
            if set(oof_mse) != expected_oof or set(oof_mse) & set(outer["test"].tolist()):
                raise RuntimeError("resumed out-of-fold predictions are incomplete or touch outer test")
            candidate["report"]["inner_oof_tb_mse"] = float(np.mean(list(oof_mse.values())))
            candidate["report"]["inner_oof_transcripts"] = len(oof_mse)
    selected_index = kinetic.final_selection_index(candidates, retained)
    selected = candidates[selected_index]
    selection = {
        "seed": seed, "outer_fold": outer_fold, "arm": arm, "selected_grid_index": selected_index,
        "rung_selected_grid_indices": retained, "rung_selection_metric": "rung_inner_oof_tb_mse",
        "selection_metric": "inner_oof_tb_mse_after_rung_resume", "outer_test_used_for_selection": False,
        "candidates": [candidate["report"] for candidate in candidates],
    }
    selected_state = {
        "seed": seed, "seed_index": seed_index, "outer_fold": outer_fold, "arm": arm,
        "arm_index": kinetic.ARMS.index(arm), "selected_grid_index": selected_index,
        "learning_rate": selected["report"]["learning_rate"],
        "weight_decay": selected["report"]["weight_decay"], "members": selected["states"],
    }
    member_predictions = []
    for state in selected["states"]:
        model = kinetic._new_model(device, state["fit_seed"], arm)
        model.load_state_dict({name: value.to(device) for name, value in state["state"].items()})
        kinetic._require_finite_parameters(model, "after restoring selected inner state")
        member_predictions.append(kinetic.predict_on_records(model, arm, outer_test, protocol, device))
    predictions = {}
    for record in outer_test:
        index = record.index
        members = [prediction[index] for prediction in member_predictions]
        predictions[index] = {
            "rho": np.mean([item["rho"] for item in members], axis=0),
            "flux": None if arm != "kinetic" else float(np.mean([item["flux"] for item in members])),
            "residual": None if arm != "kinetic" else np.mean([item["residual"] for item in members], axis=0),
            "max_abs_residual": None if arm != "kinetic" else max(item["max_abs_residual"] for item in members),
        }
    return {
        "spec": spec, "selection": selection, "selected_state": selected_state,
        "curves": curves, "predictions": predictions, "fit_costs": fit_costs,
    }


def _run_shard_task(task):
    started = time.perf_counter()
    try:
        observed = {
            "protocol": kinetic.sha256_file(task["protocol_path"]),
            "implementation": kinetic.sha256_file(kinetic.__file__),
            "mean_field_operator": kinetic.sha256_file(kinetic.kinetic_mean_field.__file__),
            "parallel_implementation": kinetic.sha256_file(__file__),
        }
        if observed != task["identity"]:
            raise RuntimeError("worker source identity differs from the parent startup identity")
        result = _run_single_shard(task)
        result["shard_cost"] = {"wall_clock_seconds": time.perf_counter() - started}
        result["worker"] = {"pid": os.getpid(), "device": task["device"]}
        return kinetic._cpu_tree(result)
    except Exception as error:
        snapshot_dir = Path(task["snapshot_dir"])
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = snapshot_dir / f"{shard_basename(task['spec'])}_worker_{time.time_ns()}_{os.getpid()}.json"
        kinetic.write_json_exclusive(path, {
            "schema": "a10-03-e2-kinetic-worker-failure-v1",
            "recorded_utc": datetime.now(timezone.utc).isoformat(), "spec": task["spec"],
            "error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc(),
            "candidate_snapshot": getattr(error, "codonflow_snapshot_path", None),
        })
        raise


def _as_array(value):
    if value is None:
        return np.asarray([], dtype=np.float64)
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().numpy()
    return np.asarray(value)


def reconstruct_backward_refinement(matrix, output_gradient, residual_tolerance=1e-10):
    trajectory = []
    try:
        matrix = torch.as_tensor(matrix, dtype=torch.float64)
        output_gradient = torch.as_tensor(output_gradient, dtype=torch.float64)
        transposed = matrix.transpose(-1, -2)
        row_scale = transposed.abs().amax(dim=-1, keepdim=True)
        if not bool(torch.isfinite(row_scale).all()) or not bool((row_scale > 0).all()):
            raise RuntimeError("invalid backward Jacobian row scales")
        factor, pivots = torch.linalg.lu_factor(transposed / row_scale)
        rhs = output_gradient.unsqueeze(-1) / row_scale
        multiplier = torch.linalg.lu_solve(factor, pivots, rhs).squeeze(-1)
        for refinement in range(3):
            recovery = torch.matmul(transposed, multiplier.unsqueeze(-1)).squeeze(-1) - output_gradient
            denominator = torch.matmul(transposed.abs(), multiplier.abs().unsqueeze(-1)).squeeze(-1) + output_gradient.abs()
            relative = torch.where(denominator > 0, recovery.abs() / denominator, recovery.abs())
            trajectory.append({
                "refinement": refinement, "multiplier": multiplier.detach().numpy(),
                "recovery": recovery.detach().numpy(), "relative_recovery": relative.detach().numpy(),
            })
            if not bool(torch.isfinite(multiplier).all()) or not bool(torch.isfinite(relative).all()):
                raise RuntimeError("nonfinite reconstructed backward solve")
            needs = relative > residual_tolerance
            if not bool(needs.any()):
                return trajectory, None
            if refinement == 2:
                break
            correction = torch.linalg.lu_solve(factor, pivots, recovery.unsqueeze(-1) / row_scale).squeeze(-1)
            multiplier = torch.where(needs, multiplier - correction, multiplier)
        return trajectory, f"recovery residual {float(relative.max()):.17g} exceeds {residual_tolerance:.17g}"
    except Exception as error:
        return trajectory, f"{type(error).__name__}: {error}"


def save_candidate_failure_snapshot(context, error):
    directory = Path(context["directory"])
    directory.mkdir(parents=True, exist_ok=True)
    capture, batch = context.get("capture", {}), context.get("batch", [])
    native_failures = getattr(error, "backward_failures", ())
    native_snapshot_fields = getattr(error, "backward_snapshot_fields", ())
    expected_native_fields = {
        "batch_index", "jacobian_transpose", "output_gradient", "multiplier",
        "recovery_extended", "denominator_extended", "relative_recovery_extended",
        "jacobian_condition_number", "refinement_steps", "qr_fallback", "qr_error",
    }
    if native_failures and set(native_snapshot_fields) != expected_native_fields:
        raise RuntimeError("unrecognized native backward failure snapshot fields")
    metadata = dict(context.get("metadata", {}))
    metadata.update({
        "schema": FAILURE_SCHEMA, "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "phase": context.get("phase"), "epoch": context.get("epoch"), "batch_index": context.get("batch_index"),
        "record_indices": [record.index for record in batch], "record_ids": [record.transcript_id for record in batch],
        "error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc(),
        "epoch_start_rng_state": context.get("epoch_start_rng_state"),
        "current_rng_state": copy.deepcopy(context["rng"].bit_generator.state) if context.get("rng") else None,
        "refinement_trace_source": (
            "native v9 backward_failures telemetry plus exact reconstruction from captured A and output_gradient"
            if native_failures else
            "exact reconstruction from captured A and output_gradient; native solver telemetry unavailable"
        ),
        "refinement_residual_tolerance": 1e-10,
        "native_backward_snapshot_fields": list(native_snapshot_fields),
    })
    arrays = {}
    native_metadata = []
    for failure_index, failure in enumerate(native_failures):
        if set(failure) != expected_native_fields:
            raise RuntimeError("incomplete native backward failure telemetry")
        prefix = f"native_backward/{failure_index}"
        for name in (
            "jacobian_transpose", "output_gradient", "multiplier", "recovery_extended",
            "denominator_extended", "relative_recovery_extended",
        ):
            arrays[f"{prefix}/{name}"] = _as_array(failure[name])
        batch_sample = failure["batch_index"]
        native_metadata.append({
            "failure_index": failure_index,
            "batch_sample": batch_sample,
            "record_index": batch[batch_sample].index if batch_sample is not None else None,
            "record_id": batch[batch_sample].transcript_id if batch_sample is not None else None,
            "jacobian_condition_number": failure["jacobian_condition_number"],
            "refinement_steps": failure["refinement_steps"],
            "qr_fallback": failure["qr_fallback"],
            "qr_error": failure["qr_error"],
            "array_prefix": prefix,
        })
    metadata["native_backward_failures"] = native_metadata
    for name in ("alpha", "k", "beta", "rho", "J", "flux", "residual", "rates", "score"):
        arrays[name] = _as_array(capture.get(name))
    lengths = np.asarray([record.length for record in batch], dtype=np.int64)
    arrays["batch/lengths"] = lengths
    if batch:
        max_length = max(record.length for record in batch)
        for name, fill, dtype in (("codons", 0, np.int64), ("target", np.nan, np.float64), ("mask", False, np.bool_)):
            value = np.full((len(batch), max_length), fill, dtype=dtype)
            for row, record in enumerate(batch):
                value[row, :record.length] = record.density if name == "target" else getattr(record, name)
            arrays[f"batch/{name}"] = value
    packed = capture.get("packed")
    if packed is not None:
        for name, value in packed.items():
            arrays[f"packed/{name}"] = _as_array(value)
    output_gradient, gradient_source = None, "unavailable"
    rho, flux = capture.get("rho"), capture.get("flux")
    if rho is not None and len(lengths):
        max_length = rho.shape[1]
        output_gradient = torch.zeros((len(lengths), max_length + 1), dtype=torch.float64)
        if "output_gradient_rho" in capture:
            output_gradient[:, :max_length] = capture["output_gradient_rho"].detach().cpu()
            gradient_source = "autograd_output_hook"
        elif "analytic_output_gradient" in capture:
            output_gradient[:, :max_length] = capture["analytic_output_gradient"].detach().cpu()
            gradient_source = "analytic_loss_gradient_fallback"
        if capture.get("output_gradient_J") is not None:
            output_gradient[np.arange(len(lengths)), lengths] = capture["output_gradient_J"].detach().cpu()
    arrays["output_gradient"] = _as_array(output_gradient)
    metadata["output_gradient_source"] = gradient_source
    alpha, k, beta = capture.get("alpha"), capture.get("k"), capture.get("beta")
    A = None
    if all(value is not None for value in (alpha, k, beta, rho, flux)) and len(lengths):
        alpha_np, k_np, beta_np, rho_np = map(_as_array, (alpha, k, beta, rho))
        max_length = rho_np.shape[1]
        A = np.zeros((len(lengths), max_length + 1, max_length + 1), dtype=np.float64)
        for index, length_value in enumerate(lengths):
            length = int(length_value)
            A[index, 0, 0] = -alpha_np[index]
            if length > 1:
                rows = np.arange(1, length)
                A[index, rows, rows - 1] = k_np[index, :length - 1] * (1.0 - rho_np[index, 1:length])
                A[index, rows, rows] = -k_np[index, :length - 1] * rho_np[index, :length - 1]
            A[index, length, length - 1] = beta_np[index]
            A[index, :length + 1, length] = -1.0
    arrays["A"], arrays["jacobian"] = _as_array(A), _as_array(A)
    refinement = []
    if A is not None and output_gradient is not None:
        for index, length_value in enumerate(lengths):
            length = int(length_value)
            trajectory, refinement_error = reconstruct_backward_refinement(
                A[index, :length + 1, :length + 1], output_gradient[index, :length + 1].numpy(),
            )
            for step in trajectory:
                for name, value in step.items():
                    if name != "refinement":
                        arrays[f"refinement/{index}/{step['refinement']}/{name}"] = value
            refinement.append({
                "batch_sample": index, "record_index": batch[index].index, "record_id": batch[index].transcript_id,
                "steps": [step["refinement"] for step in trajectory], "error": refinement_error,
            })
    metadata["refinement_trajectory"] = refinement
    state_arrays = {}
    metadata["states"] = {
        name: _pack_tree(context.get(name), state_arrays)
        for name in ("epoch_start_model_state", "epoch_start_optimizer_state")
    }
    if context.get("model") is not None:
        metadata["states"]["current_model_state"] = _pack_tree(context["model"].state_dict(), state_arrays)
    if context.get("optimizer") is not None:
        metadata["states"]["current_optimizer_state"] = _pack_tree(context["optimizer"].state_dict(), state_arrays)
    arrays.update({f"state/{key}": value for key, value in state_arrays.items()})
    arrays["metadata"] = np.asarray(json.dumps(metadata, ensure_ascii=False, allow_nan=False))
    spec_name = shard_basename({"seed_index": metadata.get("seed", 0), "outer_fold": metadata.get("outer_fold", 0), "arm": metadata.get("arm", "unknown")})
    path = directory / (
        f"{spec_name}_grid_{metadata.get('grid_index')}_inner_{metadata.get('inner_fold')}_"
        f"epoch_{metadata.get('epoch')}_batch_{metadata.get('batch_index')}_{time.time_ns()}_{os.getpid()}.npz"
    )
    with path.open("xb") as handle:
        np.savez_compressed(handle, **arrays)
    digest = kinetic.sha256_file(path)
    path.with_suffix(path.suffix + ".sha256").write_text(digest + "\n", encoding="ascii")
    return path


def run_experiment(protocol_path, raw_path, output_dir, device, max_workers, shard_cache_dir, arm_max_workers=None):
    started, started_utc = time.perf_counter(), datetime.now(timezone.utc).isoformat()
    protocol_path, raw_path = Path(protocol_path).expanduser().resolve(), Path(raw_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output_dir}")
    protocol = kinetic.load_protocol(protocol_path)
    if protocol["inputs"].get("expected_basename") and raw_path.name != protocol["inputs"]["expected_basename"]:
        raise ValueError("raw input basename mismatch")
    startup_sha256 = {
        "protocol": kinetic.sha256_file(protocol_path), "implementation": kinetic.sha256_file(kinetic.__file__),
        "mean_field_operator": kinetic.sha256_file(kinetic.kinetic_mean_field.__file__),
    }
    identity = {**startup_sha256, "parallel_implementation": kinetic.sha256_file(__file__)}
    output_dir.mkdir(parents=True, exist_ok=False)
    kinetic.write_json_exclusive(output_dir / "provenance.json", {
        "schema": kinetic.PROVENANCE_SCHEMA, "protocol": kinetic.PROTOCOL, "recorded_utc": started_utc,
        "stage": "startup_before_device_probe_raw_parse_or_training", "sha256": startup_sha256,
    })
    device = kinetic.resolve_cuda_device(device)
    kinetic._require_batch_solver()
    records, qc = kinetic.parse_raw_matrix(raw_path, protocol["inputs"]["sha256"])
    if len(records) != protocol["inputs"]["expected_eligible_transcripts"]:
        raise ValueError("eligible transcript count mismatch")
    splits = kinetic.make_nested_splits(records, protocol["split"]["seed"])
    kinetic.write_json_exclusive(output_dir / "splits.json", kinetic.split_payload(splits, records))
    cache_dir = Path(shard_cache_dir).expanduser().resolve() if shard_cache_dir else output_dir.with_name(output_dir.name + "_shard_cache")
    snapshot_dir = cache_dir / "failures"
    tasks = [
        {"spec": spec, "protocol_path": str(protocol_path), "raw_path": str(raw_path), "device": str(device),
         "identity": identity, "snapshot_dir": str(snapshot_dir)}
        for spec in kinetic_first(shard_specs(protocol))
    ]
    try:
        shard_results, parallel = execute_shard_tasks(
            tasks, cache_dir, identity, max_workers, _run_shard_task, arm_max_workers,
        )
    except Exception as error:
        kinetic.write_json_exclusive(output_dir / "failure.json", {
            "schema": "a10-03-e2-kinetic-parallel-failure-v1", "recorded_utc": datetime.now(timezone.utc).isoformat(),
            "status": "failed_no_completion_summary", "max_workers": max_workers, "start_method": "spawn",
            "wall_clock_seconds": time.perf_counter() - started, "error_type": type(error).__name__, "error": str(error),
            "shard_spec": getattr(error, "spec", None),
            "scheduler_cancellation": getattr(error, "scheduler_cancellation", {}),
            "snapshot_files": sorted(str(path) for path in snapshot_dir.glob("*") if path.is_file()),
            "scientific_gate_claimed": False,
        })
        raise
    seeds, max_length = protocol["training"]["model_seeds"], max(record.length for record in records)
    predictions = np.full((len(seeds), len(kinetic.ARMS), len(records), max_length), np.nan, dtype=np.float64)
    fluxes = np.full((len(seeds), len(kinetic.ARMS), len(records)), np.nan, dtype=np.float64)
    residuals = np.full((len(seeds), len(kinetic.ARMS), len(records), max_length + 1), np.nan, dtype=np.float64)
    solver_residuals = np.full((len(seeds), len(kinetic.ARMS), len(records)), np.nan, dtype=np.float64)
    target, mask = np.full((len(records), max_length), np.nan), np.zeros((len(records), max_length), dtype=np.bool_)
    codons, outer_assignment = np.full((len(records), max_length), -1, dtype=np.int64), np.full(len(records), -1, dtype=np.int64)
    for record in records:
        target[record.index, :record.length], mask[record.index, :record.length] = record.density, record.mask
        codons[record.index, :record.length] = record.codons
    for outer in splits:
        outer_assignment[outer["test"]] = outer["outer_fold"]
    selection_records, selected_state_records, fit_costs = [], [], []
    with (output_dir / "curves.jsonl").open("x", encoding="utf-8", newline="\n") as curve_handle:
        for result in sorted(shard_results, key=lambda item: canonical_spec_key(item["spec"])):
            selection_records.append(result["selection"])
            selected_state_records.append(result["selected_state"])
            fit_costs.extend(result["fit_costs"])
            for curve in result["curves"]:
                curve_handle.write(json.dumps(curve, allow_nan=False) + "\n")
            spec, seed_index = result["spec"], result["spec"]["seed_index"]
            arm_index = kinetic.ARMS.index(spec["arm"])
            for index, prediction in result["predictions"].items():
                record = records[index]
                predictions[seed_index, arm_index, index, :record.length] = prediction["rho"]
                if spec["arm"] == "kinetic":
                    fluxes[seed_index, arm_index, index] = prediction["flux"]
                    residuals[seed_index, arm_index, index, :record.length + 1] = prediction["residual"]
                    solver_residuals[seed_index, arm_index, index] = prediction["max_abs_residual"]
    state_path = output_dir / "selected_inner_states.npz"
    kinetic.save_selected_inner_states(state_path, selected_state_records, protocol["model"], startup_sha256)
    rows = kinetic.prediction_metrics(records, predictions, solver_residuals, seeds)
    for row in rows:
        row["outer_fold"] = int(outer_assignment[row["transcript_index"]])
    with (output_dir / "per_transcript_metrics.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=kinetic.METRIC_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    kinetic.write_json_exclusive(output_dir / "selection.json", {"schema": kinetic.SELECTION_SCHEMA, "protocol": kinetic.PROTOCOL, "records": selection_records})
    with (output_dir / "predictions.npz").open("xb") as handle:
        np.savez_compressed(
            handle, seeds=np.asarray(seeds, dtype=np.int64), arms=np.asarray(kinetic.ARMS),
            transcript_indices=np.arange(len(records), dtype=np.int64), transcript_ids=np.asarray([r.transcript_id for r in records]),
            lengths=np.asarray([r.length for r in records], dtype=np.int64), codons=codons, target=target, mask=mask,
            outer_fold=outer_assignment, prediction=predictions, flux=fluxes, ensemble_mean_residual_diagnostic=residuals,
            solver_max_abs_normalized_residual=solver_residuals, ensemble_mean_is_common_steady_state=np.asarray(False),
            kinetic_conservation_level=np.asarray("selected_inner_member_separately"),
        )
    candidate_serial_wall = sum(cost["wall_clock_seconds"] for cost in fit_costs)
    parallel.update({
        "schema": PARALLEL_SCHEMA, "protocol": kinetic.PROTOCOL, "schedule": "kinetic_first",
        "scheduled_specs": [task["spec"] for task in tasks], "canonical_merge": "seed_index,outer_fold,protocol_arm_order",
        "parallel_implementation_sha256": identity["parallel_implementation"],
        "candidate_fit_wall_clock_seconds_serial_sum": candidate_serial_wall,
        "wall_is_not_serial_sum": True, "scientific_gate_claimed": False,
    })
    kinetic.write_json_exclusive(output_dir / "parallel.json", parallel)
    all_fits = [fold for record in selection_records for candidate in record["candidates"] for fold in candidate["folds"]]
    artifact_names = ("provenance.json", "splits.json", "curves.jsonl", "selection.json", "selected_inner_states.npz", "predictions.npz", "per_transcript_metrics.csv", "parallel.json")
    summary = {
        "schema": kinetic.SUMMARY_SCHEMA, "protocol": kinetic.PROTOCOL, "status": "development_experiment_completed",
        "scope": protocol["scope"],
        "data": {"path": str(raw_path), "sha256": protocol["inputs"]["sha256"], "qc": qc, "normalization": protocol["preprocessing"], "untouched_read": False},
        "parameter_matching": {
            "per_inner_model": {arm: sum(p.numel() for p in kinetic._new_model(torch.device("cpu"), 1, arm).parameters()) for arm in kinetic.ARMS},
            "selected_inner_members_per_arm": 3,
            "per_selected_ensemble": {arm: 3 * sum(p.numel() for p in kinetic._new_model(torch.device("cpu"), 1, arm).parameters()) for arm in kinetic.ARMS},
        },
        "comparisons": {"primary": "independent_minus_kinetic_tb_mse", "simple_position_control": "position_minus_kinetic_tb_mse"},
        "ensemble": {"density_prediction": "equal-weight mean of selected inner member densities", "kinetic_conservation": "evaluated separately for every selected inner member", "mean_is_common_steady_state": False, "mean_residual_array_is_diagnostic_only": True},
        "selected_inner_states": {"path": "selected_inner_states.npz", "selections": len(selected_state_records), "members": sum(len(r["members"]) for r in selected_state_records), "reconstruction": "load_selected_inner_member or predict_from_saved_state"},
        "metrics": kinetic.summarize_metric_rows(rows, seeds),
        "convergence": {
            "fits": len(all_fits), "rung_fits": len(all_fits), "resumed_fits": sum(f["resumed_from_rung_last_state"] for f in all_fits),
            "validation_plateau": sum(f["stop_reason"] == "validation_plateau" for f in all_fits),
            "rejected_at_rung_not_converged": sum(f["stop_reason"] == "rejected_at_rung_not_converged" for f in all_fits),
            "rung_rejection_is_not_convergence": True, "selected_candidates_have_no_final_epoch_cap": True, "complete_curves_file": "curves.jsonl",
        },
        "cost": {
            "started_utc": started_utc, "finished_utc": datetime.now(timezone.utc).isoformat(), "wall_clock_seconds": time.perf_counter() - started,
            "candidate_fits": len(fit_costs), "epochs_ran": sum(c["epochs_ran"] for c in fit_costs), "candidate_fit_wall_clock_seconds": candidate_serial_wall,
            "rung_wall_clock_seconds": sum(c["rung_wall_clock_seconds"] for c in fit_costs),
            "continuation_wall_clock_seconds": sum(c["continuation_wall_clock_seconds"] for c in fit_costs),
            "cuda_peak_memory_bytes": max((c["cuda_peak_memory_bytes"] or 0 for c in fit_costs), default=0),
            "parallel": {key: parallel[key] for key in ("max_workers", "start_method", "configured_arm_max_workers", "arm_max_workers", "shard_execution_wall_clock_seconds", "shard_wall_clock_seconds_sum", "cache_hits", "cache_misses")},
        },
        "environment": kinetic._environment(device),
        "sha256": {**startup_sha256, "parallel_implementation": identity["parallel_implementation"], "raw_input": protocol["inputs"]["sha256"], "artifacts": {name: kinetic.sha256_file(output_dir / name) for name in artifact_names}},
        "limitations": protocol["limitations"],
    }
    kinetic.write_json_exclusive(output_dir / "summary.json", summary)
    print(json.dumps({"status": summary["status"], "output_dir": str(output_dir), "seeds": seeds, "max_workers": max_workers, "scientific_gate_claimed": False}))
    return summary
