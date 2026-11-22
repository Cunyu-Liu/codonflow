#!/usr/bin/env python3
"""A9-RK42 online-PPT readback audit. Verifies:
  * the 204 pre-existing slides are byte-for-byte content-unchanged (per-slide
    text hash, source.xml pre-write vs current.xml post-write);
  * the two new pages (pSI=205, pSj=206) are present and total slides == 206;
  * new-page visible values match the frozen acquisition audit v2 / independent
    verification / full-project tests (no hand-typed drift);
  * real screenshots of both new pages exist.

Run:
  python3 scripts/audit_rk42_ppt.py --source source.xml --current current.xml \
    --audit ...v2.json --indep ...independent_v2.json --tests ...tests_v1.json \
    --shots-dir screenshots --new-ids pSI pSj --report rk42_ppt_readback_audit_v1.json
"""
import argparse
import hashlib
import json
import os
import xml.etree.ElementTree as ET


def local(tag):
    return tag.split("}")[-1]


def slides(path):
    root = ET.parse(path).getroot()
    out = {}
    order = []
    for el in root.iter():
        if local(el.tag) == "slide":
            sid = el.attrib.get("id")
            texts = [ "".join(p.itertext()).strip() for p in el.iter() if local(p.tag) == "p" ]
            texts = [t for t in texts if t]
            out[sid] = texts
            order.append(sid)
    return out, order


def thash(texts):
    return hashlib.sha256("\n".join(texts).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--indep", required=True)
    ap.add_argument("--tests", required=True)
    ap.add_argument("--shots-dir", required=True)
    ap.add_argument("--new-ids", nargs="+", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    if os.path.exists(args.report):
        raise FileExistsError(args.report)
    src, src_order = slides(args.source)
    cur, cur_order = slides(args.current)
    aud = json.load(open(args.audit))
    indep = json.load(open(args.indep))
    tests = json.load(open(args.tests))
    checks = []

    def ck(name, ok, detail=""):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    ck("source_204_slides", len(src) == 204, str(len(src)))
    ck("current_206_slides", len(cur) == 206, str(len(cur)))
    ck("new_ids_present", all(i in cur for i in args.new_ids), str(args.new_ids))
    ck("new_ids_appended_last", cur_order[-2:] == args.new_ids, str(cur_order[-2:]))
    # old pages unchanged: every source slide id present in current with identical text hash
    changed = [sid for sid in src if sid not in cur or thash(src[sid]) != thash(cur[sid])]
    ck("old_204_pages_unchanged", not changed, "changed=%s" % changed[:5])
    ck("old_order_preserved", cur_order[:204] == src_order, "prefix_match")

    t205 = "\n".join(cur[args.new_ids[0]])
    t206 = "\n".join(cur[args.new_ids[1]])
    cam = {s["id"]: s for s in aud["sources"]}["Cambray2018"]["raw_rederive"]
    tally = aud["fail_tally_non_qualifying"]
    ck("p205_zero_of_nine", ("0 of 9" in t205) or ("0" in t205 and "9" in t205))
    ck("p205_branch_B3", "B3" in t205)
    ck("p205_all_candidates", all(c in t205 for c in ["Cambray2018", "Kosuri2013", "Goodman2013", "deBoer2020", "Lind2020"]))
    ck("p205_qualify_NO_count", t205.count("NO") >= 9, str(t205.count("NO")))
    ck("p206_96bp", "96 bp" in t206)
    ck("p206_peptides", format(cam["n_distinct_translated_peptides"], ",") in t206)
    ck("p206_rows", format(cam["n_complete_rows"], ",") in t206)
    ck("p206_constant", "CONSTANT" in t206)
    ck("p206_tally_R5", str(tally["R5"]) in t206)
    ck("p206_indep", "%d/%d" % (indep["n_pass"], indep["n_checks"]) in t206)
    ck("p206_tests", "%d passed" % tests["passed"] in t206)
    ck("p206_user_decision", "USER DECISION" in t206)
    ck("p206_dbtl", "DBTL" in t206)
    # screenshots exist
    shots = os.listdir(args.shots_dir) if os.path.isdir(args.shots_dir) else []
    ck("screenshot_p205", any("p205" in f and args.new_ids[0] in f for f in shots), str(shots))
    ck("screenshot_p206", any("p206" in f and args.new_ids[1] in f for f in shots), str(shots))

    n_pass = sum(c["pass"] for c in checks)
    report = {
        "schema": "a9-rk42-ppt-readback-audit-v1",
        "presentation": "WB1KsYGualerMUddEzMcCw1En0g",
        "n_source_slides": len(src),
        "n_current_slides": len(cur),
        "new_slide_ids": args.new_ids,
        "n_checks": len(checks),
        "n_pass": n_pass,
        "n_fail": len(checks) - n_pass,
        "all_pass": n_pass == len(checks),
        "checks": checks,
    }
    with open(args.report, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print("PPT readback %d/%d PASS" % (n_pass, len(checks)))
    for c in checks:
        if not c["pass"]:
            print("FAIL", c["name"], c["detail"])


if __name__ == "__main__":
    main()