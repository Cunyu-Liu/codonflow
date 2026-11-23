import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from codonflow.models import kinetic_mean_field
from scripts import a10_03_e2_kinetic as kinetic


ROOT = Path(__file__).resolve().parents[1]
FROZEN_PROTOCOL = ROOT / "configs" / "a10_03_e2_kinetic_protocol_v1.json"
RAW_SHA = "d093a3b0c53aa90d0626cc277a65a558c538ecbeb4d1cda091f02aad134588bc"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


NONSTOP_CODONS = tuple(codon for codon in kinetic.CODONS if codon not in kinetic.STOP_CODONS)


def synthetic_codons(transcript, length):
    return (
        ["ATG"]
        + [NONSTOP_CODONS[(transcript * 7 + position * 3) % len(NONSTOP_CODONS)] for position in range(1, length - 1)]
        + ["TAA"]
    )


def raw_text(n_transcripts=9, altered=None):
    records = []
    for transcript in range(n_transcripts):
        length = 10 + transcript % 3
        codons = synthetic_codons(transcript, length)
        counts = [1.0 + ((transcript * 3 + position * 5) % 11) for position in range(length)]
        if altered is not None and transcript == altered:
            counts[5] *= 4.0
            counts[6] += 2.0
        records.extend([
            f">synthetic_{transcript}",
            " ".join(codons),
            " ".join(str(value) for value in counts),
        ])
    return "\n".join(records) + "\n"


def write_raw(path, n_transcripts=9, altered=None):
    path.write_text(raw_text(n_transcripts, altered), encoding="utf-8")
    return path


def synthetic_protocol(tmp_path, raw_path, n_transcripts=9):
    protocol = json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))
    protocol["inputs"]["expected_basename"] = raw_path.name
    protocol["inputs"]["sha256"] = sha256(raw_path)
    protocol["inputs"]["expected_eligible_transcripts"] = n_transcripts
    protocol["training"]["model_seeds"] = [11, 22, 33]
    protocol["training"]["batch_transcripts"] = 4
    protocol["training"]["successive_halving"]["rung_epochs"] = 2
    protocol["training"]["early_stopping"]["patience_epochs"] = 1
    protocol["training"]["early_stopping"]["min_absolute_improvement"] = 1e100
    protocol["hyperparameters"]["learning_rate"] = {
        "spacing": "log10_uniform", "minimum": 0.001, "maximum": 0.001, "count": 1,
    }
    protocol["hyperparameters"]["weight_decays"] = [0.0, 0.0001, 0.001]
    path = tmp_path / f"{raw_path.stem}_protocol.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")
    return path


def science_selection(payload, outer_fold=0):
    records = []
    for record in payload["records"]:
        if record["outer_fold"] != outer_fold:
            continue
        records.append({
            "seed": record["seed"],
            "arm": record["arm"],
            "selected_grid_index": record["selected_grid_index"],
            "rung_selected_grid_indices": record["rung_selected_grid_indices"],
            "candidates": [
                {
                    "learning_rate": candidate["learning_rate"],
                    "weight_decay": candidate["weight_decay"],
                    "rung_selected": candidate["rung_selected"],
                    "rung_inner_oof_tb_mse": candidate["rung_inner_oof_tb_mse"],
                    "inner_oof_tb_mse": candidate["inner_oof_tb_mse"],
                    "folds": [
                        {
                            "best_epoch": fold["best_epoch"],
                            "best_validation_tb_mse": fold["best_validation_tb_mse"],
                            "stop_reason": fold["stop_reason"],
                        }
                        for fold in candidate["folds"]
                    ],
                }
                for candidate in record["candidates"]
            ],
        })
    return records


def science_curves(path, outer_fold=0):
    result = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["outer_fold"] != outer_fold:
                continue
            result.append({
                "seed": record["seed"],
                "arm": record["arm"],
                "inner_fold": record["inner_fold"],
                "grid_index": record["grid_index"],
                "rung_selected": record["rung_selected"],
                "rung": record["rung"],
                "resume": record["resume"],
                "stop_reason": record["stop_reason"],
                "epochs": [
                    {
                        "epoch": epoch["epoch"],
                        "train_tb_mse": epoch["train_tb_mse"],
                        "validation_tb_mse": epoch["validation_tb_mse"],
                    }
                    for epoch in record["epochs"]
                ],
            })
    return result


