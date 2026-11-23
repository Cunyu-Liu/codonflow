import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import a10_01_g0_closeout as production
from scripts import a10_01_verify_g0_closeout as verifier


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "a10_01_verify_g0_closeout.py"
FROZEN_PROTOCOL = ROOT / "configs" / "a10_01_g0_closeout_protocol_v1.json"
HISTORICAL_REPORT_IDS = verifier.REQUIRED_REPORT_IDS[8:]
LIST_CHECK_REPORT_IDS = HISTORICAL_REPORT_IDS[:-1]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def set_pointer(payload, pointer, value):
    parts = pointer.lstrip("/").split("/")
    target = payload
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = copy.deepcopy(value)


def synthetic_report(spec):
    report = {}
    for pointer, value in spec["expected"].items():
        set_pointer(report, pointer, value)
    if spec["passed_required"]:
        report["passed"] = True
    if spec["status_required"]:
        report["status"] = spec["accepted_statuses"][0]
    if spec["checks_required"]:
        report["checks"] = {name: True for name in spec["required_checks"]} or {
            "execution_verified": True
        }
    return report


def save_protocol(case):
    write_json(case.protocol_path, case.protocol)


def save_report(case, report_id, refresh_hash=True):
    write_json(case.report_paths[report_id], case.reports[report_id])
    if refresh_hash:
        case.specs[report_id]["sha256"] = sha256(case.report_paths[report_id])
        save_protocol(case)


def verify(case, expected_sha256=...):
    if expected_sha256 is ...:
        expected_sha256 = sha256(case.closeout_path)
    return verifier.verify_g0_closeout(
        case.protocol_path,
        case.report_root,
        case.closeout_path,
        synthetic=True,
        expected_closeout_sha256=expected_sha256,
    )


def arguments(case, output, expected_sha256=...):
    if expected_sha256 is ...:
        expected_sha256 = sha256(case.closeout_path)
    return [
        "--protocol", str(case.protocol_path),
        "--report-root", str(case.report_root),
        "--closeout", str(case.closeout_path),
        "--closeout-sha256", expected_sha256,
        "--output", str(output),
        "--synthetic",
    ]


@pytest.fixture
def synthetic_case(tmp_path):
    protocol = read_json(FROZEN_PROTOCOL)
    report_root = tmp_path / "synthetic_reports"
    report_root.mkdir()
    case = SimpleNamespace(
        root=tmp_path,
        protocol=protocol,
        protocol_path=tmp_path / "synthetic_protocol.json",
        report_root=report_root,
        specs={spec["id"]: spec for spec in protocol["reports"]},
        reports={},
        report_paths={},
        closeout_path=tmp_path / "closeout.json",
    )
    for report_id in HISTORICAL_REPORT_IDS:
        case.specs[report_id]["passed_required"] = False
        case.specs[report_id]["required_checks"] = ["execution_verified"]
    for report_id, spec in case.specs.items():
        path = report_root / spec["relative_path"]
        case.report_paths[report_id] = path
        case.reports[report_id] = synthetic_report(spec)
        if report_id in LIST_CHECK_REPORT_IDS:
            checks = case.reports[report_id]["checks"]
            case.reports[report_id]["checks"] = [
                {"name": name, "pass" if index % 2 == 0 else "passed": True}
                for index, name in enumerate(checks)
            ]
        save_report(case, report_id)
    closeout = production.run_closeout(case.protocol_path, case.report_root, synthetic=True)
    assert closeout["passed"] is True
    write_json(case.closeout_path, closeout)
    case.closeout = closeout
    return case


def test_verifier_does_not_import_production_modules():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden = {"scripts", "codonflow", "torch", "transformers", "importlib"}
    assert not any(
        module == name or module.startswith(f"{name}.")
        for module in imported for name in forbidden
    )


