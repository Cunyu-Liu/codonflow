import ast
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from scripts import a10_03_verify_e2_kinetic as verifier


ROOT = Path(__file__).resolve().parents[1]
FROZEN_PROTOCOL = ROOT / "configs" / "a10_03_e2_kinetic_protocol_v1.json"
SEEDS = (1234, 2345, 3456)
N_TRANSCRIPTS = 18


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_raw(path):
    rng = np.random.default_rng(90210)
    lines = []
    for index in range(N_TRANSCRIPTS):
        length = 12 + index % 4
        counts = 0.75 + rng.random(length) * 1.5
        safe_codons = [codon for codon in verifier.CODONS if codon not in verifier.STOP_CODONS]
        codons = ["ATG"] + [safe_codons[(index * 7 + position * 3) % len(safe_codons)] for position in range(1, length - 1)] + ["TAA"]
        lines.extend([
            f">synthetic_{index:03d} development_only",
            " ".join(codons),
            " ".join(f"{value:.12f}" for value in counts),
        ])
    lines.extend([
        ">too_short", "ATG GAA GAA TAA", "1 1 1 1",
        ">no_positive", "ATG GAA GAA GAA GAA GAA GAA GAA GAA GAA GAA TAA", " ".join(["0.1"] * 12),
        ">coverage_exactly_point_six", "ATG GAA GAA GAA GAA GAA GAA GAA GAA TAA",
        " ".join(["1.0"] * 6 + ["0.1"] * 4),
        ">threshold_is_strict", "ATG CAA GAA GAA GAA GAA GAA GAA GAA GAA GAA TAA",
        " ".join(["0.5"] * 12),
        ">missing_start", "GAA GCA GAA GAA GAA GAA GAA GAA GAA GAA GAA TAA", " ".join(["1"] * 12),
        ">missing_terminal_stop", "ATG GAA GAA GAA GAA GAA GAA GAA GAA GAA GAA GAA", " ".join(["1"] * 12),
        ">internal_stop", "ATG GAA TAA GAA GAA GAA GAA GAA GAA GAA GAA TAA", " ".join(["1"] * 12),
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_protocol(path, raw_path):
    protocol = json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))
    protocol["inputs"]["sha256"] = sha256(raw_path)
    protocol["inputs"]["expected_eligible_transcripts"] = N_TRANSCRIPTS
    protocol["inputs"]["expected_basename"] = raw_path.name
    protocol["training"]["early_stopping"]["patience_epochs"] = 2
    protocol["training"]["successive_halving"]["rung_epochs"] = 5
    protocol["outputs"]["v3_requires_new_directory_not_v1_or_v2_output"] = True
    write_json(path, protocol)
    return protocol


def epoch_values(candidate_index):
    if candidate_index == 0:
        return [0.50, 0.20, 0.21, 0.22], 2
    return [0.60, 0.40, 0.30, 0.31, 0.32], 3


def selected_state(seed, outer, inner, arm):
    seed_index = SEEDS.index(seed)
    if arm == "position":
        return {"relative_position.weight": np.asarray([[-3.0 - 0.1 * seed_index - 0.01 * inner]], dtype=np.float64)}
    if arm == "independent":
        embedding = np.log(0.04 / 0.96) + 0.01 * seed_index + 0.001 * inner
        weight = 0.001 * (seed_index + 1)
    else:
        embedding = 5.0 + 0.02 * seed_index + 0.001 * inner
        weight = -10.0 - 0.02 * seed_index
    return {
        "codon.weight": np.full((64, 1), embedding, dtype=np.float64),
        "relative_position.weight": np.asarray([[weight]], dtype=np.float64),
    }


def make_training(output, protocol, splits):
    grid = verifier.curve_grid(protocol)
    rung_epochs = protocol["training"]["successive_halving"]["rung_epochs"]
    selection_records = []
    curve_lines = []
    for seed in SEEDS:
        for outer in splits:
            outer_index = outer["outer_fold"]
            for arm in verifier.ARMS:
                candidates = []
                for grid_index, (learning_rate, weight_decay) in enumerate(grid):
                    promoted = grid_index < 2
                    folds = []
                    weighted_rung_score = 0.0
                    weighted_final_score = 0.0
                    validation_count = 0
                    for inner in outer["inner"]:
                        inner_index = inner["inner_fold"]
                        rung_values = [1.0 + 0.05 * grid_index - 0.05 * epoch for epoch in range(rung_epochs)]
                        if grid_index == 0:
                            continuation_values = [0.20, 0.21, 0.22]
                        elif grid_index == 1:
                            continuation_values = [0.40, 0.30, 0.31, 0.32]
                        else:
                            continuation_values = []
                        all_values = rung_values + continuation_values
                        rung_history = [
                            {
                                "epoch": index + 1, "train_tb_mse": 0.8 - 0.001 * index,
                                "validation_tb_mse": value, "elapsed_seconds": 0.1 * (index + 1),
                            }
                            for index, value in enumerate(rung_values)
                        ]
                        continuation_history = [
                            {
                                "epoch": rung_epochs + index + 1, "train_tb_mse": 0.7 - 0.001 * index,
                                "validation_tb_mse": value,
                                "elapsed_seconds": 0.1 * (rung_epochs + index + 1),
                            }
                            for index, value in enumerate(continuation_values)
                        ]
                        stop_reason = "validation_plateau" if promoted else "rejected_at_rung_not_converged"
                        state_sha = hashlib.sha256(f"state/{seed}/{outer_index}/{inner_index}/{arm}/{grid_index}".encode()).hexdigest()
                        optimizer_sha = hashlib.sha256(f"optimizer/{seed}/{outer_index}/{inner_index}/{arm}/{grid_index}".encode()).hexdigest()
                        resume = {
                            "source": "rung_last_state", "source_epoch": rung_epochs,
                            "start_epoch": rung_epochs + 1,
                            "rung_last_state_sha256": state_sha,
                            "restored_model_state_sha256": state_sha,
                            "rung_last_optimizer_state_sha256": optimizer_sha,
                            "optimizer_state_restored": True, "rng_state_restored": True,
                        } if promoted else None
                        curve = {
                            "schema": verifier.CURVE_SCHEMA,
                            "seed": seed, "outer_fold": outer_index, "inner_fold": inner_index,
                            "arm": arm, "grid_index": grid_index,
                            "learning_rate": learning_rate, "weight_decay": weight_decay,
                            "rung_selected": promoted,
                            "rung": {
                                "epochs": rung_epochs, "last_epoch": rung_epochs,
                                "last_validation_tb_mse": rung_values[-1],
                                "last_state_sha256": state_sha, "last_optimizer_state_sha256": optimizer_sha,
                            },
                            "resume": resume,
                            "stop_reason": stop_reason,
                            "validation_plateau_converged": promoted,
                            "rung_rejection_is_not_convergence": True,
                            "selected_candidates_have_no_final_epoch_cap": True,
                            "epochs": rung_history + continuation_history,
                        }
                        curve_lines.append(json.dumps(curve, allow_nan=False))
                        epochs = rung_history + continuation_history
                        cost = {
                            "wall_clock_seconds": epochs[-1]["elapsed_seconds"] + 0.01,
                            "epochs_ran": len(epochs),
                            "train_transcripts": len(inner["train"]),
                            "validation_transcripts": len(inner["validation"]),
                            "cuda_peak_memory_bytes": 1024,
                        }
                        best_epoch = int(np.argmin(all_values)) + 1
                        best_loss = min(all_values)
                        folds.append({
                            "inner_fold": inner_index,
                            "rung_last_validation_tb_mse": rung_values[-1],
                            "resumed_from_rung_last_state": promoted,
                            "best_epoch": best_epoch,
                            "best_validation_tb_mse": best_loss,
                            "stop_reason": stop_reason,
                            "validation_plateau_converged": promoted,
                            "cost": cost,
                        })
                        weighted_rung_score += rung_values[-1] * len(inner["validation"])
                        if promoted:
                            weighted_final_score += best_loss * len(inner["validation"])
                        validation_count += len(inner["validation"])
                    candidates.append({
                        "grid_index": grid_index,
                        "learning_rate": learning_rate,
                        "weight_decay": weight_decay,
                        "folds": folds,
                        "rung_selected": promoted,
                        "rung_inner_oof_tb_mse": weighted_rung_score / validation_count,
                        "rung_inner_oof_transcripts": validation_count,
                        "inner_oof_tb_mse": weighted_final_score / validation_count if promoted else None,
                        "inner_oof_transcripts": validation_count if promoted else 0,
                    })
                selection_records.append({
                    "seed": seed, "outer_fold": outer_index, "arm": arm,
                    "selected_grid_index": 0, "rung_selected_grid_indices": [0, 1],
                    "rung_selection_metric": "rung_inner_oof_tb_mse",
                    "selection_metric": "inner_oof_tb_mse_after_rung_resume",
                    "outer_test_used_for_selection": False,
                    "candidates": candidates,
                })
    (output / "curves.jsonl").write_text("\n".join(curve_lines) + "\n", encoding="utf-8")
    write_json(output / "selection.json", {
        "schema": verifier.SELECTION_SCHEMA,
        "protocol": verifier.PROTOCOL,
        "records": selection_records,
    })


