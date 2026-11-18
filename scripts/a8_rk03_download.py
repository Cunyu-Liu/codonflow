#!/usr/bin/env python3
"""Resume and verify A8-RK public data downloads without overwriting bad payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from scripts.a8_rk_functional_data import (
    DataValidationError,
    sha256_file,
    validate_payload,
)

USER_AGENT = "CodonFlow-A8-RK03-public-data/1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_integrity(path: Path, spec: Mapping[str, object]) -> Dict[str, object]:
    if not path.is_file():
        raise DataValidationError(f"missing file: {path}")
    actual_bytes = path.stat().st_size
    expected_bytes = spec.get("expected_bytes")
    if expected_bytes is not None and actual_bytes != int(expected_bytes):
        raise DataValidationError(
            f"byte count mismatch for {path.name}: expected={expected_bytes}, actual={actual_bytes}"
        )
    validate_payload(path, str(spec.get("media_type", "text/csv")))
    result: Dict[str, object] = {"bytes": actual_bytes, "sha256": sha256_file(path)}
    for algorithm in ("md5", "sha256"):
        key = f"expected_{algorithm}"
        expected = spec.get(key)
        if expected:
            actual = result["sha256"] if algorithm == "sha256" else digest_file(path, algorithm)
            result[algorithm] = actual
            if str(actual).lower() != str(expected).lower():
                raise DataValidationError(
                    f"{algorithm} mismatch for {path.name}: expected={expected}, actual={actual}"
                )
    return result


def _part_path(destination: Path) -> Path:
    return destination.with_name(destination.name + ".part")


def download_verified(
    url: str,
    destination: Path,
    spec: Mapping[str, object],
    timeout: float = 120.0,
    retries: int = 3,
) -> Dict[str, object]:
    """Download to a resumable sidecar and atomically promote only verified bytes."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        result = verify_integrity(destination, spec)
        return {"status": "reused_verified", "attempts": 0, **result}

    part = _part_path(destination)
    last_error: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        offset = part.stat().st_size if part.exists() else 0
        try:
            headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = int(getattr(response, "status", 200))
                append = bool(offset and status == 206)
                if offset and status == 206:
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.startswith(f"bytes {offset}-"):
                        raise DataValidationError(
                            f"invalid Content-Range for offset {offset}: {content_range!r}"
                        )
                mode = "ab" if append else "wb"
                with part.open(mode) as handle:
                    while True:
                        chunk = response.read(8 * 1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        expected_bytes = spec.get("expected_bytes")
                        if expected_bytes is not None and handle.tell() > int(expected_bytes):
                            raise DataValidationError(
                                f"payload exceeds expected byte count: {expected_bytes}"
                            )
            result = verify_integrity(part, spec)
            os.replace(part, destination)
            return {
                "status": "downloaded_verified",
                "attempts": attempt,
                "resumed_from_bytes": offset if append else 0,
                "http_status": status,
                **result,
            }
        except (OSError, urllib.error.URLError, DataValidationError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(2 ** (attempt - 1), 8))
    raise DataValidationError(
        f"download failed after {retries} attempts: {type(last_error).__name__}: {last_error}"
    )


def download_config(
    config_path: Path,
    data_root: Path,
    source_ids: Optional[Sequence[str]] = None,
    timeout: float = 120.0,
    retries: int = 3,
) -> Dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    selected = set(source_ids or [])
    records: List[Dict[str, object]] = []
    failures: List[Dict[str, object]] = []
    for source in config["sources"]:
        source_id = str(source["source_id"])
        if selected and source_id not in selected:
            continue
        for file_spec in source.get("files", []):
            url = file_spec.get("download_url")
            if not url:
                continue
            name = Path(str(file_spec["filename"])).name
            if name != file_spec["filename"] or name in {"", ".", ".."}:
                raise DataValidationError(f"unsafe output filename: {file_spec['filename']!r}")
            relative = Path("raw") / source_id / name
            destination = data_root / relative
            record: Dict[str, object] = {
                "source_id": source_id,
                "file_id": file_spec["file_id"],
                "filename": name,
                "url": url,
                "path": str(destination),
                "role": file_spec.get("role", ""),
                "evidence_class": source.get("evidence_class", "unclassified"),
            }
            try:
                result = download_verified(
                    str(url), destination, file_spec, timeout=timeout, retries=retries
                )
                record.update(result)
            except Exception as exc:
                record.update({
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "resumable_part": str(_part_path(destination)),
                })
                failures.append(dict(record))
            records.append(record)
    if not records:
        raise DataValidationError("no downloadable files selected")
    return {
        "schema_version": "a8-rk03-download-manifest-v1",
        "created_at": utc_now(),
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "data_root": str(data_root),
        "selected_source_ids": sorted(selected),
        "records": records,
        "failures": failures,
        "status": "partial" if failures else "complete",
    }


def write_manifest(manifest: Mapping[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + f".part.{os.getpid()}")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, output_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-id", action="append", dest="source_ids")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args(argv)
    manifest = download_config(
        args.config, args.data_root, args.source_ids, args.timeout, args.retries
    )
    write_manifest(manifest, args.manifest)
    print(json.dumps({
        "status": manifest["status"],
        "records": len(manifest["records"]),
        "failures": len(manifest["failures"]),
        "manifest": str(args.manifest),
    }, sort_keys=True))
    return 1 if manifest["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
