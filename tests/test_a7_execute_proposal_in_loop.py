import pytest

from scripts.a7_execute_proposal_in_loop import parse_arm


def test_execute_diagnostic_arm_parser():
    assert parse_arm("FULL=/teams/model.pt:" + "a" * 64) == ("FULL", "/teams/model.pt", "a" * 64)
    with pytest.raises(ValueError):
        parse_arm("INVALID=/teams/model.pt:" + "a" * 64)
    with pytest.raises(ValueError):
        parse_arm("FULL=/teams/model.pt:short")
