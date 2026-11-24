
import unittest
from datetime import datetime, timezone

from gpt_researcher.actions.evidence_store import EvidenceStore
from gpt_researcher.actions.decision_engine import DecisionEngine


NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)

BASE = (
    "Repository: example/repo\n"
    "Language: Python\n"
    "Archived: False\n"
    "Stars: 11000\n"
    "License: MIT\n"
    "Last pushed: 2026-10-20T00:00:00Z"
)


class TestDecisionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DecisionEngine(now=NOW)

    def make_store(self, content=BASE, source="GitHubSearch"):
        store = EvidenceStore()
        store.add_search_results(
            source=source,
            query="browser agent",
            results=[{
                "title": "example/repo",
                "href": "https://github.com/example/repo",
                "raw_content": content,
            }],
        )
        return store

    def evaluate(self, content=BASE):
        store = self.make_store(content)
        return self.engine.rank(store)[0]

    def test_eligible_score(self):
        result = self.evaluate()
        self.assertEqual(result["status"], "eligible")
        self.assertEqual(result["score"], 100)

    def test_wrong_language_excluded(self):
        content = BASE.replace(
            "Language: Python", "Language: TypeScript"
        )
        result = self.evaluate(content)
        self.assertEqual(result["status"], "excluded")
        self.assertIsNone(result["score"])

    def test_archived_excluded(self):
        content = BASE.replace(
            "Archived: False", "Archived: True"
        )
        self.assertEqual(
            self.evaluate(content)["status"], "excluded"
        )

    def test_missing_license(self):
        content = BASE.replace(
            "License: MIT", "License: Unknown"
        )
        result = self.evaluate(content)
        self.assertEqual(result["status"], "needs_review")
        self.assertIsNone(result["score"])

    def test_future_push_date(self):
        content = BASE.replace(
            "2026-10-20", "2026-11-20"
        )
        self.assertEqual(
            self.evaluate(content)["status"], "needs_review"
        )

    def test_report_contains_evidence(self):
        store = self.make_store()
        ranked = self.engine.rank(store)
        report = self.engine.render_markdown(ranked)

        self.assertIn(
            "https://github.com/example/repo", report
        )
        self.assertIn(
            ranked[0]["evidence_id"], report
        )

    def test_unrelated_sources_ignored(self):
        store = self.make_store(source="TavilySearch")
        self.assertEqual(self.engine.rank(store), [])


if __name__ == "__main__":
    unittest.main()