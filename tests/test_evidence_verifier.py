
import unittest

from gpt_researcher.actions.evidence_store import EvidenceStore
from gpt_researcher.actions.evidence_verifier import EvidenceVerifier


class TestEvidenceVerifier(unittest.TestCase):

    def setUp(self):
        self.store = EvidenceStore()
        self.verifier = EvidenceVerifier(self.store, recent_days=90)

    def add_evidence(self, content):
        return self.store.add_search_results(
            "GitHubSearch",
            "test query",
            [{
                "title": "example/project",
                "href": "https://github.com/example/project",
                "raw_content": content,
            }],
        )[0]

    def test_language_supported(self):
        eid = self.add_evidence(
            "Repository: example/project\nLanguage: Python"
        )
        claim = self.store.link_claim("项目主要使用 Python", [eid])

        result = self.verifier.verify_claim(claim)
        self.assertEqual(result["status"], "supported")

    def test_language_contradicted(self):
        eid = self.add_evidence(
            "Repository: example/project\nLanguage: JavaScript"
        )
        claim = self.store.link_claim("项目主要使用 Python", [eid])

        result = self.verifier.verify_claim(claim)
        self.assertEqual(result["status"], "contradicted")

    def test_missing_field_insufficient(self):
        eid = self.add_evidence(
            "Repository: example/project\nDescription: Browser automation"
        )
        claim = self.store.link_claim("项目主要使用 Python", [eid])

        result = self.verifier.verify_claim(claim)
        self.assertEqual(result["status"], "insufficient")

    def test_star_count(self):
        eid = self.add_evidence(
            "Repository: example/project\nStars: 125"
        )
        claim = self.store.link_claim("Stars: 125", [eid])

        result = self.verifier.verify_claim(claim)
        self.assertEqual(result["status"], "supported")

    def test_unsupported_claim_type(self):
        eid = self.add_evidence(
            "Repository: example/project\nLanguage: Python"
        )
        claim = self.store.link_claim(
            "项目适合生产环境", [eid]
        )

        result = self.verifier.verify_claim(claim)
        self.assertEqual(result["status"], "insufficient")

    def test_result_contains_traceability(self):
        eid = self.add_evidence(
            "Repository: example/project\nLanguage: Python"
        )
        claim = self.store.link_claim("项目主要使用 Python", [eid])

        result = self.verifier.verify_claim(claim)

        self.assertIn(eid, result["evidence_ids"])
        self.assertIn("reason", result)
        self.assertIn("verified_at", result)


if __name__ == "__main__":
    unittest.main()