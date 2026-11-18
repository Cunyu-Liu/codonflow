#!/usr/bin/env python3
"""Wait for an existing RK03 downloader, then run hash-gated QC and verification."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

REPO = Path("/home/codonflow-a8-rk")
PYTHON = Path("/root/miniconda3/envs/codonflow/bin/python")
DATA = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03")
AUDITS = REPO / "audits/20261118/RK03"
CONFIG = REPO / "configs/a8_rk03_sources.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    if path.exists(): raise RuntimeError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + f".part.{os.getpid()}")
    part.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(part, path)


def pid_active(pid):
    stat = Path(f"/proc/{pid}/stat")
    if not stat.exists(): return False
    try: return stat.read_text().rsplit(") ", 1)[1][0] != "Z"
    except Exception: return True


def wait_pid(pid, timeout, interval):
    deadline = time.time() + timeout
    while pid_active(pid):
        if time.time() >= deadline: raise TimeoutError(f"download PID {pid} still active after {timeout}s")
        time.sleep(interval)


def run_step(steps, name, arguments):
    started = time.time()
    completed = subprocess.run(arguments, cwd=REPO, env={**os.environ, "PYTHONPATH": str(REPO)})
    step = {"name": name, "arguments": [str(item) for item in arguments],
            "returncode": completed.returncode, "elapsed_seconds": time.time() - started}
    steps.append(step)
    if completed.returncode != 0: raise RuntimeError(f"step failed: {name}: {completed.returncode}")


def require_complete_manifest(path, source_id, count):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    records = [item for item in manifest["records"] if item["source_id"] == source_id]
    if manifest["status"] != "complete" or manifest["failures"] or len(records) != count:
        raise RuntimeError(f"download manifest not complete: status={manifest['status']}, records={len(records)}, failures={len(manifest['failures'])}")
    return manifest


def finalize_rnarl(steps):
    manifest_path = AUDITS / "rnarl_download_manifest.json"
    require_complete_manifest(manifest_path, "rnarl_v1", 21)
    raw = DATA / "raw/rnarl_v1"
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    specs = next(item["files"] for item in config["sources"] if item["source_id"] == "rnarl_v1")
    for spec in specs:
        path = raw / spec["filename"]
        if not path.is_file() or hashlib.md5(path.read_bytes()).hexdigest().lower() != spec["expected_md5"].lower():
            raise RuntimeError(f"RNARL final failed MD5 gate: {path}")
    run_step(steps, "freeze_exact_bytes", [PYTHON, REPO / "scripts/a8_rk03_freeze_rnarl_bytes.py",
        "--config", CONFIG, "--raw-dir", raw, "--output", AUDITS / "rnarl_official_file_sizes_final.json", "--write-config"])
    reverify_manifest_path = AUDITS / "rnarl_reverify_download_manifest.json"
    run_step(steps, "reverify_download_with_bytes", [PYTHON, REPO / "scripts/a8_rk03_download.py",
        "--config", CONFIG, "--data-root", DATA, "--manifest", reverify_manifest_path, "--source-id", "rnarl_v1",
        "--timeout", "120", "--retries", "3", "--workers", "3"])
    require_complete_manifest(reverify_manifest_path, "rnarl_v1", 21)
    qc_dir = DATA / "clean/rnarl_v2"
    run_step(steps, "full_rnarl_qc", [PYTHON, REPO / "scripts/a8_rk03_rnarl_qc.py",
        "--config", CONFIG, "--raw-dir", raw, "--output-dir", qc_dir, "--audit", AUDITS / "rnarl_qc.json"])
    verification_path = AUDITS / "rnarl_independent_verification.json"
    run_step(steps, "independent_rnarl_verifier", [PYTHON, REPO / "scripts/a8_rk03_verify_rnarl.py",
        "--config", CONFIG, "--raw-dir", raw, "--qc-dir", qc_dir, "--audit", verification_path,
        "--production-script", REPO / "scripts/a8_rk03_rnarl_qc.py"])
    summary = json.loads((qc_dir / "qc_summary.json").read_text(encoding="utf-8"))
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    return {"rows": summary["total_rows"], "clean_rows": summary["clean_rows"], "clean_pairs": summary["clean_pairs"],
            "processed_files": summary["processed_file_count"], "bounded_pair_table_ready": summary["bounded_lineardesign_pair_table_ready_pending_verifier"],
            "natural_distribution_eligible": summary["natural_distribution_eligible"], "functional_training_authorized": False,
            "raw_split_overlap_detected": summary["raw_split_overlap_detected"], "verification_status": verification["status"],
            "verification_checks": f"{verification['passed_checks']}/{verification['check_count']}",
            "config_sha256": sha256(CONFIG), "qc_summary_sha256": sha256(qc_dir / "qc_summary.json"),
            "recovery_download_manifest_sha256": sha256(manifest_path),
            "reverify_download_manifest_sha256": sha256(reverify_manifest_path)}


def finalize_codontransformer(steps):
    manifest_path = AUDITS / "codontransformer_download_manifest.json"
    require_complete_manifest(manifest_path, "codontransformer_training", 1)
    raw = DATA / "raw/codontransformer_training/dataset.csv"
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    spec = next(item["files"][0] for item in config["sources"] if item["source_id"] == "codontransformer_training")
    if not raw.is_file() or raw.stat().st_size != int(spec["expected_bytes"]) or sha256(raw) != spec["expected_sha256"]:
        raise RuntimeError("CodonTransformer final failed byte/SHA256 gate")
    qc_dir = DATA / "clean/codontransformer_v1"
    run_step(steps, "full_codontransformer_qc", [PYTHON, REPO / "scripts/a8_rk03_codontransformer_qc.py",
        "--config", CONFIG, "--raw", raw, "--output-dir", qc_dir, "--audit", AUDITS / "codontransformer_qc.json"])
    verification_path = AUDITS / "codontransformer_independent_verification.json"
    run_step(steps, "independent_codontransformer_verifier", [PYTHON, REPO / "scripts/a8_rk03_verify_codontransformer.py",
        "--config", CONFIG, "--raw", raw, "--qc-dir", qc_dir, "--audit", verification_path,
        "--production-script", REPO / "scripts/a8_rk03_codontransformer_qc.py"])
    summary = json.loads((qc_dir / "qc_summary.json").read_text(encoding="utf-8"))
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    return {"rows": summary["raw_rows"], "clean_rows": summary["clean_rows"],
            "raw_organisms": summary["raw_organism_count"], "clean_organisms": summary["clean_organism_count"],
            "publisher_scope_matches": summary["publisher_scope_matches_independent_count"],
            "bounded_natural_sequence_distribution_ready": verification["bounded_natural_sequence_distribution_ready"],
            "functional_training_authorized": False, "verification_status": verification["status"],
            "verification_checks": f"{verification['passed_checks']}/{verification['check_count']}",
            "raw_sha256": sha256(raw), "qc_summary_sha256": sha256(qc_dir / "qc_summary.json")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["rnarl", "codontransformer"])
    parser.add_argument("--download-pid", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=10800)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = {"schema_version": "a8-rk03-finalization-v1", "mode": args.mode, "download_pid": args.download_pid,
              "started_at": now(), "status": "RUNNING", "steps": []}
    try:
        wait_pid(args.download_pid, args.timeout_seconds, args.poll_seconds)
        result = finalize_rnarl(report["steps"]) if args.mode == "rnarl" else finalize_codontransformer(report["steps"])
        report["result"] = result; report["status"] = "PASS"
    except Exception as exc:
        report["status"] = "FAIL"; report["error"] = f"{type(exc).__name__}: {exc}"
    report["finished_at"] = now()
    atomic_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