def test_frozen_protocol_pins_raw_qc_nested_cv_three_seeds_and_claim_boundary():
    protocol = kinetic.load_protocol(FROZEN_PROTOCOL)
    assert protocol["protocol"] == "a10_03_e2_kinetic_protocol_v3"
    assert kinetic.SUMMARY_SCHEMA == "a10-03-e2-kinetic-summary-v4"
    assert protocol["model"]["arms"] == ["independent", "position", "kinetic"]
    assert protocol["model"]["trainable_parameters_per_model"] == {"independent": 65, "position": 1, "kinetic": 65}
    assert protocol["evaluation"]["ensemble_mean_is_common_steady_state"] is False
    assert "selected_inner_states.npz" in protocol["outputs"]["files"]
    assert "provenance.json" in protocol["outputs"]["files"]
    assert protocol["inputs"]["sha256"] == RAW_SHA
    assert protocol["inputs"]["expected_eligible_transcripts"] == 1073
    expected_qc = protocol["inputs"]["expected_label_free_qc"]
    assert expected_qc["label_free"] is True
    assert expected_qc["counts"] == {
        "input_records": 1761,
        "rejected_too_short": 0,
        "rejected_missing_start_atg": 171,
        "rejected_missing_terminal_stop": 0,
        "rejected_internal_stop": 0,
        "rejected_coverage": 517,
        "rejected_no_unmasked_positive_position": 0,
        "eligible_transcripts": 1073,
    }
    assert expected_qc["minimum_eligible_length"] == 16
    assert expected_qc["maximum_eligible_length"] == 1521
    assert expected_qc["transcript_id_conflicts"] == 0
    assert expected_qc["exact_cds_conflicts"] == 0
    rejection_counts = {key: value for key, value in expected_qc["counts"].items() if key.startswith("rejected_")}
    assert set(expected_qc["rejection_reasons"]) == set(rejection_counts)
    assert expected_qc["counts"]["input_records"] - sum(rejection_counts.values()) == 1073
    assert protocol["preprocessing"]["positive_rule"] == "count > 0.5"
    assert protocol["preprocessing"]["masked_first_positions"] == 5
    assert protocol["preprocessing"]["masked_last_positions"] == 4
    assert protocol["split"]["outer_folds"] == 3
    assert protocol["split"]["inner_folds"] == 3
    assert protocol["training"]["model_seeds"] == [1234, 2345, 3456]
    assert protocol["training"]["successive_halving"]["rung_epochs"] == 50
    assert protocol["training"]["successive_halving"]["retained_candidates_per_arm"] == 2
    assert protocol["training"]["final_epoch_limit"] is None
    assert protocol["training"]["resume_from_rung_last_state"] is True
    assert protocol["training"]["resume_optimizer_and_rng_state"] is True
    assert protocol["training"]["selected_candidates_stop_only_on_validation_plateau"] is True
    assert protocol["training"]["rung_rejection_is_not_convergence"] is True
    assert "maximum_epochs" not in protocol["training"]
    assert protocol["training"]["gradient_clip_error_if_nonfinite"] is True
    assert protocol["training"]["finite_parameters_required_after_optimizer_step"] is True
    assert protocol["hyperparameters"]["learning_rate"]["spacing"] == "log10_uniform"
    assert kinetic.learning_rate_grid(protocol["hyperparameters"]["learning_rate"]) == pytest.approx(
        [1e-4, 1e-3, 1e-2],
    )
    assert protocol["runtime"]["device"] == "cuda"
    assert protocol["runtime"]["cpu_fallback"] is False
    assert protocol["scope"]["development_only"] is True
    assert protocol["scope"]["final_research_ood"] is False
    assert protocol["scope"]["sota_claim"] is False
    assert protocol["outputs"]["overwrite"] == "forbidden"


