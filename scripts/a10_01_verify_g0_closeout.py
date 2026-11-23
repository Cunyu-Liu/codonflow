#!/usr/bin/env python3
"""Independently verify A10-G0 closeout using only declared report JSON files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath


VERIFICATION_PROTOCOL = "a10_01_g0_closeout_independent_verification_v1"
CLOSEOUT_PROTOCOL = "a10_01_g0_closeout_protocol_v1"
PROTOCOL_SCHEMA = "a10-01-g0-closeout-protocol-v1"
CLOSEOUT_SCHEMA = "a10-01-g0-closeout-result-v1"
DEFAULT_PROTOCOL = Path(__file__).resolve().parents[1] / "configs" / "a10_01_g0_closeout_protocol_v1.json"
PASS_TOKEN = "A10_G0=PASS_DATA_AND_BASELINE_READY"
FAIL_TOKEN = "A10_G0=FAIL_DATA_AND_BASELINE_NOT_READY"
REQUIRED_REPORT_IDS = (
    "goodman_e0_v3_report",
    "goodman_e0_v3_independent",
    "goodman_split_independent_v3",
    "goodman_baseline_independent_v2",
    "tunney_e0_report",
    "tunney_e0_independent",
    "codontransformer_gpu_report",
    "codontransformer_gpu_independent",
    "ixnos_bounded_finalization",
    "rose_bounded_finalization",
    "veloharmo_bounded_finalization",
    "ribomimo_bounded_finalization",
    "ensembledesign_bounded_finalization",
    "lineardesign_bounded_finalization",
    "rnarl_negative_availability",
)
DIRECT_EXECUTION_REPORT_IDS = (
    "goodman_baseline_independent_v2",
    "codontransformer_gpu_report",
    "codontransformer_gpu_independent",
    "ixnos_bounded_finalization",
    "rose_bounded_finalization",
    "veloharmo_bounded_finalization",
    "ribomimo_bounded_finalization",
    "ensembledesign_bounded_finalization",
    "lineardesign_bounded_finalization",
)
EXPECTED_REPORT_SHA256 = {
    "goodman_e0_v3_report": "3036961a32502c1ea7a9bf6cd45f2ffbb0cadf2d18ff8f3405b4abd4bb1a6304",
    "goodman_e0_v3_independent": "c78359d03a45f3bbbcc867f36be8b2c74219a9410c543a90d08e8784a6bf42ab",
    "goodman_split_independent_v3": "379ef698d8f0029d929468c94bcdf594bd83384e957fcc31e4e66d46b4fc2f43",
    "goodman_baseline_independent_v2": "384519f7bfc4a6cd574694bee838176b6f4d0c871367c4a567bfffd30828e5a4",
    "tunney_e0_report": "9fecfb838762950b2545f6db4fb0d6ba4ab92cc9483aad20c33cd1f0d8abf9b9",
    "tunney_e0_independent": "0ea53ae7a35a55f4fb946e216b157de943784ac885368f72050e40080b547285",
    "codontransformer_gpu_report": "dc9b72aa678576229e3c9477e184e2f3878eafea87d4bcac3a7d3f50b65c951f",
    "codontransformer_gpu_independent": "c22d234304cc8c5c9e4156cbeddbaa732fcfd76ecee5276429cdceb6b74db0bf",
    "ixnos_bounded_finalization": "a3fb63540d59e5f76cebcbea555bf1a4c063b19c4d3917e48304c94ef3ab1c28",
    "rose_bounded_finalization": "c1733d1c937af26892fbfebf6385bcd9ca80b9825bd07f7597e7188716d48817",
    "veloharmo_bounded_finalization": "c056cc6207a15d74403926c676010a0fae50d7f7a215cb0ab19ce1fd40e609c5",
    "ribomimo_bounded_finalization": "69c532e20612b7d8de83486f7c2ced7961ac416f7c3e5218946f2804956407d8",
    "ensembledesign_bounded_finalization": "226cf4b15b0bdfac35a846941fc17986e5f1f3a76851ed33e106946d8b8a4fde",
    "lineardesign_bounded_finalization": "9a5e7e92c9578e4eda1f18774a8a21de2c8abc6bfda076f3ccafcc0a8fe61f79",
    "rnarl_negative_availability": "065215732f57a601431949220a4f4a25e7219d5f0cf7b22e3064288c87fdb47b",
}
A10_REPORT_IDS = frozenset(REQUIRED_REPORT_IDS[:8])
TOP_LEVEL_PASSED_REQUIRED_IDS = frozenset({
    "goodman_e0_v3_independent",
    "goodman_split_independent_v3",
    "goodman_baseline_independent_v2",
    "tunney_e0_independent",
    "codontransformer_gpu_independent",
})
A10_ROOT_PATTERN = re.compile(r"^/teams/(?:[^/]+/)*codonflow1031/a10/e0$")
HISTORICAL_ROOT = "/home/codonflow-a8-rk/audits/20261118/RK05"
GATE_CONTRACT = {
    "pass_token": PASS_TOKEN,
    "fail_token": FAIL_TOKEN,
    "final_untouched": False,
    "cross_study_H1_proven": False,
    "cross_study_H2_proven": False,
    "E3_proven": False,
    "G2_proven": False,
    "SOTA": False,
    "generation_training_allowed": False,
    "generation_training_requires_G2": True,
}
EXCLUSIONS = {
    "rnarl_counts_as_runnable": False,
    "rnarl_evidence": "negative_availability_only",
    "id3_cpc_trajectories": "excluded",
    "id3_cpc_report_required": False,
}
EXECUTION_CONTRACT = {
    "input_kind": "existing_report_json_only",
    "local_inputs": "synthetic_json_only",
    "scientific_rerun": False,
    "raw_data_reads": False,
    "untouched_reads": False,
    "remote_paths_are_provenance_only": True,
    "report_root_argument_required": True,
    "overwrite": "forbidden",
    "creation_mode": "exclusive",
}
MISSING = object()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(payload):
    return (json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def write_json_exclusive(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical_json_bytes(payload))


def reject_constant(value):
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="strict") as handle:
        payload = json.load(handle, parse_constant=reject_constant, object_pairs_hook=unique_object)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def require_boolean(mapping, key):
    if type(mapping.get(key)) is not bool:
        raise ValueError(f"protocol {key} must be boolean")


def load_protocol(path, synthetic=False):
    protocol = load_json(path)
    if protocol.get("schema") != PROTOCOL_SCHEMA or protocol.get("protocol") != CLOSEOUT_PROTOCOL:
        raise ValueError(f"closeout protocol identity mismatch: expected {CLOSEOUT_PROTOCOL}")
    if protocol.get("status") != "frozen_report_only_closeout":
        raise ValueError("closeout protocol must be frozen")
    if protocol.get("execution") != EXECUTION_CONTRACT:
        raise ValueError("protocol execution is not report-only, synthetic-local and non-overwriting")
    if protocol.get("gate_contract") != GATE_CONTRACT or protocol.get("exclusions") != EXCLUSIONS:
        raise ValueError("protocol gate boundaries or exclusions differ from the frozen contract")
    if protocol.get("required_report_ids") != list(REQUIRED_REPORT_IDS):
        raise ValueError("protocol required_report_ids does not match the frozen closeout set")
    if protocol.get("direct_execution_report_ids") != list(DIRECT_EXECUTION_REPORT_IDS):
        raise ValueError("protocol direct-execution set does not match the frozen closeout set")
    reports = protocol.get("reports")
    if not isinstance(reports, list) or len(reports) != len(REQUIRED_REPORT_IDS):
        raise ValueError(f"protocol must contain exactly {len(REQUIRED_REPORT_IDS)} reports")
    roots = protocol.get("report_roots")
    if not isinstance(roots, dict) or set(roots) != {"a10_e0", "historical_rk05"}:
        raise ValueError("protocol must declare exactly the A10 and historical report roots")
    if A10_ROOT_PATTERN.fullmatch(roots["a10_e0"]) is None:
        raise ValueError("A10 reports must be under /teams/.../codonflow1031/a10/e0")
    if roots["historical_rk05"] != HISTORICAL_ROOT:
        raise ValueError("historical reports must be under the frozen RK05 root")
    seen = set()
    for spec in reports:
        if not isinstance(spec, dict):
            raise ValueError("every report specification must be an object")
        report_id = spec.get("id")
        if report_id not in REQUIRED_REPORT_IDS or report_id in seen:
            raise ValueError(f"unknown or duplicate report id: {report_id}")
        seen.add(report_id)
        relative = PurePosixPath(spec.get("relative_path", ""))
        absolute = PurePosixPath(spec.get("absolute_path", ""))
        root_name = "a10_e0" if report_id in A10_REPORT_IDS else "historical_rk05"
        if any((
            relative.is_absolute(),
            not relative.parts,
            any(part in ("", ".", "..") for part in relative.parts),
            relative.suffix != ".json",
            not absolute.is_absolute(),
            absolute.suffix != ".json",
            absolute != PurePosixPath(roots[root_name]) / relative,
        )):
            raise ValueError(f"invalid or out-of-root report paths for {report_id}")
        sha256 = spec.get("sha256", "")
        if re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
            raise ValueError(f"report SHA256 must be lowercase hexadecimal for {report_id}")
        if not synthetic and sha256 != EXPECTED_REPORT_SHA256[report_id]:
            raise ValueError(f"frozen report SHA256 mismatch in protocol for {report_id}")
        for key in ("passed_required", "status_required", "checks_required"):
            require_boolean(spec, key)
        if report_id in TOP_LEVEL_PASSED_REQUIRED_IDS and spec["passed_required"] is not True:
            raise ValueError(f"A10 independent report must require top-level passed: {report_id}")
        if not isinstance(spec.get("role"), str) or not spec["role"]:
            raise ValueError(f"report role is missing for {report_id}")
        statuses = spec.get("accepted_statuses")
        if not isinstance(statuses, list) or any(not isinstance(value, str) for value in statuses):
            raise ValueError(f"accepted_statuses must be a string list for {report_id}")
        required_checks = spec.get("required_checks")
        if (
            not isinstance(required_checks, list)
            or any(not isinstance(value, str) or not value for value in required_checks)
            or len(set(required_checks)) != len(required_checks)
        ):
            raise ValueError(f"required_checks must be a unique string list for {report_id}")
        expected = spec.get("expected")
        if not isinstance(expected, dict) or any(
            not isinstance(pointer, str) or not pointer.startswith("/") for pointer in expected
        ):
            raise ValueError(f"expected must contain JSON pointers for {report_id}")
    if seen != set(REQUIRED_REPORT_IDS):
        raise ValueError("protocol report set is incomplete")
    return protocol


def pointer_value(payload, pointer):
    current = payload
    for raw_part in pointer.lstrip("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if part not in current:
                return MISSING
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return MISSING
    return current


def strict_equal(observed, expected):
    if isinstance(expected, dict):
        return (
            isinstance(observed, dict)
            and set(observed) == set(expected)
            and all(strict_equal(observed[key], value) for key, value in expected.items())
        )
    if isinstance(expected, list):
        return (
            isinstance(observed, list)
            and len(observed) == len(expected)
            and all(strict_equal(left, right) for left, right in zip(observed, expected))
        )
    return type(observed) is type(expected) and observed == expected


def normalize_checks(checks):
    if isinstance(checks, dict):
        return checks, bool(checks) and all(value is True for value in checks.values())
    if not isinstance(checks, list) or not checks:
        return None, False
    normalized = {}
    checks_ok = True
    for item in checks:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
            checks_ok = False
            continue
        name = item["name"]
        flags = [item[key] for key in ("pass", "passed") if key in item]
        item_ok = bool(flags) and all(value is True for value in flags)
        if name in normalized:
            checks_ok = False
        normalized[name] = item_ok
        checks_ok = checks_ok and item_ok
    return normalized, checks_ok


def evaluate_report(spec, payload):
    errors = []
    passed_present = "passed" in payload
    passed_ok = payload.get("passed") is True if passed_present else not spec["passed_required"]
    if not passed_ok:
        errors.append("passed must be true" if passed_present else "passed is required")
    status = payload.get("status", MISSING)
    accepted = {value.casefold() for value in spec["accepted_statuses"]}
    status_ok = (
        isinstance(status, str) and status.strip().casefold() in accepted
        if status is not MISSING else not spec["status_required"]
    )
    if not status_ok:
        errors.append("status is not an accepted passing status")
    checks = payload.get("checks", MISSING)
    if checks is MISSING:
        checks_ok = not spec["checks_required"]
        normalized_checks = None
    else:
        normalized_checks, checks_ok = normalize_checks(checks)
    if not checks_ok:
        errors.append(
            "checks must be a nonempty true-value object or a nonempty list of named pass/passed items"
        )
    missing_checks = [
        name for name in spec["required_checks"]
        if not isinstance(normalized_checks, dict) or normalized_checks.get(name) is not True
    ]
    if missing_checks:
        errors.append(f"required checks are missing or false: {missing_checks}")
    mismatches = []
    for pointer, expected in spec["expected"].items():
        observed = pointer_value(payload, pointer)
        if observed is MISSING or not strict_equal(observed, expected):
            mismatches.append({
                "pointer": pointer,
                "expected": expected,
                "observed": None if observed is MISSING else observed,
            })
    if mismatches:
        errors.append("required report semantics do not match")
    return {
        "passed_present": passed_present,
        "passed": None if not passed_present else payload.get("passed"),
        "passed_ok": passed_ok,
        "status": None if status is MISSING else status,
        "status_ok": status_ok,
        "checks": normalized_checks,
        "checks_ok": checks_ok,
        "required_checks_ok": not missing_checks,
        "missing_or_failed_required_checks": missing_checks,
        "semantic_ok": not mismatches,
        "semantic_mismatches": mismatches,
        "errors": errors,
    }


def inspect_report(spec, report_root):
    path = report_root / Path(*PurePosixPath(spec["relative_path"]).parts)
    record = {
        "id": spec["id"],
        "role": spec["role"],
        "relative_path": spec["relative_path"],
        "declared_absolute_path": spec["absolute_path"],
        "input_path": str(path),
        "expected_sha256": spec["sha256"],
        "actual_sha256": None,
        "hash_ok": False,
        "json_ok": False,
        "report_ok": False,
    }
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(report_root) or not resolved.is_file():
            raise ValueError("report must be a regular JSON file inside report-root")
        record["actual_sha256"] = file_sha256(resolved)
        record["hash_ok"] = record["actual_sha256"] == spec["sha256"]
        payload = load_json(resolved)
        record["json_ok"] = True
        record.update(evaluate_report(spec, payload))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
    record["report_ok"] = (
        record["hash_ok"]
        and record["json_ok"]
        and all(record.get(field) is True for field in (
            "passed_ok", "status_ok", "checks_ok", "required_checks_ok", "semantic_ok",
        ))
    )
    return record


def recompute_gate(protocol, records):
    by_id = {record["id"]: record for record in records}

    def group(*ids):
        return all(by_id[report_id]["report_ok"] for report_id in ids)

    return {
        "all_report_files": all(record["report_ok"] for record in records),
        "real_functional_raw_and_qc": group("goodman_e0_v3_report", "goodman_e0_v3_independent"),
        "no_leak_nested_split": group("goodman_split_independent_v3"),
        "baseline_predictions": group("goodman_baseline_independent_v2"),
        "development_ribo_and_tunney_candidates": group("tunney_e0_report", "tunney_e0_independent"),
        "direct_baseline_real_execution": group(*DIRECT_EXECUTION_REPORT_IDS),
        "rnarl_negative_availability_only": group("rnarl_negative_availability"),
        "id3_cpc_trajectories_excluded": protocol["exclusions"]["id3_cpc_trajectories"] == "excluded",
    }


def walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def forbidden_positive_claims(payload):
    forbidden = {
        "final_untouched", "untouched_read", "untouched_inputs_read",
        "cross_study_H1_proven", "cross_study_H2_proven", "cross_study_H1_H2_proven",
        "E3_proven", "G2_proven", "G3_proven", "SOTA", "sota_claim",
        "generation_training_allowed", "generator_training_started", "scientific_rerun",
        "raw_or_untouched_data_read", "mechanism_evidence", "protein_ood",
        "protein_ood_supported", "full_length_cds_supported", "native_utr_supported",
        "real_biological_generalization", "wet_lab_validated",
    }
    return sorted({
        key for node in walk_dicts(payload) for key, value in node.items()
        if key in forbidden and value is not False
    })


def closeout_boundaries_ok(closeout, gate_checks):
    return all((
        closeout.get("claim_boundaries") == GATE_CONTRACT,
        closeout.get("final_untouched") is False,
        closeout.get("cross_study_H1_H2_proven") is False,
        closeout.get("E3_proven") is False,
        closeout.get("G2_proven") is False,
        closeout.get("SOTA") is False,
        closeout.get("generation_training_allowed") is False,
        closeout.get("generation_training_constraint")
        == "G2_must_pass_before_large_scale_generation_training",
        closeout.get("scientific_rerun") is False,
        closeout.get("raw_or_untouched_data_read") is False,
        closeout.get("rnarl") == {
            "negative_availability_evidence": gate_checks["rnarl_negative_availability_only"],
            "runnable": False,
            "counts_as_runnable_baseline": False,
        },
        closeout.get("id3_cpc_trajectories") == "excluded",
        not forbidden_positive_claims(closeout),
    ))


def initial_result(protocol_path, report_root, closeout_path, synthetic, expected_closeout_sha256):
    return {
        "protocol": VERIFICATION_PROTOCOL,
        "evidence_mode": "synthetic" if synthetic else "pinned_existing_report_json",
        "inputs": {
            "protocol": str(protocol_path),
            "report_root": str(report_root),
            "closeout": str(closeout_path),
        },
        "protocol_sha256": None,
        "closeout_sha256": None,
        "expected_closeout_sha256": expected_closeout_sha256,
        "closeout_sha256_pinned": expected_closeout_sha256 is not None,
        "checks": {"protocol": False},
        "reports": [],
        "errors": [],
        "passed": False,
        "gate": FAIL_TOKEN,
        "A10_G0": "FAIL_DATA_AND_BASELINE_NOT_READY",
        "E1_start_allowed": False,
        "E2_start_allowed": False,
        "SOTA": False,
        "generation_training_allowed": False,
    }


def finalize_result(result):
    result["passed"] = bool(result["checks"]) and all(result["checks"].values())
    result["gate"] = PASS_TOKEN if result["passed"] else FAIL_TOKEN
    result["A10_G0"] = result["gate"].split("=", 1)[1]
    result["E1_start_allowed"] = result["passed"]
    result["E2_start_allowed"] = result["passed"]
    result["verifier_script_sha256"] = file_sha256(Path(__file__).resolve())
    return result


def verify_g0_closeout(
    protocol_path, report_root, closeout_path, synthetic=False, expected_closeout_sha256=None,
):
    protocol_path = Path(protocol_path).expanduser().resolve()
    report_root = Path(report_root).expanduser().resolve()
    closeout_path = Path(closeout_path).expanduser().resolve()
    result = initial_result(
        protocol_path, report_root, closeout_path, synthetic, expected_closeout_sha256,
    )
    checks = result["checks"]
    try:
        result["protocol_sha256"] = file_sha256(protocol_path)
        protocol = load_protocol(protocol_path, synthetic=synthetic)
        if closeout_path.suffix != ".json":
            raise ValueError("closeout input must be JSON")
        if expected_closeout_sha256 is not None and re.fullmatch(
            r"[0-9a-f]{64}", expected_closeout_sha256,
        ) is None:
            raise ValueError("expected closeout SHA256 must be lowercase hexadecimal")
        if not report_root.is_dir():
            raise ValueError(f"report-root is not a directory: {report_root}")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        result["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        return result
    checks["protocol"] = True

    records = [
        inspect_report(spec, report_root)
        for spec in sorted(protocol["reports"], key=lambda item: REQUIRED_REPORT_IDS.index(item["id"]))
    ]
    result["reports"] = records
    gate_checks = recompute_gate(protocol, records)
    checks.update({
        "all_report_hashes": all(record["hash_ok"] for record in records),
        "all_report_statuses": all(record.get("status_ok") is True for record in records),
        "all_report_checks": all(
            record.get("checks_ok") is True and record.get("required_checks_ok") is True
            for record in records
        ),
        "all_report_semantics": all(record.get("semantic_ok") is True for record in records),
        **gate_checks,
    })
    try:
        result["closeout_sha256"] = file_sha256(closeout_path)
        closeout = load_json(closeout_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        result["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        checks.update({
            "closeout_sha256": False,
            "closeout_protocol_sha256": False,
            "closeout_reports": False,
            "closeout_checks": False,
            "closeout_verdict": False,
            "closeout_metadata": False,
            "claim_boundaries": False,
        })
        return result

    evidence_passed = all(gate_checks.values())
    expected_gate = PASS_TOKEN if evidence_passed else FAIL_TOKEN
    expected_suffix = expected_gate.split("=", 1)[1]
    checks.update({
        "closeout_sha256": (
            expected_closeout_sha256 is None
            or result["closeout_sha256"] == expected_closeout_sha256
        ),
        "closeout_protocol_sha256": closeout.get("protocol_sha256") == result["protocol_sha256"],
        "closeout_reports": closeout.get("reports") == records,
        "closeout_checks": closeout.get("checks") == gate_checks,
        "closeout_verdict": all((
            closeout.get("passed") is evidence_passed,
            closeout.get("gate") == expected_gate,
            closeout.get("A10_G0") == expected_suffix,
            closeout.get("E1_start_allowed") is evidence_passed,
            closeout.get("E2_start_allowed") is evidence_passed,
        )),
        "closeout_metadata": all((
            closeout.get("schema") == CLOSEOUT_SCHEMA,
            closeout.get("protocol") == CLOSEOUT_PROTOCOL,
            closeout.get("evidence_mode") == result["evidence_mode"],
            closeout.get("report_root") == str(report_root),
        )),
        "claim_boundaries": closeout_boundaries_ok(closeout, gate_checks),
    })
    result["independent_closeout"] = {
        "expected_gate": expected_gate,
        "declared_gate": closeout.get("gate"),
        "expected_checks": gate_checks,
        "declared_checks": closeout.get("checks"),
    }
    return finalize_result(result)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    parser.add_argument("--report-root", required=True)
    parser.add_argument("--closeout", "--closeout-json", dest="closeout", required=True)
    parser.add_argument("--output", required=True, help="New independent verification JSON")
    parser.add_argument(
        "--closeout-sha256", "--expected-closeout-sha256",
        dest="expected_closeout_sha256", help="Optional external pin for the closeout JSON bytes",
    )
    parser.add_argument("--synthetic", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        print(f"Refusing to overwrite existing output: {output}", file=sys.stderr)
        return 2
    result = verify_g0_closeout(
        args.protocol,
        args.report_root,
        args.closeout,
        synthetic=args.synthetic,
        expected_closeout_sha256=args.expected_closeout_sha256,
    )
    try:
        write_json_exclusive(output, result)
    except FileExistsError:
        print(f"Refusing to overwrite existing output: {output}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Cannot write verification output: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "output": str(output), "passed": result["passed"], "gate": result["gate"],
        "closeout_sha256": result["closeout_sha256"], "checks": result["checks"],
    }))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