def test_frozen_registry_hashes_versions_and_remote_roots_are_enforced():
    protocol = verifier.load_protocol(FROZEN_PROTOCOL)
    specs = {spec["id"]: spec for spec in protocol["reports"]}
    assert verifier.EXPECTED_REPORT_SHA256 == production.EXPECTED_REPORT_SHA256
    assert len(specs) == 15
    assert set(specs) == set(verifier.EXPECTED_REPORT_SHA256)
    assert specs["goodman_split_independent_v3"]["expected"]["/protocol"] == (
        "a10_01_goodman_nested_grouped_cv_independent_verification_v2"
    )
    assert specs["goodman_baseline_independent_v2"]["expected"]["/protocol"] == (
        "a10_01_goodman_baseline_independent_verification_v1"
    )
    assert all(specs[report_id]["passed_required"] is False for report_id in HISTORICAL_REPORT_IDS)
    assert all(
        specs[report_id]["passed_required"] is True
        for report_id in verifier.TOP_LEVEL_PASSED_REQUIRED_IDS
    )
    for report_id, spec in specs.items():
        if report_id in verifier.A10_REPORT_IDS:
            assert spec["absolute_path"].startswith("/teams/")
            assert "/codonflow1031/a10/e0/" in spec["absolute_path"]
        else:
            assert spec["absolute_path"].startswith(verifier.HISTORICAL_ROOT + "/")


def test_synthetic_closeout_passes_through_cli(synthetic_case):
    output = synthetic_case.root / "verification.json"

    returncode = verifier.main(arguments(synthetic_case, output))

    assert returncode == 0
    result = read_json(output)
    assert result["passed"] is True
    assert result["gate"] == verifier.PASS_TOKEN
    assert result["E1_start_allowed"] is True
    assert result["E2_start_allowed"] is True
    assert result["SOTA"] is False
    assert result["generation_training_allowed"] is False
    assert len(result["reports"]) == 15
    assert all(result["checks"].values())
    assert result["closeout_sha256"] == sha256(synthetic_case.closeout_path)
    assert result["closeout_sha256_pinned"] is True
    historical = {
        record["id"]: record for record in result["reports"]
        if record["id"] in HISTORICAL_REPORT_IDS
    }
    assert len(historical) == 7
    assert all(record["passed_present"] is False for record in historical.values())
    assert all(record["passed_ok"] is True for record in historical.values())
    assert all(record["status_ok"] is True for record in historical.values())
    assert all(record["checks_ok"] is True for record in historical.values())
    assert all(record["required_checks_ok"] is True for record in historical.values())
    assert all(isinstance(record["checks"], dict) for record in historical.values())
    assert all(
        isinstance(synthetic_case.reports[report_id]["checks"], list)
        for report_id in LIST_CHECK_REPORT_IDS
    )
    assert isinstance(synthetic_case.reports["rnarl_negative_availability"]["checks"], dict)


def test_forged_pass_cannot_hide_failed_report_checks(synthetic_case):
    report_id = "goodman_baseline_independent_v2"
    synthetic_case.reports[report_id]["checks"]["outer_test_isolation"] = False
    synthetic_case.reports[report_id]["passed"] = True
    save_report(synthetic_case, report_id)

    result = verify(synthetic_case)

    assert result["passed"] is False
    assert result["checks"]["all_report_hashes"] is True
    assert result["checks"]["all_report_checks"] is False
    assert result["checks"]["direct_baseline_real_execution"] is False
    assert result["checks"]["closeout_protocol_sha256"] is False
    assert result["checks"]["closeout_reports"] is False
    assert result["checks"]["closeout_checks"] is False
    assert result["checks"]["closeout_verdict"] is False
    assert result["independent_closeout"]["expected_gate"] == verifier.FAIL_TOKEN
    assert result["independent_closeout"]["declared_gate"] == verifier.PASS_TOKEN


def test_missing_report_is_not_skipped(synthetic_case):
    report_id = "tunney_e0_independent"
    synthetic_case.report_paths[report_id].unlink()

    result = verify(synthetic_case)

    record = next(item for item in result["reports"] if item["id"] == report_id)
    assert result["passed"] is False
    assert record["report_ok"] is False
    assert record["hash_ok"] is False
    assert result["checks"]["development_ribo_and_tunney_candidates"] is False
    assert result["checks"]["closeout_verdict"] is False


