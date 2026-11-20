from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "configs/a8_g0_closeout_protocol_v2.json"
PRODUCTION_PATH = ROOT / "audits/20261120/RK06/g0_unified_cost_closeout_v2.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = load_module("a8_g0_verify_closeout_test", ROOT / "scripts/a8_g0_verify_closeout.py")
PROTOCOL = json.loads(PROTOCOL_PATH.read_text())
PRODUCTION = json.loads(PRODUCTION_PATH.read_text())


def verify(protocol=None, production=None):
    return verifier.verify_report(ROOT, protocol or PROTOCOL, production or PRODUCTION,
                                  PROTOCOL_PATH, PRODUCTION_PATH)


def test_real_closeout_independent_pass():
    report = verify()
    assert report["all_pass"]
    assert report["passed_checks"] == report["check_count"]
    assert report["max_numeric_delta"] == 0.0


def test_cost_matrix_counts_and_anchor_values():
    rows = {row["row_id"]: row for row in PRODUCTION["cost_matrix"]}
    assert len(rows) == 22
    assert PRODUCTION["summary"]["measured_wall_clock_scopes"] == 13
    assert PRODUCTION["summary"]["explicit_null_wall_clock_scopes"] == 9
    assert rows["lineardesign_unique18"]["metrics"]["wall_clock_s"] == 5459.871640930884
    assert rows["ensembledesign_unique18"]["metrics"]["wall_clock_s"] == 6001.057458210271
    assert rows["rk06_dense_uniform"]["metrics"]["unique_scorer_calls"] == 27000
    assert rows["rnarl_availability"]["metrics"]["qc_pairs"] == 128289
    assert rows["coformer_not_run"]["status"] == "NOT_RUN"
    assert rows["charming_not_run"]["status"] == "NOT_RUN"


def test_gate_result_is_bounded_and_does_not_authorize_generator():
    assert PRODUCTION["g0_status"] == "PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY"
    assert PRODUCTION["rk03_remaining_status"] == "FEASIBILITY_CLOSED_NOT_FULL_REMAP"
    assert PRODUCTION["boundaries"]["rk_g1_passed"] is False
    assert PRODUCTION["boundaries"]["generator_training_authorized"] is False
    assert PRODUCTION["boundaries"]["time_matched_complete"] is False
    assert PRODUCTION["boundaries"]["complete_sota"] is False
    assert PRODUCTION["summary"]["global_wall_clock_sum"] is None


def test_changed_cost_is_rejected():
    changed = copy.deepcopy(PRODUCTION)
    changed["cost_matrix"][0]["metrics"]["wall_clock_s"] += 1.0
    report = verify(production=changed)
    assert not report["all_pass"]
    assert any(not c["passed"] and c["check_id"].startswith("metric:lineardesign_unique18:wall_clock_s")
               for c in report["checks"])


def test_changed_status_is_rejected():
    changed = copy.deepcopy(PRODUCTION)
    changed["cost_matrix"][0]["status"] = "PASS"
    report = verify(production=changed)
    assert not report["all_pass"]
    assert any(not c["passed"] and c["check_id"] == "row_status:lineardesign_unique18"
               for c in report["checks"])


def test_removed_null_reason_is_rejected():
    changed = copy.deepcopy(PRODUCTION)
    row = next(row for row in changed["cost_matrix"] if row["row_id"] == "inherited_codongpt")
    row["unavailable_reasons"]["wall_clock_s"] = ""
    report = verify(production=changed)
    assert not report["all_pass"]
    assert any(not c["passed"] and c["check_id"] == "unavailable_reasons:inherited_codongpt"
               for c in report["checks"])


def test_changed_source_hash_is_rejected():
    changed = copy.deepcopy(PROTOCOL)
    changed["sources"]["rk12_final"]["sha256"] = "0" * 64
    report = verify(protocol=changed)
    assert not report["all_pass"]
    assert any(not c["passed"] and c["check_id"] == "source_sha256:rk12_final"
               for c in report["checks"])


def test_changed_boundary_is_rejected():
    changed = copy.deepcopy(PRODUCTION)
    changed["boundaries"]["generator_training_authorized"] = True
    report = verify(production=changed)
    assert not report["all_pass"]
    assert any(not c["passed"] and c["check_id"] == "boundaries" for c in report["checks"])


def test_json_pointer_array_and_escape_semantics():
    document = {"a": [{"b": 2}, {"b": 3}], "x/y": {"~key": 5}}
    assert verifier.at(document, "/a/0/b") == 2
    assert verifier.at(document, "/a/1/b") == 3
    assert verifier.at(document, "/x~1y/~0key") == 5
    assert verifier.materialize({"sum_pointers": ["/a/0/b", "/a/1/b"]}, document) == 5
    assert verifier.materialize({"null_reason": "unavailable"}, document) is None
