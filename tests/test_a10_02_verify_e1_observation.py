import ast
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from scripts import a10_02_e1_observation as production
from scripts import a10_02_verify_e1_observation as verifier


ROOT = Path(__file__).resolve().parents[1]
FROZEN_PROTOCOL = ROOT / "configs" / "a10_02_e1_observation_protocol_v1.json"
SEEDS = (1234, 2345, 3456)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_synthetic_npz(path, seed, n_transcripts=16):
    rng = np.random.default_rng(seed)
    lengths = 2 + np.arange(n_transcripts) % 5
    offsets = np.concatenate([[0], np.cumsum(lengths)]).astype(np.int64)
    target = rng.normal(size=int(offsets[-1])) + np.repeat(
        np.linspace(-2, 2, n_transcripts), lengths,
    )
    arrays = {
        "offsets": offsets,
        "positions": np.arange(len(target), dtype=np.int64) % 31,
        "target": target,
        "prediction_position_raw_unanchored": 2.25 * target + 1.25,
        "prediction_position_raw_anchored": 0.5 * target - 1.5,
        "prediction_constant": np.full(len(target), np.mean(target)),
    }
    with path.open("wb") as handle:
        np.savez(handle, **arrays)
    return arrays


def make_case(tmp_path, resamples=64, n_transcripts=16):
    tmp_path.mkdir(parents=True, exist_ok=True)
    inputs = {}
    for seed in SEEDS:
        path = tmp_path / f"synthetic_rk37_{seed}.npz"
        write_synthetic_npz(path, seed, n_transcripts)
        inputs[seed] = path
    protocol = json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))
    protocol["inputs"]["expected_transcripts"] = n_transcripts
    protocol["inputs"]["expected_offsets_length"] = n_transcripts + 1
    protocol["inputs"]["seeds"] = [
        {"seed": seed, "sha256": sha256(path)} for seed, path in sorted(inputs.items())
    ]
    protocol["split"]["calibration_count"] = n_transcripts // 2
    protocol["split"]["test_count"] = n_transcripts - n_transcripts // 2
    protocol["inference"]["bootstrap"]["n_resamples"] = resamples
    protocol["inference"]["signflip"]["n_resamples"] = resamples
    protocol_path = tmp_path / "synthetic_protocol.json"
    write_json(protocol_path, protocol)
    output_dir = tmp_path / "production_outputs"
    production.run_analysis(protocol_path, inputs, output_dir)
    return {
        "inputs": inputs, "protocol": protocol_path, "output": output_dir,
        "resamples": resamples, "n_transcripts": n_transcripts,
    }


def verify(case):
    return verifier.verify_e1_observation(
        case["protocol"], case["inputs"], case["output"], allow_synthetic_protocol=True,
    )


def load_summary(case):
    return json.loads((case["output"] / "summary.json").read_text(encoding="utf-8"))


def save_summary(case, summary):
    write_json(case["output"] / "summary.json", summary)


def load_result(case, seed):
    return json.loads((case["output"] / f"seed_{seed}" / "result.json").read_text(encoding="utf-8"))


def update_artifact_sha(case, relative):
    summary = load_summary(case)
    summary["sha256"]["artifacts"][relative] = sha256(case["output"] / relative)
    save_summary(case, summary)


def save_result(case, seed, result, refresh_sha=True):
    relative = f"seed_{seed}/result.json"
    write_json(case["output"] / relative, result)
    if refresh_sha:
        update_artifact_sha(case, relative)


def rewrite_npz(case, seed, name, arrays):
    relative = f"seed_{seed}/{name}"
    with (case["output"] / relative).open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    update_artifact_sha(case, relative)


def read_npz(case, seed, name):
    with np.load(case["output"] / f"seed_{seed}" / name, allow_pickle=False) as archive:
        return {key: archive[key].copy() for key in archive.files}


