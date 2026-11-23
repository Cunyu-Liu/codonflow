import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import a10_01_g0_closeout as closeout


ROOT = Path(__file__).resolve().parents[1]
FROZEN_PROTOCOL = ROOT / "configs" / "a10_01_g0_closeout_protocol_v1.json"
HISTORICAL_LIST_REPORT_IDS = (
    "ixnos_bounded_finalization",
    "rose_bounded_finalization",
    "veloharmo_bounded_finalization",
    "ribomimo_bounded_finalization",
    "ensembledesign_bounded_finalization",
    "lineardesign_bounded_finalization",
)
HISTORICAL_REPORT_IDS = (*HISTORICAL_LIST_REPORT_IDS, "rnarl_negative_availability")
EXPECTED_SHA256 = {
    "goodman_e0_v3_report": "3036961a32502c1ea7a9bf6cd45f2ffbb0cadf2d18ff8f3405b4abd4bb1a6304",
    "goodman_e0_v3_independent": "c78359d03a45f3bbbcc867f36be8b2c74219a9410c543a90d08e8784a6bf42ab",
    "goodman_split_independent_v3": "379ef698d8f0029d929468c94bcdf594bd83384e957fcc31e4e66d46b4fc2f43",
    "goodman_baseline_independent_v2": "384519f7bfc4a6cd574694bee838176b6f4d0c871367c4a567bfffd30828e5a4",
    "tunney_e0_report": "9fecfb838762950b2545f6db4fb0d6ba4ab92cc9483aad20c33cd1f0d8abf9b9",
    "tunney_e0_independent": "0ea53ae7a35a55f4fb946e216b157de943784ac885368f72050e40080b547285",
    "codontransformer_gpu_report": "dc9b72aa678576229e3c9477e184e2f3878eafea87d4bcac3a7d3f50b65c951f",
    "codontransformer_gpu_independent": "c22d234304cc8c5c9e4156cbeddbaa732fcfd76ecee5276429cdceb6b74db0bf",
    "ixnos_bounded_finalization": "a3fb63540d59e5f76cebcbea555bf1a4c063b19c4d3917e48304c94ef3ab1c28",
    "rose_bounded_finalization": "c1733d1c937af26892fbfebf6385bcd9ca80b9825bd07f7597e7188716d48817",
    "veloharmo_bounded_finalization": "c056cc6207a15d74403926c676010a0fae50d7f7a215cb0ab19ce1fd40e609c5",
    "ribomimo_bounded_finalization": "69c532e20612b7d8de83486f7c2ced7961ac416f7c3e5218946f2804956407d8",
    "ensembledesign_bounded_finalization": "226cf4b15b0bdfac35a846941fc17986e5f1f3a76851ed33e106946d8b8a4fde",
    "lineardesign_bounded_finalization": "9a5e7e92c9578e4eda1f18774a8a21de2c8abc6bfda076f3ccafcc0a8fe61f79",
    "rnarl_negative_availability": "065215732f57a601431949220a4f4a25e7219d5f0cf7b22e3064288c87fdb47b",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        names = spec["required_checks"] or ["execution_verified"]
        if spec["id"] in HISTORICAL_LIST_REPORT_IDS:
            report["checks"] = [{"name": name, "pass": True} for name in names]
        else:
            report["checks"] = {name: True for name in names}
    return report


def save_protocol(case):
    case["protocol_path"].write_text(
        json.dumps(case["protocol"], indent=2) + "\n",
        encoding="utf-8",
    )


def save_report(case, report_id, refresh_hash=True):
    spec = case["specs"][report_id]
    path = case["report_paths"][report_id]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(case["reports"][report_id], indent=2) + "\n", encoding="utf-8")
    if refresh_hash:
        spec["sha256"] = sha256(path)
        save_protocol(case)


def make_case(tmp_path):
    protocol = json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))
    report_root = tmp_path / "synthetic_reports"
    report_root.mkdir()
    case = {
        "protocol": protocol,
        "protocol_path": tmp_path / "synthetic_protocol.json",
        "report_root": report_root,
        "specs": {spec["id"]: spec for spec in protocol["reports"]},
        "reports": {},
        "report_paths": {},
    }
    for report_id, spec in case["specs"].items():
        path = report_root / spec["relative_path"]
        case["report_paths"][report_id] = path
        case["reports"][report_id] = synthetic_report(spec)
        save_report(case, report_id)
    return case


def run(case, synthetic=True):
    return closeout.run_closeout(
        case["protocol_path"], case["report_root"], synthetic=synthetic,
    )


def report(result, report_id):
    return next(item for item in result["reports"] if item["id"] == report_id)


def arguments(case, output, synthetic=True):
    args = [
        "--protocol", str(case["protocol_path"]),
        "--report-root", str(case["report_root"]),
        "--output", str(output),
    ]
    if synthetic:
        args.append("--synthetic")
    return args