def test_raw_parser_applies_rk37_density_mask_and_eligibility_qc(tmp_path):
    lines = []
    eligible_codons = synthetic_codons(0, 10)
    eligible_counts = [0.0, 1.0, 1.0, 1.0, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0]
    lines.extend([">eligible", "".join(eligible_codons), " ".join(map(str, eligible_counts))])
    lines.extend([">coverage", " ".join(synthetic_codons(1, 10)), " ".join(["1"] * 6 + ["0"] * 4)])
    lines.extend([">short", " ".join(synthetic_codons(2, 9)), " ".join(["1"] * 9)])
    lines.extend([
        ">no_unmasked", " ".join(synthetic_codons(3, 10)),
        " ".join(["1"] * 5 + ["0"] + ["1"] * 4),
    ])
    lines.extend([">start", " ".join(["GAA"] + synthetic_codons(4, 10)[1:]), " ".join(["1"] * 10)])
    lines.extend([">terminal", " ".join(synthetic_codons(5, 10)[:-1] + ["GAA"]), " ".join(["1"] * 10)])
    internal = synthetic_codons(6, 10)
    internal[5] = "TAA"
    lines.extend([">internal", " ".join(internal), " ".join(["1"] * 10)])
    raw = tmp_path / "synthetic_qc.txt"
    raw.write_text("\n".join(lines) + "\n", encoding="utf-8")

    records, qc = kinetic.parse_raw_matrix(raw, sha256(raw))

    assert len(records) == 1
    record = records[0]
    assert record.transcript_id == "eligible"
    assert record.coverage == pytest.approx(0.9)
    assert record.positive_mean == pytest.approx(10 / 9)
    np.testing.assert_allclose(record.density, np.asarray(eligible_counts) / (10 / 9))
    assert record.mask.tolist() == [False] * 5 + [True] + [False] * 4
    assert qc["input_records"] == 7
    assert qc["eligible_transcripts"] == 1
    assert qc["rejected_too_short"] == 1
    assert qc["rejected_missing_start_atg"] == 1
    assert qc["rejected_missing_terminal_stop"] == 1
    assert qc["rejected_internal_stop"] == 1
    assert qc["rejected_coverage"] == 1
    assert qc["rejected_no_unmasked_positive_position"] == 1
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        kinetic.parse_raw_matrix(raw, "0" * 64)


def test_raw_parser_rejects_transcript_id_and_exact_normalized_cds_conflicts(tmp_path):
    codons = synthetic_codons(0, 10)
    duplicate_id = tmp_path / "duplicate_id.txt"
    duplicate_id.write_text(
        "\n".join([
            ">same first", " ".join(codons), " ".join(["1"] * 10),
            ">same second", " ".join(synthetic_codons(1, 10)), " ".join(["1"] * 10),
        ]) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="transcript ID conflict.*record 1"):
        kinetic.parse_raw_matrix(duplicate_id)

    duplicate_cds = tmp_path / "duplicate_cds.txt"
    duplicate_cds.write_text(
        "\n".join([
            ">first", " ".join(codons), " ".join(["1"] * 10),
            ">second", " ".join(codons).replace("T", "U"), " ".join(["1"] * 10),
        ]) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exact CDS conflict with record 1"):
        kinetic.parse_raw_matrix(duplicate_cds)


def test_nested_transcript_partitions_are_disjoint_and_deterministic(tmp_path):
    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    first = kinetic.make_nested_splits(records, 9100301)
    second = kinetic.make_nested_splits(records, 9100301)
    assert [outer["test"].tolist() for outer in first] == [outer["test"].tolist() for outer in second]
    tested = []
    for outer in first:
        tested.extend(outer["test"].tolist())
        development = set()
        for inner in outer["inner"]:
            train = set(inner["train"].tolist())
            validation = set(inner["validation"].tolist())
            test = set(outer["test"].tolist())
            assert not train & validation
            assert not train & test
            assert not validation & test
            assert not development & validation
            development |= validation
        assert development == set(range(len(records))) - set(outer["test"].tolist())
    assert sorted(tested) == list(range(len(records)))


def test_position_arm_is_position_only_and_independent_kinetic_score_fields_match(tmp_path):
    independent = kinetic._new_model(torch.device("cpu"), 7, "independent")
    position = kinetic._new_model(torch.device("cpu"), 7, "position")
    kinetic_model = kinetic._new_model(torch.device("cpu"), 7, "kinetic")
    assert {
        arm: sum(parameter.numel() for parameter in model.parameters())
        for arm, model in (("independent", independent), ("position", position), ("kinetic", kinetic_model))
    } == {"independent": 65, "position": 1, "kinetic": 65}
    assert [name for name, _ in position.named_parameters()] == ["relative_position.weight"]
    assert [name for name, _ in independent.named_parameters()] == [name for name, _ in kinetic_model.named_parameters()]

    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    packed = kinetic._pack(records[:1], torch.device("cpu"))
    altered = dict(packed)
    altered["codons"] = packed["codons"].clone()
    altered["codons"][0, 1:-1] = altered["codons"][0, 1:-1].flip(0)
    protocol = kinetic.load_protocol(FROZEN_PROTOCOL)
    first = kinetic.forward_arm(position, "position", packed, protocol["model"])
    second = kinetic.forward_arm(position, "position", altered, protocol["model"])
    torch.testing.assert_close(first["rho"], second["rho"], rtol=0, atol=0)
    assert first["flux"] is None and first["residual"] is None and first["rates"] is None


def test_kinetic_rates_and_solver_outputs_are_legal_and_stay_on_requested_device(tmp_path):
    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    packed = kinetic._pack(records[:2], torch.device("cpu"))
    model = kinetic.ScoreField().to(dtype=torch.float64)
    output = kinetic.forward_arm(model, "kinetic", packed, kinetic.load_protocol(FROZEN_PROTOCOL)["model"])
    assert output["rates"] is not None
    for row, record in enumerate(records[:2]):
        rates = output["rates"][row, :record.length]
        assert bool(torch.isfinite(rates).all())
        assert bool((rates > 0).all())
        assert bool((output["rho"][row, :record.length] >= 0).all())
        assert bool((output["rho"][row, :record.length] <= 1).all())
        assert output["residual"][row, :record.length + 1].abs().max() < 1e-8
    assert all(value.device.type == "cpu" for value in (output["rates"], output["rho"], output["flux"], output["residual"]))


def test_missing_batch_interface_and_cpu_production_device_fail_closed(monkeypatch):
    with pytest.raises(ValueError, match="refusing CPU fallback"):
        kinetic.resolve_cuda_device("cpu")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="unavailable.*refusing CPU fallback"):
        kinetic.resolve_cuda_device("cuda:0")
    monkeypatch.delattr(kinetic_mean_field, "solve_kinetic_mean_field_batch", raising=False)
    with pytest.raises(RuntimeError, match="no CPU or single-sample production fallback"):
        kinetic._require_batch_solver()