def test_report_content_tampering_fails_hash_and_semantics(synthetic_case):
    report_id = "goodman_e0_v3_report"
    synthetic_case.reports[report_id]["raw_csv"]["data_rows"] = 1
    save_report(synthetic_case, report_id, refresh_hash=False)

    result = verify(synthetic_case)

    record = next(item for item in result["reports"] if item["id"] == report_id)
    assert result["passed"] is False
    assert record["hash_ok"] is False
    assert record["semantic_ok"] is False
    assert result["checks"]["all_report_hashes"] is False
    assert result["checks"]["real_functional_raw_and_qc"] is False


def test_non_boolean_check_is_rejected(synthetic_case):
    report_id = "goodman_split_independent_v3"
    synthetic_case.reports[report_id]["checks"]["outer_gene_isolation"] = 1
    save_report(synthetic_case, report_id)

    result = verify(synthetic_case)

    assert result["passed"] is False
    assert result["checks"]["all_report_checks"] is False
    assert result["checks"]["no_leak_nested_split"] is False


def test_new_a10_independent_report_without_top_level_passed_is_rejected(synthetic_case):
    report_id = "goodman_baseline_independent_v2"
    del synthetic_case.reports[report_id]["passed"]
    save_report(synthetic_case, report_id)

    result = verify(synthetic_case)

    record = next(item for item in result["reports"] if item["id"] == report_id)
    assert record["passed_present"] is False
    assert record["passed_ok"] is False
    assert record["checks_ok"] is True
    assert result["checks"]["baseline_predictions"] is False
    assert result["passed"] is False


@pytest.mark.parametrize("tamper", ["false_flag", "missing_required_name", "bad_status"])
def test_historical_list_checks_require_name_flag_and_accepted_status(synthetic_case, tamper):
    report_id = "ixnos_bounded_finalization"
    report = synthetic_case.reports[report_id]
    if tamper == "false_flag":
        report["checks"][0]["pass"] = False
    elif tamper == "missing_required_name":
        report["checks"][0]["name"] = "different_check"
    else:
        report["status"] = "scientific_performance_proven"
    save_report(synthetic_case, report_id)

    result = verify(synthetic_case)

    record = next(item for item in result["reports"] if item["id"] == report_id)
    assert record["passed_present"] is False
    assert record["passed_ok"] is True
    if tamper == "false_flag":
        assert record["checks_ok"] is False
        assert record["required_checks_ok"] is False
    elif tamper == "missing_required_name":
        assert record["checks_ok"] is True
        assert record["required_checks_ok"] is False
    else:
        assert record["checks_ok"] is True
        assert record["required_checks_ok"] is True
        assert record["status_ok"] is False
    assert result["checks"]["direct_baseline_real_execution"] is False
    assert result["passed"] is False


def test_closeout_sha_mismatch_is_rejected(synthetic_case):
    result = verify(synthetic_case, expected_sha256="0" * 64)

    assert result["passed"] is False
    assert result["checks"]["closeout_sha256"] is False
    assert result["checks"]["closeout_verdict"] is True


def test_closeout_verdict_disagreement_is_rejected_even_with_refreshed_sha(synthetic_case):
    synthetic_case.closeout.update({
        "passed": False,
        "gate": verifier.FAIL_TOKEN,
        "A10_G0": "FAIL_DATA_AND_BASELINE_NOT_READY",
        "E1_start_allowed": False,
        "E2_start_allowed": False,
    })
    write_json(synthetic_case.closeout_path, synthetic_case.closeout)

    result = verify(synthetic_case)

    assert result["checks"]["closeout_sha256"] is True
    assert result["checks"]["closeout_verdict"] is False
    assert result["passed"] is False


def test_closeout_report_record_tampering_is_rejected(synthetic_case):
    synthetic_case.closeout["reports"][0]["report_ok"] = False
    write_json(synthetic_case.closeout_path, synthetic_case.closeout)

    result = verify(synthetic_case)

    assert result["checks"]["closeout_sha256"] is True
    assert result["checks"]["closeout_reports"] is False
    assert result["passed"] is False


def test_closeout_check_omission_is_rejected(synthetic_case):
    del synthetic_case.closeout["checks"]["baseline_predictions"]
    write_json(synthetic_case.closeout_path, synthetic_case.closeout)

    result = verify(synthetic_case)

    assert result["checks"]["closeout_checks"] is False
    assert result["passed"] is False


