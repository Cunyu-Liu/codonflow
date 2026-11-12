import numpy as np

from codonflow.core.codon import gc_fraction
from scripts.a7_build_calibration_pool import build_pool, calibration_runs

SOURCE = "TTTGCTTAA"


def objective(sequence):
    return [gc_fraction(sequence), -abs(gc_fraction(sequence) - 0.55), -sequence.count("TTT"), 0.0]


def test_calibration_runs_include_uniform_and_four_single_axis_searches():
    runs = calibration_runs(2, 1)
    assert runs[0][0] == "uniform"
    assert [run[0] for run in runs[1:]] == ["hill_climbing"] * 4
    assert [run[1].index(1.0) for run in runs[1:]] == [0, 1, 2, 3]


def test_pool_uses_only_calibration_methods():
    points, runs = build_pool(SOURCE, objective, n_uniform=2, n_per_axis=1, seed=1729)
    assert len(points) == 6
    assert np.asarray(points).shape == (6, 4)
    assert all(run["status"] == "done" for run in runs)
