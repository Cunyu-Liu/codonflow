import copy
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("yu_response", ROOT / "scripts" / "a10_03_yu_local_response.py")
yu = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(yu)


def write_gzip(path, text):
    with gzip.open(path, "wt", encoding="ascii") as handle:
        handle.write(text)


def synthetic_protocol(tmp_path):
    protocol = yu.load_protocol(ROOT / "configs" / "a10_03_yu_local_response_protocol_v1.json")
    protocol = copy.deepcopy(protocol)
    protocol["geometry"] = {
        "reporter_length_nt": 18,
        "cds_start_zero_based": 3,
        "cds_end_zero_based_exclusive": 15,
        "edited_sense_codon_first_one_based": 3,
        "edited_sense_codon_last_one_based": 3,
        "terminal_stop_included_in_sense_edit": False,
        "downstream_coding_region_available": False,
    }
    paths = {}
    sequences = {"opt": "AAATTTGGGCCCTGAAAA", "cwt_opt": "AAATTTGGGCCATGAAAA"}
    wigs = {
        "opt": "Opt_luc\t0\t3\t0\nOpt_luc\t3\t9\t1\nOpt_luc\t9\t12\t2\nOpt_luc\t12\t18\t1\n",
        "cwt_opt": "Cwt-Opt_luc\t0\t3\t0\nCwt-Opt_luc\t3\t9\t2\nCwt-Opt_luc\t9\t12\t6\nCwt-Opt_luc\t12\t18\t2\n",
    }
    for arm, config in protocol["constructs"].items():
        fasta = tmp_path / f"{arm}.fa.gz"
        wig = tmp_path / f"{arm}.wig.gz"
        write_gzip(fasta, f">{config['reporter']}\n{sequences[arm]}\n")
        write_gzip(wig, wigs[arm])
        config["fasta_sha256"] = yu.sha256_file(fasta)
        config["wig_sha256"] = yu.sha256_file(wig)
        paths[arm] = {"fasta": fasta, "wig": wig}
    return protocol, paths


def test_synonymous_codon_response_and_two_scales(tmp_path):
    protocol, paths = synthetic_protocol(tmp_path)
    rows, summary = yu.analyze(protocol, paths)
    assert summary["qc"]["protein_identical"] is True
    assert summary["qc"]["wig_complete_contiguous_coverage"] is True
    edited = [row for row in rows if row["region"] == "edited_sense"]
    assert len(edited) == 1
    assert edited[0]["cwt_opt_minus_opt_rpm"] == pytest.approx(4.0)
    assert edited[0]["cwt_opt_minus_opt_upstream_normalized"] == pytest.approx(1.0)
    assert summary["statistical_inference"]["p_values"] is None
    assert summary["qc"]["downstream_coding_region_available"] is False


def test_incomplete_wig_fails_closed(tmp_path):
    protocol, paths = synthetic_protocol(tmp_path)
    write_gzip(paths["opt"]["wig"], "Opt_luc\t0\t9\t1\n")
    protocol["constructs"]["opt"]["wig_sha256"] = yu.sha256_file(paths["opt"]["wig"])
    with pytest.raises(ValueError, match="continuously cover"):
        yu.analyze(protocol, paths)


def test_nonsynonymous_change_is_rejected(tmp_path):
    protocol, paths = synthetic_protocol(tmp_path)
    write_gzip(paths["cwt_opt"]["fasta"], ">Cwt-Opt_luc\nAAATTTGGGCTTTGAAAA\n")
    protocol["constructs"]["cwt_opt"]["fasta_sha256"] = yu.sha256_file(paths["cwt_opt"]["fasta"])
    with pytest.raises(ValueError, match="proteins differ"):
        yu.analyze(protocol, paths)
