import subprocess

import pytest

from scripts.a7_provenance import resolve_accepted_code_commits


def git(repository, *args):
    return subprocess.check_output(["git", *args], cwd=repository, text=True).strip()


def test_provenance_accepts_current_and_registered_ancestors_only(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "tests@example.invalid")
    git(tmp_path, "config", "user.name", "CodonFlow tests")
    (tmp_path / "tracked.txt").write_text("first\n")
    git(tmp_path, "add", "tracked.txt")
    git(tmp_path, "commit", "-qm", "first")
    ancestor = git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "tracked.txt").write_text("second\n")
    git(tmp_path, "commit", "-qam", "second")
    current = git(tmp_path, "rev-parse", "HEAD")

    accepted = resolve_accepted_code_commits([ancestor, current], repository=tmp_path)
    assert accepted == frozenset({ancestor, current})
    with pytest.raises(ValueError, match="not an ancestor"):
        resolve_accepted_code_commits(["f" * 40], repository=tmp_path)
    with pytest.raises(ValueError, match="full lowercase Git SHA"):
        resolve_accepted_code_commits([ancestor[:7]], repository=tmp_path)
