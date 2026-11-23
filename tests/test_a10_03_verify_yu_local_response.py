import gzip
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_yu", ROOT / "scripts" / "a10_03_verify_yu_local_response.py")
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def test_independent_wig_expands_intervals(tmp_path):
    path = tmp_path / "reporter.wig.gz"
    with gzip.open(path, "wt") as handle:
        handle.write("other\t0\t4\t99\nreporter\t0\t2\t1.5\nreporter\t2\t5\t0\n")
    assert verify.load_wig(path, "reporter", 5) == [1.5, 1.5, 0.0, 0.0, 0.0]


def test_independent_wig_rejects_discontinuity(tmp_path):
    path = tmp_path / "reporter.wig.gz"
    with gzip.open(path, "wt") as handle:
        handle.write("reporter\t0\t2\t1\nreporter\t3\t5\t1\n")
    with pytest.raises(ValueError, match="gap"):
        verify.load_wig(path, "reporter", 5)


def test_independent_translation_and_numeric_contract():
    sequence = "AAAATGAAATAGGGG"
    assert verify.protein(sequence, 3, 12) == "MK"
    with pytest.raises(ValueError, match="stop"):
        verify.protein(sequence, 3, 9)
    verify.require_equal(1.0, 1.0 + 1e-12, "numeric tolerance")
    with pytest.raises(ValueError, match="mismatch"):
        verify.require_equal(None, 1.0, "missing value")
