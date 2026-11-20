#!/usr/bin/env python3
"""RK19 environment and pytest configuration contract."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def optional_dependency(name):
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(rf"(?m)^{re.escape(name)} = (\[[^\n]*\])$", text)
    assert match, f"missing optional dependency group: {name}"
    return ast.literal_eval(match.group(1))


def test_conda_environment_contains_analysis_dependencies():
    text = (ROOT / "environment.yml").read_text(encoding="utf-8")
    assert "  - pandas=2.2.2\n" in text
    assert "  - scikit-learn=1.7.2\n" in text


def test_test_and_analysis_extras_are_complete():
    for group in ("dev", "analysis"):
        dependencies = optional_dependency(group)
        assert "pandas>=2.2" in dependencies
        assert "scikit-learn>=1.7" in dependencies


def test_integration_marker_is_registered():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "markers = [" in text
    assert "integration: isolated integration test" in text
