from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import a8_rk05_cdgb_source_audit as audit  # noqa: E402
import a8_rk05_verify_cdgb_source_audit as verify  # noqa: E402


class CDGBSourceAuditHelpersTest(unittest.TestCase):
    def test_normalize_candidate_title_punctuation(self) -> None:
        variant = audit.CANDIDATE_TITLE.replace("de-optimization", "de—optimization").replace(":", " : ")
        self.assertEqual(audit.normalize_title(variant), audit.normalize_title(audit.CANDIDATE_TITLE))

    def test_candidate_and_doi_title_are_distinct(self) -> None:
        self.assertNotEqual(audit.normalize_title(audit.CANDIDATE_TITLE), audit.normalize_title(verify.EXPECTED_DOI_TITLE))

    def test_query_contract_is_complete_and_https(self) -> None:
        definitions = audit.query_definitions()
        self.assertEqual(len(definitions), 9)
        self.assertEqual({item["name"] for item in definitions}, verify.EXPECTED_QUERIES)
        self.assertTrue(all(item["url"].startswith("https://") for item in definitions))
        self.assertEqual(len({item["url"] for item in definitions}), 9)

    def test_extract_crossref_titles(self) -> None:
        payload = {"message": {"items": [{"title": ["one"]}, {"title": ["two"]}]}}
        self.assertEqual(audit.extract_titles("x", "crossref_search", payload), ["one", "two"])

    def test_extract_openalex_and_europepmc_titles(self) -> None:
        self.assertEqual(audit.extract_titles("x", "openalex_search", {"results": [{"display_name": "one"}]}), ["one"])
        payload = {"resultList": {"result": [{"title": "two"}]}}
        self.assertEqual(audit.extract_titles("x", "europepmc_search", payload), ["two"])

    def test_exact_candidate_match_is_not_fuzzy(self) -> None:
        payload = {"message": {"items": [{"title": [audit.CANDIDATE_TITLE]}, {"title": ["CDGB unrelated"]}]}}
        summary = audit.summarize_query("x", "crossref_search", payload)
        self.assertEqual(summary["exact_candidate_title_matches"], [audit.CANDIDATE_TITLE])
        self.assertEqual(summary["returned_title_or_repository_count"], 2)

    def test_github_summary_preserves_repository_identity(self) -> None:
        payload = {"total_count": 1, "items": [{"full_name": "example/CDGB", "html_url": "https://github.com/example/CDGB", "description": None, "owner": {"login": "example"}}]}
        summary = audit.summarize_query("x", "github_search", payload)
        self.assertEqual(summary["total_count_reported_by_github"], 1)
        self.assertEqual(summary["repositories"][0]["owner"], "example")
        self.assertNotIn("official", summary["repositories"][0])

    def test_independent_normalizer_rejects_doi_title_as_candidate(self) -> None:
        self.assertNotEqual(verify.norm(verify.EXPECTED_DOI_TITLE), verify.norm(audit.CANDIDATE_TITLE))
        self.assertEqual(verify.norm("CDGB: de-optimization"), verify.norm("cdgb de—optimization"))


if __name__ == "__main__":
    unittest.main()
