import pytest

from scripts.a7_convergence_audit import validate_history


def history_and_rows(values):
    return values, {"epoch": len(values), "best_epoch": values.index(min(values)) + 1,
                    "best_val_loss": min(values), "last_val_loss": values[-1]}, [
        {"epoch": i, "val_loss": value} for i, value in enumerate(values, 1)
    ]


def test_convergence_history_requires_three_independent_plateau_epochs():
    history, reported, rows = history_and_rows([3.0, 2.0, 1.9995, 1.9994, 1.9993])
    result = validate_history(history, reported, rows)
    assert result["n_epochs"] == 5
    assert result["best_epoch"] == 5
    assert len(result["last_three_relative_improvements"]) == 3


def test_convergence_rejects_continued_meaningful_improvement():
    history, reported, rows = history_and_rows([3.0, 2.0, 1.9995, 1.9994, 1.98])
    with pytest.raises(ValueError, match="plateau"):
        validate_history(history, reported, rows)


def test_convergence_rejects_log_history_mismatch():
    history, reported, rows = history_and_rows([3.0, 2.0, 1.9995, 1.9994, 1.9993])
    rows[-1]["val_loss"] = 1.99
    with pytest.raises(ValueError, match="log.jsonl"):
        validate_history(history, reported, rows)


def test_convergence_rejects_wrong_best_epoch():
    history, reported, rows = history_and_rows([3.0, 2.0, 1.9995, 1.9994, 1.9993])
    reported["best_epoch"] = 1
    with pytest.raises(ValueError, match="epoch"):
        validate_history(history, reported, rows)