def test_rung_rejection_is_not_convergence_and_top2_uses_rung_score(tmp_path):
    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    protocol = kinetic.load_protocol(FROZEN_PROTOCOL)
    protocol["training"]["batch_transcripts"] = 3
    protocol["training"]["successive_halving"]["rung_epochs"] = 2
    protocol["training"]["early_stopping"]["patience_epochs"] = 1
    rung = kinetic.start_candidate_rung(
        "position", records[:1], records[1:2], 1e-3, 0.0, 17, protocol, torch.device("cpu"),
    )
    rejected = kinetic.reject_rung_candidate(rung)
    assert rejected["stop_reason"] == "rejected_at_rung_not_converged"
    assert rejected["validation_plateau_converged"] is False
    assert rejected["resume"] is None
    assert len(rejected["curves"]) == 2
    candidates = [
        {"report": {"grid_index": index, "rung_inner_oof_tb_mse": score}}
        for index, score in enumerate((0.3, 0.1, 0.2))
    ]
    assert kinetic.successive_halving_indices(candidates) == [1, 2]


def test_selected_candidate_resumes_rung_last_state_beyond_old_epoch_ceiling(tmp_path):
    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    protocol = kinetic.load_protocol(FROZEN_PROTOCOL)
    protocol["training"]["batch_transcripts"] = 1
    protocol["training"]["successive_halving"]["rung_epochs"] = 2000
    protocol["training"]["early_stopping"]["patience_epochs"] = 1
    protocol["training"]["early_stopping"]["min_absolute_improvement"] = 1e100
    rung = kinetic.start_candidate_rung(
        "position", records[:1], records[1:2], 1e-3, 0.0, 17, protocol, torch.device("cpu"),
    )
    rung_curves = [dict(epoch) for epoch in rung["curves"]]
    fitted = kinetic.resume_candidate(
        rung, "position", records[:1], records[1:2], 1e-3, 0.0, 17, protocol, torch.device("cpu"),
    )
    assert fitted["stop_reason"] == "validation_plateau"
    assert fitted["validation_plateau_converged"] is True
    assert len(fitted["curves"]) == 2001
    assert fitted["curves"][:2000] == rung_curves
    assert fitted["curves"][-1]["epoch"] == 2001
    assert fitted["resume"]["source"] == "rung_last_state"
    assert fitted["resume"]["source_epoch"] == 2000
    assert fitted["resume"]["start_epoch"] == 2001
    assert fitted["resume"]["restored_model_state_sha256"] == rung["rung"]["last_state_sha256"]
    assert fitted["resume"]["optimizer_state_restored"] is True
    assert fitted["resume"]["rng_state_restored"] is True
    assert fitted["best_epoch"] == 1
    assert np.mean(list(fitted["validation_transcript_mse"].values())) == pytest.approx(
        fitted["best_validation_tb_mse"],
    )


