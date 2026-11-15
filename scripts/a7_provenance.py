"""Resolve an explicit, immutable set of source commits accepted for a resumed run."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


def resolve_accepted_code_commits(values=(), repository=None):
    root = Path(repository) if repository is not None else Path(__file__).resolve().parents[1]
    current = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True,
    ).strip()
    commits = {current}
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError(f"accepted code commit must be a full lowercase Git SHA: {value}")
        if value == current:
            continue
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", value, current], cwd=root,
        )
        if ancestor.returncode != 0:
            raise ValueError(f"accepted code commit is not an ancestor of HEAD: {value}")
        commits.add(value)
    return frozenset(commits)
