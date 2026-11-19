#!/usr/bin/env python3
"""Evidence-only pre/post verification for the bounded source-feasibility slide."""
import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TITLE = "Ribo/VeloHARMO 来源可恢复，但本轮未执行重比对"
EXPECTED_COMMIT = "c5046b9c25a700f6231f0411b95f4d881dcda5d8"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def local(tag):
    return tag.rsplit("}", 1)[-1]


def children(element, name):
    return [child for child in list(element) if local(child.tag) == name]


def first(element, name):
    return next((child for child in list(element) if local(child.tag) == name), None)


def descendants(element, name):
    return [item for item in element.iter() if local(item.tag) == name]


def text(element):
    return "".join(element.itertext()) if element is not None else ""


def paragraph_texts(slide, include_notes=True):
    data = first(slide, "data")
    values = [text(p) for p in descendants(data, "p")] if data is not None else []
    if include_notes:
        note = first(slide, "note")
        values.extend(text(p) for p in descendants(note, "p")) if note is not None else None
    return values


def table_rows(slide):
    table = next(iter(descendants(slide, "table")), None)
    if table is None:
        return []
    return [[text(td).strip() for td in descendants(tr, "td")] for tr in children(table, "tr")]


def semantic(element, ignore_ids=False):
    attribute_map = {k: v for k, v in element.attrib.items() if not (ignore_ids and k == "id")}
    # The Slides service materializes the schema default col@span=1 on readback.
    # Normalize that explicit default only; all other attributes remain strict.
    if local(element.tag) == "col":
        attribute_map.setdefault("span", "1")
    attributes = tuple(sorted(attribute_map.items()))
    value = element.text or ""
    if not value.strip():
        value = ""
    return (element.tag, attributes, value, tuple(semantic(c, ignore_ids) for c in list(element)))


def slides_from(path):
    root = ET.parse(path).getroot()
    if local(root.tag) == "presentation":
        return children(root, "slide")
    if local(root.tag) == "slide":
        return [root]
    raise ValueError(f"Unsupported XML root: {root.tag}")