def source_sha256(protocol_path, include_banded=False):
    identity = {
        "protocol": sha256(protocol_path),
        "implementation": sha256(verifier.IMPLEMENTATION_PATH),
        "mean_field_operator": sha256(verifier.MEAN_FIELD_OPERATOR_PATH),
    }
    if include_banded:
        identity["banded_cuda_backend"] = sha256(verifier.BANDED_CUDA_BACKEND_PATH)
    return identity


def make_state_archive(output, protocol, protocol_path, include_banded=False):
    selection = json.loads((output / "selection.json").read_text(encoding="utf-8"))
    arrays = {}
    records = []
    for record in selection["records"]:
        seed, outer, arm = record["seed"], record["outer_fold"], record["arm"]
        seed_index, arm_index = SEEDS.index(seed), verifier.ARMS.index(arm)
        selected_index = record["selected_grid_index"]
        selected = record["candidates"][selected_index]
        metadata = {
            "seed": seed, "seed_index": seed_index, "outer_fold": outer,
            "arm": arm, "arm_index": arm_index, "selected_grid_index": selected_index,
            "learning_rate": selected["learning_rate"], "weight_decay": selected["weight_decay"],
            "members": [],
        }
        for inner in range(3):
            state = selected_state(seed, outer, inner, arm)
            fold = selected["folds"][inner]
            state_keys = {}
            for name, value in state.items():
                key = f"state/{seed_index}/{outer}/{arm_index}/{inner}/{name}"
                arrays[key] = value
                state_keys[name] = key
            metadata["members"].append({
                "inner_fold": inner,
                "fit_seed": int(np.random.SeedSequence([seed, outer, inner]).generate_state(1)[0]),
                "best_epoch": fold["best_epoch"],
                "best_validation_tb_mse": fold["best_validation_tb_mse"],
                "state_keys": state_keys,
            })
        records.append(metadata)
    payload = {
        "schema": verifier.STATE_SCHEMA, "protocol": verifier.PROTOCOL, "dtype": "float64",
        "model_config": protocol["model"], "startup_sha256": source_sha256(protocol_path, include_banded),
        "records": records,
    }
    arrays["metadata"] = np.asarray(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    with (output / "selected_inner_states.npz").open("wb") as handle:
        np.savez_compressed(handle, **arrays)


def make_predictions(output, records, protocol, splits, selected_states):
    n_records = len(records)
    max_length = max(record["length"] for record in records)
    target = np.full((n_records, max_length), np.nan)
    codons = np.full((n_records, max_length), -1, dtype=np.int64)
    mask = np.zeros((n_records, max_length), dtype=np.bool_)
    outer_assignment = np.empty(n_records, dtype=np.int64)
    for outer in splits:
        outer_assignment[outer["test"]] = outer["outer_fold"]
    prediction = np.full((len(SEEDS), len(verifier.ARMS), n_records, max_length), np.nan)
    flux = np.full((len(SEEDS), len(verifier.ARMS), n_records), np.nan)
    mean_residual = np.full((len(SEEDS), len(verifier.ARMS), n_records, max_length + 1), np.nan)
    solver_residual = np.full((len(SEEDS), len(verifier.ARMS), n_records), np.nan)
    for record in records:
        index, length = record["index"], record["length"]
        target[index, :length] = record["density"]
        codons[index, :length] = record["codons"]
        mask[index, :length] = record["mask"]
        outer = int(outer_assignment[index])
        for seed_index, seed in enumerate(SEEDS):
            for arm_index, arm in enumerate(verifier.ARMS):
                members = [
                    verifier.rebuild_selected_member(record, state, arm, protocol["model"])
                    for state in selected_states[(seed, outer, arm)]
                ]
                prediction[seed_index, arm_index, index, :length] = np.mean(
                    [member["rho"] for member in members], axis=0,
                )
                if arm == "kinetic":
                    flux[seed_index, arm_index, index] = np.mean([member["flux"] for member in members])
                    residuals = [member["residual"] for member in members]
                    mean_residual[seed_index, arm_index, index, :length + 1] = np.mean(residuals, axis=0)
                    solver_residual[seed_index, arm_index, index] = max(np.max(np.abs(value)) for value in residuals)
    arrays = {
        "seeds": np.asarray(SEEDS, dtype=np.int64),
        "arms": np.asarray(verifier.ARMS),
        "transcript_indices": np.arange(n_records, dtype=np.int64),
        "transcript_ids": np.asarray([record["transcript_id"] for record in records]),
        "lengths": np.asarray([record["length"] for record in records]),
        "codons": codons,
        "target": target,
        "mask": mask,
        "outer_fold": outer_assignment,
        "prediction": prediction,
        "flux": flux,
        "ensemble_mean_residual_diagnostic": mean_residual,
        "solver_max_abs_normalized_residual": solver_residual,
        "ensemble_mean_is_common_steady_state": np.asarray(False),
        "kinetic_conservation_level": np.asarray("selected_inner_member_separately"),
    }
    with (output / "predictions.npz").open("wb") as handle:
        np.savez(handle, **arrays)
    return arrays


def write_metric_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=verifier.CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else value for key, value in row.items()})


def make_case(tmp_path, include_banded=False):
    tmp_path = tmp_path.resolve()
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw_path = tmp_path / "synthetic_mohammad.txt"
    write_raw(raw_path)
    protocol_path = tmp_path / "protocol.json"
    protocol = make_protocol(protocol_path, raw_path)
    records, qc = verifier.parse_raw(raw_path)
    splits = verifier.make_nested_splits(records, protocol["split"]["seed"])
    output = tmp_path / "production"
    output.mkdir()
    write_json(output / "splits.json", verifier.split_payload(splits, records))
    write_json(output / "provenance.json", {
        "schema": verifier.PROVENANCE_SCHEMA, "protocol": verifier.PROTOCOL,
        "recorded_utc": "2026-01-01T00:00:00+00:00",
        "stage": "startup_before_device_probe_raw_parse_or_training",
        "sha256": source_sha256(protocol_path, include_banded),
    })
    make_training(output, protocol, splits)
    make_state_archive(output, protocol, protocol_path, include_banded)
    training = verifier.audit_training(output, protocol, splits)
    selected_states = verifier.load_selected_states(
        output / "selected_inner_states.npz", protocol, source_sha256(protocol_path, include_banded),
    )
    arrays = make_predictions(output, records, protocol, splits, selected_states)
    evaluation = verifier.evaluate_predictions(arrays, records, protocol, splits, selected_states)
    write_metric_csv(output / "per_transcript_metrics.csv", evaluation["rows"])
    metrics = verifier.summarize_metric_rows(evaluation["rows"], SEEDS)
    summary = {
        "schema": verifier.SUMMARY_SCHEMA,
        "protocol": verifier.PROTOCOL,
        "status": "development_experiment_completed",
        "scope": protocol["scope"],
        "data": {
            "path": str(raw_path),
            "sha256": sha256(raw_path),
            "qc": qc,
            "normalization": protocol["preprocessing"],
            "untouched_read": False,
        },
        "parameter_matching": {
            "per_inner_model": {"independent": 65, "position": 1, "kinetic": 65},
            "selected_inner_members_per_arm": 3,
            "per_selected_ensemble": {"independent": 195, "position": 3, "kinetic": 195},
        },
        "comparisons": {
            "primary": "independent_minus_kinetic_tb_mse",
            "simple_position_control": "position_minus_kinetic_tb_mse",
        },
        "ensemble": {
            "density_prediction": "equal-weight mean of selected inner member densities",
            "kinetic_conservation": "evaluated separately for every selected inner member",
            "mean_is_common_steady_state": False,
            "mean_residual_array_is_diagnostic_only": True,
        },
        "selected_inner_states": {
            "path": "selected_inner_states.npz", "selections": 27, "members": 81,
            "reconstruction": "load_selected_inner_member or predict_from_saved_state",
        },
        "metrics": metrics,
        "convergence": training["convergence"],
        "cost": {
            "started_utc": "2026-01-01T00:00:00+00:00",
            "finished_utc": "2026-01-01T00:01:00+00:00",
            "wall_clock_seconds": training["fit_wall_clock_seconds"] + 1.0,
            "candidate_fits": training["fit_count"],
            "epochs_ran": training["epochs_ran"],
            "candidate_fit_wall_clock_seconds": training["fit_wall_clock_seconds"],
            "cuda_peak_memory_bytes": training["cuda_peak_memory_bytes"],
        },
        "environment": {
            "cuda": {
                "requested_device": "cuda:0",
                "available": True,
                "torch_cuda_version": "synthetic",
                "name": "Synthetic CUDA record",
                "capability": [9, 0],
            },
        },
        "sha256": {
            **source_sha256(protocol_path, include_banded),
            "raw_input": sha256(raw_path),
            "artifacts": {name: sha256(output / name) for name in verifier.ARTIFACT_FILES},
        },
        "limitations": protocol["limitations"],
    }
    write_json(output / "summary.json", summary)
    return {
        "raw": raw_path, "protocol": protocol_path, "protocol_payload": protocol,
        "output": output, "splits": splits,
    }