def test_frozen_registry_paths_and_exclusions_match_protocol():
    protocol = closeout.load_protocol(FROZEN_PROTOCOL)
    specs = {spec["id"]: spec for spec in protocol["reports"]}
    assert closeout.EXPECTED_REPORT_SHA256 == EXPECTED_SHA256
    assert set(specs) == set(EXPECTED_SHA256)
    assert len(specs) == 15
    assert all(specs[report_id]["passed_required"] is False for report_id in HISTORICAL_REPORT_IDS)
    assert all(
        specs[report_id]["passed_required"] is True
        for report_id in set(EXPECTED_SHA256) - set(HISTORICAL_REPORT_IDS) - {
            "goodman_e0_v3_report", "tunney_e0_report", "codontransformer_gpu_report",
        }
    )
    for report_id, spec in specs.items():
        assert spec["sha256"] == EXPECTED_SHA256[report_id]
        assert spec["relative_path"].endswith(".json")
        assert spec["absolute_path"].endswith(spec["relative_path"])
        if spec["absolute_path"].startswith("/teams/"):
            assert "/codonflow1031/a10/e0/" in spec["absolute_path"]
        else:
            assert spec["absolute_path"].startswith(
                "/home/codonflow-a8-rk/audits/20261118/RK05/"
            )
    assert specs["goodman_split_independent_v3"]["expected"]["/protocol"] == (
        "a10_01_goodman_nested_grouped_cv_independent_verification_v2"
    )
    assert specs["goodman_baseline_independent_v2"]["expected"]["/protocol"] == (
        "a10_01_goodman_baseline_independent_verification_v1"
    )
    assert "rnarl_negative_availability" not in protocol["direct_execution_report_ids"]
    assert all("id3" not in report_id for report_id in specs)
    assert protocol["exclusions"]["id3_cpc_trajectories"] == "excluded"
    assert protocol["execution"]["scientific_rerun"] is False
    assert protocol["execution"]["untouched_reads"] is False


def test_synthetic_all_reports_pass_and_only_e1_e2_open(tmp_path):
    case = make_case(tmp_path)
    result = run(case)

    assert result["passed"]
    assert result["gate"] == "A10_G0=PASS_DATA_AND_BASELINE_READY"
    assert result["A10_G0"] == "PASS_DATA_AND_BASELINE_READY"
    assert len(result["reports"]) == 15
    assert all(item["report_ok"] for item in result["reports"])
    assert all(item["hash_ok"] for item in result["reports"])
    for report_id in HISTORICAL_REPORT_IDS:
        observed = report(result, report_id)
        assert observed["passed_present"] is False
        assert observed["passed_ok"] is True
        assert observed["checks_ok"] is True
    for report_id in HISTORICAL_LIST_REPORT_IDS:
        assert isinstance(case["reports"][report_id]["checks"], list)
        assert report(result, report_id)["checks"] == {"execution_verified": True}
    assert isinstance(case["reports"]["rnarl_negative_availability"]["checks"], dict)
    assert all(result["checks"].values())
    assert result["E1_start_allowed"] is True
    assert result["E2_start_allowed"] is True
    assert result["final_untouched"] is False
    assert result["cross_study_H1_H2_proven"] is False
    assert result["claim_boundaries"]["cross_study_H1_proven"] is False
    assert result["claim_boundaries"]["cross_study_H2_proven"] is False
    assert result["E3_proven"] is False
    assert result["G2_proven"] is False
    assert result["SOTA"] is False
    assert result["generation_training_allowed"] is False
    assert "G2" in result["generation_training_constraint"]
    assert result["rnarl"] == {
        "negative_availability_evidence": True,
        "runnable": False,
        "counts_as_runnable_baseline": False,
    }
    assert result["id3_cpc_trajectories"] == "excluded"
    assert result["scientific_rerun"] is False
    assert result["raw_or_untouched_data_read"] is False
    assert all(
        Path(item["input_path"]).is_relative_to(case["report_root"])
        for item in result["reports"]
    )


@pytest.mark.parametrize("report_id,kind,value,failed_field", [
    ("goodman_baseline_independent_v2", "passed", False, "passed_ok"),
    ("goodman_baseline_independent_v2", "check", False, "checks_ok"),
    ("goodman_split_independent_v3", "missing_check", None, "required_checks_ok"),
    ("goodman_baseline_independent_v2", "prediction_rows", 1, "semantic_ok"),
    ("codontransformer_gpu_report", "status", "scientific_performance_proven", "status_ok"),
    ("rnarl_negative_availability", "status", "PASS", "status_ok"),
])
def test_synthetic_failed_status_passed_checks_or_semantics_block_gate(
    tmp_path, report_id, kind, value, failed_field,
):
    case = make_case(tmp_path)
    payload = case["reports"][report_id]
    if kind == "passed":
        payload["passed"] = value
    elif kind == "check":
        payload["checks"]["outer_test_isolation"] = value
    elif kind == "missing_check":
        del payload["checks"]["outer_gene_isolation"]
    elif kind == "prediction_rows":
        payload["recomputed"]["prediction_rows"] = value
    elif kind == "status":
        payload["status"] = value
    save_report(case, report_id)

    result = run(case)
    observed = report(result, report_id)
    assert observed["hash_ok"]
    assert not observed[failed_field]
    assert not observed["report_ok"]
    assert not result["passed"]
    assert result["gate"] == "A10_G0=FAIL_DATA_AND_BASELINE_NOT_READY"
    assert result["E1_start_allowed"] is False
    assert result["E2_start_allowed"] is False
    assert result["generation_training_allowed"] is False