@pytest.mark.parametrize("field", [
    "SOTA", "generation_training_allowed", "final_untouched", "protein_ood",
])
def test_closeout_overreach_is_rejected(synthetic_case, field):
    synthetic_case.closeout[field] = True
    write_json(synthetic_case.closeout_path, synthetic_case.closeout)

    result = verify(synthetic_case)

    assert result["checks"]["closeout_sha256"] is True
    assert result["checks"]["claim_boundaries"] is False
    assert result["passed"] is False


def test_rnarl_negative_report_cannot_be_rewritten_as_positive(synthetic_case):
    report_id = "rnarl_negative_availability"
    synthetic_case.reports[report_id]["status"] = "PASS"
    save_report(synthetic_case, report_id)

    result = verify(synthetic_case)

    assert result["checks"]["rnarl_negative_availability_only"] is False
    assert result["checks"]["closeout_verdict"] is False
    assert result["passed"] is False


def test_rnarl_cannot_be_counted_as_runnable_in_closeout(synthetic_case):
    synthetic_case.closeout["rnarl"]["runnable"] = True
    synthetic_case.closeout["rnarl"]["counts_as_runnable_baseline"] = True
    write_json(synthetic_case.closeout_path, synthetic_case.closeout)

    result = verify(synthetic_case)

    assert result["checks"]["claim_boundaries"] is False
    assert result["passed"] is False


def test_protocol_cannot_omit_required_report(synthetic_case):
    synthetic_case.protocol["reports"] = [
        spec for spec in synthetic_case.protocol["reports"]
        if spec["id"] != "goodman_baseline_independent_v2"
    ]
    save_protocol(synthetic_case)

    result = verify(synthetic_case)

    assert result["passed"] is False
    assert result["checks"] == {"protocol": False}
    assert result["reports"] == []


def test_protocol_cannot_weaken_a10_top_level_passed_requirement(synthetic_case):
    report_id = "goodman_baseline_independent_v2"
    synthetic_case.specs[report_id]["passed_required"] = False
    del synthetic_case.reports[report_id]["passed"]
    save_report(synthetic_case, report_id)

    result = verify(synthetic_case)

    assert result["passed"] is False
    assert result["checks"] == {"protocol": False}
    assert "must require top-level passed" in result["errors"][0]["message"]


def test_remote_path_outside_frozen_root_is_rejected(synthetic_case):
    synthetic_case.protocol["report_roots"]["historical_rk05"] = "/tmp/historical"
    save_protocol(synthetic_case)

    result = verify(synthetic_case)

    assert result["passed"] is False
    assert result["checks"] == {"protocol": False}


def test_synthetic_hashes_cannot_weaken_production_mode(synthetic_case):
    result = verifier.verify_g0_closeout(
        synthetic_case.protocol_path,
        synthetic_case.report_root,
        synthetic_case.closeout_path,
        synthetic=False,
        expected_closeout_sha256=sha256(synthetic_case.closeout_path),
    )

    assert result["passed"] is False
    assert result["checks"] == {"protocol": False}
    assert "frozen report SHA256 mismatch" in result["errors"][0]["message"]


def test_missing_closeout_is_a_failed_verification(synthetic_case):
    synthetic_case.closeout_path.unlink()

    result = verify(synthetic_case, expected_sha256=None)

    assert result["passed"] is False
    assert result["checks"]["closeout_sha256"] is False
    assert result["checks"]["closeout_verdict"] is False
    assert result["reports"]


def test_cli_refuses_to_overwrite_before_reading_inputs(tmp_path):
    output = tmp_path / "verification.json"
    sentinel = b"do not overwrite synthetic output\n"
    output.write_bytes(sentinel)

    returncode = verifier.main([
        "--protocol", str(tmp_path / "must-not-be-read.json"),
        "--report-root", str(tmp_path / "must-not-be-read"),
        "--closeout", str(tmp_path / "must-not-be-read-closeout.json"),
        "--output", str(output),
    ])

    assert returncode == 2
    assert output.read_bytes() == sentinel