def verify(case):
    return verifier.verify_e2_kinetic(
        case["protocol"], case["raw"], case["output"], allow_synthetic=True, n_resamples=512,
    )


def load_summary(case):
    return json.loads((case["output"] / "summary.json").read_text(encoding="utf-8"))


def save_summary(case, summary):
    write_json(case["output"] / "summary.json", summary)


def refresh_artifact_sha(case, name):
    summary = load_summary(case)
    summary["sha256"]["artifacts"][name] = sha256(case["output"] / name)
    save_summary(case, summary)


def load_selection(case):
    return json.loads((case["output"] / "selection.json").read_text(encoding="utf-8"))


def save_selection(case, selection):
    write_json(case["output"] / "selection.json", selection)
    refresh_artifact_sha(case, "selection.json")


def read_predictions(case):
    with np.load(case["output"] / "predictions.npz", allow_pickle=False) as archive:
        return {name: archive[name].copy() for name in archive.files}


def save_predictions(case, arrays):
    with (case["output"] / "predictions.npz").open("wb") as handle:
        np.savez(handle, **arrays)
    refresh_artifact_sha(case, "predictions.npz")


def test_frozen_identity_and_verifier_has_no_production_imports(tmp_path):
    assert json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))["protocol"].endswith("_v3")
    frozen = verifier.load_protocol(FROZEN_PROTOCOL)
    assert frozen["inputs"]["expected_eligible_transcripts"] == 1073
    assert frozen["training"]["successive_halving"]["rung_epochs"] == 50
    assert frozen["training"]["successive_halving"]["retained_candidates_per_arm"] == 2
    assert frozen["training"]["final_epoch_limit"] is None
    assert verifier.REAL_ELIGIBLE == 1073
    raw_path = tmp_path / "synthetic.txt"
    write_raw(raw_path)
    make_protocol(tmp_path / "protocol.json", raw_path)
    protocol = verifier.load_protocol(tmp_path / "protocol.json", allow_synthetic=True)
    assert protocol["inputs"]["expected_eligible_transcripts"] == N_TRANSCRIPTS
    assert protocol["model"]["trainable_parameters_per_model"] == {"independent": 65, "position": 1, "kinetic": 65}
    tree = ast.parse(Path(verifier.__file__).read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(name == "codonflow" or name.startswith(("codonflow.", "scripts.")) for name in imported)
    assert verifier.REAL_RAW_SHA256 == "d093a3b0c53aa90d0626cc277a65a558c538ecbeb4d1cda091f02aad134588bc"
    assert verifier.REAL_OUTER_TEST_KINETIC_MEMBERS == 3 * 1073 * 3 == 9657


def test_pre_outer_analysis_addendum_matches_verifier_inference_contract():
    addendum = json.loads(
        (ROOT / "configs" / "a10_03_e2_analysis_addendum_v1.json").read_text(encoding="utf-8")
    )
    inference = addendum["inference"]
    assert addendum["status"] == "specified_before_outer_results"
    assert addendum["outer_results_available"] is False
    assert addendum["scientific_gate_change"] is False
    assert inference["seed"] == verifier.INFERENCE_SEED == 9100302
    assert inference["bootstrap_resamples"] == inference["signflip_resamples"] == verifier.REAL_RESAMPLES == 20000
    assert inference["comparators"] == list(verifier.COMPARATORS)
    assert "two comparators" in inference["holm_family"]
    assert "within each transcript" in inference["pooled_seed_first"]
    assert "every model seed" in inference["per_seed_condition"]
    assert "both comparators" in inference["joint_development_condition"]


def test_synthetic_full_independent_verification_passes(tmp_path):
    case = make_case(tmp_path)
    result = verify(case)
    assert result["passed"], result["mismatches"]
    assert all(result["checks"].values())
    assert result["recomputed"]["qc"]["input_records"] == N_TRANSCRIPTS + 7
    assert result["recomputed"]["qc"]["eligible_transcripts"] == N_TRANSCRIPTS
    assert result["recomputed"]["training"]["fit_count"] == 486
    convergence = result["recomputed"]["training"]["convergence"]
    assert convergence["rung_fits"] == 486
    assert convergence["resumed_fits"] == 162
    assert convergence["validation_plateau"] == 162
    assert convergence["rejected_at_rung_not_converged"] == 324
    assert convergence["rung_rejection_is_not_convergence"] is True
    assert convergence["selected_candidates_have_no_final_epoch_cap"] is True
    assert result["recomputed"]["member_conservation"]["kinetic_members_checked"] == 3 * N_TRANSCRIPTS * 3
    assert result["recomputed"]["member_conservation"]["maximum_member_abs_normalized_residual"] <= 1e-10
    assert result["recomputed"]["member_conservation"]["ensemble_mean_is_common_steady_state"] is False
    with (case["output"] / "per_transcript_metrics.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(row["seed"], row["arm"], row["transcript_index"]) for row in rows[:3]] == [
        ("1234", "independent", "0"), ("1234", "independent", "1"), ("1234", "independent", "2"),
    ]
    assert (rows[N_TRANSCRIPTS]["seed"], rows[N_TRANSCRIPTS]["arm"], rows[N_TRANSCRIPTS]["transcript_index"]) == ("1234", "position", "0")
    assert (rows[2 * N_TRANSCRIPTS]["seed"], rows[2 * N_TRANSCRIPTS]["arm"], rows[2 * N_TRANSCRIPTS]["transcript_index"]) == ("1234", "kinetic", "0")
    assert result["recomputed"]["inference"]["h2_development_positive"] is True
    for comparator in verifier.COMPARATORS:
        assert result["recomputed"]["inference"]["across_seeds"][comparator]["all_seed_effects_positive"] is True
    for seed_result in result["recomputed"]["inference"]["per_seed"].values():
        for inference in seed_result["comparisons"].values():
            assert inference["bootstrap_95ci"][0] > 0
            assert inference["holm_p"] < 0.05


def test_raw_qc_threshold_density_mask_and_grouped_folds_are_independent(tmp_path):
    raw_path = tmp_path / "raw.txt"
    write_raw(raw_path)
    records, qc = verifier.parse_raw(raw_path)
    assert qc["rejected_too_short"] == 1
    assert qc["rejected_coverage"] == 3
    assert qc["rejected_missing_start_atg"] == 1
    assert qc["rejected_missing_terminal_stop"] == 1
    assert qc["rejected_internal_stop"] == 1
    first = records[0]
    expected = first["counts"] / np.mean(first["counts"][first["counts"] > 0.5])
    np.testing.assert_allclose(first["density"], expected)
    assert not np.any(first["mask"][:5])
    assert not np.any(first["mask"][-4:])
    assert np.all(first["mask"][5:-4])
    protocol = make_protocol(tmp_path / "protocol.json", raw_path)
    splits = verifier.make_nested_splits(records, protocol["split"]["seed"])
    assert sorted(np.concatenate([outer["test"] for outer in splits]).tolist()) == list(range(N_TRANSCRIPTS))
    for outer in splits:
        test = set(outer["test"].tolist())
        for inner in outer["inner"]:
            assert not set(inner["train"].tolist()) & test
            assert not set(inner["validation"].tolist()) & test
            assert not set(inner["train"].tolist()) & set(inner["validation"].tolist())


def test_correlations_use_average_ties_and_leave_undefined_values_null():
    x = np.asarray([1.0, 1.0, 2.0, 3.0])
    assert np.array_equal(verifier.average_ranks(x), np.asarray([1.5, 1.5, 3.0, 4.0]))
    assert verifier.correlation(x, np.asarray([1.0, 2.0, 3.0, 4.0])) is not None
    assert verifier.correlation(np.ones(4), np.arange(4)) is None
    assert verifier.correlation(np.asarray([1.0, 2.0, 3.0]), np.asarray([1.0, 2.0, 4.0])) == pytest.approx(0.9819805060619659)


def test_split_artifact_and_outer_test_selection_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    splits = json.loads((case["output"] / "splits.json").read_text(encoding="utf-8"))
    splits["outer_folds"][0]["inner_folds"][0]["validation_indices"][0] = splits["outer_folds"][0]["test_indices"][0]
    write_json(case["output"] / "splits.json", splits)
    refresh_artifact_sha(case, "splits.json")
    result = verify(case)
    assert not result["checks"]["raw_rebuilt_transcript_nested_splits"]
    assert result["checks"]["summary_artifact_sha256"]

    case = make_case(tmp_path / "selection")
    selection = load_selection(case)
    selection["records"][0]["outer_test_used_for_selection"] = True
    save_selection(case, selection)
    assert not verify(case)["checks"]["complete_inner_curves_plateau_and_inner_only_selection"]


def test_plateau_curve_tampering_is_detected(tmp_path):
    case = make_case(tmp_path)
    lines = (case["output"] / "curves.jsonl").read_text(encoding="utf-8").splitlines()
    curve = json.loads(lines[0])
    curve["stop_reason"] = "maximum_epochs_reached"
    curve["validation_plateau_converged"] = False
    lines[0] = json.dumps(curve)
    (case["output"] / "curves.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    refresh_artifact_sha(case, "curves.jsonl")
    result = verify(case)
    assert not result["checks"]["complete_inner_curves_plateau_and_inner_only_selection"]
    assert result["checks"]["summary_artifact_sha256"]


def test_rung_top2_elimination_and_continuation_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    lines = (case["output"] / "curves.jsonl").read_text(encoding="utf-8").splitlines()
    eliminated_index = next(index for index, line in enumerate(lines) if json.loads(line)["grid_index"] == 2)
    curve = json.loads(lines[eliminated_index])
    curve["stop_reason"] = "validation_plateau"
    curve["validation_plateau_converged"] = True
    lines[eliminated_index] = json.dumps(curve)
    (case["output"] / "curves.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    refresh_artifact_sha(case, "curves.jsonl")
    result = verify(case)
    assert not result["checks"]["complete_inner_curves_plateau_and_inner_only_selection"]
    assert "rejected rung candidates cannot be converged" in result["mismatches"]["training"][0]

    case = make_case(tmp_path / "top2")
    selection = load_selection(case)
    selection["records"][0]["rung_selected_grid_indices"] = [0, 2]
    save_selection(case, selection)
    result = verify(case)
    assert not result["checks"]["complete_inner_curves_plateau_and_inner_only_selection"]
    assert "top2 promotion" in result["mismatches"]["training"][0]

    case = make_case(tmp_path / "eliminated_final_score")
    selection = load_selection(case)
    selection["records"][0]["candidates"][2]["inner_oof_tb_mse"] = 0.5
    save_selection(case, selection)
    result = verify(case)
    assert not result["checks"]["complete_inner_curves_plateau_and_inner_only_selection"]
    assert "eliminated candidate must not have a final converged OOF score" in result["mismatches"]["training"][0]

    case = make_case(tmp_path / "rung_length")
    lines = (case["output"] / "curves.jsonl").read_text(encoding="utf-8").splitlines()
    curve = json.loads(lines[0])
    curve["epochs"].pop(4)
    lines[0] = json.dumps(curve)
    (case["output"] / "curves.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    refresh_artifact_sha(case, "curves.jsonl")
    assert not verify(case)["checks"]["complete_inner_curves_plateau_and_inner_only_selection"]

    case = make_case(tmp_path / "continuation_restart")
    lines = (case["output"] / "curves.jsonl").read_text(encoding="utf-8").splitlines()
    curve = json.loads(lines[0])
    curve["epochs"][5]["epoch"] = 1
    lines[0] = json.dumps(curve)
    (case["output"] / "curves.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    refresh_artifact_sha(case, "curves.jsonl")
    result = verify(case)
    assert not result["checks"]["complete_inner_curves_plateau_and_inner_only_selection"]
    assert "contiguous" in result["mismatches"]["training"][0]

    case = make_case(tmp_path / "not_from_rung_last")
    lines = (case["output"] / "curves.jsonl").read_text(encoding="utf-8").splitlines()
    curve = json.loads(lines[0])
    curve["resume"]["restored_model_state_sha256"] = "0" * 64
    lines[0] = json.dumps(curve)
    (case["output"] / "curves.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    refresh_artifact_sha(case, "curves.jsonl")
    assert not verify(case)["checks"]["complete_inner_curves_plateau_and_inner_only_selection"]


def test_eliminated_oof_transcript_semantics_and_grid_order_final_tie_break(tmp_path):
    case = make_case(tmp_path)
    selection = load_selection(case)
    eliminated = selection["records"][0]["candidates"][2]
    assert eliminated["inner_oof_tb_mse"] is None
    assert eliminated["inner_oof_transcripts"] == 0
    eliminated["inner_oof_transcripts"] = N_TRANSCRIPTS - 3
    save_selection(case, selection)
    result = verify(case)
    assert not result["checks"]["complete_inner_curves_plateau_and_inner_only_selection"]
    assert "zero final OOF transcripts" in result["mismatches"]["training"][0]
    assert verifier.grid_order_minimum({1: 0.25, 0: 0.25, 2: 0.50}) == 0


def test_member_residual_threshold_accepts_boundary_and_rejects_next_float(monkeypatch):
    solved = type("Solved", (), {"success": True, "message": "synthetic"})()
    state = np.asarray([0.5, 1.0])

    def residual_at(value):
        return lambda *args: np.asarray([value, value])

    monkeypatch.setattr(verifier, "steady_state_residual", residual_at(verifier.MEMBER_RESIDUAL_TOLERANCE))
    accepted = verifier.checked_physical_state(solved, state, 2.0, np.asarray([]), 2.0)
    assert np.max(np.abs(accepted["residual"])) == verifier.MEMBER_RESIDUAL_TOLERANCE
    monkeypatch.setattr(
        verifier, "steady_state_residual",
        residual_at(np.nextafter(verifier.MEMBER_RESIDUAL_TOLERANCE, 1.0)),
    )
    with pytest.raises(RuntimeError, match="flux conservation tolerance"):
        verifier.checked_physical_state(solved, state, 2.0, np.asarray([]), 2.0)


def test_legacy_cumulative_cost_is_decomposed_without_double_counting(tmp_path):
    case = make_case(tmp_path)
    result = verify(case)
    assert result["passed"], result["mismatches"]
    training = result["recomputed"]["training"]
    assert training["legacy_cumulative_cost_fits"] == training["fit_count"]
    assert training["fit_wall_clock_seconds"] == pytest.approx(
        training["rung_wall_clock_seconds"] + training["continuation_wall_clock_seconds"]
    )
    summary = load_summary(case)
    summary["cost"]["candidate_fit_wall_clock_seconds"] += training["rung_wall_clock_seconds"]
    save_summary(case, summary)
    assert not verify(case)["checks"]["complete_cost_ledger"]


def test_promoted_plateau_has_no_final_epoch_ceiling(tmp_path):
    raw_path = tmp_path / "synthetic.txt"
    write_raw(raw_path)
    protocol = make_protocol(tmp_path / "protocol.json", raw_path)
    protocol["training"]["successive_halving"]["rung_epochs"] = 50
    protocol["training"]["early_stopping"]["patience_epochs"] = 25
    total_epochs = 2005

    def validation_value(epoch):
        return 2.0 - min(epoch // 20, 99) * 0.001

    history = [
        {
            "epoch": epoch, "train_tb_mse": 1.0,
            "validation_tb_mse": validation_value(epoch), "elapsed_seconds": epoch * 0.01,
        }
        for epoch in range(1, total_epochs + 1)
    ]
    learning_rate, weight_decay = verifier.curve_grid(protocol)[0]
    curve = {
        "schema": verifier.CURVE_SCHEMA, "seed": 1234, "outer_fold": 0, "inner_fold": 0,
        "arm": "independent", "grid_index": 0,
        "learning_rate": learning_rate, "weight_decay": weight_decay,
        "rung_selected": True,
        "rung": {
            "epochs": 50, "last_epoch": 50, "last_validation_tb_mse": history[49]["validation_tb_mse"],
            "last_state_sha256": "1" * 64, "last_optimizer_state_sha256": "2" * 64,
        },
        "resume": {
            "source": "rung_last_state", "source_epoch": 50, "start_epoch": 51,
            "rung_last_state_sha256": "1" * 64, "restored_model_state_sha256": "1" * 64,
            "rung_last_optimizer_state_sha256": "2" * 64,
            "optimizer_state_restored": True, "rng_state_restored": True,
        },
        "stop_reason": "validation_plateau", "validation_plateau_converged": True,
        "rung_rejection_is_not_convergence": True,
        "selected_candidates_have_no_final_epoch_cap": True,
        "epochs": history,
    }
    audit = verifier.validate_curve(curve, (1234, 0, 0, "independent", 0), verifier.curve_grid(protocol), protocol)
    assert audit["epochs_ran"] == 2005
    assert audit["continuation_epochs_ran"] == 1955
    assert audit["best_epoch"] == 1980



def test_parallel_ledger_preserves_serial_cost_sum_and_rejects_schedule_tampering(tmp_path):
    case = make_case(tmp_path)
    summary = load_summary(case)
    training = verifier.audit_training(case["output"], case["protocol_payload"], case["splits"])
    expected_specs = [
        {"seed": seed, "seed_index": seed_index, "outer_fold": outer, "arm": arm}
        for seed_index, seed in enumerate(SEEDS) for outer in range(3) for arm in verifier.ARMS
    ]
    scheduled = sorted(expected_specs, key=lambda spec: (spec["arm"] != "kinetic", spec["seed_index"], spec["outer_fold"]))
    ledger = {
        "schema": verifier.PARALLEL_SCHEMA, "protocol": verifier.PROTOCOL,
        "max_workers": 4, "start_method": "spawn", "schedule": "kinetic_first",
        "scheduled_specs": scheduled, "canonical_merge": "seed_index,outer_fold,protocol_arm_order",
        "parallel_implementation_sha256": sha256(verifier.PARALLEL_IMPLEMENTATION_PATH),
        "shards": [
            {"spec": spec, "cache_hit": False, "path": f"external/{index}.npz", "sha256": f"{index:064d}", "shard_cost": {"wall_clock_seconds": 0.1}}
            for index, spec in enumerate(expected_specs)
        ],
        "cache_hits": 0, "cache_misses": 27, "shard_execution_wall_clock_seconds": 1.0,
        "shard_wall_clock_seconds_sum": 2.7,
        "candidate_fit_wall_clock_seconds_serial_sum": training["fit_wall_clock_seconds"],
        "wall_is_not_serial_sum": True, "scientific_gate_claimed": False,
    }
    write_json(case["output"] / "parallel.json", ledger)
    summary["cost"]["wall_clock_seconds"] = 2.0
    summary["cost"]["parallel"] = {
        key: ledger[key] for key in (
            "max_workers", "start_method", "shard_execution_wall_clock_seconds",
            "shard_wall_clock_seconds_sum", "cache_hits", "cache_misses",
        )
    }
    summary["sha256"]["parallel_implementation"] = sha256(verifier.PARALLEL_IMPLEMENTATION_PATH)
    summary["sha256"]["artifacts"]["parallel.json"] = sha256(case["output"] / "parallel.json")
    save_summary(case, summary)
    result = verify(case)
    assert result["passed"], result["mismatches"]
    ledger["scheduled_specs"] = list(reversed(scheduled))
    write_json(case["output"] / "parallel.json", ledger)
    summary["sha256"]["artifacts"]["parallel.json"] = sha256(case["output"] / "parallel.json")
    save_summary(case, summary)
    result = verify(case)
    assert not result["checks"]["parallel_shard_execution_ledger"]
    assert "parallel.schedule" in result["mismatches"]["parallel"]


def make_v13_parallel_case(tmp_path):
    from scripts import a10_03_e2_kinetic_parallel as parallel

    case = make_case(tmp_path, include_banded=True)
    summary = load_summary(case)
    training = verifier.audit_training(case["output"], case["protocol_payload"], case["splits"])
    expected_specs = [
        {"seed": seed, "seed_index": seed_index, "outer_fold": outer, "arm": arm}
        for seed_index, seed in enumerate(SEEDS) for outer in range(3) for arm in verifier.ARMS
    ]
    scheduled = sorted(expected_specs, key=lambda spec: (spec["arm"] != "kinetic", spec["seed_index"], spec["outer_fold"]))
    identity = {
        **source_sha256(case["protocol"], include_banded=True),
        "parallel_implementation": sha256(verifier.PARALLEL_IMPLEMENTATION_PATH),
    }
    cache = tmp_path / "v13_shard_cache"
    cache.mkdir()
    shards = []
    for spec in expected_specs:
        path = cache / f"{parallel.shard_basename(spec)}.npz"
        result = {"spec": spec, "shard_cost": {"wall_clock_seconds": 0.1}}
        digest = parallel.save_shard(path, result, identity)
        shards.append({
            "spec": spec, "cache_hit": False, "path": str(path),
            "sha256": digest, "shard_cost": result["shard_cost"],
        })
    ledger = {
        "schema": verifier.PARALLEL_SCHEMA, "protocol": verifier.PROTOCOL,
        "max_workers": 4, "start_method": "spawn", "schedule": "kinetic_first",
        "configured_arm_max_workers": dict(parallel.DEFAULT_ARM_MAX_WORKERS),
        "arm_max_workers": {arm: min(4, limit) for arm, limit in parallel.DEFAULT_ARM_MAX_WORKERS.items()},
        "scheduled_specs": scheduled, "canonical_merge": "seed_index,outer_fold,protocol_arm_order",
        "parallel_implementation_sha256": identity["parallel_implementation"],
        "shards": shards, "cache_hits": 0, "cache_misses": 27,
        "shard_execution_wall_clock_seconds": 1.0, "shard_wall_clock_seconds_sum": 2.7,
        "candidate_fit_wall_clock_seconds_serial_sum": training["fit_wall_clock_seconds"],
        "wall_is_not_serial_sum": True, "scientific_gate_claimed": False,
    }
    write_json(case["output"] / "parallel.json", ledger)
    summary["cost"]["wall_clock_seconds"] = 2.0
    summary["cost"]["parallel"] = {
        key: ledger[key] for key in (
            "max_workers", "start_method", "configured_arm_max_workers", "arm_max_workers",
            "shard_execution_wall_clock_seconds", "shard_wall_clock_seconds_sum", "cache_hits", "cache_misses",
        )
    }
    summary["sha256"]["parallel_implementation"] = identity["parallel_implementation"]
    summary["sha256"]["artifacts"]["parallel.json"] = sha256(case["output"] / "parallel.json")
    save_summary(case, summary)
    case.update({"cache": cache, "cache_identity": identity})
    return case


def load_parallel(case):
    return json.loads((case["output"] / "parallel.json").read_text(encoding="utf-8"))


def save_parallel(case, ledger):
    write_json(case["output"] / "parallel.json", ledger)
    refresh_artifact_sha(case, "parallel.json")


def test_v13_parallel_schema_real_shard_cache_and_outer_member_contract(tmp_path):
    case = make_v13_parallel_case(tmp_path)
    result = verify(case)
    assert result["passed"], result["mismatches"]
    assert result["checks"]["outer_test_member_residual_contract"]
    assert result["recomputed"]["member_conservation"]["kinetic_members_checked"] == 3 * N_TRANSCRIPTS * 3


@pytest.mark.parametrize("repeat", [0, 1, 2])
def test_real_cuda_v13_small_producer_rebuild_three_times(tmp_path, repeat):
    import torch
    from scripts import a10_03_e2_kinetic_parallel as parallel

    if not torch.cuda.is_available():
        pytest.skip("real CUDA producer rebuild requires CUDA")
    raw_path = tmp_path / "synthetic_mohammad.txt"
    write_raw(raw_path)
    protocol_path = tmp_path / "protocol.json"
    protocol = make_protocol(protocol_path, raw_path)
    protocol["training"]["batch_transcripts"] = 4
    protocol["training"]["successive_halving"]["rung_epochs"] = 1
    protocol["training"]["early_stopping"]["patience_epochs"] = 1
    protocol["training"]["early_stopping"]["min_absolute_improvement"] = 1e100
    protocol["hyperparameters"]["weight_decays"] = [0.0]
    write_json(protocol_path, protocol)
    output = tmp_path / "producer_output"
    parallel.run_experiment(
        protocol_path, raw_path, output, "cuda:0", 1, tmp_path / "shard_cache",
        arm_max_workers={arm: 1 for arm in verifier.ARMS},
    )
    result = verifier.verify_e2_kinetic(
        protocol_path, raw_path, output, allow_synthetic=True, n_resamples=128,
    )
    assert result["passed"], result["mismatches"]
    assert result["checks"]["outer_test_member_residual_contract"]
    assert result["recomputed"]["member_conservation"]["kinetic_members_checked"] == 3 * N_TRANSCRIPTS * 3


@pytest.mark.parametrize("kind,expected", [
    ("missing", "parallel.shards.cache_missing"),
    ("payload", "parallel.shards.cache_sha256"),
    ("sidecar", "parallel.shards.cache_sidecar_sha256"),
])
def test_v13_verifier_rejects_missing_or_tampered_real_shard_cache(tmp_path, kind, expected):
    case = make_v13_parallel_case(tmp_path)
    path = case["cache"] / "seed_00_outer_00_independent.npz"
    if kind == "missing":
        path.unlink()
    elif kind == "payload":
        with path.open("ab") as handle:
            handle.write(b"tampered")
    else:
        path.with_suffix(path.suffix + ".sha256").write_text("0" * 64 + "\n", encoding="ascii")
    result = verify(case)
    assert not result["checks"]["parallel_shard_execution_ledger"]
    assert expected in result["mismatches"]["parallel"]


def test_v13_verifier_rejects_backend_identity_mismatch_even_with_refreshed_hashes(tmp_path):
    case = make_v13_parallel_case(tmp_path)
    path = case["cache"] / "seed_00_outer_00_independent.npz"
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name].copy() for name in archive.files}
    metadata = json.loads(arrays["metadata"].item())
    metadata["identity"]["banded_cuda_backend"] = "0" * 64
    arrays["metadata"] = np.asarray(json.dumps(metadata, ensure_ascii=False, allow_nan=False))
    with path.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    digest = sha256(path)
    path.with_suffix(path.suffix + ".sha256").write_text(digest + "\n", encoding="ascii")
    ledger = load_parallel(case)
    ledger["shards"][0]["sha256"] = digest
    save_parallel(case, ledger)
    result = verify(case)
    assert not result["checks"]["parallel_shard_execution_ledger"]
    assert "parallel.shards.cache_identity" in result["mismatches"]["parallel"]
    assert "parallel.shards.cache_sha256" not in result["mismatches"]["parallel"]


def test_v13_verifier_strictly_checks_scheduler_arm_quotas(tmp_path):
    case = make_v13_parallel_case(tmp_path)
    ledger = load_parallel(case)
    ledger["arm_max_workers"]["kinetic"] += 1
    save_parallel(case, ledger)
    summary = load_summary(case)
    summary["cost"]["parallel"]["arm_max_workers"]["kinetic"] += 1
    save_summary(case, summary)
    result = verify(case)
    assert not result["checks"]["parallel_shard_execution_ledger"]
    assert not result["checks"]["complete_cost_ledger"]
    assert "parallel.arm_max_workers" in result["mismatches"]["parallel"]

    case = make_v13_parallel_case(tmp_path / "missing_quotas")
    ledger = load_parallel(case)
    del ledger["configured_arm_max_workers"], ledger["arm_max_workers"]
    save_parallel(case, ledger)
    summary = load_summary(case)
    del summary["cost"]["parallel"]["configured_arm_max_workers"], summary["cost"]["parallel"]["arm_max_workers"]
    save_summary(case, summary)
    result = verify(case)
    assert result["checks"]["startup_source_provenance_recomputed"]
    assert not result["checks"]["parallel_shard_execution_ledger"]
    assert not result["checks"]["complete_cost_ledger"]
    assert "parallel.arm_quotas" in result["mismatches"]["parallel"]


def test_missing_curve_and_non_inner_selected_candidate_are_detected(tmp_path):
    case = make_case(tmp_path)
    lines = (case["output"] / "curves.jsonl").read_text(encoding="utf-8").splitlines()
    (case["output"] / "curves.jsonl").write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
    refresh_artifact_sha(case, "curves.jsonl")
    assert not verify(case)["checks"]["complete_inner_curves_plateau_and_inner_only_selection"]

    case = make_case(tmp_path / "selection")
    selection = load_selection(case)
    selection["records"][0]["selected_grid_index"] = 1
    save_selection(case, selection)
    result = verify(case)
    assert not result["checks"]["complete_inner_curves_plateau_and_inner_only_selection"]
    assert "promoted post-continuation" in result["mismatches"]["training"][0]


def test_parameter_count_mismatch_is_detected(tmp_path):
    case = make_case(tmp_path)
    summary = load_summary(case)
    summary["parameter_matching"]["per_inner_model"]["kinetic"] += 1
    save_summary(case, summary)
    assert not verify(case)["checks"]["parameter_count_matching"]


@pytest.mark.parametrize("field,value", [
    ("available", False), ("requested_device", "cpu"), ("name", ""),
])
def test_cuda_fallback_or_missing_execution_record_is_detected(tmp_path, field, value):
    case = make_case(tmp_path)
    summary = load_summary(case)
    summary["environment"]["cuda"][field] = value
    save_summary(case, summary)
    assert not verify(case)["checks"]["real_cuda_no_fallback_recorded"]


def test_prediction_target_mask_membership_and_residual_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    arrays = read_predictions(case)
    arrays["target"][0, 0] += 0.1
    save_predictions(case, arrays)
    result = verify(case)
    assert not result["checks"]["selected_states_outer_ensembles_and_member_conservation"]
    assert result["checks"]["summary_artifact_sha256"]

    case = make_case(tmp_path / "membership")
    arrays = read_predictions(case)
    arrays["outer_fold"][0] = (arrays["outer_fold"][0] + 1) % 3
    save_predictions(case, arrays)
    assert not verify(case)["checks"]["selected_states_outer_ensembles_and_member_conservation"]

    case = make_case(tmp_path / "residual")
    arrays = read_predictions(case)
    arrays["solver_max_abs_normalized_residual"][0, verifier.ARMS.index("kinetic"), 0] = -1.0
    save_predictions(case, arrays)
    assert not verify(case)["checks"]["selected_states_outer_ensembles_and_member_conservation"]


def test_independent_arm_cannot_invent_kinetic_flux(tmp_path):
    case = make_case(tmp_path)
    arrays = read_predictions(case)
    arrays["flux"][0, 0, 0] = 0.2
    save_predictions(case, arrays)
    assert not verify(case)["checks"]["selected_states_outer_ensembles_and_member_conservation"]


def test_density_tampering_recomputes_metrics_even_with_updated_hash(tmp_path):
    case = make_case(tmp_path)
    arrays = read_predictions(case)
    arrays["prediction"][0, 1, 0, 5] += 0.01
    save_predictions(case, arrays)
    result = verify(case)
    assert not result["checks"]["summary_tb_mse_pearson_spearman_recomputed"]
    assert not result["checks"]["per_transcript_metrics_csv_recomputed"]
    assert result["checks"]["summary_artifact_sha256"]


def test_paired_ci_holm_and_three_seed_direction_use_two_comparators():
    rows = []
    for seed in SEEDS:
        for transcript in range(4):
            for arm, mse in (("independent", 1.0), ("kinetic", 1.0), ("position", 2.0)):
                rows.append({"seed": seed, "transcript_index": transcript, "arm": arm, "mse": mse})
    inference = verifier.recompute_inference(rows, SEEDS, n_resamples=512)
    assert inference["across_seeds"]["independent"]["effects"] == [0.0, 0.0, 0.0]
    assert inference["across_seeds"]["independent"]["all_seed_effects_positive"] is False
    assert inference["h2_development_positive"] is False
    for seed_result in inference["per_seed"].values():
        raw = [seed_result["comparisons"][name]["signflip_p_two_sided"] for name in verifier.COMPARATORS]
        adjusted = verifier.holm_adjust(raw)
        assert seed_result["comparisons"]["independent"]["holm_p"] == 1.0
        for comparator, expected in zip(verifier.COMPARATORS, adjusted):
            assert seed_result["comparisons"][comparator]["holm_p"] == expected
    pooled = inference["pooled_seed_first"]
    assert "holm_p" not in pooled and "signflip_p_two_sided" not in pooled
    raw = [pooled["comparisons"][name]["signflip_p_two_sided"] for name in verifier.COMPARATORS]
    for comparator, expected in zip(verifier.COMPARATORS, verifier.holm_adjust(raw)):
        assert pooled["comparisons"][comparator]["holm_p"] == expected
        assert pooled["comparisons"][comparator]["signflip_p_two_sided"] == raw[verifier.COMPARATORS.index(comparator)]


def test_csv_tampering_is_detected(tmp_path):
    case = make_case(tmp_path)
    path = case["output"] / "per_transcript_metrics.csv"
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    rows[0]["mse"] = str(float(rows[0]["mse"]) + 0.1)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    refresh_artifact_sha(case, "per_transcript_metrics.csv")
    result = verify(case)
    assert not result["checks"]["per_transcript_metrics_csv_recomputed"]
    assert result["checks"]["summary_artifact_sha256"]


def test_summary_statistics_cost_scope_and_unexpected_output_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    summary = load_summary(case)
    summary["metrics"]["1234"]["kinetic"]["tb_mse"] += 0.1
    summary["cost"]["wall_clock_seconds"] = -1
    summary["scope"]["sota_claim"] = True
    save_summary(case, summary)
    (case["output"] / "unexpected.json").write_text("{}")
    result = verify(case)
    assert not result["checks"]["summary_tb_mse_pearson_spearman_recomputed"]
    assert not result["checks"]["complete_cost_ledger"]
    assert not result["checks"]["summary_scope"]
    assert not result["checks"]["output_files_exact"]


def test_raw_target_and_artifact_hash_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    lines = case["raw"].read_text(encoding="utf-8").splitlines()
    counts = lines[2].split()
    counts[0] = str(float(counts[0]) + 0.1)
    lines[2] = " ".join(counts)
    case["raw"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify(case)
    assert not result["checks"]["summary_data"]
    assert not result["checks"]["summary_artifact_sha256"]

    case = make_case(tmp_path / "hash")
    summary = load_summary(case)
    summary["sha256"]["artifacts"]["predictions.npz"] = "0" * 64
    save_summary(case, summary)
    assert not verify(case)["checks"]["summary_artifact_sha256"]


def test_selected_state_and_source_sha_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    state_path = case["output"] / "selected_inner_states.npz"
    with np.load(state_path, allow_pickle=False) as archive:
        state_arrays = {name: archive[name].copy() for name in archive.files}
    state_arrays["state/0/0/0/0/codon.weight"][0, 0] += 0.1
    with state_path.open("wb") as handle:
        np.savez_compressed(handle, **state_arrays)
    refresh_artifact_sha(case, "selected_inner_states.npz")
    result = verify(case)
    assert not result["checks"]["selected_states_outer_ensembles_and_member_conservation"]
    assert result["checks"]["summary_artifact_sha256"]

    case = make_case(tmp_path / "source_hash")
    summary = load_summary(case)
    summary["sha256"]["implementation"] = "f" * 64
    summary["sha256"]["mean_field_operator"] = "e" * 64
    save_summary(case, summary)
    result = verify(case)
    assert not result["checks"]["summary_artifact_sha256"]
    assert "summary.sha256.implementation" in result["mismatches"]["sha256"]
    assert "summary.sha256.mean_field_operator" in result["mismatches"]["sha256"]


def test_exact_duplicate_cds_or_id_is_a_fatal_qc_conflict(tmp_path):
    raw_path = tmp_path / "duplicate_cds.txt"
    write_raw(raw_path)
    lines = raw_path.read_text(encoding="utf-8").splitlines()
    lines.extend([">same_cds_different_id", lines[1], lines[2]])
    raw_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exact CDS conflict"):
        verifier.parse_raw(raw_path)

    raw_path = tmp_path / "duplicate_id.txt"
    write_raw(raw_path)
    lines = raw_path.read_text(encoding="utf-8").splitlines()
    lines.extend([">synthetic_000", lines[4], lines[5]])
    raw_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="transcript ID conflict"):
        verifier.parse_raw(raw_path)


def test_independent_scipy_and_score_field_have_known_answers():
    single = verifier.independent_steady_state(2.0, [], 2.0)
    np.testing.assert_allclose(single["rho"], [0.5], atol=1e-12, rtol=0)
    assert single["flux"] == pytest.approx(1.0, abs=1e-12)
    rate = 0.7
    q = (3.0 - np.sqrt(5.0)) / 2.0
    double = verifier.independent_steady_state(rate, [rate], rate)
    np.testing.assert_allclose(double["rho"], [1.0 - q, q], atol=1e-11, rtol=0)
    assert double["flux"] == pytest.approx(rate * q, abs=1e-11)
    assert np.max(np.abs(double["residual"])) < 1e-10
    difficult_rates = np.asarray([
        0.6241776213442669, 0.47451355545013385, 1.1964860125474894,
        0.11568940550497601, 0.5519937948950983, 0.2333057929701008,
        0.646396051742627, 1.0761101284563321, 0.12215197964929495,
        0.03568107619543787, 0.26869833324597975,
    ])
    difficult = verifier.independent_steady_state(difficult_rates[0], difficult_rates[1:-1], difficult_rates[-1])
    assert np.all((difficult["rho"] >= 0) & (difficult["rho"] <= 1))
    assert difficult["flux"] > 0
    assert np.max(np.abs(difficult["residual"])) <= 1e-10

    record = {"length": 3, "codons": np.asarray([0, 1, 63])}
    state = {
        "codon.weight": (np.arange(64, dtype=np.float64) / 100.0).reshape(64, 1),
        "relative_position.weight": np.asarray([[0.2]], dtype=np.float64),
    }
    score = np.asarray([0.0, 0.11, 0.83])
    independent = verifier.rebuild_selected_member(record, state, "independent", {"rate_floor": 0.0001, "rate_ceiling": 1000.0})
    np.testing.assert_allclose(independent["rho"], 1.0 / (1.0 + np.exp(-score)), atol=1e-14, rtol=0)
    position = verifier.rebuild_selected_member(
        record, {"relative_position.weight": np.asarray([[0.2]], dtype=np.float64)}, "position",
        {"rate_floor": 0.0001, "rate_ceiling": 1000.0},
    )
    np.testing.assert_allclose(position["rho"], 1.0 / (1.0 + np.exp(-np.asarray([0.0, 0.1, 0.2]))), atol=1e-14, rtol=0)


def test_seed_dependent_resampling_and_seed_first_effects_have_known_answers():
    first = verifier.paired_inference([1.0, 2.0, 4.0], 8, 8, 73, 3)
    second = verifier.paired_inference([1.0, 2.0, 4.0], 8, 8, 74, 3)
    assert first["effect"] == pytest.approx(7.0 / 3.0)
    assert first["bootstrap_95ci"] == pytest.approx([1.0, 3.8833333333333333])
    assert first["signflip_p_two_sided"] == pytest.approx(4.0 / 9.0)
    assert second["bootstrap_95ci"] == pytest.approx([2.0583333333333336, 3.3333333333333335])
    assert second["signflip_p_two_sided"] == pytest.approx(1.0 / 9.0)

    rows = []
    for seed_index, seed in enumerate(SEEDS):
        for transcript in range(2):
            independent_effect = transcript + seed_index + 1
            position_effect = seed_index + 2 if transcript == 0 else seed_index
            for arm, mse in (
                ("independent", independent_effect), ("position", position_effect), ("kinetic", 0.0),
            ):
                rows.append({"seed": seed, "transcript_index": transcript, "arm": arm, "mse": float(mse)})
    result = verifier.recompute_inference(rows, SEEDS, n_resamples=16)
    assert [result["per_seed"][str(seed)]["comparisons"]["independent"]["effect"] for seed in SEEDS] == [1.5, 2.5, 3.5]
    assert result["pooled_seed_first"]["comparisons"]["independent"]["effect"] == pytest.approx(2.5)
    assert result["pooled_seed_first"]["comparisons"]["position"]["effect"] == pytest.approx(2.0)
    assert result["pooled_seed_first"]["comparisons"]["independent"]["n_transcripts"] == 2


def test_real_strict_qc_contract_is_frozen_and_compared_to_independent_raw_qc(tmp_path):
    expected = {
        "input_records": 1761,
        "rejected_too_short": 0,
        "rejected_missing_start_atg": 171,
        "rejected_missing_terminal_stop": 0,
        "rejected_internal_stop": 0,
        "rejected_coverage": 517,
        "rejected_no_unmasked_positive_position": 0,
        "eligible_transcripts": 1073,
        "sha256": verifier.REAL_RAW_SHA256,
        "minimum_eligible_length": 16,
        "maximum_eligible_length": 1521,
    }
    assert verifier.REAL_QC == expected
    assert not verifier.value_mismatches(expected, verifier.REAL_QC, "qc")
    tampered = dict(expected)
    tampered["rejected_coverage"] += 1
    tampered["eligible_transcripts"] -= 1
    assert verifier.value_mismatches(tampered, verifier.REAL_QC, "qc") == [
        "qc.rejected_coverage", "qc.eligible_transcripts",
    ]

    raw_path = tmp_path / "synthetic.txt"
    write_raw(raw_path)
    _, independently_recomputed_qc = verifier.parse_raw(raw_path)
    mismatches = verifier.value_mismatches(independently_recomputed_qc, verifier.REAL_QC, "qc")
    assert "qc.input_records" in mismatches
    assert "qc.eligible_transcripts" in mismatches


def make_real_shaped_protocol(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw_path = tmp_path / "synthetic.txt"
    write_raw(raw_path)
    protocol = make_protocol(tmp_path / "protocol.json", raw_path)
    protocol["inputs"]["sha256"] = verifier.REAL_RAW_SHA256
    protocol["inputs"]["expected_eligible_transcripts"] = verifier.REAL_ELIGIBLE
    protocol["inputs"]["expected_basename"] = "Mohammad16.txt"
    protocol["training"]["successive_halving"]["rung_epochs"] = 50
    protocol["training"]["early_stopping"]["patience_epochs"] = 25
    write_json(tmp_path / "protocol.json", protocol)
    return tmp_path / "protocol.json", raw_path, protocol


@pytest.mark.parametrize("path,value", [
    (("split", "seed"), 9100302),
    (("training", "model_seeds"), [1234, 2345, 9999]),
    (("hyperparameters", "learning_rate", "minimum"), 0.0002),
    (("hyperparameters", "weight_decays"), [0.0]),
    (("training", "successive_halving", "retained_candidates_per_arm"), 1),
    (("training", "batch_transcripts"), 31),
    (("model", "rate_floor"), 0.001),
])
def test_real_mode_freezes_all_scientific_numeric_paths(tmp_path, path, value):
    protocol_path, _, protocol = make_real_shaped_protocol(tmp_path)
    assert verifier.load_protocol(protocol_path)["split"]["seed"] == verifier.REAL_SPLIT_SEED
    target = protocol
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    write_json(protocol_path, protocol)
    with pytest.raises(ValueError, match="frozen scientific numerics|successive-halving"):
        verifier.load_protocol(protocol_path)


def test_real_mode_rejects_synthetic_raw(tmp_path):
    case = make_case(tmp_path)
    with pytest.raises(ValueError, match="pinned Mohammad16"):
        verifier.verify_e2_kinetic(case["protocol"], case["raw"], case["output"])
    protocol_path, raw_path, _ = make_real_shaped_protocol(tmp_path / "resamples")
    with pytest.raises(ValueError, match="exactly 20000 resamples"):
        verifier.verify_e2_kinetic(protocol_path, raw_path, tmp_path / "unused", n_resamples=512)


def test_producer_format_end_to_end_verifies_eliminated_oof_and_split_costs(tmp_path, monkeypatch):
    from scripts import a10_03_e2_kinetic as producer

    monkeypatch.setattr(producer, "resolve_cuda_device", lambda name: producer.torch.device("cpu"))
    monkeypatch.setattr(producer, "_environment", lambda device: {
        "cuda": {
            "requested_device": "cuda:0", "available": True, "torch_cuda_version": "synthetic",
            "name": "Synthetic CUDA record", "capability": [9, 0],
        },
    })
    original_candidate_cost = producer._candidate_cost

    def synthetic_cuda_cost(*args, **kwargs):
        cost = original_candidate_cost(*args, **kwargs)
        cost["cuda_peak_memory_bytes"] = 1024
        return cost

    monkeypatch.setattr(producer, "_candidate_cost", synthetic_cuda_cost)
    raw_path = tmp_path / "synthetic_mohammad.txt"
    write_raw(raw_path)
    protocol_path = tmp_path / "protocol.json"
    protocol = make_protocol(protocol_path, raw_path)
    protocol["training"]["batch_transcripts"] = 4
    protocol["training"]["successive_halving"]["rung_epochs"] = 2
    protocol["training"]["early_stopping"]["patience_epochs"] = 1
    protocol["training"]["early_stopping"]["min_absolute_improvement"] = 1e100
    protocol["hyperparameters"]["weight_decays"] = [0.0]
    write_json(protocol_path, protocol)
    output = tmp_path / "producer_output"
    summary = producer.run_experiment(protocol_path, raw_path, output)
    summary["cost"]["cuda_peak_memory_bytes"] = 1024
    write_json(output / "summary.json", summary)
    result = verify({"protocol": protocol_path, "raw": raw_path, "output": output})
    assert result["passed"], json.dumps(result["mismatches"], indent=2)
    selection = load_selection({"output": output})
    eliminated = [
        candidate for record in selection["records"] for candidate in record["candidates"]
        if not candidate["rung_selected"]
    ]
    assert eliminated
    assert all(candidate["inner_oof_tb_mse"] is None for candidate in eliminated)
    assert all(candidate["inner_oof_transcripts"] == 0 for candidate in eliminated)
    assert result["recomputed"]["training"]["legacy_cumulative_cost_fits"] == 0
    assert summary["cost"]["candidate_fit_wall_clock_seconds"] == pytest.approx(
        summary["cost"]["rung_wall_clock_seconds"] + summary["cost"]["continuation_wall_clock_seconds"]
    )


def cli_arguments(case, output):
    return [
        "--protocol", str(case["protocol"]), "--raw", str(case["raw"]),
        "--output-dir", str(case["output"]), "--output", str(output),
        "--allow-synthetic", "--resamples", "512",
    ]


def test_cli_synthetic_success_tamper_failure_and_exclusive_overwrite(tmp_path):
    case = make_case(tmp_path)
    output = tmp_path / "nested" / "verification.json"
    assert verifier.main(cli_arguments(case, output)) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["passed"]
    original = output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        verifier.main(cli_arguments(case, output))
    assert output.read_bytes() == original

    summary = load_summary(case)
    summary["metrics"]["1234"]["independent_minus_kinetic_tb_mse"] += 0.1
    save_summary(case, summary)
    failed = tmp_path / "failed.json"
    assert verifier.main(cli_arguments(case, failed)) == 1
    assert not json.loads(failed.read_text(encoding="utf-8"))["passed"]
