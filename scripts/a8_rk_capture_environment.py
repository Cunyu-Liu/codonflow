#!/usr/bin/env python3
"""Capture an A8-RK source/execution manifest without reading secret env vars."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

DOCUMENTS = (
    "docs/handover/spec.md",
    "docs/handover/tasks.md",
    "docs/handover/HANDOFF_A8_RK_20261118.md",
    "docs/handover/PROMPT_NEXT_AGENT_A8_RK.md",
    "docs/review/CodonFlow_A8_严格科研工程审查与一个月路线_20261118.md",
    "paper/CodonFlow_preprint_A7.md",
)
PACKAGES = ("numpy", "pandas", "scipy", "pytest", "openpyxl", "requests", "biopython")


def run(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, text=True, capture_output=True
    ).stdout.strip()


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_versions() -> dict[str, str | None]:
    result = {}
    for package in PACKAGES:
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = None
    return result


def capture(repo: Path, data_root: Path, baseline_status: str) -> dict:
    repo = repo.resolve()
    return {
        "schema_version": "a8-rk-environment-v1",
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": {
            "path": str(repo),
            "branch": run(repo, "branch", "--show-current"),
            "base_commit": run(repo, "rev-parse", "HEAD"),
            "baseline_status": baseline_status,
            "current_status": run(repo, "status", "--short"),
            "remote_origin": run(repo, "remote", "get-url", "origin"),
        },
        "documents": {
            name: {"sha256": sha256(repo / name), "present": (repo / name).is_file()}
            for name in DOCUMENTS
        },
        "runtime": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "packages": package_versions(),
            "git_version": subprocess.run(
                ["git", "--version"], check=True, text=True, capture_output=True
            ).stdout.strip(),
            "curl_version": subprocess.run(
                ["curl", "--version"], check=True, text=True, capture_output=True
            ).stdout.splitlines()[0],
        },
        "storage": {
            "data_root": str(data_root),
            "data_root_exists": data_root.exists(),
            "data_root_free_bytes": shutil.disk_usage(data_root).free if data_root.exists() else None,
        },
        "secret_policy": "No environment dump, credential, token, password, or SSH command is captured.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--baseline-status", default="clean")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = capture(args.repo, args.data_root, args.baseline_status)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
