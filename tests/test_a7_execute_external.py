import pytest

from scripts.a7_execute_external import expected_inputs


def test_external_input_matrix_is_complete(tmp_path):
    records = ["g1", "g2"]
    for record in records:
        for seed in (0, 1, 2):
            (tmp_path / f"{record}_s{seed}.json").write_text("{}")
    paths = expected_inputs(records, tmp_path)
    assert len(paths) == 6
    assert paths[0].name == "g1_s0.json"
    assert paths[-1].name == "g2_s2.json"


def test_external_input_matrix_rejects_missing(tmp_path):
    (tmp_path / "g1_s0.json").write_text("{}")
    with pytest.raises(ValueError, match="missing external inputs"):
        expected_inputs(("g1",), tmp_path)
