import hashlib
import json
from pathlib import Path

import pytest

from scripts.a7_proposal_in_loop_gate import evaluate_diagnostic, select_genes
from tests.test_a7_g2_raw_verification import valid_result


def diagnostic_inputs(tmp_path):
    learned, source, calibration_dir = valid_result(tmp_path)
    learned.update({"method": "learned_hill", "code_commit": "abc", "device": "cuda:0",
                    "terminal_step": 1, "path_batch_size": 1})
    baseline, _, _ = valid_result(tmp_path)
    baseline.update({"method": "hill_climbing", "code_commit": "abc",
                     "checkpoint_path": None, "checkpoint_sha256": None, "device": None})
    baseline_path = tmp_path / "baseline" / "g1_hill_climbing_s0.json"
    baseline_path.parent.mkdir()
    baseline_path.write_text(json.dumps(baseline))
    learned["baseline_path"] = str(baseline_path)
    learned["baseline_sha256"] = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    learned_path = tmp_path / "g1_learned_hill_s0.json"
    learned_path.write_text(json.dumps(learned))
    arm = {"name": "FULL", "checkpoint_sha256": "9" * 64,
           "paths": [str(learned_path)], "baseline_dir": str(baseline_path.parent)}
    return arm, source, calibration_dir


def test_diagnostic_gate_recomputes_raw_metrics_without_go_claim(tmp_path):
    arm, source, calibration_dir = diagnostic_inputs(tmp_path)
    result = evaluate_diagnostic([arm], {"g1": source}, calibration_dir,
                                 frozenset({"abc"}), expected_genes=("g1",), expected_seeds=(0,))
    assert result["diagnostic_complete"] is True
    assert result["scientific_gate_passed"] is False
    assert result["exploratory_not_gate"] is True
    assert result["raw_metrics_recomputed"] is True
    assert result["arms"][0]["per_gene"][0]["relative_improvement"] == 0.0
    assert result["arms"][0]["per_gene"][0]["elapsed_ratio"] == 1.0
    assert result["arms"][0]["statistics"]["n_genes"] == 1
    assert result["arms"][0]["statistics"]["wilcoxon_greater_p"] == 1.0
    assert result["holm_adjusted_wilcoxon_p"] == {"FULL": 1.0}
    seed = result["arms"][0]["per_gene"][0]["seeds"][0]
    assert set(seed["learned_best_at_budget"]) == {"50", "100", "500"}
    assert len(seed["simple_best_at_budget"]["500"]) == 4


def test_record_selection_excludes_exact_diagnostic_genes():
    records = {f"g{index}": "SEQUENCE" for index in range(18)}
    selected = select_genes(records, ("g0", "g1", "g2"))
    assert selected == tuple(f"g{index}" for index in range(3, 18))
    assert len(selected) == 15
    with pytest.raises(ValueError, match="must be unique"):
        select_genes(records, ("g0", "g0"))
    with pytest.raises(ValueError, match="unknown excluded"):
        select_genes(records, ("missing",))
    with pytest.raises(ValueError, match="cannot be empty"):
        select_genes(records, tuple(records))


def test_diagnostic_gate_rejects_baseline_hash_mismatch(tmp_path):
    arm, source, calibration_dir = diagnostic_inputs(tmp_path)
    path = Path(arm["paths"][0])
    payload = json.loads(path.read_text())
    payload["baseline_sha256"] = "0" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="baseline link mismatch"):
        evaluate_diagnostic([arm], {"g1": source}, calibration_dir,
                            frozenset({"abc"}), expected_genes=("g1",), expected_seeds=(0,))
