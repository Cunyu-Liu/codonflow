#!/usr/bin/env python3
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(tag):
    return tag.rsplit("}", 1)[-1]


def semantic(node):
    return (local(node.tag), tuple(sorted(node.attrib.items())), (node.text or "").strip(), tuple(semantic(child) for child in node))


def paragraphs(root):
    return [" ".join("".join(node.itertext()).split()) for node in root.iter() if local(node.tag) == "p"]


def main():
    p = argparse.ArgumentParser()
    for name in ["source", "source-response", "candidate", "readback", "readback-response", "write-response", "preflight", "report"]:
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    source_root = ET.parse(args.source).getroot()
    current_root = ET.parse(args.readback).getroot()
    ns = source_root.tag.split("}")[0] + "}"
    old = source_root.findall(ns + "slide")
    new = current_root.findall(ns + "slide")
    candidate = ET.parse(args.candidate).getroot()
    added = new[-1]
    source_response = json.loads(args.source_response.read_text())
    readback_response = json.loads(args.readback_response.read_text())
    write_response = json.loads(args.write_response.read_text())
    preflight = json.loads(args.preflight.read_text())
    actual_text = " ".join("".join(added.itertext()).split())
    checks = []

    def check(name, condition, detail):
        checks.append({"id": name, "pass": bool(condition), "detail": detail})

    check("preflight_passed", preflight["all_pass"] and preflight["checks_passed"] == preflight["checks_total"] == 27, "27/27 before write")
    check("write_confirmed", write_response["ok"] and write_response["data"]["slide_id"] == "pgb", "single successful append, page pgb")
    check("readback_ok", readback_response["ok"], "live readback succeeded")
    check("source_baseline", source_response["data"]["revision_id"] == 48 and len(old) == 86, "86-page source baseline")
    check("page_count", len(new) == len(old) + 1 == 87, "exactly one page added")
    check("revision_advanced", readback_response["data"]["revision_id"] == 49, "revision 49")
    check("last_page_id", new[-1].get("id") == write_response["data"]["slide_id"] == "pgb", "new page is last and matches write response")
    check("old_page_ids", [s.get("id") for s in new[:-1]] == [s.get("id") for s in old], "all 86 old IDs and order unchanged")
    changed = [i + 1 for i, (a, b) in enumerate(zip(old, new[:-1])) if semantic(a) != semantic(b)]
    check("old_pages_semantically_unchanged", not changed, f"semantic XML differences on old pages: {changed}")
    expected_paragraphs = paragraphs(candidate)
    actual_paragraphs = paragraphs(added)
    check("all_candidate_paragraphs", actual_paragraphs == expected_paragraphs, f"{len(actual_paragraphs)} visible/note paragraphs reproduced in order")
    check("title", "最小 CodonFlow-RK 数学核通过精确小状态核验" in actual_text, "bounded mathematical-kernel title")
    check("state_counts", all(value in actual_text for value in ["226,981", "10,981", "181 one-step targets"]), "enumeration counts present")
    check("naive_tv", "0.324196" in actual_text, "naive endpoint TV present")
    check("path_scale", all(value in actual_text for value in ["14,641 paths", "3,721 ends"]), "path and endpoint counts present")
    check("path_error_bound", "errors <1e-12" in actual_text and "max error 0" not in actual_text and "最大误差均为零" not in actual_text, "floating-point errors bounded, never misstated as zero")
    check("event_time", "MC 0.249865 · mean 0.25" in actual_text, "event-time Monte Carlo and analytic mean")
    check("budget", "103 kept · 78 excluded" in actual_text, "preference-budget counts")
    check("verification", all(value in actual_text for value in ["22/22", "16/16", "14/14", "10 unit tests", "paper 30/30"]), "all verification layers present")
    check("failure_history", "19/22" in actual_text and "15/16" in actual_text and "failures retained" in actual_text, "initial failure history retained")
    check("boundary", all(value in actual_text for value in ["不是训练或功能性能结果", "RK-G1 未改", "生成器未授权", "SOTA 未支持"]), "no unsupported training/function/generation/SOTA claim")
    check("no_duplicate_title", sum("最小 CodonFlow-RK 数学核通过精确小状态核验" in " ".join("".join(s.itertext()).split()) for s in new) == 1, "title occurs on exactly one page")
    candidate_notes = [n for n in candidate.iter() if local(n.tag) == "note"]
    actual_notes = [n for n in added.iter() if local(n.tag) == "note"]
    check("speaker_notes", len(actual_notes) == 1 and len([n for n in actual_notes[0].iter() if local(n.tag) == "p"]) == 3, "three speaker-note paragraphs")
    check("native_structure", sum(local(n.tag) == "shape" for n in added.iter()) == sum(local(n.tag) == "shape" for n in candidate.iter()) and sum(local(n.tag) == "table" for n in added.iter()) == 1, "all native shapes and one table retained")
    check("no_external_media", not any(local(n.tag) in {"img", "embed"} for n in added.iter()), "no external media or embed")
    check("candidate_hash_lock", preflight["candidate_sha256"] == sha(args.candidate), "written candidate is the preflighted candidate")
    result = {"schema": "a8-rk09-minimal-slide-verification-v1", "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g", "slide_id": added.get("id"), "slide_number": len(new), "revision_id": readback_response["data"]["revision_id"], "source_sha256": sha(args.source), "candidate_sha256": sha(args.candidate), "readback_sha256": sha(args.readback), "old_pages_semantically_unchanged": not changed, "checks": checks, "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "all_pass": all(c["pass"] for c in checks)}
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"all_pass": result["all_pass"], "checks": f"{result['checks_passed']}/{result['checks_total']}", "slides": len(new), "slide_id": result["slide_id"]}))
    if not result["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