def expected_rows(production):
    organisms = {
        "Mohammad16": "E. coli",
        "Grady17": "P. aeruginosa",
        "Dunn13": "D. melanogaster",
        "Pop14": "S. cerevisiae",
        "Battle15": "human",
        "Mohammad19": "E. coli",
        "Subtelny14": "S. cerevisiae",
    }
    release = {
        "Mohammad16": "matrix + GA",
        "Grady17": "none",
        "Dunn13": "none",
        "Pop14": "yeast GA",
        "Battle15": "none",
        "Mohammad19": "n/a",
        "Subtelny14": "n/a",
    }
    records = list(production["veloharmo_organism_feasibility"])
    records.extend(x for x in production["ribomimo_raw_feasibility"] if x["label"] != "Mohammad16")
    rows = [["Study", "Organism", "Source", "RunInfo", "Runs", "MB", "Velo release"]]
    for record in records:
        label = record["label"]
        source = record.get("source_accession", record.get("accession"))
        raw = record["raw_source"]
        rows.append([
            label,
            organisms[label],
            source,
            raw["runinfo_accessions"][0],
            str(raw["run_count"]),
            f'{raw["size_mb"]:,}',
            release[label],
        ])
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pre", "post"], required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--baseline-xml", required=True)
    parser.add_argument("--baseline-response", required=True)
    parser.add_argument("--production", required=True)
    parser.add_argument("--independent", required=True)
    parser.add_argument("--finalization", required=True)
    parser.add_argument("--paper-verification", required=True)
    parser.add_argument("--post-xml")
    parser.add_argument("--post-response")
    parser.add_argument("--write-response")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    production = load_json(args.production)
    independent = load_json(args.independent)
    finalization = load_json(args.finalization)
    paper = load_json(args.paper_verification)
    baseline_response = load_json(args.baseline_response)
    baseline = slides_from(args.baseline_xml)
    candidate = slides_from(args.candidate)[0]
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("production_74_of_74", production["overall_pass"] and production["check_counts"] == {"total": 74, "passed": 74, "failed": 0}, production["check_counts"])
    check("production_terminal_state", production["status"] == "SOURCE_METADATA_RECOVERABLE_REMAP_NOT_PERFORMED", production["status"])
    check("independent_169_of_169", independent["independent_pass"] and independent["check_counts"] == {"total": 169, "passed": 169, "failed": 0}, independent["check_counts"])
    check("independent_numeric_delta_zero", independent["production_independent_max_numeric_delta"] == 0, independent["production_independent_max_numeric_delta"])
    check("finalization_47_of_47", finalization["overall_pass"] and finalization["check_counts"] == {"total": 47, "passed": 47, "failed": 0}, finalization["check_counts"])
    check("bounded_audit_closed_only", finalization["bounded_source_feasibility_closed"] is True and finalization["raw_read_or_p_site_remapping_completed"] is False)
    check("paper_61_of_61", paper["status"] == "PASS" and paper["checks_passed"] == 61 and paper["checks_total"] == 61)
    check("paper_30_of_30_facts", paper["candidate_facts_passed"] == 30 and paper["candidate_facts_total"] == 30)
    check("manuscript_remains_non_submittable", paper["submittable"] is False)
    check("baseline_read_ok", baseline_response.get("ok") is True and baseline_response.get("data", {}).get("revision_id") == 64)
    check("baseline_102_pages", len(baseline) == 102, len(baseline))
    baseline_ids = [s.attrib.get("id") for s in baseline]
    check("baseline_last_pages_preserved", baseline_ids[-2:] == ["pgI", "pgj"], baseline_ids[-2:])
    check("baseline_title_not_already_present", sum(TITLE in paragraph_texts(s) for s in baseline) == 0)

    velo = production["veloharmo_organism_feasibility"]
    extras = [x for x in production["ribomimo_raw_feasibility"] if x["label"] != "Mohammad16"]
    velo_runs = sum(x["raw_source"]["run_count"] for x in velo)
    velo_mb = sum(x["raw_source"]["size_mb"] for x in velo)
    extra_runs = sum(x["raw_source"]["run_count"] for x in extras)
    extra_mb = sum(x["raw_source"]["size_mb"] for x in extras)
    runinfo = production["runinfo_evidence"]
    total_runs = sum(x["run_count"] for x in runinfo.values())
    total_mb = sum(x["size_mb"] for x in runinfo.values())
    check("computed_veloharmo_totals", (len(velo), velo_runs, velo_mb) == (5, 125, 143663), [len(velo), velo_runs, velo_mb])
    check("computed_ribomimo_extra_totals", (len(extras), extra_runs, extra_mb) == (2, 13, 9236), [len(extras), extra_runs, extra_mb])
    check("computed_distinct_runinfo_totals", (len(runinfo), total_runs, total_mb) == (7, 138, 152899), [len(runinfo), total_runs, total_mb])
    check("no_large_reads_downloaded", production["large_read_files_downloaded"] == [])
    check("utr_cds_not_constructed", production["utr_cds_and_site_protocol"]["utr_cds_mapping_completed"] is False)
    check("raw_remapping_not_performed", production["utr_cds_and_site_protocol"]["raw_read_remapping_completed"] is False)
    check("rk_g1_open", production["boundaries"]["rk_g1_closed"] is False and finalization["rk_g1_closed"] is False)
    check("no_generator_training_authorization", production["boundaries"]["expensive_generator_training_authorized"] is False)

    repo = production["pinned_repository"]
    check("correct_repository_and_commit", repo["repository"] == "https://github.com/BianBian2021/VeloHARMO" and repo["commit"] == "38b48079856aeb9d33a1b10844d77aa8f6640032")
    check("fixed_tree_14_files", len(repo["files"]) == 14)
    check("fixed_files_current_hashes_match", all(x["bytes"] == x["current_bytes"] and x["sha256"] == x["current_sha256"] for x in repo["files"]))
    zips = [x for x in repo["files"] if x["path"] in repo["harmonized_matrix_zips"]]
    check("two_identical_ecoli_zips", len(zips) == 2 and zips[0]["sha256"] == zips[1]["sha256"])
    check("only_ecoli_matrix_released", all("E.coli" in x for x in repo["harmonized_matrix_zips"]) and len(repo["harmonized_matrix_zips"]) == 2)
    check("only_ecoli_and_yeast_ga", len(repo["ga_checkpoints"]) == 2 and any("E.coli" in x for x in repo["ga_checkpoints"]) and any("yeast" in x for x in repo["ga_checkpoints"]))
    check("four_non_ecoli_matrices_absent", sum(not x["released_harmonized_matrix_in_pinned_repo"] for x in velo) == 4)
    check("subtelny_bioproject_fallback", runinfo["PRJNA231671"]["run_count"] == 3 and runinfo["PRJNA231671"]["size_mb"] == 4034)
    check("dunn_pop_mapping_correct", next(x for x in velo if x["label"] == "Dunn13")["organism"] == "Drosophila melanogaster" and next(x for x in velo if x["label"] == "Pop14")["organism"] == "Saccharomyces cerevisiae")

    actual_rows = table_rows(candidate)
    wanted_rows = expected_rows(production)
    check("candidate_table_exactly_matches_production", actual_rows == wanted_rows, {"expected": wanted_rows, "actual": actual_rows})
    candidate_text = "\n".join(paragraph_texts(candidate, include_notes=True))
    required_text = [
        "169/169 + 47/47 · VERIFIED", "125 runs", "5 studies · 143,663 MB metadata",
        "13 runs", "2 studies · 9,236 MB metadata", "NOT REMAPPED",
        "7 RunInfo accessions", "138 runs · 152,899 MB", "14/14 fixed files rehashed",
        "2 byte-identical E. coli ZIPs", "4 non-E. coli matrices absent",
        "raw / GA ≠ harmonized matrix", "未下载 reads", "未构建 UTR–CDS", "未重比对",
        "RK-G1 未关闭", "production 74/74", "independent 169/169", "final 47/47", "paper 61/61",
        "GitHub c5046b9c25a7", "SOURCE_METADATA_RECOVERABLE_REMAP_NOT_PERFORMED",
        EXPECTED_COMMIT,
    ]
    missing = [x for x in required_text if x not in candidate_text]
    check("candidate_required_facts_and_boundaries", not missing, missing)
    check("candidate_has_five_note_paragraphs", len(descendants(first(candidate, "note"), "p")) == 5)
    check("candidate_has_no_external_images", all(not (img.attrib.get("src", "").startswith("http://") or img.attrib.get("src", "").startswith("https://")) for img in descendants(candidate, "img")))
    geometry_ok = True
    for element in descendants(candidate, "shape") + descendants(candidate, "table") + descendants(candidate, "img"):
        try:
            x, y = float(element.attrib["topLeftX"]), float(element.attrib["topLeftY"])
            w, h = float(element.attrib["width"]), float(element.attrib["height"])
            geometry_ok = geometry_ok and x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540
        except (KeyError, ValueError):
            geometry_ok = False
    check("candidate_elements_within_canvas", geometry_ok)

    post_summary = None
    if args.mode == "post":
        if not args.post_xml or not args.post_response or not args.write_response:
            raise ValueError("post mode requires --post-xml, --post-response and --write-response")
        post_response = load_json(args.post_response)
        write_response = load_json(args.write_response)
        post = slides_from(args.post_xml)
        post_ids = [s.attrib.get("id") for s in post]
        check("write_response_ok", write_response.get("ok") is True and write_response.get("data", {}).get("slide_id"))
        check("post_read_ok", post_response.get("ok") is True)
        check("post_103_pages", len(post) == 103, len(post))
        check("post_revision_advanced", post_response.get("data", {}).get("revision_id", -1) > 64, post_response.get("data", {}).get("revision_id"))
        check("previous_page_ids_unchanged", post_ids[:102] == baseline_ids)
        changed = [baseline_ids[i] for i in range(102) if semantic(baseline[i]) != semantic(post[i])]
        check("previous_102_pages_semantically_unchanged", not changed, changed)
        new_slide = post[-1]
        new_id = new_slide.attrib.get("id")
        check("new_page_id_matches_write_response", new_id == write_response.get("data", {}).get("data", {}).get("slide_id", write_response.get("data", {}).get("slide_id")), new_id)
        check("new_page_id_is_distinct", new_id not in baseline_ids, new_id)
        check("new_page_content_preserved", paragraph_texts(new_slide) == paragraph_texts(candidate))
        check("new_page_table_preserved", table_rows(new_slide) == wanted_rows)
        check("new_page_semantics_preserved_ignoring_assigned_ids", semantic(new_slide, ignore_ids=True) == semantic(candidate, ignore_ids=True))
        check("title_appears_exactly_once", sum(TITLE in paragraph_texts(s) for s in post) == 1)
        post_summary = {"new_slide_id": new_id, "new_page_number": 103, "revision_id": post_response.get("data", {}).get("revision_id")}

    report = {
        "schema": "a8_rk03_source_feasibility_ppt_verification_v1",
        "mode": args.mode,
        "status": "PASS" if all(x["pass"] for x in checks) else "FAIL",
        "check_counts": {"total": len(checks), "passed": sum(x["pass"] for x in checks), "failed": sum(not x["pass"] for x in checks)},
        "checks": checks,
        "input_sha256": {name: sha256(getattr(args, name)) for name in ["candidate", "baseline_xml", "baseline_response", "production", "independent", "finalization", "paper_verification"]},
        "scientific_scope": "Metadata-only source feasibility; no read download, UTR-CDS construction, P-site remapping, mechanism validation or model result.",
        "xml_normalization": "Only schema-default col@span=1 and server-assigned IDs are normalized in the new-page semantic comparison; text, table values, geometry and all other attributes remain strict.",
        "postwrite": post_summary,
    }
    if args.mode == "post":
        report["input_sha256"].update({name: sha256(getattr(args, name)) for name in ["post_xml", "post_response", "write_response"]})
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": f'{report["check_counts"]["passed"]}/{report["check_counts"]["total"]}', "postwrite": post_summary}, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        for item in checks:
            if not item["pass"]:
                print("FAIL", item["name"], json.dumps(item["detail"], ensure_ascii=False)[:2000], file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
