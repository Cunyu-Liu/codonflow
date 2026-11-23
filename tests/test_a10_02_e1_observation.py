import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from scripts import a10_02_e1_observation as observation


ROOT = Path(__file__).resolve().parents[1]
FROZEN_PROTOCOL = ROOT / "configs" / "a10_02_e1_observation_protocol_v1.json"
EXPECTED_HASHES = {
    1234: "dc3f06a2df0114f3bf02ccad37018e9d1c0654b0e87ebed1bd9292cd14edcfc8",
    2345: "896489c8774216b7667dd7a203f6219f2aa8a1bcc777f02bc838638e0c1048ef",
    3456: "79d35876312778d6497db1cf085496e8ef9de326605b39707674e3f8baf5ce31",
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_synthetic_npz(path, seed, n_transcripts=16):
    rng = np.random.default_rng(seed)
    lengths = np.asarray([2 + index % 5 for index in range(n_transcripts)])
    offsets = np.concatenate(([0], np.cumsum(lengths))).astype(np.int64)
    target = rng.normal(size=int(offsets[-1])) + np.repeat(
        np.linspace(-2.0, 2.0, n_transcripts), lengths,
    )
    raw_unanchored = 2.25 * target + 1.25
    raw_anchored = 0.5 * target - 1.5
    arrays = {
        "offsets": offsets,
        "positions": np.arange(len(target), dtype=np.int64) % 31,
        "target": target,
        "prediction_position_raw_unanchored": raw_unanchored,
        "prediction_position_raw_anchored": raw_anchored,
        "prediction_constant": np.full(len(target), np.mean(target)),
    }
    with Path(path).open("wb") as handle:
        np.savez(handle, **arrays)
    return arrays


def write_protocol(tmp_path, inputs, n_transcripts=16, n_bootstrap=1000, n_signflip=1000):
    protocol = json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))
    protocol["inputs"]["expected_transcripts"] = n_transcripts
    protocol["inputs"]["expected_offsets_length"] = n_transcripts + 1
    protocol["inputs"]["seeds"] = [
        {"seed": seed, "sha256": sha256(path)} for seed, path in sorted(inputs.items())
    ]
    protocol["split"]["calibration_count"] = n_transcripts // 2
    protocol["split"]["test_count"] = n_transcripts - n_transcripts // 2
    protocol["inference"]["bootstrap"]["n_resamples"] = n_bootstrap
    protocol["inference"]["signflip"]["n_resamples"] = n_signflip
    path = tmp_path / "synthetic_protocol.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")
    return path


def synthetic_case(tmp_path, seeds=(1234,), n_transcripts=16, n_bootstrap=1000, n_signflip=1000):
    inputs = {}
    for seed in seeds:
        path = tmp_path / f"synthetic_{seed}.npz"
        write_synthetic_npz(path, seed, n_transcripts)
        inputs[seed] = path
    protocol = write_protocol(
        tmp_path, inputs, n_transcripts, n_bootstrap, n_signflip,
    )
    return inputs, protocol, tmp_path / "outputs"


def test_frozen_protocol_pins_three_inputs_inference_and_claim_boundaries():
    protocol = observation.load_protocol(FROZEN_PROTOCOL)
    assert protocol["inputs"]["expected_transcripts"] == 3921
    assert protocol["inputs"]["expected_offsets_length"] == 3922
    assert {
        item["seed"]: item["sha256"] for item in protocol["inputs"]["seeds"]
    } == EXPECTED_HASHES
    assert protocol["split"]["calibration_count"] == 1960
    assert protocol["split"]["test_count"] == 1961
    assert protocol["split"]["shared_across_model_seeds"] is True
    assert protocol["observation_model"]["fit_split"] == "calibration_only"
    assert protocol["observation_model"]["transcript_point_weight"] == "1 / n_i"
    assert protocol["inference"]["bootstrap"]["n_resamples"] == 20000
    assert protocol["inference"]["signflip"]["n_resamples"] == 20000
    assert protocol["evaluation"]["co_primary_endpoints"] == list(observation.ENDPOINTS)
    assert protocol["evaluation"]["correlation_gain_claim_allowed"] is False
    assert protocol["scope"]["studies"] == {
        "Mohammad": "development_only",
        "Subtelny": "development_only",
    }
    assert protocol["scope"]["untouched"] is False
    assert protocol["scope"]["absolute_elongation_rates"] is False
    assert protocol["scope"]["cross_study_final_confirmation"] is False
    assert protocol["scope"]["sota_claim"] is False
    assert protocol["outputs"]["overwrite"] == "forbidden"