def test_synthetic_list_passed_alias_and_required_names_pass(tmp_path):
    case = make_case(tmp_path)
    report_id = "ixnos_bounded_finalization"
    case["specs"][report_id]["required_checks"] = ["source_verified", "execution_verified"]
    case["reports"][report_id]["checks"] = [
        {"name": "source_verified", "passed": True},
        {"name": "execution_verified", "pass": True},
    ]
    save_report(case, report_id)

    result = run(case)
    observed = report(result, report_id)
    assert observed["checks_ok"] is True
    assert observed["required_checks_ok"] is True
    assert observed["checks"] == {"source_verified": True, "execution_verified": True}
    assert result["passed"] is True


@pytest.mark.parametrize("mutation,failed_field", [
    ("missing", "required_checks_ok"),
    ("failed", "checks_ok"),
    ("missing_flag", "checks_ok"),
])
def test_synthetic_list_missing_or_failed_items_block_gate(tmp_path, mutation, failed_field):
    case = make_case(tmp_path)
    report_id = "rose_bounded_finalization"
    case["specs"][report_id]["required_checks"] = ["source_verified", "execution_verified"]
    case["reports"][report_id]["checks"] = [
        {"name": "source_verified", "pass": True},
        {"name": "execution_verified", "passed": True},
    ]
    if mutation == "missing":
        case["reports"][report_id]["checks"].pop()
    elif mutation == "failed":
        case["reports"][report_id]["checks"][1]["passed"] = False
    else:
        del case["reports"][report_id]["checks"][1]["passed"]
    save_report(case, report_id)

    result = run(case)
    observed = report(result, report_id)
    assert observed["hash_ok"] is True
    assert observed["passed_ok"] is True
    assert observed[failed_field] is False
    assert observed["report_ok"] is False
    assert result["checks"]["direct_baseline_real_execution"] is False
    assert result["passed"] is False


def test_synthetic_non_boolean_check_value_is_rejected(tmp_path):
    case = make_case(tmp_path)
    case["reports"]["goodman_split_independent_v3"]["checks"]["outer_gene_isolation"] = 1
    save_report(case, "goodman_split_independent_v3")
    result = run(case)
    assert not report(result, "goodman_split_independent_v3")["checks_ok"]
    assert not result["passed"]


def test_synthetic_hash_tampering_blocks_gate_even_when_protocol_is_unchanged(tmp_path):
    case = make_case(tmp_path)
    original_hash = case["specs"]["goodman_e0_v3_report"]["sha256"]
    case["reports"]["goodman_e0_v3_report"]["raw_csv"]["data_rows"] = 1
    save_report(case, "goodman_e0_v3_report", refresh_hash=False)

    result = run(case)
    observed = report(result, "goodman_e0_v3_report")
    assert observed["expected_sha256"] == original_hash
    assert observed["actual_sha256"] != original_hash
    assert not observed["hash_ok"]
    assert not observed["semantic_ok"]
    assert not result["passed"]
    assert not result["checks"]["real_functional_raw_and_qc"]


def test_synthetic_mode_cannot_weaken_fixed_production_hashes(tmp_path):
    case = make_case(tmp_path)
    with pytest.raises(ValueError, match="frozen report SHA256 mismatch"):
        run(case, synthetic=False)


def test_missing_report_is_a_failed_file_not_an_ignored_input(tmp_path):
    case = make_case(tmp_path)
    case["report_paths"]["tunney_e0_independent"].unlink()
    result = run(case)
    observed = report(result, "tunney_e0_independent")
    assert not observed["hash_ok"]
    assert not observed["json_ok"]
    assert not result["checks"]["development_ribo_and_tunney_candidates"]
    assert not result["passed"]


def test_main_synthetic_pass_writes_once_and_refuses_overwrite(tmp_path):
    case = make_case(tmp_path)
    output = tmp_path / "nested" / "closeout.json"
    assert closeout.main(arguments(case, output)) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["gate"] == closeout.PASS_TOKEN
    assert payload["claim_boundaries"]["generation_training_requires_G2"] is True
    original = output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        closeout.main(arguments(case, output))
    assert output.read_bytes() == original


def test_main_synthetic_failure_is_persisted_and_not_overwritten(tmp_path):
    case = make_case(tmp_path)
    case["reports"]["goodman_baseline_independent_v2"]["checks"]["outer_test_isolation"] = False
    save_report(case, "goodman_baseline_independent_v2")
    output = tmp_path / "failed-closeout.json"
    assert closeout.main(arguments(case, output)) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["gate"] == closeout.FAIL_TOKEN
    assert not payload["checks"]["direct_baseline_real_execution"]
    assert payload["SOTA"] is False
    original = output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        closeout.main(arguments(case, output))
    assert output.read_bytes() == original
