
import json
import tempfile
import unittest
from pathlib import Path

from gpt_researcher.actions.evidence_store import EvidenceStore


def sample_result(stars=100):
    return {
        "title": "example/browser-agent",
        "href": "https://github.com/example/browser-agent",
        "raw_content": f"Repository: example/browser-agent\nStars: {stars}",
    }


class TestEvidenceStore(unittest.TestCase):

    def setUp(self):
        self.store = EvidenceStore()

    def test_capture(self):
        ids = self.store.add_search_results(
            "GitHubSearch", "browser agent", [sample_result()]
        )
        record = self.store.records[ids[0]]

        self.assertEqual(record.source, "GitHubSearch")
        self.assertEqual(record.content_kind, "raw_content")
        self.assertIn("Stars: 100", record.content)

    def test_deduplication(self):
        self.store.add_search_results(
            "GitHubSearch", "query 1", [sample_result(), sample_result()]
        )
        self.store.add_search_results(
            "GitHubSearch", "query 2", [sample_result()]
        )

        self.assertEqual(len(self.store.records), 1)
        record = next(iter(self.store.records.values()))
        self.assertEqual(record.queries, ["query 1", "query 2"])

    def test_changed_content(self):
        self.store.add_search_results(
            "GitHubSearch", "q", [sample_result(100)]
        )
        self.store.add_search_results(
            "GitHubSearch", "q", [sample_result(101)]
        )
        self.assertEqual(len(self.store.records), 2)

    def test_invalid_results(self):
        self.store.add_search_results(
            "TavilySearch",
            "q",
            [
                None,
                {"href": "file:///etc/passwd", "body": "x"},
                {"href": "https://example.com", "body": ""},
                {"href": "http://[broken", "body": "x"},
            ],
        )
        self.assertEqual(len(self.store.records), 0)

    def test_claim_link(self):
        eid = self.store.add_search_results(
            "GitHubSearch", "q", [sample_result()]
        )[0]

        claim = self.store.link_claim(
            "该仓库的 Star 数量为 100", [eid, eid]
        )

        self.assertEqual(claim.evidence_ids, [eid])
        self.assertEqual(claim.status, "unverified")

        with self.assertRaises(ValueError):
            self.store.link_claim("无来源结论", ["missing"])

    def test_json_export(self):
        self.store.add_search_results(
            "GitHubSearch", "q", [sample_result()]
        )

        with tempfile.TemporaryDirectory() as dirname:
            path = self.store.save_json(
                Path(dirname) / "evidence.json"
            )
            data = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(data["schema_version"], "0.1")
            self.assertEqual(len(data["evidence"]), 1)


if __name__ == "__main__":
    unittest.main()