def test_affine_fit_recovers_map_and_enforces_nonnegative_slope():
    transcript_ids = np.asarray([0, 0, 1, 1, 2, 2])
    x = np.asarray([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    fitted = observation.fit_affine(x, 1.7 + 2.4 * x, transcript_ids)
    assert fitted["a"] == pytest.approx(1.7)
    assert fitted["b"] == pytest.approx(2.4)
    assert fitted["n_transcripts"] == 3
    assert fitted["sum_transcript_weights"] == pytest.approx(3.0)

    negative = observation.fit_affine(x, 4.0 - 3.0 * x, transcript_ids)
    assert negative["b"] == 0.0
    assert negative["a"] == pytest.approx(np.mean(4.0 - 3.0 * x))


def test_fit_and_tb_mse_are_transcript_balanced_not_position_weighted():
    fitted = observation.fit_affine(
        np.zeros(4), np.asarray([0.0, 0.0, 0.0, 3.0]), np.asarray([0, 0, 0, 1]),
    )
    assert fitted["b"] == 0.0
    assert fitted["a"] == pytest.approx(1.5)

    data = {
        "offsets": np.asarray([0, 1, 4]),
        "target": np.zeros(4),
    }
    predictions = {
        "raw_unanchored": np.asarray([0.0, 1.0, 1.0, 1.0]),
        "raw_anchored": np.zeros(4),
        "constant": np.zeros(4),
        "calibrated_unanchored": np.zeros(4),
        "calibrated_anchored": np.zeros(4),
    }
    records = observation.per_transcript_metrics(data, predictions, [0, 1])
    metrics = observation.summarize_metrics(records, list(predictions))
    assert metrics["tb_mse"]["raw_unanchored"] == pytest.approx(0.5)
    assert np.mean(predictions["raw_unanchored"] ** 2) == pytest.approx(0.75)


def test_split_is_deterministic_exact_and_transcript_disjoint():
    first = observation.deterministic_split(3921, 9100201)
    second = observation.deterministic_split(3921, 9100201)
    assert np.array_equal(first[0], second[0])
    assert np.array_equal(first[1], second[1])
    assert len(first[0]) == 1960
    assert len(first[1]) == 1961
    assert not np.intersect1d(*first).size
    combined = np.sort(np.concatenate(first))
    assert np.array_equal(combined, np.arange(3921))


def test_three_seed_synthetic_cli_outputs_raw_points_and_passes_frozen_rule(tmp_path):
    inputs, protocol, output = synthetic_case(
        tmp_path, seeds=(1234, 2345, 3456), n_bootstrap=20000, n_signflip=20000,
    )
    args = ["--protocol", str(protocol), "--output-dir", str(output)]
    for seed, path in sorted(inputs.items()):
        args.extend(["--input", f"{seed}={path}"])

    assert observation.main(args) == 0

    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["h1_development_positive"] is True
    assert summary["status"] == "h1_development_positive"
    assert set(summary["seeds"]) == {"1234", "2345", "3456"}
    assert all(item["same_nonzero_sign"] for item in summary["across_seeds"].values())
    assert summary["environment"]["numpy"] == np.__version__
    assert summary["environment"]["scipy"]
    assert summary["cost"]["wall_clock_seconds"] >= 0.0
    for relative, digest in summary["sha256"]["artifacts"].items():
        assert sha256(output / relative) == digest

    for seed in inputs:
        result = json.loads((output / f"seed_{seed}" / "result.json").read_text())
        assert result["split"]["test_targets_used_for_fitting"] is False
        assert result["test"]["all_co_primary_pass"] is True
        for endpoint in observation.ENDPOINTS:
            endpoint_result = result["test"]["endpoints"][endpoint]
            assert endpoint_result["n_bootstrap"] == 20000
            assert endpoint_result["n_signflip"] == 20000
            assert endpoint_result["effect"] > 0.0
            assert endpoint_result["bootstrap_95ci"][0] > 0.0
            assert endpoint_result["holm_p"] < 0.05
        for mapping in ("unanchored", "anchored"):
            invariance = result["test"]["correlation_invariance"][mapping]
            assert invariance["passed"] is True
            assert invariance["pearson_max_abs_difference"] < 1e-12
            assert invariance["spearman_max_abs_difference"] < 1e-12
            assert invariance["gain_claim_allowed"] is False
        assert result["calibration"]["parameters"]["raw_unanchored"]["b"] == pytest.approx(1 / 2.25)
        assert result["calibration"]["parameters"]["raw_anchored"]["b"] == pytest.approx(2.0)

        with np.load(output / f"seed_{seed}" / "test_points.npz", allow_pickle=False) as points:
            test_indices = points["transcript_indices"]
            offsets = points["offsets"]
            recomputed = {endpoint: [] for endpoint in observation.ENDPOINTS}
            for index, transcript_index in enumerate(test_indices):
                start, stop = offsets[index:index + 2]
                target = points["target"][start:stop]
                for endpoint, raw_name, calibrated_name, parameter_name in (
                    (
                        observation.ENDPOINTS[0], "raw_unanchored", "calibrated_unanchored",
                        "raw_unanchored",
                    ),
                    (
                        observation.ENDPOINTS[1], "raw_anchored", "calibrated_anchored",
                        "raw_anchored",
                    ),
                ):
                    raw = points[raw_name][start:stop]
                    calibrated = points[calibrated_name][start:stop]
                    parameters = result["calibration"]["parameters"][parameter_name]
                    assert np.allclose(calibrated, parameters["a"] + parameters["b"] * raw)
                    recomputed[endpoint].append(
                        np.mean((target - raw) ** 2) - np.mean((target - calibrated) ** 2)
                    )
            for endpoint in observation.ENDPOINTS:
                assert np.mean(recomputed[endpoint]) == pytest.approx(
                    result["test"]["endpoints"][endpoint]["effect"]
                )
        with np.load(
            output / f"seed_{seed}" / "calibration_points.npz", allow_pickle=False,
        ) as points:
            assert len(points["transcript_indices"]) == 8
            assert not np.intersect1d(points["transcript_indices"], test_indices).size
        with (output / f"seed_{seed}" / "test_transcript_effects.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 8
        assert {int(row["transcript_index"]) for row in rows} == set(test_indices.tolist())


def test_changing_only_test_targets_cannot_change_calibration(tmp_path):
    inputs, protocol, first_output = synthetic_case(
        tmp_path, n_transcripts=12, n_bootstrap=100, n_signflip=100,
    )
    observation.run_analysis(protocol, inputs, first_output)
    first = json.loads((first_output / "seed_1234" / "result.json").read_text())
    test_indices = np.asarray(first["split"]["test_transcript_indices"])

    source = inputs[1234]
    with np.load(source, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    offsets = arrays["offsets"]
    point_transcript = np.repeat(np.arange(12), np.diff(offsets))
    mask = np.isin(point_transcript, test_indices)
    arrays["target"][mask] += 1000.0
    changed = tmp_path / "synthetic_1234_changed_test_only.npz"
    with changed.open("wb") as handle:
        np.savez(handle, **arrays)
    changed_protocol = write_protocol(
        tmp_path, {1234: changed}, 12, 100, 100,
    )
    second_output = tmp_path / "changed_outputs"
    observation.run_analysis(changed_protocol, {1234: changed}, second_output)
    second = json.loads((second_output / "seed_1234" / "result.json").read_text())

    assert second["split"] == first["split"]
    assert second["calibration"]["parameters"] == first["calibration"]["parameters"]
    assert second["calibration"]["metrics"] == first["calibration"]["metrics"]
    assert second["test"]["metrics"] != first["test"]["metrics"]


def test_paired_inference_is_reproducible_and_holm_controls_family():
    effects = np.asarray([1.0, 2.0, 3.0, 4.0])
    first = observation.paired_transcript_inference(effects, 20000, 20000, 77, batch_size=7)
    second = observation.paired_transcript_inference(effects, 20000, 20000, 77, batch_size=7)
    assert first == second
    assert first["effect"] == pytest.approx(2.5)
    assert first["bootstrap_95ci"][0] > 0.0
    assert 0.10 < first["signflip_p_two_sided"] < 0.15
    assert observation.holm_adjust([0.01, 0.02, 0.03]) == [0.03, 0.04, 0.04]


def test_existing_output_directory_is_never_overwritten(tmp_path):
    inputs, protocol, output = synthetic_case(tmp_path, n_bootstrap=10, n_signflip=10)
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_bytes(b"keep-original")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        observation.run_analysis(protocol, inputs, output)

    assert sentinel.read_bytes() == b"keep-original"
    assert not (output / "summary.json").exists()


def test_input_sha_mismatch_fails_before_output_creation(tmp_path):
    inputs, protocol, output = synthetic_case(tmp_path, n_bootstrap=10, n_signflip=10)
    with inputs[1234].open("ab") as handle:
        handle.write(b"hash mismatch")

    with pytest.raises(ValueError, match="NPZ SHA256 mismatch"):
        observation.run_analysis(protocol, inputs, output)

    assert not output.exists()
