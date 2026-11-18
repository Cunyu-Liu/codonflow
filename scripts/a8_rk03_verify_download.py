#!/usr/bin/env python3
"""Independent byte/hash verification of the recovered RNARL download.

This does not perform row-level QC and does not authorize training. It verifies
both manifests, all final bytes, and the retained checksum-failed quarantine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def hashes(path: Path, *, md5: bool = True) -> dict[str, Any]:
    hm = hashlib.md5() if md5 else None
    hs = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            size += len(chunk)
            if hm is not None:
                hm.update(chunk)
            hs.update(chunk)
    result: dict[str, Any] = {"bytes": size, "sha256": hs.hexdigest()}
    if hm is not None:
        result["md5"] = hm.hexdigest()
    return result


def file_sha(path: Path) -> str:
    return hashes(path, md5=False)["sha256"]


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    audit_dir = repo / "audits/20261118/RK03"
    config_path = repo / "configs/a8_rk03_sources.json"
    recovery_path = audit_dir / "rnarl_download_manifest.json"
    reverify_path = audit_dir / "rnarl_reverify_download_manifest.json"
    output = args.output or audit_dir / "rnarl_download_independent_verification.json"
    config = json.loads(config_path.read_text())
    recovery = json.loads(recovery_path.read_text())
    reverify = json.loads(reverify_path.read_text())
    source = next(s for s in config["sources"] if s["source_id"] == "rnarl_v1")
    expected = {f["file_id"]: f for f in source["files"]}
    rec = {r["file_id"]: r for r in recovery["records"]}
    rev = {r["file_id"]: r for r in reverify["records"]}
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    check("config_hash_matches_both_manifests", recovery["config_sha256"] == reverify["config_sha256"] == file_sha(config_path), recovery["config_sha256"])
    check("expected_21_unique_files", len(expected) == len(rec) == len(rev) == 21 and set(expected) == set(rec) == set(rev), len(expected))
    check("both_manifests_complete_without_failures", recovery["status"] == reverify["status"] == "complete" and not recovery["failures"] and not reverify["failures"], None)
    check("recovery_modes_preserved", sum(r["status"] == "downloaded_verified" for r in rec.values()) == 2 and sum(r["status"] == "reused_verified" for r in rec.values()) == 19 and all(r["status"] == "reused_verified" for r in rev.values()), {"recovery": {k: sum(r["status"] == k for r in rec.values()) for k in ("downloaded_verified", "reused_verified")}, "reverify": {k: sum(r["status"] == k for r in rev.values()) for k in ("reused_verified",)}})

    raw_root = Path(rec[next(iter(rec))]["path"]).parent
    per_file = []
    all_ok = True
    for file_id in sorted(expected):
        exp = expected[file_id]
        a, b = rec[file_id], rev[file_id]
        path = raw_root / exp["filename"]
        actual = hashes(path)
        ok = (
            path.is_file()
            and Path(a["path"]) == path == Path(b["path"])
            and actual["bytes"] == exp["expected_bytes"] == a["bytes"] == b["bytes"]
            and actual["md5"] == exp["expected_md5"] == a["md5"] == b["md5"]
            and actual["sha256"] == a["sha256"] == b["sha256"]
        )
        all_ok &= ok
        per_file.append({"file_id": file_id, "path": str(path), "pass": ok, **actual})
    check("all_final_bytes_md5_sha256_match_independently", all_ok, {"files": len(per_file), "total_bytes": sum(x["bytes"] for x in per_file)})

    finals = sorted(p.name for p in raw_root.iterdir() if p.is_file() and p.suffix == ".csv")
    active_parts = sorted(p.name for p in raw_root.iterdir() if p.is_file() and p.name.endswith(".part"))
    check("exact_final_set_and_no_active_parts", finals == sorted(f["filename"] for f in expected.values()) and not active_parts, {"finals": len(finals), "active_parts": active_parts})

    quarantine_records = []
    for file_id, record in rec.items():
        for item in record.get("quarantined_parts", []):
            quarantine_records.append((file_id, record, item))
    quarantine_actual = []
    quarantine_ok = len(quarantine_records) == 2
    for file_id, final_record, item in quarantine_records:
        path = Path(item["path"])
        actual = hashes(path)
        expected_md5 = expected[file_id]["expected_md5"]
        reason_prefix = f"actual={actual['md5']}"
        ok = (
            path.parent == raw_root
            and ".part.rejected-" in path.name
            and actual["bytes"] == item["bytes"]
            and actual["md5"] != expected_md5
            and actual["sha256"] != final_record["sha256"]
            and reason_prefix in item["reason"]
        )
        quarantine_ok &= ok
        quarantine_actual.append({"file_id": file_id, "path": str(path), "pass": ok, **actual})
    disk_quarantine = sorted(p.name for p in raw_root.iterdir() if p.is_file() and ".part.rejected-" in p.name)
    quarantine_ok &= disk_quarantine == sorted(Path(item["path"]).name for _, _, item in quarantine_records)
    check("two_checksum_failed_parts_preserved_and_distinct", quarantine_ok, quarantine_actual)
    check("reverify_does_not_overwrite_recovery_quarantine_evidence", sum(len(r.get("quarantined_parts", [])) for r in rec.values()) == 2 and sum(len(r.get("quarantined_parts", [])) for r in rev.values()) == 0, None)

    passed = sum(c["pass"] for c in checks)
    report = {
        "schema_version": "a8-rk03-independent-download-verification-v1",
        "status": "PASS_DOWNLOAD_ONLY_QC_PENDING" if passed == len(checks) else "FAIL",
        "config": str(config_path),
        "config_sha256": file_sha(config_path),
        "recovery_manifest": str(recovery_path),
        "recovery_manifest_sha256": file_sha(recovery_path),
        "reverify_manifest": str(reverify_path),
        "reverify_manifest_sha256": file_sha(reverify_path),
        "checks": checks,
        "passed_checks": passed,
        "check_count": len(checks),
        "per_file": per_file,
        "scope": {
            "all_21_official_files_bytes_md5_sha256_verified": passed == len(checks),
            "row_level_qc_complete": False,
            "clean_pairs_authorized": False,
            "natural_cds_claim": False,
            "functional_training_or_ood_authorized": False,
            "sota_claim": False,
        },
    }
    atomic_json(output, report)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "files": len(per_file), "bytes": sum(x["bytes"] for x in per_file), "output": str(output)}, indent=2))
    if report["status"] == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
