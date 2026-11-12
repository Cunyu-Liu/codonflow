import json

import pytest

from scripts.a7_species_audit import audit_species, species_for_header


def test_species_identifier_conventions():
    assert species_for_header("ENST00000641515.2") == "homo_sapiens"
    assert species_for_header("ENSECAT00000031957.1") == "equus_caballus"
    assert species_for_header("ENSOCUT00000027669.2") == "oryctolagus_cuniculus"
    assert species_for_header("ENSOART00000000039.1") == "ovis_aries"
    assert species_for_header("ENSORLT00000032594.1") == "oryzias_latipes"
    assert species_for_header("FBtr0343930") == "drosophila_melanogaster"
    assert species_for_header("YDR387C_mRNA") == "saccharomyces_cerevisiae"
    assert species_for_header("C55C2.5a.1") == "caenorhabditis_elegans"


def test_unknown_ensembl_prefix_fails():
    with pytest.raises(ValueError, match="unmapped Ensembl"):
        species_for_header("ENSUNKNOWN00001")


def test_species_audit_counts_and_map(tmp_path):
    fasta = tmp_path / "records.fasta"
    fasta.write_text(">ENST00001\nATGTAA\n>FBtr01\nATGTAA\n>C55C2.5a.1\nATGTAA\n")
    map_out = tmp_path / "species.json"
    result = audit_species([fasta], map_out)
    row = result["records"][0]
    assert row["n"] == 3 and row["n_species"] == 3
    assert row["species_counts"]["homo_sapiens"] == 1
    assert len(json.loads(map_out.read_text())) == 3
