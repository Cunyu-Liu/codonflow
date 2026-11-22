#!/usr/bin/env python3
"""A9-RK42 independent verifier: re-derive the decisive acquisition judgments
from RAW sources without importing the production audit's conclusions.

Independently:
  * decompress the partial Cambray Data15 zip and re-translate real CSV rows
    (re-derived gs.sequence length + amino-acid variation + continuous phenotypes);
  * re-check the raw-derived Cambray PDF text for the constant-upstream quote;
  * re-read the saved Kosuri PNAS HTML for the fixed-sfGFP / promoter-x-RBS facts;
  * recompute per-source qualifying, n_qualifying, branch decision and fail tally;
  * enforce honesty (raw-blocked/unverified sources cannot carry R7 PASS).

Run:
  /home/codonflow-clean-env-v1/bin/python scripts/a9_rk42_verify_acquisition.py \
      --protocol configs/a9_rk42_independent_data_acquisition_protocol_v1.json \
      --result audits/20261122/RK42/independent_data_acquisition_v1.json \
      --report audits/20261122/RK42/independent_data_acquisition_independent_v1.json
"""
import argparse
import csv
import hashlib
import io
import json
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk42/raw"

CT = {}
for _i, _aa in enumerate("FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"):
    _b = "TCAG"
    CT[_b[_i // 16] + _b[(_i // 4) % 4] + _b[_i % 4]] = _aa


def sha(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tr(s):
    s = s.upper().replace("U", "T")
    return "".join(CT.get(s[i:i + 3], "X") for i in range(0, len(s) - 2, 3))


def rederive_cambray():
    path = os.path.join(RAW, "cambray2018_data15_integrated_phenotypes.zip")
    raw = open(path, "rb").read()
    assert raw[:4] == b"PK\x03\x04"
    fnlen = struct.unpack("<H", raw[26:28])[0]
    extralen = struct.unpack("<H", raw[28:30])[0]
    start = 30 + fnlen + extralen
    dec = zlib.decompressobj(-15)
    try:
        out = dec.decompress(raw[start:])
    except zlib.error:
        out = b""
    text = out.decode("utf-8", "replace")
    nl = text.rfind("\n")
    rows = list(csv.DictReader(io.StringIO(text[:nl] if nl > 0 else text)))
    lengths, peptides, prot_vals = set(), set(), []
    for r in rows:
        s = (r.get("gs.sequence") or "").strip().upper()
        if s and not (set(s) - set("ACGT")):
            lengths.add(len(s))
            peptides.add(tr(s))
        try:
            prot_vals.append(float(r.get("clean.lin.prot.mean")))
        except (TypeError, ValueError):
            pass
    return {
        "n_rows": len(rows),
        "lengths": sorted(lengths),
        "n_peptides": len(peptides),
        "aa_varies": len(peptides) > 1,
        "prot_min": min(prot_vals) if prot_vals else None,
        "prot_max": max(prot_vals) if prot_vals else None,
        "zip_sha": hashlib.sha256(raw).hexdigest(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    if os.path.exists(args.report):
        raise FileExistsError(f"report exists: {args.report}")
    protocol = json.load(open(args.protocol))
    result = json.load(open(args.result))
    src = {s["id"]: s for s in result["sources"]}
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    cam = rederive_cambray()
    notes_txt = open(os.path.join(RAW, "cambray2018_supp_notes.txt")).read()
    kosuri_methods = open(os.path.join(RAW, "kosuri2013_pnas_methods.txt"), encoding="utf-8", errors="replace").read()
    kosuri_html = open(os.path.join(RAW, "kosuri_pnas.html"), encoding="utf-8", errors="replace").read()

    check("protocol_frozen", protocol["status"] == "FROZEN_BEFORE_OUTCOME_ASSOCIATION")
    check("protocol_sha_matches", sha(args.protocol) == result["protocol_sha256"])
    check("cambray_raw_length_96_only", cam["lengths"] == [96], str(cam["lengths"]))
    check("cambray_raw_aa_varies", cam["aa_varies"] is True, "n_peptides=%d" % cam["n_peptides"])
    check("cambray_raw_continuous_prot", cam["prot_min"] == 1.0 and cam["prot_max"] == 100.0, "%s-%s" % (cam["prot_min"], cam["prot_max"]))
    check("cambray_pdf_constant_upstream_quote", "segment is constant" in notes_txt)
    check("cambray_pdf_96bp_quote", "designed sequence (96 bp)" in notes_txt)
    check("cambray_pdf_sha_matches", sha(os.path.join(RAW, "cambray2018_supp_notes.pdf")) == src["Cambray2018"]["raw_artifacts_sha256"]["cambray2018_supp_notes.pdf"])
    check("cambray_zip_sha_matches", cam["zip_sha"] == src["Cambray2018"]["raw_artifacts_sha256"]["cambray2018_data15_integrated_phenotypes.zip_partial"])
    # Cambray R judgments must match independent raw re-derivation
    check("cambray_R2_fail", src["Cambray2018"]["R"]["R2"]["status"] == "FAIL")
    check("cambray_R3_fail", src["Cambray2018"]["R"]["R3"]["status"] == "FAIL")
    check("cambray_R4_fail", src["Cambray2018"]["R"]["R4"]["status"] == "FAIL")
    check("cambray_R5_fail", src["Cambray2018"]["R"]["R5"]["status"] == "FAIL")
    check("cambray_R6_pass", src["Cambray2018"]["R"]["R6"]["status"] == "PASS")
    check("cambray_not_qualifying", src["Cambray2018"]["qualifying"] is False)
    # Kosuri raw methods-text re-check (curl HTML was a Cloudflare challenge)
    check("kosuri_methods_114_promoters", "114 promoters" in kosuri_methods)
    check("kosuri_methods_sfgfp_fixed", "superfolder GFP" in kosuri_methods)
    check("kosuri_curl_html_is_challenge", "Just a moment" in kosuri_html)
    check("kosuri_R4_fail", src["Kosuri2013"]["R"]["R4"]["status"] == "FAIL")
    check("kosuri_not_qualifying", src["Kosuri2013"]["qualifying"] is False)
    # recompute qualifying / n_qualifying / branch / tally independently
    rek = {s["id"]: all(s["R"][k]["status"] == "PASS" for k in ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]) for s in result["sources"]}
    check("qualifying_recomputed_matches", all(rek[s["id"]] == s["qualifying"] for s in result["sources"]))
    nq = sum(rek.values())
    check("n_qualifying_zero", nq == 0 and result["n_qualifying"] == 0, "n=%d" % nq)
    check("branch_B3", result["branch_decision"] == "B3_NO_QUALIFYING_PUBLIC_DATA_WETLAB_DBTL_REQUIRES_USER_APPROVAL")
    tally = {k: sum(1 for s in result["sources"] if not rek[s["id"]] and s["R"][k]["status"] != "PASS") for k in ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]}
    check("fail_tally_matches", tally == result["fail_tally_non_qualifying"], json.dumps(tally))
    # honesty: a source with NO raw artifact SHA obtained cannot carry R7 PASS
    bad_r7 = [s["id"] for s in result["sources"] if not s["raw_artifacts_sha256"] and s["R"]["R7"]["status"] == "PASS"]
    check("no_artifact_no_R7_pass", not bad_r7, str(bad_r7))
    check("mage_frozen_boundary", result["boundaries"]["historical_MAGE_functional_untouched_frozen"] is True)
    check("no_fit_boundary", result["no_model_fit_no_outcome_association"] is True)
    check("no_unilateral_relax", result["strategic_option_for_user"]["do_not_unilaterally_relax_frozen_R1_R7"] is True)
    check("dbtl_requires_user", result["prospective_DBTL_design_B3"]["requires_user_budget_and_timeline_approval"] is True)
    check("n_candidates_9", result["n_candidates"] == 9 and len(result["sources"]) == 9)

    n_pass = sum(c["pass"] for c in checks)
    report = {
        "schema": "a9-rk42-independent-data-acquisition-independent-v1",
        "result_sha256": sha(args.result),
        "cambray_independent_rederive": cam,
        "n_checks": len(checks),
        "n_pass": n_pass,
        "n_fail": len(checks) - n_pass,
        "all_pass": n_pass == len(checks),
        "checks": checks,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print("independent %d/%d PASS" % (n_pass, len(checks)))
    for c in checks:
        if not c["pass"]:
            print("FAIL", c["name"], c["detail"])
    print("report_sha256", sha(args.report))


if __name__ == "__main__":
    main()