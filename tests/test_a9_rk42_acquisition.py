"""Targeted contract tests for A9-RK42 independent-data acquisition audit.

Project style: real logic checks (eligibility rule, branch rule, source verdicts,
honesty of raw-access vs R7), not import-only or shape-only tests.
"""
import os
import sys

import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)
import a9_rk42_acquisition_audit as aud  # noqa: E402


def _src(**r):
    base = {k: {"status": "PASS", "evidence": ""} for k in aud.R_KEYS}
    base.update({k: {"status": v, "evidence": ""} for k, v in r.items()})
    return {"R": base}


def test_qualify_iff_all_seven_pass():
    assert aud.is_qualifying(_src()) is True
    for k in aud.R_KEYS:
        assert aud.is_qualifying(_src(**{k: "FAIL"})) is False


def test_branch_rule():
    assert aud.decide_branch(0).startswith("B3_NO_QUALIFYING_PUBLIC_DATA")
    assert aud.decide_branch(1).startswith("B2_QUALIFYING_PUBLIC_DATA")
    assert aud.decide_branch(3).startswith("B2_QUALIFYING_PUBLIC_DATA")


def test_nine_candidates_zero_qualifying():
    sources = aud.build_sources()
    assert len(sources) == 9
    ids = {s["id"] for s in sources}
    assert {"Cambray2018", "Kosuri2013", "Goodman2013", "deBoer2020", "Lind2020"} <= ids
    assert sum(s["qualifying"] for s in sources) == 0


def test_cambray_fails_R2_R3_R4_R5_passes_R6():
    s = {x["id"]: x for x in aud.build_sources()}["Cambray2018"]
    assert s["R"]["R2"]["status"] == "FAIL"  # 96-bp segment, not full CDS
    assert s["R"]["R3"]["status"] == "FAIL"  # constant upstream leader
    assert s["R"]["R4"]["status"] == "FAIL"  # amino-acid variation
    assert s["R"]["R5"]["status"] == "FAIL"  # single reporter
    assert s["R"]["R6"]["status"] == "PASS"  # continuous phenotypes
    assert s["qualifying"] is False


def test_regulatory_libraries_fail_R4():
    s = {x["id"]: x for x in aud.build_sources()}
    for cid in ["Kosuri2013", "Mutalik2013", "Salis2011", "EspahBorujeni2014_2017", "deBoer2020"]:
        assert s[cid]["R"]["R4"]["status"] == "FAIL", cid


def test_lind_synonymous_but_insufficient_scale():
    s = {x["id"]: x for x in aud.build_sources()}["Lind2020"]
    assert s["R"]["R4"]["status"] == "PASS"  # genuine fixed-protein synonymous
    assert s["R"]["R5"]["status"] == "FAIL"  # single gene, no family map
    assert s["qualifying"] is False


def test_no_raw_artifact_cannot_pass_R7():
    for s in aud.build_sources():
        if not s["raw_artifacts_sha256"]:
            assert s["R"]["R7"]["status"] != "PASS", s["id"]


def test_every_source_has_seven_requirements():
    for s in aud.build_sources():
        assert set(s["R"].keys()) == set(aud.R_KEYS)
        for k in aud.R_KEYS:
            assert s["R"][k]["status"] in ("PASS", "FAIL")
            assert s["R"][k]["evidence"]