def test_nonfinite_gradient_fails_at_strict_clip_before_optimizer_step(tmp_path, monkeypatch):
    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    protocol = kinetic.load_protocol(FROZEN_PROTOCOL)
    protocol["training"]["batch_transcripts"] = 3
    protocol["training"]["successive_halving"]["rung_epochs"] = 2
    protocol["training"]["early_stopping"]["patience_epochs"] = 1
    original_clip = torch.nn.utils.clip_grad_norm_
    observed = {"called": False}

    def inject_nonfinite_gradient(parameters, max_norm, error_if_nonfinite=False):
        parameters = list(parameters)
        assert error_if_nonfinite is True
        parameters[0].grad.fill_(float("nan"))
        observed["called"] = True
        return original_clip(parameters, max_norm, error_if_nonfinite=error_if_nonfinite)

    monkeypatch.setattr(torch.nn.utils, "clip_grad_norm_", inject_nonfinite_gradient)
    with pytest.raises(RuntimeError, match="non-finite"):
        kinetic.fit_candidate(
            "independent", records[:5], records[5:8], 1e-3, 0.0, 17, protocol, torch.device("cpu"),
        )
    assert observed["called"] is True


def test_nonfinite_parameter_after_optimizer_step_fails_closed(tmp_path, monkeypatch):
    raw = write_raw(tmp_path / "synthetic.txt")
    records, _ = kinetic.parse_raw_matrix(raw)
    protocol = kinetic.load_protocol(FROZEN_PROTOCOL)
    protocol["training"]["batch_transcripts"] = 3
    protocol["training"]["successive_halving"]["rung_epochs"] = 2
    protocol["training"]["early_stopping"]["patience_epochs"] = 1
    original_step = torch.optim.AdamW.step

    def inject_nonfinite_parameter(optimizer, *args, **kwargs):
        result = original_step(optimizer, *args, **kwargs)
        with torch.no_grad():
            optimizer.param_groups[0]["params"][0].view(-1)[0] = float("inf")
        return result

    monkeypatch.setattr(torch.optim.AdamW, "step", inject_nonfinite_parameter)
    with pytest.raises(RuntimeError, match="nonfinite model parameter.*after optimizer step"):
        kinetic.fit_candidate(
            "position", records[:5], records[5:8], 1e-3, 0.0, 17, protocol, torch.device("cpu"),
        )