def test_frozen_identity_and_verifier_has_no_production_imports():
    protocol = verifier.load_protocol(FROZEN_PROTOCOL)
    assert protocol["inputs"]["expected_transcripts"] == 3921
    assert protocol["inputs"]["expected_offsets_length"] == 3922
    assert {item["seed"]: item["sha256"] for item in protocol["inputs"]["seeds"]} == {
        1234: "dc3f06a2df0114f3bf02ccad37018e9d1c0654b0e87ebed1bd9292cd14edcfc8",
        2345: "896489c8774216b7667dd7a203f6219f2aa8a1bcc777f02bc838638e0c1048ef",
        3456: "79d35876312778d6497db1cf085496e8ef9de326605b39707674e3f8baf5ce31",
    }
    assert protocol["split"]["seed"] == 9100201
    assert protocol["split"]["calibration_count"] == 1960
    assert protocol["split"]["test_count"] == 1961
    assert protocol["inference"]["seed"] == 9100202
    assert protocol["inference"]["bootstrap"]["n_resamples"] == 20000
    assert protocol["inference"]["signflip"]["n_resamples"] == 20000
    tree = ast.parse(Path(verifier.__file__).read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(name == "codonflow" or name.startswith(("codonflow.", "scripts.")) for name in imported)


def test_synthetic_production_outputs_full_20000_independent_recomputation_passes(tmp_path):
    case = make_case(tmp_path, resamples=20000)
    result = verify(case)
    assert result["passed"], result["mismatches"]
    assert all(result["checks"].values())
    assert result["recomputed"]["h1_development_positive"] is True
    assert len(result["checks"]) == 36
    for seed in SEEDS:
        report = load_result(case, seed)
        assert report["split"]["calibration_count"] == 8
        assert report["split"]["test_count"] == 8
        assert report["calibration"]["parameters"]["raw_unanchored"]["b"] == pytest.approx(1 / 2.25)
        assert report["calibration"]["parameters"]["raw_anchored"]["b"] == pytest.approx(2.0)
        for endpoint in verifier.ENDPOINTS:
            endpoint_result = report["test"]["endpoints"][endpoint]
            assert endpoint_result["n_bootstrap"] == 20000
            assert endpoint_result["n_signflip"] == 20000
            assert endpoint_result["effect"] > 0
            assert endpoint_result["bootstrap_95ci"][0] > 0
            assert endpoint_result["holm_p"] < 0.05
        for invariance in report["test"]["correlation_invariance"].values():
            assert invariance["passed"] is True
            assert invariance["gain_claim_allowed"] is False


def test_calibration_split_and_test_target_leakage_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    report = load_result(case, 1234)
    report["split"]["calibration_transcript_indices"] = list(range(case["n_transcripts"]))
    report["split"]["calibration_count"] = case["n_transcripts"]
    report["split"]["test_targets_used_for_fitting"] = True
    save_result(case, 1234, report)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["result_1234_values"]
    assert any("split" in item for item in result["mismatches"]["result_1234"])
    assert result["checks"]["summary_sha256"]


@pytest.mark.parametrize("raw_name,field", [
    ("raw_unanchored", "a"), ("raw_unanchored", "b"),
    ("raw_anchored", "a"), ("raw_anchored", "sum_transcript_weights"),
])
def test_calibration_parameter_tampering_is_detected(tmp_path, raw_name, field):
    case = make_case(tmp_path)
    report = load_result(case, 2345)
    report["calibration"]["parameters"][raw_name][field] += 0.1
    save_result(case, 2345, report)
    result = verify(case)
    assert not result["checks"]["result_2345_values"]
    assert "calibration.parameters" in result["mismatches"]["result_2345"][0]


def test_calibration_points_and_transcript_membership_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    points = read_npz(case, 1234, "calibration_points.npz")
    test_indices = read_npz(case, 1234, "test_points.npz")["transcript_indices"]
    points["transcript_indices"][0] = test_indices[0]
    rewrite_npz(case, 1234, "calibration_points.npz", points)
    result = verify(case)
    assert result["checks"]["summary_sha256"]
    assert not result["checks"]["calibration_points.npz_1234_values"]
    assert "transcript_indices" in result["mismatches"]["calibration_points.npz_1234"]


@pytest.mark.parametrize("name", ["calibrated_unanchored", "calibrated_anchored", "target"])
def test_test_point_prediction_tampering_is_detected_even_with_updated_sha(tmp_path, name):
    case = make_case(tmp_path)
    points = read_npz(case, 3456, "test_points.npz")
    points[name][0] += 0.5
    rewrite_npz(case, 3456, "test_points.npz", points)
    result = verify(case)
    assert result["checks"]["summary_sha256"]
    assert not result["checks"]["test_points.npz_3456_values"]
    assert name in result["mismatches"]["test_points.npz_3456"]


@pytest.mark.parametrize("field", ["effect_unanchored", "mse_calibrated_anchored", "pearson_raw_unanchored"])
def test_per_transcript_csv_tampering_is_detected(tmp_path, field):
    case = make_case(tmp_path)
    path = case["output"] / "seed_1234" / "test_transcript_effects.csv"
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    rows[0][field] = str(float(rows[0][field]) + 0.25)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    update_artifact_sha(case, "seed_1234/test_transcript_effects.csv")
    result = verify(case)
    assert result["checks"]["summary_sha256"]
    assert not result["checks"]["test_transcript_effects_1234_values"]
    assert field in result["mismatches"]["test_transcript_effects_1234"][0]


@pytest.mark.parametrize("field", ["effect", "signflip_p_two_sided", "holm_p", "passes"])
def test_result_statistical_tampering_is_detected(tmp_path, field):
    case = make_case(tmp_path)
    report = load_result(case, 1234)
    endpoint = report["test"]["endpoints"][verifier.ENDPOINTS[0]]
    endpoint[field] = not endpoint[field] if isinstance(endpoint[field], bool) else endpoint[field] + 0.01
    save_result(case, 1234, report)
    result = verify(case)
    assert not result["checks"]["result_1234_values"]
    assert verifier.ENDPOINTS[0] in result["mismatches"]["result_1234"][0]


def test_bootstrap_ci_correlation_invariance_and_seed_gate_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    report = load_result(case, 2345)
    report["test"]["endpoints"][verifier.ENDPOINTS[0]]["bootstrap_95ci"][0] += 0.01
    report["test"]["correlation_invariance"]["unanchored"]["passed"] = False
    report["test"]["all_co_primary_pass"] = not report["test"]["all_co_primary_pass"]
    save_result(case, 2345, report)
    result = verify(case)
    assert not result["checks"]["result_2345_values"]
    assert result["checks"]["correlation_invariance_2345"]


def test_summary_statistics_holm_and_three_seed_gate_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    summary = load_summary(case)
    summary["seeds"]["1234"]["endpoints"][verifier.ENDPOINTS[0]]["holm_p"] += 0.01
    summary["across_seeds"][verifier.ENDPOINTS[0]]["same_nonzero_sign"] = False
    summary["h1_development_positive"] = not summary["h1_development_positive"]
    summary["status"] = (
        "h1_development_not_positive" if summary["status"] == "h1_development_positive"
        else "h1_development_positive"
    )
    save_summary(case, summary)
    result = verify(case)
    assert not result["checks"]["summary_seeds"]
    assert not result["checks"]["summary_across_seeds"]
    assert not result["checks"]["summary_h1_development_positive"]
    assert not result["checks"]["summary_status"]


def test_input_and_artifact_sha_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    summary = load_summary(case)
    summary["sha256"]["artifacts"]["seed_1234/test_points.npz"] = "0" * 64
    summary["sha256"]["input_files"]["1234"] = "1" * 64
    save_summary(case, summary)
    result = verify(case)
    assert not result["checks"]["summary_sha256"]
    assert result["checks"]["input_1234_sha256"]

    case = make_case(tmp_path / "changed-input")
    arrays = write_synthetic_npz(case["inputs"][1234], 999)
    arrays["target"][0] += 1
    with case["inputs"][1234].open("wb") as handle:
        np.savez(handle, **arrays)
    result = verify(case)
    assert not result["checks"]["input_1234_sha256"]
    assert not result["checks"]["result_1234_values"]


def test_scope_cost_environment_and_unexpected_output_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    summary = load_summary(case)
    summary["scope"]["untouched"] = True
    summary["scope"]["sota_claim"] = True
    summary["cost"]["wall_clock_seconds"] = -1
    summary["environment"]["numpy"] = ""
    save_summary(case, summary)
    report = load_result(case, 1234)
    report["cost"]["wall_clock_seconds"] = -0.5
    save_result(case, 1234, report)
    (case["output"] / "unexpected.json").write_text("{}")
    result = verify(case)
    assert not result["checks"]["summary_scope"]
    assert not result["checks"]["summary_cost"]
    assert not result["checks"]["summary_environment"]
    assert not result["checks"]["result_1234_cost"]
    assert not result["checks"]["output_files_exact"]


def cli_arguments(case, output):
    arguments = ["--protocol", str(case["protocol"])]
    for seed, path in sorted(case["inputs"].items()):
        arguments.extend(["--input", f"{seed}={path}"])
    return arguments + ["--output-dir", str(case["output"]), "--output", str(output)]


def test_main_synthetic_success_and_exclusive_overwrite(tmp_path, monkeypatch):
    case = make_case(tmp_path)
    original = verifier.verify_e1_observation
    monkeypatch.setattr(
        verifier, "verify_e1_observation",
        lambda protocol, inputs, output_dir: original(
            protocol, inputs, output_dir, allow_synthetic_protocol=True,
        ),
    )
    output = tmp_path / "nested" / "verification.json"
    assert verifier.main(cli_arguments(case, output)) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"]
    assert payload["summary_sha256"] == sha256(case["output"] / "summary.json")
    original_bytes = output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        verifier.main(cli_arguments(case, output))
    assert output.read_bytes() == original_bytes


def test_main_synthetic_tampering_returns_nonzero_and_preserves_failure_output(tmp_path, monkeypatch):
    case = make_case(tmp_path)
    report = load_result(case, 1234)
    report["calibration"]["parameters"]["raw_unanchored"]["a"] += 1
    save_result(case, 1234, report)
    original = verifier.verify_e1_observation
    monkeypatch.setattr(
        verifier, "verify_e1_observation",
        lambda protocol, inputs, output_dir: original(
            protocol, inputs, output_dir, allow_synthetic_protocol=True,
        ),
    )
    output = tmp_path / "failed.json"
    assert verifier.main(cli_arguments(case, output)) == 1
    assert not json.loads(output.read_text(encoding="utf-8"))["passed"]
    original_bytes = output.read_bytes()
    with pytest.raises(FileExistsError):
        verifier.main(cli_arguments(case, output))
    assert output.read_bytes() == original_bytes
