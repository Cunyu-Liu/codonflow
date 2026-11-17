from scripts.download_corpora import BIOMART_URL


def test_human_biomart_source_is_release_pinned():
    assert "release112.ensembl.org" in BIOMART_URL
    assert "www.ensembl.org" not in BIOMART_URL