def test_synthetic_end_to_end_outer_test_cannot_change_its_fold_selection_or_curves(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(kinetic, "resolve_cuda_device", lambda name: torch.device("cpu"))
    first_raw = write_raw(tmp_path / "synthetic_first.txt")
    first_protocol = synthetic_protocol(tmp_path, first_raw)
    first_output = tmp_path / "first_output"
    first_summary = kinetic.run_experiment(first_protocol, first_raw, first_output)

    assert first_summary["schema"] == kinetic.SUMMARY_SCHEMA
    assert first_summary["status"] == "development_experiment_completed"
    assert first_summary["parameter_matching"]["per_inner_model"] == {"independent": 65, "position": 1, "kinetic": 65}
    assert first_summary["parameter_matching"]["per_selected_ensemble"] == {"independent": 195, "position": 3, "kinetic": 195}
    assert first_summary["comparisons"] == {
        "primary": "independent_minus_kinetic_tb_mse",
        "simple_position_control": "position_minus_kinetic_tb_mse",
    }
    assert first_summary["ensemble"]["mean_is_common_steady_state"] is False
    assert first_summary["selected_inner_states"]["selections"] == 27
    assert first_summary["selected_inner_states"]["members"] == 81
    assert first_summary["convergence"]["fits"] == 243
    assert first_summary["convergence"]["rung_fits"] == 243
    assert first_summary["convergence"]["resumed_fits"] == 162
    assert first_summary["convergence"]["validation_plateau"] == 162
    assert first_summary["convergence"]["rejected_at_rung_not_converged"] == 81
    assert first_summary["convergence"]["rung_rejection_is_not_convergence"] is True
    assert first_summary["convergence"]["selected_candidates_have_no_final_epoch_cap"] is True
    assert first_summary["cost"]["candidate_fits"] == 243
    assert first_summary["data"]["qc"]["eligible_transcripts"] == 9
    assert first_summary["scope"]["development_only"] is True
    assert first_summary["scope"]["final_research_ood"] is False
    for relative, digest in first_summary["sha256"]["artifacts"].items():
        assert sha256(first_output / relative) == digest

    with (first_output / "curves.jsonl").open(encoding="utf-8") as handle:
        curves = [json.loads(line) for line in handle]
    assert len(curves) == 243
    rejected_curves = [record for record in curves if not record["rung_selected"]]
    resumed_curves = [record for record in curves if record["rung_selected"]]
    assert len(rejected_curves) == 81
    assert len(resumed_curves) == 162
    assert all(len(record["epochs"]) == 2 for record in rejected_curves)
    assert all(record["stop_reason"] == "rejected_at_rung_not_converged" for record in rejected_curves)
    assert all(record["validation_plateau_converged"] is False for record in rejected_curves)
    assert all(record["resume"] is None for record in rejected_curves)
    assert all(len(record["epochs"]) >= 3 for record in resumed_curves)
    assert all(record["stop_reason"] == "validation_plateau" for record in resumed_curves)
    assert all(record["validation_plateau_converged"] is True for record in resumed_curves)
    assert all(record["resume"]["source_epoch"] == 2 for record in resumed_curves)
    assert all(record["resume"]["start_epoch"] == 3 for record in resumed_curves)
    assert all(
        record["resume"]["restored_model_state_sha256"] == record["rung"]["last_state_sha256"]
        for record in resumed_curves
    )
    assert all(record["resume"]["optimizer_state_restored"] for record in resumed_curves)
    assert all(record["resume"]["rng_state_restored"] for record in resumed_curves)
    selection = json.loads((first_output / "selection.json").read_text(encoding="utf-8"))
    assert selection["schema"] == kinetic.SELECTION_SCHEMA
    assert len(selection["records"]) == 27
    assert all(len(record["rung_selected_grid_indices"]) == 2 for record in selection["records"])
    assert all(record["selected_grid_index"] in record["rung_selected_grid_indices"] for record in selection["records"])
    assert all(len(record["candidates"]) == 3 for record in selection["records"])
    assert all(sum(candidate["rung_selected"] for candidate in record["candidates"]) == 2 for record in selection["records"])
    assert all(record["outer_test_used_for_selection"] is False for record in selection["records"])
    with (first_output / "per_transcript_metrics.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3 * 3 * 9
    assert {row["arm"] for row in rows} == set(kinetic.ARMS)
    assert all(
        effect in first_summary["metrics"][str(seed)]
        for seed in (11, 22, 33)
        for effect in ("independent_minus_kinetic_tb_mse", "position_minus_kinetic_tb_mse")
    )
    with np.load(first_output / "predictions.npz", allow_pickle=False) as predictions:
        assert predictions["arms"].tolist() == list(kinetic.ARMS)
        assert predictions["prediction"].shape[:3] == (3, 3, 9)
        valid = np.broadcast_to(predictions["mask"][None, None, :, :], predictions["prediction"].shape)
        assert np.all(np.isfinite(predictions["prediction"][valid]))
        kinetic_index = kinetic.ARMS.index("kinetic")
        assert np.isnan(predictions["flux"][:, :kinetic_index]).all()
        assert np.isfinite(predictions["flux"][:, kinetic_index]).all()
        assert np.nanmax(predictions["solver_max_abs_normalized_residual"][:, kinetic_index]) < 1e-8
        assert predictions["ensemble_mean_is_common_steady_state"].item() is False
        assert predictions["kinetic_conservation_level"].item() == "selected_inner_member_separately"
        assert "mean_normalized_residual" not in predictions.files

    first_records, _ = kinetic.parse_raw_matrix(first_raw)
    first_splits = kinetic.make_nested_splits(first_records, 9100301)
    first_protocol_payload = kinetic.load_protocol(first_protocol)
    state_path = first_output / "selected_inner_states.npz"
    with np.load(state_path, allow_pickle=False) as archive:
        state_metadata = json.loads(archive["metadata"].item())
    assert state_metadata["schema"] == kinetic.STATE_SCHEMA
    assert state_metadata["model_config"] == first_protocol_payload["model"]
    assert len(state_metadata["records"]) == 27
    assert {
        (record["seed"], record["outer_fold"], record["arm"])
        for record in state_metadata["records"]
    } == {
        (seed, outer, arm) for seed in (11, 22, 33) for outer in range(3) for arm in kinetic.ARMS
    }
    for record in state_metadata["records"]:
        assert len(record["members"]) == 3
        expected_fields = {"relative_position.weight"} if record["arm"] == "position" else {
            "relative_position.weight", "codon.weight",
        }
        assert all(set(member["state_keys"]) == expected_fields for member in record["members"])

    outer_test = [first_records[int(index)] for index in first_splits[0]["test"]]
    with np.load(first_output / "predictions.npz", allow_pickle=False) as saved_predictions:
        for arm_index, arm in enumerate(kinetic.ARMS):
            member_predictions = [
                kinetic.predict_from_saved_state(
                    state_path, 11, 0, arm, inner_fold, outer_test,
                    first_protocol_payload, torch.device("cpu"),
                )
                for inner_fold in range(3)
            ]
            for record in outer_test:
                rebuilt_mean = np.mean(
                    [prediction[record.index]["rho"] for prediction in member_predictions], axis=0,
                )
                np.testing.assert_allclose(
                    rebuilt_mean,
                    saved_predictions["prediction"][0, arm_index, record.index, :record.length],
                    rtol=0,
                    atol=1e-12,
                )

    changed_transcript = int(first_splits[0]["test"][0])
    second_raw = write_raw(tmp_path / "synthetic_changed_test.txt", altered=changed_transcript)
    second_protocol = synthetic_protocol(tmp_path, second_raw)
    second_output = tmp_path / "second_output"
    kinetic.run_experiment(second_protocol, second_raw, second_output)
    second_selection = json.loads((second_output / "selection.json").read_text(encoding="utf-8"))

    assert science_selection(second_selection) == science_selection(selection)
    assert science_curves(second_output / "curves.jsonl") == science_curves(first_output / "curves.jsonl")
    with np.load(first_output / "predictions.npz", allow_pickle=False) as before, np.load(
        second_output / "predictions.npz", allow_pickle=False,
    ) as after:
        assert not np.array_equal(
            before["target"][changed_transcript], after["target"][changed_transcript],
        )
        np.testing.assert_array_equal(
            before["prediction"][:, :, changed_transcript], after["prediction"][:, :, changed_transcript],
        )


def test_startup_hashes_are_recorded_before_raw_parsing_or_training(tmp_path, monkeypatch):
    monkeypatch.setattr(kinetic, "resolve_cuda_device", lambda name: torch.device("cpu"))
    raw = write_raw(tmp_path / "synthetic.txt")
    protocol = synthetic_protocol(tmp_path, raw)
    output = tmp_path / "startup_output"

    def assert_provenance_then_stop(*args):
        provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
        assert provenance["schema"] == kinetic.PROVENANCE_SCHEMA
        assert provenance["stage"] == "startup_before_device_probe_raw_parse_or_training"
        assert provenance["sha256"] == {
            "protocol": sha256(protocol),
            "implementation": sha256(kinetic.__file__),
            "mean_field_operator": sha256(kinetic_mean_field.__file__),
        }
        raise RuntimeError("raw parser reached after startup provenance")

    monkeypatch.setattr(kinetic, "parse_raw_matrix", assert_provenance_then_stop)
    with pytest.raises(RuntimeError, match="raw parser reached after startup provenance"):
        kinetic.run_experiment(protocol, raw, output)
    assert not (output / "curves.jsonl").exists()
    assert not (output / "summary.json").exists()


def test_existing_output_directory_is_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(kinetic, "resolve_cuda_device", lambda name: torch.device("cpu"))
    raw = write_raw(tmp_path / "synthetic.txt")
    protocol = synthetic_protocol(tmp_path, raw)
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_bytes(b"keep-original")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        kinetic.run_experiment(protocol, raw, output)
    assert sentinel.read_bytes() == b"keep-original"
    assert not (output / "summary.json").exists()
